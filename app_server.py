from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping
from urllib.parse import urlparse

from llm_planner import LLMPlannerError, generate_day_plan_with_llm
from nutrition_planner import (
    ACTIVITY_MULTIPLIERS,
    Ingredient,
    MacroTargets,
    Meal,
    MealLogger,
    NutritionPlanner,
    UserProfile,
    build_daily_report,
    build_day_totals,
    generate_day_plan_from_preferences,
)


ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
MEAL_LOG_PATH = ROOT / "meal_logs.jsonl"


def ingredient_to_dict(ingredient: Ingredient) -> Dict[str, Any]:
    return {
        "name": ingredient.name,
        "grams": ingredient.grams,
        "kcal_per_g": ingredient.kcal_per_g,
        "protein_per_g": ingredient.protein_per_g,
        "carbs_per_g": ingredient.carbs_per_g,
        "fats_per_g": ingredient.fats_per_g,
        "calories": ingredient.calories,
    }


def meal_to_dict(meal: Meal) -> Dict[str, Any]:
    return {
        "name": meal.name,
        "calories": meal.calories,
        "macros": meal.macro_totals(),
        "ingredients": [ingredient_to_dict(item) for item in meal.ingredients],
    }


def day_plan_to_dict(day_plan: Mapping[str, Meal]) -> Dict[str, Any]:
    return {meal_name: meal_to_dict(meal) for meal_name, meal in day_plan.items()}


def parse_profile(payload: Mapping[str, Any]) -> UserProfile:
    try:
        profile = UserProfile(
            height_cm=float(payload["height_cm"]),
            weight_kg=float(payload["weight_kg"]),
            workout_level=str(payload["workout_level"]).strip().lower(),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Profile must include numeric height_cm, weight_kg, and workout_level.") from exc
    if profile.workout_level not in ACTIVITY_MULTIPLIERS:
        raise ValueError(f"Unsupported workout level: {profile.workout_level}")
    if profile.height_cm <= 0 or profile.weight_kg <= 0:
        raise ValueError("Height and weight must be positive values.")
    return profile


def parse_targets(payload: Mapping[str, Any]) -> MacroTargets:
    try:
        return MacroTargets(
            calories=float(payload["calories"]),
            protein_g=float(payload["protein_g"]),
            carbs_g=float(payload["carbs_g"]),
            fats_g=float(payload["fats_g"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Invalid target payload.") from exc


def parse_meal(payload: Mapping[str, Any]) -> Meal:
    if "name" not in payload or "ingredients" not in payload:
        raise ValueError("Meal payload must include name and ingredients.")
    ingredients = []
    for item in payload["ingredients"]:
        ingredients.append(
            Ingredient(
                name=str(item["name"]),
                grams=float(item["grams"]),
                kcal_per_g=float(item["kcal_per_g"]),
                protein_per_g=float(item.get("protein_per_g", 0.0)),
                carbs_per_g=float(item.get("carbs_per_g", 0.0)),
                fats_per_g=float(item.get("fats_per_g", 0.0)),
            )
        )
    return Meal(name=str(payload["name"]), ingredients=ingredients)


def parse_day_plan(payload: Mapping[str, Any]) -> Dict[str, Meal]:
    day_plan: Dict[str, Meal] = {}
    for meal_name, meal_payload in payload.items():
        meal = parse_meal(meal_payload)
        day_plan[str(meal_name)] = meal
    return day_plan


def within_limits(actual: Mapping[str, float], targets: MacroTargets, tolerance: float = 0.1) -> Dict[str, bool]:
    def in_range(value: float, target: float) -> bool:
        return target * (1 - tolerance) <= value <= target * (1 + tolerance)

    return {
        "calories": in_range(actual["calories"], targets.calories),
        "protein_g": in_range(actual["protein_g"], targets.protein_g),
        "carbs_g": in_range(actual["carbs_g"], targets.carbs_g),
        "fats_g": in_range(actual["fats_g"], targets.fats_g),
    }


class NutritionRequestHandler(SimpleHTTPRequestHandler):
    server_version = "NutritionPlannerHTTP/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/ingredients":
            payload = {
                "workout_levels": list(ACTIVITY_MULTIPLIERS.keys()),
                "llm_enabled": bool(os.getenv("OPENAI_API_KEY", "").strip()),
            }
            self._send_json(payload)
            return
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "llm_enabled": bool(os.getenv("OPENAI_API_KEY", "").strip())})
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            body = self._read_json()
            if parsed.path == "/api/plan":
                self._handle_plan(body)
                return
            if parsed.path == "/api/llm-plan":
                self._handle_llm_plan(body)
                return
            if parsed.path == "/api/rebalance":
                self._handle_rebalance(body)
                return
            if parsed.path == "/api/log":
                self._handle_log(body)
                return
            if parsed.path == "/api/report":
                self._handle_report(body)
                return
            self._send_json({"error": "Unknown endpoint."}, status=HTTPStatus.NOT_FOUND)
        except LLMPlannerError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # pragma: no cover
            self._send_json({"error": f"Internal server error: {exc}"}, status=HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_plan(self, body: Mapping[str, Any]) -> None:
        profile = parse_profile(body.get("profile", {}))
        preferences = body.get("preferences", {})
        planner = NutritionPlanner(profile, {})
        targets = planner.daily_targets()
        day_plan = generate_day_plan_from_preferences(targets, preferences=preferences)
        totals = build_day_totals(day_plan)
        self._send_json(
            {
                "targets": asdict(targets),
                "plan": day_plan_to_dict(day_plan),
                "day_totals": totals,
                "within_limits": within_limits(totals, targets),
            }
        )

    def _handle_llm_plan(self, body: Mapping[str, Any]) -> None:
        profile = parse_profile(body.get("profile", {}))
        ingredients_by_meal = body.get("ingredients_by_meal", {})
        extra_preferences = str(body.get("extra_preferences", "")).strip()
        model_override = str(body.get("model", "")).strip() or None

        planner = NutritionPlanner(profile, {})
        targets = planner.daily_targets()
        day_plan, llm_metadata = generate_day_plan_with_llm(
            profile=profile,
            targets=targets,
            ingredients_by_meal=ingredients_by_meal,
            extra_preferences=extra_preferences,
            model=model_override,
        )
        totals = build_day_totals(day_plan)
        self._send_json(
            {
                "targets": asdict(targets),
                "plan": day_plan_to_dict(day_plan),
                "day_totals": totals,
                "within_limits": within_limits(totals, targets),
                "llm": llm_metadata,
            }
        )

    def _handle_rebalance(self, body: Mapping[str, Any]) -> None:
        if "meal" not in body:
            raise ValueError("Rebalance payload must include meal.")
        if "ingredient_name" not in body:
            raise ValueError("Rebalance payload must include ingredient_name.")
        if "new_grams" not in body:
            raise ValueError("Rebalance payload must include new_grams.")

        meal = parse_meal(body["meal"])
        ingredient_name = str(body["ingredient_name"])
        new_grams = float(body["new_grams"])
        updated_meal = meal.rebalance_ingredient(ingredient_name, new_grams)

        response: Dict[str, Any] = {"meal": meal_to_dict(updated_meal)}
        if "day_plan" in body:
            day_plan = parse_day_plan(body["day_plan"])
            day_plan[updated_meal.name] = updated_meal
            totals = build_day_totals(day_plan)
            response["day_plan"] = day_plan_to_dict(day_plan)
            response["day_totals"] = totals
            if "targets" in body:
                targets = parse_targets(body["targets"])
                response["within_limits"] = within_limits(totals, targets)

        self._send_json(response)

    def _handle_log(self, body: Mapping[str, Any]) -> None:
        date_raw = str(body.get("date", "")).strip()
        if not date_raw:
            raise ValueError("Log payload must include date.")
        try:
            when = date.fromisoformat(date_raw)
        except ValueError as exc:
            raise ValueError("Date must be in YYYY-MM-DD format.") from exc

        meal_payloads = body.get("meals", [])
        if not isinstance(meal_payloads, list):
            raise ValueError("Meals must be a list.")
        meals = [parse_meal(item) for item in meal_payloads]
        if not meals:
            raise ValueError("At least one meal is required to log.")

        logger = MealLogger(str(MEAL_LOG_PATH))
        for meal in meals:
            logger.log_meal(when, meal.name, meal)

        logged_today = logger.meals_for_date(when)
        self._send_json(
            {
                "date": when.isoformat(),
                "logged_count": len(meals),
                "total_logged_meals_for_day": len(logged_today),
            }
        )

    def _handle_report(self, body: Mapping[str, Any]) -> None:
        profile = parse_profile(body.get("profile", {}))
        date_raw = str(body.get("date", "")).strip()
        if not date_raw:
            raise ValueError("Report payload must include date.")
        try:
            when = date.fromisoformat(date_raw)
        except ValueError as exc:
            raise ValueError("Date must be in YYYY-MM-DD format.") from exc

        targets = NutritionPlanner(profile, {}).daily_targets()
        logger = MealLogger(str(MEAL_LOG_PATH))
        meals = logger.meals_for_date(when)
        report = build_daily_report(targets, meals)

        self._send_json(
            {
                "date": when.isoformat(),
                "meal_count": len(meals),
                **report,
            }
        )

    def _read_json(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
        if not raw:
            return {}
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        if not isinstance(body, dict):
            raise ValueError("Request body must be a JSON object.")
        return body

    def _send_json(self, payload: Mapping[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def run_server(port: int = 8000) -> None:
    WEB_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), NutritionRequestHandler)
    print(f"Nutrition planning app available at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopping server...")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the nutrition planning web app.")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the app server on.")
    args = parser.parse_args()
    run_server(port=args.port)


if __name__ == "__main__":
    main()

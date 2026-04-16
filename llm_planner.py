from __future__ import annotations

from dataclasses import asdict
import json
import os
import re
from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple
from urllib import error, request

from nutrition_planner import Ingredient, MacroTargets, Meal, UserProfile, build_day_totals


MEAL_NAMES = ("breakfast", "lunch", "dinner")
DEFAULT_MODEL = "gpt-4.1-mini"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


class LLMPlannerError(ValueError):
    pass


def parse_ingredient_lines(value: Any) -> List[str]:
    if isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        raw_items = re.split(r"[\n,;]+", str(value or ""))

    output: List[str] = []
    seen = set()
    for item in raw_items:
        cleaned = re.sub(r"\s+", " ", item).strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        output.append(cleaned)
    return output


def normalize_ingredients_by_meal(payload: Mapping[str, Any] | None) -> Dict[str, List[str]]:
    payload = payload or {}
    output: Dict[str, List[str]] = {}
    for meal_name in MEAL_NAMES:
        options = parse_ingredient_lines(payload.get(meal_name, []))
        if not options:
            raise LLMPlannerError(f"Please provide at least one ingredient for {meal_name}.")
        output[meal_name] = options
    return output


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _word_set(value: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", value.lower()) if part}


def _match_allowed_name(raw_name: str, allowed: Sequence[str]) -> str | None:
    raw_norm = _normalize_token(raw_name)
    raw_words = _word_set(raw_name)
    for candidate in allowed:
        candidate_norm = _normalize_token(candidate)
        if raw_norm == candidate_norm:
            return candidate
        if raw_norm and (raw_norm in candidate_norm or candidate_norm in raw_norm):
            return candidate
        if raw_words and raw_words.intersection(_word_set(candidate)):
            return candidate
    return None


def _coerce_float(value: Any, field: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise LLMPlannerError(f"Invalid numeric value for {field}: {value}") from exc
    if numeric < 0:
        raise LLMPlannerError(f"{field} cannot be negative.")
    return numeric


def _extract_text_content(response_payload: Mapping[str, Any]) -> str:
    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    parts: List[str] = []
    for output_item in response_payload.get("output", []):
        if not isinstance(output_item, Mapping):
            continue
        for content in output_item.get("content", []):
            if not isinstance(content, Mapping):
                continue
            if content.get("type") in {"output_text", "text"}:
                text_value = content.get("text")
                if isinstance(text_value, str):
                    parts.append(text_value)
                elif isinstance(text_value, Mapping):
                    maybe_value = text_value.get("value")
                    if isinstance(maybe_value, str):
                        parts.append(maybe_value)
    combined = "\n".join(part for part in parts if part.strip()).strip()
    if not combined:
        raise LLMPlannerError("LLM did not return any text output.")
    return combined


def extract_json_object(text: str) -> Dict[str, Any]:
    candidate = text.strip()
    if not candidate:
        raise LLMPlannerError("LLM response was empty.")

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for index, char in enumerate(candidate):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(candidate[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise LLMPlannerError("LLM response was not valid JSON.")


def _call_openai(system_prompt: str, user_prompt: str, model: str) -> Tuple[str, str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise LLMPlannerError("OPENAI_API_KEY is not set. Add it before generating an LLM meal plan.")

    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_output_tokens": 1400,
    }
    encoded = json.dumps(payload).encode("utf-8")
    req = request.Request(
        OPENAI_RESPONSES_URL,
        data=encoded,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise LLMPlannerError(f"LLM request failed ({exc.code}): {detail[:240]}") from exc
    except error.URLError as exc:
        raise LLMPlannerError(f"Could not reach LLM service: {exc.reason}") from exc

    payload_json = json.loads(raw)
    output_text = _extract_text_content(payload_json)
    used_model = str(payload_json.get("model") or model)
    return output_text, used_model


def _build_meals_from_llm_plan(
    plan_payload: Mapping[str, Any],
    ingredients_by_meal: Mapping[str, Sequence[str]],
) -> Dict[str, Meal]:
    meals_blob = plan_payload.get("meals")
    if not isinstance(meals_blob, Mapping):
        raise LLMPlannerError("LLM output must include a 'meals' object.")

    meals: Dict[str, Meal] = {}
    for meal_name in MEAL_NAMES:
        items = meals_blob.get(meal_name)
        if not isinstance(items, list) or not items:
            raise LLMPlannerError(f"LLM output missing ingredients for {meal_name}.")
        allowed_ingredients = ingredients_by_meal.get(meal_name, [])
        ingredient_list: List[Ingredient] = []
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                raise LLMPlannerError(f"Invalid ingredient entry for {meal_name} at index {index}.")
            raw_name = str(item.get("name", "")).strip()
            if not raw_name:
                raise LLMPlannerError(f"Ingredient name missing for {meal_name} at index {index}.")
            matched_name = _match_allowed_name(raw_name, allowed_ingredients)
            if not matched_name:
                raise LLMPlannerError(
                    f"LLM used '{raw_name}' for {meal_name}, which is outside your provided ingredients."
                )
            grams = _coerce_float(item.get("grams"), f"{meal_name}.{raw_name}.grams")
            kcal_per_g = _coerce_float(item.get("kcal_per_g"), f"{meal_name}.{raw_name}.kcal_per_g")
            if kcal_per_g <= 0:
                raise LLMPlannerError(f"{meal_name}.{raw_name}.kcal_per_g must be greater than zero.")
            protein_per_g = _coerce_float(item.get("protein_per_g", 0.0), f"{meal_name}.{raw_name}.protein_per_g")
            carbs_per_g = _coerce_float(item.get("carbs_per_g", 0.0), f"{meal_name}.{raw_name}.carbs_per_g")
            fats_per_g = _coerce_float(item.get("fats_per_g", 0.0), f"{meal_name}.{raw_name}.fats_per_g")

            ingredient_list.append(
                Ingredient(
                    name=matched_name,
                    grams=grams,
                    kcal_per_g=kcal_per_g,
                    protein_per_g=protein_per_g,
                    carbs_per_g=carbs_per_g,
                    fats_per_g=fats_per_g,
                )
            )
        if not ingredient_list:
            raise LLMPlannerError(f"LLM output resulted in empty ingredient list for {meal_name}.")
        meals[meal_name] = Meal(name=meal_name, ingredients=ingredient_list)
    return meals


def _scale_day_plan_to_target_calories(day_plan: Dict[str, Meal], target_calories: float) -> Dict[str, Meal]:
    if target_calories <= 0:
        return day_plan
    totals = build_day_totals(day_plan)
    current = totals["calories"]
    if current <= 0:
        raise LLMPlannerError("LLM returned a plan with zero calories.")
    scale = target_calories / current
    return {
        meal_name: Meal(
            name=meal.name,
            ingredients=[ingredient.scale_to_grams(ingredient.grams * scale) for ingredient in meal.ingredients],
        )
        for meal_name, meal in day_plan.items()
    }


def _build_llm_prompts(
    profile: UserProfile,
    targets: MacroTargets,
    ingredients_by_meal: Mapping[str, Sequence[str]],
    extra_preferences: str | None,
) -> Tuple[str, str]:
    system_prompt = (
        "You are a precise sports nutrition planner. Build one day meal plan for breakfast, lunch, and dinner "
        "using only ingredients provided by the user. Return strict JSON only with no markdown."
    )
    user_payload = {
        "instructions": {
            "goal": "Meet daily calories and macros as closely as possible.",
            "constraints": [
                "Use only user-provided ingredients in each meal.",
                "Provide grams and per-gram nutrition values for each ingredient.",
                "Prefer realistic serving amounts and balanced meals.",
            ],
            "output_schema": {
                "meals": {
                    "breakfast": [
                        {
                            "name": "string",
                            "grams": "number",
                            "kcal_per_g": "number",
                            "protein_per_g": "number",
                            "carbs_per_g": "number",
                            "fats_per_g": "number",
                        }
                    ],
                    "lunch": "same shape",
                    "dinner": "same shape",
                },
                "notes": "short string",
            },
        },
        "profile": asdict(profile),
        "targets": asdict(targets),
        "ingredients_by_meal": ingredients_by_meal,
        "extra_preferences": (extra_preferences or "").strip(),
    }
    return system_prompt, json.dumps(user_payload, ensure_ascii=False)


def generate_day_plan_with_llm(
    profile: UserProfile,
    targets: MacroTargets,
    ingredients_by_meal: Mapping[str, Any],
    extra_preferences: str | None = None,
    model: str | None = None,
    api_caller: Callable[[str, str, str], Tuple[str, str]] | None = None,
) -> Tuple[Dict[str, Meal], Dict[str, Any]]:
    normalized_ingredients = normalize_ingredients_by_meal(ingredients_by_meal)
    model_name = (model or os.getenv("OPENAI_MODEL") or DEFAULT_MODEL).strip()
    system_prompt, user_prompt = _build_llm_prompts(profile, targets, normalized_ingredients, extra_preferences)
    caller = api_caller or _call_openai
    raw_output, used_model = caller(system_prompt, user_prompt, model_name)
    parsed = extract_json_object(raw_output)
    day_plan = _build_meals_from_llm_plan(parsed, normalized_ingredients)
    scaled_plan = _scale_day_plan_to_target_calories(day_plan, targets.calories)
    metadata = {
        "model": used_model or model_name,
        "notes": str(parsed.get("notes", "")).strip(),
    }
    return scaled_plan, metadata

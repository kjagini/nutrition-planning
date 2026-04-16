from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
import json
from pathlib import Path
from typing import Dict, List


ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "high": 1.725,
    "athlete": 1.9,
}


@dataclass
class UserProfile:
    height_cm: float
    weight_kg: float
    workout_level: str


@dataclass
class MacroTargets:
    calories: float
    protein_g: float
    carbs_g: float
    fats_g: float


@dataclass
class Ingredient:
    name: str
    grams: float
    kcal_per_g: float
    protein_per_g: float = 0.0
    carbs_per_g: float = 0.0
    fats_per_g: float = 0.0

    @property
    def calories(self) -> float:
        return self.grams * self.kcal_per_g

    def scale_to_grams(self, grams: float) -> "Ingredient":
        return Ingredient(
            name=self.name,
            grams=grams,
            kcal_per_g=self.kcal_per_g,
            protein_per_g=self.protein_per_g,
            carbs_per_g=self.carbs_per_g,
            fats_per_g=self.fats_per_g,
        )


@dataclass
class Meal:
    name: str
    ingredients: List[Ingredient]

    @property
    def calories(self) -> float:
        return sum(i.calories for i in self.ingredients)

    def macro_totals(self) -> Dict[str, float]:
        return {
            "protein_g": sum(i.grams * i.protein_per_g for i in self.ingredients),
            "carbs_g": sum(i.grams * i.carbs_per_g for i in self.ingredients),
            "fats_g": sum(i.grams * i.fats_per_g for i in self.ingredients),
        }

    def rebalance_ingredient(self, ingredient_name: str, new_grams: float) -> "Meal":
        """
        Rebalances the meal so calories stay constant when one ingredient changes.
        Remaining ingredients are scaled proportionally by calorie share.
        """
        original_total = self.calories
        target_idx = next(
            (idx for idx, ing in enumerate(self.ingredients) if ing.name == ingredient_name),
            None,
        )
        if target_idx is None:
            raise ValueError(f"Ingredient not found: {ingredient_name}")

        old_target = self.ingredients[target_idx]
        new_target = old_target.scale_to_grams(new_grams)
        delta = new_target.calories - old_target.calories

        if abs(delta) < 1e-9:
            return Meal(self.name, [i.scale_to_grams(i.grams) for i in self.ingredients])

        other_indices = [i for i in range(len(self.ingredients)) if i != target_idx]
        other_total = sum(self.ingredients[i].calories for i in other_indices)
        if other_total <= 0 and delta > 0:
            raise ValueError("Cannot increase ingredient calories when other items have no calories to reduce")

        new_ingredients: List[Ingredient] = []
        for idx, ing in enumerate(self.ingredients):
            if idx == target_idx:
                new_ingredients.append(new_target)
                continue

            if other_total <= 0:
                new_grams_other = ing.grams
            else:
                calorie_share = ing.calories / other_total
                calorie_adjustment = delta * calorie_share
                new_calories = max(0.0, ing.calories - calorie_adjustment)
                new_grams_other = new_calories / ing.kcal_per_g if ing.kcal_per_g else 0.0

            new_ingredients.append(ing.scale_to_grams(new_grams_other))

        adjusted = Meal(self.name, new_ingredients)
        drift = original_total - adjusted.calories
        if abs(drift) > 1e-6:
            # Correct tiny floating-point drift using target ingredient.
            target = next(i for i in adjusted.ingredients if i.name == ingredient_name)
            target_extra_g = drift / target.kcal_per_g if target.kcal_per_g else 0.0
            final_ings = []
            for ing in adjusted.ingredients:
                if ing.name == ingredient_name:
                    final_ings.append(ing.scale_to_grams(max(0.0, ing.grams + target_extra_g)))
                else:
                    final_ings.append(ing)
            adjusted = Meal(self.name, final_ings)

        return adjusted


class NutritionPlanner:
    def __init__(self, profile: UserProfile, meal_preferences: Dict[str, Meal]):
        if profile.workout_level not in ACTIVITY_MULTIPLIERS:
            raise ValueError(f"Unsupported workout level: {profile.workout_level}")
        self.profile = profile
        self.meal_preferences = meal_preferences

    def daily_targets(self) -> MacroTargets:
        # Practical approximation when age/sex are unavailable.
        bmr_estimate = 10 * self.profile.weight_kg + 6.25 * self.profile.height_cm - 5 * 30 + 5
        calories = bmr_estimate * ACTIVITY_MULTIPLIERS[self.profile.workout_level]

        protein_g = 1.8 * self.profile.weight_kg
        fats_g = 0.9 * self.profile.weight_kg
        carbs_g = max(0.0, (calories - protein_g * 4 - fats_g * 9) / 4)
        return MacroTargets(calories=calories, protein_g=protein_g, carbs_g=carbs_g, fats_g=fats_g)

    def build_day_plan(self) -> Dict[str, Meal]:
        return {k: Meal(v.name, [i.scale_to_grams(i.grams) for i in v.ingredients]) for k, v in self.meal_preferences.items()}


class MealLogger:
    def __init__(self, path: str = "meal_logs.jsonl"):
        self.path = Path(path)

    def log_meal(self, when: date, meal_name: str, meal: Meal) -> None:
        payload = {
            "date": when.isoformat(),
            "meal_name": meal_name,
            "ingredients": [asdict(i) for i in meal.ingredients],
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload) + "\n")

    def meals_for_date(self, when: date) -> List[Meal]:
        if not self.path.exists():
            return []
        output = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            data = json.loads(line)
            if data.get("date") != when.isoformat():
                continue
            output.append(
                Meal(
                    name=data["meal_name"],
                    ingredients=[Ingredient(**ing) for ing in data["ingredients"]],
                )
            )
        return output


def build_daily_report(targets: MacroTargets, meals: List[Meal]) -> Dict[str, object]:
    actual_calories = sum(m.calories for m in meals)
    actual_protein = sum(m.macro_totals()["protein_g"] for m in meals)
    actual_carbs = sum(m.macro_totals()["carbs_g"] for m in meals)
    actual_fats = sum(m.macro_totals()["fats_g"] for m in meals)

    def met(actual: float, target: float, tolerance: float = 0.1) -> bool:
        lower, upper = target * (1 - tolerance), target * (1 + tolerance)
        return lower <= actual <= upper

    return {
        "targets": asdict(targets),
        "actual": {
            "calories": actual_calories,
            "protein_g": actual_protein,
            "carbs_g": actual_carbs,
            "fats_g": actual_fats,
        },
        "met": {
            "calories": met(actual_calories, targets.calories),
            "protein_g": met(actual_protein, targets.protein_g),
            "carbs_g": met(actual_carbs, targets.carbs_g),
            "fats_g": met(actual_fats, targets.fats_g),
        },
        "improvements": [
            "Increase protein sources (eggs, yogurt, lean meat, tofu)" if actual_protein < targets.protein_g * 0.9 else "Protein intake is on track",
            "Reduce calorie-dense extras to stay within range" if actual_calories > targets.calories * 1.1 else "Calorie intake is within acceptable range",
        ],
    }

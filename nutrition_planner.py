from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence


ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "high": 1.725,
    "athlete": 1.9,
}

DEFAULT_MEAL_DISTRIBUTION = {
    "breakfast": 0.30,
    "lunch": 0.35,
    "dinner": 0.35,
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


@dataclass(frozen=True)
class IngredientTemplate:
    key: str
    label: str
    meal_name: str
    default_grams: float
    kcal_per_g: float
    protein_per_g: float
    carbs_per_g: float
    fats_per_g: float

    def to_ingredient(self, grams: float) -> Ingredient:
        return Ingredient(
            name=self.label,
            grams=grams,
            kcal_per_g=self.kcal_per_g,
            protein_per_g=self.protein_per_g,
            carbs_per_g=self.carbs_per_g,
            fats_per_g=self.fats_per_g,
        )


INGREDIENT_TEMPLATES: Dict[str, IngredientTemplate] = {
    "oats": IngredientTemplate("oats", "Oats", "breakfast", 90, 3.89, 0.169, 0.663, 0.069),
    "banana": IngredientTemplate("banana", "Banana", "breakfast", 100, 0.89, 0.011, 0.228, 0.003),
    "greek_yogurt": IngredientTemplate("greek_yogurt", "Greek Yogurt", "breakfast", 180, 0.59, 0.103, 0.036, 0.004),
    "milk": IngredientTemplate("milk", "Milk", "breakfast", 220, 0.64, 0.034, 0.048, 0.032),
    "peanut_butter": IngredientTemplate("peanut_butter", "Peanut Butter", "breakfast", 28, 5.88, 0.25, 0.20, 0.50),
    "chia_seeds": IngredientTemplate("chia_seeds", "Chia Seeds", "breakfast", 18, 4.86, 0.17, 0.42, 0.31),
    "eggs": IngredientTemplate("eggs", "Eggs", "breakfast", 100, 1.55, 0.126, 0.011, 0.106),
    "berries": IngredientTemplate("berries", "Berries", "breakfast", 100, 0.57, 0.007, 0.14, 0.003),
    "chicken_breast": IngredientTemplate("chicken_breast", "Chicken Breast", "lunch", 180, 1.65, 0.31, 0.0, 0.036),
    "rice": IngredientTemplate("rice", "Rice", "lunch", 180, 1.30, 0.027, 0.285, 0.003),
    "quinoa": IngredientTemplate("quinoa", "Quinoa", "lunch", 150, 1.20, 0.044, 0.213, 0.019),
    "tofu": IngredientTemplate("tofu", "Tofu", "lunch", 180, 0.76, 0.08, 0.019, 0.048),
    "avocado": IngredientTemplate("avocado", "Avocado", "lunch", 90, 1.60, 0.02, 0.085, 0.147),
    "broccoli": IngredientTemplate("broccoli", "Broccoli", "lunch", 120, 0.34, 0.028, 0.07, 0.004),
    "olive_oil": IngredientTemplate("olive_oil", "Olive Oil", "lunch", 15, 8.84, 0.0, 0.0, 1.0),
    "lentils": IngredientTemplate("lentils", "Lentils", "lunch", 160, 1.16, 0.09, 0.20, 0.004),
    "salmon": IngredientTemplate("salmon", "Salmon", "dinner", 170, 2.08, 0.20, 0.0, 0.13),
    "sweet_potato": IngredientTemplate("sweet_potato", "Sweet Potato", "dinner", 180, 0.86, 0.016, 0.201, 0.001),
    "paneer": IngredientTemplate("paneer", "Paneer", "dinner", 140, 2.65, 0.18, 0.02, 0.21),
    "mixed_veggies": IngredientTemplate("mixed_veggies", "Mixed Veggies", "dinner", 160, 0.50, 0.021, 0.10, 0.002),
    "whole_wheat_roti": IngredientTemplate("whole_wheat_roti", "Whole Wheat Roti", "dinner", 110, 2.70, 0.09, 0.53, 0.03),
    "brown_rice": IngredientTemplate("brown_rice", "Brown Rice", "dinner", 170, 1.11, 0.026, 0.23, 0.009),
    "spinach": IngredientTemplate("spinach", "Spinach", "dinner", 120, 0.23, 0.029, 0.036, 0.004),
    "chickpeas": IngredientTemplate("chickpeas", "Chickpeas", "dinner", 160, 1.64, 0.089, 0.274, 0.026),
}

MEAL_OPTION_ORDER = {
    "breakfast": ["oats", "banana", "greek_yogurt", "milk", "peanut_butter", "chia_seeds", "eggs", "berries"],
    "lunch": ["chicken_breast", "rice", "quinoa", "tofu", "avocado", "broccoli", "olive_oil", "lentils"],
    "dinner": ["salmon", "sweet_potato", "paneer", "mixed_veggies", "whole_wheat_roti", "brown_rice", "spinach", "chickpeas"],
}


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
        Rebalances a meal while keeping meal calories constant.
        Remaining ingredients are scaled by calorie share.
        """
        original_total = self.calories
        target_idx = next(
            (idx for idx, ing in enumerate(self.ingredients) if ing.name == ingredient_name),
            None,
        )
        if target_idx is None:
            raise ValueError(f"Ingredient not found: {ingredient_name}")
        if new_grams < 0:
            raise ValueError("Ingredient grams cannot be negative")

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


def get_preference_catalog() -> Dict[str, List[Dict[str, object]]]:
    catalog: Dict[str, List[Dict[str, object]]] = {}
    for meal_name, keys in MEAL_OPTION_ORDER.items():
        catalog[meal_name] = []
        for key in keys:
            item = INGREDIENT_TEMPLATES[key]
            catalog[meal_name].append(
                {
                    "key": item.key,
                    "label": item.label,
                    "default_grams": item.default_grams,
                    "kcal_per_g": item.kcal_per_g,
                    "protein_per_g": item.protein_per_g,
                    "carbs_per_g": item.carbs_per_g,
                    "fats_per_g": item.fats_per_g,
                }
            )
    return catalog


def _normalize_distribution(meal_distribution: Mapping[str, float] | None) -> Dict[str, float]:
    candidate = dict(DEFAULT_MEAL_DISTRIBUTION)
    if meal_distribution:
        for meal_name in DEFAULT_MEAL_DISTRIBUTION:
            if meal_name in meal_distribution:
                candidate[meal_name] = max(0.0, float(meal_distribution[meal_name]))
    total = sum(candidate.values())
    if total <= 0:
        return dict(DEFAULT_MEAL_DISTRIBUTION)
    return {meal_name: value / total for meal_name, value in candidate.items()}


def _valid_preference_keys(meal_name: str, keys: Sequence[str] | None) -> List[str]:
    allowed = set(MEAL_OPTION_ORDER[meal_name])
    clean_keys = [key for key in (keys or []) if key in allowed]
    if clean_keys:
        return clean_keys
    return MEAL_OPTION_ORDER[meal_name][:3]


def _build_meal_for_target(meal_name: str, calorie_target: float, preference_keys: Sequence[str] | None) -> Meal:
    ingredient_keys = _valid_preference_keys(meal_name, preference_keys)
    templates = [INGREDIENT_TEMPLATES[key] for key in ingredient_keys]
    baseline_calories = sum(t.default_grams * t.kcal_per_g for t in templates)
    if baseline_calories <= 0:
        raise ValueError(f"Cannot build meal '{meal_name}' with zero-calorie ingredients")
    scale = calorie_target / baseline_calories
    ingredients = [template.to_ingredient(max(0.0, template.default_grams * scale)) for template in templates]
    return Meal(name=meal_name, ingredients=ingredients)


def generate_day_plan_from_preferences(
    targets: MacroTargets,
    preferences: Mapping[str, Sequence[str]] | None = None,
    meal_distribution: Mapping[str, float] | None = None,
) -> Dict[str, Meal]:
    distribution = _normalize_distribution(meal_distribution)
    preferences = preferences or {}
    day_plan: Dict[str, Meal] = {}
    for meal_name, share in distribution.items():
        meal_target = targets.calories * share
        day_plan[meal_name] = _build_meal_for_target(meal_name, meal_target, preferences.get(meal_name))
    return day_plan


def build_day_totals(meals: Mapping[str, Meal] | Iterable[Meal]) -> Dict[str, float]:
    if isinstance(meals, Mapping):
        meal_list = list(meals.values())
    else:
        meal_list = list(meals)
    total_calories = sum(meal.calories for meal in meal_list)
    total_protein = sum(meal.macro_totals()["protein_g"] for meal in meal_list)
    total_carbs = sum(meal.macro_totals()["carbs_g"] for meal in meal_list)
    total_fats = sum(meal.macro_totals()["fats_g"] for meal in meal_list)
    return {
        "calories": total_calories,
        "protein_g": total_protein,
        "carbs_g": total_carbs,
        "fats_g": total_fats,
    }


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
    actual = build_day_totals(meals)

    def met(actual_value: float, target_value: float, tolerance: float = 0.1) -> bool:
        lower, upper = target_value * (1 - tolerance), target_value * (1 + tolerance)
        return lower <= actual_value <= upper

    met_status = {
        "calories": met(actual["calories"], targets.calories),
        "protein_g": met(actual["protein_g"], targets.protein_g),
        "carbs_g": met(actual["carbs_g"], targets.carbs_g),
        "fats_g": met(actual["fats_g"], targets.fats_g),
    }
    completion_score = 100.0 * (sum(1 for is_met in met_status.values() if is_met) / len(met_status))

    improvements = []
    if actual["protein_g"] < targets.protein_g * 0.9:
        improvements.append("Increase protein sources like eggs, yogurt, lean meat, tofu, or paneer.")
    if actual["calories"] > targets.calories * 1.1:
        improvements.append("Trim calorie-dense extras to stay closer to your target.")
    if actual["carbs_g"] < targets.carbs_g * 0.9:
        improvements.append("Add slow-digesting carbs such as oats, rice, quinoa, or sweet potato.")
    if actual["fats_g"] > targets.fats_g * 1.1:
        improvements.append("Reduce high-fat add-ons like oil, nut butter, and fried sides.")
    if not improvements:
        improvements.append("Great job - your intake is aligned with your goal range today.")

    return {
        "targets": asdict(targets),
        "actual": actual,
        "met": met_status,
        "completion_score": completion_score,
        "improvements": improvements,
    }

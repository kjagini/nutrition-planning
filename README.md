# Nutrition Planning App (Starter)

This repo now includes a starter implementation for the app you described:

- Enter **height, weight, workout level**.
- Define preferred meals for **breakfast/lunch/dinner**.
- Generate daily targets and meal quantities.
- If one ingredient changes (e.g., oats 100g -> 120g), rebalance other ingredients to keep totals within limits.
- Log meals daily and generate a report of goals met/unmet plus improvement tips.

## Core module

`nutrition_planner.py` provides:

- `NutritionPlanner`: computes calorie and macro targets.
- `Meal.rebalance_ingredient(...)`: adjusts one item and proportionally rebalances others while preserving meal calories.
- `MealLogger`: JSONL meal logging and retrieval by date.
- `build_daily_report(...)`: compares actual intake with targets and flags goals met/unmet.

## Quick example

```python
from datetime import date
from nutrition_planner import Ingredient, Meal, NutritionPlanner, UserProfile, MealLogger, build_daily_report

breakfast = Meal(
    "breakfast",
    [
        Ingredient("oats", 100, 3.89, protein_per_g=0.17, carbs_per_g=0.66, fats_per_g=0.07),
        Ingredient("banana", 50, 0.89, protein_per_g=0.01, carbs_per_g=0.23),
        Ingredient("milk", 250, 0.64, protein_per_g=0.03, carbs_per_g=0.05, fats_per_g=0.03),
    ],
)

# Increase oats and auto-rebalance the rest.
adjusted_breakfast = breakfast.rebalance_ingredient("oats", 120)

planner = NutritionPlanner(
    UserProfile(height_cm=175, weight_kg=75, workout_level="moderate"),
    {"breakfast": adjusted_breakfast},
)
targets = planner.daily_targets()

logger = MealLogger("meal_logs.jsonl")
logger.log_meal(date.today(), "breakfast", adjusted_breakfast)
report = build_daily_report(targets, logger.meals_for_date(date.today()))
print(report)
```

## Run tests

```bash
python -m pytest -q
```


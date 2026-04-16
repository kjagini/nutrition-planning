from datetime import date

from nutrition_planner import (
    Ingredient,
    Meal,
    MealLogger,
    NutritionPlanner,
    UserProfile,
    build_daily_report,
)


def test_rebalance_preserves_meal_calories():
    meal = Meal(
        name="breakfast",
        ingredients=[
            Ingredient("oats", 100, 3.89, protein_per_g=0.17, carbs_per_g=0.66, fats_per_g=0.07),
            Ingredient("banana", 50, 0.89, protein_per_g=0.01, carbs_per_g=0.23, fats_per_g=0.00),
            Ingredient("milk", 250, 0.64, protein_per_g=0.03, carbs_per_g=0.05, fats_per_g=0.03),
        ],
    )

    updated = meal.rebalance_ingredient("oats", 120)
    assert round(updated.calories, 5) == round(meal.calories, 5)
    oats = next(i for i in updated.ingredients if i.name == "oats")
    banana = next(i for i in updated.ingredients if i.name == "banana")
    assert oats.grams == 120
    assert banana.grams < 50


def test_daily_report_and_logging(tmp_path):
    breakfast = Meal(
        name="breakfast",
        ingredients=[Ingredient("oats", 100, 3.89, protein_per_g=0.17, carbs_per_g=0.66, fats_per_g=0.07)],
    )
    lunch = Meal(
        name="lunch",
        ingredients=[Ingredient("rice", 150, 1.3, protein_per_g=0.026, carbs_per_g=0.28, fats_per_g=0.003)],
    )

    planner = NutritionPlanner(
        UserProfile(height_cm=175, weight_kg=75, workout_level="moderate"),
        {"breakfast": breakfast, "lunch": lunch},
    )
    targets = planner.daily_targets()

    logger = MealLogger(str(tmp_path / "logs.jsonl"))
    logger.log_meal(date(2026, 4, 16), "breakfast", breakfast)
    logger.log_meal(date(2026, 4, 16), "lunch", lunch)

    meals = logger.meals_for_date(date(2026, 4, 16))
    report = build_daily_report(targets, meals)

    assert report["actual"]["calories"] > 0
    assert set(report["met"].keys()) == {"calories", "protein_g", "carbs_g", "fats_g"}
    assert len(report["improvements"]) >= 1

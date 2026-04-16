from nutrition_planner import (
    MacroTargets,
    build_day_totals,
    generate_day_plan_from_preferences,
    get_preference_catalog,
)


def test_generated_day_plan_matches_daily_calorie_target():
    targets = MacroTargets(calories=2400, protein_g=150, carbs_g=300, fats_g=70)
    preferences = {
        "breakfast": ["oats", "banana", "greek_yogurt"],
        "lunch": ["chicken_breast", "rice", "broccoli"],
        "dinner": ["salmon", "sweet_potato", "spinach"],
    }

    day_plan = generate_day_plan_from_preferences(targets, preferences=preferences)
    totals = build_day_totals(day_plan)

    assert set(day_plan.keys()) == {"breakfast", "lunch", "dinner"}
    assert abs(totals["calories"] - targets.calories) < 1e-6


def test_generated_plan_uses_default_options_when_preference_missing():
    targets = MacroTargets(calories=2100, protein_g=130, carbs_g=260, fats_g=65)
    day_plan = generate_day_plan_from_preferences(targets, preferences={"breakfast": []})

    assert len(day_plan["breakfast"].ingredients) == 3
    assert len(day_plan["lunch"].ingredients) == 3
    assert len(day_plan["dinner"].ingredients) == 3


def test_preference_catalog_is_grouped_by_meal():
    catalog = get_preference_catalog()

    assert set(catalog.keys()) == {"breakfast", "lunch", "dinner"}
    assert all(len(items) >= 6 for items in catalog.values())

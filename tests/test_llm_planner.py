from llm_planner import (
    LLMPlannerError,
    extract_json_object,
    generate_day_plan_with_llm,
    normalize_ingredients_by_meal,
)
from nutrition_planner import MacroTargets, UserProfile, build_day_totals


def test_normalize_ingredients_by_meal():
    payload = {
        "breakfast": "oats, banana, oats",
        "lunch": ["rice", "chicken breast", "rice"],
        "dinner": "salmon\nspinach",
    }
    normalized = normalize_ingredients_by_meal(payload)
    assert normalized["breakfast"] == ["oats", "banana"]
    assert normalized["lunch"] == ["rice", "chicken breast"]
    assert normalized["dinner"] == ["salmon", "spinach"]


def test_extract_json_object_from_wrapped_text():
    wrapped = "Here is the plan:\n{\"meals\": {\"breakfast\": []}}"
    parsed = extract_json_object(wrapped)
    assert "meals" in parsed


def test_generate_day_plan_with_llm_scales_to_target():
    def fake_api(_system_prompt: str, _user_prompt: str, _model: str):
        return (
            """
            {
              "meals": {
                "breakfast": [
                  {"name":"oats","grams":100,"kcal_per_g":3.89,"protein_per_g":0.169,"carbs_per_g":0.663,"fats_per_g":0.069},
                  {"name":"banana","grams":100,"kcal_per_g":0.89,"protein_per_g":0.011,"carbs_per_g":0.228,"fats_per_g":0.003}
                ],
                "lunch": [
                  {"name":"rice","grams":150,"kcal_per_g":1.30,"protein_per_g":0.027,"carbs_per_g":0.285,"fats_per_g":0.003},
                  {"name":"chicken breast","grams":150,"kcal_per_g":1.65,"protein_per_g":0.31,"carbs_per_g":0.0,"fats_per_g":0.036}
                ],
                "dinner": [
                  {"name":"salmon","grams":160,"kcal_per_g":2.08,"protein_per_g":0.2,"carbs_per_g":0.0,"fats_per_g":0.13},
                  {"name":"spinach","grams":120,"kcal_per_g":0.23,"protein_per_g":0.029,"carbs_per_g":0.036,"fats_per_g":0.004}
                ]
              },
              "notes": "sample"
            }
            """,
            "fake-model",
        )

    profile = UserProfile(height_cm=175, weight_kg=75, workout_level="moderate")
    targets = MacroTargets(calories=2300, protein_g=140, carbs_g=290, fats_g=70)
    ingredients = {
        "breakfast": ["oats", "banana"],
        "lunch": ["rice", "chicken breast"],
        "dinner": ["salmon", "spinach"],
    }
    day_plan, metadata = generate_day_plan_with_llm(
        profile=profile,
        targets=targets,
        ingredients_by_meal=ingredients,
        api_caller=fake_api,
    )
    totals = build_day_totals(day_plan)

    assert set(day_plan.keys()) == {"breakfast", "lunch", "dinner"}
    assert abs(totals["calories"] - targets.calories) < 1e-5
    assert metadata["model"] == "fake-model"


def test_generate_day_plan_with_llm_rejects_unknown_ingredient():
    def fake_api(_system_prompt: str, _user_prompt: str, _model: str):
        return (
            """
            {
              "meals": {
                "breakfast": [{"name":"oats","grams":100,"kcal_per_g":3.89,"protein_per_g":0.169,"carbs_per_g":0.663,"fats_per_g":0.069}],
                "lunch": [{"name":"rice","grams":100,"kcal_per_g":1.3,"protein_per_g":0.027,"carbs_per_g":0.285,"fats_per_g":0.003}],
                "dinner": [{"name":"pasta","grams":100,"kcal_per_g":1.5,"protein_per_g":0.05,"carbs_per_g":0.3,"fats_per_g":0.02}]
              },
              "notes": ""
            }
            """,
            "fake-model",
        )

    profile = UserProfile(height_cm=175, weight_kg=75, workout_level="moderate")
    targets = MacroTargets(calories=2200, protein_g=130, carbs_g=270, fats_g=65)
    ingredients = {
        "breakfast": ["oats"],
        "lunch": ["rice"],
        "dinner": ["salmon", "spinach"],
    }

    try:
        generate_day_plan_with_llm(
            profile=profile,
            targets=targets,
            ingredients_by_meal=ingredients,
            api_caller=fake_api,
        )
    except LLMPlannerError as exc:
        assert "outside your provided ingredients" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected LLMPlannerError for unknown ingredient")

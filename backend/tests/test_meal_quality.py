import pytest

from app.schemas.meal_plans import Dish, GeneratedMealPlan, Ingredient, MealPlanRequest, PlannedMeal
from app.services.meal_quality import quality_issues


def dish(name, *names, instruction="Simmer until cooked.", grams=80):
    return Dish(name=name, ingredients=[Ingredient(name=item, quantity=grams, unit="g") for item in names],
                instructions=[instruction])


def meal(kind, *dishes, minutes=15):
    return PlannedMeal(meal_type=kind, dishes=list(dishes), estimated_preparation_minutes=minutes)


def review(*meals, text="Plan a simple meal for one"):
    request = MealPlanRequest(user_request=text, language="en-US",
                              scope="single_meal" if len(meals) == 1 else "full_day", ingredient_mode="flexible")
    return quality_issues(GeneratedMealPlan(title="Everyday meals", meals=list(meals), explanation="Simple"), request)


@pytest.mark.parametrize("meal_type, names, text", [
    ("dinner", ("鸡胸肉", "米饭", "小白菜"), "一顿家常晚餐"),
    ("dinner", ("tofu", "rice", "broccoli"), "Vegetarian dinner"),
    ("lunch", ("鸡蛋", "面条", "菠菜"), "一人份中式午餐"),
])
def test_complete_integrated_meals_accept_meat_or_plant_protein(meal_type, names, text):
    assert review(meal(meal_type, dish("家常一碗", *names)), text=text) == ()


def test_main_meal_needs_distinct_components_except_when_requested_light():
    vegetables = meal("dinner", dish("Simmered bok choy", "bok choy"))
    assert review(vegetables) == ("missing_complete_meal_roles",)
    assert review(vegetables, text="I want a light dinner") == ()
    assert review(vegetables, text="Not a light dinner") == ("missing_complete_meal_roles",)
    garnish = dish("A few tofu crumbs", "tofu", grams=1)
    assert "missing_complete_meal_roles" in review(
        meal("dinner", dish("Vegetable rice", "bok choy", "rice"), garnish),
    )


def test_breakfast_prefers_quick_cooked_dish_and_no_cook_accompaniment():
    eggs = dish("Steamed eggs", "eggs", instruction="Steam the eggs.")
    oats = dish("Boiled oats", "oats", instruction="Boil the oats.")
    assert review(meal("breakfast", eggs, dish("Toast", "toast", instruction="Serve."), minutes=12)) == ()
    assert review(meal("breakfast", eggs, oats, minutes=35)) == ("multiple_slow_breakfast_dishes",)
    assert review(meal("breakfast", eggs, oats, minutes=35), text="Elaborate breakfast") == ()


def test_one_person_portion_and_ingredient_effort_checks():
    assert "impractical_meal_size_or_effort" in review(
        meal("lunch", dish("Large batch", "chicken", "rice", "spinach", grams=1500)),
    )
    large_pantry = dish("Busy bowl", "tofu", "rice", "spinach", *(f"seasoning {i}" for i in range(10)))
    assert "impractical_meal_size_or_effort" in review(meal("lunch", large_pantry))
    assert review(meal("lunch", large_pantry), text="Elaborate lunch for guests") == ()


def test_varies_preparation_and_dishes_while_reusing_rice_and_tofu():
    rice = dish("Rice", "cooked rice", instruction="Serve.")
    lunch = meal("lunch", dish("Spinach tofu stir-fry", "tofu", "spinach", instruction="Stir-fry."), rice)
    dinner = meal("dinner", dish("Tomato tofu stew", "tofu", "tomatoes"), rice)
    breakfast = meal("breakfast", dish("Oatmeal", "oats"), minutes=10)
    assert review(breakfast, lunch, dinner) == ()
    repeated = meal("dinner", dish("Another name", "tofu", "spinach", instruction="Stir-fry."), rice)
    assert review(breakfast, lunch, repeated) == ("repeated_cooking_pattern",)
    assert "repeated_dish" in review(breakfast, lunch, meal("dinner", *lunch.dishes))


def test_explicit_vegetarian_and_vegan_conflicts_are_not_counted_as_feasible():
    assert review(meal("dinner", dish("Chicken rice", "chicken", "rice", "spinach")),
                  text="Vegetarian dinner") == ("explicit_diet_conflict",)
    assert review(meal("dinner", dish("Egg rice", "eggs", "rice", "spinach")),
                  text="Vegan dinner") == ("explicit_diet_conflict",)

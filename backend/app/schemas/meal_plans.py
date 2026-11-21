from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MealType = Literal["breakfast", "lunch", "dinner", "snack"]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
Minutes = Annotated[int, Field(ge=1, le=480)]


def ingredient_key(name: str) -> str:
    return " ".join(name.split()).casefold()


class MealPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    user_request: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    language: Literal["zh-CN", "en-US"]
    scope: Literal["single_meal", "full_day"]
    meal_type: MealType | None = None
    available_ingredients: list[Name] = Field(default_factory=list, max_length=60)
    ingredient_mode: Literal["existing", "flexible"]
    cooking_time_limit: Minutes | None = None

    @model_validator(mode="after")
    def check_scope_and_ingredients(self):
        if self.scope == "full_day" and self.meal_type is not None:
            raise ValueError("meal_type applies only to single_meal")
        if self.ingredient_mode == "existing" and not self.available_ingredients:
            raise ValueError("existing mode requires available_ingredients")
        return self


class StructuredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Ingredient(StructuredOutput):
    name: Name
    quantity: Annotated[float, Field(ge=0.001, allow_inf_nan=False)]
    unit: Name


class Dish(StructuredOutput):
    name: Name
    ingredients: Annotated[list[Ingredient], Field(min_length=1, max_length=20)]
    instructions: Annotated[list[Text], Field(min_length=1, max_length=10)]


class PlannedMeal(StructuredOutput):
    meal_type: MealType
    dishes: Annotated[list[Dish], Field(min_length=1, max_length=4)]
    estimated_preparation_minutes: Minutes


class GeneratedMealPlan(StructuredOutput):
    title: Name
    meals: Annotated[list[PlannedMeal], Field(min_length=1, max_length=4)]
    explanation: Text


class MealPlanResponse(GeneratedMealPlan):
    additional_ingredients: list[Name]

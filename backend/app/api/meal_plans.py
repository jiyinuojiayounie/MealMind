from fastapi import APIRouter, HTTPException, Request

from app.schemas.meal_plans import MealPlanRequest, MealPlanResponse
from app.services.meal_plans import (
    PlannerFailure,
    PlannerTimeout,
    PlannerUnavailable,
    generate_meal_plan,
)

router = APIRouter(prefix="/meal-plans", tags=["meal plans"])


@router.post("/generate", response_model=MealPlanResponse)
def generate(
    payload: MealPlanRequest, request: Request, infer_scope: bool = False
) -> MealPlanResponse:
    try:
        return generate_meal_plan(payload, request.app.state.settings, infer_scope=infer_scope)
    except PlannerUnavailable:
        raise HTTPException(503, "Meal planning is currently unavailable.") from None
    except PlannerTimeout:
        raise HTTPException(504, "Meal planning timed out. Try again later.") from None
    except PlannerFailure:
        raise HTTPException(502, "A meal plan could not be generated. Try again or adjust your requirements.") from None

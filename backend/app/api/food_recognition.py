from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.food_logs import local_food_log_settings
from app.core.settings import Settings
from app.schemas.food_recognition import FoodRecognitionRequest, FoodRecognitionResponse
from app.services.food_recognition import recognize_food_text
from app.services.meal_plans import PlannerFailure, PlannerTimeout, PlannerUnavailable

router = APIRouter(prefix="/food-logs", tags=["food recognition"])


@router.post("/recognize-text")
def recognize_text(
    payload: FoodRecognitionRequest,
    settings: Annotated[Settings, Depends(local_food_log_settings)],
) -> FoodRecognitionResponse:
    try:
        return recognize_food_text(payload, settings)
    except PlannerUnavailable:
        raise HTTPException(503, "Food recognition is currently unavailable.") from None
    except PlannerTimeout:
        raise HTTPException(504, "Food recognition timed out. Try again later.") from None
    except PlannerFailure:
        raise HTTPException(502, "Food recognition could not produce a valid proposal.") from None

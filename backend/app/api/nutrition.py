from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BeforeValidator

from app.api.food_logs import Store
from app.schemas.daily_nutrition import DailyNutritionAnalysis
from app.services.daily_nutrition import analyze_confirmed_logs
from app.services.nutrition_calculation import NutritionCalculator
from app.storage.food_logs import FoodLogStorageUnavailable

router = APIRouter(prefix="/nutrition", tags=["nutrition"])
PRIVATE_HEADERS = {"Cache-Control": "no-store"}


def parse_calendar_date(value: object) -> date:
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() == value:
                return parsed
        except ValueError:
            pass
    raise ValueError("Use a valid calendar date in YYYY-MM-DD format.")


@router.get("/daily")
def daily_nutrition(
    consumed_on: Annotated[date, BeforeValidator(parse_calendar_date), Query(alias="date")],
    store: Store,
    response: Response,
) -> DailyNutritionAnalysis:
    try:
        logs = store.list_confirmed_by_date(consumed_on)
        analysis = analyze_confirmed_logs(logs, consumed_on, NutritionCalculator())
    except (FoodLogStorageUnavailable, OSError, ValueError):
        raise HTTPException(
            503, {"status": "nutrition_unavailable", "message": "Nutrition analysis is unavailable."},
            headers=PRIVATE_HEADERS,
        ) from None

    response.headers.update(PRIVATE_HEADERS)
    return analysis

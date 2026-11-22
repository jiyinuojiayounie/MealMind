from fastapi import APIRouter, Depends, HTTPException, Response

from app.api.food_logs import local_food_log_settings
from app.schemas.food_normalization import FoodMatchingPreview, FoodNormalizationResult
from app.services.food_normalization import get_food_normalizer

router = APIRouter(prefix="/food-normalization", tags=["food normalization"],
                   dependencies=[Depends(local_food_log_settings)])


@router.post("/preview")
def preview_matching(payload: FoodMatchingPreview, response: Response) -> list[FoodNormalizationResult]:
    try:
        normalizer = get_food_normalizer()
    except (OSError, ValueError):
        raise HTTPException(503, "Food matching is unavailable.") from None
    response.headers["Cache-Control"] = "no-store"
    return [
        normalizer.match_item(entry.item, identity_uncertain=entry.identity_uncertain)
        for entry in payload.items
    ]

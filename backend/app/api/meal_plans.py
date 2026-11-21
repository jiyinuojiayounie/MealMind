from ipaddress import ip_address
from typing import Literal

from fastapi import APIRouter, HTTPException, Request

from app.schemas.meal_plans import MealPlanRequest, MealPlanResponse
from app.services.catalog_planning import generate_catalog_plan
from app.services.meal_composition import NoFeasiblePlan
from app.services.planning_intent import PlanningBlocked
from app.services.recipe_catalog import DEVELOPMENT_CATALOG_PATH, CatalogLoadError, load_recipe_catalog
from app.services.meal_plans import (
    PlannerFailure,
    PlannerTimeout,
    PlannerUnavailable,
    generate_meal_plan,
)

router = APIRouter(prefix="/meal-plans", tags=["meal plans"])


def _is_loopback(host: str) -> bool:
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


@router.post("/generate", response_model=MealPlanResponse)
def generate(
    payload: MealPlanRequest, request: Request, infer_scope: bool = False,
    planning_mode: Literal["prompt_only", "catalog"] = "prompt_only",
) -> MealPlanResponse:
    settings = request.app.state.settings
    try:
        if planning_mode == "prompt_only":
            return generate_meal_plan(payload, settings, infer_scope=infer_scope)

        if not settings.catalog_planning_enabled:
            raise HTTPException(403, {"status": "catalog_disabled"})
        if settings.catalog_use_drafts:
            server = request.scope.get("server")
            if (
                settings.environment != "development"
                or not request.client or not _is_loopback(request.client.host)
                or not server or not _is_loopback(server[0])
            ):
                raise HTTPException(403, {"status": "draft_catalog_forbidden"})

        try:
            catalog = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH)
        except CatalogLoadError:
            raise PlannerUnavailable from None
        result = generate_catalog_plan(
            payload, settings, catalog, infer_scope=infer_scope,
            mode="development_drafts" if settings.catalog_use_drafts else "production",
        )
        if isinstance(result, PlanningBlocked):
            raise HTTPException(422, {"status": result.status, "reasons": result.reasons})
        if isinstance(result, NoFeasiblePlan):
            raise HTTPException(409, {
                "status": result.status, "reason": result.reason, "blocked_meals": result.blocked_meals,
            })
        return result
    except PlannerUnavailable:
        raise HTTPException(503, "Meal planning is currently unavailable.") from None
    except PlannerTimeout:
        raise HTTPException(504, "Meal planning timed out. Try again later.") from None
    except PlannerFailure:
        raise HTTPException(502, "A meal plan could not be generated. Try again or adjust your requirements.") from None

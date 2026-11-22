from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.api.food_logs import Store, local_food_log_settings
from app.core.settings import Settings
from app.schemas.replan import LocalDate, ReplanContext, ReplanPreview, ReplanRequest
from app.services.meal_plans import PlannerFailure, PlannerTimeout, PlannerUnavailable
from app.services.recipe_catalog import CatalogLoadError
from app.services.replan import ReplanBlocked, generate_replan_preview, replan_context
from app.storage.food_logs import FoodLogStorageUnavailable

PRIVATE_HEADERS = {"Cache-Control": "no-store"}


class PrivateReplanRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, {"status": "invalid_replan_request"}, headers=PRIVATE_HEADERS) from None

        return handle


router = APIRouter(prefix="/replan", tags=["replan"], route_class=PrivateReplanRoute)
LocalSettings = Annotated[Settings, Depends(local_food_log_settings)]


@router.get("/context")
def get_context(
    consumed_on: Annotated[LocalDate, Query(alias="date")], store: Store, response: Response,
) -> ReplanContext:
    try:
        context = replan_context(consumed_on, store.list_confirmed_by_date(consumed_on))
    except FoodLogStorageUnavailable:
        raise HTTPException(503, {"status": "replan_unavailable"}, headers=PRIVATE_HEADERS) from None
    response.headers.update(PRIVATE_HEADERS)
    return context


@router.post("/preview", max_body_size=256 * 1024)
def preview(
    payload: ReplanRequest, store: Store, settings: LocalSettings, response: Response,
) -> ReplanPreview:
    try:
        result = generate_replan_preview(payload, store, settings)
    except ReplanBlocked as error:
        raise HTTPException(error.code, error.detail, headers=PRIVATE_HEADERS) from None
    except (FoodLogStorageUnavailable, PlannerUnavailable, CatalogLoadError):
        raise HTTPException(503, {"status": "replan_unavailable"}, headers=PRIVATE_HEADERS) from None
    except PlannerTimeout:
        raise HTTPException(504, {"status": "replan_timeout"}, headers=PRIVATE_HEADERS) from None
    except PlannerFailure:
        raise HTTPException(502, {"status": "replan_failed"}, headers=PRIVATE_HEADERS) from None
    response.headers.update(PRIVATE_HEADERS)
    return result

from datetime import date
from ipaddress import ip_address
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from app.core.settings import Settings
from app.schemas.food_logs import FoodLog, FoodLogConfirmation, FoodLogCreate, FoodLogDraft, FoodLogUpdate
from app.services.food_reference_binding import FoodReferenceBindingRejected, FoodReferenceBindingUnavailable
from app.storage.food_logs import FoodLogConflict, FoodLogNotFound, FoodLogStore

router = APIRouter(prefix="/food-logs", tags=["food logs"])


def _is_loopback_ip(host: str) -> bool:
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _is_local_hostname(host: str | None) -> bool:
    return bool(host and (host == "localhost" or _is_loopback_ip(host)))


def local_food_log_settings(request: Request) -> Settings:
    settings = request.app.state.settings
    server = request.scope.get("server")
    forbidden = HTTPException(403, "Food logs are accessible only in local development.")
    if (
        settings.environment != "development"
        or not request.client or not _is_loopback_ip(request.client.host)
        or not server or not _is_loopback_ip(server[0])
    ):
        raise forbidden

    try:
        host = urlsplit("//" + request.headers.get("host", ""))
        origin = request.headers.get("origin")
        if (
            not _is_local_hostname(host.hostname) or host.username is not None
            or host.path or host.query or host.fragment
            or (origin is not None and (
                not _is_local_hostname(urlsplit(origin).hostname)
                or origin not in {str(item).rstrip("/") for item in settings.cors_origins}
            ))
        ):
            raise forbidden
    except ValueError:
        raise forbidden from None
    return settings


def local_store(settings: Annotated[Settings, Depends(local_food_log_settings)]) -> FoodLogStore:
    return FoodLogStore(settings.food_log_db_path)


Store = Annotated[FoodLogStore, Depends(local_store)]


@router.post("", status_code=201)
def create_log(payload: FoodLogCreate, store: Store) -> FoodLog:
    return store.create(payload)


@router.get("")
def list_logs(
    consumed_on: Annotated[date, Query(alias="date", description="Consumption date in the recorded UTC offset")],
    store: Store,
) -> list[FoodLog]:
    return store.list_by_date(consumed_on)


@router.put("/{log_id}")
def correct_draft(log_id: UUID, payload: FoodLogUpdate, store: Store) -> FoodLog:
    return store.update(
        log_id, FoodLogDraft.model_validate(payload.model_dump(exclude={"expected_revision", "recognition_applied"})),
        payload.expected_revision, recognition_applied=payload.recognition_applied,
    )


@router.post("/{log_id}/confirm")
def confirm_log(log_id: UUID, payload: FoodLogConfirmation, store: Store) -> FoodLog:
    return store.confirm(log_id, payload.expected_revision)


@router.delete("/{log_id}", status_code=204)
def delete_log(log_id: UUID, expected_revision: Annotated[int, Query(gt=0)], store: Store) -> Response:
    store.delete(log_id, expected_revision)
    return Response(status_code=204)


def food_log_error(_request: Request, exc: Exception) -> Response:
    if isinstance(exc, FoodReferenceBindingRejected):
        return JSONResponse({"detail": {
            "status": "food_reference_binding_rejected", "item_index": exc.item_index, "reason": exc.reason,
        }}, status_code=422)
    if isinstance(exc, FoodReferenceBindingUnavailable):
        return JSONResponse({"detail": "Food reference validation is unavailable."}, status_code=503)
    if isinstance(exc, FoodLogNotFound):
        return JSONResponse({"detail": "Food log not found."}, status_code=404)
    if isinstance(exc, FoodLogConflict):
        return JSONResponse({"detail": "Food log changed or is no longer a draft."}, status_code=409)
    return JSONResponse({"detail": "Food log storage is unavailable."}, status_code=503)

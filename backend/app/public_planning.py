"""Standalone public planner. Start with --no-proxy-headers and one Uvicorn worker."""

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from hashlib import sha256
from hmac import digest
from ipaddress import ip_address, ip_network
from pathlib import Path
from time import monotonic
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import ClientDisconnect

from app.core.settings import Settings
from app.schemas.meal_plans import MealPlanRequest, MealPlanResponse
from app.services.meal_plans import (
    PUBLIC_COMPACT_SCHEMA_MODEL,
    PlannerConstraintUnverified,
    PlannerFailure,
    PlannerInputTooLarge,
    PlannerTimeout,
    PlannerUnavailable,
    generate_meal_plan,
)
from app.storage.planning_quota import QuotaExceeded, QuotaUnavailable, reserve
from app.storage.planning_quota_redis import reserve_redis


ORIGIN = "https://mealmind-ao3k.onrender.com"
PATH = "/api/v1/meal-plans/generate"
BODY_LIMIT = 16 * 1024
LOGGER = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class PublicSettings:
    enabled: bool = False
    quota_path: Path = Path("/var/data/planning-quota.sqlite3")
    quota_secret: str = ""
    trusted_proxies: tuple[str, ...] = ()
    quota_backend: str = "sqlite"
    redis_url: str = ""
    redis_token: str = field(default="", repr=False)

    @classmethod
    def from_env(cls):
        render = os.environ.get("RENDER") == "true"
        backend = os.environ.get("MEALMIND_PUBLIC_QUOTA_BACKEND", "redis" if render else "sqlite")
        proxies = tuple(filter(None, (
            cidr.strip() for cidr in os.environ.get("MEALMIND_PUBLIC_TRUSTED_PROXIES", "").split(",")
        )))
        enabled = os.environ.get("MEALMIND_PUBLIC_PLANNING_ENABLED") == "true"
        return cls(
            enabled=enabled and (not render or (backend == "redis" and bool(proxies))),
            quota_path=Path(os.environ.get("MEALMIND_PUBLIC_QUOTA_PATH", "/var/data/planning-quota.sqlite3")),
            quota_secret=os.environ.get("MEALMIND_PUBLIC_QUOTA_SECRET", ""),
            quota_backend=backend,
            redis_url=os.environ.get("MEALMIND_PUBLIC_REDIS_URL", ""),
            redis_token=os.environ.get("MEALMIND_PUBLIC_REDIS_TOKEN", ""),
            trusted_proxies=proxies,
        )



class PlanningCORS(CORSMiddleware):
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"] == PATH:
            await super().__call__(scope, receive, send)
        else:
            await self.app(scope, receive, send)

def _ip(value: str):
    address = ip_address(value.strip())
    return getattr(address, "ipv4_mapped", None) or address


def _client_address(request: Request, trusted):
    if not request.client:
        raise ValueError("missing client")
    address = _ip(request.client.host)
    if any(address in network for network in trusted):
        hops = request.headers.getlist("x-forwarded-for")
        if len(hops) != 1 or len(hops[0]) > 1024:
            raise ValueError("invalid proxy chain")
        for hop in reversed(hops[0].split(",")):
            address = _ip(hop)
            if all(address not in network for network in trusted):
                return address
        raise ValueError("missing visitor IP")
    if trusted:
        # In proxy mode the service accepts generation only via configured ingress.
        raise ValueError("untrusted peer")
    return address


async def _read_payload(request: Request) -> MealPlanRequest:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, {"status": "invalid_content_type"})
    declared = request.headers.getlist("content-length")
    if declared:
        length = declared[0]
        if len(declared) != 1 or not length.isascii() or not length.isdecimal() or len(length) > 12:
            raise HTTPException(400, {"status": "invalid_request"})
        if int(length) > BODY_LIMIT:
            raise HTTPException(413, {"status": "request_too_large"})
    data = bytearray()
    try:
        async with asyncio.timeout(5):
            async for chunk in request.stream():
                if len(data) + len(chunk) > BODY_LIMIT:
                    raise HTTPException(413, {"status": "request_too_large"})
                data.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, {"status": "request_timeout"}) from None
    except ClientDisconnect:
        raise HTTPException(400, {"status": "invalid_request"}) from None
    try:
        return MealPlanRequest.model_validate_json(data)
    except ValidationError:
        raise HTTPException(422, {"status": "invalid_request"}) from None


def create_public_app(config: PublicSettings | None = None, *, planner_settings: Settings | None = None) -> FastAPI:
    config = config or PublicSettings.from_env()
    settings = planner_settings if planner_settings is not None else Settings(gemini_diagnostics=False, _env_file=None)
    trusted = tuple(ip_network(cidr.strip()) for cidr in config.trusted_proxies)
    if any(network.prefixlen == 0 for network in trusted):
        raise ValueError("Public planner requires specific trusted proxy networks")
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)
    app.add_middleware(
        PlanningCORS, allow_origins=[ORIGIN], allow_methods=["POST"], allow_headers=["Content-Type"],
        expose_headers=["Retry-After", "X-Request-ID"],
    )
    capacity = asyncio.Semaphore(2)
    quota_reserve = {
        "sqlite": partial(reserve, config.quota_path),
        "redis": partial(reserve_redis, config.redis_url, config.redis_token),
    }.get(config.quota_backend)

    @app.post(PATH, response_model=MealPlanResponse)
    async def generate(request: Request, response: Response):
        request_id = uuid4().hex
        trace: dict = {"provider_attempts": 0, "stage": "admission"}
        headers = {"X-Request-ID": request_id, "Cache-Control": "no-store"}
        started = monotonic()
        status = 200
        try:
            if (
                not config.enabled or quota_reserve is None or len(config.quota_secret) < 32 or not settings.gemini_api_key
                or not settings.gemini_api_key.get_secret_value().strip()
                or settings.gemini_model not in {"gemini-3.1-flash-lite", PUBLIC_COMPACT_SCHEMA_MODEL}
            ):
                raise HTTPException(503, {"status": "service_unavailable"})
            try:
                ip = _client_address(request, trusted)
            except ValueError:
                raise HTTPException(403, {"status": "client_unverified"}) from None
            subject = digest(config.quota_secret.encode(), ip.packed, sha256).hex()
            await run_in_threadpool(quota_reserve, subject, datetime.now(UTC))
            query = request.query_params.multi_items()
            if query not in ([], [("infer_scope", "true")], [("infer_scope", "false")]):
                raise HTTPException(422, {"status": "invalid_request"})
            payload = await _read_payload(request)
            if capacity.locked():
                raise HTTPException(429, {"status": "service_busy"}, headers={"Retry-After": "5"})
            async with capacity:
                result = await run_in_threadpool(
                    generate_meal_plan, payload, settings, infer_scope=query == [("infer_scope", "true")],
                    trace=trace, free_recommendation=True,
                    before_provider_call=lambda: quota_reserve("provider", datetime.now(UTC), provider=True),
                )
            response.headers.update(headers)
            return result
        except QuotaExceeded as exc:
            status = 429
            raise HTTPException(status, {"status": exc.reason}, headers={**headers, "Retry-After": str(exc.retry_after)}) from None
        except (QuotaUnavailable, PlannerUnavailable):
            status = 503
            raise HTTPException(status, {"status": "service_unavailable"}, headers=headers) from None
        except PlannerTimeout:
            status = 504
            raise HTTPException(status, {"status": "provider_timeout"}, headers=headers) from None
        except PlannerFailure:
            status = 502
            raise HTTPException(status, {"status": "generation_failed"}, headers=headers) from None
        except PlannerInputTooLarge:
            status = 413
            raise HTTPException(status, {"status": "request_too_large"}, headers=headers) from None
        except PlannerConstraintUnverified as exc:
            status = 422
            raise HTTPException(status, {"status": exc.reason}, headers=headers) from None
        except HTTPException as exc:
            status = exc.status_code
            exc.headers = {**headers, **(exc.headers or {})}
            raise
        except Exception:
            status = 500
            raise HTTPException(status, {"status": "internal_error"}, headers=headers) from None
        finally:
            LOGGER.info(
                "public_planning id=%s status=%d stage=%s attempts=%d upstream_http=%s elapsed_ms=%d input=%s output=%s thinking=%s total=%s",
                request_id, status, trace["stage"], trace["provider_attempts"], trace.get("provider_status"),
                int((monotonic() - started) * 1000),
                trace.get("prompt_token_count"), trace.get("candidates_token_count"),
                trace.get("thoughts_token_count"), trace.get("total_token_count"),
            )

    return app


app = create_public_app()

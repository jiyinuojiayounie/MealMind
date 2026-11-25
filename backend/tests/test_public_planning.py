from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import UTC, datetime, timedelta
from sqlite3 import connect
from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx2
import pytest
from fastapi.testclient import TestClient
from google.genai.errors import ServerError

from app import public_planning
from app.core.settings import Settings
from app.public_planning import BODY_LIMIT, ORIGIN, PATH, PublicSettings, create_public_app
from app.services import meal_plans
from app.storage.planning_quota import QuotaExceeded, initialize_quota, reserve


REQUEST = {
    "user_request": "请给我推荐一份晚餐",
    "scope": "single_meal", "meal_type": "dinner", "ingredient_mode": "flexible", "language": "zh-CN",
}
RESULT = ('{"title":"番茄炒蛋","explanation":"家常做法","meals":[{"meal_type":"dinner",'
          '"estimated_preparation_minutes":12,"dishes":[{"name":"番茄炒蛋","ingredients":'
          '[{"name":"鸡蛋","quantity":2,"unit":"个"}],"instructions":["炒熟后盛出"]}]}]}')
NOW = datetime(2026, 11, 24, 8, tzinfo=UTC)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    path = tmp_path / "quota.sqlite3"
    initialize_quota(path)
    sdk = MagicMock()
    monkeypatch.setattr(meal_plans.genai, "Client", sdk)
    provider = sdk.return_value.__enter__.return_value.models.generate_content
    provider.return_value = SimpleNamespace(text=RESULT, usage_metadata=SimpleNamespace(
        prompt_token_count=1500, candidates_token_count=250, thoughts_token_count=5, total_token_count=1755,
    ))

    def app(*, enabled=True, proxies=(), model="gemini-3.1-flash-lite"):
        return create_public_app(
            PublicSettings(enabled, path, "q" * 32, proxies),
            planner_settings=Settings(gemini_api_key="fixture-only-key", gemini_model=model, _env_file=None),
        )
    return app, path, sdk, provider


def test_only_generation_route_and_cors(fixture, caplog):
    app, _, sdk, provider = fixture
    caplog.set_level("INFO", logger="uvicorn.error")
    with TestClient(app(), client=("192.0.2.10", 5000)) as client:
        headers = {"Origin": ORIGIN, "Access-Control-Request-Method": "POST",
                   "Access-Control-Request-Headers": "content-type"}
        preflight = client.options(PATH, headers=headers)
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == ORIGIN
        assert client.options(PATH, headers={**headers, "Origin": "https://other.example"}).status_code == 400
        provider.assert_not_called()
        for path in ["/openapi.json", "/docs", "/api/v1/health", "/api/v1/food-logs",
                     "/api/v1/food-logs/recognize-text", "/api/v1/nutrition/daily", "/api/v1/replan/context",
                     "/api/v1/meal-plans/local-traces", PATH + "/"]:
            assert client.get(path).status_code == client.post(path).status_code == 404
            assert client.options(path, headers=headers).status_code == 404
        assert client.post(PATH + "?planning_mode=catalog", json=REQUEST).status_code == 422
        response = client.post(PATH + "?infer_scope=true", json=REQUEST, headers={"Origin": ORIGIN})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ORIGIN
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["title"] == "番茄炒蛋"
        provider.assert_called_once()
        config = provider.call_args.kwargs["config"]
        assert config.max_output_tokens == 4096
        assert config.thinking_config.thinking_level == "MINIMAL"
        assert sdk.call_args.kwargs["http_options"].retry_options.attempts == 1
        assert sdk.call_args.kwargs["http_options"].client_args == {"follow_redirects": False}
        assert "input=1500 output=250 thinking=5 total=1755" in caplog.text
        assert REQUEST["user_request"] not in caplog.text
        assert "fixture-only-key" not in caplog.text


@pytest.mark.parametrize("failure,status", [
    (ServerError(503, {"error": {"message": "private upstream detail"}}), 503),
    (httpx2.ReadTimeout("private upstream detail"), 504),
    (None, 502),
])
def test_failures_spend_one_attempt_without_retry(fixture, failure, status, caplog):
    caplog.set_level("INFO", logger="uvicorn.error")
    app, _, _, provider = fixture
    if failure:
        provider.side_effect = failure
    else:
        provider.return_value = SimpleNamespace(text="private upstream detail")
    with TestClient(app(), client=("192.0.2.10", 5000)) as client:
        response = client.post(PATH, json=REQUEST)
        assert response.status_code == status
        assert "private upstream detail" not in response.text
    provider.assert_called_once()
    if status == 503:
        assert "upstream_http=503" in caplog.text
    assert "private upstream detail" not in caplog.text


def test_model_input_budget_is_checked_before_attempt(fixture, monkeypatch):
    app, path, sdk, provider = fixture
    monkeypatch.setattr(meal_plans, "PUBLIC_PROVIDER_INPUT_BYTES", 100)
    with TestClient(app(), client=("192.0.2.10", 5000)) as client:
        assert client.post(PATH, json=REQUEST).status_code == 413
    sdk.assert_not_called()
    provider.assert_not_called()
    with closing(connect(path)) as db:
        assert db.execute("SELECT COUNT(*) FROM events WHERE subject = 'provider'").fetchone() == (0,)


def test_admission_and_spoofed_proxy_headers(fixture):
    app, _, _, provider = fixture
    with TestClient(app(), client=("192.0.2.10", 5000)) as client:
        for number in range(3):
            assert client.post(PATH, json=REQUEST, headers={"X-Forwarded-For": f"198.51.100.{number}"}).status_code == 200
        limited = client.post(PATH, json=REQUEST, headers={"X-Forwarded-For": "203.0.113.9"})
        assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1

    with TestClient(app(proxies=("10.0.0.0/24",)), client=("10.0.0.30", 5000)) as client:
        for number in range(3):
            response = client.post(PATH, json=REQUEST, headers={
                "X-Forwarded-For": f"198.51.100.{number}, 203.0.113.10, 10.0.0.31",
            })
            assert response.status_code == 200
        assert client.post(PATH, json=REQUEST, headers={"X-Forwarded-For": "198.51.100.7, 203.0.113.10"}).status_code == 429
        assert client.post(PATH, json=REQUEST, headers={"X-Forwarded-For": "not-an-ip"}).status_code == 403
        assert client.post(PATH, json=REQUEST, headers={"X-Forwarded-For": "203.0.113.11"}).status_code == 200

    with TestClient(app(proxies=("10.0.0.0/24",)), client=("192.0.2.11", 5000)) as client:
        assert client.post(PATH, json=REQUEST, headers={"X-Forwarded-For": "203.0.113.11"}).status_code == 403
    assert provider.call_count == 7


def test_streaming_size_and_validation(fixture):
    app, _, _, provider = fixture
    with TestClient(app(), client=("192.0.2.10", 5000)) as client:
        headers = {"Content-Type": "application/json"}
        assert client.post(PATH, content=b"x" * (BODY_LIMIT + 1), headers=headers).status_code == 413
        streamed = client.post(PATH, content=iter((b"x" * BODY_LIMIT, b"x")), headers=headers)
        assert "content-length" not in streamed.request.headers
        assert streamed.status_code == 413
        response = client.post(PATH, json={**REQUEST, "user_request": "x" * 2001})
        assert response.status_code == 422
        assert response.json() == {"detail": {"status": "invalid_request"}}
    provider.assert_not_called()


def test_switch_and_storage_fail_closed(fixture):
    app, path, _, provider = fixture
    for factory in (lambda: create_public_app(PublicSettings()), lambda: app(enabled=False)):
        with TestClient(factory()) as client:
            assert client.post(PATH, json=REQUEST).status_code == 503
    path.unlink()
    with TestClient(app(), client=("192.0.2.10", 5000)) as client:
        assert client.post(PATH, json=REQUEST).status_code == 503
    assert not path.exists()
    provider.assert_not_called()


def test_atomic_daily_and_monthly_quota_and_ip_day(fixture, monkeypatch):
    app, path, _, provider = fixture

    def worker(_):
        try:
            reserve(path, "provider", NOW, provider=True)
            return True
        except QuotaExceeded:
            return False

    with ThreadPoolExecutor(max_workers=12) as executor:
        assert sum(executor.map(worker, range(45))) == 30
    monkeypatch.setattr(public_planning, "datetime", SimpleNamespace(now=lambda _: NOW))
    with TestClient(app(), client=("192.0.2.10", 5000)) as client:
        response = client.post(PATH, json=REQUEST)
        assert response.status_code == 429
        assert response.json() == {"detail": {"status": "global_quota"}}
    # New app and connections do not reset the daily or monthly quota.
    with TestClient(app(), client=("192.0.2.11", 5000)) as client:
        assert client.post(PATH, json=REQUEST).status_code == 429
    provider.assert_not_called()

    monthly = path.with_name("monthly.sqlite3")
    initialize_quota(monthly)
    for day in range(1, 21):
        for _ in range(25):
            reserve(monthly, "provider", NOW.replace(day=day), provider=True)
    with pytest.raises(QuotaExceeded) as exc:
        reserve(monthly, "provider", NOW.replace(day=25), provider=True)
    assert exc.value.retry_after == int((NOW.replace(month=12, day=1, hour=0) - NOW.replace(day=25)).total_seconds())
    reserve(monthly, "provider", NOW.replace(month=12, day=1), provider=True)

    for minute in range(10):
        reserve(path, "ip", NOW + timedelta(minutes=minute))
    with pytest.raises(QuotaExceeded):
        reserve(path, "ip", NOW + timedelta(minutes=10))


def test_only_two_provider_calls_in_flight(fixture):
    app, _, _, provider = fixture
    entered = [Event(), Event()]
    release = Event()

    def waiting(**_):
        for event in entered:
            if not event.is_set():
                event.set()
                break
        assert release.wait(8)
        return SimpleNamespace(text=RESULT)

    provider.side_effect = waiting
    with TestClient(app(), client=("192.0.2.10", 5000)) as client, ThreadPoolExecutor(max_workers=2) as executor:
        try:
            futures = [executor.submit(client.post, PATH, json=REQUEST) for _ in range(2)]
            assert all(event.wait(5) for event in entered)
            response = client.post(PATH, json=REQUEST)
            assert response.status_code == 429 and response.json()["detail"]["status"] == "service_busy"
        finally:
            release.set()
        assert all(f.result().status_code == 200 for f in futures)
    assert provider.call_count == 2

def test_compact_provider_schema_preserves_required_fields_and_backend_validation(fixture):
    app, _, _, provider = fixture
    with TestClient(app(model="gemini-3.5-flash-lite"), client=("192.0.2.10", 5000)) as client:
        assert client.post(PATH, json=REQUEST).status_code == 200
        schema = provider.call_args.kwargs["config"].response_json_schema
        assert "$defs" not in schema
        assert schema["required"] == ["title", "meals", "explanation"]
        dish = schema["properties"]["meals"]["items"]["properties"]["dishes"]["items"]
        assert dish["required"] == ["name", "ingredients", "instructions"]
        assert dish["properties"]["ingredients"]["items"]["required"] == ["name", "quantity", "unit"]

        provider.return_value = SimpleNamespace(text=RESULT.replace('"quantity":2', '"quantity":0'))
        assert client.post(PATH, json=REQUEST).status_code == 502

        provider.return_value = SimpleNamespace(text=RESULT.replace('"title":', '"unexpected":true,"title":'))
        assert client.post(PATH, json=REQUEST).status_code == 502
    assert provider.call_count == 3


@pytest.mark.parametrize(("results", "expected"), [
    ([0, 0], 200),
    ([0, 60], 429),
    ([0, -1], 503),
    ([-1], 503),
])
def test_redis_admission_precedes_gemini(fixture, monkeypatch, results, expected):
    from dataclasses import replace
    import requests

    _, path, _, provider = fixture
    config = PublicSettings(
        True, path, "q" * 32, quota_backend="redis",
        redis_url="https://fixture.upstash.io", redis_token="fixture-token",
    )
    settings = Settings(gemini_api_key="fixture-only-key", gemini_model="gemini-3.5-flash-lite", _env_file=None)
    post = MagicMock(side_effect=[
        SimpleNamespace(status_code=200, json=lambda r=result: {"result": r}) for result in results
    ])
    monkeypatch.setattr(requests, "post", post)
    with TestClient(create_public_app(replace(config, enabled=False), planner_settings=settings)) as client:
        assert client.post(PATH, json=REQUEST).status_code == 503
        post.assert_not_called()
    with TestClient(create_public_app(config, planner_settings=settings), client=("192.0.2.10", 5000)) as client:
        assert client.post(PATH, json=REQUEST).status_code == expected
    assert post.call_count == len(results)
    assert provider.call_count == int(expected == 200)
    assert post.call_args_list[0].kwargs["json"][4] != post.call_args_list[0].kwargs["json"][3]
    if len(results) == 2:
        assert post.call_args_list[1].kwargs["json"][4] == post.call_args_list[1].kwargs["json"][3]


def test_render_env_requires_redis_and_trusted_proxy(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("MEALMIND_PUBLIC_PLANNING_ENABLED", "true")
    monkeypatch.delenv("MEALMIND_PUBLIC_QUOTA_BACKEND", raising=False)
    monkeypatch.setenv("MEALMIND_PUBLIC_TRUSTED_PROXIES", " , ")
    assert not PublicSettings.from_env().enabled
    assert PublicSettings.from_env().quota_backend == "redis"

    monkeypatch.setenv("MEALMIND_PUBLIC_TRUSTED_PROXIES", " 192.0.2.0/28 ")
    assert PublicSettings.from_env().enabled
    monkeypatch.setenv("MEALMIND_PUBLIC_QUOTA_BACKEND", "sqlite")
    assert not PublicSettings.from_env().enabled

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.settings import Settings
from app.main import create_app

HEALTH_PATH = "/api/v1/health"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("MEALMIND_SERVICE_NAME", raising=False)
    monkeypatch.delenv("MEALMIND_CORS_ORIGINS", raising=False)
    with TestClient(create_app(Settings(_env_file=None))) as test_client:
        yield test_client


def test_health(client):
    response = client.get(HEALTH_PATH)

    assert response.status_code == 200
    assert response.json() == {"service": "mealmind-api", "status": "ok"}


def test_openapi_and_docs(client):
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    response = schema["paths"][HEALTH_PATH]["get"]["responses"]["200"]
    assert response["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/HealthResponse"
    }


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_local_origins(client, origin):
    response = client.get(HEALTH_PATH, headers={"Origin": origin})

    assert response.headers["access-control-allow-origin"] == origin
    assert "access-control-allow-credentials" not in response.headers


def test_unlisted_origin(client):
    response = client.get(HEALTH_PATH, headers={"Origin": "https://other.example"})

    assert "access-control-allow-origin" not in response.headers


def test_unsupported_preflight_method(client):
    response = client.options(
        HEALTH_PATH,
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PUT",
        },
    )

    assert response.status_code == 400


def test_environment_settings(monkeypatch):
    monkeypatch.setenv("MEALMIND_SERVICE_NAME", "local-api")
    monkeypatch.setenv("MEALMIND_CORS_ORIGINS", '["http://localhost:5174"]')

    with TestClient(create_app(Settings(_env_file=None))) as client:
        response = client.get(HEALTH_PATH, headers={"Origin": "http://localhost:5174"})

    assert response.json()["service"] == "local-api"
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"


@pytest.mark.parametrize("origin", ["*", "https://*.example.com", "https://example.com/path"])
def test_invalid_origins(monkeypatch, origin):
    monkeypatch.setenv("MEALMIND_CORS_ORIGINS", f'["{origin}"]')

    with pytest.raises(ValidationError, match="cors_origins"):
        Settings(_env_file=None)


@pytest.mark.parametrize("path", [
    "/api/v1/meal-plans/generate",
    "/api/v1/meal-plans/generate?infer_scope=true",
])
@pytest.mark.parametrize("origin,expected", [
    ("http://localhost:5173", 200),
    ("http://127.0.0.1:5173", 200),
    ("https://other.example", 400),
])
def test_meal_plan_preflight(client, path, origin, expected):
    response = client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == expected
    if expected == 200:
        assert response.headers["access-control-allow-origin"] == origin
        assert "POST" in response.headers["access-control-allow-methods"]
        assert "content-type" in response.headers["access-control-allow-headers"].lower()
    else:
        assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_meal_plan_unavailable_response_keeps_cors(origin):
    settings = Settings(_env_file=None, GEMINI_API_KEY=None, cors_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",
    ])
    with TestClient(create_app(settings)) as client:
        response = client.post(
            "/api/v1/meal-plans/generate?infer_scope=true",
            headers={"Origin": origin},
            json={
                "user_request": "A quick tofu dinner",
                "language": "en-US",
                "scope": "single_meal",
                "ingredient_mode": "flexible",
            },
        )

    assert response.status_code == 503
    assert response.headers["access-control-allow-origin"] == origin

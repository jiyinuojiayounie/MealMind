import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from google.genai import errors

from app.core.settings import Settings
from app.main import create_app
from app.services import meal_plans

PATH = "/api/v1/food-logs/recognize-text"


@pytest.fixture(autouse=True)
def gemini(monkeypatch):
    factory = MagicMock()
    generate = factory.return_value.__enter__.return_value.models.generate_content
    generate.side_effect = AssertionError("Unexpected Gemini call")
    monkeypatch.setattr(meal_plans.genai, "Client", factory)
    return factory, generate


def client(database, *, environment="development", peer="127.0.0.1", server="127.0.0.1", key="test-key", **options):
    return TestClient(
        create_app(Settings(
            _env_file=None, environment=environment, food_log_db_path=database,
            GEMINI_API_KEY=key, GEMINI_MODEL="test-model", **options,
        )),
        base_url=f"http://{server}:8000", client=(peer, 50000),
    )


def item(name, evidence, portion=None, method=None):
    return dict(name=name, evidence=evidence, portion_text=portion, preparation_method=method)


def output(gemini, items, clarify=False):
    gemini[1].side_effect = None
    gemini[1].return_value = SimpleNamespace(text=json.dumps({
        "items": items, "needs_clarification": clarify,
    }))


@pytest.mark.parametrize("description,proposed,expected", [
    (" 午饭吃了150g鸡胸肉、半碗糙米饭，还有一些青菜。 ",
     [item("鸡胸肉", "150g鸡胸肉", "150g"), item("糙米饭", "半碗糙米饭", "半碗"), item("青菜", "一些青菜", "一些")],
     [("鸡胸肉", 150, "g", None), ("糙米饭", .5, "碗", None), ("青菜", None, None, None)]),
    ("I ate 2 grilled eggs and half a bowl of rice.",
     [item("eggs", "2 grilled eggs", "2", "grilled"), item("rice", "half a bowl of rice", "half a bowl")],
     [("eggs", 2, None, "grilled"), ("rice", .5, "bowl", None)]),
    ("吃了一根banana and 一小把坚果，另外喝了水。",
     [item("banana", "一根banana", "一根"), item("坚果", "一小把坚果", "一小把"), item("水", "喝了水")],
     [("banana", 1, "根", None), ("坚果", 1, "小把", None), ("水", None, None, None)]),
])
def test_recognizes_reviewable_portions_without_persistence(tmp_path, gemini, description, proposed, expected):
    database = tmp_path / "food-logs.sqlite3"
    output(gemini, proposed)
    with client(database) as test:
        response = test.post(PATH, json={"description": description})
        assert not database.exists()
        assert test.get("/api/v1/food-logs?date=2026-11-21").json() == []
    assert response.status_code == 200
    result = response.json()
    assert result["description"] == description
    assert result["status"] == "draft" and result["source"] == "ai_text" and "id" not in result
    assert [(entry["name"], entry["quantity"], entry["unit"], entry["preparation_method"])
            for entry in result["items"]] == expected
    gemini[1].assert_called_once()
    call = gemini[1].call_args.kwargs
    assert json.loads(call["contents"]) == {"description": description}
    assert call["model"] == "test-model"
    assert call["config"].response_mime_type == "application/json"


@pytest.mark.parametrize("description", ["", " \n ", "x" * 2001])
def test_invalid_input_skips_provider(tmp_path, gemini, description):
    with client(tmp_path / "logs.sqlite3") as test:
        assert test.post(PATH, json={"description": description}).status_code == 422
    gemini[0].assert_not_called()


def test_ambiguous_or_unidentified_food(tmp_path, gemini):
    with client(tmp_path / "logs.sqlite3") as test:
        output(gemini, [item("rice", "1–2 bowls of rice", "1–2 bowls")], clarify=True)
        result = test.post(PATH, json={"description": "I ate 1–2 bowls of rice."}).json()
        assert result["items"][0]["quantity"] is None
        assert result["items"][0]["portion_note"] == "portion_needs_review"
        assert result["notes"] == ["description_needs_review"]
        output(gemini, [], clarify=True)
        result = test.post(PATH, json={"description": "I might eat something later."}).json()
        assert result["items"] == []
        assert result["notes"] == ["no_identifiable_foods", "description_needs_review"]


@pytest.mark.parametrize("description,evidence,portion", [
    ("I ate 1–2 bowls of rice.", "2 bowls of rice", "2 bowls"),
    ("我吃了约150g鸡胸肉。", "150g鸡胸肉", "150g"),
    ("我吃了150g鸡胸肉。", "150g鸡胸肉", "150"),
])
def test_truncated_portion_is_not_promoted_to_an_exact_quantity(tmp_path, gemini, description, evidence, portion):
    name = "rice" if "rice" in description else "鸡胸肉"
    output(gemini, [item(name, evidence, portion)])
    with client(tmp_path / "logs.sqlite3") as test:
        response = test.post(PATH, json={"description": description})
    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] is None
    assert response.json()["items"][0]["portion_note"] == "portion_needs_review"


@pytest.mark.parametrize("result", [
    "not-json",
    '{"items":[],"needs_clarification":false,"calories":500}',
    json.dumps({"items": [item("eggs", "eggs", "150 g")], "needs_clarification": False}),
    json.dumps({"items": [item("eggs", "I ate eggs", method="fried")], "needs_clarification": False}),
    json.dumps({"items": [item("beef", "I ate eggs")], "needs_clarification": False}),
    json.dumps({"items": [item("beef", "I ate beef")], "needs_clarification": False}),
])
def test_rejects_malformed_or_ungrounded_output(tmp_path, gemini, result):
    gemini[1].side_effect = None
    gemini[1].return_value = SimpleNamespace(text=result)
    with client(tmp_path / "logs.sqlite3") as test:
        response = test.post(PATH, json={"description": "I ate eggs"})
    assert response.status_code == 502
    assert "I ate eggs" not in response.text


@pytest.mark.parametrize("error,status", [
    (TimeoutError("private-food-description"), 504),
    (errors.ClientError(400, {"error": {"message": "private-food-description test-key"}}), 502),
])
def test_provider_errors_are_sanitized(tmp_path, gemini, caplog, error, status):
    gemini[1].side_effect = error
    with client(tmp_path / "logs.sqlite3", gemini_diagnostics=True) as test:
        response = test.post(PATH, json={"description": "private-food-description"})
    assert response.status_code == status
    assert "private-food-description" not in response.text + caplog.text
    assert "test-key" not in response.text + caplog.text
    gemini[1].assert_called_once()


@pytest.mark.parametrize("options,headers,status", [
    ({"environment": "production"}, {}, 404),
    ({"peer": "192.0.2.1"}, {}, 403),
    ({"server": "192.0.2.1"}, {"host": "localhost:8000"}, 403),
    ({}, {"host": "example.com"}, 403),
    ({}, {"origin": "https://example.com"}, 403),
    ({"key": ""}, {}, 503),
])
def test_unavailable_and_nonlocal_never_call_provider(tmp_path, gemini, options, headers, status):
    database = tmp_path / "logs.sqlite3"
    with client(database, **options) as test:
        assert test.post(PATH, json={"description": "I ate eggs"}, headers=headers).status_code == status
    gemini[0].assert_not_called()
    assert not database.exists()

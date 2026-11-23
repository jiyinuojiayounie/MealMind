import json
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from google.genai import errors
from PIL import Image

from app.core.settings import Settings
from app.main import create_app
from app.services import meal_plans
from app.services.food_images import MAX_IMAGE_BYTES, MAX_REQUEST_BYTES

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


IMAGE_PATH = "/api/v1/food-logs/recognize-image"


def image_bytes(fmt="JPEG", size=(64, 32), **options):
    buffer = BytesIO()
    with Image.new("RGB", size, "orange") as image:
        image.save(buffer, format=fmt, **options)
    return buffer.getvalue()


def image_output(gemini, items, *, needs_review=False):
    gemini[1].side_effect = None
    gemini[1].return_value = SimpleNamespace(text=json.dumps({"items": items, "needs_review": needs_review}))


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_image_suggestion_uses_actual_format_and_never_creates_database(tmp_path, gemini, fmt):
    database = tmp_path / "logs.sqlite3"
    image_output(gemini, [
        {"name": "米饭", "identity_uncertain": False, "count": None, "count_unit": None},
        {"name": "鸡蛋", "identity_uncertain": False, "count": 2, "count_unit": "个"},
        {"name": "蔬菜", "identity_uncertain": True, "count": 3, "count_unit": "片"},
    ])
    with client(database) as test:
        response = test.post(IMAGE_PATH, files={"image": ("misleading.gif", image_bytes(fmt), "image/gif")})

    assert response.status_code == 200
    result = response.json()
    assert not database.exists()
    assert result["description"] is None
    assert result["source"] == "ai_image" and result["status"] == "draft" and "id" not in result
    assert result["notes"] == ["image_needs_review"]
    assert [(item["name"], item["quantity"], item["unit"], item["identity_uncertain"]) for item in result["items"]] == [
        ("米饭", None, None, False), ("鸡蛋", 2, "个", False), ("蔬菜", None, None, True),
    ]
    assert result["items"][0]["portion_note"] == "portion_needs_review"
    assert all(item["preparation_method"] is None for item in result["items"])

    gemini[1].assert_called_once()
    call = gemini[1].call_args.kwargs
    assert call["model"] == "test-model"
    assert call["config"].response_mime_type == "application/json"
    part, = call["contents"]
    assert part.inline_data.mime_type == "image/jpeg"
    with Image.open(BytesIO(part.inline_data.data)) as normalized:
        assert normalized.format == "JPEG"
        assert normalized.size == (64, 32)


def test_normalizes_orientation_dimensions_and_strips_metadata(tmp_path, gemini):
    exif = Image.Exif()
    exif[274] = 6  # Rotate the displayed photo 90 degrees clockwise.
    exif[270] = "private-metadata-fixture"
    image_output(gemini, [])
    with client(tmp_path / "logs.sqlite3") as test:
        response = test.post(IMAGE_PATH, files={"image": ("photo.jpg", image_bytes(size=(1800, 100), exif=exif))})

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["notes"] == ["no_identifiable_foods"]
    normalized_bytes = gemini[1].call_args.kwargs["contents"][0].inline_data.data
    assert b"private-metadata-fixture" not in normalized_bytes
    with Image.open(BytesIO(normalized_bytes)) as normalized:
        assert normalized.size == (89, 1600)
        assert not normalized.getexif()


@pytest.mark.parametrize("make_data,status", [
    (lambda: b"", 400),
    (lambda: b"plain text dressed as an image", 415),
    (lambda: b"\xff\xd8broken JPEG", 400),
    (lambda: image_bytes("PNG")[:30], 400),
    (lambda: image_bytes("GIF"), 415),
    (lambda: b"0" * (MAX_IMAGE_BYTES + 1), 413),
    (lambda: image_bytes("PNG", (8193, 1)), 413),
    (lambda: image_bytes("PNG", (5000, 5000)), 413),
])
def test_rejects_invalid_image_before_gemini(tmp_path, gemini, make_data, status):
    with client(tmp_path / "logs.sqlite3") as test:
        response = test.post(IMAGE_PATH, files={"image": ("image.jpg", make_data(), "image/jpeg")})
    assert response.status_code == status
    gemini[0].assert_not_called()


def test_rejects_animated_supported_format(tmp_path, gemini):
    with Image.new("RGB", (10, 10), "blue") as next_frame:
        animated = image_bytes("PNG", size=(10, 10), save_all=True, append_images=[next_frame], duration=10)
    with client(tmp_path / "logs.sqlite3") as test:
        response = test.post(IMAGE_PATH, files={"image": ("animated.png", animated)})
    assert response.status_code == 415
    gemini[0].assert_not_called()


def test_streaming_multipart_guard_and_single_file_contract(tmp_path, gemini):
    data = image_bytes()
    with client(tmp_path / "logs.sqlite3") as test:
        assert test.post(IMAGE_PATH, content=data).status_code == 415
        assert test.post(IMAGE_PATH, files={"file": ("test.jpg", data)}).status_code == 400
        assert test.post(IMAGE_PATH, files=[("image", ("a.jpg", data)), ("image", ("b.jpg", data))]).status_code == 400
        assert test.post(IMAGE_PATH, headers={"Content-Type": "multipart/form-data"}, content=b"malformed").status_code == 400
        prefix = b'--test\r\nContent-Disposition: form-data; name="image"; filename="test.jpg"\r\n\r\n'
        headers = {"Content-Type": "multipart/form-data; boundary=test"}
        assert test.post(IMAGE_PATH, headers=headers, content=prefix + data + b"\r\n--test\r\n").status_code == 400

        def large_chunks():
            yield prefix
            yield b"x" * MAX_REQUEST_BYTES

        assert test.post(IMAGE_PATH, headers=headers, content=large_chunks()).status_code == 413
    gemini[0].assert_not_called()


@pytest.mark.parametrize("error,status", [
    (TimeoutError("private-fixture"), 504),
    (errors.ClientError(400, {"error": {"message": "private-fixture test-key"}}), 502),
])
def test_image_provider_failure_is_generic(tmp_path, gemini, caplog, error, status):
    gemini[1].side_effect = error
    database = tmp_path / "logs.sqlite3"
    with client(database, gemini_diagnostics=True) as test:
        response = test.post(IMAGE_PATH, files={"image": ("private-fixture.jpg", image_bytes())})
    assert response.status_code == status and not database.exists()
    assert "private-fixture" not in response.text + caplog.text
    assert "test-key" not in response.text + caplog.text
    gemini[1].assert_called_once()


def test_image_provider_cannot_return_weight_or_nutrition_fields(tmp_path, gemini):
    image_output(gemini, [{"name": "米饭", "identity_uncertain": False, "count": 100, "count_unit": "g"}])
    with client(tmp_path / "logs.sqlite3") as test:
        assert test.post(IMAGE_PATH, files={"image": ("photo.jpg", image_bytes())}).status_code == 502


@pytest.mark.parametrize("options,status", [({"environment": "production"}, 404), ({"peer": "192.0.2.1"}, 403)])
def test_image_route_uses_same_local_access_guard(tmp_path, gemini, options, status):
    database = tmp_path / "logs.sqlite3"
    with client(database, **options) as test:
        assert test.post(IMAGE_PATH, files={"image": ("photo.jpg", image_bytes())}).status_code == status
    gemini[0].assert_not_called()
    assert not database.exists()


def test_oversized_webp_canvas_is_rejected_before_opening_decoder(tmp_path, gemini, monkeypatch):
    oversized_canvas = (
        b"RIFF" + (22).to_bytes(4, "little") + b"WEBPVP8X" + (10).to_bytes(4, "little")
        + b"\x00" * 4 + (8192).to_bytes(3, "little") + (31).to_bytes(3, "little")
    )

    def unexpected_open(*args, **kwargs):
        pytest.fail("Oversized WebP should be rejected before opening the decoder")

    monkeypatch.setattr(Image, "open", unexpected_open)
    with client(tmp_path / "logs.sqlite3") as test:
        response = test.post(IMAGE_PATH, files={"image": ("large.webp", oversized_canvas)})
    assert response.status_code == 413
    gemini[0].assert_not_called()


@pytest.mark.parametrize(("description", "name", "evidence", "amount"), [
    ("I put canola oil 9g into a wok; left some behind.", "canola oil", "canola oil 9g", "9g"),
    ("买了 200g 生小白菜，只吃了一半。", "生小白菜", "200g 生小白菜", "200g"),
    ("140g roasted chicken breast, weighed raw.", "roasted chicken breast", "140g roasted chicken breast", "140g"),
    ("Ate banana 120g, weighed with the peel.", "banana", "banana 120g", "120g"),
])
def test_short_recognition_quote_cannot_erase_unsafe_weight_context(tmp_path, gemini, description, name, evidence, amount):
    output(gemini, [item(name, evidence, amount)])
    with client(tmp_path / "logs.sqlite3") as test:
        response = test.post(PATH, json={"description": description})
    assert response.status_code == 200
    assert response.json()["description"] == description
    suggestion = response.json()["items"][0]
    assert suggestion["name"] == name
    assert suggestion["quantity"] is None and suggestion["unit"] is None
    assert suggestion["portion_note"] == "portion_needs_review"


def test_cooking_input_cannot_reach_legacy_nutrition_through_recognition(tmp_path, gemini):
    description = "I poured canola oil 11g into the skillet and discarded the rest."
    output(gemini, [item("canola oil", "canola oil 11g", "11g")])
    with client(tmp_path / "logs.sqlite3") as test:
        suggestion, = test.post(PATH, json={"description": description}).json()["items"]
        suggestion.pop("portion_note")
        draft = test.post("/api/v1/food-logs", json={
            "description": description, "consumed_at": "2026-11-22T20:10:00+08:00",
            "source": "ai_text", "items": [suggestion],
        })
        assert draft.status_code == 201
        saved = draft.json()
        confirmation = test.post(f"/api/v1/food-logs/{saved['id']}/confirm", json={"expected_revision": 1})
        assert confirmation.status_code == 200
        analysis = test.get("/api/v1/nutrition/daily?date=2026-11-22").json()
    assert analysis["calculated_item_count"] == 0
    nutrition = analysis["logs"][0]["items"][0]
    assert nutrition["provenance"]["food_id"] == "canola_oil_as_sold"
    assert nutrition["edible_grams"] is None
    assert nutrition["reasons"] == ["quantity_unknown"]


@pytest.mark.parametrize(("description", "name", "quote", "portion", "quantity", "unit", "decision"), [
    ("我吃了150g糙米饭", "糙米饭", "150g糙米饭", "150g", 150, "g", "accepted"),
    ("买了200g鸡胸肉，只吃了一部分", "鸡胸肉", "200g鸡胸肉", "200g", None, None, "withheld"),
    ("半碗糙米饭", "糙米饭", "半碗糙米饭", "半碗", .5, "碗", "accepted"),
])
def test_evidence_survives_save_and_reopen_without_attesting_to_edible_weight(
    tmp_path, gemini, description, name, quote, portion, quantity, unit, decision,
):
    output(gemini, [item(name, quote, portion)])
    with client(tmp_path / "logs.sqlite3") as test:
        response = test.post(PATH, json={"description": description})
        assert response.status_code == 200
        proposal, = response.json()["items"]
        evidence = proposal["recognition_evidence"]
        assert evidence["quote"] == quote and evidence["portion_text"] == portion
        assert evidence["decision"] == decision
        assert (proposal["quantity"], proposal["unit"]) == (quantity, unit)
        proposal.pop("portion_note")
        payload = {"description": description, "consumed_at": "2026-11-22T20:10:00+08:00",
                   "items": [proposal]}
        saved = test.post("/api/v1/food-logs", json={**payload, "source": "ai_text"}).json()
        assert saved["recognition_weight_review"] is True
        assert saved["items"][0]["recognition_evidence"] == evidence
        edited = test.put(f"/api/v1/food-logs/{saved['id']}", json={
            **payload, "expected_revision": 1, "items": [{**proposal, "quantity": 10}],
        }).json()
        assert edited["recognition_weight_review"] is True
        assert "recognition_evidence" not in edited["items"][0]
        assert "reference_binding" not in edited["items"][0]


@pytest.mark.parametrize(("source", "guarded"), [("ai_text", True), ("ai_image", True), ("manual_text", False)])
def test_mass_calculation_guard_is_persisted_for_new_recognition_logs(tmp_path, source, guarded):
    with client(tmp_path / "logs.sqlite3") as test:
        payload = {"source": source, "consumed_at": "2026-11-22T20:10:00+08:00",
                   "items": [{"name": "canola oil", "quantity": 6, "unit": "g"}]}
        log = test.post("/api/v1/food-logs", json=payload).json()
        confirmed = test.post(f"/api/v1/food-logs/{log['id']}/confirm", json={"expected_revision": 1}).json()
        assert confirmed.get("recognition_weight_review", False) is guarded
        daily = test.get("/api/v1/nutrition/daily?date=2026-11-22").json()
    assert daily["calculated_item_count"] == (0 if guarded else 1)
    assert daily["logs"][0]["items"][0]["reasons"] == (["portion_needs_review"] if guarded else [])


def test_existing_unbound_recognition_log_without_policy_marker_is_unchanged(tmp_path):
    import sqlite3
    from contextlib import closing

    database = tmp_path / "historical.sqlite3"
    with client(database) as test:
        payload = {"source": "ai_text", "consumed_at": "2026-11-22T20:10:00+08:00",
                   "items": [{"name": "canola oil", "quantity": 6, "unit": "g"}]}
        log = test.post("/api/v1/food-logs", json=payload).json()
        confirmed = test.post(f"/api/v1/food-logs/{log['id']}/confirm", json={"expected_revision": 1}).json()
        confirmed.pop("recognition_weight_review")
        # The temporary SQLite row now has the pre-policy persisted JSON shape.
        with closing(sqlite3.connect(database)) as db, db:
            db.execute("UPDATE food_logs SET document = ? WHERE id = ?", (json.dumps(confirmed), log["id"]))
        before = database.read_bytes()
        daily = test.get("/api/v1/nutrition/daily?date=2026-11-22").json()
    assert daily["calculated_item_count"] == 1
    assert database.read_bytes() == before


def test_recognition_applied_to_existing_manual_draft_cannot_clear_mass_guard(tmp_path):
    with client(tmp_path / "logs.sqlite3") as test:
        payload = {"consumed_at": "2026-11-22T20:10:00+08:00",
                   "items": [{"name": "canola oil", "quantity": 6, "unit": "g"}]}
        log = test.post("/api/v1/food-logs", json=payload).json()
        path = f"/api/v1/food-logs/{log['id']}"
        applied = test.put(path, json={**payload, "expected_revision": 1, "recognition_applied": True}).json()
        edited = test.put(path, json={**payload, "expected_revision": 2}).json()
        assert applied["recognition_weight_review"] is edited["recognition_weight_review"] is True
        assert test.post(f"{path}/confirm", json={"expected_revision": 3}).status_code == 200
        assert test.get("/api/v1/nutrition/daily?date=2026-11-22").json()["calculated_item_count"] == 0


@pytest.mark.parametrize(("description", "provider", "expected_items", "cooking_portion"), [
    ("炒菜用了8g油，但锅里还剩一些。", [], [], "8g"),
    ("炒菜用了8g油，但锅里还剩一些。", [item("油", "8g油", "8g")], [], "8g"),
    ("炒菜用了8g油，但锅里还剩一些。", [item("油", "8g油", "8g油")], [], "8g"),
    ("炒菜用了8g油，但锅里还剩一些。", [item("油", "炒菜用了8g油，但锅里还剩一些。")], [], "8g"),
    ("炒菜用了8g油，我吃了2g油。", [item("油", "8g油", "8g"), item("油", "2g油", "2g")],
     [("油", 2)], "8g"),
    ("我吃了6g低芥酸菜籽油。", [item("低芥酸菜籽油", "6g低芥酸菜籽油", "6g")],
     [("低芥酸菜籽油", 6)], None),
    ("做菜用了9g菜籽油，这些油没吃，倒掉了。", [], [], "9g"),
    ("我吃了150g糙米饭、一个鸡蛋，炒菜用了8g油，但锅里还剩一些。",
     [item("糙米饭", "150g糙米饭", "150g"), item("鸡蛋", "一个鸡蛋", "一个"), item("油", "8g油", "8g")],
     [("糙米饭", 150), ("鸡蛋", 1)], "8g"),
    ("没有吃午饭。", [], [], None),
])
def test_text_contract_preserves_cooking_evidence_outside_consumed_items(
    tmp_path, gemini, description, provider, expected_items, cooking_portion,
):
    output(gemini, provider)
    database = tmp_path / "logs.sqlite3"
    with client(database) as test:
        response = test.post(PATH, json={"description": description})
    assert response.status_code == 200
    parsed = response.json()
    assert [(entry["name"], entry["quantity"]) for entry in parsed["items"]] == expected_items
    if cooking_portion:
        evidence, = parsed["cooking_evidence"]
        assert evidence["portion_text"] == cooking_portion and evidence["quote"] in description
        assert set(evidence) == {"quote", "portion_text"}
    else:
        assert "cooking_evidence" not in parsed
    assert not database.exists()
    gemini[1].assert_called_once()


@pytest.mark.parametrize("invalid_provider", ["schema", "grounding"])
def test_only_cooking_evidence_survives_invalid_recognition_output(tmp_path, gemini, invalid_provider):
    description = "炒菜用了8g油，但锅里还剩一些"
    if invalid_provider == "schema":
        gemini[1].side_effect = None
        gemini[1].return_value = SimpleNamespace(text='{"items":null,"needs_clarification":true}')
    else:
        output(gemini, [item("油", "8g油", "8 g")])
    database = tmp_path / "logs.sqlite3"
    with client(database) as test:
        response = test.post(PATH, json={"description": description})
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["cooking_evidence"] == [{"quote": "炒菜用了8g油", "portion_text": "8g"}]
    assert not database.exists()
    gemini[1].assert_called_once()


def test_mixed_input_recognition_failure_is_not_hidden_by_cooking_evidence(tmp_path, gemini):
    output(gemini, [item("米饭", "150 g米饭", "150 g")])
    with client(tmp_path / "logs.sqlite3") as test:
        response = test.post(PATH, json={"description": "我吃了150g米饭，炒菜用了8g油，但锅里还剩一些"})
    assert response.status_code == 502

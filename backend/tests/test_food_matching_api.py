import pytest

from test_food_logs import DATE, DRAFT, PATH, client_for

PREVIEW = "/api/v1/food-normalization/preview"


def test_preview_handles_shared_items_without_opening_database(tmp_path):
    database = tmp_path / "logs.sqlite3"
    with client_for(database) as client:
        response = client.post(PREVIEW, json={"items": [
            {"item": {"name": "raw pak choi"}},
            {"item": {"name": "鸡胸肉", "quantity": 150, "unit": "g"}},
            {"item": {"name": "cooked long-grain brown rice", "quantity": 0.5, "unit": "bowl"}},
            {"item": {"name": "全熟去壳水煮蛋"}, "identity_uncertain": True},
            {"item": {"name": "海南鸡饭"}},
        ]})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    automatic, ambiguous, rice, photo, gap = response.json()
    assert automatic["reference"]["food_id"] == "bok_choy_raw"
    assert automatic["reference"]["fdc_id"] > 0 and automatic["source_release"]
    assert automatic["original"] == "raw pak choi"
    assert automatic["portion_status"] == "quantity_unknown"
    assert automatic["requires_edible_weight_confirmation"] is False
    assert ambiguous["identity_status"] == "food_state_unknown"
    assert ambiguous["quantity"] == "150.0" and ambiguous["unit"] == "g"
    assert ambiguous["requires_edible_weight_confirmation"] is True
    assert {item["state"] for item in ambiguous["candidates"]} == {"raw", "cooked"}
    assert rice["portion_status"] == "conversion_unavailable"
    assert rice["requires_edible_weight_confirmation"] is False
    assert photo["reference"] is None and photo["clarification"] == "confirm_identity"
    assert gap["identity_status"] == "unsupported_food" and not gap["candidates"]
    assert not database.exists()


@pytest.mark.parametrize("source", ["manual_text", "ai_text", "ai_image"])
def test_existing_save_confirm_and_preview_leave_confirmed_record_untouched(tmp_path, source):
    database = tmp_path / "logs.sqlite3"
    with client_for(database) as client:
        created = client.post(PATH, json={**DRAFT, "source": source})
        assert created.status_code == 201
        draft = created.json()
        confirmed = client.post(f"{PATH}/{draft['id']}/confirm", json={"expected_revision": draft["revision"]})
        assert confirmed.status_code == 200
        before = {p.name: p.read_bytes() for p in database.parent.glob("logs.sqlite3*")}
        response = client.post(PREVIEW, json={"items": [{"item": item} for item in draft["items"]]})
        assert response.status_code == 200
        assert {p.name: p.read_bytes() for p in database.parent.glob("logs.sqlite3*")} == before
        assert client.get(PATH, params={"date": DATE}).json() == [confirmed.json()]


@pytest.mark.parametrize(("settings", "expected"), [
    ({"environment": "production"}, 404),
    ({"peer": "10.0.0.2"}, 403),
    ({"server": "10.0.0.2"}, 403),
])
def test_preview_private_to_local_development(tmp_path, settings, expected):
    with client_for(tmp_path / "logs.sqlite3", **settings) as client:
        assert client.post(PREVIEW, json={"items": [{"item": {"name": "raw pak choi"}}]}).status_code == expected


@pytest.mark.parametrize("payload", [
    {"items": []}, {"items": [{"item": {"name": " "}}]},
    {"items": [{"item": {"name": "egg", "quantity": -2}}]},
    {"items": [{"item": {"name": "egg"}, "identity_uncertain": "true"}]},
])
def test_preview_rejects_invalid_payload(tmp_path, payload):
    with client_for(tmp_path / "logs.sqlite3") as client:
        assert client.post(PREVIEW, json=payload).status_code == 422

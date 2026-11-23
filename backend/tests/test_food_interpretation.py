from decimal import Decimal

import pytest

from app.services.food_interpretation import preview_interpreted_food
from test_food_logs import client_for


def test_attached_bilingual_mass_and_state_stay_separate_from_the_draft_item():
    for sentence, name, preparation, context in (
        ("午饭吃了150g生鸡胸肉", "鸡胸肉", "raw", "consumed"),
        ("150g chicken breast, cooked", "chicken breast", "cooked", "unknown"),
    ):
        result = preview_interpreted_food(sentence)
        row, = result.items
        observed, = row.mention.observations
        assert result.interpretation.original == sentence
        assert row.proposal.name == name and row.proposal.preparation_method == preparation
        assert row.proposal.quantity is None and row.portion_status == "needs_review"
        assert observed.quantity == Decimal(150) and observed.unit == "g" and observed.context == context
        assert sentence[observed.span.start:observed.span.end] == "150g"
        assert row.reference_match.reference is None
        assert {candidate.state for candidate in row.reference_match.candidates} == {preparation}


@pytest.mark.parametrize(("sentence", "context", "basis"), [
    ("炒了8g油但锅里还剩一些", "cooking_input", "unknown"),
    ("买了200g鸡胸肉，只吃了一部分", "purchased", "unknown"),
    ("带骨鸡腿200g", "unknown", "includes_inedible"),
    ("100g干面煮熟以后吃掉了", "prepared", "unknown"),
    ("昨天剩下的饭，今天吃了一半", "consumed", "unknown"),
    ("I served 60g cooked rice noodles", "served", "unknown"),
    ("canola oil 8g in the skillet; some left behind", "cooking_input", "unknown"),
])
def test_observed_amounts_are_not_promoted_to_consumed_edible_mass(sentence, context, basis):
    row, = preview_interpreted_food(sentence).items
    observed, = row.mention.observations
    assert observed.context == context and observed.basis == basis
    assert row.portion_status == "needs_review"
    assert not row.proposal or row.proposal.quantity is None
    if sentence.startswith("100g"):
        assert observed.weighing_state == "dry" and row.mention.preparation == "cooked"


def test_divides_explicit_mentions_without_decomposing_mixed_dishes():
    split = preview_interpreted_food("吃了一个鸡蛋和一些青菜")
    assert [item.proposal.name for item in split.items] == ["鸡蛋", "青菜"]
    assert [item.portion_status for item in split.items] == ["conversion_unavailable", "quantity_unknown"]
    mixed, = preview_interpreted_food("一碗海南鸡饭").items
    assert mixed.proposal.name == "海南鸡饭"
    assert mixed.reference_match.identity_status == "unsupported_food"
    combined, = preview_interpreted_food("I ate 2 pieces of chicken and one cup of rice mixed together").items
    assert combined.portion_status == "needs_review"
    assert combined.reference_match is None
    bowl, = preview_interpreted_food("半碗糙米饭").items
    assert bowl.proposal.quantity == .5 and bowl.portion_status == "conversion_unavailable"
    assert bowl.reference_match.portion_source_row_id is None


def test_skipped_and_planned_meals_cannot_create_a_proposal():
    result = preview_interpreted_food("没有吃午饭")
    assert result.interpretation.status == "no_consumption" and not result.items
    intention = preview_interpreted_food("I want to eat 90g chicken breast")
    assert intention.interpretation.status == "review_required"
    assert not any(item.proposal for item in intention.items)


def test_interpret_then_match_a_verified_reference_without_supplying_weight():
    row, = preview_interpreted_food("I ate 92g skinless boneless chicken breast, stewed").items
    assert row.reference_match.reference.food_id == "chicken_breast_meat_stewed"
    assert row.reference_match.reference.state == "cooked"
    assert row.proposal.quantity is None
    assert row.portion_status == "needs_review"


def test_interpretation_api_is_read_only_and_local(tmp_path):
    path = "/api/v1/food-normalization/interpret"
    database = tmp_path / "no-write.sqlite"
    with client_for(database) as client:
        response = client.post(path, json={"text": "半碗糙米饭"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["items"][0]["portion_status"] == "conversion_unavailable"
        assert client.post(path, json={"text": "x" * 2001}).status_code == 422
    with client_for(database, environment="production") as client:
        assert client.post(path, json={"text": "半碗糙米饭"}).status_code == 404
    with client_for(database, peer="192.0.2.1") as client:
        assert client.post(path, json={"text": "半碗糙米饭"}).status_code == 403
    assert not database.exists()

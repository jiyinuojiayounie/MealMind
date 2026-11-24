import json
from copy import deepcopy
from pathlib import Path

import pytest

from app.services.recipe_catalog import (
    DEVELOPMENT_CATALOG_PATH,
    CatalogLoadError,
    load_recipe_catalog,
    production_recipes,
)

EVIDENCE = {
    "reference": "synthetic review record",
    "reviewer": "fixture reviewer",
    "reviewed_on": "2026-01-01",
}
REVIEWED_ABSENCE = {
    "status": "no_known_source_in_reviewed_recipe",
    "evidence": EVIDENCE,
}


@pytest.fixture
def data():
    return json.loads(DEVELOPMENT_CATALOG_PATH.read_text(encoding="utf-8"))


@pytest.fixture
def load(tmp_path):
    path = tmp_path / "fixture-v1.json"

    def load_fixture(data):
        path.write_text(json.dumps(data), encoding="utf-8")
        return load_recipe_catalog(path)

    return load_fixture


@pytest.fixture
def reviewed(data):
    data["recipes"] = data["recipes"][:1]
    recipe = data["recipes"][0]
    recipe["review"] = {"status": "reviewed", "evidence": EVIDENCE}
    recipe["provenance"].update({
        "source_kind": "original_reviewed",
        "source_reference": "synthetic source",
        "attribution": "fixture author",
        "license_or_permission": "synthetic permission for tests only",
    })
    return data


def test_development_catalog_loads_and_excludes_all_drafts():
    catalog = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH)
    assert catalog.schema_version == 1
    assert catalog.catalog_version == 4
    assert len(catalog.recipes) == 26
    assert len(catalog.ingredients) == 37
    assert all(recipe.review.status == "draft" for recipe in catalog.recipes)
    assert not production_recipes(catalog)
    assert not production_recipes(catalog, excluded_allergens=["peanut"])


def test_multiple_dish_roles_and_meal_categories():
    catalog = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH)
    assert any(set(recipe.dish_roles) == {"protein", "staple", "vegetable"} for recipe in catalog.recipes)
    assert {"breakfast", "lunch", "dinner", "snack"} == {
        slot for recipe in catalog.recipes for slot in recipe.meal_types
    }
    assert any(
        {"breakfast", "lunch", "dinner"}.issubset(recipe.meal_types)
        for recipe in catalog.recipes
    )


def test_invalid_json_and_missing_files(tmp_path):
    path = tmp_path / "missing.json"
    with pytest.raises(CatalogLoadError, match="Cannot read recipe catalog"):
        load_recipe_catalog(path)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(CatalogLoadError, match="Invalid JSON"):
        load_recipe_catalog(path)


@pytest.mark.parametrize("field,value,location", [
    ("quantity", 0, "recipes.0.ingredients.0.quantity"),
    ("quantity", -2, "recipes.0.ingredients.0.quantity"),
    ("quantity", float("inf"), "recipes.0.ingredients.0.quantity"),
    ("quantity", "40", "recipes.0.ingredients.0.quantity"),
    ("unit", "cup", "recipes.0.ingredients.0.unit"),
    ("state", "unknown_state", "recipes.0.ingredients.0.state"),
    ("household_portion", {"label": {"zh-CN": "一碗", "en-US": "one bowl"}}, "household_portion.evidence"),
])
def test_malformed_ingredient_entries(data, load, field, value, location):
    data["recipes"][0]["ingredients"][0][field] = value
    with pytest.raises(CatalogLoadError, match=location):
        load(data)


@pytest.mark.parametrize("field,value,diagnostic", [
    ("preparation_minutes", -1, "preparation_minutes"),
    ("cooking_minutes", -1, "cooking_minutes"),
    ("waiting_minutes", -1, "waiting_minutes"),
    ("total_minutes", 1, "total_minutes must cover"),
])
def test_invalid_recipe_times(data, load, field, value, diagnostic):
    data["recipes"][0]["times"][field] = value
    with pytest.raises(CatalogLoadError, match=diagnostic):
        load(data)


def test_duplicate_recipe_and_ingredient_ids(data, load):
    data["recipes"].append(deepcopy(data["recipes"][0]))
    data["ingredients"].append(deepcopy(data["ingredients"][0]))
    with pytest.raises(CatalogLoadError, match="duplicate ingredient ID ingredient_rice.*duplicate recipe ID recipe_000001"):
        load(data)


def test_unknown_ingredient_identifies_recipe(data, load):
    data["recipes"][0]["ingredients"][0]["ingredient_id"] = "ingredient_unlisted"
    with pytest.raises(CatalogLoadError, match="recipe_000001 references unknown ingredient ingredient_unlisted"):
        load(data)


def test_draft_cannot_be_published_by_changing_status(data, load):
    data["recipes"][0]["review"] = {"status": "reviewed", "evidence": EVIDENCE}
    with pytest.raises(CatalogLoadError, match="development draft provenance"):
        load(data)


def test_reviewed_recipe_requires_reuse_permission(reviewed, load):
    del reviewed["recipes"][0]["provenance"]["license_or_permission"]
    with pytest.raises(CatalogLoadError, match="reuse permission"):
        load(reviewed)


def test_reviewed_and_retired_filtering(reviewed, load):
    retired = deepcopy(reviewed["recipes"][0])
    retired["recipe_id"] = "recipe_900002"
    retired["review"]["status"] = "retired"
    reviewed["recipes"].append(retired)
    assert [recipe.recipe_id for recipe in production_recipes(load(reviewed))] == ["recipe_000001"]


@pytest.mark.parametrize("assessment", [None, {"status": "unknown"}, {"status": "unverified"}, {"status": "contains"}])
@pytest.mark.parametrize("level", ["recipe", "ingredient"])
def test_allergen_exclusions_require_positive_review_evidence(reviewed, load, assessment, level):
    recipe = reviewed["recipes"][0]
    recipe["allergens"]["peanut"] = REVIEWED_ABSENCE
    for item in reviewed["ingredients"]:
        item["allergens"] = {"peanut": REVIEWED_ABSENCE}

    assert len(production_recipes(load(reviewed), excluded_allergens=["peanut"])) == 1

    target = recipe if level == "recipe" else next(
        item for item in reviewed["ingredients"] if item["ingredient_id"] == recipe["ingredients"][0]["ingredient_id"]
    )
    if assessment is None:
        del target["allergens"]["peanut"]
    else:
        target["allergens"]["peanut"] = assessment
    assert not production_recipes(load(reviewed), excluded_allergens=["peanut"])


def test_allergen_absence_claim_without_evidence_is_invalid(reviewed, load):
    reviewed["recipes"][0]["allergens"]["peanut"] = {"status": "no_known_source_in_reviewed_recipe"}
    with pytest.raises(CatalogLoadError, match="reviewed allergen absence requires evidence"):
        load(reviewed)


def test_verified_household_label(load, reviewed):
    item = reviewed["recipes"][0]["ingredients"][0]
    item["household_portion"] = {
        "label": {"zh-CN": "测试份量", "en-US": "test portion"},
        "size_basis": "synthetic fixture for the stated weight and preparation state",
        "confidence": "verified",
        "evidence": EVIDENCE,
    }
    assert load(reviewed).recipes[0].ingredients[0].household_portion.confidence == "verified"


def test_release_candidate_updates_only_selected_drafts():
    prior = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH.with_name("catalog-v2.json"))
    candidate = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH.with_name("catalog-v3.json"))
    selected = {1, 2, 4, 5, 6, 8, 10, 14, 16, 17, 18, 19}

    assert candidate.ingredients == prior.ingredients
    assert len(candidate.recipes) == len(prior.recipes)
    for old, new in zip(prior.recipes, candidate.recipes, strict=True):
        if int(old.recipe_id.removeprefix("recipe_")) not in selected:
            assert old == new
            continue
        assert new.recipe_id == old.recipe_id and new.dish_family_id == old.dish_family_id
        assert new.revision == old.revision + 1
        assert new.ingredients == old.ingredients
        assert new.review.status == "draft" and new.review.evidence is None
        assert new.allergens == old.allergens and new.dietary == old.dietary
        assert new.serving_description and new.verification_notes
        assert len(new.steps.zh_cn) == len(new.steps.en_us) >= 2
        assert new.flavor and new.flavor.status == "provisional"
        assert new.flavor.evidence is None and not new.flavor.has_verified_heat

    assert not production_recipes(candidate)


@pytest.mark.parametrize("heat,evidence", [
    ("non_spicy", None),
    ("unknown", EVIDENCE),
])
def test_verified_heat_requires_known_level_and_evidence(data, load, heat, evidence):
    data["recipes"][0]["flavor"] = {
        "heat": heat, "status": "verified", "basis": "Fixture only", "evidence": evidence,
    }
    with pytest.raises(CatalogLoadError, match="verified flavor requires a known heat level"):
        load(data)


def test_rinsing_and_cooking_water_remain_separate():
    catalog = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH)
    by_id = {recipe.recipe_id: recipe for recipe in catalog.recipes}
    for recipe_id, cooking_volume in (("recipe_000001", 450), ("recipe_000014", 160)):
        recipe = by_id[recipe_id]
        assert recipe.process_water.purpose == "rinse"
        assert recipe.process_water.quantity_ml is None
        assert {i.quantity for i in recipe.ingredients if i.ingredient_id == "ingredient_water"} == {
            cooking_volume
        }


def test_blind_box_batch_is_a_separate_one_person_draft_catalog():
    batch_path = Path(__file__).resolve().parents[2] / "frontend/src/data/blind-box-batch-02.json"
    batch = load_recipe_catalog(batch_path)
    base = load_recipe_catalog(DEVELOPMENT_CATALOG_PATH)
    assert len(batch.recipes) == 24
    assert not production_recipes(batch)
    assert len({recipe.dish_family_id for recipe in batch.recipes}) == 24
    assert {recipe.recipe_id for recipe in batch.recipes}.isdisjoint(recipe.recipe_id for recipe in base.recipes)
    for slot, count in (("breakfast", 7), ("lunch", 20), ("dinner", 17)):
        assert sum(slot in recipe.meal_types for recipe in batch.recipes) == count
    external = [recipe for recipe in batch.recipes if recipe.provenance.source_kind == "licensed_external"]
    assert len(external) == 5
    for recipe in external:
        source = recipe.provenance
        assert source.attribution and source.source_reference.startswith("https://github.com/Anduin2017/HowToCook/")
        assert "Unlicense" in source.license_or_permission
    for recipe in batch.recipes:
        assert recipe.servings == 1 and recipe.review.status == "draft" and recipe.review.evidence is None
        assert recipe.verification_notes and len(recipe.steps.zh_cn) == len(recipe.steps.en_us) >= 3
        assert all(assessment.status == "contains" and assessment.evidence is None
                   for assessment in recipe.allergens.values())
        for item in recipe.ingredients:
            if item.ingredient_id == "ingredient_rice":
                assert recipe.times.starting_assumptions and item.state == "cooked" and item.required_starting_state

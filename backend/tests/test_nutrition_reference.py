import csv
import hashlib
from copy import deepcopy
from io import StringIO
from zipfile import ZipFile

import pytest
from pydantic import ValidationError

from app.schemas.nutrition_reference import ARCHIVE_URL, FDC_URL, NUTRIENT_DEFINITIONS, NutritionReference
from app.services.nutrition_reference import load_nutrition_reference
from scripts.verify_nutrition_reference import verify_nutrition_source


@pytest.fixture
def synthetic(tmp_path):
    """Synthetic USDA-shaped fixture only. Never loaded by application code."""
    archive = tmp_path / "synthetic.zip"
    tables = {
        "food": [("fdc_id", "data_type", "description", "publication_date"),
                 (987001, "sr_legacy_food", "Fixture food, raw", "2019-04-01")],
        "sr_legacy_food": [("fdc_id", "NDB_number"), (987001, "12345")],
        "nutrient": [("id", "name", "unit_name"),
                     *((id_, name, unit.upper()) for id_, name, unit in NUTRIENT_DEFINITIONS.values())],
        "food_nutrient": [("id", "fdc_id", "nutrient_id", "amount", "footnote"),
                          (919, 987001, 1008, "113.25", ""), (920, 987001, 1003, "0", ""),
                          (921, 987001, 1005, "", ""), (922, 987001, 1004, "0.1", "Trace fixture")],
        "food_portion": [("id", "fdc_id", "amount", "measure_unit_id", "modifier", "gram_weight",
                          "footnote", "portion_description"),
                         (700, 987001, 1, 9999, "synthetic piece", "130.5", "", "")],
    }
    with ZipFile(archive, "w") as zip_file:
        for name, rows in tables.items():
            stream = StringIO()
            csv.writer(stream).writerows(rows)
            zip_file.writestr(f"FoodData_Central_sr_legacy_food_csv_2018-04/{name}.csv", stream.getvalue())
    data = {
        "schema_version": 1, "reference_version": "usda-sr-legacy-v1",
        "source": {
            "provider": "USDA FoodData Central", "data_type": "sr_legacy_food", "release": "2018-04",
            "archive_url": ARCHIVE_URL, "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
            "retrieved_on": "2026-11-21", "license": "CC0-1.0", "license_url": "https://fdc.nal.usda.gov/",
        },
        "basis": "per_100g_edible", "unresolved_labels": ["fixture food"],
        "nutrient_definitions": {
            key: {"usda_nutrient_id": id_, "name": name, "unit": unit}
            for key, (id_, name, unit) in NUTRIENT_DEFINITIONS.items()
        },
        "foods": [{
            "food_id": "fixture_raw", "names": {"zh_cn": "测试食物（生）", "en_us": "Fixture food (raw)"},
            "aliases": ["raw fake sample"], "state": "raw", "category": "grains", "preparation": "Raw",
            "source": {"fdc_id": 987001, "ndb_number": "12345", "publication_date": "2019-04-01",
                       "description": "Fixture food, raw", "url": FDC_URL.format(fdc_id=987001)},
            "nutrients": {
                "energy_kcal": {"amount": 113.25, "source_row_id": 919},
                "protein_g": {"amount": 0, "source_row_id": 920},
                "carbohydrate_g": None, "fat_g": None,
            },
            "limitations": ["Synthetic fixture only."],
            "portions": [{"source_row_id": 700, "amount": 1, "measure_unit_id": 9999,
                          "modifier": "synthetic piece", "edible_grams": 130.5,
                          "applicability": "Synthetic fixture only."}],
        }],
    }
    return data, archive


def validate(data):
    return NutritionReference.model_validate(data)


def test_versioned_reference_snapshot():
    reference = load_nutrition_reference()
    assert len(reference.foods) == 30
    assert sum(len(food.portions) for food in reference.foods) == 3
    states = {food.food_id: food.state for food in reference.foods}
    assert states["chicken_breast_skinless_boneless_raw"] == "raw"
    assert states["chicken_breast_meat_roasted"] == "cooked"
    assert states["rice_noodles_dry"] == "dry"
    assert states["rice_noodles_cooked"] == "cooked"


def test_missing_and_trace_nutrients_stay_null_while_source_zero_is_valid(synthetic):
    data, archive = synthetic
    reference = validate(data)
    verify_nutrition_source(reference, archive)
    nutrients = reference.foods[0].nutrients
    assert nutrients.protein_g.amount == 0
    assert nutrients.carbohydrate_g is None
    assert nutrients.fat_g is None


@pytest.mark.parametrize("field", ["archive_sha256", "release", "license", "retrieved_on"])
def test_required_release_metadata(synthetic, field):
    data, _ = synthetic
    del data["source"][field]
    with pytest.raises(ValidationError):
        validate(data)


@pytest.mark.parametrize("amount", [-1, "5", False, float("inf"), float("nan"), 101])
def test_invalid_nutrient_amounts(synthetic, amount):
    data, _ = synthetic
    data["foods"][0]["nutrients"]["protein_g"]["amount"] = amount
    with pytest.raises(ValidationError):
        validate(data)


def test_rejects_wrong_nutrient_units_and_omitted_fields(synthetic):
    data, _ = synthetic
    data["nutrient_definitions"]["protein_g"]["unit"] = "kcal"
    with pytest.raises(ValidationError, match="definitions"):
        validate(data)
    data["nutrient_definitions"]["protein_g"]["unit"] = "g"
    del data["foods"][0]["nutrients"]["fat_g"]
    with pytest.raises(ValidationError, match="fat_g"):
        validate(data)


def test_rejects_duplicates_and_ambiguous_raw_or_cooked_labels(synthetic):
    data, _ = synthetic
    raw = data["foods"][0]
    cooked = deepcopy(raw)
    data["foods"].append(cooked)
    with pytest.raises(ValidationError, match="Duplicate food or source ID"):
        validate(data)
    cooked.update(food_id="fixture_cooked", state="cooked")
    cooked["source"].update(fdc_id=987002, url=FDC_URL.format(fdc_id=987002))
    with pytest.raises(ValidationError, match="state conflicts"):
        validate(data)
    cooked.update(names={"zh_cn": "测试食物（熟）", "en_us": "Fixture food (cooked)"}, aliases=["raw fake sample"])
    cooked["source"]["description"] = "Fixture food, cooked"
    with pytest.raises(ValidationError, match="cannot resolve"):
        validate(data)
    cooked["aliases"] = ["  Ｆｉｘｔｕｒｅ  Ｆｏｏｄ  "]
    with pytest.raises(ValidationError, match="unresolved food label"):
        validate(data)
    raw["aliases"] = ["shared alias"]
    cooked["aliases"] = ["  SHARED  alias "]
    with pytest.raises(ValidationError, match="Duplicate or unresolved food label"):
        validate(data)


def test_requires_source_link_and_per_value_nutrient_row(synthetic):
    data, _ = synthetic
    data["foods"][0]["source"]["url"] = FDC_URL.format(fdc_id=987002)
    with pytest.raises(ValidationError, match="match its FDC ID"):
        validate(data)
    data["foods"][0]["source"]["url"] = FDC_URL.format(fdc_id=987001)
    del data["foods"][0]["nutrients"]["energy_kcal"]["source_row_id"]
    with pytest.raises(ValidationError, match="source_row_id"):
        validate(data)


@pytest.mark.parametrize("key,new_value", [
    ("energy_kcal", {"amount": 114, "source_row_id": 919}),
    ("protein_g", {"amount": 0, "source_row_id": 923}),
    ("carbohydrate_g", {"amount": 0, "source_row_id": 921}),
    ("fat_g", {"amount": 0.1, "source_row_id": 922}),
])
def test_source_audit_rejects_changed_values_and_fallbacks(synthetic, key, new_value):
    data, archive = synthetic
    data["foods"][0]["nutrients"][key] = new_value
    with pytest.raises(ValueError, match="USDA nutrient value or row ID differs"):
        verify_nutrition_source(validate(data), archive)


def test_source_audit_rejects_portion_from_another_food_or_wrong_weight(synthetic):
    data, archive = synthetic
    data["foods"][0]["portions"][0]["edible_grams"] = 145
    with pytest.raises(ValueError, match="USDA portion"):
        verify_nutrition_source(validate(data), archive)


def test_source_audit_rejects_unpinned_archive(synthetic):
    data, archive = synthetic
    data["source"]["archive_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        verify_nutrition_source(validate(data), archive)

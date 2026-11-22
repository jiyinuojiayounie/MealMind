"""Compare the curated snapshot with USDA's official, pinned CSV archive."""

import argparse
import csv
import hashlib
from decimal import Decimal
from io import TextIOWrapper
from pathlib import Path
from zipfile import ZipFile

from app.schemas.nutrition_reference import NutritionReference
from app.services.nutrition_reference import load_nutrition_reference


def _table(archive: ZipFile, name: str):
    table_path = f"FoodData_Central_sr_legacy_food_csv_2018-04/{name}.csv"
    with archive.open(table_path) as file, TextIOWrapper(file, encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def verify_nutrition_source(reference: NutritionReference, archive_path: Path) -> None:
    with archive_path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != reference.source.archive_sha256:
            raise ValueError("USDA archive checksum does not match the pinned release")

    fdc_ids = {str(food.source.fdc_id) for food in reference.foods}
    nutrient_ids = {str(definition.usda_nutrient_id) for definition in reference.nutrient_definitions.values()}
    portion_ids = {str(portion.source_row_id) for food in reference.foods for portion in food.portions}
    with ZipFile(archive_path) as archive:
        foods = {row["fdc_id"]: row for row in _table(archive, "food") if row["fdc_id"] in fdc_ids}
        legacy = {row["fdc_id"]: row["NDB_number"] for row in _table(archive, "sr_legacy_food")
                  if row["fdc_id"] in fdc_ids}
        nutrients = {row["id"]: row for row in _table(archive, "nutrient") if row["id"] in nutrient_ids}
        entries = {}
        for row in _table(archive, "food_nutrient"):
            if row["fdc_id"] in fdc_ids and row["nutrient_id"] in nutrient_ids:
                key = (row["fdc_id"], row["nutrient_id"])
                if key in entries:
                    raise ValueError(f"USDA has multiple rows for food/nutrient {key}")
                entries[key] = row
        portions = {row["id"]: row for row in _table(archive, "food_portion") if row["id"] in portion_ids}

    for definition in reference.nutrient_definitions.values():
        row = nutrients.get(str(definition.usda_nutrient_id))
        if row is None or (row["name"], row["unit_name"].lower()) != (definition.name, definition.unit):
            raise ValueError(f"USDA nutrient definition differs for {definition.usda_nutrient_id}")

    for food in reference.foods:
        fdc_id = str(food.source.fdc_id)
        row = foods.get(fdc_id)
        if row is None or (
            row["data_type"], row["description"], row["publication_date"], legacy.get(fdc_id)
        ) != (
            reference.source.data_type, food.source.description, food.source.publication_date.isoformat(),
            food.source.ndb_number,
        ):
            raise ValueError(f"USDA food provenance differs for {food.food_id}")
        for key, definition in reference.nutrient_definitions.items():
            nutrient = getattr(food.nutrients, key)
            source = entries.get((fdc_id, str(definition.usda_nutrient_id)))
            # A qualified value is withheld until its source footnote has been reviewed.
            expected = None if source is None or not source["amount"] or source["footnote"] else (
                Decimal(source["amount"]), int(source["id"]),
            )
            actual = None if nutrient is None else (nutrient.amount, nutrient.source_row_id)
            if actual != expected:
                raise ValueError(f"USDA nutrient value or row ID differs for {food.food_id}/{key}")
        for portion in food.portions:
            row = portions.get(str(portion.source_row_id))
            if row is None or row["footnote"] or row["portion_description"] or (
                row["fdc_id"], Decimal(row["amount"]), int(row["measure_unit_id"]),
                row["modifier"], Decimal(row["gram_weight"]),
            ) != (fdc_id, portion.amount, portion.measure_unit_id, portion.modifier, portion.edible_grams):
                raise ValueError(f"USDA portion value or applicability differs for {food.food_id}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    reference = load_nutrition_reference()
    verify_nutrition_source(reference, args.archive)
    print(f"Verified {len(reference.foods)} food-state records against USDA SR Legacy {reference.source.release}.")


if __name__ == "__main__":
    main()

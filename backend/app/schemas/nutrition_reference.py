import re
import unicodedata
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, model_validator

NUTRIENT_DEFINITIONS = {
    "energy_kcal": (1008, "Energy", "kcal"),
    "protein_g": (1003, "Protein", "g"),
    "carbohydrate_g": (1005, "Carbohydrate, by difference", "g"),
    "fat_g": (1004, "Total lipid (fat)", "g"),
}
ARCHIVE_URL = "https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip"
FDC_URL = "https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients"
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveId = Annotated[int, Field(strict=True, gt=0)]


def _require_number(value: object) -> object:
    if type(value) not in (int, float, Decimal):
        raise ValueError("nutrient amount must be a JSON number")
    return value


Amount = Annotated[Decimal, BeforeValidator(_require_number), Field(ge=0, allow_inf_nan=False)]
PositiveAmount = Annotated[Decimal, BeforeValidator(_require_number), Field(gt=0, allow_inf_nan=False)]


def normalize_food_label(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


class ReferenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class UsdaRelease(ReferenceRecord):
    provider: Literal["USDA FoodData Central"]
    data_type: Literal["sr_legacy_food"]
    release: Literal["2018-04"]
    archive_url: Literal[ARCHIVE_URL]
    archive_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    retrieved_on: date
    license: Literal["CC0-1.0"]
    license_url: Literal["https://fdc.nal.usda.gov/"]


class UsdaFoodSource(ReferenceRecord):
    fdc_id: PositiveId
    ndb_number: Annotated[str, StringConstraints(pattern=r"^[0-9]{1,5}$")]
    publication_date: date
    description: Text
    url: Text

    @model_validator(mode="after")
    def validate_record_link(self):
        if self.url != FDC_URL.format(fdc_id=self.fdc_id):
            raise ValueError("food record URL must match its FDC ID")
        return self


class NutrientDefinition(ReferenceRecord):
    usda_nutrient_id: PositiveId
    name: Text
    unit: Literal["kcal", "g"]


class NutrientValue(ReferenceRecord):
    amount: Amount
    source_row_id: PositiveId


class NutrientsPer100g(ReferenceRecord):
    energy_kcal: NutrientValue | None
    protein_g: NutrientValue | None
    carbohydrate_g: NutrientValue | None
    fat_g: NutrientValue | None

    @model_validator(mode="after")
    def validate_mass(self):
        for nutrient in (self.protein_g, self.carbohydrate_g, self.fat_g):
            if nutrient is not None and nutrient.amount > 100:
                raise ValueError("a macronutrient cannot exceed 100 g per 100 g")
        return self


class FoodNames(ReferenceRecord):
    zh_cn: Text
    en_us: Text


class UsdaPortion(ReferenceRecord):
    source_row_id: PositiveId
    amount: PositiveAmount
    measure_unit_id: PositiveId
    modifier: Text
    edible_grams: PositiveAmount
    applicability: Text


class NutritionFood(ReferenceRecord):
    food_id: Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")]
    names: FoodNames
    aliases: tuple[Text, ...]
    category: Literal["grains", "noodles", "eggs", "poultry", "soy", "vegetables", "tubers", "fruit", "oil"]
    state: Literal["raw", "cooked", "dry", "as_sold"]
    preparation: Text
    source: UsdaFoodSource
    nutrients: NutrientsPer100g
    limitations: tuple[Text, ...]
    portions: tuple[UsdaPortion, ...] = ()

    @model_validator(mode="after")
    def validate_state(self):
        description = self.source.description.casefold()
        states = {
            "raw": r"\braw\b", "cooked": r"\b(?:cooked|boiled|roasted|stewed|baked|poached)\b",
            "dry": r"\bdry\b",
        }
        declared_states = {state for state, pattern in states.items() if re.search(pattern, description)}
        if declared_states and self.state not in declared_states:
            raise ValueError("food state conflicts with the USDA record description")
        for label in (self.names.zh_cn, self.names.en_us, *self.aliases):
            normalized = normalize_food_label(label)
            if self.state == "cooked" and (
                re.search(r"\b(?:raw|uncooked|dry)\b", normalized)
                or normalized.startswith("生") or "(生" in normalized
            ):
                raise ValueError("raw or dry label cannot resolve to a cooked food")
            if self.state in ("raw", "dry") and (
                re.search(states["cooked"], normalized)
                or normalized.startswith("熟") or "(熟" in normalized
            ):
                raise ValueError("cooked label cannot resolve to a raw or dry food")
        return self


class NutritionReference(ReferenceRecord):
    schema_version: Literal[1]
    reference_version: Annotated[str, StringConstraints(pattern=r"^usda-sr-legacy-v[1-9][0-9]*$")]
    source: UsdaRelease
    basis: Literal["per_100g_edible"]
    nutrient_definitions: dict[str, NutrientDefinition]
    unresolved_labels: tuple[Text, ...]
    foods: Annotated[tuple[NutritionFood, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_integrity(self):
        definitions = {
            key: (value.usda_nutrient_id, value.name, value.unit)
            for key, value in self.nutrient_definitions.items()
        }
        if definitions != NUTRIENT_DEFINITIONS:
            raise ValueError("nutrient definitions must match USDA IDs, names, and units")

        labels = {normalize_food_label(label) for label in self.unresolved_labels}
        if len(labels) != len(self.unresolved_labels):
            raise ValueError("duplicate unresolved food label")
        food_ids, fdc_ids, source_rows, portion_rows = set(), set(), set(), set()
        for food in self.foods:
            if food.food_id in food_ids or food.source.fdc_id in fdc_ids:
                raise ValueError(f"Duplicate food or source ID for {food.food_id}")
            food_ids.add(food.food_id)
            fdc_ids.add(food.source.fdc_id)
            for label in (food.names.zh_cn, food.names.en_us, *food.aliases):
                key = normalize_food_label(label)
                if key in labels:
                    raise ValueError(f"Duplicate or unresolved food label: {label}")
                labels.add(key)
            for key in definitions:
                entry = getattr(food.nutrients, key)
                if entry is not None:
                    if entry.source_row_id in source_rows:
                        raise ValueError(f"Duplicate USDA nutrient row ID: {entry.source_row_id}")
                    source_rows.add(entry.source_row_id)
            for portion in food.portions:
                if portion.source_row_id in portion_rows:
                    raise ValueError(f"Duplicate USDA portion row ID: {portion.source_row_id}")
                portion_rows.add(portion.source_row_id)
        return self

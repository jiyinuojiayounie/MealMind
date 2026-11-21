from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.meal_plans import MealType

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
RecipeId = Annotated[str, StringConstraints(pattern=r"^recipe_[0-9]{6}$")]
FamilyId = Annotated[str, StringConstraints(pattern=r"^family_[0-9]{6}$")]
IngredientId = Annotated[str, StringConstraints(pattern=r"^ingredient_[a-z0-9]+(?:_[a-z0-9]+)*$")]
Tag = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")]
Quantity = Annotated[float, Field(gt=0, allow_inf_nan=False)]
Unit = Literal["g", "ml", "piece"]
State = Literal["raw", "cooked", "dry", "ready_to_use"]
DishRole = Literal["protein", "staple", "vegetable", "accompaniment"]
ReviewStatus = Literal["draft", "reviewed", "retired"]


class CatalogRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class LocalizedText(CatalogRecord):
    zh_cn: Text = Field(alias="zh-CN")
    en_us: Text = Field(alias="en-US")


class LocalizedSteps(CatalogRecord):
    zh_cn: tuple[Text, ...] = Field(alias="zh-CN", min_length=1)
    en_us: tuple[Text, ...] = Field(alias="en-US", min_length=1)


class ReviewEvidence(CatalogRecord):
    reference: Text
    reviewer: Text
    reviewed_on: date


class AllergenAssessment(CatalogRecord):
    status: Literal["contains", "no_known_source_in_reviewed_recipe", "unknown", "unverified"]
    evidence: ReviewEvidence | None = None

    @model_validator(mode="after")
    def require_evidence_for_reviewed_absence(self):
        if self.status == "no_known_source_in_reviewed_recipe" and self.evidence is None:
            raise ValueError("reviewed allergen absence requires evidence")
        return self


class DietaryAssessment(CatalogRecord):
    status: Literal["verified", "unverified", "unknown"]
    evidence: ReviewEvidence | None = None

    @model_validator(mode="after")
    def require_evidence_for_verified_tag(self):
        if self.status == "verified" and self.evidence is None:
            raise ValueError("verified dietary tags require evidence")
        return self


class CanonicalIngredient(CatalogRecord):
    ingredient_id: IngredientId
    names: LocalizedText
    allergens: dict[Tag, AllergenAssessment] = Field(default_factory=dict)


class HouseholdPortion(CatalogRecord):
    label: LocalizedText
    size_basis: Text
    confidence: Literal["verified"]
    evidence: ReviewEvidence


class RecipeIngredient(CatalogRecord):
    ingredient_id: IngredientId
    quantity: Quantity
    unit: Unit
    state: State
    primary: bool = False
    required_starting_state: bool = False
    household_portion: HouseholdPortion | None = None


class ProcessWater(CatalogRecord):
    purpose: Literal["steam", "boil", "rinse"]
    quantity_ml: Quantity | None = None


class RecipeTimes(CatalogRecord):
    preparation_minutes: Annotated[int, Field(ge=0)]
    cooking_minutes: Annotated[int, Field(ge=0)]
    waiting_minutes: Annotated[int, Field(ge=0)] = 0
    total_minutes: Annotated[int, Field(gt=0)]
    starting_assumptions: LocalizedText | None = None

    @model_validator(mode="after")
    def validate_sequential_total(self):
        if self.total_minutes < self.preparation_minutes + self.cooking_minutes + self.waiting_minutes:
            raise ValueError("total_minutes must cover preparation, cooking, and waiting")
        return self


class RecipeProvenance(CatalogRecord):
    source_kind: Literal["original_development_draft", "original_reviewed", "licensed_external"]
    source_reference: Text | None = None
    attribution: Text | None = None
    license_or_permission: Text | None = None
    notes: Text


class RecipeReview(CatalogRecord):
    status: ReviewStatus
    evidence: ReviewEvidence | None = None


class FlavorProfile(CatalogRecord):
    heat: Literal["spicy", "non_spicy", "unknown"]
    characteristics: tuple[Literal["mild", "savory", "sweet", "sour"], ...] = ()
    status: Literal["provisional", "verified"]
    basis: Text
    evidence: ReviewEvidence | None = None

    @model_validator(mode="after")
    def require_heat_review_evidence(self):
        if self.status == "verified" and (self.heat == "unknown" or self.evidence is None):
            raise ValueError("verified flavor requires a known heat level and review evidence")
        return self

    @property
    def has_verified_heat(self) -> bool:
        return self.status == "verified" and self.heat != "unknown" and self.evidence is not None


class CatalogRecipe(CatalogRecord):
    recipe_id: RecipeId
    dish_family_id: FamilyId
    revision: Annotated[int, Field(ge=1)]
    names: LocalizedText
    meal_types: tuple[MealType, ...] = Field(min_length=1)
    dish_roles: tuple[DishRole, ...] = Field(min_length=1)
    cuisine: Tag
    cooking_methods: tuple[Tag, ...] = Field(min_length=1)
    flavor: FlavorProfile | None = None
    ingredients: tuple[RecipeIngredient, ...] = Field(min_length=1)
    process_water: ProcessWater | None = None
    verification_notes: tuple[Text, ...] = ()
    steps: LocalizedSteps
    servings: Annotated[int, Field(ge=1)]
    serving_description: LocalizedText | None = None
    times: RecipeTimes
    dietary: dict[Tag, DietaryAssessment] = Field(default_factory=dict)
    allergens: dict[Tag, AllergenAssessment] = Field(default_factory=dict)
    provenance: RecipeProvenance
    review: RecipeReview

    @model_validator(mode="after")
    def validate_review(self):
        if self.review.status == "reviewed":
            if self.provenance.source_kind == "original_development_draft":
                raise ValueError("development draft provenance cannot be published as reviewed")
            if not (
                self.review.evidence
                and self.provenance.source_reference
                and self.provenance.attribution
                and self.provenance.license_or_permission
            ):
                raise ValueError("reviewed recipes require review evidence, source, attribution, and reuse permission")
        return self


class RecipeCatalog(CatalogRecord):
    schema_version: Literal[1]
    catalog_version: Annotated[int, Field(ge=1)]
    ingredients: tuple[CanonicalIngredient, ...] = Field(min_length=1)
    recipes: tuple[CatalogRecipe, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self):
        ingredient_ids: set[str] = set()
        recipe_ids: set[str] = set()
        issues: list[str] = []
        for ingredient in self.ingredients:
            if ingredient.ingredient_id in ingredient_ids:
                issues.append(f"duplicate ingredient ID {ingredient.ingredient_id}")
            ingredient_ids.add(ingredient.ingredient_id)

        for recipe in self.recipes:
            if recipe.recipe_id in recipe_ids:
                issues.append(f"duplicate recipe ID {recipe.recipe_id}")
            recipe_ids.add(recipe.recipe_id)
            for item in recipe.ingredients:
                if item.ingredient_id not in ingredient_ids:
                    issues.append(f"{recipe.recipe_id} references unknown ingredient {item.ingredient_id}")

        if issues:
            raise ValueError(". ".join(issues))
        return self

from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from app.schemas.recipe_catalog import AllergenAssessment, CatalogRecipe, RecipeCatalog

DEVELOPMENT_CATALOG_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "recipe_catalog" / "catalog-v4.json"
)


class CatalogLoadError(ValueError):
    """A catalog file is unreadable or does not satisfy its schema."""


def load_recipe_catalog(path: Path) -> RecipeCatalog:
    try:
        return RecipeCatalog.model_validate_json(path.read_bytes())
    except OSError as exc:
        raise CatalogLoadError(f"Cannot read recipe catalog {path}: {exc.strerror}") from exc
    except ValidationError as exc:
        raise CatalogLoadError(f"Invalid recipe catalog {path}: {exc}") from exc


def _has_reviewed_absence(assessment: AllergenAssessment | None) -> bool:
    return (
        assessment is not None
        and assessment.status == "no_known_source_in_reviewed_recipe"
        and assessment.evidence is not None
    )


def recipes_with_allergen_evidence(
    catalog: RecipeCatalog,
    recipes: Iterable[CatalogRecipe],
    excluded_allergens: Iterable[str],
) -> tuple[CatalogRecipe, ...]:
    """Require recipe and ingredient evidence for every requested allergen exclusion.

    Missing, unresolved, or unverified evidence fails closed for that exclusion.
    Eligibility alone does not address cross-contact or product-specific labels.
    """
    exclusions = tuple(excluded_allergens)
    ingredients = {item.ingredient_id: item for item in catalog.ingredients}
    return tuple(
        recipe
        for recipe in recipes
        if all(
            _has_reviewed_absence(recipe.allergens.get(allergen))
            and all(
                _has_reviewed_absence(ingredients[item.ingredient_id].allergens.get(allergen))
                for item in recipe.ingredients
            )
            for allergen in exclusions
        )
    )


def production_recipes(
    catalog: RecipeCatalog, *, excluded_allergens: Iterable[str] = (),
) -> tuple[CatalogRecipe, ...]:
    reviewed = (recipe for recipe in catalog.recipes if recipe.review.status == "reviewed")
    return recipes_with_allergen_evidence(catalog, reviewed, excluded_allergens)

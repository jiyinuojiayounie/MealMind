from pathlib import Path

from app.schemas.nutrition_reference import NutritionReference

REFERENCE_PATH = Path(__file__).resolve().parents[3] / "data" / "nutrition" / "reference-v1.json"


def load_nutrition_reference(path: Path = REFERENCE_PATH) -> NutritionReference:
    return NutritionReference.model_validate_json(path.read_bytes())

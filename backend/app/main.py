from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.food_logs import food_log_error, router as food_logs_router
from app.api.food_recognition import router as food_recognition_router
from app.api.health import router as health_router
from app.api.meal_plans import router as meal_plans_router
from app.api.nutrition import router as nutrition_router
from app.api.replan import router as replan_router
from app.core.settings import Settings
from app.storage.food_logs import FoodLogConflict, FoodLogNotFound, FoodLogStorageUnavailable


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings()
    app = FastAPI(title="MealMind API", version="0.1.0")
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
        allow_methods=["GET", "POST", "PUT", "DELETE"] if settings.environment == "development" else ["GET", "POST"],
    )
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(meal_plans_router, prefix="/api/v1")
    if settings.environment == "development":
        app.include_router(food_recognition_router, prefix="/api/v1")
        app.include_router(food_logs_router, prefix="/api/v1")
        app.include_router(nutrition_router, prefix="/api/v1")
        app.include_router(replan_router, prefix="/api/v1")
        for error in (FoodLogConflict, FoodLogNotFound, FoodLogStorageUnavailable):
            app.add_exception_handler(error, food_log_error)
    return app


app = create_app()

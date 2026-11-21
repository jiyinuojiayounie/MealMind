from collections.abc import AsyncIterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from python_multipart.exceptions import FormParserError
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from app.api.food_logs import local_food_log_settings
from app.core.settings import Settings
from app.schemas.food_recognition import FoodRecognitionRequest, FoodRecognitionResponse, ImageFoodRecognitionResponse
from app.services.food_images import ImageUploadError, MAX_IMAGE_BYTES, MAX_REQUEST_BYTES
from app.services.food_recognition import recognize_food_image, recognize_food_text
from app.services.meal_plans import PlannerFailure, PlannerTimeout, PlannerUnavailable

router = APIRouter(prefix="/food-logs", tags=["food recognition"])
LocalSettings = Annotated[Settings, Depends(local_food_log_settings)]


@contextmanager
def recognition_errors():
    try:
        yield
    except PlannerUnavailable:
        raise HTTPException(503, "Food recognition is currently unavailable.") from None
    except PlannerTimeout:
        raise HTTPException(504, "Food recognition timed out. Try again later.") from None
    except PlannerFailure:
        raise HTTPException(502, "Food recognition could not produce a valid proposal.") from None


@router.post("/recognize-text")
def recognize_text(payload: FoodRecognitionRequest, settings: LocalSettings) -> FoodRecognitionResponse:
    with recognition_errors():
        return recognize_food_text(payload, settings)


class ImageMultipartParser(MultiPartParser):
    spool_max_size = MAX_REQUEST_BYTES
    completed = False

    def on_end(self) -> None:
        self.completed = True


async def bounded_upload(request: Request) -> AsyncIterator[bytes]:
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_REQUEST_BYTES:
            raise HTTPException(413, "The multipart upload exceeds the allowed size.")
        yield chunk


@router.post("/recognize-image", openapi_extra={
    "requestBody": {
        "required": True,
        "content": {"multipart/form-data": {"schema": {
            "type": "object", "required": ["image"],
            "properties": {"image": {"type": "string", "format": "binary"}},
        }}},
    },
})
async def recognize_image(request: Request, settings: LocalSettings) -> ImageFoodRecognitionResponse:
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "multipart/form-data":
        raise HTTPException(415, "Send the image as multipart/form-data.")

    parser = ImageMultipartParser(request.headers, bounded_upload(request), max_files=1, max_fields=0)
    try:
        form = await parser.parse()
    except (MultiPartException, FormParserError):
        raise HTTPException(400, "Upload exactly one file using the image field.") from None
    try:
        image = form.get("image")
        if not parser.completed or not isinstance(image, UploadFile):
            raise HTTPException(400, "Upload exactly one file using the image field.")
        data = await image.read(MAX_IMAGE_BYTES + 1)
    finally:
        await form.close()

    with recognition_errors():
        try:
            return await run_in_threadpool(recognize_food_image, data, settings)
        except ImageUploadError as error:
            raise HTTPException(error.status_code, error.detail) from None

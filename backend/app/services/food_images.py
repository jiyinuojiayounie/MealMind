import warnings
from io import BytesIO
from struct import error as StructError

from PIL import Image, ImageOps

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_IMAGE_BYTES + 64 * 1024  # Includes multipart headers and boundaries.
MAX_IMAGE_SIDE = 8192
MAX_IMAGE_PIXELS = 24_000_000
NORMALIZED_SIDE = 1600


class ImageUploadError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _image_format(data: bytes) -> str:
    if data.startswith(b"\xff\xd8"):
        return "JPEG"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "WEBP"
    raise ImageUploadError(415, "Upload a JPEG, PNG, or WebP image.")


def _check_dimensions(width: int, height: int) -> None:
    if max(width, height) > MAX_IMAGE_SIDE or width * height > MAX_IMAGE_PIXELS:
        raise ImageUploadError(413, "Image dimensions exceed the supported limit.")


def _check_webp_canvas(data: bytes) -> None:
    # The WebP decoder can allocate the canvas during Image.open. Check the
    # canvas dimensions in the first RIFF chunk before giving it the bytes.
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
    elif chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        dimensions = int.from_bytes(data[21:25], "little")
        width = (dimensions & 0x3FFF) + 1
        height = ((dimensions >> 14) & 0x3FFF) + 1
    elif chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
    else:
        raise ImageUploadError(400, "The image is corrupt or incomplete.")
    _check_dimensions(width, height)


def normalize_image(data: bytes) -> bytes:
    if not data:
        raise ImageUploadError(400, "The image upload is empty.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageUploadError(413, "The image exceeds the 5 MiB limit.")

    image_format = _image_format(data)
    if image_format == "WEBP":
        _check_webp_canvas(data)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data), formats=[image_format]) as image:
                _check_dimensions(*image.size)
                if getattr(image, "is_animated", False):
                    raise ImageUploadError(415, "Upload a single still image.")
                image.verify()

            with Image.open(BytesIO(data), formats=[image_format]) as image:
                image.load()
                with ImageOps.exif_transpose(image) as oriented:
                    oriented.thumbnail((NORMALIZED_SIDE, NORMALIZED_SIDE))
                    with Image.new("RGB", oriented.size, "white") as clean:
                        if "A" in oriented.getbands() or "transparency" in oriented.info:
                            with oriented.convert("RGBA") as rgba:
                                clean.paste(rgba, mask=rgba.getchannel("A"))
                        else:
                            clean.paste(oriented)
                        with BytesIO() as output:
                            clean.save(output, format="JPEG", quality=85)
                            return output.getvalue()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ImageUploadError(413, "Image dimensions exceed the supported limit.") from None
    except (OSError, ValueError, SyntaxError, OverflowError, EOFError, StructError):
        raise ImageUploadError(400, "The image is corrupt or incomplete.") from None

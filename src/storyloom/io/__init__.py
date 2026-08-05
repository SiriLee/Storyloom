"""I/O layer — API clients for LLM and image generation."""

from storyloom.io.api_client import ApiClient, ApiError, ApiResult
from storyloom.io.img_api_client import (
    ImageApiError,
    ImageModelPreset,
    ImageResult,
    ImageSize,
    ImgApiClient,
    MODEL_PRESETS,
    RemoveBgPolicy,
)
from storyloom.io.img_utils import (
    _check_rembg,
    detect_alpha,
    detect_format,
    get_dimensions,
    install_rembg,
    maybe_remove_background,
    remove_background,
)

__all__ = [
    "ApiClient",
    "ApiError",
    "ApiResult",
    "ImageApiError",
    "ImageModelPreset",
    "ImageResult",
    "ImageSize",
    "ImgApiClient",
    "MODEL_PRESETS",
    "RemoveBgPolicy",
    "_check_rembg",
    "detect_alpha",
    "detect_format",
    "get_dimensions",
    "install_rembg",
    "maybe_remove_background",
    "remove_background",
]

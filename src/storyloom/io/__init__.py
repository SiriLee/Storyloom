"""I/O layer — API clients for LLM and image generation."""

from storyloom.io._types import ImageResult, ImageSize, RemoveBgPolicy
from storyloom.io.api_client import ApiClient, ApiError, ApiResult
from storyloom.io.img_api_client import (
    ImageApiError,
    ImageModelPreset,
    ImgApiClient,
    MODEL_PRESETS,
)
from storyloom.io.img_utils import (
    check_model,
    detect_alpha,
    detect_format,
    get_dimensions,
    maybe_remove_background,
    remove_background,
)
from storyloom.io.thinking import get_thinking_params

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
    "check_model",
    "detect_alpha",
    "detect_format",
    "get_dimensions",
    "get_thinking_params",
    "maybe_remove_background",
    "remove_background",
]

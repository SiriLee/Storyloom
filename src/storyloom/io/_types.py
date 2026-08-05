"""Shared data types for the image I/O pipeline.

These types are pure data (dataclasses, enums) with zero internal
dependencies.  Both ``img_api_client`` (the API-calling layer) and
``img_utils`` (the local image-processing layer) import from this
module, forming a clean dependency DAG::

          _types.py
         /         \\
  img_utils.py   img_api_client.py

No module ever imports another across the dividing line at module level,
so the cycle is structurally impossible.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RemoveBgPolicy(Enum):
    """Background removal policy for image generation."""
    AUTO = "auto"        # Remove bg only if image has no alpha channel
    ALWAYS = "always"    # Force removal regardless of alpha
    NEVER = "never"      # Skip removal entirely


class ImageSize(Enum):
    """Image size presets for different asset types."""
    PORTRAIT = "portrait"        # Character portrait — square
    BACKGROUND = "background"    # Scene background — 16:9


@dataclass
class ImageResult:
    """Result from ImgApiClient.generate().

    Attributes:
        bytes: Raw image data.
        format: Detected format — "png", "webp", or "jpeg".
        has_alpha: True if the image has an alpha channel (RGBA / VP8X-alpha).
        width: Image width in pixels (0 if unknown).
        height: Image height in pixels (0 if unknown).
        url: Original response URL (may expire).
        elapsed_ms: Generation wall-clock time in milliseconds.
    """
    bytes: bytes
    format: str
    has_alpha: bool
    width: int
    height: int
    url: str
    elapsed_ms: float

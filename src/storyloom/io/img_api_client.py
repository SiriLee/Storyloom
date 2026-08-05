"""Image generation API client — OpenAI-compatible /images/generations endpoint.

Mirrors the pattern of api_client.py: reads config from UserConfig with
os.environ override. Supports multiple models via presets with per-model
default sizes.

Usage::

    client = ImgApiClient(user_config)
    result = client.generate("anime warrior", ImageSize.PORTRAIT)
    print(f"{result.format} {result.width}x{result.height} alpha={result.has_alpha}")
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal

import httpx

from storyloom.config import DEFAULT_IMG_BASE_URL, DEFAULT_IMG_MODEL


# ═══════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════

class ImageApiError(Exception):
    """Raised on image API call failures (HTTP, network, or response errors).

    Unlike ApiError (which is fatal for text generation), image errors
    should be caught and silently degraded (placeholder image, skip bg
    removal, etc.).
    """
    pass


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
class ImageModelPreset:
    """Per-model configuration: default sizes, capabilities, extra API params.

    Attributes:
        label: Human-readable model name for logging / UI display.
        default_sizes: Dict mapping ImageSize.value → size string
            (e.g. ``{"portrait": "1024x1024", "background": "1280x720"}``).
        supports_reference: Whether the model supports image_urls for
            character consistency (reference image input).
        extra_body: Extra top-level JSON fields merged into the request
            body (e.g. provider-specific parameters).
    """
    label: str
    default_sizes: dict[str, str] = field(default_factory=dict)
    supports_reference: bool = True
    extra_body: dict = field(default_factory=dict)


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


# ═══════════════════════════════════════════════════════════════════
# Model presets
# ═══════════════════════════════════════════════════════════════════

MODEL_PRESETS: dict[str, ImageModelPreset] = {
    "flux-2-pro": ImageModelPreset(
        label="FLUX.2 Pro",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "seedream-5-0-260128": ImageModelPreset(
        label="Seedream 5.0 Lite",
        default_sizes={
            "portrait": "2048x2048",
            "background": "2560x1440",
        },
        supports_reference=True,
    ),
    "gemini-3.1-flash-lite-image": ImageModelPreset(
        label="Nano Banana Lite",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1024x1024",
        },
        supports_reference=True,
    ),
}

# Fallback sizes for unknown models
_DEFAULT_PORTRAIT_SIZE = "1024x1024"
_DEFAULT_BACKGROUND_SIZE = "1280x720"


# ═══════════════════════════════════════════════════════════════════
# ImgApiClient
# ═══════════════════════════════════════════════════════════════════

class ImgApiClient:
    """OpenAI-compatible image generation API client.

    Reads configuration from UserConfig, with os.environ as override.
    Uses httpx.Client for HTTP communication.

    Config values are read lazily from the UserConfig object on each
    property access so that runtime config changes take effect without
    restarting.

    Key fallback: if ``IMG_API_KEY`` / ``img_api_key`` is empty,
    falls back to ``LLM_API_KEY`` / ``api_key``.
    """

    def __init__(self, config: "UserConfig | None" = None):
        from storyloom.user_config import UserConfig
        self._cfg = config if config is not None else UserConfig()
        self._client: httpx.Client | None = None

    # ── lazy config accessors ───────────────────────────────────────

    @property
    def api_key(self) -> str:
        """Resolved image API key.

        Priority: IMAGE_API_KEY env → img_api_key config → LLM_API_KEY
        env → api_key config.
        """
        key = os.environ.get("IMAGE_API_KEY")
        if key:
            return key
        key = self._cfg.img_api_key
        if key:
            return key
        # Fall back to LLM key
        return os.environ.get("LLM_API_KEY") or self._cfg.api_key

    @property
    def base_url(self) -> str:
        """Resolved base URL (without trailing slash)."""
        url = os.environ.get("IMAGE_BASE_URL")
        if url:
            return url.rstrip("/")
        url = self._cfg.img_api_base_url
        if url:
            return url.rstrip("/")
        return DEFAULT_IMG_BASE_URL.rstrip("/")

    @property
    def model(self) -> str:
        """Resolved model name."""
        return os.environ.get("IMAGE_MODEL") or self._cfg.img_api_model or DEFAULT_IMG_MODEL

    @property
    def remove_bg_policy(self) -> RemoveBgPolicy:
        """Resolved background removal policy."""
        raw = (
            os.environ.get("IMAGE_REMOVE_BG")
            or self._cfg.img_remove_bg
            or "auto"
        )
        try:
            return RemoveBgPolicy(raw)
        except ValueError:
            return RemoveBgPolicy.AUTO

    # ── HTTP client ──────────────────────────────────────────────────

    def _get_client(self) -> httpx.Client:
        """Return the shared httpx.Client, creating it on first use."""
        if self._client is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(
                    None,  # no read timeout — image gen is slow
                    connect=30.0,
                ),
                follow_redirects=True,
            )
        return self._client

    # ── size resolution ─────────────────────────────────────────────

    def _resolve_size(self, image_size: ImageSize) -> str:
        """Resolve an ImageSize enum to a pixel-size string for the current model.

        Uses the model preset if available; falls back to generic defaults.
        """
        preset = MODEL_PRESETS.get(self.model)
        if preset and image_size.value in preset.default_sizes:
            return preset.default_sizes[image_size.value]
        # Generic fallbacks
        if image_size == ImageSize.PORTRAIT:
            return _DEFAULT_PORTRAIT_SIZE
        return _DEFAULT_BACKGROUND_SIZE

    # ── public API ────────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        size: ImageSize,
        image_urls: list[str] | None = None,
        remove_bg: RemoveBgPolicy | None = None,
    ) -> ImageResult:
        """Generate one image via the API.

        Args:
            prompt: Text description of the desired image.
            size: Image type (PORTRAIT or BACKGROUND) — actual pixel
                dimensions are resolved from the model preset.
            image_urls: Optional list of reference image URLs for
                character consistency. Only supported by some models.
            remove_bg: Per-call background removal policy override.
                None → use the instance default.

        Returns:
            ImageResult with raw bytes, format, alpha, dimensions,
            and timing metadata.

        Raises:
            ValueError: If no API key is configured.
            ImageApiError: On HTTP, network, or response errors.
        """
        if not self.api_key:
            raise ValueError(
                "Image API key not configured. Set IMAGE_API_KEY "
                "environment variable or img_api_key in app settings."
            )

        size_str = self._resolve_size(size)
        policy = remove_bg if remove_bg is not None else self.remove_bg_policy

        # Build payload
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "size": size_str,
            "output_format": "png",
            "watermark": False,
        }
        if image_urls:
            payload["image_urls"] = image_urls

        # Merge model-specific extra params
        preset = MODEL_PRESETS.get(self.model)
        if preset and preset.extra_body:
            payload.update(preset.extra_body)

        # ── API call ──────────────────────────────────────────────
        t0 = time.perf_counter()
        try:
            resp = self._get_client().post(
                f"{self.base_url}/images/generations",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json=payload,
            )
        except httpx.RequestError as e:
            raise ImageApiError(f"Connection error: {e}") from e

        # ── Handle HTTP errors ────────────────────────────────────
        if resp.status_code != 200:
            self._handle_http_error(resp)

        data = resp.json()
        img = data.get("data", [{}])[0]
        url = img.get("url", "")
        b64 = img.get("b64_json", "")

        # ── Download / decode image ───────────────────────────────
        raw: bytes | None = None
        if url:
            try:
                dl = self._get_client().get(url)
            except httpx.RequestError as e:
                raise ImageApiError(f"Image download failed: {e}") from e
            if dl.status_code != 200:
                raise ImageApiError(
                    f"Image download failed: HTTP {dl.status_code}"
                )
            raw = dl.content
        elif b64:
            raw = base64.b64decode(b64)

        if not raw:
            raise ImageApiError(
                "API response contained neither 'url' nor 'b64_json'"
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000

        # ── Inspect image metadata ────────────────────────────────
        from storyloom.io.img_utils import (
            detect_format, detect_alpha, get_dimensions,
        )
        fmt = detect_format(raw)
        has_alpha = detect_alpha(raw, fmt)
        w, h = get_dimensions(raw, fmt)

        result = ImageResult(
            bytes=raw,
            format=fmt,
            has_alpha=has_alpha,
            width=w,
            height=h,
            url=url,
            elapsed_ms=elapsed_ms,
        )

        # ── Background removal ────────────────────────────────────
        if policy != RemoveBgPolicy.NEVER:
            from storyloom.io.img_utils import _check_rembg
            if not _check_rembg():
                # Degrade: skip removal (one-time log would be ideal,
                # but for now just silently skip)
                return result

        from storyloom.io.img_utils import maybe_remove_background
        return maybe_remove_background(result, policy)

    # ── error handling ────────────────────────────────────────────────

    @staticmethod
    def _handle_http_error(response: httpx.Response) -> None:
        """Convert HTTP error response to ImageApiError."""
        import json
        try:
            detail = response.json()
            msg = detail.get("error", {}).get(
                "message", str(response.status_code)
            )
        except Exception:
            snippet = response.text[:500] if response.text else "(empty body)"
            msg = f"Non-JSON response: {snippet}"
        raise ImageApiError(f"HTTP {response.status_code}: {msg}")

    # ── lifecycle ────────────────────────────────────────────────────

    @property
    def config_summary(self) -> str:
        """Human-readable config summary for logging / debugging."""
        return (
            f"Model:       {self.model}\n"
            f"Base URL:    {self.base_url}\n"
            f"Remove bg:   {self.remove_bg_policy.value}\n"
            f"API key:     {'configured' if self.api_key else 'MISSING'}"
        )

    def close(self) -> None:
        """Close the underlying HTTP client connection pool."""
        if self._client is not None:
            self._client.close()
            self._client = None

    def __del__(self) -> None:
        self.close()

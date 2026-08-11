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
import json
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

import httpx

from storyloom.config import (
    DEFAULT_IMG_BASE_URL,
    DEFAULT_IMG_MODEL,
    IMAGE_DOWNLOAD_TIMEOUT_SEC,
    IMAGE_GEN_TIMEOUT_SEC,
)
from storyloom.io._types import ImageResult, ImageSize, RemoveBgPolicy


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


# ═══════════════════════════════════════════════════════════════════
# Model presets
# ═══════════════════════════════════════════════════════════════════

# Treat this dict as read-only. Runtime mutation of preset fields
# (default_sizes, extra_body) would affect all concurrent requests.
# For dynamic model registration, create a new preset dict instead.
MODEL_PRESETS: dict[str, ImageModelPreset] = {
    # ── Seedream family (high-quality anime, excellent for visual novel) ─
    "seedream-5-0-pro-260628": ImageModelPreset(
        label="Seedream 5.0 Pro",
        default_sizes={
            "portrait": "2048x2048",
            "background": "2560x1440",
        },
        supports_reference=True,
    ),
    "seedream-5-0-260128": ImageModelPreset(
        label="Seedream 5.0",
        default_sizes={
            "portrait": "2048x2048",
            "background": "2560x1440",
        },
        supports_reference=True,
    ),
    "seedream-4-5-251128": ImageModelPreset(
        label="Seedream 4.5",
        default_sizes={
            "portrait": "2048x2048",
            "background": "2560x1440",
        },
        supports_reference=True,
    ),
    "seedream-4-0-250828": ImageModelPreset(
        label="Seedream 4.0",
        default_sizes={
            "portrait": "2048x2048",
            "background": "2560x1440",
        },
        supports_reference=True,
    ),

    # ── FLUX family ──────────────────────────────────────────────────
    "flux-2-max": ImageModelPreset(
        label="FLUX.2 Max",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "flux-2-pro": ImageModelPreset(
        label="FLUX.2 Pro",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "flux-2-flex": ImageModelPreset(
        label="FLUX.2 Flex",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "flux-2-klein-9b": ImageModelPreset(
        label="FLUX.2 Klein 9B",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "flux-2-klein-4b": ImageModelPreset(
        label="FLUX.2 Klein 4B",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "flux-kontext-max": ImageModelPreset(
        label="FLUX Kontext Max",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "flux-kontext-pro": ImageModelPreset(
        label="FLUX Kontext Pro",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "flux-dev": ImageModelPreset(
        label="FLUX Dev",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),

    # ── Gemini family ────────────────────────────────────────────────
    "gemini-3-pro-image-preview-4k": ImageModelPreset(
        label="Gemini 3 Pro Image 4K",
        default_sizes={
            "portrait": "2048x2048",
            "background": "3840x2160",
        },
        supports_reference=True,
    ),
    "gemini-3-pro-image-preview-2k": ImageModelPreset(
        label="Gemini 3 Pro Image 2K",
        default_sizes={
            "portrait": "2048x2048",
            "background": "2560x1440",
        },
        supports_reference=True,
    ),
    "gemini-3-pro-image-preview": ImageModelPreset(
        label="Gemini 3 Pro Image",
        default_sizes={
            "portrait": "2048x2048",
            "background": "2560x1440",
        },
        supports_reference=True,
    ),
    "gemini-3-pro-image-preview-1k": ImageModelPreset(
        label="Gemini 3 Pro Image 1K",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "gemini-3-pro-image": ImageModelPreset(
        label="Gemini 3 Pro Image (stable)",
        default_sizes={
            "portrait": "2048x2048",
            "background": "2560x1440",
        },
        supports_reference=True,
    ),
    "gemini-3.1-flash-image-preview-4k": ImageModelPreset(
        label="Gemini 3.1 Flash Image 4K",
        default_sizes={
            "portrait": "2048x2048",
            "background": "3840x2160",
        },
        supports_reference=True,
    ),
    "gemini-3.1-flash-image-4k": ImageModelPreset(
        label="Gemini 3.1 Flash Image 4K (stable)",
        default_sizes={
            "portrait": "2048x2048",
            "background": "3840x2160",
        },
        supports_reference=True,
    ),
    "gemini-3.1-flash-image-preview": ImageModelPreset(
        label="Gemini 3.1 Flash Image",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "gemini-3.1-flash-image": ImageModelPreset(
        label="Gemini 3.1 Flash Image (stable)",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "gemini-3.1-flash-lite-image": ImageModelPreset(
        label="Gemini 3.1 Flash Lite Image",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "gemini-2.5-flash-image": ImageModelPreset(
        label="Gemini 2.5 Flash Image",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "gemini-2.5-flash-image-preview": ImageModelPreset(
        label="Gemini 2.5 Flash Image (preview)",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),

    # ── Nano Banana family (budget, fast) ─────────────────────────────
    "nano-banana-pro": ImageModelPreset(
        label="Nano Banana Pro",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=False,
    ),
    "nano-banana-2": ImageModelPreset(
        label="Nano Banana 2",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=False,
    ),
    "nano-banana": ImageModelPreset(
        label="Nano Banana",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=False,
    ),

    # ── GPT Image family ─────────────────────────────────────────────
    "gpt-image-2-vip": ImageModelPreset(
        label="GPT Image 2 VIP",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "gpt-image-2-all": ImageModelPreset(
        label="GPT Image 2 All",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "gpt-image-2": ImageModelPreset(
        label="GPT Image 2",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "gpt-image-1.5": ImageModelPreset(
        label="GPT Image 1.5",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "gpt-image-1": ImageModelPreset(
        label="GPT Image 1",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "gpt-image-1-mini": ImageModelPreset(
        label="GPT Image 1 Mini",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
        },
        supports_reference=True,
    ),
    "chatgpt-image-latest": ImageModelPreset(
        label="ChatGPT Image Latest",
        default_sizes={
            "portrait": "1024x1024",
            "background": "1280x720",
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

    def __init__(self, config: "UserConfig | None" = None, *,
                 remove_bg: RemoveBgPolicy):
        """Initialize the image API client.

        Args:
            config: UserConfig instance (reads a fresh one if None).
            remove_bg: Background removal policy. **Required.**
                Callers are responsible for determining the correct policy:
                - CHAR_PORTRAIT → user-configured policy (portrait_remove_bg)
                - BACKGROUND     → RemoveBgPolicy.NEVER (hardcoded)
        """
        from storyloom.user_config import UserConfig
        self._cfg = config if config is not None else UserConfig()
        self._remove_bg = remove_bg
        # Thread-local httpx.Client: default transport is not thread-safe,
        # and Task Pool (7.4+) will call generate() from multiple threads.
        self._local = threading.local()

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
        """Background removal policy set at construction time.

        Unlike pre-7.8 behaviour, this no longer reads from UserConfig
        or the ``IMAGE_REMOVE_BG`` environment variable.  Callers are
        responsible for determining the correct policy per asset type
        and passing it explicitly to the constructor.
        """
        return self._remove_bg

    # ── HTTP client ──────────────────────────────────────────────────

    def _get_client(self) -> httpx.Client:
        """Return a per-thread httpx.Client (thread-safe for Task Pool).

        httpx default transport is NOT thread-safe. Each thread gets its
        own Client instance via threading.local().
        """
        if not hasattr(self._local, "client"):
            kwargs: dict = {
                "timeout": httpx.Timeout(
                    IMAGE_GEN_TIMEOUT_SEC,
                    connect=30.0,
                ),
                "follow_redirects": True,
            }
            proxy = self._cfg.proxy_url if self._cfg else ""
            if proxy:
                kwargs["proxy"] = proxy
            self._local.client = httpx.Client(**kwargs)
        return self._local.client

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

        # Always use light thinking for image generation.
        # Currently only Gemini 3.1 Flash/Flash Lite Image support
        # thinking control (via thinking_config.thinking_level).
        # For all other models (Seedream, FLUX, GPT Image, etc.),
        # get_image_thinking_params returns {} — a no-op.
        from storyloom.io.thinking import get_image_thinking_params
        thinking = get_image_thinking_params(self.model, "light")
        if thinking:
            payload.update(thinking)

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

        try:
            data = resp.json()
        except ValueError as e:
            raise ImageApiError(
                f"Invalid JSON in API response: {e}"
            ) from e
        img = data.get("data", [{}])[0]
        url = img.get("url", "")
        b64 = img.get("b64_json", "")

        # ── Download / decode image ───────────────────────────────
        raw: bytes | None = None
        if url:
            try:
                dl = self._get_client().get(
                    url, timeout=IMAGE_DOWNLOAD_TIMEOUT_SEC,
                )
            except httpx.RequestError as e:
                raise ImageApiError(f"Image download failed: {e}") from e
            if dl.status_code != 200:
                raise ImageApiError(
                    f"Image download failed: HTTP {dl.status_code}"
                )
            raw = dl.content
        elif b64:
            try:
                raw = base64.b64decode(b64)
            except Exception as e:
                # base64.b64decode raises binascii.Error (Exception subclass,
                # not ValueError) for corrupt data. Convert to ImageApiError
                # so callers have a uniform exception type.
                raise ImageApiError(
                    f"Invalid base64 image data: {e}"
                ) from e

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
        # maybe_remove_background degrades gracefully when model is
        # unavailable (returns the original image unchanged).
        from storyloom.io.img_utils import maybe_remove_background
        result = maybe_remove_background(result, policy)

        # NOTE: Image bytes are returned in memory. The caller
        # (Task.process, 7.4+) is responsible for saving to
        # media/{type}/{id}.{ext} and registering with AssetLibrary.
        return result

    # ── error handling ────────────────────────────────────────────────

    @staticmethod
    def _handle_http_error(response: httpx.Response) -> None:
        """Convert HTTP error response to ImageApiError."""
        try:
            detail = response.json()
            msg = detail.get("error", {}).get(
                "message", str(response.status_code)
            )
        except (ValueError, KeyError, TypeError):
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
        """Close this thread's HTTP client connection pool.

        Note: only closes the current thread's client. Other threads'
        clients remain active until their threads exit.
        """
        if hasattr(self._local, "client"):
            self._local.client.close()
            del self._local.client

    def __del__(self) -> None:
        if hasattr(self, "_local") and hasattr(self._local, "client"):
            try:
                self._local.client.close()
            except Exception:
                pass

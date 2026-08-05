"""Image utility functions — format detection, alpha check, background removal.

Format/alpha/dimension detection are pure byte-level operations with
no external dependencies.  Background removal uses onnxruntime for
direct inference — the model (~168 MB) is downloaded on-demand and
cached alongside the application.

Usage::

    from storyloom.io.img_utils import detect_format, detect_alpha

    fmt = detect_format(raw_bytes)       # "png" | "webp" | "jpeg" | "unknown"
    has_alpha = detect_alpha(raw_bytes, fmt)

    # Background removal (model downloaded on-demand via download_model())
    result_bytes = remove_background(raw_bytes, "png")
"""

from __future__ import annotations

import struct
import time

from storyloom.io._types import ImageResult, RemoveBgPolicy

# NOTE: img_api_client.py imports from this module at function level
# (lazy imports inside generate()). The shared types live in _types.py
# so neither module depends on the other at import time.


# ═══════════════════════════════════════════════════════════════════
# Format detection
# ═══════════════════════════════════════════════════════════════════

def detect_format(raw: bytes) -> str:
    """Detect image format from magic bytes.

    Returns:
        "png", "webp", "jpeg", or "unknown".
    """
    if len(raw) < 4:
        return "unknown"
    if raw[:4] == b"RIFF" and len(raw) > 11 and raw[8:12] == b"WEBP":
        return "webp"
    if raw[:2] == b"\xff\xd8":
        return "jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return "unknown"


# ═══════════════════════════════════════════════════════════════════
# Alpha channel detection
# ═══════════════════════════════════════════════════════════════════

def detect_alpha(raw: bytes, fmt: str) -> bool:
    """Check if image has an alpha channel.

    Detects:
      - PNG:  color type 6 (RGBA) or 4 (grayscale+alpha)
      - WebP: VP8X alpha flag (bit 4 of flags byte)
      - JPEG: always False
    """
    if fmt == "png":
        if len(raw) > 25:
            color_type = raw[25]
            return color_type in (4, 6)
        return False
    if fmt == "webp":
        # VP8X chunk: RIFF(12) + "VP8X"(4) + flags(4)
        if len(raw) > 21 and raw[12:16] == b"VP8X":
            return bool(raw[20] & 0x10)
        return False
    return False  # jpeg, unknown


# ═══════════════════════════════════════════════════════════════════
# Dimension extraction
# ═══════════════════════════════════════════════════════════════════

def get_dimensions(raw: bytes, fmt: str) -> tuple[int, int]:
    """Extract image width and height from headers.

    Returns:
        (width, height) or (0, 0) on failure.
    """
    try:
        if fmt == "png":
            if len(raw) < 24:
                return 0, 0
            return struct.unpack(">II", raw[16:24])

        if fmt == "webp":
            if len(raw) < 30:
                return 0, 0
            if raw[12:16] == b"VP8X":
                # VP8X stores canvas_width - 1 and canvas_height - 1
                w = (struct.unpack_from("<I", raw, 24)[0] & 0xFFFFFF) + 1
                h = (struct.unpack_from("<I", raw, 27)[0] & 0xFFFFFF) + 1
                return w, h
            if raw[12:16] == b"VP8 ":
                if len(raw) >= 30:
                    return struct.unpack_from("<HH", raw, 26)
            return 0, 0

        if fmt == "jpeg":
            pos = 2
            max_pos = min(len(raw) - 9, 65536)  # scan first 64K only
            while pos < max_pos:
                if raw[pos] != 0xFF:
                    pos += 1
                    continue
                marker = raw[pos + 1]
                if marker in (0xC0, 0xC2, 0xC1):
                    return struct.unpack(">HH", raw[pos + 5: pos + 9])
                length = struct.unpack(">H", raw[pos + 2: pos + 4])[0]
                if length < 2:
                    break
                pos += 2 + length
    except (struct.error, IndexError, ValueError):
        pass
    return 0, 0


# ═══════════════════════════════════════════════════════════════════
# Background removal — direct onnxruntime inference (no rembg/pip needed)
# ═══════════════════════════════════════════════════════════════════
#
# The model (u2net.onnx, ~168 MB) is downloaded on-demand to
# ``<app>/models/`` when the user first enables background
# removal.  Once cached, inference runs in-process via onnxruntime
# with zero external dependencies.
#
# Model source: U²-Net (Xuebin Qin et al., 2020), ONNX export by rembg.
# Hosted on:    GitHub Releases (models-v1 tag, Storyloom repo).

import hashlib
import os
import sys
import tempfile as _tempfile_mod
import time
from pathlib import Path

import httpx
import numpy as np

from storyloom.config import (
    BG_REMOVAL_DOWNLOAD_TIMEOUT_SEC,
    BG_REMOVAL_MODEL_FILENAME,
    BG_REMOVAL_MODEL_SHA256,
    BG_REMOVAL_MODEL_URL,
)

# ── Model file management ──────────────────────────────────────────

# Lazy-cached ONNX session (thread-safe for inference).
_onnx_session: "ort.InferenceSession | None" = None
"""Module-level cache for the InferenceSession.  Set by _get_session()."""


def _model_dir() -> Path:
    """Directory where the background-removal model is stored.

    Resolution order:
      1. ``STORYLOOM_MODEL_DIR`` env var (explicit override)
      2. ``STORYLOOM_APP_DIR`` / "models" (alongside config.json)
      3. PyInstaller: "models/" next to the executable
      4. Fallback: "models/" in the current directory

    This keeps the model self-contained within the program directory —
    deleting the program folder removes everything, no residue.
    """
    env = os.environ.get("STORYLOOM_MODEL_DIR")
    if env:
        return Path(env)
    app_dir = os.environ.get("STORYLOOM_APP_DIR")
    if app_dir:
        return Path(app_dir) / "models"
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "models"
    return Path.cwd() / "models"


def _model_path() -> Path:
    """Absolute path to the cached model file."""
    return _model_dir() / BG_REMOVAL_MODEL_FILENAME


def check_model() -> bool:
    """Return True if the model file exists with the expected SHA256."""
    path = _model_path()
    if not path.exists():
        return False
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
    except OSError:
        return False
    return h.hexdigest() == BG_REMOVAL_MODEL_SHA256


def download_model(on_progress=None) -> tuple[bool, str]:
    """Download the background-removal model from GitHub Releases.

    Streams ~168 MB via httpx, verifies SHA256, and atomically replaces
    the cached file.

    Args:
        on_progress: Optional callback ``(received_bytes, total_bytes)``
            called after each chunk.  ``total_bytes`` may be 0 if the
            server doesn't report ``Content-Length``.

    Returns:
        ``(True, "Download complete")`` or ``(False, error_message)``.
    """
    path = _model_path()
    _model_dir().mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".onnx.tmp")

    try:
        with httpx.stream(
            "GET",
            BG_REMOVAL_MODEL_URL,
            timeout=BG_REMOVAL_DOWNLOAD_TIMEOUT_SEC,
            follow_redirects=True,
        ) as resp:
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code}"

            total = int(resp.headers.get("content-length", 0))
            received = 0
            h = hashlib.sha256()

            with open(tmp, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    h.update(chunk)
                    received += len(chunk)
                    if on_progress and total:
                        on_progress(received, total)

        # Verify checksum before replacing the cached file.
        if h.hexdigest() != BG_REMOVAL_MODEL_SHA256:
            try:
                tmp.unlink()
            except OSError:
                pass
            return False, "Checksum mismatch — downloaded file may be corrupt"

        # Atomic replace — no partial files left behind.
        os.replace(tmp, path)
        return True, "Download complete"

    except httpx.RequestError as e:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        return False, f"Network error: {e}"
    except Exception as e:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
        return False, str(e)


# ── ONNX inference ────────────────────────────────────────────────


def _get_session() -> "ort.InferenceSession | None":
    """Return a cached onnxruntime InferenceSession, or None if unavailable.

    The session is created once and reused — ``InferenceSession.run()``
    is thread-safe for inference.
    """
    global _onnx_session
    if _onnx_session is not None:
        return _onnx_session
    try:
        import onnxruntime as ort
    except ImportError:
        return None
    _onnx_session = ort.InferenceSession(
        str(_model_path()),
        providers=["CPUExecutionProvider"],
    )
    return _onnx_session


def _preprocess(img: "PILImage") -> np.ndarray:
    """Convert a PIL image to a normalized NCHW tensor (320×320).

    Matches the U²-Net preprocessing pipeline from rembg.
    """
    from PIL import Image
    im = img.convert("RGB").resize((320, 320), Image.Resampling.LANCZOS)
    im_ary = np.array(im).astype(np.float32)
    im_ary /= max(np.max(im_ary), 1e-6)

    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    im_ary = (im_ary - mean) / std

    # HWC → NCHW → add batch dimension
    im_ary = np.transpose(im_ary, (2, 0, 1))
    return np.expand_dims(im_ary, 0).astype(np.float32)


def remove_background(raw: bytes, fmt: str) -> bytes | None:
    """Remove background from an image using onnxruntime.

    Args:
        raw: Raw image bytes (PNG, JPEG, or WebP).
        fmt: Format string from :func:`detect_format`.

    Returns:
        PNG RGBA bytes with background removed, or ``None`` if the
        model is unavailable or inference fails.
    """
    if not check_model():
        return None

    try:
        from io import BytesIO
        from PIL import Image

        session = _get_session()
        if session is None:
            return None  # onnxruntime not installed

        img = Image.open(BytesIO(raw))
        orig_size = img.size

        tensor = _preprocess(img)
        input_name = session.get_inputs()[0].name

        ort_outs = session.run(None, {input_name: tensor})
        pred = ort_outs[0][:, 0, :, :]

        # Normalise mask to [0, 1]
        ma = float(np.max(pred))
        mi = float(np.min(pred))
        denom = ma - mi
        if denom < 1e-8:
            denom = 1.0
        pred = (pred - mi) / denom
        pred = np.squeeze(pred)

        # Create alpha mask, resize to original dimensions
        mask = Image.fromarray(
            (np.clip(pred, 0, 1) * 255).astype("uint8"), mode="L"
        )
        mask = mask.resize(orig_size, Image.Resampling.LANCZOS)

        # Compose RGBA: original RGB + mask as alpha
        img_rgba = img.convert("RGBA")
        img_rgba.putalpha(mask)

        buf = BytesIO()
        img_rgba.save(buf, format="PNG")
        return buf.getvalue()

    except (ImportError, ValueError, OSError, RuntimeError):
        # ImportError:   onnxruntime or Pillow missing
        # ValueError:    corrupt image data
        # OSError:       truncated / unreadable file
        # RuntimeError:  onnxruntime inference failure
        return None


def maybe_remove_background(
    result: ImageResult,
    policy: RemoveBgPolicy = RemoveBgPolicy.AUTO,
) -> ImageResult:
    """Apply background removal based on policy and alpha detection.

    Policy:
      - AUTO:   remove bg only if image has no alpha channel (default)
      - ALWAYS: force removal regardless of alpha
      - NEVER:  return result unchanged

    When the model is unavailable, the original image is returned
    unchanged (graceful degradation).
    """
    if policy == RemoveBgPolicy.NEVER:
        return result
    if policy == RemoveBgPolicy.AUTO and result.has_alpha:
        return result

    # Policy is AUTO (no alpha) or ALWAYS
    t0 = time.perf_counter()
    new_bytes = remove_background(result.bytes, result.format)
    if new_bytes is None:
        return result  # unavailable or failed — return original

    elapsed = time.perf_counter() - t0

    return ImageResult(
        bytes=new_bytes,
        format="png",            # RGBA output is always PNG
        has_alpha=True,           # mask was applied as alpha channel
        width=result.width,
        height=result.height,
        url=result.url,
        elapsed_ms=result.elapsed_ms + elapsed * 1000,
    )

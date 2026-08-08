"""Image utility functions — format detection, alpha check, background removal.

Format/alpha/dimension detection are pure byte-level operations with
no external dependencies.  Background removal uses onnxruntime for
direct inference — the model (~4.4 MB) is bundled as package data.

Usage::

    from storyloom.io.img_utils import detect_format, detect_alpha

    fmt = detect_format(raw_bytes)       # "png" | "webp" | "jpeg" | "unknown"
    has_alpha = detect_alpha(raw_bytes, fmt)

    # Background removal (model bundled — no download needed)
    result_bytes = remove_background(raw_bytes, "png")
"""

from __future__ import annotations

import struct
import time
from io import BytesIO

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
# The model (u2netp.onnx, ~4.4 MB) is bundled as package data in
# ``src/storyloom/models/``.  It is downloaded at build time by the
# setup.py hook (``pip install -e .`` / ``pip install .``) and shipped
# in both the wheel and the PyInstaller binary.
#
# Model source: U²-Net (Xuebin Qin et al., 2020), ONNX export by rembg.

import os
import sys
from pathlib import Path

import numpy as np

from storyloom.config import (
    BG_REMOVAL_MODEL_FILENAME,
    BG_REMOVAL_MODEL_SHA256,
)

# ── Model file management ──────────────────────────────────────────

# Lazy-cached ONNX session (thread-safe for inference).
_onnx_session: "ort.InferenceSession | None" = None
"""Module-level cache for the InferenceSession.  Set by _get_session()."""


def _model_dir() -> Path:
    """Directory where the background-removal model is stored.

    Resolution order:
      1. ``STORYLOOM_MODEL_DIR`` env var (explicit override)
      2. ``<package>/models/`` — bundled package data
         (wheel / PyInstaller --add-data / dev source tree)
      3. ``STORYLOOM_APP_DIR`` / "models" (alongside config.json)
      4. PyInstaller: "models/" next to the executable
      5. Fallback: "models/" in the current directory
    """
    env = os.environ.get("STORYLOOM_MODEL_DIR")
    if env:
        return Path(env)
    # Bundled in package (wheel, PyInstaller, dev)
    pkg = Path(__file__).resolve().parent.parent / "models"
    if pkg.is_dir():
        return pkg
    app_dir = os.environ.get("STORYLOOM_APP_DIR")
    if app_dir:
        return Path(app_dir) / "models"
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "models"
    return Path.cwd() / "models"


def _model_path() -> Path:
    """Absolute path to the model file."""
    return _model_dir() / BG_REMOVAL_MODEL_FILENAME


def check_model() -> bool:
    """Return True if the model file exists with the expected SHA256."""
    import hashlib
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


# ═══════════════════════════════════════════════════════════════════
# Background aspect ratio normalisation (§7.8b)
# ═══════════════════════════════════════════════════════════════════

_TARGET_AR = 16.0 / 9.0
_AR_TOLERANCE = 0.02  # ±2% — within this range, skip crop


def normalize_background(raw: bytes) -> bytes:
    """Center-crop a background image to 16:9 if its aspect ratio deviates
    by more than ±2%.

    This is a safety net: models may return images whose dimensions differ
    slightly from the requested size.  The UI uses ``object-fit: cover``
    which crops to fill the viewport, so an off-ratio file produces
    unpredictable framing.  Normalising at save time guarantees consistent
    behaviour regardless of model quirks.

    If PIL is unavailable the original bytes are returned unchanged
    (graceful degradation — the UI's ``cover`` crop still works, just
    with less control over the framing).
    """
    fmt = detect_format(raw)
    w, h = get_dimensions(raw, fmt)
    if w == 0 or h == 0:
        return raw

    ar = w / h
    if abs(ar - _TARGET_AR) <= _AR_TOLERANCE:
        return raw

    try:
        from PIL import Image
    except ImportError:
        return raw

    if ar > _TARGET_AR:
        new_w = int(h * _TARGET_AR)
        new_h = h
    else:
        new_w = w
        new_h = int(w / _TARGET_AR)

    left = (w - new_w) // 2
    top = (h - new_h) // 2
    right = left + new_w
    bottom = top + new_h

    img = Image.open(BytesIO(raw))
    cropped = img.crop((left, top, right, bottom))

    buf = BytesIO()
    save_fmt = "PNG" if (fmt in ("png", "webp") or img.mode == "RGBA") else "JPEG"
    cropped.save(buf, format=save_fmt)
    return buf.getvalue()

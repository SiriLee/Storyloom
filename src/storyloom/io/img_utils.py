"""Image utility functions — format detection, alpha check, background removal.

Pure byte-level operations, no HTTP dependency. rembg integration is
optional — functions degrade gracefully when rembg is not installed.

Usage::

    from storyloom.io.img_utils import detect_format, detect_alpha

    fmt = detect_format(raw_bytes)       # "png" | "webp" | "jpeg" | "unknown"
    has_alpha = detect_alpha(raw_bytes, fmt)

    # Background removal (needs rembg installed via install_rembg())
    if _check_rembg():
        result_bytes = remove_background(raw_bytes, "png")
"""

from __future__ import annotations

import struct
import time

from storyloom.io.img_api_client import ImageResult, RemoveBgPolicy

# NOTE: img_api_client.py imports from this module at function level
# (lazy imports inside generate()). Keep module-level imports in this
# file restricted to pure data types from img_api_client to avoid
# circular import issues.


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
# Background removal (rembg — optional)
# ═══════════════════════════════════════════════════════════════════

_HAS_REMBG: bool | None = None
"""Module-level cache: None = unchecked, True = available, False = unavailable.

Thread safety: relies on CPython GIL for atomic reads/writes of this
reference. The check-then-import in `_check_rembg` may trigger redundant
imports under contention, but Python's import system is internally
locked so no corruption occurs. Not safe under free-threaded Python
without explicit locking.
"""


def _check_rembg() -> bool:
    """Return True if rembg is importable (lazy, cached).

    Use this before calling :func:`remove_background` to check
    availability without triggering an import.
    """
    global _HAS_REMBG
    if _HAS_REMBG is None:
        try:
            from rembg import remove  # noqa: F401
            _HAS_REMBG = True
        except ImportError:
            _HAS_REMBG = False
    return _HAS_REMBG


def install_rembg() -> tuple[bool, str]:
    """Download and install rembg[cpu] via pip. Call once at app startup.

    Returns:
        (success, message) — message is a human-readable status string.
    """
    import subprocess
    import sys

    if _check_rembg():
        return True, "rembg already installed"

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "rembg[cpu]"],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            # Force re-check on next _check_rembg() call
            global _HAS_REMBG
            _HAS_REMBG = None
            return True, "Installation complete"
        else:
            tail = result.stderr.strip()[-300:] if result.stderr else "(no output)"
            return False, f"pip install failed: {tail}"
    except Exception as e:
        return False, str(e)


def remove_background(raw: bytes, fmt: str) -> bytes | None:
    """Run rembg on the image. Returns PNG RGBA bytes, or None on failure.

    Cold: ~28s (first call downloads 176 MB u2net model).
    Warm: ~0.7s per image.
    """
    if not _check_rembg():
        return None

    try:
        from rembg import remove
        from PIL import Image
        from io import BytesIO

        img = Image.open(BytesIO(raw))
        result = remove(img)
        buf = BytesIO()
        result.save(buf, format="PNG")
        return buf.getvalue()
    except (ImportError, ValueError, OSError, RuntimeError):
        # RuntimeError: onnxruntime model/inference failures
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

    Delegates availability checking to :func:`remove_background` — if
    rembg is unavailable, it returns None and we fall back to the
    original image.
    """
    if policy == RemoveBgPolicy.NEVER:
        return result
    if policy == RemoveBgPolicy.AUTO and result.has_alpha:
        return result

    # Policy is AUTO (no alpha) or ALWAYS
    t0 = time.perf_counter()
    new_bytes = remove_background(result.bytes, result.format)
    if new_bytes is None:
        return result  # rembg unavailable or failed — return original

    elapsed = time.perf_counter() - t0

    return ImageResult(
        bytes=new_bytes,
        format="png",           # rembg always outputs PNG
        has_alpha=True,          # rembg output is always RGBA
        width=result.width,
        height=result.height,
        url=result.url,
        elapsed_ms=result.elapsed_ms + elapsed * 1000,
    )

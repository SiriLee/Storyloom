"""Shared utilities for system asset generation scripts.

Internal module — not part of the public storyloom API.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from storyloom.assets._types import AssetType
from storyloom.io._types import ImageSize, RemoveBgPolicy
from storyloom.io.img_utils import detect_format, get_dimensions

# 16:9 aspect ratio target for backgrounds
_TARGET_AR = 16.0 / 9.0
_AR_TOLERANCE = 0.02  # ±2% — within this range, skip crop

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "system_media_src"
_OUTPUT_DIR = _PROJECT_ROOT / "system_media"

# Which source JSON file corresponds to which AssetType
_TYPE_TO_SRC: dict[AssetType, str] = {
    AssetType.CHAR_PORTRAIT: "char_portrait.json",
    AssetType.BACKGROUND: "background_img.json",
}
_SRC_TO_TYPE: dict[str, AssetType] = {
    v: k for k, v in _TYPE_TO_SRC.items()
}


def find_asset(asset_id: str) -> tuple[AssetType, dict] | None:
    """Look up *asset_id* in all source files.

    Returns:
        ``(AssetType, entry_dict)`` or ``None`` if not found.
        ``entry_dict`` has keys ``name``, ``description``, ``prompt``.
    """
    for atype, filename in _TYPE_TO_SRC.items():
        path = _SRC_DIR / filename
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if asset_id in data:
            return atype, data[asset_id]
    return None


def load_source(asset_type: AssetType) -> dict[str, dict]:
    """Load all entries for *asset_type* from its source file.

    Returns:
        ``{asset_id: {name, description, prompt}}``
    """
    filename = _TYPE_TO_SRC[asset_type]
    path = _SRC_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Source file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def asset_type_from_id(asset_id: str) -> AssetType | None:
    """Infer :class:`AssetType` from an asset ID prefix convention.

    System portrait IDs start with ``sys_`` but have no type marker in
    the ID itself, so this delegates to :func:`find_asset`.
    """
    result = find_asset(asset_id)
    return result[0] if result else None


def get_image_size(asset_type: AssetType) -> ImageSize:
    """Return the :class:`ImageSize` for *asset_type*."""
    if asset_type is AssetType.CHAR_PORTRAIT:
        return ImageSize.PORTRAIT
    return ImageSize.BACKGROUND


def get_remove_bg(asset_type: AssetType) -> RemoveBgPolicy | None:
    """Return the background removal policy for *asset_type*.

    ``None`` means "defer to the caller's ``cfg.portrait_remove_bg``".
    Background images always return ``RemoveBgPolicy.NEVER``.
    """
    if asset_type is AssetType.BACKGROUND:
        return RemoveBgPolicy.NEVER
    # CHAR_PORTRAIT — caller resolves from UserConfig
    return None


def output_path(asset_type: AssetType, asset_id: str) -> Path:
    """Return the output file path for a generated asset."""
    subdir = asset_type.value
    ext = asset_type.default_extension
    return _OUTPUT_DIR / subdir / f"{asset_id}{ext}"


def output_dir() -> Path:
    """Return the root output directory (``system_media/``)."""
    return _OUTPUT_DIR


# ═══════════════════════════════════════════════════════════════════
# Post-processing — aspect-ratio normalization
# ═══════════════════════════════════════════════════════════════════

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
        return raw  # can't detect — leave alone

    ar = w / h
    if abs(ar - _TARGET_AR) <= _AR_TOLERANCE:
        return raw  # already 16:9 within tolerance

    try:
        from PIL import Image
    except ImportError:
        return raw  # PIL not available — leave alone

    # Calculate target dimensions
    if ar > _TARGET_AR:
        # Too wide — crop sides
        new_w = int(h * _TARGET_AR)
        new_h = h
    else:
        # Too tall — crop top/bottom
        new_w = w
        new_h = int(w / _TARGET_AR)

    left = (w - new_w) // 2
    top = (h - new_h) // 2
    right = left + new_w
    bottom = top + new_h

    img = Image.open(BytesIO(raw))
    cropped = img.crop((left, top, right, bottom))

    buf = BytesIO()
    # Preserve alpha if present; JPEG → PNG for consistency
    save_fmt = "PNG" if (fmt in ("png", "webp") or img.mode == "RGBA") else "JPEG"
    cropped.save(buf, format=save_fmt)
    return buf.getvalue()

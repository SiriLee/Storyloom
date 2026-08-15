"""Shared utilities for system asset generation scripts.

Internal module — not part of the public storyloom API.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from storyloom.assets._types import AssetType
from storyloom.io._types import ImageSize, RemoveBgPolicy
from storyloom.io.img_utils import detect_format, get_dimensions, normalize_background

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
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


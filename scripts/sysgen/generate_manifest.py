"""Generate ``system_media/_manifest.json`` from ``system_media_src/`` sources.

The source files (``system_media_src/{char_portrait,background_img}.json``)
are the authoritative definition of system assets.  This script extracts the
``name`` and ``description`` fields and writes the manifest — the ``prompt``
field is intentionally omitted (it is consumed only by the generation scripts).

Usage::

    python scripts/sysgen/generate_manifest.py
    python scripts/sysgen/generate_manifest.py --dry-run
    python scripts/sysgen/generate_manifest.py --version 1.1.0

The version is read from ``system_media_src/VERSION`` (the tracked source of
truth); ``--version`` overrides it for a one-off run.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_SRC_DIR = _PROJECT_ROOT / "system_media_src"
_MANIFEST_PATH = _PROJECT_ROOT / "system_media" / "_manifest.json"
_VERSION_PATH = _PROJECT_ROOT / "system_media" / "VERSION"
# The tracked source of truth for the content version.  ``system_media/VERSION``
# is generated output and gitignored; bump the version here, then regenerate.
_SRC_VERSION_PATH = _SRC_DIR / "VERSION"

# Asset types expected under system_media_src/
ASSET_TYPES = ["char_portrait", "background_img"]


def load_sources() -> dict:
    """Read all source JSON files from ``system_media_src/``.

    Returns:
        ``{asset_type_str: {asset_id: {name, description}}}``

    Raises:
        FileNotFoundError: If a source file is missing.
        ValueError: If a source entry is missing required fields.
    """
    assets: dict[str, dict] = {}

    for atype in ASSET_TYPES:
        path = _SRC_DIR / f"{atype}.json"
        if not path.exists():
            raise FileNotFoundError(f"Source file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        assets[atype] = {}
        for asset_id, entry in data.items():
            name = entry.get("name")
            description = entry.get("description")
            if not name:
                raise ValueError(f"{path}: {asset_id}: missing 'name'")
            if description is None:
                raise ValueError(f"{path}: {asset_id}: missing 'description'")
            assets[atype][asset_id] = {
                "name": name,
                "description": description,
            }

    return assets


def write_manifest(assets: dict, version: str) -> None:
    """Write ``_manifest.json`` and ``VERSION`` to ``system_media/``.

    Args:
        assets: Parsed source data (output of :func:`load_sources`).
        version: Semantic version string for the manifest.
    """
    manifest = {
        "version": version,
        "assets": assets,
    }

    _MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    with open(_VERSION_PATH, "w", encoding="utf-8") as f:
        f.write(version + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate system_media/_manifest.json from source files"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Load sources and validate, but do not write files",
    )
    parser.add_argument(
        "--version", type=str, default=None,
        help="Manifest version (default: read from system_media_src/VERSION)",
    )
    args = parser.parse_args()

    # ── Load sources ──────────────────────────────────────────────────
    try:
        assets = load_sources()
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    # ── Count ─────────────────────────────────────────────────────────
    total = sum(len(entries) for entries in assets.values())
    print(f"Loaded {total} assets from {len(assets)} source file(s):")
    for atype in ASSET_TYPES:
        print(f"  {atype}: {len(assets[atype])}")

    # ── Version ───────────────────────────────────────────────────────
    version = args.version
    if version is None:
        if _SRC_VERSION_PATH.exists():
            version = _SRC_VERSION_PATH.read_text().strip()
        else:
            version = "0.0.0"

    if args.dry_run:
        print(f"\n[dry-run] Would write manifest version {version}")
        return

    # ── Write ─────────────────────────────────────────────────────────
    write_manifest(assets, version)
    print(f"\nWrote: {_MANIFEST_PATH}")
    print(f"Wrote: {_VERSION_PATH}")
    print(f"Version: {version}")


if __name__ == "__main__":
    main()

"""System manifest loader — reads ``system_media/_manifest.json``.

Per design: the manifest declares what system assets *should* exist.
Loaded at startup for reconciliation with the persisted AssetLibrary state
(``_asset_lib.json``).  The manifest is the declarative source of truth;
the library is the runtime state.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from storyloom.assets._types import AssetType
from storyloom.config import SYSTEM_MANIFEST_FILENAME


@dataclass
class ManifestEntry:
    """A single system-asset declaration in the manifest.

    Attributes:
        name: Human-readable name (e.g. "Village Elder").
        description: Detailed visual description for LLM matching.
        tags: Optional semantic tags for future fuzzy-match filtering.
    """
    name: str
    description: str
    tags: list[str] = field(default_factory=list)


@dataclass
class SystemManifest:
    """Parsed contents of ``_manifest.json``.

    Attributes:
        version: Semantic version of the system-asset package (e.g. "1.0.0").
        assets: ``AssetType`` → ``{asset_id: ManifestEntry}``.
    """
    version: str
    assets: dict[AssetType, dict[str, ManifestEntry]]

    @staticmethod
    def load(system_dir: str) -> "SystemManifest":
        """Read and validate ``_manifest.json`` from *system_dir*.

        Raises:
            FileNotFoundError: If ``_manifest.json`` does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
            ValueError: If required keys (``version``, ``assets``) are missing.
        """
        path = os.path.join(system_dir, SYSTEM_MANIFEST_FILENAME)
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        version = data.get("version")
        if version is None:
            raise ValueError("_manifest.json: missing required key 'version'")

        raw_assets = data.get("assets")
        if raw_assets is None:
            raise ValueError("_manifest.json: missing required key 'assets'")

        assets: dict[AssetType, dict[str, ManifestEntry]] = {}
        for type_str, type_entries in raw_assets.items():
            try:
                atype = AssetType(type_str)
            except ValueError:
                # Unknown asset type — forward compatibility: skip
                continue
            assets[atype] = {}
            for asset_id, entry_data in type_entries.items():
                assets[atype][asset_id] = ManifestEntry(
                    name=entry_data["name"],
                    description=entry_data.get("description", ""),
                    tags=entry_data.get("tags", []),
                )

        return SystemManifest(
            version=version,
            assets=assets,
        )

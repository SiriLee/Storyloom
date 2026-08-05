"""Asset data types — AssetType, Asset, AssetItem.

Per design.md §2: Three-layer abstraction data model.
These are in-memory value objects; serialization is via to_dict/from_dict.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import Enum


class AssetType(Enum):
    """Type of a media asset.  Value is the directory name under media/.  (D2)."""

    CHAR_PORTRAIT = "char_portrait"
    BACKGROUND = "background_img"

    @property
    def default_extension(self) -> str:
        """Default file extension for this asset type.  (D3)."""
        # All image types use .png; audio/video types may override
        return ".png"


# ═══════════════════════════════════════════════════════════════════
# Asset
# ═══════════════════════════════════════════════════════════════════

@dataclass
class Asset:
    """A single asset entry in the global AssetLibrary.  (design.md §2.2).

    Equality is by identity (asset_type, id) — mutable fields like
    use_count and serial do not affect equality.  (D49).
    """

    asset_type: AssetType
    id: str
    name: str
    description: str = ""
    use_count: int = 0
    serial: int = field(default=-1)

    # ── Derived ──

    @property
    def file_path(self) -> str:
        """Relative path from media_dir to the asset file.  (D19)."""
        return f"{self.asset_type.value}/{self.id}{self.asset_type.default_extension}"

    # ── Serialization ──

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict.

        asset_type and id are NOT stored — they are the structural keys
        in _asset_lib.json (design.md §9).  (D5).
        """
        return {
            "name": self.name,
            "description": self.description,
            "use_count": self.use_count,
            "serial": self.serial,
        }

    @classmethod
    def from_dict(cls, data: dict, *, asset_type: AssetType, asset_id: str) -> Asset:
        """Deserialize from a JSON dict.  asset_type and asset_id are
        extracted from the outer dict keys by the caller.  (D5)."""
        return cls(
            asset_type=asset_type,
            id=asset_id,
            name=data["name"],
            description=data.get("description", ""),
            use_count=data.get("use_count", 0),
            serial=data.get("serial", -1),
        )

    # ── Equality ──

    def __eq__(self, other: object) -> bool:
        """Identity equality: same (asset_type, id).  Mutable fields ignored.  (D49)."""
        if not isinstance(other, Asset):
            return NotImplemented
        return self.asset_type is other.asset_type and self.id == other.id

    def __hash__(self) -> int:
        """Hash by identity; Asset is intended to be stored in sets/dicts."""
        return hash((self.asset_type, self.id))


# ═══════════════════════════════════════════════════════════════════
# AssetItem
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AssetItem:
    """A single entry in the per-game GameAssetRoster.  (design.md §2.3).

    Maps a local_name (used by the Director LLM) to an Asset.id (or None,
    meaning a placeholder — the asset has not been generated yet). (D36).

    Equality is by local_name — mutable fields (description, target) do
    not affect equality.  (D49).
    """

    local_name: str
    local_description: str = ""
    target: str | None = None

    # ── Serialization ──

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict.

        local_name is NOT stored — it is the structural key in
        _asset_roster.json (design.md §9).  (D5).
        """
        return {
            "local_description": self.local_description,
            "target": self.target,
        }

    @classmethod
    def from_dict(cls, local_name: str, data: dict) -> AssetItem:
        """Deserialize from a JSON dict.  local_name is extracted from
        the outer dict key by the caller.  (D5)."""
        return cls(
            local_name=local_name,
            local_description=data.get("local_description", ""),
            target=data.get("target"),
        )

    # ── Equality ──

    def __eq__(self, other: object) -> bool:
        """Identity equality: same local_name.  Mutable fields ignored.  (D49)."""
        if not isinstance(other, AssetItem):
            return NotImplemented
        return self.local_name == other.local_name

    def __hash__(self) -> int:
        """Hash by local_name."""
        return hash(self.local_name)

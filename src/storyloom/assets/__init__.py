"""Asset database layer — types, library, roster.

Per design.md §2: Three-layer abstraction:
  AssetType / Asset / AssetItem — core data types
  AssetLibrary — global asset registry (media/_asset_lib.json)
  GameAssetRoster — per-game asset mapping (saves/{id}/_asset_roster.json)
"""

from storyloom.assets._library import AssetLibrary
from storyloom.assets._roster import GameAssetRoster
from storyloom.assets._types import Asset, AssetItem, AssetType

__all__ = [
    "Asset",
    "AssetItem",
    "AssetLibrary",
    "AssetType",
    "GameAssetRoster",
]

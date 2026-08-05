"""GameAssetRoster — per-game asset mapping.  (design.md §2.3).

Thread-safe.  One instance per game.  Stored at saves/{game_id}/_asset_roster.json.
"""

from __future__ import annotations

import json
import os
import threading

from storyloom.assets._types import AssetItem, AssetType

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from storyloom.assets._library import AssetLibrary


class GameAssetRoster:
    """Per-game mapping from ``local_name`` (used by the Director LLM) to
    ``Asset.id`` (or ``None`` for placeholders).

    Thread-safe: all public methods acquire ``self._lock``.  (D18).

    Injected with an ``AssetLibrary`` for ``use_count`` coordination.  (D20).
    """

    VERSION = 1

    # ── Construction ────────────────────────────────────────────────

    def __init__(self, game_id: str, library: AssetLibrary):
        self.game_id = game_id
        self._library = library
        self._items: dict[AssetType, dict[str, AssetItem]] = {}
        self._lock = threading.Lock()

    # ── CRUD ────────────────────────────────────────────────────────

    def add(
        self,
        asset_type: AssetType,
        local_name: str,
        local_description: str = "",
        target: str | None = None,
    ) -> AssetItem:
        """Add a new entry.  Returns the created ``AssetItem``.

        If *target* is not ``None``, calls ``library.increase_usage(target)``.
        (D38).

        Raises ``ValueError`` if *(asset_type, local_name)* already exists.
        """
        with self._lock:
            type_items = self._items.setdefault(asset_type, {})
            if local_name in type_items:
                raise ValueError(
                    f"AssetItem already exists: "
                    f"{asset_type.value}/{local_name}"
                )
            if target is not None:
                self._library.increase_usage(asset_type, target)
            item = AssetItem(
                local_name=local_name,
                local_description=local_description,
                target=target,
            )
            type_items[local_name] = item
            return item

    def set_target(
        self,
        asset_type: AssetType,
        local_name: str,
        new_target: str | None,
    ) -> None:
        """Update the target of an existing entry.

        - Old target → ``library.decrease_usage``
        - New target → ``library.increase_usage`` (if not ``None``)

        Handles placeholder transitions (``None`` ↔ real target).  (D20).
        """
        with self._lock:
            item = self._require(asset_type, local_name)
            old_target = item.target

            if old_target == new_target:
                return  # no-op

            if old_target is not None:
                self._library.decrease_usage(asset_type, old_target)
            if new_target is not None:
                self._library.increase_usage(asset_type, new_target)

            item.target = new_target

    def remove(self, asset_type: AssetType, local_name: str) -> None:
        """Remove an entry.  Calls ``library.decrease_usage`` if the entry
        has a non-``None`` target.  (D48).

        Raises ``ValueError`` if not found.
        """
        with self._lock:
            item = self._require(asset_type, local_name)
            if item.target is not None:
                self._library.decrease_usage(asset_type, item.target)
            del self._items[asset_type][local_name]
            if not self._items[asset_type]:
                del self._items[asset_type]

    def lookup(self, asset_type: AssetType, local_name: str) -> AssetItem | None:
        """Return the ``AssetItem``, or ``None`` if not found.

        Exact string comparison — no fuzzy matching.  (D9).
        """
        with self._lock:
            return self._items.get(asset_type, {}).get(local_name)

    def clear(self) -> None:
        """Remove all entries.  Calls ``library.decrease_usage`` for every
        entry with a non-``None`` target.  (D48).
        """
        with self._lock:
            for atype, type_items in self._items.items():
                for item in type_items.values():
                    if item.target is not None:
                        self._library.decrease_usage(atype, item.target)
            self._items.clear()

    # ── Queries ──────────────────────────────────────────────────────

    def list_by_type(self, asset_type: AssetType) -> dict[str, AssetItem]:
        """Return a *copy* of the type→item dict."""
        with self._lock:
            return dict(self._items.get(asset_type, {}))

    # ── Persistence ──────────────────────────────────────────────────

    def save(self, filepath: str) -> None:
        """Write the roster to *filepath*.  Atomic: ``.tmp`` + ``os.replace``.
        (D16)."""
        data = self._to_save_dict()
        tmp_path = filepath + ".tmp"
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)

    @classmethod
    def load(
        cls,
        filepath: str,
        library: AssetLibrary,
        game_id: str,
    ) -> GameAssetRoster:
        """Load the roster from *filepath*.

        Returns an **empty** instance if the file does not exist.  (D41).
        The *game_id* parameter is used for the empty-instance fallback.

        Raises ``ValueError`` on version mismatch or corrupt JSON.  (D42).
        """
        if not os.path.isfile(filepath):
            return cls(game_id, library)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"corrupt _asset_roster.json: {e}") from e

        version = data.get("version")
        if version != cls.VERSION:
            raise ValueError(
                f"Unsupported _asset_roster.json version {version} "
                f"(expected {cls.VERSION})"
            )

        file_game_id = data.get("game_id", game_id)
        roster = cls(file_game_id, library)
        items_data = data.get("items", {})
        for type_str, type_items in items_data.items():
            atype = AssetType(type_str)
            roster._items[atype] = {}
            for local_name, item_data in type_items.items():
                roster._items[atype][local_name] = AssetItem.from_dict(
                    local_name, item_data
                )

        return roster

    # ── Magic ────────────────────────────────────────────────────────

    def __len__(self) -> int:
        """Total number of entries across all types."""
        with self._lock:
            return sum(len(items) for items in self._items.values())

    def __contains__(self, key: tuple[AssetType, str]) -> bool:
        """``(asset_type, local_name) in roster``."""
        atype, name = key
        with self._lock:
            return name in self._items.get(atype, {})

    # ── Internal ─────────────────────────────────────────────────────

    def _require(self, asset_type: AssetType, local_name: str) -> AssetItem:
        """Fetch an item or raise ValueError if not found."""
        type_items = self._items.get(asset_type)
        if type_items is None or local_name not in type_items:
            raise ValueError(
                f"AssetItem not found: {asset_type.value}/{local_name}"
            )
        return type_items[local_name]

    def _to_save_dict(self) -> dict:
        """Build the JSON-serializable dict.  (design.md §9)."""
        items: dict[str, dict[str, dict]] = {}
        for atype, type_items in self._items.items():
            items[atype.value] = {
                name: item.to_dict() for name, item in type_items.items()
            }
        return {
            "version": self.VERSION,
            "game_id": self.game_id,
            "items": items,
        }

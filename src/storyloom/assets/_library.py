"""AssetLibrary — global asset registry.  (design.md §2.2).

Thread-safe.  One instance per application.  Stored at media/_asset_lib.json.
"""

from __future__ import annotations

import heapq
import json
import os
import re
import threading
import uuid

from storyloom.assets._types import Asset, AssetType

# asset_id must be a filesystem-safe identifier — no path separators.
_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")


class AssetLibrary:
    """Global registry of all media assets.

    Thread-safe: all public methods acquire ``self._lock`` before accessing
    ``_items`` or ``_serial_counter``.  (D18).

    Persistence: ``save()`` / ``load()`` against ``media_dir/_asset_lib.json``
    with atomic writes (``.tmp`` + ``os.replace``).  (D16, D41).
    """

    VERSION = 1

    # ── Construction ────────────────────────────────────────────────

    def __init__(self, media_dir: str):
        self.media_dir = media_dir
        self._items: dict[AssetType, dict[str, Asset]] = {}
        self._serial_counter: int = 0
        self._lock = threading.Lock()

    # ── CRUD ────────────────────────────────────────────────────────

    def add(
        self,
        asset_type: AssetType,
        name: str,
        description: str = "",
        asset_id: str | None = None,
    ) -> Asset:
        """Add a new asset.  Returns the created Asset.

        If *asset_id* is omitted, a ``uuid4().hex`` is generated.  (D4).
        Raises ``ValueError`` if the id already exists in this type.  (D23).
        """
        if asset_id is None:
            asset_id = uuid.uuid4().hex
        elif not _SAFE_ID_RE.match(asset_id):
            raise ValueError(
                f"asset_id must match {_SAFE_ID_RE.pattern!r}, got {asset_id!r}"
            )

        with self._lock:
            type_items = self._items.setdefault(asset_type, {})
            if asset_id in type_items:
                raise ValueError(
                    f"Asset already exists: {asset_type.value}/{asset_id}"
                )
            serial = self._serial_counter
            self._serial_counter += 1
            asset = Asset(
                asset_type=asset_type,
                id=asset_id,
                name=name,
                description=description,
                use_count=0,
                serial=serial,
            )
            type_items[asset_id] = asset
            return asset

    def get(self, asset_type: AssetType, asset_id: str) -> Asset | None:
        """Return the Asset, or ``None`` if not found.  (D46)."""
        with self._lock:
            return self._items.get(asset_type, {}).get(asset_id)

    def remove(self, asset_type: AssetType, asset_id: str) -> Asset:
        """Remove an asset.  Returns the removed Asset.

        Raises ``ValueError`` if not found or if ``use_count > 0``.  (D25).
        """
        with self._lock:
            type_items = self._items.get(asset_type)
            if type_items is None or asset_id not in type_items:
                raise ValueError(
                    f"Asset not found: {asset_type.value}/{asset_id}"
                )
            asset = type_items[asset_id]
            if asset.use_count > 0:
                raise ValueError(
                    f"Cannot remove asset with use_count={asset.use_count}: "
                    f"{asset_type.value}/{asset_id}"
                )
            del type_items[asset_id]
            # Clean up empty type bucket
            if not type_items:
                del self._items[asset_type]
            return asset

    # ── Reference counting ───────────────────────────────────────────

    def increase_usage(self, asset_type: AssetType, asset_id: str) -> None:
        """Increment ``use_count`` by 1.

        Raises ``ValueError`` if the asset is not found.
        """
        with self._lock:
            asset = self._require(asset_type, asset_id)
            asset.use_count += 1

    def decrease_usage(self, asset_type: AssetType, asset_id: str) -> None:
        """Decrement ``use_count`` by 1.

        Raises ``ValueError`` if the asset is not found, or if decrementing
        would go below 0.  (D24).
        """
        with self._lock:
            asset = self._require(asset_type, asset_id)
            if asset.use_count <= 0:
                raise ValueError(
                    f"Cannot decrease use_count below 0: "
                    f"{asset_type.value}/{asset_id}"
                )
            asset.use_count -= 1

    # ── Queries ──────────────────────────────────────────────────────

    def list_all(self) -> list[Asset]:
        """Return all assets across all types as a flat list."""
        with self._lock:
            result: list[Asset] = []
            for type_items in self._items.values():
                result.extend(type_items.values())
            return result

    def list_by_type(self, asset_type: AssetType) -> dict[str, Asset]:
        """Return a *copy* of the type→asset dict."""
        with self._lock:
            return dict(self._items.get(asset_type, {}))

    def get_sorted_by_usage(
        self, asset_type: AssetType, top_n: int
    ) -> list[Asset]:
        """Return the top *top_n* assets of *asset_type*, sorted by
        ``(-use_count, -serial)``.  Uses ``heapq.nlargest`` for O(n log k)
        performance.  (D10, D51).
        """
        with self._lock:
            assets = list(self._items.get(asset_type, {}).values())
            if not assets:
                return []
            # Key: higher use_count first, then higher (more recent) serial
            key = lambda a: (a.use_count, a.serial)
            return heapq.nlargest(top_n, assets, key=key)

    # ── Maintenance ──────────────────────────────────────────────────

    def clean(self, keep_count: int) -> int:
        """Delete unused assets to keep total count at or below *keep_count*.

        Assets with ``use_count > 0`` are **never** deleted.  Among
        ``use_count == 0`` assets, those with the **lowest** priority
        (by ``(-use_count, -serial)``) are deleted first.  (D45).

        Returns the number of assets deleted.
        """
        with self._lock:
            if keep_count < 0:
                keep_count = 0

            # Collect all assets with their priority key
            all_assets: list[tuple[tuple, AssetType, str]] = []
            for atype, type_items in self._items.items():
                for aid, asset in type_items.items():
                    all_assets.append(((asset.use_count, asset.serial), atype, aid))

            # Protected: use_count > 0.  Keep newest unprotected up to keep_count.
            protected = [(k, t, i) for k, t, i in all_assets if k[0] > 0]
            unprotected = [(k, t, i) for k, t, i in all_assets if k[0] == 0]

            if len(protected) >= keep_count:
                # Delete all unprotected
                to_delete = unprotected
            else:
                budget = keep_count - len(protected)
                # Sort unprotected by (use_count, serial) ascending, then take
                # the lowest-priority ones beyond the budget
                unprotected.sort(key=lambda x: x[0])  # ascending
                to_delete = unprotected[:-budget] if budget < len(unprotected) else []

            for (_key, atype, aid) in to_delete:
                del self._items[atype][aid]
                if not self._items[atype]:
                    del self._items[atype]

            return len(to_delete)

    # ── Persistence ──────────────────────────────────────────────────

    def save(self) -> None:
        """Write the library to ``media_dir/_asset_lib.json``.  Atomic:
        writes to a ``.tmp`` file then ``os.replace``.  (D16)."""
        with self._lock:
            data = self._to_save_dict()
        filepath = os.path.join(self.media_dir, "_asset_lib.json")
        tmp_path = filepath + ".tmp"
        os.makedirs(self.media_dir, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)

    @classmethod
    def load(cls, media_dir: str) -> AssetLibrary:
        """Load the library from ``media_dir/_asset_lib.json``.

        Returns an **empty** instance if the file does not exist.  (D41).
        Raises ``ValueError`` on version mismatch or corrupt JSON.  (D42).
        """
        lib = cls(media_dir)
        filepath = os.path.join(media_dir, "_asset_lib.json")
        if not os.path.isfile(filepath):
            return lib

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"corrupt _asset_lib.json: {e}") from e

        version = data.get("version")
        if version != cls.VERSION:
            raise ValueError(
                f"Unsupported _asset_lib.json version {version} "
                f"(expected {cls.VERSION})"
            )

        max_serial = -1
        items_data = data.get("items", {})
        for type_str, type_items in items_data.items():
            try:
                atype = AssetType(type_str)
            except ValueError:
                # Unknown asset type — forward compatibility: skip,
                # don't crash.  Future versions may add new types.  (§2.1)
                continue
            lib._items[atype] = {}
            for asset_id, asset_data in type_items.items():
                asset = Asset.from_dict(asset_data, asset_type=atype, asset_id=asset_id)
                lib._items[atype][asset_id] = asset
                if asset.serial > max_serial:
                    max_serial = asset.serial

        # New instance not yet shared — _serial_counter write is safe
        # without the lock.
        lib._serial_counter = max_serial + 1
        return lib

    # ── Magic ────────────────────────────────────────────────────────

    def __len__(self) -> int:
        """Total number of assets across all types."""
        with self._lock:
            return sum(len(items) for items in self._items.values())

    def __contains__(self, key: tuple[AssetType, str]) -> bool:
        """``(asset_type, asset_id) in library``."""
        atype, aid = key
        with self._lock:
            return aid in self._items.get(atype, {})

    # ── Internal ─────────────────────────────────────────────────────

    def _require(self, asset_type: AssetType, asset_id: str) -> Asset:
        """Fetch an asset or raise ValueError if not found."""
        type_items = self._items.get(asset_type)
        if type_items is None or asset_id not in type_items:
            raise ValueError(
                f"Asset not found: {asset_type.value}/{asset_id}"
            )
        return type_items[asset_id]

    def _to_save_dict(self) -> dict:
        """Build the JSON-serializable dict.  (design.md §9)."""
        items: dict[str, dict[str, dict]] = {}
        for atype, type_items in self._items.items():
            items[atype.value] = {
                aid: asset.to_dict() for aid, asset in type_items.items()
            }
        return {"version": self.VERSION, "items": items}

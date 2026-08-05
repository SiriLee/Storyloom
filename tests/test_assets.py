"""Tests for the asset database layer — AssetType, Asset, AssetItem.

Per design.md §2: Asset data model — three-layer abstraction.
TDD: these tests define the contract before implementation exists.
"""

import json
import uuid

import pytest

from storyloom.assets import Asset, AssetItem, AssetType


# ═══════════════════════════════════════════════════════════════════
# AssetType
# ═══════════════════════════════════════════════════════════════════

class TestAssetType:
    """AssetType enum — values, properties."""

    def test_char_portrait_value(self):
        """CHAR_PORTRAIT string value is 'char_portrait' (§2.2)."""
        assert AssetType.CHAR_PORTRAIT.value == "char_portrait"

    def test_background_value(self):
        """BACKGROUND string value is 'background_img' (§2.2)."""
        assert AssetType.BACKGROUND.value == "background_img"

    def test_default_extension_char_portrait(self):
        """CHAR_PORTRAIT default extension is '.png' (§2.2)."""
        assert AssetType.CHAR_PORTRAIT.default_extension == ".png"

    def test_default_extension_background(self):
        """BACKGROUND default extension is '.png' (§2.2)."""
        assert AssetType.BACKGROUND.default_extension == ".png"

    def test_members_are_two(self):
        """Only CHAR_PORTRAIT and BACKGROUND are defined (D15)."""
        members = list(AssetType)
        assert len(members) == 2
        names = {m.name for m in members}
        assert names == {"CHAR_PORTRAIT", "BACKGROUND"}


# ═══════════════════════════════════════════════════════════════════
# Asset
# ═══════════════════════════════════════════════════════════════════

class TestAsset:
    """Asset dataclass — fields, file_path, serialization, equality."""

    # ── Construction ──

    def test_construction_with_all_fields(self):
        """All fields accepted at construction."""
        a = Asset(
            asset_type=AssetType.CHAR_PORTRAIT,
            id="abc123",
            name="Hero",
            description="A brave hero in armor.",
            use_count=3,
            serial=7,
        )
        assert a.asset_type == AssetType.CHAR_PORTRAIT
        assert a.id == "abc123"
        assert a.name == "Hero"
        assert a.description == "A brave hero in armor."
        assert a.use_count == 3
        assert a.serial == 7

    def test_defaults(self):
        """description, use_count, serial have sensible defaults."""
        a = Asset(asset_type=AssetType.BACKGROUND, id="bg001", name="Forest")
        assert a.description == ""
        assert a.use_count == 0
        assert a.serial == -1  # unset by Library

    # ── file_path ──

    def test_file_path_char_portrait(self):
        """file_path: '{type}/{id}{ext}' (§2.2, D19)."""
        a = Asset(asset_type=AssetType.CHAR_PORTRAIT, id="abc123", name="Hero")
        assert a.file_path == "char_portrait/abc123.png"

    def test_file_path_background(self):
        """file_path uses correct directory name for BACKGROUND."""
        a = Asset(asset_type=AssetType.BACKGROUND, id="bg456", name="Tavern")
        assert a.file_path == "background_img/bg456.png"

    # ── to_dict / from_dict round-trip ──

    def test_to_dict_all_fields(self):
        """to_dict produces all specified keys (§9)."""
        a = Asset(
            asset_type=AssetType.CHAR_PORTRAIT,
            id="abc123",
            name="Hero",
            description="Brave.",
            use_count=2,
            serial=5,
        )
        d = a.to_dict()
        # asset_type is NOT in the dict — it's the key in _asset_lib.json structure
        assert d == {
            "name": "Hero",
            "description": "Brave.",
            "use_count": 2,
            "serial": 5,
        }

    def test_to_dict_defaults(self):
        """to_dict with default values."""
        a = Asset(asset_type=AssetType.BACKGROUND, id="bg001", name="Forest")
        d = a.to_dict()
        assert d["name"] == "Forest"
        assert d["description"] == ""
        assert d["use_count"] == 0
        assert d["serial"] == -1

    def test_from_dict_full(self):
        """from_dict reconstructs from complete dict."""
        data = {"name": "Hero", "description": "Brave.", "use_count": 2, "serial": 5}
        a = Asset.from_dict(data, asset_type=AssetType.CHAR_PORTRAIT, asset_id="abc123")
        assert a.asset_type == AssetType.CHAR_PORTRAIT
        assert a.id == "abc123"
        assert a.name == "Hero"
        assert a.description == "Brave."
        assert a.use_count == 2
        assert a.serial == 5

    def test_from_dict_minimal(self):
        """from_dict with missing optional fields uses defaults."""
        data = {"name": "Forest"}
        a = Asset.from_dict(data, asset_type=AssetType.BACKGROUND, asset_id="bg001")
        assert a.name == "Forest"
        assert a.description == ""
        assert a.use_count == 0
        assert a.serial == -1

    def test_round_trip(self):
        """to_dict → from_dict is lossless (excluding asset_type/id which are structural keys)."""
        original = Asset(
            asset_type=AssetType.CHAR_PORTRAIT,
            id="abc123",
            name="Hero",
            description="A warrior.",
            use_count=4,
            serial=10,
        )
        data = original.to_dict()
        restored = Asset.from_dict(data, asset_type=original.asset_type, asset_id=original.id)
        assert restored == original
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.use_count == original.use_count
        assert restored.serial == original.serial

    # ── Equality ──

    def test_eq_same_identity(self):
        """Two Assets with same (type, id) are equal regardless of mutable fields (D49)."""
        a1 = Asset(AssetType.CHAR_PORTRAIT, "abc123", "Hero", use_count=1, serial=1)
        a2 = Asset(AssetType.CHAR_PORTRAIT, "abc123", "Renamed", use_count=99, serial=99)
        assert a1 == a2

    def test_eq_different_id(self):
        """Different ids → not equal."""
        a1 = Asset(AssetType.CHAR_PORTRAIT, "abc123", "Hero")
        a2 = Asset(AssetType.CHAR_PORTRAIT, "xyz789", "Hero")
        assert a1 != a2

    def test_eq_different_type(self):
        """Different types → not equal even with same id."""
        a1 = Asset(AssetType.CHAR_PORTRAIT, "abc123", "Hero")
        a2 = Asset(AssetType.BACKGROUND, "abc123", "Hero")
        assert a1 != a2

    def test_not_equal_to_none(self):
        """Asset is not equal to None."""
        a = Asset(AssetType.CHAR_PORTRAIT, "abc123", "Hero")
        assert a != None  # noqa: E711

    def test_not_equal_to_other_type(self):
        """Asset is not equal to unrelated types."""
        a = Asset(AssetType.CHAR_PORTRAIT, "abc123", "Hero")
        assert a != "abc123"

    # ── Mutable fields ──

    def test_use_count_mutable(self):
        """use_count is mutable — can be incremented in-place (D31)."""
        a = Asset(AssetType.CHAR_PORTRAIT, "abc123", "Hero")
        a.use_count += 1
        assert a.use_count == 1

    def test_description_mutable(self):
        """description can be updated after construction."""
        a = Asset(AssetType.CHAR_PORTRAIT, "abc123", "Hero")
        a.description = "Updated description."
        assert a.description == "Updated description."

    # ── JSON serialization ──

    def test_to_dict_is_json_serializable(self):
        """to_dict output can be serialized to JSON."""
        a = Asset(
            AssetType.CHAR_PORTRAIT, "abc123", "Hero",
            description="A hero with \"special\" powers.",
            use_count=2, serial=3,
        )
        encoded = json.dumps(a.to_dict(), ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["name"] == "Hero"
        assert decoded["use_count"] == 2

    def test_from_dict_preserves_unicode(self):
        """from_dict handles Unicode names and descriptions."""
        data = {"name": "神秘旅人", "description": "身披斗篷的陌生人", "use_count": 0, "serial": 1}
        a = Asset.from_dict(data, asset_type=AssetType.CHAR_PORTRAIT, asset_id="abc123")
        assert a.name == "神秘旅人"
        assert a.description == "身披斗篷的陌生人"


# ═══════════════════════════════════════════════════════════════════
# AssetItem
# ═══════════════════════════════════════════════════════════════════

class TestAssetItem:
    """AssetItem dataclass — fields, placeholder semantics, serialization, equality."""

    # ── Construction ──

    def test_construction_with_target(self):
        """Full construction with target set."""
        item = AssetItem(
            local_name="Hero",
            local_description="The main character.",
            target="abc123",
        )
        assert item.local_name == "Hero"
        assert item.local_description == "The main character."
        assert item.target == "abc123"

    def test_construction_placeholder(self):
        """target=None means placeholder — asset not yet generated (§2.3)."""
        item = AssetItem(local_name="Villain", target=None)
        assert item.target is None

    def test_defaults(self):
        """local_description defaults to empty string, target defaults to None."""
        item = AssetItem(local_name="Forest")
        assert item.local_description == ""
        assert item.target is None

    # ── to_dict / from_dict round-trip ──

    def test_to_dict_with_target(self):
        """to_dict serializes target as the asset id string."""
        item = AssetItem("Hero", "Brave warrior.", target="abc123")
        d = item.to_dict()
        assert d == {
            "local_description": "Brave warrior.",
            "target": "abc123",
        }

    def test_to_dict_placeholder(self):
        """to_dict serializes target=None as JSON null (§2.3, D36)."""
        item = AssetItem("Villain", target=None)
        d = item.to_dict()
        assert d["target"] is None

    def test_to_dict_default_description(self):
        """to_dict includes empty description."""
        item = AssetItem("Forest")
        d = item.to_dict()
        assert d["local_description"] == ""
        assert d["target"] is None

    def test_from_dict_full(self):
        """from_dict reconstructs from complete dict."""
        data = {"local_description": "Brave.", "target": "abc123"}
        item = AssetItem.from_dict("Hero", data)
        assert item.local_name == "Hero"
        assert item.local_description == "Brave."
        assert item.target == "abc123"

    def test_from_dict_minimal(self):
        """from_dict with empty dict uses defaults."""
        item = AssetItem.from_dict("Forest", {})
        assert item.local_name == "Forest"
        assert item.local_description == ""
        assert item.target is None

    def test_from_dict_null_target(self):
        """from_dict handles explicit null target."""
        data = {"local_description": "", "target": None}
        item = AssetItem.from_dict("Villain", data)
        assert item.target is None

    def test_round_trip(self):
        """to_dict → from_dict is lossless."""
        original = AssetItem("Hero", "Brave warrior.", target="abc123")
        data = original.to_dict()
        restored = AssetItem.from_dict(original.local_name, data)
        assert restored.local_name == original.local_name
        assert restored.local_description == original.local_description
        assert restored.target == original.target

    def test_round_trip_placeholder(self):
        """Round-trip preserves placeholder state."""
        original = AssetItem("Villain", target=None)
        data = original.to_dict()
        restored = AssetItem.from_dict(original.local_name, data)
        assert restored.target is None

    # ── Equality ──

    def test_eq_same_identity(self):
        """Two AssetItems with same (type, local_name) are equal, ignoring target (D49)."""
        # Note: type is not stored on AssetItem — it's the dict key in Roster.
        # At the AssetItem level, equality is by local_name.
        i1 = AssetItem("Hero", "Brave.", target="abc123")
        i2 = AssetItem("Hero", "Different.", target=None)
        assert i1 == i2  # equal by local_name

    def test_eq_different_name(self):
        """Different local_name → not equal."""
        i1 = AssetItem("Hero")
        i2 = AssetItem("Villain")
        assert i1 != i2

    def test_not_equal_to_none(self):
        """AssetItem is not equal to None."""
        item = AssetItem("Hero")
        assert item != None  # noqa: E711

    def test_not_equal_to_string(self):
        """AssetItem is not equal to its local_name string."""
        item = AssetItem("Hero")
        assert item != "Hero"

    # ── Mutable fields ──

    def test_target_mutable(self):
        """target is mutable — can be updated after construction (D31)."""
        item = AssetItem("Hero", target=None)
        item.target = "abc123"
        assert item.target == "abc123"

    def test_description_mutable(self):
        """local_description can be updated."""
        item = AssetItem("Hero")
        item.local_description = "Updated."
        assert item.local_description == "Updated."

    # ── JSON serialization ──

    def test_to_dict_is_json_serializable(self):
        """to_dict output can be serialized to JSON."""
        item = AssetItem("Hero", "A \"hero\" character.", target="abc123")
        encoded = json.dumps(item.to_dict(), ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["target"] == "abc123"

    def test_to_dict_null_is_json_null(self):
        """None target serializes as JSON null."""
        item = AssetItem("Villain", target=None)
        encoded = json.dumps(item.to_dict(), ensure_ascii=False)
        assert "null" in encoded

    def test_from_dict_preserves_unicode(self):
        """from_dict handles Unicode names and descriptions."""
        data = {"local_description": "身披斗篷的陌生人", "target": "abc123"}
        item = AssetItem.from_dict("神秘旅人", data)
        assert item.local_name == "神秘旅人"
        assert item.local_description == "身披斗篷的陌生人"


# ═══════════════════════════════════════════════════════════════════
# AssetLibrary
# ═══════════════════════════════════════════════════════════════════

import os
import tempfile
import threading
import time

from storyloom.assets import AssetLibrary

# Re-import for local clarity in AssetLibrary tests
from storyloom.assets import Asset, AssetItem, AssetType


# ── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def lib():
    """Fresh AssetLibrary with a temp media_dir."""
    with tempfile.TemporaryDirectory() as d:
        yield AssetLibrary(d)


@pytest.fixture
def media_dir():
    """Temp directory for persistence tests."""
    with tempfile.TemporaryDirectory() as d:
        yield d


def _make_asset(lib, atype=AssetType.CHAR_PORTRAIT, name="Hero",
                desc="Brave.", asset_id=None):
    """Helper: add an asset and return it."""
    return lib.add(atype, name, desc, asset_id=asset_id)


# ── Init ────────────────────────────────────────────────────────────

class TestAssetLibraryInit:
    """Construction and initial state."""

    def test_empty_on_creation(self, lib):
        """New library has zero assets."""
        assert len(lib) == 0
        assert lib.list_all() == []

    def test_media_dir_stored(self, lib):
        """media_dir is stored from constructor."""
        assert lib.media_dir is not None
        assert os.path.isdir(lib.media_dir)

    def test_version_constant(self):
        """VERSION is 1 (D14)."""
        assert AssetLibrary.VERSION == 1


# ── Add ─────────────────────────────────────────────────────────────

class TestAssetLibraryAdd:
    """AssetLibrary.add() — creation and validation."""

    def test_add_returns_asset(self, lib):
        """add() returns the created Asset."""
        a = lib.add(AssetType.CHAR_PORTRAIT, "Hero", "Brave warrior.")
        assert isinstance(a, Asset)
        assert a.asset_type == AssetType.CHAR_PORTRAIT
        assert a.name == "Hero"
        assert a.description == "Brave warrior."
        assert a.use_count == 0

    def test_add_auto_generates_id(self, lib):
        """If no asset_id is given, a UUID is generated (D4)."""
        a = lib.add(AssetType.BACKGROUND, "Forest")
        assert len(a.id) == 32  # uuid4().hex
        # Valid hex
        int(a.id, 16)

    def test_add_with_explicit_id(self, lib):
        """Explicit asset_id is accepted."""
        a = lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="custom_001")
        assert a.id == "custom_001"

    def test_add_increases_len(self, lib):
        """len() reflects added assets."""
        assert len(lib) == 0
        lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        assert len(lib) == 1
        lib.add(AssetType.BACKGROUND, "Forest")
        assert len(lib) == 2

    def test_add_assigns_serial(self, lib):
        """Each add gets a monotonically increasing serial (D43)."""
        a1 = lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        a2 = lib.add(AssetType.CHAR_PORTRAIT, "Villain")
        a3 = lib.add(AssetType.BACKGROUND, "Forest")
        assert a1.serial == 0
        assert a2.serial == 1
        assert a3.serial == 2

    def test_add_duplicate_id_raises(self, lib):
        """Adding with an existing id raises ValueError (D23)."""
        lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="dup")
        with pytest.raises(ValueError, match="already exists"):
            lib.add(AssetType.CHAR_PORTRAIT, "Another", asset_id="dup")

    def test_add_same_id_different_type_allowed(self, lib):
        """Same id in different AssetTypes is allowed."""
        lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="shared")
        a = lib.add(AssetType.BACKGROUND, "Forest", asset_id="shared")
        assert a.id == "shared"

    def test_add_default_description(self, lib):
        """Empty description when not provided."""
        a = lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        assert a.description == ""


# ── Get ─────────────────────────────────────────────────────────────

class TestAssetLibraryGet:
    """AssetLibrary.get() — single asset lookup."""

    def test_get_existing(self, lib):
        """get returns the Asset for a known (type, id)."""
        added = lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="abc")
        found = lib.get(AssetType.CHAR_PORTRAIT, "abc")
        assert found is added

    def test_get_missing(self, lib):
        """get returns None for unknown (type, id) (D46)."""
        assert lib.get(AssetType.CHAR_PORTRAIT, "nonexistent") is None

    def test_get_wrong_type(self, lib):
        """get returns None if the type doesn't match."""
        lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="abc")
        assert lib.get(AssetType.BACKGROUND, "abc") is None


# ── Remove ──────────────────────────────────────────────────────────

class TestAssetLibraryRemove:
    """AssetLibrary.remove() — deletion with use_count guard."""

    def test_remove_unused(self, lib):
        """Removing an asset with use_count==0 succeeds (D25)."""
        a = lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="abc")
        removed = lib.remove(AssetType.CHAR_PORTRAIT, "abc")
        assert removed is a
        assert len(lib) == 0
        assert lib.get(AssetType.CHAR_PORTRAIT, "abc") is None

    def test_remove_in_use_raises(self, lib):
        """Removing an asset with use_count>0 raises ValueError (D25)."""
        a = lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        lib.increase_usage(a.asset_type, a.id)
        with pytest.raises(ValueError, match="use_count"):
            lib.remove(a.asset_type, a.id)

    def test_remove_nonexistent_raises(self, lib):
        """Removing a nonexistent asset raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            lib.remove(AssetType.CHAR_PORTRAIT, "nonexistent")

    def test_remove_returns_asset(self, lib):
        """remove returns the removed Asset (D25)."""
        a = lib.add(AssetType.BACKGROUND, "Forest")
        removed = lib.remove(AssetType.BACKGROUND, a.id)
        assert removed.name == "Forest"


# ── Usage Count ─────────────────────────────────────────────────────

class TestAssetLibraryUsage:
    """increase_usage / decrease_usage — reference counting."""

    def test_increase_usage(self, lib):
        """increase_usage increments use_count."""
        a = lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        lib.increase_usage(a.asset_type, a.id)
        assert a.use_count == 1

    def test_increase_usage_multiple(self, lib):
        """Multiple increases accumulate."""
        a = lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        lib.increase_usage(a.asset_type, a.id)
        lib.increase_usage(a.asset_type, a.id)
        lib.increase_usage(a.asset_type, a.id)
        assert a.use_count == 3

    def test_decrease_usage(self, lib):
        """decrease_usage decrements use_count."""
        a = lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        lib.increase_usage(a.asset_type, a.id)
        lib.increase_usage(a.asset_type, a.id)
        lib.decrease_usage(a.asset_type, a.id)
        assert a.use_count == 1

    def test_decrease_usage_underflow_raises(self, lib):
        """decrease_usage below 0 raises ValueError (D24)."""
        a = lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        with pytest.raises(ValueError, match="use_count.*0"):
            lib.decrease_usage(a.asset_type, a.id)

    def test_increase_usage_nonexistent_raises(self, lib):
        """increase_usage on nonexistent asset raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            lib.increase_usage(AssetType.CHAR_PORTRAIT, "nonexistent")

    def test_decrease_usage_nonexistent_raises(self, lib):
        """decrease_usage on nonexistent asset raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            lib.decrease_usage(AssetType.CHAR_PORTRAIT, "nonexistent")


# ── List ────────────────────────────────────────────────────────────

class TestAssetLibraryList:
    """list_all / list_by_type — enumeration."""

    def test_list_all_empty(self, lib):
        """Empty library returns empty list."""
        assert lib.list_all() == []

    def test_list_all(self, lib):
        """list_all returns all assets across types."""
        a1 = lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        a2 = lib.add(AssetType.BACKGROUND, "Forest")
        all_assets = lib.list_all()
        assert len(all_assets) == 2
        assert a1 in all_assets
        assert a2 in all_assets

    def test_list_by_type(self, lib):
        """list_by_type returns only assets of the given type."""
        a1 = lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        a2 = lib.add(AssetType.CHAR_PORTRAIT, "Villain")
        lib.add(AssetType.BACKGROUND, "Forest")
        chars = lib.list_by_type(AssetType.CHAR_PORTRAIT)
        assert len(chars) == 2
        assert a1.id in chars
        assert a2.id in chars

    def test_list_by_type_returns_dict_copy(self, lib):
        """list_by_type returns a copy — mutation doesn't affect internals."""
        lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="abc")
        d = lib.list_by_type(AssetType.CHAR_PORTRAIT)
        d["new_key"] = Asset(AssetType.CHAR_PORTRAIT, "fake", "Fake")
        assert "new_key" not in lib.list_by_type(AssetType.CHAR_PORTRAIT)


# ── Contains ────────────────────────────────────────────────────────

class TestAssetLibraryContains:
    """__contains__ — membership test."""

    def test_contains_true(self, lib):
        """(type, id) returns True for existing asset."""
        a = lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="abc")
        assert (AssetType.CHAR_PORTRAIT, "abc") in lib

    def test_contains_false(self, lib):
        """(type, id) returns False when absent."""
        assert (AssetType.CHAR_PORTRAIT, "nonexistent") not in lib

    def test_contains_wrong_type(self, lib):
        """(wrong_type, id) returns False."""
        lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="abc")
        assert (AssetType.BACKGROUND, "abc") not in lib


# ── Sorted By Usage ─────────────────────────────────────────────────

class TestAssetLibrarySorted:
    """get_sorted_by_usage — top-N query with heap (D51)."""

    def test_empty_returns_empty(self, lib):
        """Empty library returns empty list."""
        result = lib.get_sorted_by_usage(AssetType.CHAR_PORTRAIT, 5)
        assert result == []

    def test_top_n_smaller_than_total(self, lib):
        """Returns at most top_n results."""
        for name in ["A", "B", "C", "D", "E"]:
            lib.add(AssetType.CHAR_PORTRAIT, name)
        result = lib.get_sorted_by_usage(AssetType.CHAR_PORTRAIT, 3)
        assert len(result) == 3

    def test_top_n_larger_than_total(self, lib):
        """Returns all when top_n > count."""
        for name in ["A", "B"]:
            lib.add(AssetType.CHAR_PORTRAIT, name)
        result = lib.get_sorted_by_usage(AssetType.CHAR_PORTRAIT, 10)
        assert len(result) == 2

    def test_sorted_by_usage_desc(self, lib):
        """Results are sorted by use_count descending."""
        a1 = lib.add(AssetType.CHAR_PORTRAIT, "Low")
        a2 = lib.add(AssetType.CHAR_PORTRAIT, "Med")
        a3 = lib.add(AssetType.CHAR_PORTRAIT, "High")
        lib.increase_usage(a3.asset_type, a3.id)
        lib.increase_usage(a3.asset_type, a3.id)
        lib.increase_usage(a2.asset_type, a2.id)
        # usage: a3=2, a2=1, a1=0
        result = lib.get_sorted_by_usage(AssetType.CHAR_PORTRAIT, 3)
        assert result[0].name == "High"
        assert result[1].name == "Med"
        assert result[2].name == "Low"

    def test_tiebreaker_by_serial(self, lib):
        """Same use_count: higher serial (more recent) first (D10)."""
        a1 = lib.add(AssetType.CHAR_PORTRAIT, "Older")
        a2 = lib.add(AssetType.CHAR_PORTRAIT, "Newer")
        # Both use_count=0, a2.serial > a1.serial
        result = lib.get_sorted_by_usage(AssetType.CHAR_PORTRAIT, 2)
        assert result[0].name == "Newer"
        assert result[1].name == "Older"

    def test_only_matching_type(self, lib):
        """Only assets of the specified type are returned."""
        lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        lib.add(AssetType.BACKGROUND, "Forest")
        result = lib.get_sorted_by_usage(AssetType.CHAR_PORTRAIT, 10)
        assert len(result) == 1
        assert result[0].name == "Hero"


# ── Clean ───────────────────────────────────────────────────────────

class TestAssetLibraryClean:
    """clean(keep_count) — retention with use_count protection (D45)."""

    def test_keep_count_protects_in_use(self, lib):
        """use_count>0 assets are never deleted, even if total > keep_count."""
        a1 = lib.add(AssetType.CHAR_PORTRAIT, "Unused1")
        a2 = lib.add(AssetType.CHAR_PORTRAIT, "Unused2")
        used = lib.add(AssetType.CHAR_PORTRAIT, "Used")
        lib.increase_usage(used.asset_type, used.id)
        # 3 total, keep_count=1, but 1 is protected → all unused deleted
        deleted = lib.clean(keep_count=1)
        assert deleted == 2
        assert lib.get(used.asset_type, used.id) is not None
        assert a1.id not in lib.list_by_type(AssetType.CHAR_PORTRAIT)
        assert a2.id not in lib.list_by_type(AssetType.CHAR_PORTRAIT)

    def test_keep_count_preserves_recent_unused(self, lib):
        """Among use_count==0 assets, keep the most recent ones (by serial)."""
        a1 = lib.add(AssetType.CHAR_PORTRAIT, "Oldest")
        a2 = lib.add(AssetType.CHAR_PORTRAIT, "Middle")
        a3 = lib.add(AssetType.CHAR_PORTRAIT, "Newest")
        # 3 unused, keep_count=2
        deleted = lib.clean(keep_count=2)
        assert deleted == 1
        # a1 (serial=0) should be removed; a2(1), a3(2) kept
        assert lib.get(AssetType.CHAR_PORTRAIT, a1.id) is None
        assert lib.get(AssetType.CHAR_PORTRAIT, a2.id) is not None
        assert lib.get(AssetType.CHAR_PORTRAIT, a3.id) is not None

    def test_clean_returns_zero_when_nothing_to_delete(self, lib):
        """Returns 0 when all use_count>0 or within keep_count."""
        lib.add(AssetType.CHAR_PORTRAIT, "Only")
        deleted = lib.clean(keep_count=10)
        assert deleted == 0

    def test_clean_zero_keep_count(self, lib):
        """keep_count=0 deletes all use_count==0 assets."""
        for name in ["A", "B"]:
            lib.add(AssetType.CHAR_PORTRAIT, name)
        deleted = lib.clean(keep_count=0)
        assert deleted == 2
        assert len(lib) == 0

    def test_clean_all_in_use_nothing_deleted(self, lib):
        """When all assets have use_count>0, nothing is deleted."""
        for i in range(5):
            a = lib.add(AssetType.CHAR_PORTRAIT, f"Char{i}")
            lib.increase_usage(a.asset_type, a.id)
        deleted = lib.clean(keep_count=1)
        assert deleted == 0
        assert len(lib) == 5

    def test_clean_mixed_types(self, lib):
        """clean operates across all types, not just one."""
        a1 = lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        a2 = lib.add(AssetType.BACKGROUND, "Forest")
        # keep_count=1 → keep the newest (a2, serial=1), delete a1
        deleted = lib.clean(keep_count=1)
        assert deleted == 1
        assert lib.get(AssetType.BACKGROUND, a2.id) is not None
        assert lib.get(AssetType.CHAR_PORTRAIT, a1.id) is None

    def test_clean_returns_int(self, lib):
        """clean returns the number of deleted assets."""
        lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        result = lib.clean(keep_count=0)
        assert isinstance(result, int)
        assert result == 1


# ── Persistence ─────────────────────────────────────────────────────

class TestAssetLibraryPersistence:
    """save() / load() — JSON round-trip (design.md §9)."""

    def test_save_creates_file(self, media_dir):
        """save() writes _asset_lib.json to media_dir."""
        lib = AssetLibrary(media_dir)
        lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="abc")
        lib.save()
        expected = os.path.join(media_dir, "_asset_lib.json")
        assert os.path.isfile(expected)

    def test_load_round_trip(self, media_dir):
        """save → load is lossless."""
        lib1 = AssetLibrary(media_dir)
        a1 = lib1.add(AssetType.CHAR_PORTRAIT, "Hero", "Brave.", asset_id="abc")
        lib1.increase_usage(a1.asset_type, a1.id)
        lib1.add(AssetType.BACKGROUND, "Forest", "Dark woods.", asset_id="bg1")
        lib1.save()

        lib2 = AssetLibrary.load(media_dir)
        assert len(lib2) == 2
        restored = lib2.get(AssetType.CHAR_PORTRAIT, "abc")
        assert restored is not None
        assert restored.name == "Hero"
        assert restored.description == "Brave."
        assert restored.use_count == 1
        assert restored.serial == 0
        bg = lib2.get(AssetType.BACKGROUND, "bg1")
        assert bg.name == "Forest"
        assert bg.serial == 1

    def test_load_restores_serial_counter(self, media_dir):
        """After load, new assets get serials > the max from the saved file."""
        lib1 = AssetLibrary(media_dir)
        lib1.add(AssetType.CHAR_PORTRAIT, "Hero")
        lib1.save()

        lib2 = AssetLibrary.load(media_dir)
        a2 = lib2.add(AssetType.CHAR_PORTRAIT, "Villain")
        # Serial counter should have resumed after the last saved serial (0)
        assert a2.serial == 1

    def test_load_nonexistent_returns_empty(self, media_dir):
        """Loading from a nonexistent file returns an empty Library (D41)."""
        lib = AssetLibrary.load(media_dir)
        assert len(lib) == 0
        assert lib.media_dir == media_dir

    def test_save_atomic_no_tmp_left(self, media_dir):
        """Atomic write: no .tmp file remains after save (D16)."""
        lib = AssetLibrary(media_dir)
        lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        lib.save()
        tmp_files = [f for f in os.listdir(media_dir) if f.endswith(".tmp")]
        assert len(tmp_files) == 0

    def test_save_empty_library(self, media_dir):
        """Saving an empty library produces valid JSON (D34)."""
        lib = AssetLibrary(media_dir)
        lib.save()
        lib2 = AssetLibrary.load(media_dir)
        assert len(lib2) == 0

    def test_save_preserves_unicode(self, media_dir):
        """Unicode names/descriptions survive save/load round-trip."""
        lib = AssetLibrary(media_dir)
        lib.add(AssetType.CHAR_PORTRAIT, "神秘旅人", "身披斗篷的陌生人", asset_id="abc")
        lib.save()
        lib2 = AssetLibrary.load(media_dir)
        a = lib2.get(AssetType.CHAR_PORTRAIT, "abc")
        assert a.name == "神秘旅人"
        assert a.description == "身披斗篷的陌生人"

    def test_load_version_mismatch_raises(self, media_dir):
        """Loading a file with wrong version raises ValueError (D42)."""
        import json
        bad_path = os.path.join(media_dir, "_asset_lib.json")
        with open(bad_path, "w") as f:
            json.dump({"version": 999, "items": {}}, f)
        with pytest.raises(ValueError, match="version"):
            AssetLibrary.load(media_dir)

    def test_save_json_structure(self, media_dir):
        """Saved JSON matches the structure in design.md §9 (D5)."""
        lib = AssetLibrary(media_dir)
        lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="abc")
        lib.save()

        import json
        with open(os.path.join(media_dir, "_asset_lib.json")) as f:
            data = json.load(f)
        assert data["version"] == 1
        assert "items" in data
        assert "char_portrait" in data["items"]
        assert "abc" in data["items"]["char_portrait"]
        item = data["items"]["char_portrait"]["abc"]
        assert item["name"] == "Hero"
        assert "use_count" in item
        assert "serial" in item

    def test_load_preserves_media_dir(self, media_dir):
        """load() associates the library with the correct media_dir."""
        lib = AssetLibrary(media_dir)
        lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        lib.save()
        lib2 = AssetLibrary.load(media_dir)
        assert lib2.media_dir == media_dir

    def test_load_corrupt_json_raises(self, media_dir):
        """Loading corrupt JSON raises ValueError."""
        bad_path = os.path.join(media_dir, "_asset_lib.json")
        with open(bad_path, "w") as f:
            f.write("not json {{{")
        with pytest.raises(ValueError, match="corrupt"):
            AssetLibrary.load(media_dir)


# ── Thread Safety ───────────────────────────────────────────────────

class TestAssetLibraryThreadSafety:
    """Concurrent access — lock protects shared state (D18)."""

    def _concurrent_add(self, lib, atype, names, results_holder, barrier):
        """Worker: add several assets."""
        barrier.wait()  # synchronize start
        for name in names:
            results_holder.append(lib.add(atype, name))

    def test_concurrent_adds_no_corruption(self, lib):
        """Concurrent add() calls produce consistent state."""
        barrier = threading.Barrier(4)
        results: list[Asset] = []
        threads = [
            threading.Thread(target=self._concurrent_add,
                             args=(lib, AssetType.CHAR_PORTRAIT,
                                   [f"Hero_{i}"], results, barrier))
            for i in range(4)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 4 adds should succeed
        assert len(results) == 4
        assert len(lib) == 4
        # All serials should be unique
        serials = {a.serial for a in results}
        assert len(serials) == 4

    def test_concurrent_increase_usage(self, lib):
        """Concurrent increase_usage produces correct final count."""
        a = lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        N = 100

        def worker():
            for _ in range(N):
                lib.increase_usage(a.asset_type, a.id)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert a.use_count == N * 4

    def test_concurrent_read_write_no_crash(self, lib):
        """Concurrent reads and writes don't crash or corrupt."""
        lib.add(AssetType.CHAR_PORTRAIT, "Initial", asset_id="init")

        errors = []
        barrier = threading.Barrier(3)

        def writer():
            barrier.wait()
            try:
                for i in range(50):
                    lib.add(AssetType.CHAR_PORTRAIT, f"Writer_{i}")
            except Exception as e:
                errors.append(("writer", e))

        def reader():
            barrier.wait()
            try:
                for _ in range(100):
                    _ = lib.get(AssetType.CHAR_PORTRAIT, "init")
                    _ = len(lib)
                    _ = lib.list_all()
            except Exception as e:
                errors.append(("reader", e))

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=writer)
        t3 = threading.Thread(target=reader)
        for t in [t1, t2, t3]:
            t.start()
        for t in [t1, t2, t3]:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(lib) == 101  # 1 initial + 50*2 writers


# ═══════════════════════════════════════════════════════════════════
# GameAssetRoster
# ═══════════════════════════════════════════════════════════════════

from storyloom.assets import GameAssetRoster


# ── Fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def roster_lib():
    """AssetLibrary for Roster tests (per-rost test isolation)."""
    with tempfile.TemporaryDirectory() as d:
        yield AssetLibrary(d)


@pytest.fixture
def roster(roster_lib):
    """Fresh GameAssetRoster with an injected AssetLibrary."""
    return GameAssetRoster("test-game", roster_lib)


# ── Init ────────────────────────────────────────────────────────────

class TestRosterInit:
    """Construction and initial state."""

    def test_empty_on_creation(self, roster):
        """New roster has zero entries."""
        assert len(roster) == 0

    def test_game_id_stored(self, roster):
        """game_id is stored from constructor (D7)."""
        assert roster.game_id == "test-game"

    def test_version_constant(self):
        """VERSION is 1 (D14)."""
        assert GameAssetRoster.VERSION == 1


# ── Add ─────────────────────────────────────────────────────────────

class TestRosterAdd:
    """GameAssetRoster.add() — creation + Library use_count coordination."""

    def test_add_returns_item(self, roster):
        """add() returns the created AssetItem."""
        item = roster.add(AssetType.CHAR_PORTRAIT, "Hero", "Brave.")
        assert isinstance(item, AssetItem)
        assert item.local_name == "Hero"
        assert item.local_description == "Brave."
        assert item.target is None

    def test_add_increases_len(self, roster):
        """len() reflects added entries."""
        assert len(roster) == 0
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        assert len(roster) == 1

    def test_add_duplicate_raises(self, roster):
        """Same (type, local_name) raises ValueError (D23)."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        with pytest.raises(ValueError, match="already exists"):
            roster.add(AssetType.CHAR_PORTRAIT, "Hero")

    def test_add_with_target_increases_usage(self, roster, roster_lib):
        """target非空时调用 library.increase_usage (D38)."""
        asset = roster_lib.add(AssetType.CHAR_PORTRAIT, "HeroAsset")
        assert asset.use_count == 0
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=asset.id)
        assert asset.use_count == 1

    def test_add_placeholder_no_usage_change(self, roster, roster_lib):
        """target=None → no increase_usage (placeholder)."""
        asset = roster_lib.add(AssetType.CHAR_PORTRAIT, "HeroAsset")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=None)
        assert asset.use_count == 0

    def test_add_different_types_same_name(self, roster):
        """Same local_name in different AssetTypes is allowed."""
        roster.add(AssetType.CHAR_PORTRAIT, "Forest")
        item = roster.add(AssetType.BACKGROUND, "Forest")
        assert item.local_name == "Forest"


# ── Set Target ──────────────────────────────────────────────────────

class TestRosterSetTarget:
    """set_target — swap old target for new, update use_counts (D20)."""

    def test_set_target_updates_ref(self, roster, roster_lib):
        """set_target changes the target reference."""
        asset = roster_lib.add(AssetType.CHAR_PORTRAIT, "SomeAsset")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        roster.set_target(AssetType.CHAR_PORTRAIT, "Hero", asset.id)
        item = roster.lookup(AssetType.CHAR_PORTRAIT, "Hero")
        assert item.target == asset.id

    def test_set_target_old_decrease_new_increase(self, roster, roster_lib):
        """Old target decrease_usage, new target increase_usage."""
        old = roster_lib.add(AssetType.CHAR_PORTRAIT, "OldAsset")
        new = roster_lib.add(AssetType.CHAR_PORTRAIT, "NewAsset")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=old.id)
        assert old.use_count == 1
        assert new.use_count == 0

        roster.set_target(AssetType.CHAR_PORTRAIT, "Hero", new.id)
        assert old.use_count == 0
        assert new.use_count == 1

    def test_set_target_from_placeholder(self, roster, roster_lib):
        """Placeholder (target=None) → real target: only increase new."""
        new = roster_lib.add(AssetType.CHAR_PORTRAIT, "NewAsset")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=None)
        roster.set_target(AssetType.CHAR_PORTRAIT, "Hero", new.id)
        assert new.use_count == 1

    def test_set_target_to_placeholder_allowed(self, roster, roster_lib):
        """Real target → None: old decrease, no new increase."""
        old = roster_lib.add(AssetType.CHAR_PORTRAIT, "OldAsset")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=old.id)
        assert old.use_count == 1
        roster.set_target(AssetType.CHAR_PORTRAIT, "Hero", None)
        assert old.use_count == 0

    def test_set_target_nonexistent_raises(self, roster):
        """set_target on a nonexistent entry raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            roster.set_target(AssetType.CHAR_PORTRAIT, "NoSuch", "any_id")


# ── Remove ──────────────────────────────────────────────────────────

class TestRosterRemove:
    """remove — delete entry + decrease_usage (D48)."""

    def test_remove_decreases_usage(self, roster, roster_lib):
        """remove calls decrease_usage on the target asset."""
        asset = roster_lib.add(AssetType.CHAR_PORTRAIT, "HeroAsset")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=asset.id)
        assert asset.use_count == 1
        roster.remove(AssetType.CHAR_PORTRAIT, "Hero")
        assert asset.use_count == 0

    def test_remove_placeholder_no_error(self, roster):
        """Removing a placeholder (target=None) does not crash."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=None)
        roster.remove(AssetType.CHAR_PORTRAIT, "Hero")
        assert len(roster) == 0

    def test_remove_nonexistent_raises(self, roster):
        """remove on nonexistent entry raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            roster.remove(AssetType.CHAR_PORTRAIT, "NoSuch")

    def test_remove_removes_from_len(self, roster):
        """remove reduces len()."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        assert len(roster) == 1
        roster.remove(AssetType.CHAR_PORTRAIT, "Hero")
        assert len(roster) == 0


# ── Lookup ───────────────────────────────────────────────────────────

class TestRosterLookup:
    """lookup — exact string match (D9)."""

    def test_lookup_exact_match(self, roster):
        """lookup returns AssetItem for exact local_name."""
        added = roster.add(AssetType.CHAR_PORTRAIT, "Hero", "Brave.")
        found = roster.lookup(AssetType.CHAR_PORTRAIT, "Hero")
        assert found is added

    def test_lookup_not_found(self, roster):
        """lookup returns None when not found."""
        assert roster.lookup(AssetType.CHAR_PORTRAIT, "NoSuch") is None

    def test_lookup_wrong_type(self, roster):
        """lookup in wrong type returns None."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        assert roster.lookup(AssetType.BACKGROUND, "Hero") is None

    def test_lookup_case_sensitive(self, roster):
        """lookup is case-sensitive (exact string match)."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        assert roster.lookup(AssetType.CHAR_PORTRAIT, "hero") is None


# ── Clear ───────────────────────────────────────────────────────────

class TestRosterClear:
    """clear — all entries removed, all use_counts decreased (D48)."""

    def test_clear_decreases_all(self, roster, roster_lib):
        """clear decreases usage for all target entries."""
        a1 = roster_lib.add(AssetType.CHAR_PORTRAIT, "Asset1")
        a2 = roster_lib.add(AssetType.CHAR_PORTRAIT, "Asset2")
        a3 = roster_lib.add(AssetType.BACKGROUND, "BgAsset")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=a1.id)
        roster.add(AssetType.CHAR_PORTRAIT, "Villain", target=a2.id)
        roster.add(AssetType.BACKGROUND, "Forest", target=a3.id)
        assert a1.use_count == 1
        assert a2.use_count == 1
        assert a3.use_count == 1

        roster.clear()
        assert a1.use_count == 0
        assert a2.use_count == 0
        assert a3.use_count == 0

    def test_clear_empties_roster(self, roster):
        """clear removes all entries."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        roster.add(AssetType.BACKGROUND, "Forest")
        roster.clear()
        assert len(roster) == 0

    def test_clear_empty_no_error(self, roster):
        """clear on empty roster is a no-op."""
        roster.clear()  # should not raise

    def test_clear_handles_placeholders(self, roster, roster_lib):
        """clear handles mix of real targets and None."""
        asset = roster_lib.add(AssetType.CHAR_PORTRAIT, "Real")
        roster.add(AssetType.CHAR_PORTRAIT, "WithTarget", target=asset.id)
        roster.add(AssetType.CHAR_PORTRAIT, "Placeholder", target=None)
        roster.clear()
        assert asset.use_count == 0
        assert len(roster) == 0


# ── List ─────────────────────────────────────────────────────────────

class TestRosterList:
    """list_by_type — enumeration."""

    def test_list_empty(self, roster):
        """Empty roster returns empty dict."""
        assert roster.list_by_type(AssetType.CHAR_PORTRAIT) == {}

    def test_list_by_type(self, roster):
        """Returns items only for the given type."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        roster.add(AssetType.CHAR_PORTRAIT, "Villain")
        roster.add(AssetType.BACKGROUND, "Forest")
        result = roster.list_by_type(AssetType.CHAR_PORTRAIT)
        assert len(result) == 2
        assert "Hero" in result
        assert "Villain" in result

    def test_list_returns_copy(self, roster):
        """Returns a copy — mutation doesn't affect internals."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        d = roster.list_by_type(AssetType.CHAR_PORTRAIT)
        d["new"] = AssetItem("fake")
        assert "new" not in roster.list_by_type(AssetType.CHAR_PORTRAIT)


# ── Contains ────────────────────────────────────────────────────────

class TestRosterContains:
    """__contains__ — membership test."""

    def test_contains_true(self, roster):
        """(type, local_name) in roster."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        assert (AssetType.CHAR_PORTRAIT, "Hero") in roster

    def test_contains_false(self, roster):
        """(type, local_name) not in roster."""
        assert (AssetType.CHAR_PORTRAIT, "NoSuch") not in roster


# ── Persistence ─────────────────────────────────────────────────────

class TestRosterPersistence:
    """save() / load() — JSON round-trip (design.md §9)."""

    def test_save_load_round_trip(self, roster, roster_lib, tmp_path):
        """save → load is lossless."""
        asset = roster_lib.add(AssetType.CHAR_PORTRAIT, "HeroAsset")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", "Brave.", target=asset.id)
        roster.add(AssetType.BACKGROUND, "Forest", target=None)

        filepath = str(tmp_path / "_asset_roster.json")
        roster.save(filepath)

        loaded = GameAssetRoster.load(filepath, roster_lib, game_id="test-game")
        assert loaded.game_id == "test-game"
        assert len(loaded) == 2
        item = loaded.lookup(AssetType.CHAR_PORTRAIT, "Hero")
        assert item is not None
        assert item.local_description == "Brave."
        assert item.target == asset.id

        fg_item = loaded.lookup(AssetType.BACKGROUND, "Forest")
        assert fg_item is not None
        assert fg_item.target is None

    def test_load_nonexistent_returns_empty(self, roster_lib, tmp_path):
        """Loading a nonexistent file returns an empty roster (D41)."""
        filepath = str(tmp_path / "nonexistent.json")
        loaded = GameAssetRoster.load(filepath, roster_lib, game_id="test-game")
        assert len(loaded) == 0
        assert loaded.game_id == "test-game"

    def test_save_atomic_no_tmp_left(self, roster, tmp_path):
        """Atomic write: no .tmp remains (D16)."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        filepath = str(tmp_path / "_asset_roster.json")
        roster.save(filepath)
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert len(tmp_files) == 0

    def test_save_preserves_unicode(self, roster, tmp_path):
        """Unicode names survive save/load."""
        roster.add(AssetType.CHAR_PORTRAIT, "神秘旅人", "身披斗篷")
        filepath = str(tmp_path / "_asset_roster.json")
        roster.save(filepath)
        loaded = GameAssetRoster.load(filepath, roster._library, game_id="test-game")
        item = loaded.lookup(AssetType.CHAR_PORTRAIT, "神秘旅人")
        assert item is not None
        assert item.local_description == "身披斗篷"

    def test_load_version_mismatch_raises(self, roster_lib, tmp_path):
        """Loading wrong version raises ValueError (D42)."""
        filepath = str(tmp_path / "bad.json")
        with open(filepath, "w") as f:
            json.dump({"version": 999, "game_id": "test", "items": {}}, f)
        with pytest.raises(ValueError, match="version"):
            GameAssetRoster.load(filepath, roster_lib, game_id="test-game")

    def test_save_json_structure(self, roster, roster_lib, tmp_path):
        """Saved JSON matches design.md §9 structure."""
        asset = roster_lib.add(AssetType.CHAR_PORTRAIT, "SomeAsset", asset_id="abc123")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=asset.id)
        filepath = str(tmp_path / "_asset_roster.json")
        roster.save(filepath)
        with open(filepath) as f:
            data = json.load(f)
        assert data["version"] == 1
        assert data["game_id"] == "test-game"
        assert "char_portrait" in data["items"]
        assert "Hero" in data["items"]["char_portrait"]
        entry = data["items"]["char_portrait"]["Hero"]
        assert entry["target"] == "abc123"

    def test_load_corrupt_json_raises(self, roster_lib, tmp_path):
        """Loading corrupt JSON raises ValueError."""
        bad_path = str(tmp_path / "bad.json")
        with open(bad_path, "w") as f:
            f.write("{{{bad")
        with pytest.raises(ValueError, match="corrupt"):
            GameAssetRoster.load(bad_path, roster_lib, game_id="test-game")

    def test_load_reassociates_library(self, roster, roster_lib, tmp_path):
        """loaded roster's _library is the passed-in library."""
        asset = roster_lib.add(AssetType.CHAR_PORTRAIT, "Asset")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=asset.id)
        filepath = str(tmp_path / "_asset_roster.json")
        roster.save(filepath)

        loaded = GameAssetRoster.load(filepath, roster_lib, game_id="test-game")
        assert loaded._library is roster_lib


# ── Thread Safety ───────────────────────────────────────────────────

class TestRosterThreadSafety:
    """Concurrent access to Roster (D18)."""

    def test_concurrent_add_lookup(self, roster):
        """Concurrent add and lookup don't crash or corrupt."""
        errors = []
        barrier = threading.Barrier(3)

        def adder(start):
            barrier.wait()
            try:
                for i in range(start, start + 50):
                    roster.add(AssetType.CHAR_PORTRAIT, f"Char_{i}")
            except Exception as e:
                errors.append(("adder", e))

        def looker():
            barrier.wait()
            try:
                for _ in range(100):
                    _ = roster.lookup(AssetType.CHAR_PORTRAIT, "nonexistent")
                    _ = len(roster)
            except Exception as e:
                errors.append(("looker", e))

        threads = [
            threading.Thread(target=adder, args=(0,)),
            threading.Thread(target=adder, args=(50,)),
            threading.Thread(target=looker),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        assert len(roster) == 100  # 50 * 2 adders

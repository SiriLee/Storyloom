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
        """None target serializes as JSON null (§2.3, D36)."""
        item = AssetItem("Villain", target=None)
        encoded = json.dumps(item.to_dict(), ensure_ascii=False)
        decoded = json.loads(encoded)
        assert decoded["target"] is None

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

    def test_add_rejects_path_traversal_id(self, lib):
        """asset_id with path separators raises ValueError."""
        with pytest.raises(ValueError, match="asset_id"):
            lib.add(AssetType.CHAR_PORTRAIT, "Evil", asset_id="../etc/passwd")

    def test_add_rejects_weird_chars_in_id(self, lib):
        """asset_id with special characters raises ValueError."""
        with pytest.raises(ValueError, match="asset_id"):
            lib.add(AssetType.CHAR_PORTRAIT, "Weird", asset_id="hello world")

    def test_add_rejects_sys_prefix(self, lib):
        """asset_id starting with 'sys_' is reserved for system assets."""
        with pytest.raises(ValueError, match="sys_"):
            lib.add(AssetType.CHAR_PORTRAIT, "SysHero", asset_id="sys_hero_001")

    def test_add_rejects_sys_prefix_background(self, lib):
        """sys_ prefix is rejected for all asset types."""
        with pytest.raises(ValueError, match="sys_"):
            lib.add(AssetType.BACKGROUND, "SysBg", asset_id="sys_bg_001")

    def test_add_accepts_non_sys_prefix(self, lib):
        """asset_id without sys_ prefix is accepted normally."""
        asset = lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="custom_hero")
        assert asset.id == "custom_hero"
        assert asset.name == "Hero"


# ── Asset path resolution ────────────────────────────────────────────

class TestAssetPath:
    """AssetLibrary.asset_path() — unified filesystem path resolution.

    System assets (sys_ prefix) resolve under system_media_dir;
    user assets under media_dir.  Returns None when the file is missing.
    """

    @staticmethod
    def _touch_file(dir_path: str, asset_type: AssetType, asset_id: str) -> str:
        """Create an empty file in *dir_path* and return its full path."""
        import os
        sub = os.path.join(dir_path, asset_type.value)
        os.makedirs(sub, exist_ok=True)
        path = os.path.join(sub, f"{asset_id}.png")
        with open(path, "wb") as f:
            f.write(b"")
        return path

    def test_asset_path_user_asset(self, tmp_path):
        """User asset (no sys_ prefix) resolves under media_dir."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        lib = AssetLibrary(media)
        lib.add(AssetType.CHAR_PORTRAIT, "Hero", asset_id="hero_001")
        self._touch_file(media, AssetType.CHAR_PORTRAIT, "hero_001")

        asset = lib.get(AssetType.CHAR_PORTRAIT, "hero_001")
        result = lib.asset_path(asset)
        assert result is not None
        assert "media" in result
        assert result.endswith("char_portrait/hero_001.png")

    def test_asset_path_system_asset(self, tmp_path):
        """System asset (sys_ prefix) resolves under system_media_dir."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        sys_dir = os.path.join(str(tmp_path), "system_media")
        lib = AssetLibrary(media)
        lib._system_media_dir = sys_dir
        lib._add_system_asset(AssetType.CHAR_PORTRAIT, "sys_hero_001",
                              "Hero", "A brave warrior.")
        self._touch_file(sys_dir, AssetType.CHAR_PORTRAIT, "sys_hero_001")

        asset = lib.get(AssetType.CHAR_PORTRAIT, "sys_hero_001")
        result = lib.asset_path(asset)
        assert result is not None
        assert "system_media" in result
        assert result.endswith("char_portrait/sys_hero_001.png")

    def test_asset_path_missing_file_returns_none(self, tmp_path):
        """File not on disk → returns None."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        lib = AssetLibrary(media)
        lib.add(AssetType.CHAR_PORTRAIT, "Ghost", asset_id="missing_001")

        asset = lib.get(AssetType.CHAR_PORTRAIT, "missing_001")
        assert lib.asset_path(asset) is None

    def test_asset_path_system_dir_not_set(self, tmp_path):
        """When _system_media_dir is None, sys_ asset falls back to media_dir."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        lib = AssetLibrary(media)
        # _system_media_dir is None by default — don't set it
        lib._add_system_asset(AssetType.CHAR_PORTRAIT, "sys_ghost_001",
                              "Ghost", "A ghost.")
        self._touch_file(media, AssetType.CHAR_PORTRAIT, "sys_ghost_001")

        asset = lib.get(AssetType.CHAR_PORTRAIT, "sys_ghost_001")
        result = lib.asset_path(asset)
        assert result is not None
        assert "media" in result

    def test_asset_path_background_type(self, tmp_path):
        """asset_path works for BACKGROUND type assets too."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        lib = AssetLibrary(media)
        lib.add(AssetType.BACKGROUND, "Tavern", asset_id="bg_001")
        self._touch_file(media, AssetType.BACKGROUND, "bg_001")

        asset = lib.get(AssetType.BACKGROUND, "bg_001")
        result = lib.asset_path(asset)
        assert result is not None
        assert "background_img" in result
        assert result.endswith(".png")


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

    def test_large_dataset_uses_heap(self, lib):
        """Large dataset (1000+ assets, small top_n) returns correct top (D51)."""
        N = 1000
        assets = []
        for i in range(N):
            a = lib.add(AssetType.CHAR_PORTRAIT, f"Char_{i:04d}")
            assets.append(a)
        # Give the last 5 assets higher use_count
        for a in assets[-5:]:
            lib.increase_usage(a.asset_type, a.id)
            lib.increase_usage(a.asset_type, a.id)

        result = lib.get_sorted_by_usage(AssetType.CHAR_PORTRAIT, 3)
        assert len(result) == 3
        # All top 3 should have use_count >= 2 (the bumped ones)
        for r in result:
            assert r.use_count >= 2, f"Expected top results to have use_count>=2, got {r.use_count}"
        # They should be the 5 latest (highest serial) among the bumped group
        assert result[0].use_count >= result[1].use_count >= result[2].use_count


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

    def test_load_skips_unknown_type(self, media_dir):
        """Unknown AssetType in JSON is skipped, not crashed (§2.1 forward compat)."""
        import json
        bad_path = os.path.join(media_dir, "_asset_lib.json")
        # Write a file with a known type and an unknown (future) type
        with open(bad_path, "w") as f:
            json.dump({
                "version": 1,
                "items": {
                    "char_portrait": {
                        "abc": {"name": "Hero", "description": "", "use_count": 0, "serial": 0}
                    },
                    "bgm": {  # Future type — should be silently skipped
                        "song1": {"name": "Theme", "description": "", "use_count": 0, "serial": 1}
                    }
                }
            }, f)
        lib = AssetLibrary.load(media_dir)
        # Known type loaded
        assert lib.get(AssetType.CHAR_PORTRAIT, "abc") is not None
        # Unknown type silently skipped — no crash
        assert len(lib) == 1


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

    def test_concurrent_save_during_write(self, media_dir):
        """save() called during concurrent add doesn't crash or corrupt."""
        lib = AssetLibrary(media_dir)
        errors = []
        N = 100
        barrier = threading.Barrier(3)

        def writer():
            barrier.wait()
            try:
                for i in range(N):
                    lib.add(AssetType.CHAR_PORTRAIT, f"Writer_{i}")
            except Exception as e:
                errors.append(("writer", e))

        def saver():
            barrier.wait()
            try:
                for _ in range(20):
                    lib.save()
            except Exception as e:
                errors.append(("saver", e))

        t1 = threading.Thread(target=writer)
        t2 = threading.Thread(target=writer)
        t3 = threading.Thread(target=saver)
        for t in [t1, t2, t3]:
            t.start()
        for t in [t1, t2, t3]:
            t.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        # Final save should succeed and produce valid JSON
        lib.save()
        loaded = AssetLibrary.load(media_dir)
        assert len(loaded) == N * 2  # all writes finished before final save


# ═══════════════════════════════════════════════════════════════════
# GameAssetRoster
# ═══════════════════════════════════════════════════════════════════

# ── System asset reconciliation ──────────────────────────────────────

class TestSystemAssetReconciliation:
    """AssetLibrary.import_system_assets() — manifest ↔ library sync.

    Per design: on startup, the manifest declares what system assets
    *should* exist; the library holds what *does* exist.  Reconciliation
    computes the diff and applies it — add new, release removed, update
    changed descriptions.
    """

    @staticmethod
    def _write_manifest(system_dir: str, data: dict) -> None:
        """Write a _manifest.json into *system_dir*."""
        import json, os
        os.makedirs(system_dir, exist_ok=True)
        path = os.path.join(system_dir, "_manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _make_manifest(version: str, assets: dict | None = None) -> dict:
        """Return a minimal valid manifest dict."""
        return {
            "version": version,
            "min_app_version": "1.3.0",
            "assets": assets or {},
        }

    # ── Empty manifest ───────────────────────────────────────────────

    def test_import_empty_manifest(self, tmp_path):
        """Empty manifest → report shows zero changes."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        sys_dir = os.path.join(str(tmp_path), "system_media")
        self._write_manifest(sys_dir, self._make_manifest("0.0.0"))

        lib = AssetLibrary(media)
        report = lib.import_system_assets(sys_dir)
        assert report.version == "0.0.0"
        assert report.added == []
        assert report.removed == []
        assert report.unchanged == 0

    # ── Add new assets ───────────────────────────────────────────────

    def test_import_adds_new_assets(self, tmp_path):
        """Manifest with new IDs → assets added to library with use_count=1."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        sys_dir = os.path.join(str(tmp_path), "system_media")
        manifest = self._make_manifest("1.0.0", {
            "char_portrait": {
                "sys_hero_001": {"name": "Hero", "description": "Brave."},
            },
            "background_img": {
                "sys_tavern_001": {"name": "Tavern", "description": "Cozy."},
            },
        })
        self._write_manifest(sys_dir, manifest)

        lib = AssetLibrary(media)
        report = lib.import_system_assets(sys_dir)

        assert set(report.added) == {"sys_hero_001", "sys_tavern_001"}
        assert report.removed == []
        assert report.unchanged == 0
        assert len(lib) == 2

        hero = lib.get(AssetType.CHAR_PORTRAIT, "sys_hero_001")
        assert hero is not None
        assert hero.use_count == 1
        assert hero.name == "Hero"

        tavern = lib.get(AssetType.BACKGROUND, "sys_tavern_001")
        assert tavern is not None
        assert tavern.use_count == 1

    # ── Version skip ─────────────────────────────────────────────────

    def test_import_version_skip(self, tmp_path):
        """Same version → reconciliation skipped, report shows unchanged."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        sys_dir = os.path.join(str(tmp_path), "system_media")
        manifest = self._make_manifest("1.0.0", {
            "char_portrait": {
                "sys_hero_001": {"name": "Hero", "description": "Brave."},
            },
        })
        self._write_manifest(sys_dir, manifest)

        lib = AssetLibrary(media)
        report1 = lib.import_system_assets(sys_dir)
        assert report1.added == ["sys_hero_001"]

        # Second import with same version — skipped
        report2 = lib.import_system_assets(sys_dir)
        assert report2.added == []
        assert report2.unchanged == 1
        assert len(lib) == 1  # no duplicate

    # ── Remove old declarations ──────────────────────────────────────

    def test_import_removes_old_declarations(self, tmp_path):
        """S_old − S_new → system reference released, entry preserved."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        sys_dir = os.path.join(str(tmp_path), "system_media")

        # First: import v1 with one asset
        v1 = self._make_manifest("1.0.0", {
            "char_portrait": {
                "sys_hero_001": {"name": "Hero", "description": "Brave."},
            },
        })
        self._write_manifest(sys_dir, v1)
        lib = AssetLibrary(media)
        lib.import_system_assets(sys_dir)
        assert len(lib) == 1

        # Then: import v2 with the asset removed
        v2 = self._make_manifest("2.0.0", {})
        self._write_manifest(sys_dir, v2)
        report = lib.import_system_assets(sys_dir)

        assert report.removed == ["sys_hero_001"]
        # System reference released, entry stays for manual cleanup
        hero = lib.get(AssetType.CHAR_PORTRAIT, "sys_hero_001")
        assert hero is not None
        assert hero.use_count == 0

    def test_import_removed_asset_with_active_ref_stays(self, tmp_path):
        """S_old − S_new with use_count > 1 → use_count decremented
        but entry kept (still referenced by a game roster)."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        sys_dir = os.path.join(str(tmp_path), "system_media")

        v1 = self._make_manifest("1.0.0", {
            "char_portrait": {
                "sys_hero_001": {"name": "Hero", "description": "Brave."},
            },
        })
        self._write_manifest(sys_dir, v1)
        lib = AssetLibrary(media)
        lib.import_system_assets(sys_dir)

        # Simulate a game roster referencing sys_hero_001
        lib.increase_usage(AssetType.CHAR_PORTRAIT, "sys_hero_001")
        assert lib.get(AssetType.CHAR_PORTRAIT, "sys_hero_001").use_count == 2

        # Now remove from manifest
        v2 = self._make_manifest("2.0.0", {})
        self._write_manifest(sys_dir, v2)
        report = lib.import_system_assets(sys_dir)

        assert report.removed == ["sys_hero_001"]
        hero = lib.get(AssetType.CHAR_PORTRAIT, "sys_hero_001")
        assert hero is not None  # entry still exists
        assert hero.use_count == 1  # system ref released, game ref remains

    # ── Update descriptions ──────────────────────────────────────────

    def test_import_updates_description(self, tmp_path):
        """S_new ∩ S_old with different description → updated in place."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        sys_dir = os.path.join(str(tmp_path), "system_media")

        v1 = self._make_manifest("1.0.0", {
            "char_portrait": {
                "sys_hero_001": {"name": "Hero", "description": "Old desc."},
            },
        })
        self._write_manifest(sys_dir, v1)
        lib = AssetLibrary(media)
        lib.import_system_assets(sys_dir)
        assert lib.get(AssetType.CHAR_PORTRAIT, "sys_hero_001").description == "Old desc."

        v2 = self._make_manifest("2.0.0", {
            "char_portrait": {
                "sys_hero_001": {"name": "Hero", "description": "New desc."},
            },
        })
        self._write_manifest(sys_dir, v2)
        report = lib.import_system_assets(sys_dir)

        assert report.updated == ["sys_hero_001"]
        assert lib.get(AssetType.CHAR_PORTRAIT, "sys_hero_001").description == "New desc."
        assert lib.get(AssetType.CHAR_PORTRAIT, "sys_hero_001").use_count == 1  # unchanged

    def test_import_same_description_not_updated(self, tmp_path):
        """Description unchanged → not counted as updated."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        sys_dir = os.path.join(str(tmp_path), "system_media")
        manifest = self._make_manifest("1.0.0", {
            "char_portrait": {
                "sys_hero_001": {"name": "Hero", "description": "Same."},
            },
        })
        self._write_manifest(sys_dir, manifest)
        lib = AssetLibrary(media)
        lib.import_system_assets(sys_dir)

        # Re-import with same content but different version
        manifest["version"] = "2.0.0"
        self._write_manifest(sys_dir, manifest)
        report = lib.import_system_assets(sys_dir)

        assert report.updated == []
        assert report.unchanged == 1

    # ── State tracking ───────────────────────────────────────────────

    def test_import_sets_system_metadata(self, tmp_path):
        """After import, _system_ids, _system_assets_version,
        _system_media_dir are set correctly."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        sys_dir = os.path.join(str(tmp_path), "system_media")
        self._write_manifest(sys_dir, self._make_manifest("1.0.0", {
            "char_portrait": {
                "sys_hero_001": {"name": "Hero", "description": "Brave."},
            },
        }))

        lib = AssetLibrary(media)
        lib.import_system_assets(sys_dir)

        assert lib._system_assets_version == "1.0.0"
        assert lib._system_media_dir == os.path.abspath(sys_dir)
        assert "sys_hero_001" in lib._system_ids

    # ── User assets preserved ────────────────────────────────────────

    def test_import_preserves_user_assets(self, tmp_path):
        """Reconciliation does not affect non-sys_ assets."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        sys_dir = os.path.join(str(tmp_path), "system_media")
        self._write_manifest(sys_dir, self._make_manifest("1.0.0", {
            "char_portrait": {
                "sys_hero_001": {"name": "Hero", "description": "Brave."},
            },
        }))

        lib = AssetLibrary(media)
        # Add a user asset first
        lib.add(AssetType.CHAR_PORTRAIT, "Custom", asset_id="custom_001")
        assert len(lib) == 1

        lib.import_system_assets(sys_dir)
        assert len(lib) == 2  # user + system

        # User asset untouched
        custom = lib.get(AssetType.CHAR_PORTRAIT, "custom_001")
        assert custom is not None
        assert custom.name == "Custom"

    # ── Clean protection ─────────────────────────────────────────────

    def test_import_use_count_protects_clean(self, tmp_path):
        """System assets (use_count=1) are protected from clean()."""
        from storyloom.assets._library import AssetLibrary
        import os

        media = os.path.join(str(tmp_path), "media")
        sys_dir = os.path.join(str(tmp_path), "system_media")
        self._write_manifest(sys_dir, self._make_manifest("1.0.0", {
            "char_portrait": {
                "sys_hero_001": {"name": "Hero", "description": "Brave."},
            },
        }))

        lib = AssetLibrary(media)
        # Add a user asset with use_count=0
        lib.add(AssetType.CHAR_PORTRAIT, "UserAsset", asset_id="user_001")
        lib.import_system_assets(sys_dir)

        deleted = lib.clean(keep_count=0)
        # sys_hero_001 (use_count=1) survives; user_001 (use_count=0) deleted
        assert deleted == 1
        assert lib.get(AssetType.CHAR_PORTRAIT, "sys_hero_001") is not None
        assert lib.get(AssetType.CHAR_PORTRAIT, "user_001") is None


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

    def test_set_target_same_target_noop(self, roster, roster_lib):
        """set_target to the same target is a no-op (no use_count change)."""
        asset = roster_lib.add(AssetType.CHAR_PORTRAIT, "Asset")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=asset.id)
        assert asset.use_count == 1
        # Setting to the same target should not change use_count
        roster.set_target(AssetType.CHAR_PORTRAIT, "Hero", asset.id)
        assert asset.use_count == 1


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

    def test_load_game_id_mismatch_raises(self, roster, roster_lib, tmp_path):
        """When file game_id ≠ parameter game_id, raises ValueError."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        filepath = str(tmp_path / "_asset_roster.json")
        roster.save(filepath)

        # Pass a different game_id — should raise, not silently swap
        with pytest.raises(ValueError, match="game_id mismatch"):
            GameAssetRoster.load(filepath, roster_lib, game_id="wrong-game")

    def test_load_game_id_match_succeeds(self, roster, roster_lib, tmp_path):
        """When file game_id == parameter game_id, loads successfully."""
        roster.add(AssetType.CHAR_PORTRAIT, "Hero")
        filepath = str(tmp_path / "_asset_roster.json")
        roster.save(filepath)

        loaded = GameAssetRoster.load(filepath, roster_lib, game_id="test-game")
        assert loaded.game_id == "test-game"

    def test_load_game_id_fallback_when_no_file(self, roster_lib, tmp_path):
        """When file doesn't exist, parameter game_id is used."""
        filepath = str(tmp_path / "nonexistent.json")
        loaded = GameAssetRoster.load(filepath, roster_lib, game_id="fallback-game")
        assert loaded.game_id == "fallback-game"


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

    def test_concurrent_set_target_no_use_count_leak(self, roster, roster_lib):
        """Concurrent set_target on the same entry doesn't leak use_count."""
        asset_a = roster_lib.add(AssetType.CHAR_PORTRAIT, "AssetA")
        asset_b = roster_lib.add(AssetType.CHAR_PORTRAIT, "AssetB")
        roster.add(AssetType.CHAR_PORTRAIT, "Hero", target=asset_a.id)

        errors = []
        N = 200
        barrier = threading.Barrier(2)

        def flipper(target_id):
            barrier.wait()
            try:
                for _ in range(N):
                    roster.set_target(AssetType.CHAR_PORTRAIT, "Hero", target_id)
            except Exception as e:
                errors.append(("flipper", e))

        t1 = threading.Thread(target=flipper, args=(asset_a.id,))
        t2 = threading.Thread(target=flipper, args=(asset_b.id,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0, f"Thread errors: {errors}"
        # Final use_count of a + b should be exactly 1 (one of them is the final target)
        # Total = a.use_count + b.use_count = 1 (exactly one active reference)
        assert asset_a.use_count + asset_b.use_count == 1, (
            f"use_count leak: a={asset_a.use_count}, b={asset_b.use_count}"
        )


# ═══════════════════════════════════════════════════════════════════
# §7.7: _init_stub_roster() tests
# ═══════════════════════════════════════════════════════════════════

class TestInitStubRoster:
    """Tests for _init_stub_roster() — §7.8b placeholder seeding.

    Seeds roster from story_config characters/locations as placeholders
    (target=None).  GenerateProcessor fills them on first DECLARE.
    §7.8c replaces this with real AI pre-build.
    """

    @staticmethod
    def _make_config(characters=None, locations=None):
        return {
            "characters": characters or [],
            "locations": locations or [],
        }

    @staticmethod
    def _call_init(roster, story_config):
        from storyloom.core.game_loop import _init_stub_roster
        _init_stub_roster(roster, story_config)

    def test_seeds_characters_as_char_portrait(self, tmp_path):
        """Each character → CHAR_PORTRAIT entry as placeholder (target=None)."""
        from storyloom.assets import GameAssetRoster, AssetType, AssetLibrary
        lib = AssetLibrary(str(tmp_path))
        roster = GameAssetRoster("test_game", lib)
        config = self._make_config(characters=[
            {"name": "Aldric", "description": "A wise mage"},
            {"name": "Elara", "description": "A rogue thief"},
        ])

        self._call_init(roster, config)

        aldric = roster.lookup(AssetType.CHAR_PORTRAIT, "Aldric")
        assert aldric is not None
        assert aldric.target is None  # placeholder until GenerateProcessor fills it
        assert aldric.local_description == "A wise mage"

        elara = roster.lookup(AssetType.CHAR_PORTRAIT, "Elara")
        assert elara is not None
        assert elara.target is None

    def test_seeds_locations_as_background(self, tmp_path):
        """Each location → BACKGROUND entry as placeholder (target=None)."""
        from storyloom.assets import GameAssetRoster, AssetType, AssetLibrary
        lib = AssetLibrary(str(tmp_path))
        roster = GameAssetRoster("test_game", lib)
        config = self._make_config(locations=[
            {"name": "Library", "description": "Ancient dusty library"},
            {"name": "Forest", "description": "Enchanted dark forest"},
        ])

        self._call_init(roster, config)

        lib_entry = roster.lookup(AssetType.BACKGROUND, "Library")
        assert lib_entry is not None
        assert lib_entry.target is None  # placeholder

        forest_entry = roster.lookup(AssetType.BACKGROUND, "Forest")
        assert forest_entry is not None
        assert forest_entry.target is None

    def test_idempotent_does_not_overwrite(self, tmp_path):
        """Calling twice must not overwrite existing entries."""
        from storyloom.assets import GameAssetRoster, AssetType, AssetLibrary
        lib = AssetLibrary(str(tmp_path))
        roster = GameAssetRoster("test_game", lib)
        config = self._make_config(characters=[
            {"name": "Aldric", "description": "Original"},
        ])

        self._call_init(roster, config)
        # Manually change both mutable fields to simulate modification
        item = roster.lookup(AssetType.CHAR_PORTRAIT, "Aldric")
        item.local_description = "Modified"
        item.target = "other_asset"
        # Second call — must skip (already exists)
        self._call_init(roster, config)

        item2 = roster.lookup(AssetType.CHAR_PORTRAIT, "Aldric")
        assert item2.local_description == "Modified"   # not overwritten
        assert item2.target == "other_asset"            # not overwritten

    def test_empty_config_no_error(self, tmp_path):
        """Empty or missing characters/locations → no error."""
        from storyloom.assets import AssetLibrary, GameAssetRoster
        lib = AssetLibrary(str(tmp_path))
        roster = GameAssetRoster("test_game", lib)

        self._call_init(roster, {})  # no 'characters' or 'locations' keys
        assert len(roster) == 0

    def test_skips_empty_names(self, tmp_path):
        """Characters/locations with empty name are skipped."""
        from storyloom.assets import GameAssetRoster, AssetType, AssetLibrary
        lib = AssetLibrary(str(tmp_path))
        roster = GameAssetRoster("test_game", lib)
        config = self._make_config(characters=[
            {"name": "", "description": "No name"},
            {"name": "Valid", "description": "Has name"},
        ])

        self._call_init(roster, config)

        assert roster.lookup(AssetType.CHAR_PORTRAIT, "") is None
        assert roster.lookup(AssetType.CHAR_PORTRAIT, "Valid") is not None

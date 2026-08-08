"""SystemManifest — _manifest.json loader unit tests.

Per design: the manifest declares what system assets *should* exist.
Loaded by ``SystemManifest.load(system_dir)`` at startup for
reconciliation with the persisted AssetLibrary state.
"""

import json
import os

import pytest

from storyloom.assets._types import AssetType


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _write_manifest(tmp_path, data: dict) -> str:
    """Write a _manifest.json into *tmp_path* and return the directory path."""
    path = os.path.join(str(tmp_path), "_manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(tmp_path)


def _make_valid_manifest() -> dict:
    """Return a minimal valid manifest dict for reuse across tests."""
    return {
        "version": "1.0.0",
        "min_app_version": "1.3.0",
        "assets": {
            "char_portrait": {
                "sys_hero_001": {
                    "name": "Hero",
                    "description": "A brave young warrior.",
                    "tags": ["hero", "young", "fantasy"],
                },
            },
            "background_img": {
                "sys_tavern_001": {
                    "name": "Tavern",
                    "description": "A cozy tavern interior.",
                },
            },
        },
    }


# ═══════════════════════════════════════════════════════════════════════
# ManifestEntry
# ═══════════════════════════════════════════════════════════════════════

class TestManifestEntry:
    """ManifestEntry is a simple value object holding name, description, tags."""

    def test_fields_populated(self):
        """All fields from manifest JSON are accessible on the entry."""
        from storyloom.assets._manifest import ManifestEntry

        entry = ManifestEntry(
            name="Hero",
            description="A brave warrior.",
            tags=["hero", "fantasy"],
        )
        assert entry.name == "Hero"
        assert entry.description == "A brave warrior."
        assert entry.tags == ["hero", "fantasy"]

    def test_tags_defaults_to_empty_list(self):
        """tags is optional — defaults to [] when not provided."""
        from storyloom.assets._manifest import ManifestEntry

        entry = ManifestEntry(name="Hero", description="Desc")
        assert entry.tags == []


# ═══════════════════════════════════════════════════════════════════════
# SystemManifest.load()
# ═══════════════════════════════════════════════════════════════════════

class TestSystemManifestLoad:
    """SystemManifest.load(system_dir) reads and validates _manifest.json."""

    def test_load_valid_manifest(self, tmp_path):
        """A complete manifest produces a populated SystemManifest."""
        _write_manifest(tmp_path, _make_valid_manifest())

        from storyloom.assets._manifest import SystemManifest

        m = SystemManifest.load(str(tmp_path))
        assert m.version == "1.0.0"
        assert m.min_app_version == "1.3.0"
        assert AssetType.CHAR_PORTRAIT in m.assets
        assert AssetType.BACKGROUND in m.assets
        assert len(m.assets[AssetType.CHAR_PORTRAIT]) == 1
        assert len(m.assets[AssetType.BACKGROUND]) == 1

    def test_load_parses_entries_correctly(self, tmp_path):
        """Each manifest key maps to a ManifestEntry with correct fields."""
        _write_manifest(tmp_path, _make_valid_manifest())

        from storyloom.assets._manifest import SystemManifest

        m = SystemManifest.load(str(tmp_path))
        hero = m.assets[AssetType.CHAR_PORTRAIT]["sys_hero_001"]
        assert hero.name == "Hero"
        assert hero.description == "A brave young warrior."
        assert hero.tags == ["hero", "young", "fantasy"]

        tavern = m.assets[AssetType.BACKGROUND]["sys_tavern_001"]
        assert tavern.name == "Tavern"
        assert tavern.description == "A cozy tavern interior."
        assert tavern.tags == []  # tags key absent → default

    def test_load_empty_assets(self, tmp_path):
        """Empty assets dict is valid — no assets declared yet."""
        data = {
            "version": "0.0.0",
            "min_app_version": "1.3.0",
            "assets": {},
        }
        _write_manifest(tmp_path, data)

        from storyloom.assets._manifest import SystemManifest

        m = SystemManifest.load(str(tmp_path))
        assert m.version == "0.0.0"
        assert m.assets == {}

    def test_load_missing_file(self, tmp_path):
        """Directory without _manifest.json raises FileNotFoundError."""
        empty_dir = os.path.join(str(tmp_path), "no_manifest")
        os.makedirs(empty_dir, exist_ok=True)

        from storyloom.assets._manifest import SystemManifest

        with pytest.raises(FileNotFoundError):
            SystemManifest.load(empty_dir)

    def test_load_missing_version(self, tmp_path):
        """Manifest without 'version' key raises ValueError."""
        data = _make_valid_manifest()
        del data["version"]
        _write_manifest(tmp_path, data)

        from storyloom.assets._manifest import SystemManifest

        with pytest.raises(ValueError, match="version"):
            SystemManifest.load(str(tmp_path))

    def test_load_missing_assets(self, tmp_path):
        """Manifest without 'assets' key raises ValueError."""
        data = _make_valid_manifest()
        del data["assets"]
        _write_manifest(tmp_path, data)

        from storyloom.assets._manifest import SystemManifest

        with pytest.raises(ValueError, match="assets"):
            SystemManifest.load(str(tmp_path))

    def test_load_corrupt_json(self, tmp_path):
        """Non-JSON content raises json.JSONDecodeError (let it propagate)."""
        path = os.path.join(str(tmp_path), "_manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("not json{{{")

        from storyloom.assets._manifest import SystemManifest

        with pytest.raises(json.JSONDecodeError):
            SystemManifest.load(str(tmp_path))

    def test_load_unknown_asset_type_skipped(self, tmp_path):
        """Unknown type strings are silently skipped (forward compat)."""
        data = _make_valid_manifest()
        data["assets"]["audio_bgm"] = {
            "sys_music_001": {"name": "Theme", "description": "BGM"}
        }
        _write_manifest(tmp_path, data)

        from storyloom.assets._manifest import SystemManifest

        m = SystemManifest.load(str(tmp_path))
        # Known types still loaded
        assert AssetType.CHAR_PORTRAIT in m.assets
        assert AssetType.BACKGROUND in m.assets
        # Unknown type key absent from parsed dict
        unknown_keys = [
            k for k in m.assets if k not in (AssetType.CHAR_PORTRAIT, AssetType.BACKGROUND)
        ]
        assert len(unknown_keys) == 0

    def test_load_missing_tags_defaults_empty(self, tmp_path):
        """Entries without 'tags' key get an empty list (not KeyError)."""
        data = _make_valid_manifest()
        # sys_tavern_001 already has no tags — verified in
        # test_load_parses_entries_correctly.  Here we assert it
        # doesn't crash.
        _write_manifest(tmp_path, data)

        from storyloom.assets._manifest import SystemManifest

        m = SystemManifest.load(str(tmp_path))
        tavern = m.assets[AssetType.BACKGROUND]["sys_tavern_001"]
        assert tavern.tags == []

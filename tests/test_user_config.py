"""Tests for user_config module."""
import json
import tempfile
from pathlib import Path

import pytest
from storyloom.user_config import UserConfig


class TestUserConfigDefaults:
    """Headless mode — no file on disk, all defaults."""

    def test_headless_uses_defaults(self):
        cfg = UserConfig()
        assert cfg.language == "en"
        assert cfg.api_key == ""
        assert cfg.api_base_url == "https://api.deepseek.com"
        assert cfg.api_model == "deepseek-v4-pro"

    def test_headless_set_and_read_properties(self):
        cfg = UserConfig()
        cfg.language = "en"
        cfg.api_key = "sk-test"
        assert cfg.language == "en"
        assert cfg.api_key == "sk-test"

    def test_headless_save_is_noop(self):
        """Headless mode should not raise on save — just skip disk I/O."""
        cfg = UserConfig()
        cfg.language = "en"
        cfg.save()  # must not raise


class TestUserConfigLoad:
    """Load from existing config.json on disk."""

    def test_loads_all_fields(self, tmp_path):
        data = {
            "version": 1,
            "language": "en",
            "api_key": "sk-abc123",
            "api_base_url": "https://api.openai.com",
            "api_model": "gpt-4",
        }
        _write_json(tmp_path / "config.json", data)
        cfg = UserConfig(tmp_path)
        assert cfg.language == "en"
        assert cfg.api_key == "sk-abc123"
        assert cfg.api_base_url == "https://api.openai.com"
        assert cfg.api_model == "gpt-4"

    def test_missing_file_creates_default(self, tmp_path):
        cfg = UserConfig(tmp_path)
        assert cfg.language == "en"
        assert (tmp_path / "config.json").exists()

    def test_partial_file_backfills_missing_fields(self, tmp_path):
        """v2 config with missing fields → backfill + re-save."""
        _write_json(tmp_path / "config.json", {"version": 2, "language": "en"})
        cfg = UserConfig(tmp_path)
        assert cfg.language == "en"
        # Missing fields get defaults
        assert cfg.api_key == ""
        assert cfg.api_base_url == "https://api.deepseek.com"
        # File should have been re-saved with all fields
        saved = json.loads((tmp_path / "config.json").read_text())
        assert "api_key" in saved

    def test_copies_example_json_if_present(self, tmp_path):
        _write_json(tmp_path / "config.example.json", {
            "version": 1,
            "language": "en",
            "api_key": "your-api-key-here",
            "api_base_url": "https://api.deepseek.com",
            "api_model": "deepseek-v4-pro",
        })
        cfg = UserConfig(tmp_path)
        assert cfg.language == "en"
        assert (tmp_path / "config.json").exists()

    def test_corrupt_json_falls_back_to_defaults(self, tmp_path):
        (tmp_path / "config.json").write_text("not valid json {{{")
        cfg = UserConfig(tmp_path)
        # Should not raise; should use defaults
        assert cfg.language == "en"
        # Original corrupt file should NOT be deleted
        assert (tmp_path / "config.json").exists()


class TestUserConfigSave:
    """Atomic save to disk."""

    def test_save_writes_all_fields(self, tmp_path):
        cfg = UserConfig(tmp_path)
        cfg.language = "en"
        cfg.api_key = "sk-new"
        cfg.save()
        saved = json.loads((tmp_path / "config.json").read_text())
        assert saved["language"] == "en"
        assert saved["api_key"] == "sk-new"

    def test_save_is_atomic_no_partial_write(self, tmp_path):
        """If save() succeeds, file must be complete and valid JSON."""
        cfg = UserConfig(tmp_path)
        cfg.api_key = "sk-atomic"
        cfg.save()
        data = json.loads((tmp_path / "config.json").read_text())
        assert "api_key" in data
        assert data["version"] == 2
        # No .tmp file should remain
        tmps = list(tmp_path.glob("*.tmp"))
        assert len(tmps) == 0

    def test_save_preserves_version(self, tmp_path):
        _write_json(tmp_path / "config.json", {"version": 1, "language": "en"})
        cfg = UserConfig(tmp_path)
        cfg.language = "zh-CN"
        cfg.save()
        saved = json.loads((tmp_path / "config.json").read_text())
        assert saved["version"] == 1


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════════════════════════════
# Image API & game mode fields (7.3)
# ═══════════════════════════════════════════════════════════════════

class TestUserConfigImageFields:
    """New fields added in 7.3 for image API configuration."""

    # ── Defaults ──

    def test_game_mode_default(self):
        cfg = UserConfig()
        assert cfg.game_mode == "text"

    def test_img_api_key_default(self):
        cfg = UserConfig()
        assert cfg.img_api_key == ""

    def test_img_api_base_url_default(self):
        cfg = UserConfig()
        assert cfg.img_api_base_url == ""

    def test_img_api_model_default(self):
        cfg = UserConfig()
        assert cfg.img_api_model == "flux-2-pro"

    def test_portrait_remove_bg_default(self):
        cfg = UserConfig()
        assert cfg.portrait_remove_bg == "auto"

    # ── Setters ──

    def test_game_mode_setter_valid_values(self):
        cfg = UserConfig()
        cfg.game_mode = "text"
        assert cfg.game_mode == "text"
        cfg.game_mode = "graph"
        assert cfg.game_mode == "graph"

    def test_game_mode_setter_rejects_invalid(self):
        cfg = UserConfig()
        with pytest.raises(ValueError, match="game_mode"):
            cfg.game_mode = "invalid"

    def test_portrait_remove_bg_setter_rejects_invalid(self):
        cfg = UserConfig()
        with pytest.raises(ValueError, match="portrait_remove_bg"):
            cfg.portrait_remove_bg = "sometimes"

    def test_img_fields_setters(self):
        cfg = UserConfig()
        cfg.img_api_key = "sk-img-test"
        cfg.img_api_base_url = "https://img.example.com"
        cfg.img_api_model = "custom-model"
        cfg.portrait_remove_bg = "always"
        assert cfg.img_api_key == "sk-img-test"
        assert cfg.img_api_base_url == "https://img.example.com"
        assert cfg.img_api_model == "custom-model"
        assert cfg.portrait_remove_bg == "always"

    # ── Load backfill ──

    def test_old_config_without_img_fields_gets_defaults(self, tmp_path):
        """v2 config without image fields → load + backfill defaults."""
        _write_json(tmp_path / "config.json", {
            "version": 2,
            "language": "en",
            "api_key": "sk-old",
            "api_base_url": "https://old.example.com",
            "api_model": "old-model",
        })
        cfg = UserConfig(tmp_path)
        assert cfg.game_mode == "text"
        assert cfg.img_api_key == ""
        assert cfg.img_api_base_url == ""
        assert cfg.img_api_model == "flux-2-pro"
        assert cfg.portrait_remove_bg == "auto"
        # Should have been re-saved with all fields
        saved = json.loads((tmp_path / "config.json").read_text())
        assert "game_mode" in saved
        assert "img_api_key" in saved
        assert saved["game_mode"] == "text"

    # ── Save round-trip ──

    def test_save_load_round_trip_img_fields(self, tmp_path):
        cfg = UserConfig(tmp_path)
        cfg.game_mode = "graph"
        cfg.img_api_key = "sk-img-save"
        cfg.img_api_base_url = "https://images.example.com"
        cfg.img_api_model = "my-model"
        cfg.portrait_remove_bg = "never"
        cfg.save()

        cfg2 = UserConfig(tmp_path)
        assert cfg2.game_mode == "graph"
        assert cfg2.img_api_key == "sk-img-save"
        assert cfg2.img_api_base_url == "https://images.example.com"
        assert cfg2.img_api_model == "my-model"
        assert cfg2.portrait_remove_bg == "never"

    def test_save_json_structure_includes_img_fields(self, tmp_path):
        cfg = UserConfig(tmp_path)
        cfg.game_mode = "graph"
        cfg.img_api_key = "sk-test"
        cfg.save()
        data = json.loads((tmp_path / "config.json").read_text())
        assert data["game_mode"] == "graph"
        assert data["img_api_key"] == "sk-test"
        assert data["img_api_base_url"] == ""
        assert data["img_api_model"] == "flux-2-pro"
        assert data["portrait_remove_bg"] == "auto"
        # Version matches current schema
        assert data["version"] == 2

    # ── Version migration (7.3) ──

    def test_version_mismatch_sets_needs_migration(self, tmp_path):
        """v1 config → needs_migration is True, old values still loaded."""
        _write_json(tmp_path / "config.json", {
            "version": 1,
            "language": "zh-CN",
            "api_key": "sk-old-key",
            "api_base_url": "https://old.example.com",
            "api_model": "old-model",
        })
        cfg = UserConfig(tmp_path)
        assert cfg.needs_migration is True
        # Old values loaded in memory for this session
        assert cfg.language == "zh-CN"
        assert cfg.api_key == "sk-old-key"
        # Missing fields get defaults
        assert cfg.game_mode == "text"
        # File NOT backfilled (version stays 1)
        saved = json.loads((tmp_path / "config.json").read_text())
        assert saved["version"] == 1
        assert "game_mode" not in saved

    def test_version_match_no_migration(self, tmp_path):
        """v2 config → needs_migration is False, backfill works."""
        _write_json(tmp_path / "config.json", {
            "version": 2,
            "language": "en",
            "api_key": "sk-v2",
            "api_base_url": "https://api.example.com",
            "api_model": "gpt-4",
        })
        cfg = UserConfig(tmp_path)
        assert cfg.needs_migration is False

    def test_reset_to_defaults_clears_migration(self, tmp_path):
        """After reset, needs_migration is False and version is 2."""
        _write_json(tmp_path / "config.json", {
            "version": 1,
            "language": "zh-CN",
            "api_key": "sk-old-key",
        })
        cfg = UserConfig(tmp_path)
        assert cfg.needs_migration is True

        cfg.reset_to_defaults()
        assert cfg.needs_migration is False
        assert cfg.language == "en"  # factory default
        assert cfg.api_key == ""
        assert cfg.game_mode == "text"

        # Persisted with version 2
        saved = json.loads((tmp_path / "config.json").read_text())
        assert saved["version"] == 2
        assert saved["game_mode"] == "text"

    # ── Property isolation ──

    def test_img_fields_dont_affect_llm_fields(self, tmp_path):
        """Setting image fields should not change LLM fields."""
        cfg = UserConfig(tmp_path)
        cfg.api_key = "sk-llm"
        cfg.api_model = "deepseek-v4-pro"
        cfg.img_api_key = "sk-img"
        cfg.img_api_model = "flux-2-pro"
        cfg.save()

        cfg2 = UserConfig(tmp_path)
        assert cfg2.api_key == "sk-llm"
        assert cfg2.api_model == "deepseek-v4-pro"
        assert cfg2.img_api_key == "sk-img"
        assert cfg2.img_api_model == "flux-2-pro"

    # ── img_generation_enabled (§7.8 framework) ──

    def test_img_generation_enabled_default(self):
        """img_generation_enabled defaults to True."""
        cfg = UserConfig()
        assert cfg.img_generation_enabled is True

    def test_img_generation_enabled_setter(self):
        """img_generation_enabled accepts True/False."""
        cfg = UserConfig()
        cfg.img_generation_enabled = False
        assert cfg.img_generation_enabled is False
        cfg.img_generation_enabled = True
        assert cfg.img_generation_enabled is True

    def test_img_generation_enabled_round_trip(self, tmp_path):
        """img_generation_enabled survives save→load."""
        cfg = UserConfig(tmp_path)
        cfg.img_generation_enabled = False
        cfg.save()

        cfg2 = UserConfig(tmp_path)
        assert cfg2.img_generation_enabled is False

    def test_img_generation_enabled_backfill(self, tmp_path):
        """Old config without img_generation_enabled → defaults to True."""
        _write_json(tmp_path / "config.json", {
            "version": 2,
            "language": "en",
            "api_key": "sk-old",
            "api_base_url": "https://old.example.com",
            "api_model": "old-model",
        })
        cfg = UserConfig(tmp_path)
        assert cfg.img_generation_enabled is True
        # Backfilled on save
        saved = json.loads((tmp_path / "config.json").read_text())
        assert "img_generation_enabled" in saved

    def test_img_generation_enabled_in_json_structure(self, tmp_path):
        """config.json contains img_generation_enabled after save."""
        cfg = UserConfig(tmp_path)
        cfg.img_generation_enabled = False
        cfg.save()
        data = json.loads((tmp_path / "config.json").read_text())
        assert data["img_generation_enabled"] is False

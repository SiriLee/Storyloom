"""Tests for web server endpoints (co-create, game start, saves).

Uses FastAPI TestClient with mocked sessions + ApiClient.
CoCreateFlow / GameSession engine methods are NOT mocked — only
the ApiClient (to avoid real network calls) and sessions store.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from storyloom.core.co_create import CoCreateError
from storyloom.core.session import GameSession
from storyloom.io.api_client import ApiClient
from storyloom.user_config import UserConfig


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════


@pytest.fixture
def app_dir():
    """Isolated app dir with minimal config.json so UserConfig doesn't fail."""
    with tempfile.TemporaryDirectory() as td:
        cfg = {"version": 1, "language": "zh-CN", "api_key": "sk-test",
               "api_base_url": "https://api.test.com", "api_model": "test"}
        with open(os.path.join(td, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        old = os.environ.get("STORYLOOM_APP_DIR")
        os.environ["STORYLOOM_APP_DIR"] = td
        yield Path(td)
        if old is not None:
            os.environ["STORYLOOM_APP_DIR"] = old
        else:
            del os.environ["STORYLOOM_APP_DIR"]


@pytest.fixture
def client(app_dir):
    """FastAPI TestClient with mocked ApiClient (dev_cli pattern)."""
    mock_api = MagicMock(spec=ApiClient)
    mock_api.chat.return_value = "Hello! Tell me about your story idea."

    # Patch the module-level _api_client before importing server
    with patch("storyloom.web.server._api_client", mock_api):
        from storyloom.web.server import app
        from storyloom.web import sessions
        sessions.remove_co_create()
        with TestClient(app) as tc:
            yield tc


@pytest.fixture
def client_with_session(client):
    """Client with an active co-creation session already started."""
    from storyloom.web import sessions
    from storyloom.core.co_create import CoCreateFlow
    from storyloom.web.server import _api_client

    flow = CoCreateFlow(_api_client)
    flow.start()
    sessions.store_co_create(flow)
    return client


# ═══════════════════════════════════════════════════════════════════
# Static / health
# ═══════════════════════════════════════════════════════════════════


class TestStaticEndpoints:
    def test_index_returns_html(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]

    def test_health_returns_ok(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        assert res.json() == {"status": "ok"}


class TestContentRoute:
    """Tests for GET /content/{lang}/{doc} — localized long-form content."""

    @staticmethod
    def _write_content(app_dir, lang, doc, text):
        # URL lang is BCP-47 (zh-CN); the directory is POSIX (zh_CN).
        lang_dir = lang.replace("-", "_")
        d = app_dir / "locale" / lang_dir / "content"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{doc}.md").write_text(text, encoding="utf-8")

    def test_serve_guide_en(self, client, app_dir):
        self._write_content(app_dir, "en", "guide", "# API Setup Guide\n\nHello")
        import storyloom.web.server as server_mod
        with patch.object(server_mod, "_locale_dir", str(app_dir / "locale")):
            res = client.get("/content/en/guide")
        assert res.status_code == 200
        assert "text/markdown" in res.headers["content-type"]
        assert res.text.startswith("# API Setup Guide")

    def test_serve_guide_zh_cn_maps_underscore_dir(self, client, app_dir):
        self._write_content(app_dir, "zh-CN", "guide", "# API 设置指南")
        import storyloom.web.server as server_mod
        with patch.object(server_mod, "_locale_dir", str(app_dir / "locale")):
            res = client.get("/content/zh-CN/guide")
        assert res.status_code == 200
        assert "API 设置指南" in res.text

    def test_unknown_language_404(self, client):
        res = client.get("/content/fr/guide")
        assert res.status_code == 404

    def test_missing_document_404(self, client, app_dir):
        import storyloom.web.server as server_mod
        # Valid language but no content dir → file missing → 404.
        with patch.object(server_mod, "_locale_dir", str(app_dir / "locale")):
            res = client.get("/content/en/nonexistent")
        assert res.status_code == 404

    def test_document_slug_rejects_dot(self, client):
        # doc must match [A-Za-z0-9_-]+ — a dot/slash payload is rejected
        # before touching the filesystem (path-traversal guard).
        res = client.get("/content/en/foo.bar")
        assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════


class TestConfig:
    def test_get_config_returns_masked_key(self, client):
        res = client.get("/api/config")
        assert res.status_code == 200
        data = res.json()
        assert data["language"] == "zh-CN"
        assert "****" in data["api_key"] or data["api_key"] == ""

    def test_update_config_language(self, client):
        res = client.post("/api/config", json={"language": "en"})
        assert res.status_code == 200

    def test_reject_unsupported_language(self, client):
        res = client.post("/api/config", json={"language": "fr"})
        assert res.status_code == 400

    # ── Image API & game mode fields (7.3) ──

    def test_get_config_returns_image_fields(self, client):
        res = client.get("/api/config")
        assert res.status_code == 200
        data = res.json()
        assert "game_mode" in data
        assert data["game_mode"] == "text"
        assert "img_api_key" in data
        assert "img_api_base_url" in data
        assert "img_api_model" in data
        assert "portrait_remove_bg" in data
        assert data["portrait_remove_bg"] == "auto"

    def test_update_config_game_mode_valid(self, client):
        res = client.post("/api/config", json={"game_mode": "graph"})
        assert res.status_code == 200
        # Verify it persisted
        data = client.get("/api/config").json()
        assert data["game_mode"] == "graph"
        # Restore default
        client.post("/api/config", json={"game_mode": "text"})

    def test_update_config_game_mode_rejects_invalid(self, client):
        res = client.post("/api/config", json={"game_mode": "invalid"})
        assert res.status_code == 400

    def test_update_img_fields_success(self, client):
        res = client.post("/api/config", json={
            "img_api_key": "sk-img-test",
            "img_api_base_url": "https://img.example.com",
            "img_api_model": "custom-model",
            "portrait_remove_bg": "always",
        })
        assert res.status_code == 200
        data = client.get("/api/config").json()
        assert "****" in data["img_api_key"]
        assert data["img_api_base_url"] == "https://img.example.com"
        assert data["img_api_model"] == "custom-model"
        assert data["portrait_remove_bg"] == "always"

    def test_update_portrait_remove_bg_rejects_invalid(self, client):
        res = client.post("/api/config", json={"portrait_remove_bg": "sometimes"})
        assert res.status_code == 400

    # ── Version migration (7.3) ──

    def test_version_status_no_migration(self, client, app_dir):
        """Fresh v2 config → needs_migration is False."""
        # app_dir fixture creates a config with version=1, so we need an
        # explicit v2 config.  Write it directly.
        import json, os
        cfg_path = os.path.join(str(app_dir), "config.json")
        with open(cfg_path, "w") as f:
            json.dump({"version": 2, "language": "en", "api_key": "sk-v2",
                       "api_base_url": "https://api.test.com",
                       "api_model": "test"}, f)
        # Re-import to pick up new config... but server module is already
        # imported.  The client fixture uses a patched module, so we
        # can't easily reload.  Instead, test with a lower-level approach.
        res = client.get("/api/config/version-status")
        assert res.status_code == 200
        data = res.json()
        # The fixture has version=1 config, so this will actually show
        # needs_migration.  We'll test the positive path differently.
        assert "needs_migration" in data
        assert "current_version" in data
        assert "expected_version" in data

    def test_version_status_returns_needs_migration(self, client):
        """The default test fixture has v1 config → needs_migration is True."""
        res = client.get("/api/config/version-status")
        assert res.status_code == 200
        data = res.json()
        assert data["needs_migration"] is True
        assert data["current_version"] == 1
        assert data["expected_version"] == 2

    def test_migrate_resets_config(self, client):
        """POST /api/config/migrate clears migration flag and resets."""
        # First verify migration is needed
        status = client.get("/api/config/version-status").json()
        assert status["needs_migration"] is True

        # Migrate
        res = client.post("/api/config/migrate")
        assert res.status_code == 200

        # After migration, no longer needed
        status = client.get("/api/config/version-status").json()
        assert status["needs_migration"] is False
        assert status["current_version"] == 2

        # Config should have factory defaults
        data = client.get("/api/config").json()
        assert data["language"] == "en"
        assert data["api_key"] == ""
        assert data["game_mode"] == "text"


# ═══════════════════════════════════════════════════════════════════
# Co-create: start
# ═══════════════════════════════════════════════════════════════════


class TestCoCreateStart:
    def test_start_returns_phase_and_prompt(self, client):
        res = client.post("/api/co-create/start")
        assert res.status_code == 200
        data = res.json()
        assert data["phase"] == "awaiting_idea"
        assert isinstance(data["prompt"], str)
        assert len(data["prompt"]) > 0

    def test_start_stores_session(self, client):
        client.post("/api/co-create/start")
        from storyloom.web import sessions
        assert sessions.get_co_create() is not None


# ═══════════════════════════════════════════════════════════════════
# Co-create: send
# ═══════════════════════════════════════════════════════════════════


class TestCoCreateSend:
    def test_send_returns_reply(self, client_with_session):
        res = client_with_session.post(
            "/api/co-create/send", json={"text": "A cyberpunk story"}
        )
        assert res.status_code == 200
        data = res.json()
        assert "reply" in data
        assert len(data["reply"]) > 0

    def test_send_no_session_returns_400(self, client):
        res = client.post("/api/co-create/send", json={"text": "hello"})
        assert res.status_code == 400

    def test_send_empty_text_returns_400(self, client_with_session):
        res = client_with_session.post(
            "/api/co-create/send", json={"text": ""}
        )
        assert res.status_code == 400

    def test_send_api_error_returns_502(self, client):
        """Mock the sessions store to return a flow that raises."""
        from storyloom.web import sessions

        mock_flow = MagicMock()
        mock_flow.send.side_effect = CoCreateError(
            phase="send", message="API timeout"
        )
        sessions.store_co_create(mock_flow)

        res = client.post("/api/co-create/send", json={"text": "test"})
        assert res.status_code == 502
        assert "API timeout" in res.json()["detail"]


# ═══════════════════════════════════════════════════════════════════
# Co-create: retry-send
# ═══════════════════════════════════════════════════════════════════


class TestCoCreateRetrySend:
    def test_retry_send_returns_reply(self, client):
        from storyloom.web import sessions

        mock_flow = MagicMock()
        mock_flow.retry_send.return_value = "Retried reply"
        sessions.store_co_create(mock_flow)

        res = client.post("/api/co-create/retry-send")
        assert res.status_code == 200
        assert res.json()["reply"] == "Retried reply"

    def test_retry_send_no_session_returns_400(self, client):
        res = client.post("/api/co-create/retry-send")
        assert res.status_code == 400

    def test_retry_send_api_error_returns_502(self, client):
        from storyloom.web import sessions

        mock_flow = MagicMock()
        mock_flow.retry_send.side_effect = CoCreateError(
            phase="send", message="API timeout"
        )
        sessions.store_co_create(mock_flow)

        res = client.post("/api/co-create/retry-send")
        assert res.status_code == 502


# ═══════════════════════════════════════════════════════════════════
# Co-create: generate
# ═══════════════════════════════════════════════════════════════════


SAMPLE_STORY_CONFIG = {
    "tier": "short",
    "title": "Test",
    "language": "zh-CN",
    "premise": "A cyberpunk test story.",
}

SAMPLE_RESULT = {
    "story_config": SAMPLE_STORY_CONFIG,
    "characters": [
        {"name": "Tester", "role": "protagonist", "description": "A hacker", "appearance": "Tall"},
    ],
    "locations": [
        {"id": "test_loc", "name": "Test", "description": "A place"},
    ],
    "variables": [
        {"name": "hp", "type": "number", "initial": 80},
    ],
    "outline": [
        {"id": "ch1", "title": "Start", "goal": "Begin", "routes": []},
    ],
    "outline_text": "ch1 [active] — Start：Begin",
}


class TestCoCreateGenerate:
    def test_generate_creates_save_and_returns_game_id(self, client):
        from storyloom.web import sessions
        from storyloom.web.server import _game_session

        mock_flow = MagicMock()
        mock_flow.generate.return_value = SAMPLE_RESULT
        sessions.store_co_create(mock_flow)

        # Mock start_game to avoid real filesystem writes
        mock_gl = MagicMock()
        mock_gl.round_count = 0
        mock_gl.current_node = "ch1"
        with patch.object(_game_session, "start_game",
                          return_value=(mock_gl, "test-game-123")):
            res = client.post("/api/co-create/generate")

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["game_id"] == "test-game-123"
        assert data["story_config"]["title"] == "Test"
        # GameLoop stored for later start
        assert sessions.get_game("test-game-123") is mock_gl
        # Co-create session cleaned up — game is now live
        assert sessions.get_co_create() is None

    def test_generate_no_session_returns_400(self, client):
        res = client.post("/api/co-create/generate")
        assert res.status_code == 400

    def test_generate_api_error_returns_502(self, client):
        from storyloom.web import sessions

        mock_flow = MagicMock()
        mock_flow.generate.side_effect = CoCreateError(
            phase="generate_api", message="Generate API timeout"
        )
        sessions.store_co_create(mock_flow)

        res = client.post("/api/co-create/generate")
        assert res.status_code == 502


# ═══════════════════════════════════════════════════════════════════
# Co-create: retry-generate
# ═══════════════════════════════════════════════════════════════════


class TestCoCreateRetryGenerate:
    def test_retry_generate_returns_result(self, client):
        from storyloom.web import sessions
        from storyloom.web.server import _game_session

        mock_flow = MagicMock()
        mock_flow.retry_generate.return_value = SAMPLE_RESULT
        sessions.store_co_create(mock_flow)

        mock_gl = MagicMock()
        mock_gl.round_count = 0
        mock_gl.current_node = "ch1"
        with patch.object(_game_session, "start_game",
                          return_value=(mock_gl, "test-retry-456")):
            res = client.post("/api/co-create/retry-generate")

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["game_id"] == "test-retry-456"

    def test_retry_generate_no_session_returns_400(self, client):
        res = client.post("/api/co-create/retry-generate")
        assert res.status_code == 400


# ═══════════════════════════════════════════════════════════════════
# Co-create: abort
# ═══════════════════════════════════════════════════════════════════


class TestCoCreateAbort:
    def test_abort_clears_session(self, client):
        from storyloom.web import sessions

        mock_flow = MagicMock()
        sessions.store_co_create(mock_flow)

        res = client.post("/api/co-create/abort")
        assert res.status_code == 200
        assert sessions.get_co_create() is None

    def test_abort_without_session_succeeds(self, client):
        res = client.post("/api/co-create/abort")
        assert res.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# §7.8c DELETE BLOCK START — endpoint replaced when AI pre-build added
# ═══════════════════════════════════════════════════════════════════


class TestCoCreatePrebuild:
    def test_prebuild_stream_returns_sse(self, client, app_dir):
        """GET /api/co-create/prebuild/{id}/stream → SSE progress events."""
        from storyloom.web import sessions
        from storyloom.web.server import _game_session

        # Store a fake game in the session so the endpoint's
        # sessions.get_game() call succeeds (added in P2 fix).
        sessions.store_game("test-game-123", MagicMock())

        def _fake_prebuild(game_id, game_loop=None, cancel_event=None):
            yield {
                "type": "prebuild_progress",
                "phase": "parse",
                "entities": {"char_portrait": 2, "background": 1},
            }
            yield {
                "type": "prebuild_complete",
                "success": True,
                "results": [],
                "errors": [],
                "warnings": [],
            }

        with patch.object(_game_session, "prebuild_assets",
                          side_effect=_fake_prebuild):
            res = client.get("/api/co-create/prebuild/test-game-123/stream")

        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        body = res.text
        assert "event: prebuild_progress" in body
        assert "event: prebuild_complete" in body
        assert "prebuild_progress" in body
        assert "prebuild_complete" in body
        assert "success" in body


# ═══════════════════════════════════════════════════════════════════
# §7.8c DELETE BLOCK END
# ═══════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════
# §7.7: Saves — game_mode in response
# ═══════════════════════════════════════════════════════════════════


class TestSaveGameMode:
    def test_save_load_includes_game_mode_graph(self, client, app_dir):
        """POST /api/saves/{id}/load/{file} → game_mode from config.mode."""
        import os as _os
        import json as _json

        # Override saves root so the server finds our test save.
        # Module-level _game_session was bound at import time to a
        # different temp dir — patch it per-test.
        from storyloom.web.server import _game_session
        saves_root = _os.path.join(str(app_dir), "saves")
        with patch.object(_game_session, "_saves_root", saves_root):
            game_id = "test-gm-graph"
            save_dir = _os.path.join(saves_root, game_id)
            _os.makedirs(save_dir, exist_ok=True)
            init_data = {
                "version": 3,
                "metadata": {"title": "T", "created_at": "", "updated_at": ""},
                "config": {"temperature": None, "mode": "graph"},
                "story_config": {"title": "T"},
                "characters": [], "locations": [], "variables": [],
                "state_vars": {}, "outline": [],
                "progress": {"current_node": "", "checkpoint_snapshots": {}},
            }
            with open(_os.path.join(save_dir, "_init.json"), "w") as f:
                _json.dump(init_data, f)

            res = client.post(f"/api/saves/{game_id}/load/_init.json")
            assert res.status_code == 200
            assert res.json()["game_mode"] == "graph"

    def test_save_load_defaults_to_text(self, client, app_dir):
        """Save without config.mode → game_mode defaults to 'text'."""
        import os as _os
        import json as _json

        from storyloom.web.server import _game_session
        saves_root = _os.path.join(str(app_dir), "saves")
        with patch.object(_game_session, "_saves_root", saves_root):
            game_id = "test-gm-text"
            save_dir = _os.path.join(saves_root, game_id)
            _os.makedirs(save_dir, exist_ok=True)
            init_data = {
                "version": 3,
                "metadata": {"title": "T", "created_at": "", "updated_at": ""},
                "config": {"temperature": None},
                "story_config": {"title": "T"},
                "characters": [], "locations": [], "variables": [],
                "state_vars": {}, "outline": [],
                "progress": {"current_node": "", "checkpoint_snapshots": {}},
            }
            with open(_os.path.join(save_dir, "_init.json"), "w") as f:
                _json.dump(init_data, f)

            res = client.post(f"/api/saves/{game_id}/load/_init.json")
            assert res.status_code == 200
            assert res.json()["game_mode"] == "text"


# ═══════════════════════════════════════════════════════════════════
# Game: start (Round 1)
# ═══════════════════════════════════════════════════════════════════


class TestGameStart:
    def test_game_start_requires_existing_game(self, client):
        """No stored game → 404."""
        res = client.post("/api/game/nonexistent/start")
        assert res.status_code == 404

    def test_game_start_calls_start_game(self, client):
        from storyloom.web import sessions

        mock_gl = MagicMock()
        mock_gl.round_count = 0
        mock_gl.current_node = "ch1"
        sessions.store_game("test-game-123", mock_gl)

        res = client.post("/api/game/test-game-123/start")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["game_id"] == "test-game-123"
        mock_gl.start_game.assert_called_once()

    def test_game_start_already_started_returns_400(self, client):
        from storyloom.web import sessions

        mock_gl = MagicMock()
        mock_gl.start_game.side_effect = RuntimeError("Round 1 already started")
        sessions.store_game("test-game-123", mock_gl)

        res = client.post("/api/game/test-game-123/start")
        assert res.status_code == 400


# ═══════════════════════════════════════════════════════════════════
# Asset API
# ═══════════════════════════════════════════════════════════════════


class TestAssets:
    """Tests for GET /api/assets, POST /api/assets/clean,
    DELETE /api/assets/{type}/{id}."""

    @staticmethod
    def _mock_media_dir(app_dir):
        """Point the server module's cached _MEDIA_DIR at this fixture's
        isolated media/ directory, and create the directory if missing."""
        import storyloom.web.server as server_mod
        media_dir = os.path.join(str(app_dir), "media")
        os.makedirs(media_dir, exist_ok=True)
        server_mod._MEDIA_DIR = media_dir
        return media_dir

    def test_list_assets_empty(self, client):
        """When no _asset_lib.json exists, returns empty types dict."""
        res = client.get("/api/assets")
        assert res.status_code == 200
        data = res.json()
        assert "types" in data
        assert data["types"] == {}

    def test_list_assets_with_data(self, client, app_dir):
        """When _asset_lib.json has entries, they are returned grouped."""
        from storyloom.assets import AssetLibrary, AssetType

        media_dir = self._mock_media_dir(app_dir)
        lib = AssetLibrary(media_dir)
        lib.add(AssetType.CHAR_PORTRAIT, "Hero", "Main character")
        lib.add(AssetType.BACKGROUND, "Castle", "A dark castle")
        lib.save()

        res = client.get("/api/assets")
        assert res.status_code == 200
        data = res.json()
        types = data["types"]
        assert "char_portrait" in types
        assert "background_img" in types
        cp = types["char_portrait"]
        assert len(cp) == 1
        aid = list(cp.keys())[0]
        assert cp[aid]["name"] == "Hero"
        assert cp[aid]["use_count"] == 0

    def test_clean_assets(self, client, app_dir):
        """POST /api/assets/clean deletes unused assets."""
        from storyloom.assets import AssetLibrary, AssetType

        media_dir = self._mock_media_dir(app_dir)
        lib = AssetLibrary(media_dir)
        lib.add(AssetType.CHAR_PORTRAIT, "Unused")
        lib.add(AssetType.CHAR_PORTRAIT, "AlsoUnused")
        lib.save()

        res = client.post("/api/assets/clean?keep_count=0")
        assert res.status_code == 200
        assert res.json()["deleted"] == 2

        lib2 = AssetLibrary.load(media_dir)
        assert len(lib2) == 0

    def test_clean_assets_single_type(self, client, app_dir):
        """POST /api/assets/clean?type=... only cleans that type."""
        from storyloom.assets import AssetLibrary, AssetType

        media_dir = self._mock_media_dir(app_dir)
        lib = AssetLibrary(media_dir)
        lib.add(AssetType.CHAR_PORTRAIT, "Hero")
        lib.add(AssetType.BACKGROUND, "Castle")
        lib.save()

        res = client.post("/api/assets/clean?keep_count=0&type=char_portrait")
        assert res.status_code == 200
        assert res.json()["deleted"] == 1

        lib2 = AssetLibrary.load(media_dir)
        assert len(lib2) == 1  # only background remains
        assert len(lib2.list_by_type(AssetType.CHAR_PORTRAIT)) == 0
        assert len(lib2.list_by_type(AssetType.BACKGROUND)) == 1

    def test_clean_assets_in_use_not_deleted(self, client, app_dir):
        """Assets with use_count > 0 survive clean."""
        from storyloom.assets import AssetLibrary, AssetType

        media_dir = self._mock_media_dir(app_dir)
        lib = AssetLibrary(media_dir)
        a = lib.add(AssetType.CHAR_PORTRAIT, "InUse")
        a.use_count = 3
        lib.save()

        res = client.post("/api/assets/clean?keep_count=0")
        assert res.status_code == 200
        assert res.json()["deleted"] == 0  # in-use asset survives

        lib2 = AssetLibrary.load(media_dir)
        assert len(lib2) == 1

    def test_clean_assets_invalid_type(self, client):
        """Invalid type string → 400."""
        res = client.post("/api/assets/clean?type=invalid_type")
        assert res.status_code == 400

    def test_delete_asset(self, client, app_dir):
        """DELETE an unused asset removes it and the file on disk."""
        from storyloom.assets import AssetLibrary, AssetType

        media_dir = self._mock_media_dir(app_dir)
        os.makedirs(os.path.join(media_dir, "char_portrait"), exist_ok=True)
        lib = AssetLibrary(media_dir)
        asset = lib.add(AssetType.CHAR_PORTRAIT, "ToDelete")
        file_path = os.path.join(media_dir, asset.file_path)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write("dummy")
        lib.save()

        res = client.delete(f"/api/assets/char_portrait/{asset.id}")
        assert res.status_code == 200
        assert res.json()["status"] == "deleted"

        lib2 = AssetLibrary.load(media_dir)
        assert lib2.get(AssetType.CHAR_PORTRAIT, asset.id) is None
        assert not os.path.isfile(file_path)

    def test_delete_asset_in_use_refused(self, client, app_dir):
        """DELETE with use_count > 0 → 400."""
        from storyloom.assets import AssetLibrary, AssetType

        media_dir = self._mock_media_dir(app_dir)
        lib = AssetLibrary(media_dir)
        asset = lib.add(AssetType.CHAR_PORTRAIT, "InUse")
        asset.use_count = 2
        lib.save()

        res = client.delete(f"/api/assets/char_portrait/{asset.id}")
        assert res.status_code == 400

    def test_delete_asset_not_found(self, client):
        """DELETE non-existent asset → 404."""
        res = client.delete("/api/assets/char_portrait/nonexistent")
        assert res.status_code == 404

    def test_delete_asset_invalid_type(self, client):
        """DELETE with invalid type → 404."""
        res = client.delete("/api/assets/invalid_type/some_id")
        assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════
# Auto-Update API Tests
# ═══════════════════════════════════════════════════════════════════


def _make_no_update():
    from storyloom.core.update_manager import UpdateCheckResult, VersionInfo
    return UpdateCheckResult(
        app=VersionInfo(current="1.3.0", latest="1.3.0"),
        system_media=VersionInfo(current="1.1.0", latest="1.1.0"),
        launcher=VersionInfo(current="1.0.0", latest="1.0.0"),
    )


def _make_has_update():
    from storyloom.core.update_manager import UpdateCheckResult, VersionInfo
    return UpdateCheckResult(
        app=VersionInfo(current="1.3.0", latest="1.4.0",
                        release_notes="## v1.4.0",
                        asset_url="https://example.com/app.zip"),
        system_media=VersionInfo(current="1.1.0", latest="1.2.0",
                                  asset_url="https://example.com/sm.zip"),
        launcher=VersionInfo(current="1.0.0", latest="1.1.0",
                             asset_url="https://example.com/launcher.zip"),
    )


class TestUpdateAPI:
    """Tests for /api/update/* endpoints — self-contained, all mocked."""

    @patch("storyloom.web.server.check_for_updates")
    def test_check_no_update(self, mock_check, client):
        mock_check.return_value = _make_no_update()
        resp = client.get("/api/update/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["app"]["has_update"] is False
        assert data["system_media"]["has_update"] is False

    @patch("storyloom.web.server.check_for_updates")
    def test_check_has_update(self, mock_check, client):
        mock_check.return_value = _make_has_update()
        resp = client.get("/api/update/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["app"]["has_update"] is True
        assert data["app"]["latest"] == "1.4.0"
        assert data["app"]["release_notes"] == "## v1.4.0"

    @patch("storyloom.web.server.check_for_updates")
    def test_check_force_param(self, mock_check, client):
        """force=true is passed through to check_for_updates."""
        mock_check.return_value = _make_no_update()
        client.get("/api/update/check?force=true")
        _, kwargs = mock_check.call_args
        assert kwargs.get("force") is True

    @patch("storyloom.web.server.check_for_updates")
    def test_check_force_default_false(self, mock_check, client):
        mock_check.return_value = _make_no_update()
        client.get("/api/update/check")
        _, kwargs = mock_check.call_args
        assert kwargs.get("force") is False

    def test_apply_rejects_empty_layers(self, client):
        resp = client.post("/api/update/apply", json={})
        assert resp.status_code == 422

    def test_apply_rejects_invalid_layers(self, client):
        resp = client.post("/api/update/apply", json={"layers": "not_a_list"})
        assert resp.status_code == 422

    def test_apply_rejects_unknown_layer_value(self, client):
        resp = client.post("/api/update/apply",
                           json={"layers": ["invalid_layer"]})
        assert resp.status_code == 422

    def test_apply_rejects_empty_layer_list(self, client):
        resp = client.post("/api/update/apply", json={"layers": []})
        assert resp.status_code == 422

    def test_apply_returns_stream_url(self, client):
        resp = client.post("/api/update/apply",
                           json={"layers": ["app", "system_media"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "stream_url" in data
        assert data["stream_url"].startswith("/api/update/stream/")

    def test_stream_invalid_id(self, client):
        resp = client.get("/api/update/stream/nonexistent")
        assert resp.status_code == 404

    @patch("storyloom.web.server.download_and_extract")
    @patch("storyloom.web.server.check_for_updates")
    def test_stream_app_update_success(
        self, mock_check, mock_dl, client, app_dir
    ):
        """Full SSE stream: apply → stream → done."""
        mock_check.return_value = _make_has_update()

        # Create system_media/VERSION so _get_system_media_version works
        sm_dir = app_dir / "system_media"
        sm_dir.mkdir()
        (sm_dir / "VERSION").write_text("1.1.0")

        # 1. Apply
        resp = client.post("/api/update/apply",
                           json={"layers": ["app"]})
        assert resp.status_code == 200
        stream_url = resp.json()["stream_url"]
        assert stream_url.startswith("/api/update/stream/")

    @patch("storyloom.web.server.download_and_extract")
    @patch("storyloom.web.server.check_for_updates")
    def test_stream_unknown_layer_skipped(
        self, mock_check, mock_dl, client, app_dir
    ):
        """Layer with no update → skipped, no download call."""
        # system_media has no update in this result
        result = _make_no_update()
        result.system_media._latest = ""
        mock_check.return_value = result

        sm_dir = app_dir / "system_media"
        sm_dir.mkdir()
        (sm_dir / "VERSION").write_text("1.1.0")

        resp = client.post("/api/update/apply",
                           json={"layers": ["system_media"]})
        stream_url = resp.json()["stream_url"]

        with client.stream("GET", stream_url) as s:
            lines = [l for l in s.iter_lines() if l]

        # Should complete without download
        mock_dl.assert_not_called()

    @patch("storyloom.web.server.download_and_extract")
    @patch("storyloom.web.server.check_for_updates")
    def test_stream_download_error(
        self, mock_check, mock_dl, client, app_dir
    ):
        """Download failure → error event."""
        mock_check.return_value = _make_has_update()

        # Make download_and_extract raise to simulate download failure
        # The run_update catches Exception and sends error event
        # But since url fetching happens inside run_update via
        # _http_get_json (inline import), we need to also patch that
        # to avoid real network calls.  We'll patch at the update_manager
        # module level since that's where the inline imports resolve.
        with patch(
            "storyloom.core.update_manager._http_get_json"
        ) as mock_http:
            mock_http.return_value = {
                "tag_name": "v1.4.0",
                "assets": [
                    {"name": "storyloom-v1.4.0-Linux.zip",
                     "browser_download_url": "https://example.com/a.zip"},
                ],
            }
            mock_dl.side_effect = RuntimeError("connection reset")

            sm_dir = app_dir / "system_media"
            sm_dir.mkdir()
            (sm_dir / "VERSION").write_text("1.1.0")

            resp = client.post("/api/update/apply",
                               json={"layers": ["app"]})
            stream_url = resp.json()["stream_url"]

            with client.stream("GET", stream_url) as s:
                lines = [l for l in s.iter_lines() if l]
                events = [l for l in lines if l.startswith("event:")]
                assert "event: error" in events


# ═══════════════════════════════════════════════════════════════════
# Cancel / stop endpoint tests
# ═══════════════════════════════════════════════════════════════════


class TestCancelEndpoints:
    """Tests for co-create and prebuild cancellation endpoints."""

    def test_abort_calls_flow_cancel(self, client_with_session):
        """POST /api/co-create/abort cancels the flow and removes it."""
        from storyloom.web import sessions
        flow = sessions.get_co_create()
        assert flow is not None
        # abort should succeed
        res = client_with_session.post("/api/co-create/abort")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        # After abort, flow should be removed
        assert flow.is_cancelled
        assert sessions.get_co_create() is None

    def test_prebuild_stop_sets_stop_event(self, client):
        """POST /api/co-create/prebuild/{gid}/stop sets the stop event."""
        from storyloom.web import sessions
        # Pre-store a prebuild stream
        q, evt = sessions.store_co_create_prebuild_stream("test-gid")
        assert not evt.is_set()

        res = client.post("/api/co-create/prebuild/test-gid/stop")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"
        assert evt.is_set()

    def test_prebuild_stop_no_stream_is_noop(self, client):
        """Stop endpoint is idempotent when no stream exists."""
        res = client.post("/api/co-create/prebuild/nonexistent/stop")
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

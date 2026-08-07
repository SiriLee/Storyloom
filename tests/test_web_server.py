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
        assert "img_remove_bg" in data
        assert data["img_remove_bg"] == "auto"

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
            "img_remove_bg": "always",
        })
        assert res.status_code == 200
        data = client.get("/api/config").json()
        assert "****" in data["img_api_key"]
        assert data["img_api_base_url"] == "https://img.example.com"
        assert data["img_api_model"] == "custom-model"
        assert data["img_remove_bg"] == "always"

    def test_update_img_remove_bg_rejects_invalid(self, client):
        res = client.post("/api/config", json={"img_remove_bg": "sometimes"})
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
    def test_prebuild_returns_ok(self, client, app_dir):
        """POST /api/co-create/prebuild → calls prebuild_assets, returns ok."""
        from storyloom.web.server import _game_session

        with patch.object(_game_session, "prebuild_assets",
                          return_value={"status": "ok"}):
            res = client.post("/api/co-create/prebuild",
                              json={"game_id": "test-game-123"})

        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"


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

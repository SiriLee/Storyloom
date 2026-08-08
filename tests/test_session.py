"""Tests for GameSession orchestrator."""
import os
import tempfile

import pytest
from unittest.mock import Mock

from storyloom.core.session import GameSession
from storyloom.core.co_create import CoCreateFlow
from storyloom.core.game_loop import GameLoop
from storyloom.user_config import UserConfig
from storyloom.io.api_client import ApiClient


def _test_api_client():
    """Return an ApiClient with test credentials (no disk I/O)."""
    cfg = UserConfig()
    cfg.api_key = "sk-test"
    cfg.api_base_url = "https://api.test.com"
    return ApiClient(cfg)


SAMPLE_STORY_CONFIG = {
    "tier": "short",
    "title": "test-story",
    "language": "zh-CN",
    "premise": "A test story for unit testing.",
}

SAMPLE_RESULT = {
    "story_config": SAMPLE_STORY_CONFIG,
    "characters": [
        {"name": "Tester", "role": "protagonist", "description": "A brave tester", "appearance": "Plain"},
    ],
    "locations": [
        {"id": "test_loc", "name": "Test Location", "description": "A test place"},
    ],
    "variables": [
        {"name": "hp", "type": "number", "initial": 80},
    ],
    "outline": [
        {"id": "ch1", "title": "Start", "goal": "Begin", "routes": []},
    ],
    "outline_text": "ch1 [active] — Start：Begin",
}


class TestGameSessionInit:
    def test_accepts_explicit_api_client(self):
        api = _test_api_client()
        session = GameSession(api_client=api)
        assert session._api_client is api

    def test_game_loop_is_none_initially(self):
        session = GameSession(api_client=_test_api_client())
        assert session.game_loop is None


class TestGameSessionSaveManagement:
    @pytest.fixture
    def root(self):
        with tempfile.TemporaryDirectory() as d:
            yield d

    def test_list_games_delegates(self, root):
        session = GameSession(api_client=_test_api_client(), saves_dir=root)
        result = session.list_games()
        assert result == []  # empty saves root

    def test_list_saves_requires_game_id(self, root):
        session = GameSession(api_client=_test_api_client(), saves_dir=root)
        result = session.list_saves("nonexistent_game")
        assert result == []

    def test_delete_game_returns_false_for_nonexistent(self, root):
        session = GameSession(api_client=_test_api_client(), saves_dir=root)
        assert session.delete_game("nonexistent") is False

    def test_delete_save_returns_false_for_nonexistent(self, root):
        session = GameSession(api_client=_test_api_client(), saves_dir=root)
        assert session.delete_save("nonexistent", "_init.json") is False


class TestGameSessionLifecycle:
    def test_new_co_create_returns_flow(self):
        mock_api = Mock()
        session = GameSession(api_client=mock_api)
        flow = session.new_co_create()
        assert isinstance(flow, CoCreateFlow)
        assert flow._api is mock_api

    def test_start_game_returns_game_loop_and_game_id(self):
        with tempfile.TemporaryDirectory() as root:
            session = GameSession(api_client=Mock(), saves_dir=root)

            gl, game_id = session.start_game(SAMPLE_RESULT)

            assert isinstance(gl, GameLoop)
            assert game_id.startswith("test-story_")
            assert session.game_loop is gl
            # _init.json should be created
            init_path = os.path.join(root, game_id, "_init.json")
            assert os.path.exists(init_path)

    def test_load_game_restores_game_loop(self):
        with tempfile.TemporaryDirectory() as root:
            session = GameSession(api_client=Mock(), saves_dir=root)

            # Create a game first (writes _init.json)
            _, game_id = session.start_game(SAMPLE_RESULT)

            # Load it back
            gl = session.load_game(game_id, "_init.json")
            assert isinstance(gl, GameLoop)

    def test_load_game_nonexistent_raises(self):
        with tempfile.TemporaryDirectory() as root:
            session = GameSession(api_client=Mock(), saves_dir=root)
            with pytest.raises(FileNotFoundError):
                session.load_game("no_such_game", "_init.json")

    def test_init_json_writes_default_text_mode(self):
        """_build_init_dict defaults to 'text' mode when game_mode not passed."""
        import json
        import os
        import tempfile
        data = dict(SAMPLE_RESULT)
        with tempfile.TemporaryDirectory() as root:
            session = GameSession(api_client=Mock(), saves_dir=root)
            gl, game_id = session.start_game(data)
            init_path = os.path.join(root, game_id, "_init.json")
            saved = json.loads(open(init_path).read())
            assert saved["config"]["mode"] == "text"

    def test_init_json_writes_graph_mode_when_passed(self):
        """_build_init_dict writes 'graph' when game_mode='graph' is passed."""
        import json
        import os
        import tempfile

        data = dict(SAMPLE_RESULT)
        with tempfile.TemporaryDirectory() as root:
            session = GameSession(api_client=Mock(), saves_dir=root)
            gl, game_id = session.start_game(data, game_mode="graph")
            init_path = os.path.join(root, game_id, "_init.json")
            saved = json.loads(open(init_path).read())
            assert saved["config"]["mode"] == "graph"

    def test_start_game_graph_mode_mounts_pipeline(self):
        """start_game(game_mode='graph') calls mount_graph_pipeline."""
        with tempfile.TemporaryDirectory() as root:
            session = GameSession(api_client=Mock(), saves_dir=root)
            gl, game_id = session.start_game(SAMPLE_RESULT, game_mode="graph")
            assert gl._roster is not None
            assert gl._task_pool is not None
            assert gl._match_processor is not None

    def test_start_game_text_mode_does_not_mount(self):
        """start_game(game_mode='text') → all graph attrs stay None."""
        with tempfile.TemporaryDirectory() as root:
            session = GameSession(api_client=Mock(), saves_dir=root)
            gl, game_id = session.start_game(SAMPLE_RESULT, game_mode="text")
            assert gl._roster is None
            assert gl._task_pool is None
            assert gl._match_processor is None

    def test_load_game_graph_mode_mounts_pipeline(self):
        """load_game reads config.mode='graph' → mount_graph_pipeline called."""
        with tempfile.TemporaryDirectory() as root:
            session = GameSession(api_client=Mock(), saves_dir=root)
            _, game_id = session.start_game(SAMPLE_RESULT, game_mode="graph")
            # Load back — should re-mount graph pipeline
            gl = session.load_game(game_id, "_init.json")
            assert gl._roster is not None
            assert gl._task_pool is not None
            assert gl._match_processor is not None

    def test_load_game_text_mode_does_not_mount(self):
        """load_game reads config.mode='text' → all graph attrs stay None."""
        with tempfile.TemporaryDirectory() as root:
            session = GameSession(api_client=Mock(), saves_dir=root)
            _, game_id = session.start_game(SAMPLE_RESULT, game_mode="text")
            gl = session.load_game(game_id, "_init.json")
            assert gl._roster is None
            assert gl._task_pool is None
            assert gl._match_processor is None

    def test_checkpoint_save_preserves_mode(self):
        """start_game(graph) → to_save_dict() writes config.mode='graph'.
        Loading that save data back → from_save_dict reads mode → graph."""
        with tempfile.TemporaryDirectory() as root:
            session = GameSession(api_client=Mock(), saves_dir=root)
            gl, game_id = session.start_game(SAMPLE_RESULT, game_mode="graph")

            # Simulate a checkpoint save
            save_data = gl.to_save_dict()
            assert save_data["config"]["mode"] == "graph"

            # Load back from the save data (round-trip)
            gl2 = session.load_game(game_id, "_init.json")
            assert gl2._roster is not None
            assert gl2._game_mode == "graph"


# ═══════════════════════════════════════════════════════════════════
# §7.7: prebuild_assets()
# ═══════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════
# §7.8c DELETE BLOCK START — removed when prebuild_assets() replaced
# ═══════════════════════════════════════════════════════════════════

class TestPrebuildAssets:
    """§7.7: material pre-build — temporary stub, §7.8c replaces with AI."""

    # Self-contained test data — does not depend on SAMPLE_RESULT
    _DATA = {
        "story_config": {"title": "test"},
        "characters": [
            {"name": "Kael", "description": "A warrior"},
            {"name": "Lira", "description": "A mage"},
        ],
        "locations": [
            {"name": "Forest", "description": "Dark woods"},
            {"name": "Castle", "description": "Ancient fortress"},
        ],
        "variables": [],
        "outline": [],
        "outline_text": "",
    }

    def test_prebuild_seeds_roster_from_story_config(self, tmp_path):
        """prebuild_assets() calls _init_stub_roster and persists roster."""
        from storyloom.assets import AssetType

        api = _test_api_client()
        session = GameSession(api, saves_dir=str(tmp_path))
        data = dict(self._DATA)  # copy — start_game mutates it

        gl, game_id = session.start_game(data, game_mode="graph")
        assert gl._roster is not None

        result = session.prebuild_assets(game_id)
        assert result == {"status": "ok"}

        # prebuild_assets() loads a new GameLoop internally — use it
        gl2 = session.game_loop
        assert gl2 is not None
        roster = gl2._roster
        assert roster.lookup(AssetType.CHAR_PORTRAIT, "Kael").target == "stub_default_portrait"
        assert roster.lookup(AssetType.CHAR_PORTRAIT, "Lira").target == "stub_default_portrait"
        assert roster.lookup(AssetType.BACKGROUND, "Forest").target == "stub_default_background"
        assert roster.lookup(AssetType.BACKGROUND, "Castle").target == "stub_default_background"

        import os as _os
        roster_path = _os.path.join(session._saves_root, game_id, "_asset_roster.json")
        assert _os.path.isfile(roster_path)

    def test_prebuild_idempotent(self, tmp_path):
        """Calling prebuild twice is safe."""
        api = _test_api_client()
        session = GameSession(api, saves_dir=str(tmp_path))

        gl, game_id = session.start_game(dict(self._DATA), game_mode="graph")
        assert gl._roster is not None

        first = session.prebuild_assets(game_id)
        second = session.prebuild_assets(game_id)
        assert first == second == {"status": "ok"}

    def test_prebuild_text_mode_is_noop(self, tmp_path):
        """prebuild_assets() on text-mode game returns ok (roster is None)."""
        api = _test_api_client()
        session = GameSession(api, saves_dir=str(tmp_path))

        gl, game_id = session.start_game(dict(self._DATA), game_mode="text")
        assert gl._roster is None

        data = session.prebuild_assets(game_id)
        assert data == {"status": "ok"}

# ═══════════════════════════════════════════════════════════════════
# §7.8c DELETE BLOCK END
# ═══════════════════════════════════════════════════════════════════

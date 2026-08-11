"""GameSession — lightweight lifecycle coordinator for the Storyloom engine.

Owns ApiClient. Wires CoCreateFlow → GameLoop transitions so the UI
doesn't need to know internal dependency order.

New game and load-game converge on the same code path::

    start_game(result) → _init.json → load_game(game_id, "_init.json")
    load_game(game_id, filename) → from_save_dict() → GameLoop

UI retains full control over rendering and interaction flow.
"""

import copy
import os
import time

from storyloom.config import DEFAULT_SAVES_DIR, SAVE_VERSION, GLOBAL_SCOPE
from storyloom.io.api_client import ApiClient
from storyloom.core.save_manager import SaveManager
from storyloom.core.co_create import CoCreateFlow
from storyloom.core.game_loop import GameLoop, GameState


class GameSession:
    """Lightweight lifecycle coordinator.

    Does NOT control UI flow. UI calls methods at its own pace.

    Usage::

        session = GameSession()
        flow = session.new_co_create()
        # ... drive flow ...
        gl, game_id = session.start_game(flow.result)
        # ... drive gl.start_game() / gl.stream_round() ...
        # Or load:
        gl = session.load_game("game_id", "_init.json")
    """

    def __init__(self, api_client: ApiClient | None = None,
                 saves_dir: str = DEFAULT_SAVES_DIR):
        self._api_client = api_client if api_client is not None else ApiClient()
        self._saves_root = saves_dir
        self._game_loop: GameLoop | None = None

    # ── Lifecycle ──────────────────────────────────────────────────

    def new_co_create(self) -> CoCreateFlow:
        return CoCreateFlow(self._api_client)

    def start_game(self, data: dict, game_mode: str = "text") -> tuple[GameLoop, str]:
        """Create a new game from co-creation result dict.

        1. Create per-game directory under ``saves/``.
        2. Write ``_init.json`` directly from the result dict.
        3. Load via the unified ``load_game()`` path.

        Args:
            data: Dict returned by ``CoCreateFlow.generate()`` — keys:
                ``story_config``, ``characters``, ``locations``,
                ``variables``, ``outline``, ``outline_text``.
            game_mode: ``"text"`` or ``"graph"`` — written to
                ``_init.json`` ``config.mode``.  Default ``"text"``.

        Returns:
            ``(GameLoop, game_id)`` — UI uses *game_id* for subsequent
            save operations (list, delete, etc.).
        """
        title = data["story_config"].get("title", "untitled")
        game_dir, game_id, created_at = SaveManager.create_game(
            self._saves_root, title
        )

        init_data = self._build_init_dict(data, created_at, game_mode=game_mode)
        SaveManager(game_dir).save(init_data)  # cp_title=None → _init.json

        gl = self.load_game(game_id, "_init.json")
        return gl, game_id

    def prebuild_assets(self, game_id: str, game_loop=None,
                        cancel_event=None):
        """Run AI material pre-build for a graph-mode game.  (§7.8c)

        Loads the game (triggers ``mount_graph_pipeline``), then runs the
        full pre-build pipeline: batch LLM selection → AI image generation
        → force-select fallback → roster persistence.

        Called by the UI after story generation completes, BEFORE entering
        the game loop.  Yields progress events for the UI to display.

        Args:
            game_id: Game directory name under ``saves/``.
            game_loop: Optional existing ``GameLoop`` to reuse.  When
                provided, skips ``load_game()`` and uses this instance's
                roster + library.  When ``None`` (default), loads from
                disk (backward-compatible for tests).
            cancel_event: Optional ``threading.Event`` for cooperative
                cancellation.  Passed through to ``Prebuilder`` so the
                SSE event_generator can stop the pipeline on disconnect.

        Yields:
            ``{"type": "prebuild_progress", "phase": str, ...}``
            ``{"type": "prebuild_complete", "success": bool, ...}``
            ``{"type": "prebuild_cancelled"}``
        """
        sm = SaveManager(os.path.join(self._saves_root, game_id))
        data = sm.load("_init.json")

        if game_loop is not None:
            gl = game_loop
        else:
            gl = self.load_game(game_id, "_init.json")

        if gl._roster is None:
            yield {
                "type": "prebuild_complete",
                "success": False,
                "results": [],
                "errors": ["Graph-mode pipeline not mounted"],
                "warnings": [],
            }
            return

        from storyloom.core.prebuild import Prebuilder
        from storyloom.io._types import RemoveBgPolicy
        from storyloom.io.img_api_client import ImgApiClient
        from storyloom.user_config import UserConfig

        # Create ImgApiClient instances with appropriate bg-removal policies
        raw_cfg = getattr(self._api_client, '_cfg', None)
        if raw_cfg is None or not isinstance(raw_cfg, UserConfig):
            raw_cfg = UserConfig()
        portrait_policy = RemoveBgPolicy(raw_cfg.portrait_remove_bg)
        img_enabled = raw_cfg.img_generation_enabled

        prebuilder = Prebuilder(
            api_client=self._api_client,
            img_client_portrait=ImgApiClient(
                raw_cfg, remove_bg=portrait_policy,
            ),
            img_client_background=ImgApiClient(
                raw_cfg, remove_bg=RemoveBgPolicy.NEVER,
            ),
            library=gl._roster.library,
            img_generation_enabled=img_enabled,
            cancel_event=cancel_event,
        )

        roster_path = os.path.join(self._saves_root, game_id, "_asset_roster.json")

        for event in prebuilder.build(
            data.get("characters", []),
            data.get("locations", []),
            gl._roster,
        ):
            # Save roster BEFORE yielding prebuild_complete — the SSE
            # consumer abandons the generator on prebuild_complete, so
            # any code after the yield would never execute.
            if event["type"] == "prebuild_complete" and event["success"]:
                gl._roster.save(roster_path)
            # prebuild_cancelled — skip roster save, skip library save
            # (handled inside Prebuilder.build()), just forward the event.
            yield event

    def load_game(self, game_id: str, filename: str) -> GameLoop:
        """Load a save file and return a ready-to-play ``GameLoop``.

        Args:
            game_id: Game directory name under ``saves/``.
            filename: Save file name (e.g. ``_init.json`` or
                      ``萌芽之春_20260713T133038Z.json``).
        """
        sm = SaveManager(os.path.join(self._saves_root, game_id))
        data = sm.load(filename)
        return self._load_from_data(game_id, filename, data)

    def _load_from_data(
        self, game_id: str, filename: str, data: dict
    ) -> GameLoop:
        """Reconstruct a ``GameLoop`` from already-loaded save data.

        Internal — called by :meth:`load_game` and by the web server's
        ``save_start`` endpoint that needs both the raw data (for the
        HTTP response) and the GameLoop (for the server-side session).
        """
        sm = SaveManager(os.path.join(self._saves_root, game_id))
        gl = GameLoop.from_save_dict(data, self._api_client)
        gl.set_save_manager(sm)

        # ── §7.6: graph mode — mount Task pipeline ──────────────────
        # Mode is stored in every save file (config.mode).  from_save_dict
        # reads it into gl._game_mode so checkpoint loads work identically.
        if gl._game_mode == "graph":
            gl.mount_graph_pipeline(game_id, self._saves_root)

        self._game_loop = gl
        # Track last played so "Continue" can find this save in O(1).
        title = data.get("metadata", {}).get(
            "title", data.get("story_config", {}).get("title", "")
        )
        SaveManager.write_last_played(
            self._saves_root, game_id, title, filename,
        )
        return gl

    def read_save(self, game_id: str, filename: str) -> dict:
        """Read a save file and return its raw data.

        Lightweight counterpart to :meth:`load_game`.  Use when the
        caller only needs save contents (e.g. preview page reading
        ``story_config``), not a fully reconstructed ``GameLoop``.

        Raises:
            FileNotFoundError: Save file or game directory not found.
            ValueError: Save file is invalid (outdated version, corrupt
                        JSON, or structural issues).  The file is NOT
                        deleted — the caller decides whether to keep it.
        """
        sm = SaveManager(os.path.join(self._saves_root, game_id))
        return sm.load(filename)

    # ── Save management ───────────────────────────────────────────

    def list_games(self, enrich_last_played: bool = False) -> list[dict]:
        """List all games under ``saves/``.

        Args:
            enrich_last_played: When True, each game dict includes
                ``last_played_at`` and the result is sorted by it
                descending (most recent first).

        Returns:
            List of ``{game_id, title, language, premise, tier,
            created_at, save_count, mode[, last_played_at]}`` dicts.
        """
        games = SaveManager.list_games(self._saves_root, enrich=enrich_last_played)
        if enrich_last_played:
            games.sort(key=lambda g: g.get("last_played_at", ""), reverse=True)
        return games

    def list_saves(self, game_id: str) -> list[dict]:
        """List all saves in a game directory.

        Returns:
            List of ``{filename, checkpoint_title, checkpoint_node,
            round, saved_at, current_node}`` dicts.
        """
        return SaveManager.list_saves_for_game(self._saves_root, game_id)

    def delete_game(self, game_id: str) -> bool:
        """Delete an entire game directory. Returns True if deleted.

        Loads the roster first and clears it to decrement ``use_count``
        on every referenced asset in the global ``AssetLibrary``, then
        persists the library BEFORE removing the directory.  Cleanup is
        best-effort — failures are logged but never block deletion.
        """
        roster_path = os.path.join(self._saves_root, game_id, "_asset_roster.json")
        if os.path.isfile(roster_path):
            try:
                from storyloom.assets import GameAssetRoster
                # GameAssetRoster.load() takes a library parameter;
                # pass a throwaway instance — clear() calls
                # library.decrease_usage() on the same instance, so
                # use counts are decremented in the real _asset_lib.json.
                from storyloom.assets import AssetLibrary
                from storyloom.config import DEFAULT_MEDIA_DIR
                _media = os.environ.get(
                    "STORYLOOM_MEDIA_DIR",
                    os.path.join(self._saves_root, "..", DEFAULT_MEDIA_DIR),
                )
                library = AssetLibrary.load(os.path.normpath(_media))
                roster = GameAssetRoster.load(roster_path, library, game_id)
                roster.clear()
                library.save()
            except Exception as e:
                import logging
                logging.getLogger("storyloom").warning(
                    "delete_game: roster cleanup failed for %s: %s", game_id, e
                )

        return SaveManager.delete_game(self._saves_root, game_id)

    def delete_save(self, game_id: str, filename: str) -> bool:
        """Delete a single save file. Returns True if deleted."""
        sm = SaveManager(os.path.join(self._saves_root, game_id))
        return sm.delete(filename)

    # ── State ─────────────────────────────────────────────────────

    @property
    def game_loop(self) -> GameLoop | None:
        return self._game_loop

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _build_init_dict(data: dict, created_at: str, game_mode: str = "text") -> dict:
        """Build ``_init.json`` save dict directly from co-creation result.

        No ``GameLoop`` involvement — pure data assembly.
        Format matches ``GameLoop.to_save_dict()`` so that
        ``from_save_dict()`` can consume it identically.

        *data* is the dict returned by ``CoCreateFlow.generate()``.
        *game_mode* is written to ``config.mode`` (``"text"`` or ``"graph"``).
        """
        sc = copy.deepcopy(data["story_config"])
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        title = sc.get("title", "untitled")

        # Initialize nested state_vars from variable definitions
        state_vars: dict[str, dict[str, int | str]] = {}
        for v in data.get("variables", []):
            scope = v.get("scope") or GLOBAL_SCOPE
            state_vars.setdefault(scope, {})[v["name"]] = v["initial"]

        # Convert outline nodes to save format
        first_node_id = ""
        outline_for_save = []
        for i, node in enumerate(data.get("outline", [])):
            nid = node.get("id", "")
            if i == 0:
                first_node_id = nid
            outline_for_save.append({
                "node_id": nid,
                "title": node.get("title", ""),
                "goal": node.get("goal", ""),
                "status": "active" if i == 0 else "pending",
                "summary": "",
                "branches": [
                    {"condition": r.get("condition"),
                     "target": r.get("target", "")}
                    for r in node.get("routes", [])
                ],
            })

        return {
            "version": SAVE_VERSION,
            "metadata": {
                "title": title,
                "created_at": created_at,
                "updated_at": now,
            },
            "config": {
                "temperature": None,
                "mode": game_mode,
            },
            "story_config": sc,
            "characters": copy.deepcopy(data.get("characters", [])),
            "locations": copy.deepcopy(data.get("locations", [])),
            "variables": copy.deepcopy(data.get("variables", [])),
            "state_vars": state_vars,
            "outline": outline_for_save,
            "progress": {
                "current_node": first_node_id,
                "checkpoint_snapshots": {},
            },
        }

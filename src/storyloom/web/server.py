"""Storyloom Web UI — FastAPI application server.

Usage: python -m storyloom.web

Endpoint groups:
  Pages:         GET  /                                   — index page
                 GET  /health                             — health check
  Config:        GET  /api/config                         — read UserConfig properties
                 POST /api/config                         — update + cfg.save()
  Co-Create:     POST /api/co-create/start                — start Q&A session
                 POST /api/co-create/send                 — send message in Q&A
                 POST /api/co-create/retry-send           — retry failed send()
                 POST /api/co-create/generate             — gen story setup + create save
                 POST /api/co-create/retry-generate       — retry failed generate()
                 GET  /api/co-create/prebuild/{id}/stream — SSE material pre-build progress
                 POST /api/co-create/abort                — abort co-creation
  Game:          POST /api/game/{id}/start               — start Round 1 prompt
                 GET  /api/game/{id}/stream               — SSE narrative stream
                 POST /api/game/{id}/choice               — inject player choice
                 POST /api/game/{id}/retry                — retry failed API call
                 GET  /api/game/{id}/state                — sidebar state
                 GET  /api/game/{id}/adventure-log        — post-ending log (Phase 2)
  Saves:         GET    /api/saves/games                  — list all games
                 GET    /api/saves/{game_id}              — list saves in a game
                 POST   /api/saves/{game_id}/load/{filename} — load a save
                 DELETE /api/saves/{game_id}              — delete a game
                 DELETE /api/saves/{game_id}/{filename}   — delete a save
  System:        POST   /api/exit                         — graceful shutdown

SSE architecture:
    Daemon thread runs stream_round() → pushes events into Queue.
    Async endpoint drains Queue → StreamingResponse (SSE).

GameSession construction:
    UserConfig → ApiClient(config) → GameSession(api_client, saves_dir)
"""

import asyncio
import json
import logging
import os
import sys
import threading
from pathlib import Path

logger = logging.getLogger("storyloom")

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, model_validator

from storyloom.config import DEFAULT_IMG_BASE_URL, DEFAULT_MEDIA_DIR, SUPPORTED_LANGUAGES, CLEANUP_KEEP_COUNT, GITHUB_REPO_OWNER, GITHUB_REPO_NAME
from storyloom.core.co_create import CoCreateError
from storyloom.core.save_manager import SaveManager
from storyloom.core.session import GameSession
from storyloom.core.update_manager import (
    check_for_updates,
    download_and_extract,
    set_update_proxy_url,
    UpdateCheckResult,
    UpdateProgress,
)
from storyloom.i18n import init_i18n, switch_language
from storyloom.io.api_client import ApiClient
from storyloom.user_config import UserConfig
from storyloom.web import sessions
from storyloom import __version__

# ── App setup ──────────────────────────────────────────────────────

_STATIC = Path(__file__).resolve().parent / "static"

# App directory — where config.json / locale / saves / media / system_media live.
# Dev: repo root (server.py → web → storyloom → src → repo root).
# PyInstaller (new launcher layout): exe at <root>/app/storyloom-web → root = ../..
# PyInstaller (old flat layout): exe at <root>/storyloom-web → root = .
if getattr(sys, 'frozen', False):
    exe_dir = Path(sys.executable).parent
    if exe_dir.name == "app":
        _PROJECT_ROOT = exe_dir.parent
    else:
        _PROJECT_ROOT = exe_dir
else:
    _PROJECT_ROOT = Path(__file__).resolve().parents[3]
_APP_DIR = os.environ.get("STORYLOOM_APP_DIR", str(_PROJECT_ROOT))

app = FastAPI(title="Storyloom", docs_url=None, redoc_url=None)
cfg = UserConfig(_APP_DIR)
set_update_proxy_url(cfg.proxy_url)

# ── First-run bootstrap ────────────────────────────────────────────
# Ensure user data directories exist.  system_media/ is created empty
# if missing — the user downloads it later via the update UI.
for _dir in ("saves", "media", "system_media"):
    os.makedirs(os.path.join(_APP_DIR, _dir), exist_ok=True)

# ── i18n — locale lives next to the exe (inside app/) so it gets
#    replaced on update along with the binary.
if getattr(sys, 'frozen', False):
    _locale_dir = os.path.join(os.path.dirname(sys.executable), "locale")
else:
    _locale_dir = os.path.join(_APP_DIR, "locale")
init_i18n(cfg.language, locale_dir=_locale_dir)

# ── Engine wiring (mirrors dev_cli/dev_main.py) ──────────────────
_api_client = ApiClient(cfg)
_game_session = GameSession(_api_client, saves_dir=os.path.join(_APP_DIR, "saves"))

app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")

# §7.7: graph mode — serve media assets under a single /media namespace.
# User-generated assets live in media/; system assets (sys_ prefix) in
# system_media/.  The route resolves asset IDs to files without the
# frontend knowing the file extension — the server looks up the correct
# file in both directories.
from storyloom.config import DEFAULT_SYSTEM_MEDIA_DIR

_MEDIA_DIR = os.environ.get("STORYLOOM_MEDIA_DIR",
                            os.path.join(_APP_DIR, DEFAULT_MEDIA_DIR))
_SYS_MEDIA_DIR = os.environ.get("STORYLOOM_SYSTEM_MEDIA_DIR",
                                 os.path.join(_APP_DIR, DEFAULT_SYSTEM_MEDIA_DIR))

@app.get("/" + DEFAULT_MEDIA_DIR + "/{asset_type}/{asset_id}")
async def serve_media(asset_type: str, asset_id: str, thumb: str = "0"):
    """Serve an asset file by ID, checking user media then system media.

    Frontend uses a single URL pattern: ``/media/{type}/{id}`` — no
    file extension.  The route resolves the correct filesystem path
    regardless of asset type, format, or storage directory.

    Uses ``AssetType.default_extension`` as the primary lookup, then
    falls back to other common image extensions for robustness
    (manually imported files may not use the canonical format).

    When ``?thumb=<width>``, returns a WebP thumbnail of the given width
    (aspect ratio preserved).  Generated on first request and cached to
    disk as ``{id}_thumb_{width}.webp`` alongside the original.
    """
    from fastapi.responses import FileResponse
    from storyloom.assets import AssetType

    # Security: reject path traversal
    if ".." in asset_type or ".." in asset_id or "/" in asset_type or "\\" in asset_type:
        raise HTTPException(400, "Invalid asset path")

    # Build extension list: canonical first, then common fallbacks
    try:
        atype = AssetType(asset_type)
        canonical_ext = atype.default_extension
    except ValueError:
        canonical_ext = ".png"
    extensions = [canonical_ext] + [
        e for e in (".png", ".jpg", ".jpeg", ".webp")
        if e != canonical_ext
    ]

    # Thumbnail width from query param (0 or absent = full image)
    thumb_w = 0
    try:
        thumb_w = int(thumb)
    except (ValueError, TypeError):
        pass

    for base_dir in (_MEDIA_DIR, _SYS_MEDIA_DIR):
        for ext in extensions:
            path = os.path.join(base_dir, asset_type, f"{asset_id}{ext}")
            if os.path.isfile(path):
                if not thumb_w:
                    return FileResponse(
                        path,
                        headers={"Cache-Control": "public, max-age=31536000, immutable"},
                    )

                # Thumbnail path — includes width in filename for cache busting
                thumb_path = os.path.join(
                    base_dir, asset_type, f"{asset_id}_thumb_{thumb_w}.webp"
                )
                if os.path.isfile(thumb_path):
                    return FileResponse(
                        thumb_path,
                        headers={"Cache-Control": "public, max-age=31536000, immutable"},
                    )

                # Generate thumbnail on the fly
                try:
                    from PIL import Image

                    im = Image.open(path)
                    im = im.convert("RGB")
                    im.thumbnail((thumb_w, thumb_w), Image.LANCZOS)
                    im.save(thumb_path, "WEBP", quality=85)
                    return FileResponse(
                        thumb_path,
                        headers={"Cache-Control": "public, max-age=31536000, immutable"},
                    )
                except Exception:
                    # Fall back to full image if thumbnail fails
                    return FileResponse(
                        path,
                        headers={"Cache-Control": "public, max-age=31536000, immutable"},
                    )

    raise HTTPException(404, f"Asset not found: {asset_type}/{asset_id}")


@app.get("/")
async def index():
    return FileResponse(str(_STATIC / "index.html"))


@app.get("/health")
async def health():
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════
# Config — thin pass-through to UserConfig
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/config")
async def get_config():
    """Return current config.  api_key and img_api_key are masked —
       only first 4 and last 4 characters are shown."""
    def _mask(k: str) -> str:
        if len(k) > 8:
            return k[:4] + "****" + k[-4:]
        elif k:
            return "****"
        return ""

    return {
        "language": cfg.language,
        "theme": cfg.theme,
        "accent_color": cfg.accent_color,
        "api_key": _mask(cfg.api_key),
        "api_base_url": cfg.api_base_url,
        "api_model": cfg.api_model,
        "game_mode": cfg.game_mode,
        "img_api_key": _mask(cfg.img_api_key),
        "img_api_base_url": cfg.img_api_base_url or DEFAULT_IMG_BASE_URL,
        "img_api_model": cfg.img_api_model,
        "portrait_remove_bg": cfg.portrait_remove_bg,
        "img_generation_enabled": cfg.img_generation_enabled,
        "proxy_url": cfg.proxy_url,
    }


class ConfigUpdate(BaseModel):
    language: str | None = None
    theme: str | None = None
    accent_color: str | None = None
    api_key: str | None = None
    api_base_url: str | None = None
    api_model: str | None = None
    game_mode: str | None = None
    img_api_key: str | None = None
    img_api_base_url: str | None = None
    img_api_model: str | None = None
    portrait_remove_bg: str | None = None
    img_generation_enabled: bool | None = None
    proxy_url: str | None = None


class ApplyUpdateRequest(BaseModel):
    layers: list[str]  # each must be "app" or "system_media"

    @model_validator(mode="after")
    def _validate_layers(self):
        for layer in self.layers:
            if layer not in ("app", "system_media"):
                raise ValueError(f"Unknown layer: {layer!r}")
        if not self.layers:
            raise ValueError("layers must not be empty")
        return self


@app.post("/api/config")
async def update_config(body: ConfigUpdate):
    """Update fields and persist to config.json via UserConfig.save()."""
    if body.language is not None:
        if body.language not in SUPPORTED_LANGUAGES:
            raise HTTPException(
                400,
                f"Unsupported language: {body.language}. "
                f"Supported: {', '.join(sorted(SUPPORTED_LANGUAGES))}",
            )
        cfg.language = body.language
        switch_language(body.language)
    if body.theme is not None:
        if body.theme not in ("system", "dark", "light"):
            raise HTTPException(
                400,
                f"theme must be 'system', 'dark', or 'light', "
                f"got {body.theme!r}",
            )
        cfg.theme = body.theme
    if body.accent_color is not None:
        if body.accent_color not in ("green", "emerald", "blue", "amber", "rose", "violet"):
            raise HTTPException(
                400,
                f"accent_color must be one of green/emerald/blue/amber/rose/violet, "
                f"got {body.accent_color!r}",
            )
        cfg.accent_color = body.accent_color
    if body.api_key is not None:
        cfg.api_key = body.api_key
    if body.api_base_url is not None:
        cfg.api_base_url = body.api_base_url
    if body.api_model is not None:
        cfg.api_model = body.api_model
    if body.game_mode is not None:
        if body.game_mode not in ("text", "graph"):
            raise HTTPException(
                400,
                f"game_mode must be 'text' or 'graph', got {body.game_mode!r}",
            )
        cfg.game_mode = body.game_mode
    if body.img_api_key is not None:
        cfg.img_api_key = body.img_api_key
    if body.img_api_base_url is not None:
        cfg.img_api_base_url = body.img_api_base_url
    if body.img_api_model is not None:
        cfg.img_api_model = body.img_api_model
    if body.portrait_remove_bg is not None:
        if body.portrait_remove_bg not in ("auto", "always", "never"):
            raise HTTPException(
                400,
                f"portrait_remove_bg must be 'auto', 'always', or 'never', "
                f"got {body.portrait_remove_bg!r}",
            )
        cfg.portrait_remove_bg = body.portrait_remove_bg
    if body.img_generation_enabled is not None:
        cfg.img_generation_enabled = body.img_generation_enabled
    if body.proxy_url is not None:
        cfg.proxy_url = body.proxy_url.strip()
        set_update_proxy_url(cfg.proxy_url)
    cfg.save()
    return {"status": "ok"}


@app.get("/api/config/version-status")
async def config_version_status():
    """Check whether config.json needs migration to current schema version."""
    return {
        "needs_migration": cfg.needs_migration,
        "current_version": cfg._version,
        "expected_version": UserConfig._DEFAULTS["version"],
    }


@app.post("/api/config/migrate")
async def config_migrate():
    """Reset config.json to factory defaults after user confirms migration."""
    cfg.reset_to_defaults()
    # Re-init i18n with new (default) language after reset
    switch_language(cfg.language)
    return {"status": "ok"}


@app.get("/api/config/bg-removal-status")
async def config_bg_removal_status():
    """Check whether the background-removal model is available."""
    from storyloom.io.img_utils import check_model
    return {"available": check_model()}


# ═══════════════════════════════════════════════════════════════════
# Co-Create — Q&A phase before story generation
# ═══════════════════════════════════════════════════════════════════


class CoCreateStartReply(BaseModel):
    phase: str
    prompt: str


@app.post("/api/co-create/start", response_model=CoCreateStartReply)
async def co_create_start():
    """Start a new co-creation Q&A session.

    Creates a CoCreateFlow, calls start(), and stores it server-side.
    The returned *prompt* is the LLM's opening question — display it
    as the first assistant message in the chat UI.
    """
    flow = _game_session.new_co_create()
    result = flow.start()
    sessions.store_co_create(flow)
    return CoCreateStartReply(**result)


class CoCreateSendBody(BaseModel):
    text: str


class CoCreateSendReply(BaseModel):
    reply: str


@app.post("/api/co-create/send", response_model=CoCreateSendReply)
def co_create_send(body: CoCreateSendBody):
    """Send a user message in the co-creation Q&A.

    Returns the LLM's reply text.  On API failure, returns HTTP 502
    so the UI can offer a retry.
    """
    flow = sessions.get_co_create()
    if flow is None:
        raise HTTPException(400, "No active co-creation session.  Call start first.")
    try:
        reply = flow.send(body.text)
    except CoCreateError as e:
        raise HTTPException(502, e.message)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(400, str(e))
    return CoCreateSendReply(reply=reply)


@app.post("/api/co-create/retry-send", response_model=CoCreateSendReply)
def co_create_retry_send():
    """Retry the last failed send() call."""
    flow = sessions.get_co_create()
    if flow is None:
        raise HTTPException(400, "No active co-creation session.")
    try:
        reply = flow.retry_send()
    except CoCreateError as e:
        raise HTTPException(502, e.message)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    return CoCreateSendReply(reply=reply)


@app.post("/api/co-create/generate")
def co_create_generate():
    """Generate the story setup from the Q&A conversation.

    On success, creates the save file immediately (``_init.json``) and
    loads the GameLoop, ready for ``POST /api/game/{game_id}/start``
    to kick off Round 1.  Returns the game_id and story config.
    """
    flow = sessions.get_co_create()
    if flow is None:
        raise HTTPException(400, "No active co-creation session.")
    try:
        result = flow.generate()
    except CoCreateError as e:
        raise HTTPException(502, e.message)
    except RuntimeError as e:
        raise HTTPException(400, str(e))

    # Create save file immediately — the save is the canonical source
    # of truth for story_config.  GameLoop is loaded but not started
    # (Round 1 prompt is deferred to POST /api/game/{game_id}/start).
    gl, game_id = _game_session.start_game(result, game_mode=cfg.game_mode)
    sessions.store_game(game_id, gl)
    sessions.remove_co_create()  # co-create is done — game is now live

    return {
        "status": "ok",
        "game_id": game_id,
        "game_mode": cfg.game_mode,
        "story_config": result["story_config"],
        "characters": result["characters"],
        "locations": result["locations"],
        "outline_text": result["outline_text"],
    }


@app.post("/api/co-create/retry-generate")
def co_create_retry_generate():
    """Retry the last failed generate() call."""
    flow = sessions.get_co_create()
    if flow is None:
        raise HTTPException(400, "No active co-creation session.")
    try:
        result = flow.retry_generate()
    except CoCreateError as e:
        raise HTTPException(502, e.message)
    except RuntimeError as e:
        raise HTTPException(400, str(e))

    gl, game_id = _game_session.start_game(result, game_mode=cfg.game_mode)
    sessions.store_game(game_id, gl)
    sessions.remove_co_create()

    return {
        "status": "ok",
        "game_id": game_id,
        "game_mode": cfg.game_mode,
        "story_config": result["story_config"],
        "characters": result["characters"],
        "locations": result["locations"],
        "outline_text": result["outline_text"],
    }


@app.get("/api/co-create/generate/stream")
async def co_create_generate_stream():
    """SSE endpoint for streaming story setup generation.

    Replaces the blocking ``POST /api/co-create/generate`` with a
    streaming flow: the LLM generates JSON token-by-token, and the
    server emits ``section_complete`` events as each top-level key
    (story_config, characters, etc.) is fully received.

    On success, creates the save file and emits a final
    ``generate_done`` event with ``game_id`` and ``story_config``.
    """
    import asyncio

    from storyloom.core.co_create import CoCreateCancelled

    flow = sessions.get_co_create()
    if flow is None:
        raise HTTPException(400, "No active co-creation session.  Call start first.")

    q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def run_generate() -> None:
        try:
            for event in flow.generate_stream():
                etype = event.get("type", "")
                if etype == "section_complete":
                    loop.call_soon_threadsafe(q.put_nowait, event)
                elif etype == "generate_done" and "result" in event:
                    # Internal done event with parsed result — create save,
                    # emit a single client-facing generate_done with game_id.
                    result = event["result"]
                    gl, game_id = _game_session.start_game(
                        result, game_mode=cfg.game_mode
                    )
                    sessions.store_game(game_id, gl)
                    sessions.remove_co_create()

                    loop.call_soon_threadsafe(
                        q.put_nowait, {
                            "type": "generate_done",
                            "game_id": game_id,
                            "game_mode": cfg.game_mode,
                            "story_config": result["story_config"],
                            "characters": result["characters"],
                            "locations": result["locations"],
                            "outline_text": result.get("outline_text", ""),
                        }
                    )
                    return
        except CoCreateCancelled:
            # User cancelled or client disconnected — end stream quietly.
            # Do NOT create save file or store game.
            pass
        except CoCreateError as exc:
            loop.call_soon_threadsafe(
                q.put_nowait, {
                    "type": "generate_error",
                    "phase": exc.phase,
                    "message": exc.message,
                }
            )
        except Exception as exc:
            loop.call_soon_threadsafe(
                q.put_nowait, {
                    "type": "generate_error",
                    "phase": "generate_api",
                    "message": str(exc),
                }
            )
        finally:
            try:
                loop.call_soon_threadsafe(q.put_nowait, None)
            except RuntimeError:
                pass

    thread = threading.Thread(target=run_generate, daemon=True)
    thread.start()

    async def event_generator():
        _KEEPALIVE_INTERVAL = 15.0  # well under typical 60 s proxy timeout
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        q.get(), timeout=_KEEPALIVE_INTERVAL
                    )
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                if event is None:
                    break
                etype = event.get("type", "")
                data = json.dumps(event, ensure_ascii=False)
                yield f"event: {etype}\ndata: {data}\n\n"
                if etype in ("generate_done", "generate_error"):
                    break
        finally:
            # Client disconnected (or stream ended naturally) —
            # signal the daemon thread to stop at the next chunk
            # boundary.  flow.cancel() is idempotent — harmless if
            # the stream already completed.
            flow.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/co-create/prebuild/{game_id}/stream")
async def co_create_prebuild_stream(game_id: str):
    """SSE endpoint for material pre-build progress.  (§7.8c)

    A background daemon thread runs the ``prebuild_assets()`` generator.
    Events are pushed into an ``asyncio.Queue`` via
    ``call_soon_threadsafe`` and the async generator drains it with
    ``await q.get()``.

    On client disconnect, the ``event_generator`` ``finally`` block sets
    the stop event, which propagates through to ``Prebuilder.build()``
    via the ``cancel_event`` parameter — the pipeline stops at the next
    checkpoint.
    """
    import asyncio

    # ── Reuse the stored GameLoop (from co_create_generate) instead
    # of loading a throwaway copy — its roster is the one the game
    # will use after prebuild completes.
    gl = sessions.get_game(game_id)

    q, stop_evt = sessions.store_co_create_prebuild_stream(game_id)
    loop = asyncio.get_running_loop()

    # ── Background thread: run prebuild pipeline ────────────────────
    def run_prebuild() -> None:
        try:
            for event in _game_session.prebuild_assets(
                game_id, game_loop=gl, cancel_event=stop_evt,
            ):
                loop.call_soon_threadsafe(q.put_nowait, event)
                if event["type"] == "prebuild_cancelled":
                    # Prebuild was cancelled — roster was cleared at
                    # Step 0 (§7.8c) and not rebuilt.  The _init.json
                    # save file exists but the game cannot be played in
                    # graph mode without a prebuilt roster.  Remove the
                    # game so the user doesn't see a broken entry.
                    sessions.remove_game(game_id)
                    _game_session.delete_game(game_id)
                    return
                if event["type"] == "prebuild_complete":
                    return
        except Exception as exc:
            loop.call_soon_threadsafe(
                q.put_nowait, {
                    "type": "prebuild_complete",
                    "success": False,
                    "results": [],
                    "errors": [str(exc)],
                    "warnings": [],
                }
            )
        finally:
            try:
                loop.call_soon_threadsafe(q.put_nowait, None)
            except RuntimeError:
                pass
            # Identity-checked cleanup — only removes state if no
            # new stream has replaced it (re-connect guard).
            sessions.pop_co_create_prebuild_stream(game_id, q)

    thread = threading.Thread(target=run_prebuild, daemon=True)
    thread.start()

    # ── Async SSE generator ─────────────────────────────────────────
    async def event_generator():
        _KEEPALIVE_INTERVAL = 15.0  # well under typical 60 s proxy timeout
        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        q.get(), timeout=_KEEPALIVE_INTERVAL
                    )
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                # None sentinel — producer thread has exited.
                if event is None:
                    break

                etype = event.get("type", "")
                data = json.dumps(event, ensure_ascii=False)
                yield f"event: {etype}\ndata: {data}\n\n"

                if etype in ("prebuild_complete", "prebuild_cancelled"):
                    break
        finally:
            # Client disconnected (or stream ended naturally) —
            # signal the daemon thread to stop at the next pipeline
            # checkpoint.  Setting the stop event propagates through
            # prebuild_assets → Prebuilder.build().
            stop_evt.set()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/co-create/abort")
async def co_create_abort():
    """Abort the co-creation session and discard all state.

    Calls ``flow.cancel()`` first to stop any in-flight
    ``generate_stream()``, then ``flow.abort()`` to reset phase +
    retry state, then removes the co-create session.
    """
    flow = sessions.get_co_create()
    if flow is not None:
        flow.cancel()
        flow.abort()
    sessions.remove_co_create()
    return {"status": "ok"}


@app.post("/api/co-create/prebuild/{game_id}/stop")
async def co_create_prebuild_stop(game_id: str):
    """Cancel an in-flight prebuild stream for a game.

    Sets the stop event so the prebuild daemon thread exits at the
    next pipeline checkpoint.  Idempotent — safe to call multiple
    times or when no stream is active.
    """
    sessions.request_stop_co_create_prebuild(game_id)
    return {"status": "ok"}


# ═══════════════════════════════════════════════════════════════════
# Game — create from co-creation result
# ═══════════════════════════════════════════════════════════════════


@app.post("/api/game/{game_id}/start")
async def game_start(game_id: str):
    """Start Round 1 for a game created by co-create/generate.

    The game must have been created by a prior successful
    ``POST /api/co-create/generate``, which writes ``_init.json``
    and loads the GameLoop server-side.

    Calls ``GameLoop.start_game()`` to build the Round 1 prompt and
    launch the background API call.  The UI then connects to
    ``GET /api/game/{game_id}/stream`` for the SSE narrative stream.
    """
    gl = sessions.get_game(game_id)
    if gl is None:
        raise HTTPException(
            404,
            f"Game '{game_id}' not found.  Call /api/co-create/generate first.",
        )
    try:
        gl.start_game()
    except RuntimeError as e:
        raise HTTPException(400, str(e))

    sc = gl.story_config
    return {
        "status": "ok",
        "game_id": game_id,
        "game_mode": cfg.game_mode,
        "round_count": gl.round_count,
        "current_node": gl.current_node,
        "story_config": sc,
    }


# ═══════════════════════════════════════════════════════════════════
# Game — SSE narrative stream
# ═══════════════════════════════════════════════════════════════════


@app.get("/api/game/{game_id}/stream")
async def game_stream(game_id: str):
    """SSE endpoint for the narrative event stream.

    A background daemon thread runs the game loop (stream_round()
    generator).  Events are pushed into an ``asyncio.Queue`` via
    ``call_soon_threadsafe`` and the async generator drains it with
    ``await q.get()`` — zero-polling, event-driven SSE.

    When the generator yields an ``options`` event, the background
    thread blocks on ``wait_for_choice()`` until the player sends a
    choice via ``POST /api/game/{game_id}/choice``.

    The stream ends naturally after the ``ending`` → ``done`` sequence,
    or on a fatal error.
    """
    gl = sessions.get_game(game_id)
    if gl is None:
        raise HTTPException(404, f"Game '{game_id}' not found.")

    # ── Guard: wait for any existing stream to fully exit ──────────
    # If the user exited mid-game and immediately re-entered, the old
    # daemon thread and event_generator may still be running.  Cancel
    # the old GameLoop via the per-stream stored reference (NOT the
    # global _game_loops lookup — save_start() may have already
    # replaced it with a new GameLoop), then poll until the old
    # thread's finally block has run and _game_streams is cleared.
    if sessions.get_game_stream(game_id) is not None:
        old_gl = sessions.get_game_stream_loop(game_id)
        if old_gl is not None:
            old_gl.cancel()
        sessions.request_stop_game_stream(game_id)
        for _ in range(50):  # 5 s timeout (50 × 100 ms)
            if sessions.get_game_stream(game_id) is None:
                break
            await asyncio.sleep(0.1)

    q, stop_evt = sessions.store_game_stream(game_id, gl)
    loop = asyncio.get_running_loop()

    # ── Background thread: run game loop ──────────────────────────
    def run_loop() -> None:
        try:
            while True:
                # Check LOCAL stop event reference — never the global
                # is_game_stream_stopped() lookup, which races with a
                # new store_game_stream() overwriting the event.
                if stop_evt.is_set():
                    return

                gen = gl.stream_round()
                for event in gen:
                    # Check stop signal after every yielded event.
                    if stop_evt.is_set():
                        return

                    loop.call_soon_threadsafe(q.put_nowait, event)
                    if event["type"] == "options":
                        # Block until choice arrives via POST /choice
                        key = sessions.wait_for_choice(game_id)
                        # Stop may have been requested while we were
                        # blocked — check local reference before
                        # resuming the generator.
                        if stop_evt.is_set():
                            return
                        try:
                            gen.send(key)
                        except StopIteration:
                            # Generator exhausted prematurely —
                            # Phase 5 (add_round + _launch_api) was
                            # not executed.  This is an abnormal state;
                            # report to client and stop.
                            loop.call_soon_threadsafe(q.put_nowait, {
                                "type": "error",
                                "message": (
                                    "Generator exhausted after choice — "
                                    "round state may be lost."
                                ),
                            })
                            return
                        # Continue receiving post-choice events from
                        # the generator (bridge_text, etc.)
                    elif event["type"] == "error":
                        # Error event sent to client — loop ends.
                        # Client may call POST /retry to re-launch.
                        logger.error(
                            "game_stream: fatal error for game=%s "
                            "round=%d node=%s: %s",
                            game_id, gl.round_count,
                            gl.current_node, event.get("message", ""),
                        )
                        return
                    elif event["type"] == "done":
                        # Round complete.  If ending, exit the while
                        # loop after this round.
                        if gl.ending_flag:
                            loop.call_soon_threadsafe(
                                q.put_nowait, {"type": "stream_end"}
                            )
                            return
                        # Otherwise, loop continues to next round.
                        break  # exit for loop, continue while loop
        except Exception as exc:
            logger.error(
                "game_stream: unhandled exception for game=%s "
                "round=%d node=%s",
                game_id, gl.round_count, gl.current_node,
                exc_info=True,
            )
            loop.call_soon_threadsafe(
                q.put_nowait, {"type": "error", "message": str(exc)}
            )
        finally:
            # Signal the async consumer that we're done, then clean up.
            # call_soon_threadsafe is safe even if the loop is closing
            # (the callback is a no-op in that case).
            try:
                loop.call_soon_threadsafe(q.put_nowait, None)
            except RuntimeError:
                pass  # loop already closed — consumer is already gone
            # Identity-checked pop — only removes the queue if a new
            # stream hasn't already replaced it (see sessions.py).
            sessions.pop_game_stream(game_id, q)

    thread = threading.Thread(target=run_loop, daemon=True)
    thread.start()

    # ── Async SSE generator ───────────────────────────────────────
    async def event_generator():
        """Drain the asyncio.Queue with zero-polling await.

        Uses ``asyncio.wait_for(q.get(), timeout=15)`` so keepalive
        comments still go out every 15 s during idle periods (prevents
        proxy timeout, typically 60 s).  The producer signals stream
        end by putting a ``None`` sentinel.
        """
        _KEEPALIVE_INTERVAL = 15.0  # well under typical 60 s proxy timeout

        try:
            while True:
                try:
                    event = await asyncio.wait_for(
                        q.get(), timeout=_KEEPALIVE_INTERVAL
                    )
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

                # None sentinel — producer thread has exited cleanly.
                if event is None:
                    break

                etype = event.get("type", "")

                # Serialize event data.  For "token" events, the text
                # may contain characters that confuse SSE — use JSON.
                data = json.dumps(event, ensure_ascii=False)
                yield f"event: {etype}\ndata: {data}\n\n"

                if etype in ("stream_end",):
                    break
        finally:
            # Client disconnected (or stream ended naturally) —
            # signal the background daemon thread to stop.  Use
            # CAPTURED references (stop_evt, gl), NOT global lookups
            # — a new stream for the same game_id may have already
            # replaced the global state by the time this async
            # generator is finalised.
            stop_evt.set()
            gl.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


class ChoiceBody(BaseModel):
    key: str


@app.post("/api/game/{game_id}/choice")
async def game_choice(game_id: str, body: ChoiceBody):
    """Inject a player choice into the running game loop.

    The background SSE thread is blocked on ``wait_for_choice()``.
    This handler sets the choice and signals the event to unblock it.
    The generator resumes with ``gen.send(key)``.
    """
    gl = sessions.get_game(game_id)
    if gl is None:
        raise HTTPException(404, f"Game '{game_id}' not found.")
    sessions.inject_choice(game_id, body.key)
    return {"status": "ok"}


@app.post("/api/game/{game_id}/retry")
async def game_retry(game_id: str):
    """Retry the last failed API call.

    Call after receiving an ``error`` event.  Re-launches the failed
    round with the same messages.  The SSE stream reconnects afterward.
    """
    gl = sessions.get_game(game_id)
    if gl is None:
        raise HTTPException(404, f"Game '{game_id}' not found.")
    try:
        gl.retry()
    except RuntimeError as e:
        logger.warning(
            "game_retry: retry rejected for game=%s: %s", game_id, e,
        )
        raise HTTPException(400, str(e))
    logger.info(
        "game_retry: retry launched for game=%s round=%d",
        game_id, gl.round_count,
    )
    return {"status": "ok"}


@app.post("/api/game/{game_id}/stop")
async def game_stop(game_id: str):
    """Stop the background daemon thread and clean up stream state.

    Call when navigating away from the game view (exit button, browser
    back, etc.).  Idempotent — safe to call multiple times.
    """
    # Cancel the GameLoop first (correct ref at this point — new game
    # hasn't been loaded yet), then signal session-level state.
    gl = sessions.get_game(game_id)
    if gl is not None:
        gl.cancel()
    sessions.request_stop_game_stream(game_id)
    return {"status": "ok"}


@app.get("/api/game/{game_id}/adventure-log")
async def game_adventure_log(game_id: str):
    """Get the adventure log after natural ending.

    Call after receiving an ``ending`` event.  Returns the generated
    adventure log text, or null if still generating.
    """
    gl = sessions.get_game(game_id)
    if gl is None:
        raise HTTPException(404, f"Game '{game_id}' not found.")
    log_text = gl.get_adventure_log(timeout=5.0)
    if log_text is not None:
        return {"status": "ok", "text": log_text}
    err = gl.adventure_log_error
    if err is not None:
        return {"status": "error", "message": err}
    return {"status": "pending"}


# ═══════════════════════════════════════════════════════════════════
# Assets — browse, clean, delete
# ═══════════════════════════════════════════════════════════════════


def _get_asset_library() -> "AssetLibrary":
    """Load the asset library and sync system assets.

    Called by every asset API endpoint so the library always reflects
    the current state of ``system_media/``, not just persisted data.
    Idempotent — if the version hasn't changed, ``import_system_assets``
    is a no-op.
    """
    from storyloom.assets import AssetLibrary

    lib = AssetLibrary.load(_MEDIA_DIR)
    if os.path.isdir(_SYS_MEDIA_DIR):
        try:
            lib.import_system_assets(_SYS_MEDIA_DIR)
            lib.save()
        except Exception:
            # system_media/ exists but is broken — skip, don't block
            pass
    return lib


@app.get("/api/assets")
async def assets_list():
    """List all assets grouped by type from the global asset library."""
    from storyloom.assets import AssetType

    lib = _get_asset_library()
    result: dict[str, dict[str, dict]] = {}
    for atype in AssetType:
        items = lib.list_by_type(atype)
        if items:
            result[atype.value] = {
                aid: asset.to_dict() for aid, asset in items.items()
            }
    return {"types": result}


@app.post("/api/assets/clean")
async def assets_clean(keep_count: int = CLEANUP_KEEP_COUNT, type: str | None = None):
    """Clean unused assets.

    If *type* is given, only that :class:`AssetType` is cleaned.
    Returns ``{deleted: N}`` — *deleted* is the number of assets removed.
    """
    from storyloom.assets import AssetLibrary, AssetType

    atype = None
    if type is not None:
        try:
            atype = AssetType(type)
        except ValueError:
            raise HTTPException(400, f"Unknown asset type: {type}")

    lib = _get_asset_library()
    deleted = lib.clean(keep_count, asset_type=atype)
    if deleted > 0:
        lib.save()
    return {"deleted": deleted}


@app.delete("/api/assets/{asset_type}/{asset_id}")
async def assets_delete(asset_type: str, asset_id: str):
    """Delete a single asset.  Refuses if ``use_count > 0``."""
    from storyloom.assets import AssetLibrary, AssetType

    try:
        atype = AssetType(asset_type)
    except ValueError:
        raise HTTPException(404, f"Unknown asset type: {asset_type}")

    lib = _get_asset_library()
    asset = lib.get(atype, asset_id)
    if asset is None:
        raise HTTPException(404, f"Asset not found: {asset_type}/{asset_id}")

    if asset.use_count > 0:
        raise HTTPException(400, "Asset in use, cannot delete")

    lib.remove(atype, asset_id)
    lib.save()

    # Also delete the file on disk
    file_path = os.path.join(_MEDIA_DIR, asset.file_path)
    if os.path.isfile(file_path):
        os.remove(file_path)

    return {"status": "deleted"}


# ═══════════════════════════════════════════════════════════════════
# Saves — list, load, delete
# ═══════════════════════════════════════════════════════════════════


@app.get("/api/saves/last-played")
async def saves_last_played():
    """Return the last-played game + save (O(1) via ``.last_played.json``).

    Returns ``{game_id, game_title, save_file, played_at}`` or 404.
    """
    data = SaveManager.read_last_played(_game_session._saves_root)
    if data is None:
        raise HTTPException(404, "No last-played save found.")
    return data


@app.get("/api/saves/games")
async def saves_list_games():
    """List all games sorted by last activity (most recent first).

    Delegates to ``GameSession.list_games(enrich_last_played=True)``
    which enriches each game with ``last_played_at`` (from the most
    recently modified save file) and sorts descending.
    """
    return _game_session.list_games(enrich_last_played=True)


@app.get("/api/saves/{game_id}")
async def saves_list(game_id: str):
    """List all saves in a game directory."""
    try:
        return _game_session.list_saves(game_id)
    except FileNotFoundError:
        raise HTTPException(404, f"Game not found: {game_id}")


@app.post("/api/saves/{game_id}/load/{filename}")
async def save_load(game_id: str, filename: str):
    """Load a save file and return its data with computed fields.

    Returns the complete save dict plus ``game_id``, ``round_count``,
    and ``current_node`` for the UI.  The preview page reads
    ``story_config``; the game page uses the full state.
    """
    try:
        data = _game_session.read_save(game_id, filename)
    except FileNotFoundError:
        raise HTTPException(
            404, f"Save '{filename}' not found in game '{game_id}'."
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    progress = data.get("progress", {})
    # ContextManager._round_count is never persisted to save files
    # (to_save_dict / _build_init_dict only write current_node +
    # checkpoint_snapshots).  After load the counter always starts at 0.
    return {
        "game_id": game_id,
        "game_mode": data.get("config", {}).get("mode", "text"),  # §7.7
        "story_config": data.get("story_config", {}),
        "metadata": data.get("metadata", {}),
        "round_count": 0,
        "current_node": progress.get("current_node", ""),
    }


@app.post("/api/saves/{game_id}/start/{filename}")
async def save_start(game_id: str, filename: str):
    """Load a save into the active game session and return preview data.

    This is the checkpoint-left-click path: reads the save once via
    ``GameSession.read_save()``, uses the same data to reconstruct a
    ``GameLoop`` (via ``_load_from_data()``, which also updates
    ``.last_played.json``), stores it server-side, and returns
    story_config for the game-preview page.

    After this, the UI navigates to ``#game-preview`` and the
    "Begin Adventure" button calls ``POST /api/game/{game_id}/start``.
    """
    try:
        data = _game_session.read_save(game_id, filename)
    except FileNotFoundError:
        raise HTTPException(
            404, f"Save '{filename}' not found in game '{game_id}'."
        )
    except ValueError as e:
        raise HTTPException(400, str(e))

    gl = _game_session._load_from_data(game_id, filename, data)
    sessions.store_game(game_id, gl)

    progress = data.get("progress", {})
    return {
        "game_id": game_id,
        "game_mode": data.get("config", {}).get("mode", "text"),  # §7.7
        "story_config": data.get("story_config", {}),
        "metadata": data.get("metadata", {}),
        "round_count": 0,
        "current_node": progress.get("current_node", ""),
    }


@app.delete("/api/saves/{game_id}")
async def saves_delete_game(game_id: str):
    """Delete an entire game directory and all its saves."""
    deleted = _game_session.delete_game(game_id)
    if not deleted:
        raise HTTPException(404, f"Game not found: {game_id}")
    sessions.remove_game(game_id)
    return {"status": "deleted"}


@app.delete("/api/saves/{game_id}/{filename}")
async def saves_delete(game_id: str, filename: str):
    """Delete a single save file."""
    try:
        deleted = _game_session.delete_save(game_id, filename)
    except FileNotFoundError:
        raise HTTPException(404, f"Game not found: {game_id}")
    return {"status": "deleted" if deleted else "not_found"}


# ═══════════════════════════════════════════════════════════════════
# Auto-Update
# Spec: docs/superpowers/specs/2026-08-10-auto-update-design.md §5
# ═══════════════════════════════════════════════════════════════════


def _get_system_media_version() -> str:
    """Read system_media version from VERSION file, or '' if missing."""
    version_file = os.path.join(_APP_DIR, "system_media", "VERSION")
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (OSError, FileNotFoundError):
        return ""


@app.get("/api/version")
async def app_version():
    """Return the current app version — no network call, instant response."""
    return {"version": __version__}


@app.get("/api/update/check")
async def update_check(force: bool = False):
    """Check GitHub Releases for available updates."""
    sm_ver = _get_system_media_version()
    result = check_for_updates(
        app_version=__version__,
        system_media_version=sm_ver,
        force=force,
    )
    return result


@app.post("/api/update/apply")
async def update_apply(req: ApplyUpdateRequest):
    """Start downloading and extracting update layers.

    Returns a stream URL for SSE progress tracking.
    """
    stream_id = os.urandom(8).hex()
    sessions.update_store[stream_id] = {
        "layers": req.layers,
        "status": "pending",
    }
    return {"stream_url": f"/api/update/stream/{stream_id}"}


@app.get("/api/update/stream/{stream_id}")
async def update_stream(stream_id: str):
    """SSE endpoint for update download progress."""
    import asyncio
    import threading

    params = sessions.update_store.pop(stream_id, None)
    if not params:
        raise HTTPException(404, "Unknown or expired stream ID")

    q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def run_update():
        try:
            layers = params["layers"]
            results = {}
            sm_ver = _get_system_media_version()
            check = check_for_updates(__version__, sm_ver, force=False)

            for layer in layers:
                if layer == "app" and check.app.has_update:
                    url = check.app.asset_url
                elif layer == "system_media" and check.system_media.has_update:
                    url = check.system_media.asset_url
                    sm_target = os.path.join(_APP_DIR, "system_media")
                else:
                    continue

                if not url:
                    continue

                def progress_cb(p: UpdateProgress):
                    loop.call_soon_threadsafe(
                        q.put_nowait,
                        {
                            "type": "progress",
                            "layer": p.layer,
                            "stage": p.stage,
                            "received": p.received,
                            "total": p.total,
                            "error": p.error,
                        },
                    )

                target = (
                    sm_target if layer == "system_media" else _APP_DIR
                )
                download_and_extract(
                    layer=layer,
                    url=url,
                    target_root=target,
                    progress_callback=progress_cb,
                )

                results[layer] = (
                    check.app.latest
                    if layer == "app"
                    else check.system_media.latest
                )

            loop.call_soon_threadsafe(
                q.put_nowait, {"type": "done", "layers": results}
            )
        except Exception as exc:
            loop.call_soon_threadsafe(
                q.put_nowait, {"type": "error", "error": str(exc)}
            )
        finally:
            try:
                loop.call_soon_threadsafe(q.put_nowait, None)
            except RuntimeError:
                pass

    thread = threading.Thread(target=run_update, daemon=True)
    thread.start()

    async def event_generator():
        while True:
            event = await q.get()
            if event is None:
                break
            etype = event.get("type", "")
            data = json.dumps(event, ensure_ascii=False)
            yield f"event: {etype}\ndata: {data}\n\n"
            if etype in ("done", "error"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ═══════════════════════════════════════════════════════════════════
# System
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/exit")
async def exit_app():
    import signal
    os.kill(os.getpid(), signal.SIGTERM)
    return {"status": "shutting_down"}


def _find_free_port() -> int:
    """Return an available TCP port on localhost.

    Uses port 0 (OS auto-assign), the same pattern as Jupyter, Streamlit,
    and Gradio.  No race window — the socket is bound, read, and closed
    before uvicorn re-binds it.
    """
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _webview_available() -> bool:
    """Return True if pywebview can create a native desktop window.

    ``import webview`` succeeds even without a display server — the
    real test is creating a throwaway window and catching the exception.
    """
    # Suppress noisy GTK/QT backend-probing output from pywebview.
    import io
    _stderr = sys.stderr
    sys.stderr = io.StringIO()
    try:
        import webview
    except ImportError:
        return False
    finally:
        sys.stderr = _stderr

    return True


def _open_browser(url: str) -> None:
    """Open *url* in the system browser, suppressing stderr noise."""
    import os
    import webbrowser
    saved = os.dup(2)
    null_fd = os.open(os.devnull, os.O_WRONLY)
    os.dup2(null_fd, 2)
    os.close(null_fd)
    try:
        webbrowser.open(url)
    except Exception:
        pass
    finally:
        os.dup2(saved, 2)
        os.close(saved)
    print()
    print(f"Storyloom {__version__} — application server")
    print(f"Visit: {url}")
    print("Closing this window will exit Storyloom.")


def _show_desktop_window(url: str) -> None:
    """Open *url* in a native pywebview desktop window.

    Falls back to browser mode if a display server is unavailable
    (e.g. SSH session, WSL without WSLg, CI).
    """
    import time
    time.sleep(1)  # let uvicorn bind the port

    print()
    print(f"Storyloom {__version__} — application server")
    print("Opening desktop window.  You may minimize this window.")

    import webview

    # Determine the port from the URL for asset download support
    from urllib.parse import urlparse
    port = urlparse(url).port or 8000

    class _JsApi:
        """Exposed to frontend via pywebview JS bridge.

        Provides native OS save dialogs for file downloads —
        browser-based download mechanisms (<a download>, Blob URLs)
        are silently ignored by pywebview/WebView2.
        """

        def _get_window(self):
            return webview.active_window()

        def save_asset(self, asset_url: str, filename: str) -> None:
            """Download asset from local server, save via native dialog."""
            import urllib.request
            url = f"http://127.0.0.1:{port}{asset_url}"
            win = self._get_window()
            path = win.create_file_dialog(
                dialog_type=webview.FileDialog.SAVE,
                save_filename=filename,
            )
            if not path:
                return
            try:
                with urllib.request.urlopen(url) as resp:
                    with open(path[0] if isinstance(path, list) else path, 'wb') as f:
                        f.write(resp.read())
            except Exception as exc:
                print(f"Asset download failed: {exc}", file=sys.stderr)

        def save_text(self, content: str, filename: str) -> None:
            """Save text content via native save dialog (log export)."""
            win = self._get_window()
            path = win.create_file_dialog(
                dialog_type=webview.FileDialog.SAVE,
                save_filename=filename,
                file_types=["Markdown (*.md)", "Text (*.txt)"],
            )
            if not path:
                return
            try:
                out = path[0] if isinstance(path, list) else path
                with open(out, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as exc:
                print(f"Text save failed: {exc}", file=sys.stderr)

    try:
        webview.create_window("Storyloom", url, width=1200, height=800,
                              js_api=_JsApi())
        webview.start()
    except Exception:
        # GUI unavailable — webview.start() raises WebViewException when
        # no display server is reachable (headless, SSH, WSL without WSLg).
        import webbrowser
        print("Desktop window unavailable — opening browser instead.")
        print(f"Visit: {url}")
        print("Closing this window will exit Storyloom.")
        webbrowser.open(url)
        # Block until Ctrl+C (daemon thread keeps uvicorn alive).
        import threading
        threading.Event().wait()


def main():
    """Start the Storyloom web server.

    Default: native desktop window (pywebview).  Falls back to browser
    when pywebview is not installed or no display server is available.

    CLI flags::

        --browser       Always open in the system browser
        --port PORT     Override the auto-assigned port
        --help          Show help
    """
    import argparse
    import os
    import sys
    import threading

    # When running without a console (PyInstaller --noconsole), stdout/stderr
    # are None and uvicorn's log formatter crashes trying to call .isatty().
    # Redirect to a log file next to the executable for debugging.
    if sys.stdout is None or sys.stderr is None:
        log_path = os.path.join(os.path.dirname(sys.executable), "storyloom.log")
        f = open(log_path, "w")
        if sys.stdout is None:
            sys.stdout = f
        if sys.stderr is None:
            sys.stderr = f

    parser = argparse.ArgumentParser(description="Storyloom — AI Real-Time Visual Novel")
    parser.add_argument(
        "--browser", action="store_true",
        help="Open in system browser instead of a native desktop window.",
    )
    parser.add_argument(
        "--port", type=int, default=0,
        help="TCP port (default: auto-assign a free port).",
    )
    parser.add_argument(
        "--regenerate-launcher", action="store_true",
        help="Download and restore the Storyloom launcher binary.",
    )
    args, _ = parser.parse_known_args()

    # --regenerate-launcher: download launcher binary and exit
    if args.regenerate_launcher:
        from storyloom.core.update_manager import regenerate_launcher
        ok = regenerate_launcher(_APP_DIR)
        sys.exit(0 if ok else 1)

    HOST = "127.0.0.1"
    PORT = args.port if args.port else _find_free_port()
    url = f"http://{HOST}:{PORT}"

    # ── Start uvicorn in a daemon thread ───────────────────────────
    import uvicorn
    t = threading.Thread(
        target=uvicorn.run,
        args=("storyloom.web.server:app",),
        kwargs={"host": HOST, "port": PORT, "log_level": "warning"},
        daemon=True,
    )
    t.start()

    # ── Open the UI ────────────────────────────────────────────────
    if args.browser or not _webview_available():
        _open_browser(url)
        t.join()  # block until Ctrl+C
    else:
        _show_desktop_window(url)
        # Window closed — daemon thread exits with process.
        sys.exit(0)


if __name__ == "__main__":
    main()

"""Storyloom web server — FastAPI + SSE + GameLoop integration.

Run with:
    uvicorn src.storyloom.server:app --reload
"""

import asyncio
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from storyloom.i18n import init_i18n
from storyloom.io.api_client import ApiClient
from storyloom.core.co_create import CoCreateFlow, CoCreationAborted
from storyloom.core.game_loop import GameLoop, GameState
from storyloom.main import DEFAULT_STORY_CONFIG, SAMPLE_OUTLINE
from storyloom.parser.streaming_parser import StreamingXmlParser, EventType
from storyloom.web_cocreate import WebCoCreateDisplay
from storyloom.web_display import WebDisplay

# Initialize i18n for web server (same locale dir as CLI)
init_i18n()

# ── Request models ──────────────────────────────────────────────────


class NewGameRequest(BaseModel):
    story_config: dict | None = None
    outline_text: str | None = None


class ChoiceRequest(BaseModel):
    choice_key: str


# ── Session storage ─────────────────────────────────────────────────


@dataclass
class SessionData:
    game_loop: GameLoop
    web_display: WebDisplay
    task_thread: threading.Thread | None = None
    error: str | None = None
    done: threading.Event = field(default_factory=threading.Event)
    processing: bool = False  # guard against concurrent choices


class SessionManager:
    """Thread-safe in-memory session store."""

    def __init__(self):
        self._sessions: dict[str, SessionData] = {}
        self._lock = threading.Lock()

    def create(self, session_id: str, sd: SessionData) -> None:
        with self._lock:
            self._sessions[session_id] = sd

    def get(self, session_id: str) -> SessionData | None:
        with self._lock:
            return self._sessions.get(session_id)

    def remove(self, session_id: str) -> SessionData | None:
        with self._lock:
            return self._sessions.pop(session_id, None)


sessions = SessionManager()

# ── FastAPI app ─────────────────────────────────────────────────────

app = FastAPI(title="Storyloom Web")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files ────────────────────────────────────────────────────

# Resolve frontend/ directory relative to this source file.
# Walk up from __file__ until we find a directory containing 'frontend/index.html'.
_WEB_DIR = Path(__file__).resolve().parent
for _ in range(5):
    _WEB_DIR = _WEB_DIR.parent
    if (_WEB_DIR / "frontend" / "index.html").exists():
        _WEB_DIR = _WEB_DIR / "frontend"
        break


@app.get("/")
async def serve_index():
    """Serve the game frontend."""
    return FileResponse(_WEB_DIR / "index.html")


# ── Helpers ─────────────────────────────────────────────────────────


def _extract_first_node(outline_text: str) -> str:
    """Extract first node ID from outline text."""
    for line in outline_text.strip().split("\n"):
        line = line.strip()
        if line and not line.startswith("├") and not line.startswith(
            "└"
        ) and not line.startswith("→"):
            parts = line.split()
            if parts:
                return parts[0]
    return ""


def _extract_first_goal(outline_text: str) -> str:
    """Extract first node goal from outline text."""
    for line in outline_text.strip().split("\n"):
        line = line.strip()
        if "：" in line:
            return line.split("：", 1)[1].strip()
    return ""


def _make_game_loop(
    story_config: dict,
    outline_text: str,
    api_client: ApiClient,
    web_display: WebDisplay,
) -> GameLoop:
    """Create a GameLoop wired to a WebDisplay."""
    game_state = GameState(story_config)
    first_node = _extract_first_node(outline_text)
    first_goal = _extract_first_goal(outline_text)

    return GameLoop(
        story_config=story_config,
        outline_text=outline_text,
        api_client=api_client,
        display=web_display,
        game_state=game_state,
        current_node=first_node,
        goal=first_goal,
    )


def _run_stream_round_in_thread(
    session: SessionData, stream_fn, **kwargs
):
    """Execute a game round via streaming API in a background thread.

    Feeds raw LLM tokens into StreamingXmlParser line-by-line.  Each
    complete <seg> is pushed to WebDisplay *immediately* while the LLM
    is still generating — no waiting for the full response.

    The GameLoop's own segment events (from final XmlParser.parse) are
    skipped to avoid duplicates; only choices/state/done from the final
    parse are forwarded.
    """
    wd = session.web_display
    wd.show_wait_message("故事生成中...")
    # Push initial state snapshot so the dashboard renders immediately
    wd.show_state(session.game_loop.game_state.state_vars)

    line_buf = ""
    parser = StreamingXmlParser()

    try:
        for event in stream_fn(**kwargs):
            etype = event["type"]

            if etype == "token":
                token_text = event["text"]
                wd.show_token(token_text)  # frontend progress counter

                # Feed complete lines to streaming parser.
                # DeepSeek occasionally merges lines (missing \n), so we
                # also split on NNN|  prefixes that appear mid-buffer.
                line_buf += token_text
                line_buf = re.sub(r"(?<!\n)(\d{3}\| )", r"\n\1", line_buf)
                while "\n" in line_buf:
                    raw_line, line_buf = line_buf.split("\n", 1)
                    for pe in parser.feed_line(raw_line):
                        if pe.type == EventType.SEGMENT and pe.text:
                            wd.buffer_segment_dict({
                                "type": "segment",
                                "n": 0,
                                "text": pe.text,
                                "position": pe.position,
                                "branch": None,
                            })

            elif etype == "segment":
                # Skip — streaming parser already emitted these in real time
                pass

            elif etype == "state":
                # GameLoop now yields state after applying sets
                wd.show_state(event["vars"])

            elif etype == "options":
                wd.buffer_choices_raw(event["choices"])

            elif etype == "error":
                session.error = event["message"]

            elif etype == "done":
                pass  # final event, loop ends naturally

        # Flush any remaining buffer (incomplete last line)
        if line_buf.strip():
            for pe in parser.feed_line(line_buf.strip()):
                if pe.type == EventType.SEGMENT and pe.text:
                    wd.buffer_segment_dict({
                        "type": "segment",
                        "n": 0,
                        "text": pe.text,
                        "position": pe.position,
                        "branch": None,
                    })

        # Capture state from final parsed result
        result = parser.get_result()
        if result.checkpoint_node:
            session.game_loop.current_node = result.checkpoint_node

    except Exception as e:
        session.error = str(e)
    finally:
        session.done.set()
        session.processing = False
        wd.signal_round_done()


# ── API Routes ──────────────────────────────────────────────────────


@app.post("/api/game/new")
async def new_game(req: NewGameRequest):
    """Create a new game session and start Round 1 in a background thread.

    Returns immediately with a session_id. The client should then
    connect to GET /api/game/{session_id}/stream for the narrative.
    """
    story_config = req.story_config or DEFAULT_STORY_CONFIG
    outline_text = req.outline_text or SAMPLE_OUTLINE

    try:
        api_client = ApiClient()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    web_display = WebDisplay()
    game_loop = _make_game_loop(story_config, outline_text, api_client, web_display)

    session_id = uuid.uuid4().hex[:12]
    sd = SessionData(game_loop=game_loop, web_display=web_display, processing=True)
    sessions.create(session_id, sd)

    # Fire-and-forget Round 1 in a background thread (streaming)
    thread = threading.Thread(
        target=_run_stream_round_in_thread,
        args=(sd, game_loop.start_round1_stream),
        daemon=True,
    )
    sd.task_thread = thread
    thread.start()

    return {
        "session_id": session_id,
        "message": "Game started. Connect to SSE stream for narrative.",
    }


@app.get("/api/game/{session_id}/stream")
async def stream_story(session_id: str, request: Request):
    """SSE endpoint that streams narrative segments, choices, and state.

    Polls the WebDisplay buffer every 100ms while the background thread
    runs the game round. Sends heartbeat every 15s to keep the
    connection alive during long API calls.
    """
    sd = sessions.get(session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail="Session not found")

    wd = sd.web_display

    async def event_generator():
        sent_seg_count = 0
        last_heartbeat = time.monotonic()
        was_done = False  # track done→clear→done transitions across rounds

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                return

            # Drain state FIRST — dashboard should render before text
            state = wd.drain_state()
            if state:
                yield _sse("state", state)

            # Drain real-time tokens (progress counter, not displayed)
            token_text = wd.drain_tokens()
            if token_text:
                yield _sse("token", {"type": "token", "text": token_text})

            # Drain segments (new ones only)
            all_segs = wd.drain_segments()
            for seg in all_segs[sent_seg_count:]:
                yield _sse("segment", seg)
            sent_seg_count = len(all_segs)

            # Drain choices
            choices = wd.drain_choices()
            if choices:
                yield _sse("choices", choices)

            # Drain status messages → wait events
            for msg in wd.drain_status():
                yield _sse("wait", {"type": "wait", "message": msg})

            # Drain errors
            for err in wd.drain_errors():
                yield _sse("error", {"type": "error", "message": err})

            # done: detect rising edge (clear→set) so each round fires once
            if sd.done.is_set():
                if not was_done:
                    was_done = True
                    if sd.error:
                        yield _sse(
                            "error",
                            {"type": "error", "message": sd.error},
                        )
                    else:
                        yield _sse(
                            "done",
                            {
                                "type": "done",
                                "round_number": sd.game_loop.round_count,
                            },
                        )
            else:
                was_done = False  # user submitted a choice, reset for next round

            # Heartbeat
            now_ts = time.monotonic()
            if now_ts - last_heartbeat > 15:
                yield _sse("heartbeat", {"type": "heartbeat"})
                last_heartbeat = now_ts

            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/game/{session_id}/choice")
async def submit_choice(session_id: str, req: ChoiceRequest):
    """Submit a player choice and continue the game round."""
    sd = sessions.get(session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail="Session not found")

    if sd.processing:
        raise HTTPException(status_code=409, detail="A round is already in progress")

    if sd.game_loop.last_parsed is None or not sd.game_loop.last_parsed.choices:
        raise HTTPException(status_code=400, detail="No choices available")

    # Validate choice_key is in range
    opts = sd.game_loop.get_available_options()
    try:
        idx = int(req.choice_key)
        if idx < 1 or idx > len(opts):
            raise HTTPException(
                status_code=400,
                detail=f"Choice must be between 1 and {len(opts)}",
            )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid choice_key")

    # Reset for new round
    sd.processing = True
    sd.error = None
    sd.done.clear()
    sd.web_display.reset_round_done()

    thread = threading.Thread(
        target=_run_stream_round_in_thread,
        args=(sd, sd.game_loop.continue_round_stream),
        kwargs={"choice_key": req.choice_key},
        daemon=True,
    )
    sd.task_thread = thread
    thread.start()

    return {
        "session_id": session_id,
        "message": "Choice accepted. Watch SSE stream for next round.",
    }


@app.get("/api/game/{session_id}/state")
async def get_state(session_id: str):
    """Return the current game state as a JSON snapshot."""
    sd = sessions.get(session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail="Session not found")

    gl = sd.game_loop
    parsed = gl.last_parsed

    return {
        "session_id": session_id,
        "round_number": gl.round_count,
        "current_node": gl.current_node,
        "state_vars": gl.game_state.state_vars,
        "has_choices": bool(parsed and parsed.choices),
        "error": sd.error,
    }


@app.delete("/api/game/{session_id}")
async def end_session(session_id: str):
    """End a game session and clean up resources."""
    sd = sessions.remove(session_id)
    if sd is None:
        raise HTTPException(status_code=404, detail="Session not found")
    sd.done.set()  # unblock any waiting SSE consumer
    return {"message": "Session ended"}


# ── Co-creation routes ──────────────────────────────────────────────


class SeedRequest(BaseModel):
    seed: str


# Separate session store for co-creation
_cocreate_sessions: dict[str, WebCoCreateDisplay] = {}
_cocreate_lock = threading.Lock()


@app.get("/cocreate")
async def serve_cocreate():
    """Serve the co-creation frontend."""
    return FileResponse(_WEB_DIR / "cocreate.html")


@app.post("/api/cocreate")
async def start_cocreate(req: SeedRequest):
    """Start the co-creation flow with a seed idea.

    Spawns a background thread running CoCreateFlow.run().
    Returns a session_id for the SSE stream.
    """
    try:
        api_client = ApiClient()
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    display = WebCoCreateDisplay()
    flow = CoCreateFlow(api_client, display)

    session_id = uuid.uuid4().hex[:12]
    with _cocreate_lock:
        _cocreate_sessions[session_id] = display

    def _run():
        try:
            result = flow.run()
            display.set_result(result.story_config, result.outline_text)
        except CoCreationAborted:
            display.set_error("aborted")
        except Exception as e:
            display.set_error(str(e))
        finally:
            display.signal_done()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return {"session_id": session_id}


@app.get("/api/cocreate/{session_id}/stream")
async def stream_cocreate(session_id: str, request: Request):
    """SSE endpoint for co-creation progress."""
    with _cocreate_lock:
        display = _cocreate_sessions.get(session_id)
    if display is None:
        raise HTTPException(status_code=404, detail="Session not found")

    async def event_generator():
        last_heartbeat = time.monotonic()
        was_prompting = False

        while True:
            if await request.is_disconnected():
                return

            # Drain output text
            out_text = display.drain_output()
            if out_text:
                yield _sse("output", {"type": "output", "text": out_text})

            # Drain status → wait events
            for msg in display.drain_status():
                yield _sse("wait", {"type": "wait", "message": msg})

            # Drain errors
            for err in display.drain_errors():
                yield _sse("error", {"type": "error", "message": err})

            # Check for prompt (waiting for user input)
            if display.has_prompt and not was_prompting:
                was_prompting = True
                yield _sse(
                    "prompt",
                    {"type": "prompt", "text": display.drain_prompt()},
                )
            elif not display.has_prompt:
                was_prompting = False

            # Check if done
            if display.done.is_set():
                if display.error_msg:
                    yield _sse(
                        "error",
                        {"type": "error", "message": display.error_msg},
                    )
                else:
                    yield _sse("result", display.result)
                return

            # Heartbeat
            now_ts = time.monotonic()
            if now_ts - last_heartbeat > 15:
                yield _sse("heartbeat", {"type": "heartbeat"})
                last_heartbeat = now_ts

            await asyncio.sleep(0.1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/cocreate/{session_id}/input")
async def cocreate_input(session_id: str, req: dict):
    """Submit user's answer to the current co-creation prompt."""
    with _cocreate_lock:
        display = _cocreate_sessions.get(session_id)
    if display is None:
        raise HTTPException(status_code=404, detail="Session not found")

    answer = req.get("answer", "")
    display.submit_answer(answer)
    return {"message": "ok"}


@app.post("/api/cocreate/{session_id}/abort")
async def cocreate_abort(session_id: str):
    """Abort the co-creation flow."""
    with _cocreate_lock:
        display = _cocreate_sessions.pop(session_id, None)
    if display is None:
        raise HTTPException(status_code=404, detail="Session not found")
    display.submit_answer("退出")
    return {"message": "aborted"}


# ── SSE formatting helper ───────────────────────────────────────────


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event line."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

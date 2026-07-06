"""Web display — buffers output data for web server consumption.

Replaces terminal `Display` with thread-safe buffered collections.
GameLoop calls the same show_*() methods, but data is stored for
the FastAPI SSE layer to drain and push to the browser.
"""

import threading
from storyloom.xml_parser import Segment


class WebDisplay:
    """Buffer-based display for web server consumption.

    Thread-safe: the GameLoop background thread writes segments/choices,
    the FastAPI SSE coroutine drains them via the drain_*() methods.
    """

    def __init__(self):
        self._lock = threading.Lock()

        # Accumulated data (producer: GameLoop thread)
        self._segments: list[dict] = []
        self._choices: dict | None = None
        self._state_snapshot: dict | None = None
        self._status_messages: list[str] = []
        self._errors: list[str] = []
        self._tokens: list[str] = []  # real-time LLM token stream

        # Sentinel to signal "round complete" to the SSE consumer
        self._round_done = threading.Event()

    # ── Producer methods (called by GameLoop in background thread) ──

    def show_segment(self, seg: Segment, delay_ms: int = 300) -> None:
        """Buffer a single narrative segment."""
        _ = delay_ms  # ignored in web mode
        with self._lock:
            self._segments.append({
                "type": "segment",
                "n": seg.n,
                "text": seg.text,
                "position": seg.position,
                "branch": seg.branch,
            })

    def show_segments(self, segments: list[Segment], delay_ms: int = 300) -> None:
        """Buffer multiple narrative segments."""
        for seg in segments:
            self.show_segment(seg, delay_ms=delay_ms)

    def show_options(
        self, choice_id: str, branches: list[str], labels: list[str]
    ) -> None:
        """Buffer the choice panel."""
        with self._lock:
            self._choices = {
                "type": "choices",
                "choice_id": choice_id,
                "options": [
                    {"index": i + 1, "branch": b, "label": l}
                    for i, (b, l) in enumerate(zip(branches, labels))
                ],
            }

    def show_state(self, state_vars: dict) -> None:
        """Buffer a state variable snapshot."""
        with self._lock:
            self._state_snapshot = {"type": "state", "vars": dict(state_vars)}

    def show_token(self, text: str) -> None:
        """Buffer a single LLM token for real-time streaming."""
        with self._lock:
            self._tokens.append(text)

    def buffer_segment_dict(self, seg: dict) -> None:
        """Buffer a segment from a stream event dict (no Segment object needed)."""
        with self._lock:
            self._segments.append(seg)

    def buffer_choices_raw(self, choices: list[dict]) -> None:
        """Buffer choice panels from raw parsed choice list.

        Args:
            choices: List of choice dicts, each with id/branches/labels keys.
        """
        with self._lock:
            last = choices[-1]
            self._choices = {
                "type": "choices",
                "choice_id": last["id"],
                "options": [
                    {"index": i + 1, "branch": b, "label": l}
                    for i, (b, l) in enumerate(
                        zip(last["branches"], last["labels"])
                    )
                ],
            }

    def show_wait_message(self, msg: str) -> None:
        """Buffer a status / progress message."""
        with self._lock:
            self._status_messages.append(msg)

    def show_error(self, msg: str) -> None:
        """Buffer an error message."""
        with self._lock:
            self._errors.append(msg)

    def show_separator(self) -> None:
        """No-op in web mode."""
        pass

    def show_section_break(self) -> None:
        """No-op in web mode."""
        pass

    def show_main_menu(self, save_count: int) -> None:
        """No-op in web mode."""
        pass

    def get_input(self, prompt: str = "") -> str:
        """Not available in web mode."""
        raise NotImplementedError("get_input is not available in web mode")

    def signal_round_done(self) -> None:
        """Signal that the current round is complete."""
        self._round_done.set()

    def reset_round_done(self) -> None:
        """Clear the round-done signal for the next round."""
        self._round_done.clear()

    # ── Consumer methods (called by FastAPI SSE coroutine) ──────────

    def drain_segments(self) -> list[dict]:
        """Atomically fetch and clear buffered segments."""
        with self._lock:
            segs = list(self._segments)
            self._segments.clear()
            return segs

    def drain_choices(self) -> dict | None:
        """Fetch and clear the current choice panel."""
        with self._lock:
            c = self._choices
            self._choices = None
            return c

    def drain_state(self) -> dict | None:
        """Fetch and clear the state snapshot."""
        with self._lock:
            s = self._state_snapshot
            self._state_snapshot = None
            return s

    def drain_status(self) -> list[str]:
        """Fetch and clear status messages."""
        with self._lock:
            msgs = list(self._status_messages)
            self._status_messages.clear()
            return msgs

    def drain_errors(self) -> list[str]:
        """Fetch and clear error messages."""
        with self._lock:
            errs = list(self._errors)
            self._errors.clear()
            return errs

    def drain_tokens(self) -> str:
        """Fetch and clear buffered tokens, returning them as a single string."""
        with self._lock:
            text = "".join(self._tokens)
            self._tokens.clear()
            return text

    @property
    def round_done(self) -> threading.Event:
        """Event that is set when the current round completes."""
        return self._round_done

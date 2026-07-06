"""Web co-creation display — buffers output for web consumption.

Replaces terminal Display with thread-safe buffers + async get_input
via threading.Event.  CoCreateFlow calls the same interface, but
output is stored for the FastAPI SSE layer to drain and push to the
browser; get_input blocks until the user submits an answer via API.
"""

import threading


class _OutputBuffer:
    """File-like buffer that captures write() calls as strings."""

    def __init__(self):
        self._lock = threading.Lock()
        self._lines: list[str] = []

    def write(self, text: str) -> None:
        with self._lock:
            self._lines.append(text)

    def flush(self) -> None:
        pass

    def drain(self) -> str:
        """Fetch and clear all captured output."""
        with self._lock:
            text = "".join(self._lines)
            self._lines.clear()
            return text


class WebCoCreateDisplay:
    """Buffer-based display for web co-creation consumption.

    Thread-safe: the background thread writes output / prompts,
    the FastAPI SSE coroutine drains them.  get_input() blocks
    the background thread until the user submits an answer.
    """

    def __init__(self):
        self.output = _OutputBuffer()

        self._lock = threading.Lock()
        self._status_messages: list[str] = []
        self._errors: list[str] = []
        self._current_prompt: str | None = None
        self._user_answer: str | None = None
        self._answer_event = threading.Event()
        self._done = threading.Event()
        self._result: dict | None = None
        self._error_msg: str | None = None

    # ── UiInterface protocol (called by CoCreateFlow in background thread) ──

    def write(self, text: str) -> None:
        """Display text to the user — delegates to output buffer."""
        self.output.write(text)

    def show_wait_message(self, msg: str) -> None:
        """Buffer a status / progress message."""
        with self._lock:
            self._status_messages.append(msg)

    def show_error(self, msg: str) -> None:
        """Buffer an error message."""
        with self._lock:
            self._errors.append(msg)

    def ask(self, prompt: str = "") -> str:
        """Ask user for input — alias for get_input following UiInterface."""
        return self.get_input(prompt)

    def get_input(self, prompt: str = "") -> str:
        """Block until the user submits an answer via API.

        Sets the current prompt, clears the answer event, and waits.
        The SSE layer picks up the prompt and the frontend displays
        an input field.  POST /api/cocreate/{sid}/input unblocks.
        """
        with self._lock:
            self._current_prompt = prompt
        self._answer_event.clear()
        self._answer_event.wait()
        with self._lock:
            answer = self._user_answer or ""
            self._user_answer = None
            self._current_prompt = None
        return answer

    def submit_answer(self, answer: str) -> None:
        """Called from the API when the user submits a response."""
        with self._lock:
            self._user_answer = answer
        self._answer_event.set()

    def set_result(self, story_config: dict, outline_text: str) -> None:
        """Store the final co-creation result."""
        with self._lock:
            self._result = {
                "story_config": story_config,
                "outline_text": outline_text,
            }

    def set_error(self, msg: str) -> None:
        """Set a fatal error that ends the co-creation."""
        with self._lock:
            self._error_msg = msg

    def signal_done(self) -> None:
        """Signal that the co-creation flow is complete."""
        self._done.set()

    # ── Consumer methods (called by FastAPI SSE coroutine) ──────────

    def drain_output(self) -> str:
        """Fetch and clear captured output text."""
        return self.output.drain()

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

    def drain_prompt(self) -> str | None:
        """Fetch and clear the current prompt (non-blocking).

        Returns the prompt text if the background thread is waiting
        for user input, or None otherwise.
        """
        with self._lock:
            prompt = self._current_prompt
            # Don't clear — the prompt stays until answered.
            # The frontend uses the prompt text to show an input field.
            return prompt

    @property
    def has_prompt(self) -> bool:
        """True if the co-creation flow is waiting for user input."""
        with self._lock:
            return self._current_prompt is not None

    @property
    def result(self) -> dict | None:
        """Final co-creation result, or None if not yet complete."""
        with self._lock:
            return self._result

    @property
    def error_msg(self) -> str | None:
        """Fatal error message, if any."""
        with self._lock:
            return self._error_msg

    @property
    def done(self) -> threading.Event:
        """Event that is set when co-creation is complete."""
        return self._done

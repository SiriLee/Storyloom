"""Streaming XML parser — produces Event objects from token lines.

Per design.md §3.2: line-by-line parsing of the token stream into Events.
Image-tag triggering of TaskGenerator and DECLARE filtering are Phase 2
concerns.

Converts the token stream into program-processable Events.  Never blocks,
never accumulates business data.

Usage::

    parser = StreamParser()
    for line in lines:
        for event in parser.feed_line(line):
            handle(event)
"""

import re
from dataclasses import dataclass, field
from enum import Enum, auto

from storyloom.config import SCENE_VAR_NAME


# ── Event ──────────────────────────────────────────────────────────
# Per design.md §4.1:
#   Event:
#     type: EventType
#     line: int           # line number from NNN| prefix
#     payload: dict       # type-specific data


class EventType(Enum):
    """Types of events flowing through the pipeline (design.md §4.1)."""
    STORY_BEGIN = auto()       # <story>
    STORY_END = auto()         # </story>
    SEGMENT = auto()           # <seg>text</seg>
    CHOICE_BEGIN = auto()      # <choice id="X">
    OPT = auto()               # <opt key="A" branch="X">text</opt>
    CHOICE_END = auto()        # </choice>
    SET = auto()               # <set var="X" op="+" val="5"/>
    CHECKPOINT = auto()        # <checkpoint node="X" summary="...">
    ROUTE = auto()             # <route if="X" target="Y"/>
    CHECKPOINT_END = auto()    # </checkpoint>
    BRIDGE = auto()            # <bridge/>
    BRANCH_ENTER = auto()      # <branch name="X">
    BRANCH_EXIT = auto()       # </branch>
    PARSE_ERROR = auto()       # Unrecognized or invalid element
    SCENE = auto()             # <set var="SCENE" val="...">   (Phase 2)
    DECLARE = auto()           # <declare kind="CHAR/SCENE" name="...">...</declare>  (Phase 2)


@dataclass
class Event:
    """Unified event type flowing through the entire pipeline.

    Per design.md §4.1 — Event carries type, line number, and a
    type-specific payload dict through all three pipeline stages
    (StreamParser → StateManager → EventDispatcher).

    Payload keys by event type::

        STORY_BEGIN    — (empty)
        STORY_END      — (empty)
        SEGMENT        — text, position, branch, char (optional, Phase 2)
        CHOICE_BEGIN   — id
        OPT            — key, branch, if, text
        CHOICE_END     — choice_data (accumulated from CHOICE_BEGIN + OPT)
        SET            — var, op, val, if
        CHECKPOINT     — node, summary
        ROUTE          — if, target
        CHECKPOINT_END — (empty)
        BRIDGE         — (empty)
        BRANCH_ENTER   — name, position
        BRANCH_EXIT    — name, position
        PARSE_ERROR    — error
        SCENE          — val (local_name)                      (Phase 2)
        DECLARE        — kind, name, desc                      (Phase 2)
    """
    type: EventType
    line: int
    payload: dict = field(default_factory=dict)


# ── Line regex patterns ───────────────────────────────────────────
# Each line may start with NNN|  (line-number prefix), which is
# stripped before matching.

_RE_STORY_OPEN = re.compile(r'^<story>\s*$')
_RE_STORY_CLOSE = re.compile(r'^</story>\s*$')
_RE_SEG = re.compile(r'^<seg(?: char="([^"]*)")?>(.*)</seg>\s*$')
_RE_CHOICE_OPEN = re.compile(r'^<choice id="([^"]+)">\s*$')
_RE_CHOICE_CLOSE = re.compile(r'^</choice>\s*$')
_RE_OPT = re.compile(
    r'^<opt key="(\d+)"(?: branch="([^"]+)")?(?: if="([^"]+)")?>(.*)</opt>\s*$'
)
_RE_SET = re.compile(
    r'^<set var="([^"]+)"(?: op="([^"]+)")? val="([^"]+)"'
    r'(?: if="([^"]+)")?\s*/>\s*$'
)
_RE_CHECKPOINT_OPEN = re.compile(
    r'^<checkpoint node="([^"]+)" summary="([^"]+)">\s*$'
)
_RE_CHECKPOINT_SELF_CLOSE = re.compile(
    r'^<checkpoint node="([^"]+)" summary="([^"]+)"\s*/>\s*$'
)
_RE_CHECKPOINT_CLOSE = re.compile(r'^</checkpoint>\s*$')
_RE_ROUTE = re.compile(
    r'^<route(?: if="([^"]+)")? target="([^"]+)"/>\s*$'
)
_RE_BRIDGE = re.compile(r'^<bridge\s*/>\s*$')
_RE_BRANCH_OPEN = re.compile(r'^<branch name="([^"]+)">\s*$')
_RE_BRANCH_CLOSE = re.compile(r'^</branch>\s*$')
_RE_DECLARE = re.compile(
    r'^<declare kind="([^"]+)" name="([^"]+)">(.*)</declare>\s*$'
)


# ── StreamParser ───────────────────────────────────────────────────


class StreamParser:
    """Pure line-by-line streaming parser: line → Event.

    Per design.md §3.2: line-by-line parsing of token stream into Events.
    Per design.md §3.5: converts the content source from producing tokens
    to producing program-processable Events.

    ``feed_line()`` is synchronous and side-effect-free — never blocks.
    The parse state machine (in_story / in_branch / in_checkpoint /
    in_choice / post_bridge) affects only the interpretation of the
    current line.

    Does NOT accumulate business data (segments, sets, routes, etc.)
    — that is StateManager's responsibility per design.md §3.2.
    """

    def __init__(self):
        # ── Parse state machine ───────────────────────────────────
        self._in_story = False
        self._in_branch: str | None = None
        self._in_checkpoint = False
        self._in_choice: str | None = None
        self._post_bridge = False
        self._bridge_seen = False

        # ── Counters ──────────────────────────────────────────────
        self._line_count = 0

        # ── Pending choice accumulator ────────────────────────────
        # Needed to build choice_data at CHOICE_END.  This is a
        # parse-time concern (reconstructing structured data from
        # streaming open/body/close tags), not business data
        # accumulation.
        self._pending_choices: list[dict] = []

        # ── Format errors ─────────────────────────────────────────
        # Post-bridge violation detection is inherently a parse-time
        # concern — only the parser knows whether it is currently
        # post-bridge.  StateManager reads this at end-of-round.
        self._format_errors: list[str] = []

    # ── Public API ─────────────────────────────────────────────────

    def feed_line(self, line: str) -> list[Event]:
        """Process one line and return any events it generates.

        Per design.md §3.5: pure format conversion — never blocks.

        Args:
            line: Raw line from LLM output (may include ``NNN| `` prefix).

        Returns:
            List of 0–1 ``Event`` objects.  A line produces at most one
            event; empty lines and XML comments produce none.
        """
        # Extract and strip line-number prefix (NNN| ).
        # The local counter is authoritative; the NNN| prefix from the
        # LLM is used only to verify the LLM's numbering.  Mismatches
        # are recorded as format errors so the LLM can self-correct.
        prefix_match = re.match(r'^(\d{3})\| ', line)
        llm_line_num = int(prefix_match.group(1)) if prefix_match else None
        clean = line[5:].strip() if prefix_match else line.strip()
        if not clean:
            return []

        # Skip XML comments
        if clean.startswith('<!--'):
            return []

        self._line_count += 1

        # Verify LLM line numbering against the authoritative local counter
        if llm_line_num is not None and llm_line_num != self._line_count:
            self._format_errors.append(
                f"Line number mismatch at line {self._line_count}: "
                f"LLM says {llm_line_num:03d}, parser expects {self._line_count:03d}"
            )

        # ── Container open / close ────────────────────────────────
        if _RE_STORY_OPEN.match(clean):
            self._in_story = True
            return [Event(type=EventType.STORY_BEGIN,
                          line=self._line_count)]

        if _RE_STORY_CLOSE.match(clean):
            self._in_story = False
            return [Event(type=EventType.STORY_END,
                          line=self._line_count)]

        if not self._in_story:
            return []

        m = _RE_CHOICE_OPEN.match(clean)
        if m:
            self._in_choice = m.group(1)
            if self._post_bridge:
                self._format_errors.append(
                    f"<choice> found after <bridge/> (line {self._line_count})"
                )
                return []
            return [Event(
                type=EventType.CHOICE_BEGIN,
                line=self._line_count,
                payload={"id": m.group(1), "position": self._position,
                         "branch": self._in_branch},
            )]

        if _RE_CHOICE_CLOSE.match(clean):
            if self._post_bridge:
                self._format_errors.append(
                    f"</choice> found after <bridge/>"
                    f" (line {self._line_count})"
                )
                return []
            # Pop the current choice — each CHOICE_END consumes its
            # own accumulated data.  Without pop(), an empty <choice>
            # (no <opt> children) would inherit the previous choice's
            # payload, violating Event payload isolation (§4.1).
            choice_data = (
                dict(self._pending_choices.pop())
                if self._pending_choices
                else None
            )
            self._in_choice = None
            return [Event(
                type=EventType.CHOICE_END,
                line=self._line_count,
                payload={
                    "position": self._position,
                    "choice_data": choice_data,
                    "branch": self._in_branch,
                },
            )]

        m = _RE_CHECKPOINT_OPEN.match(clean)
        if m:
            if self._post_bridge:
                self._format_errors.append(
                    f"<checkpoint> found after <bridge/>"
                    f" (line {self._line_count})"
                )
                return []
            self._in_checkpoint = True
            return [Event(
                type=EventType.CHECKPOINT,
                line=self._line_count,
                payload={
                    "node": m.group(1),
                    "summary": m.group(2),
                    "position": self._position,
                },
            )]

        m = _RE_CHECKPOINT_SELF_CLOSE.match(clean)
        if m:
            if self._post_bridge:
                self._format_errors.append(
                    f"<checkpoint> found after <bridge/>"
                    f" (line {self._line_count})"
                )
                return []
            return [Event(
                type=EventType.CHECKPOINT,
                line=self._line_count,
                payload={
                    "node": m.group(1),
                    "summary": m.group(2),
                    "position": self._position,
                },
            )]

        if _RE_CHECKPOINT_CLOSE.match(clean):
            if self._post_bridge:
                self._format_errors.append(
                    f"</checkpoint> found after <bridge/>"
                    f" (line {self._line_count})"
                )
                return []
            self._in_checkpoint = False
            return [Event(
                type=EventType.CHECKPOINT_END,
                line=self._line_count,
                payload={"position": self._position},
            )]

        m = _RE_BRANCH_OPEN.match(clean)
        if m:
            branch_name = m.group(1)
            self._in_branch = branch_name
            return [Event(
                type=EventType.BRANCH_ENTER,
                line=self._line_count,
                payload={"name": branch_name, "position": self._position},
            )]

        if _RE_BRANCH_CLOSE.match(clean):
            branch_name = self._in_branch
            self._in_branch = None
            return [Event(
                type=EventType.BRANCH_EXIT,
                line=self._line_count,
                payload={
                    "name": branch_name,
                    "position": self._position,
                },
            )]

        # ── Bridge ────────────────────────────────────────────────
        if _RE_BRIDGE.match(clean):
            if self._post_bridge:
                self._format_errors.append(
                    f"<bridge/> found after <bridge/>"
                    f" (line {self._line_count})"
                )
                return []
            self._bridge_seen = True
            self._post_bridge = True
            return [Event(type=EventType.BRIDGE, line=self._line_count)]

        # ── Leaf elements ─────────────────────────────────────────
        m = _RE_SEG.match(clean)
        if m:
            char_val = m.group(1)  # None if no char attribute
            text = m.group(2).strip()

            payload = {
                "text": text,
                "position": self._position,
                "branch": self._in_branch,
            }
            if char_val:  # non-empty only — "" same as absent
                payload["char"] = char_val

            return [Event(type=EventType.SEGMENT, line=self._line_count,
                          payload=payload)]

        m = _RE_OPT.match(clean)
        if m:
            if self._post_bridge:
                self._format_errors.append(
                    f"<opt> found after <bridge/>"
                    f" (line {self._line_count})"
                )
                return []
            key = m.group(1)
            branch = m.group(2)
            if_cond = m.group(3)
            text = m.group(4).strip()

            # Accumulate into pending choices for CHOICE_END
            if self._in_choice is not None:
                pending = self._pending_choices
                if not pending or pending[-1]["id"] != self._in_choice:
                    pending.append({
                        "id": self._in_choice,
                        "branches": [],
                        "labels": [],
                        "conditions": {},
                    })
                pending[-1]["branches"].append(branch)
                pending[-1]["labels"].append(text)
                if if_cond:
                    pending[-1]["conditions"][branch] = if_cond

            return [Event(
                type=EventType.OPT,
                line=self._line_count,
                payload={
                    "key": key,
                    "target": branch,
                    "if": if_cond,
                    "text": text,
                    "position": self._position,
                    "branch": self._in_branch,
                },
            )]

        m = _RE_SET.match(clean)
        if m:
            var = m.group(1)
            op = m.group(2) or "="
            val = m.group(3)
            if_cond = m.group(4)

            # SCENE interception (Phase 2): <set var="SCENE" val="...">
            # is a separate event type — scene switch, not state change.
            if var == SCENE_VAR_NAME:
                if op != "=":
                    return [Event(
                        type=EventType.PARSE_ERROR,
                        line=self._line_count,
                        payload={"error": f"SCENE does not support op={op!r}"},
                    )]
                if self._post_bridge:
                    self._format_errors.append(
                        f"<set var=\"SCENE\"> found after <bridge/>"
                        f" (line {self._line_count})"
                    )
                    return []
                return [Event(
                    type=EventType.SCENE,
                    line=self._line_count,
                    payload={
                        "val": val,
                        "if": if_cond,
                        "position": self._position,
                        "branch": self._in_branch,
                    },
                )]

            if self._post_bridge:
                self._format_errors.append(
                    f"<set> found after <bridge/> (line {self._line_count})"
                )
                return []

            return [Event(
                type=EventType.SET,
                line=self._line_count,
                payload={
                    "var": var,
                    "op": op,
                    "val": val,
                    "if": if_cond,
                    "position": self._position,
                    "branch": self._in_branch,
                },
            )]

        m = _RE_ROUTE.match(clean)
        if m:
            if self._post_bridge:
                self._format_errors.append(
                    f"<route> found after <bridge/>"
                    f" (line {self._line_count})"
                )
                return []
            if_cond = m.group(1)
            target = m.group(2)
            return [Event(
                type=EventType.ROUTE,
                line=self._line_count,
                payload={
                    "if": if_cond,
                    "target": target,
                    "position": self._position,
                },
            )]

        # ── DECLARE (Phase 2) ──────────────────────────────────────
        # Per design.md §4.1: parsed + validated, does NOT enter the
        # event stream.  Only triggers TaskGenerator (§7.6).
        m = _RE_DECLARE.match(clean)
        if m:
            kind = m.group(1)
            name = m.group(2)
            desc = m.group(3).strip()

            if kind.upper() not in ("CHAR", "SCENE"):
                return [Event(
                    type=EventType.PARSE_ERROR,
                    line=self._line_count,
                    payload={"error": f"Invalid declare kind: {kind!r}"},
                )]

            if self._post_bridge:
                self._format_errors.append(
                    f"<declare> found after <bridge/>"
                    f" (line {self._line_count})"
                )
                return []

            # Build event (validated, full info) — discarded in §7.5.
            # §7.6: pipeline coordinator calls task_gen.enqueue(event).
            _declare_event = Event(
                type=EventType.DECLARE,
                line=self._line_count,
                payload={"kind": kind, "name": name, "desc": desc},
            )
            # TODO(§7.6): task_gen.enqueue(_declare_event)
            return []

        # ── Unrecognized line ─────────────────────────────────────
        # Post-bridge violations (LLM output error → record for feedback)
        if self._post_bridge:
            for tag in ("choice", "set", "checkpoint"):
                if f"<{tag}" in clean:
                    self._format_errors.append(
                        f"<{tag}> found after <bridge/>"
                        f" (line {self._line_count})"
                    )

        # Lines that look like XML but match no known pattern are LLM
        # output errors.  Emit a PARSE_ERROR event (for the pipeline /
        # UI) and record a format_error (for LLM feedback next round).
        if "<" in clean and ">" in clean:
            self._format_errors.append(
                f"Unrecognized element at line {self._line_count}: {clean}"
            )
            return [Event(
                type=EventType.PARSE_ERROR,
                line=self._line_count,
                payload={"error": f"Unrecognized element: {clean}"},
            )]

        return []

    # ── Properties ────────────────────────────────────────────────

    @property
    def _position(self) -> str:
        """Current position relative to bridge: ``"pre"`` or ``"post"``."""
        return "post" if self._post_bridge else "pre"

    @property
    def bridge_seen(self) -> bool:
        """Whether ``<bridge/>`` has been encountered."""
        return self._bridge_seen

    @property
    def in_checkpoint(self) -> bool:
        """Whether parser is currently inside a ``<checkpoint>`` block."""
        return self._in_checkpoint

    @property
    def format_errors(self) -> list[str]:
        """Format errors detected during parsing.

        Post-bridge prohibited elements, duplicate bridges, etc.
        Read by StateManager at end of round.
        """
        return list(self._format_errors)


# ── LineBuffer ────────────────────────────────────────────────────


class LineBuffer:
    """Accumulates token chunks and yields complete lines.

    The API streams individual tokens (sub-word chunks).  The streaming
    parser needs complete lines delimited by ``\\n``.  This adapter sits
    between the token stream and the parser.

    Usage::

        lb = LineBuffer()
        for chunk in api_stream:
            for line in lb.feed(chunk):
                process(line)
        remaining = lb.flush()
        if remaining:
            process(remaining)
    """

    def __init__(self):
        self._buffer: str = ""

    def feed(self, text: str) -> list[str]:
        """Feed a token chunk; return any completed lines.

        Lines are stripped of leading / trailing whitespace.  Empty
        lines are omitted from the return list.
        """
        self._buffer += text
        if "\n" not in self._buffer:
            return []

        parts = self._buffer.split("\n")
        if text.endswith("\n"):
            self._buffer = ""
            complete = parts
        else:
            self._buffer = parts[-1]
            complete = parts[:-1]

        return [s.strip() for s in complete if s.strip()]

    def flush(self) -> str | None:
        """Return any remaining buffered text (end-of-stream).

        Returns ``None`` if the buffer is empty.
        """
        if self._buffer:
            result = self._buffer.strip()
            self._buffer = ""
            return result if result else None
        return None


# ── Shared data types ─────────────────────────────────────────────
# Used across the pipeline: StateManager accumulates Segment /
# SetOperation / RouteTarget; GameLoop and ContextManager consume
# ParsedOutput; GameState accepts SetOperation for validation.


class ParseError(Exception):
    """Raised when XML output is malformed or violates rules."""
    pass


@dataclass
class Segment:
    """A single narrative segment."""
    text: str
    position: str  # "pre" or "post"
    branch: str | None = None


@dataclass
class SetOperation:
    """A state change operation."""
    var: str
    op: str
    val: str
    condition: str | None = None


@dataclass
class RouteTarget:
    """A checkpoint route target."""
    condition: str | None
    target: str


@dataclass
class ParsedOutput:
    """Structured result of processing a round's events.

    Produced by ``StateManager.get_result()`` after processing all
    events in a round.  Consumed by GameLoop (context management,
    observer notification) and dev_cli (debug display).
    """
    segments: list[Segment] = field(default_factory=list)
    total_segments: int = 0
    pre_segments: int = 0
    post_segments: int = 0
    choice_id: str | None = None
    opt_branches: list[str] = field(default_factory=list)
    choices: list[dict] = field(default_factory=list)
    sets: list[SetOperation] = field(default_factory=list)
    checkpoint_node: str | None = None
    checkpoint_summary: str | None = None
    routes: list[RouteTarget] = field(default_factory=list)
    bridge_found: bool = False
    bridge_text: str = ""
    numbering_issues: list[str] = field(default_factory=list)
    pre_branches: list[str] = field(default_factory=list)
    post_branches: list[str] = field(default_factory=list)

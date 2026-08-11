"""Main narrative game loop, GameState, and result types.

Coordinates all modules: PromptBuilder, ContextManager, ApiClient,
StreamParser, StateManager, EventDispatcher.  Validates all
LLM-suggested state changes (local source of truth).
"""

import copy
import logging
import os
import queue
import re
import threading
import time
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

logger = logging.getLogger("storyloom")

from storyloom.config import DEFAULT_MEDIA_DIR, SAVE_VERSION, STREAM_STALL_TIMEOUT_SEC, GLOBAL_SCOPE
from storyloom.io.api_client import ApiClient
from storyloom.core.context_manager import ContextManager
from storyloom.core.prompt_builder import PromptBuilder
from storyloom.parser.stream_parser import (
    EventType,
    LineBuffer,
    ParsedOutput,
    SetOperation,
    StreamParser,
)
from storyloom.core.state_manager import StateManager
from storyloom.core.event_dispatcher import EventDispatcher

if TYPE_CHECKING:
    from storyloom.assets import GameAssetRoster
    from storyloom.tasks import TaskPool


@dataclass
class SetResult:
    """Result of applying a state change suggestion."""

    accepted: bool
    reason: str | None = None


@dataclass
class RoundResult:
    """Result of processing one narrative round."""

    parsed: ParsedOutput
    round_number: int
    ending_triggered: bool = False


@dataclass
class RoundRecord:
    """Snapshot of a completed narrative round for observers.

    Contains everything needed for debugging, testing, and analytics:
    the full messages array sent to the API, the raw LLM response,
    timing data, and the parsed output.
    """

    round_number: int
    messages_sent: list[dict]           # full messages array sent to API
    raw_response: str                   # LLM raw output
    parsed: ParsedOutput | None         # parsed result (None if parse failed)
    ttft: float | None                  # seconds to first token
    tokens: dict | None                 # {"prompt": N, "completion": N, "total": N}
    timestamp: str                      # ISO 8601
    node: str | None                    # current_node this round
    selected_branch: str | None         # player's chosen branch name (None if no choice)


# ── GameState ─────────────────────────────────────────────────────


class GameState:
    """Manages in-memory game state variables.

    The LLM can only SUGGEST changes via <set> elements.
    The program validates each suggestion — type checks, range checks,
    variable existence — before applying.
    """

    VALID_NUMBER_OPS = {"+", "-", "="}
    VALID_STRING_OPS = {"="}
    NUMBER_MIN = 0
    NUMBER_MAX = 100

    def __init__(self, variables: list[dict] | None = None):
        """Initialize state from variable definitions.

        Args:
            variables: List of variable definitions.
                       Each variable has: scope (optional), name, type, initial.
                       scope omitted = GLOBAL. None or empty list → no state variables.

        Raises:
            ValueError: On unsupported variable type.
        """
        self._state_vars: dict[str, dict] = {}          # {scope: {name: value}}
        self._var_types: dict[str, dict[str, str]] = {}  # {scope: {name: type}}

        for v in (variables or []):
            scope = v.get("scope") or GLOBAL_SCOPE
            name = v["name"]
            var_type = v["type"]
            initial = v["initial"]

            if scope not in self._state_vars:
                self._state_vars[scope] = {}
                self._var_types[scope] = {}

            if var_type == "number":
                self._state_vars[scope][name] = int(initial)
            elif var_type == "string":
                self._state_vars[scope][name] = initial
            else:
                raise ValueError(f"Unknown variable type: {var_type}")

            self._var_types[scope][name] = var_type

    @property
    def state_vars(self) -> dict:
        """Return current state variables as a nested dict copy.

        Format: ``{scope: {name: value}}``.
        """
        return {s: dict(vars_) for s, vars_ in self._state_vars.items()}

    def to_dict(self) -> dict:
        """Serialize state variables to a plain dict.

        Returns:
            Dict with 'state_vars' key containing current nested values.
        """
        return {
            "state_vars": {
                s: dict(vars_) for s, vars_ in self._state_vars.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict, variables: list[dict]) -> "GameState":
        """Restore GameState from save data.

        Uses *variables* for type definitions; actual state values come
        from ``data['state_vars']`` (nested: ``{scope: {name: value}}``).

        Args:
            data: Dict with 'state_vars' key from save file.
            variables: Variable definitions (name, type, initial)
                       from the save file's top-level ``variables`` key.

        Returns:
            New GameState instance with restored values.
        """
        gs = cls(variables)
        gs._state_vars = {
            s: dict(vars_) for s, vars_ in data.get("state_vars", {}).items()
        }
        return gs

    @staticmethod
    def _split_var(var: str) -> tuple[str, str]:
        """Split a dot-notation variable reference into (scope, name).

        ``Scope.Name`` → ``(Scope, Name)``; bare name → ``(GLOBAL_SCOPE, name)``.
        """
        if "." in var:
            scope, name = var.split(".", 1)
            return scope, name
        return GLOBAL_SCOPE, var

    def apply_set(self, set_op: SetOperation, choice_dict: dict[str, int]) -> SetResult:
        """Validate and apply a state change from the LLM.

        Per block-spec.md §5, all validation failures are returned as
        ``SetResult(accepted=False, reason=...)`` — never raised.  This
        implements the "silent rejection" contract: single-set failure
        does not affect other valid sets in the same round.

        Steps:
        1. Resolve ``scope.name`` reference.
        2. Verify variable exists.
        3. Verify operation is valid for the variable type.
        4. For numbers: try int conversion, verify range [0, 100].
        5. Evaluate condition if present.
        6. Apply the change.

        Args:
            set_op: The SetOperation from parsed XML.
            choice_dict: Player choice mapping (choice_id -> selected_index).

        Returns:
            SetResult with accepted flag and optional rejection reason.
            Never raises — all failures are communicated via the return
            value so the caller can accumulate rejected_changes.
        """
        scope, var_name = self._split_var(set_op.var)

        # Step 1: Verify variable exists (per block-spec.md §5:
        # unknown variable → silently reject, record in rejected_changes).
        scope_vars = self._state_vars.get(scope, {})
        scope_types = self._var_types.get(scope, {})
        if var_name not in scope_vars:
            return SetResult(
                accepted=False,
                reason=f"unknown variable: {set_op.var}",
            )

        var_type = scope_types[var_name]

        # Step 2: Verify operation is valid for type (per block-spec.md §5:
        # type mismatch → silently reject).
        if var_type == "number" and set_op.op not in self.VALID_NUMBER_OPS:
            return SetResult(
                accepted=False,
                reason=f"Invalid number operation: {set_op.op} for {set_op.var}",
            )
        if var_type == "string" and set_op.op not in self.VALID_STRING_OPS:
            return SetResult(
                accepted=False,
                reason=f"Invalid string operation: {set_op.op} for {set_op.var}",
            )

        # Step 3: Parse/try value
        if var_type == "number":
            try:
                val = int(set_op.val)
            except ValueError:
                return SetResult(
                    accepted=False,
                    reason=f"Cannot parse '{set_op.val}' as integer for {set_op.var}",
                )
        else:
            val = set_op.val

        # Step 4: Evaluate condition (per block-spec.md §5: condition
        # not met → skip without rejection).
        if set_op.condition:
            if not self.evaluate_condition(set_op.condition, choice_dict):
                return SetResult(
                    accepted=True,
                    reason="skipped: condition not met",
                )

        # Step 5: Apply
        if var_type == "number":
            return self._apply_number_op(scope, var_name, set_op.op, val)
        elif var_type == "string":
            return self._apply_string_op(scope, var_name, val)

        return SetResult(accepted=False, reason="Unknown variable type")

    def _apply_number_op(self, scope: str, var_name: str, op: str,
                         val: int) -> SetResult:
        """Apply a numeric operation with range validation."""
        current = self._state_vars[scope][var_name]

        if op == "=":
            new_val = val
        elif op == "+":
            new_val = current + val
        elif op == "-":
            new_val = current - val
        else:
            return SetResult(accepted=False, reason=f"Unknown op: {op}")

        # Per block-spec.md §5: out-of-range → clamp silently.
        clamped = False
        if new_val < self.NUMBER_MIN:
            new_val = self.NUMBER_MIN
            clamped = True
        elif new_val > self.NUMBER_MAX:
            new_val = self.NUMBER_MAX
            clamped = True

        self._state_vars[scope][var_name] = new_val
        if clamped:
            return SetResult(
                accepted=True,
                reason=f"{var_name} clamped to {new_val} (range [{self.NUMBER_MIN}, {self.NUMBER_MAX}])",
            )
        return SetResult(accepted=True)

    def _apply_string_op(self, scope: str, var_name: str, val: str) -> SetResult:
        """Apply a string assignment."""
        self._state_vars[scope][var_name] = val
        return SetResult(accepted=True)

    def evaluate_condition(
        self, condition: str | None, choice_dict: dict[str, int]
    ) -> bool:
        """Evaluate a condition expression against state and choice dict.

        Supports:
        - Comparison: ==, !=, >, >=, <, <=
        - Combinators: and, or
        - Scoped variables: ``Scope.Name`` (has dot) → ``state_vars[scope][name]``
        - Bare names: ``choice_dict`` first, then ``state_vars[GLOBAL]``

        Args:
            condition: Condition string (e.g., ``"approach==1"``, ``"耗子.信任度>=50"``).
            choice_dict: Player choice mapping.

        Returns:
            True if condition is met or no condition provided.
        """
        if not condition or not condition.strip():
            return True

        # Handle "and" / "or" combinators
        if " and " in condition:
            parts = condition.split(" and ")
            return all(
                self.evaluate_condition(p.strip(), choice_dict) for p in parts
            )
        if " or " in condition:
            parts = condition.split(" or ")
            return any(
                self.evaluate_condition(p.strip(), choice_dict) for p in parts
            )

        # Parse single condition: var_ref operator value
        # var_ref supports dot notation: Scope.Name
        match = re.match(
            r"^\s*([\w.]+)\s*(==|!=|>=|<=|>|<)\s*(.+?)\s*$", condition
        )
        if not match:
            return False

        var_ref = match.group(1)
        operator = match.group(2)
        raw_value = match.group(3).strip()

        # Resolve variable value.
        # Per block-spec.md §3:
        #  - Dot notation "Scope.Name" → state_vars[scope][name]
        #  - Bare name → choice_dict first, then state_vars[GLOBAL]
        if "." in var_ref:
            scope, name = var_ref.split(".", 1)
            scope_vars = self._state_vars.get(scope, {})
            if name in scope_vars:
                var_value = scope_vars[name]
            else:
                return False
        elif var_ref in choice_dict:
            var_value = choice_dict[var_ref]
        elif var_ref in self._state_vars.get(GLOBAL_SCOPE, {}):
            var_value = self._state_vars[GLOBAL_SCOPE][var_ref]
        else:
            return False

        # Try numeric comparison first
        try:
            numeric_value = int(raw_value)
            var_numeric = int(var_value) if not isinstance(var_value, int) else var_value
            return self._compare_numbers(var_numeric, operator, numeric_value)
        except (ValueError, TypeError):
            pass

        # Fall back to string comparison
        return self._compare_strings(str(var_value), operator, raw_value)

    @staticmethod
    def _compare_numbers(a: int, op: str, b: int) -> bool:
        """Compare two numbers with the given operator."""
        if op == "==":
            return a == b
        elif op == "!=":
            return a != b
        elif op == ">":
            return a > b
        elif op == ">=":
            return a >= b
        elif op == "<":
            return a < b
        elif op == "<=":
            return a <= b
        return False

    @staticmethod
    def _compare_strings(a: str, op: str, b: str) -> bool:
        """Compare two strings with the given operator."""
        if op in ("==", "="):
            return a == b
        elif op == "!=":
            return a != b
        elif op == ">":
            return a > b
        elif op == ">=":
            return a >= b
        elif op == "<":
            return a < b
        elif op == "<=":
            return a <= b
        return False


# ── GameLoop ──────────────────────────────────────────────────────


class GameLoop:
    """Main narrative game loop, coordinating all modules.

    Unified per-round flow (all rounds identical per exec-flow.md §4.1)::

        gl.start_game()              # Round 1: build prompt + launch API
        gen = gl.stream_round()      # Round 1 generator
        for event in gen:            # Phase 1-4: streaming parse
            if event["type"] == "options":
                gen.send(key)         # choice pause → resume
        # Phase 5: </story> → store, launch next API, yield done
        gen = gl.stream_round()      # Round 2 (API already running)
        ...
    """

    def __init__(
        self,
        story_config: dict,
        api_client: ApiClient,
        game_state: GameState | None = None,
        current_node: str | None = None,
        goal: str | None = None,
        observers: list[Callable[[RoundRecord], None]] | None = None,
        observer: Callable[[RoundRecord], None] | None = None,
        outline_nodes: list[dict] | None = None,
        characters: list[dict] | None = None,
        locations: list[dict] | None = None,
        variables: list[dict] | None = None,
    ):
        """Initialize game loop with story config and dependencies.

        Args:
            story_config: Story configuration dict (4 fields: tier, title,
                          language, premise).
            api_client: API client for LLM calls.
            game_state: Optional GameState (created from *variables* if omitted).
            current_node: Starting node ID (optional).
            goal: Starting node goal description (optional).
            observers: Optional list of observer callbacks invoked after each
                       round completes. Each receives a RoundRecord.
            observer: Deprecated. Single observer (use observers=list instead).
            outline_nodes: Structured outline from co-creation (optional).
                Each node: {id, title, goal, routes, status?, summary?}.
            characters: Character definitions from co-creation (optional).
                Each: {name, role, description, appearance}.
            locations: Location definitions from co-creation (optional).
                Each: {id, name, description}.
            variables: Variable definitions from co-creation (optional).
                Each: {name, type, initial}.

        Observer failures are silently ignored (must not break the game loop).
        """
        self.story_config = story_config
        self.api_client = api_client
        self.characters = characters or []
        self.locations = locations or []
        self.variables = variables or []

        # Normalize outline nodes and bake in initial status + empty summary
        self._outline_nodes = self._normalize_outline_nodes(outline_nodes or [])
        if self._outline_nodes:
            for node in self._outline_nodes:
                node.setdefault("status", "pending")
                node.setdefault("summary", "")
            # Set active node — first node unless current_node points elsewhere
            active_id = current_node or self._outline_nodes[0]["id"]
            for node in self._outline_nodes:
                if node.get("id") == active_id:
                    node["status"] = "active"
                    break

        # Internal modules
        self._prompter = PromptBuilder()
        self._context_mgr = ContextManager()

        # Observers — merge deprecated `observer` into list
        obs_list = list(observers) if observers else []
        if observer is not None:
            obs_list.append(observer)
        self._observers: list[Callable[[RoundRecord], None]] = obs_list

        # State
        self.game_state = game_state or GameState(self.variables)
        self.current_node = current_node or (
            self._outline_nodes[0]["id"] if self._outline_nodes else None
        )
        self.goal = goal or (
            self._outline_nodes[0].get("goal", "")
            if self._outline_nodes else None
        )
        self.last_parsed: ParsedOutput | None = None
        self._rejected_changes: list[str] = []
        self._format_error: str | None = None
        self._game_started: bool = False
        self._current_branch: str = "main"

        # Checkpoint and save accumulators
        self._temperature = getattr(api_client, "temperature", None)
        self._checkpoint_snapshots: dict[str, dict] = {}
        self.ending_flag: bool = False
        self._save_manager = None
        self._created_at: str | None = None

        # Adventure log — launched in a daemon thread during Phase 5 of the
        # final round (same pattern as _launch_api for regular pre-fetch).
        # The UI calls get_adventure_log() to retrieve the result.
        self._adv_thread: threading.Thread | None = None
        self._adv_result: str | None = None
        self._adv_error: str | None = None
        self._adv_retry_prompt: str | None = None

        # ── Graph-mode pipeline (§7.6) ──────────────────────────────
        # Set by mount_graph_pipeline().  None in text mode.
        # stream_round() reads these to decide whether to create TaskGen
        # and inject task_queue + roster into EventDispatcher.
        self._game_mode: str = "text"  # written to every save file
        self._roster: GameAssetRoster | None = None
        self._roster_path: str | None = None  # §7.8c: _asset_roster.json path
        self._task_pool: TaskPool | None = None
        self._last_scene: str | None = None  # §7.7: persisted in save, emitted on load
        self._match_processor: Callable | None = None
        self._generate_processor: Callable | None = None

        # Pending API state — every round's Phase 5 launches the *next*
        # round's API call in a daemon thread and stores the result queue
        # here.  stream_round() drains this queue.  All rounds are
        # identical — Round 1 is no exception (its Phase 5 also launches
        # the Round 2 API call).
        self._pending_queue: queue.Queue | None = None
        # While stream_round() is draining the pending queue it keeps a
        # reference here so cancel() can inject a sentinel and unblock
        # the consumer thread immediately.
        self._active_queue: queue.Queue | None = None
        self._pending_user_content: str = ""
        self._pending_messages: list[dict] = []

        # Retry state — when stream_round() encounters a severe error
        # (API timeout / network failure), it stores the original messages
        # here so the UI can call retry() after user confirmation.
        # Cleared on successful round completion.
        self._retry_messages: list[dict] | None = None
        self._retry_user_content: str = ""

    # ── Properties ─────────────────────────────────────────────────

    @property
    def round_count(self) -> int:
        """Current round number (0 before first ``stream_round()``)."""
        return self._context_mgr.round_count

    @property
    def outline_text(self) -> str:
        """Formatted outline derived from _outline_nodes in real time.

        Renders node ID, status, title, summary (if completed), and
        branch routes. Goal is omitted — it appears separately in
        the prompt's Active Node section.
        """
        node_ids = {n.get("id") or n.get("node_id", "") for n in self._outline_nodes}
        lines = []
        for node in self._outline_nodes:
            nid = node.get("id") or node.get("node_id", "")
            status = node.get("status", "pending")
            lines.append(f"{nid} [{status}] — {node.get('title', '')}")
            if status == "completed" and node.get("summary"):
                lines.append(f"  ↳ {node['summary']}")
            routes = node.get("routes", [])
            if routes:
                for j, route in enumerate(routes):
                    is_last = (j == len(routes) - 1)
                    prefix = "  └→" if is_last else "  ├→"
                    target = route.get("target", "") if isinstance(route, dict) else route
                    if target in node_ids:
                        lines.append(f"{prefix} {target} [pending]")
        return "\n".join(lines)

    @property
    def checkpoint_history(self) -> list[dict]:
        """Checkpoint history derived from _outline_nodes (backward compat).

        Each entry: {node, title, goal, summary}.
        """
        return [
            {
                "node": n.get("id") or n.get("node_id", ""),
                "title": n.get("title", ""),
                "goal": n.get("goal", ""),
                "summary": n.get("summary", ""),
            }
            for n in self._outline_nodes
            if n.get("status") == "completed" and n.get("summary")
        ]

    @property
    def outline_nodes(self) -> list[dict]:
        """Current outline with status from node data (backward compat).

        Returns a copy for external consumers (UI, tests).
        """
        result = []
        for node in self._outline_nodes:
            nid = node.get("id") or node.get("node_id", "")
            result.append({
                "id": nid,
                "title": node.get("title", ""),
                "goal": node.get("goal", ""),
                "status": node.get("status", "pending"),
                "summary": node.get("summary", ""),
                "branches": [
                    r.get("target", r) if isinstance(r, dict) else r
                    for r in node.get("routes", node.get("branches", []))
                ],
            })
        return result

    @property
    def completed_nodes(self) -> list[str]:
        """List of completed node IDs (derived from node status)."""
        return [
            n.get("id") or n.get("node_id", "")
            for n in self._outline_nodes
            if n.get("status") == "completed"
        ]

    @property
    def current_branch(self) -> str:
        """Active branch name from the player's last choice.

        Defaults to ``"main"`` per block-spec.md §3.  UI layers use
        this to select which post-bridge ``<branch name="...">``
        content to display.
        """
        return self._current_branch

    # ── Game Start ──────────────────────────────────────────────────
    # Called once by the UI after construction.  Builds the Round 1
    # prompt and launches the background API call so that the very first
    # stream_round() can consume it just like any other round.

    def start_game(self) -> None:
        """Build Round 1 prompt and launch the background API call.

        Must be called once before the first ``stream_round()``.
        Each ``GameLoop`` instance supports exactly one game session.

        Raises:
            RuntimeError: If already started.
        """
        if self._game_started:
            raise RuntimeError("Round 1 already started")
        self._game_started = True

        if self._roster is not None:
            sys_prompt = self._prompter.build_graph_system_prompt(
                story_config=self.story_config,
                characters=self.characters,
                locations=self.locations,
            )
            r1_user = self._prompter.build_round_n_graph(
                outline_text=self.outline_text,
                current_node=self.current_node or "",
                goal=self.goal or "",
                state_vars=self.game_state.state_vars,
                variables=self.variables,
                bridge_text="(Story begins)",
                current_scene=self._last_scene,
            )
        else:
            sys_prompt = self._prompter.build_text_system_prompt(
                story_config=self.story_config,
                characters=self.characters,
                locations=self.locations,
            )
            r1_user = self._prompter.build_round_n(
                outline_text=self.outline_text,
                current_node=self.current_node or "",
                goal=self.goal or "",
                state_vars=self.game_state.state_vars,
                variables=self.variables,
                bridge_text="(Story begins)",
            )

        self._context_mgr.set_system_prompt(sys_prompt)

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": r1_user},
        ]
        self._launch_api(messages, r1_user)

    # ── stream_round (unified) ─────────────────────────────────────

    def stream_round(self) -> Iterator[dict]:
        """Unified per-round generator.  All rounds (1…N) use the same flow.

        Per exec-flow.md §4.1, every round follows the identical 6-phase
        pipeline.  Phase 5 of round *k* launches the background API call
        for round *k+1*; ``stream_round()`` for round *k+1* drains the
        queue that was stored then.

        **Choice pause** — when the parser encounters ``</choice>`` the
        generator yields an ``options`` event and suspends.  The UI must
        call ``gen.send(key)`` with the player's selected key (1-indexed
        string).  The generator resumes with ``current_branch`` and
        ``choice_dict`` populated.

        Yields:
            ``{"type": "story_begin"}``
            ``{"type": "story_end"}``
            ``{"type": "token", "text": str}``
            ``{"type": "segment", "text": str, ...}``
            ``{"type": "bridge"}``
            ``{"type": "options", "choices": [dict]}``
            ``{"type": "state", "vars": dict, "changes": [dict]}``
            ``{"type": "save", "filename": str, "checkpoint_node": str}``
            ``{"type": "error", "message": str}``
            ``{"type": "ending", ...}``
            ``{"type": "done", "node": str, "state": dict}``
        """
        # ── Guard: ending already triggered ─────────────────────────
        if self.ending_flag:
            yield {
                "type": "done",
                "node": "end",
                "state": self.game_state.state_vars,
            }
            return

        # ── Guard: API must be launched ─────────────────────────────
        if self._pending_queue is None:
            raise RuntimeError(
                "start_game() must be called before stream_round()"
            )

        # ── Consume pending API state (stored by last round's Phase 5
        #    or by start_game()) ──────────────────────────────────────
        result_queue = self._pending_queue
        user_content = self._pending_user_content
        messages_sent = self._pending_messages
        self._pending_queue = None
        self._pending_user_content = ""
        self._pending_messages = []
        # Expose the active queue so cancel() can inject a sentinel
        # and unblock this thread when it's stuck waiting for the
        # next API chunk (up to STREAM_STALL_TIMEOUT_SEC = 180 s).
        self._active_queue = result_queue

        # ── Per-round state (fresh each round per block-spec.md §3) ─
        # State variables are now managed by StateManager.
        self._format_error = None  # reset each round — errors are fed back
        # via build_round_n() in Phase 5; must not persist into later rounds.

        # ── Phase 1-4: Streaming parse ──────────────────────────────
        # Per exec-flow.md §4.4: token chunks → LineBuffer complete
        # lines → StreamParser events → StateManager → EventDispatcher.
        # Per design.md §3.3: all in Thread 2 (Event Pipe) via
        # generator yield.

        lb = LineBuffer()

        # ── §7.6: graph mode assembles TaskGen + injects into parser & dispatcher.
        # Text mode: roster is None → task_gen=None, task_queue=None → Phase 1 path.
        if self._roster is not None:
            from storyloom.tasks import TaskGenerator
            task_queue: deque[object] | None = deque()
            task_gen = TaskGenerator(task_queue, self._roster,
                                     match_processor=self._match_processor,
                                     generate_processor=self._generate_processor,
                                     task_pool=self._task_pool,
                                     roster_path=self._roster_path)
        else:
            task_queue = None
            task_gen = None
        parser = StreamParser(task_gen=task_gen)

        state_mgr = StateManager(game_state=self.game_state)
        state_mgr.set_outline(self._outline_nodes)
        state_mgr.set_save_callback(
            lambda node, summary: (
                self._save_manager.save(self.to_save_dict(), node)
                if self._save_manager else None
            )
        )
        state_mgr.init_progress(
            current_node=self.current_node,
            goal=self.goal,
        )
        dispatcher = EventDispatcher(task_queue, self._roster)

        # §7.7: restore scene background on first round after load.
        # Only fires when _last_scene is set (loaded save) and this is
        # the first round of the session (round_count == 0).  New games
        # have _last_scene=None → no-op.
        if self._last_scene and self._roster is not None and self._context_mgr.round_count == 0:
            from storyloom.assets import AssetType
            item = self._roster.lookup(AssetType.BACKGROUND, self._last_scene)
            if item is not None and item.target is not None:
                yield {
                    "type": "scene",
                    "val": self._last_scene,
                    "assets": {"background_img": item.target},
                }

        collected: list[str] = []
        ttft: float | None = None
        tokens: dict | None = None

        while True:
            try:
                chunk = result_queue.get(timeout=STREAM_STALL_TIMEOUT_SEC)
            except queue.Empty:
                # ── Severe error: save messages for retry ─────────
                self._retry_messages = messages_sent
                self._retry_user_content = user_content
                self._active_queue = None
                logger.error(
                    "stream_round: API timeout after %ds "
                    "round=%d node=%s model=%s",
                    STREAM_STALL_TIMEOUT_SEC,
                    self._context_mgr.round_count,
                    self.current_node,
                    self.api_client.model,
                )
                yield {
                    "type": "error",
                    "message": (
                        f"API timeout after {STREAM_STALL_TIMEOUT_SEC}s"
                    ),
                }
                return

            # ── Cancellation sentinel injected by cancel() ─────────
            if chunk.get("__cancel__"):
                self._active_queue = None
                return

            if chunk.get("__api_error__"):
                # ── Severe error: save messages for retry ─────────
                self._retry_messages = messages_sent
                self._retry_user_content = user_content
                self._active_queue = None
                logger.error(
                    "stream_round: API error round=%d node=%s "
                    "model=%s: %s",
                    self._context_mgr.round_count,
                    self.current_node,
                    self.api_client.model,
                    chunk["__api_error__"],
                )
                yield {
                    "type": "error",
                    "message": f"API error: {chunk['__api_error__']}",
                }
                return

            if chunk.get("done"):
                tokens = chunk.get("usage")
                break  # end of API stream → Phase 5

            if chunk.get("ttft") is not None:
                ttft = chunk["ttft"]

            delta = chunk["delta"]
            collected.append(delta)
            yield {"type": "token", "text": delta}

            for line in lb.feed(delta):
                for event in parser.feed_line(line):
                    # ── All Events flow through StateManager ───────
                    # Per design.md §4.1: every Phase 1 event type
                    # passes through StateManager.
                    for processed in state_mgr.process(event):
                        ui_event = dispatcher.consume_event(processed)
                        if ui_event:
                            yield ui_event

                    # ── CHOICE_END: pause for player input ─────────
                    if state_mgr.needs_input:
                        key = yield dispatcher.dispatch_choice(
                            state_mgr.choice_data
                        )
                        for evt in state_mgr.apply_choice(key):
                            ui_event = dispatcher.dispatch(evt)
                            if ui_event:
                                yield ui_event

                    # ── CHECKPOINT_END / self-closing CHECKPOINT ───
                    # Per design.md §3.2: checkpoint processing
                    # happens in StateManager.  Trigger when the
                    # parser exits a checkpoint block (CHECKPOINT_END
                    # event) or when a self-closing <checkpoint/>
                    # appears (parser never entered _in_checkpoint).
                    if event.type == EventType.CHECKPOINT_END:
                        for cp_evt in state_mgr.process_checkpoint():
                            saved = cp_evt.payload.get("save_filename")
                            cp_node = cp_evt.payload.get("checkpoint_node")
                            if saved:
                                yield dispatcher.dispatch_save(
                                    saved, cp_node
                                )
                    elif (event.type == EventType.CHECKPOINT
                          and not parser.in_checkpoint):
                        # Self-closing <checkpoint/> — process now
                        for cp_evt in state_mgr.process_checkpoint():
                            saved = cp_evt.payload.get("save_filename")
                            cp_node = cp_evt.payload.get("checkpoint_node")
                            if saved:
                                yield dispatcher.dispatch_save(
                                    saved, cp_node
                                )

        # ── Flush any remaining partial line ────────────────────────
        # Route through the full pipeline so StateManager accumulates
        # segments / checkpoint data.  Don't yield UI events — the
        # stream has ended and a partial line is truncated garbage.
        remaining = lb.flush()
        if remaining:
            for event in parser.feed_line(remaining):
                list(state_mgr.process(event))

        # ═══════════════════════════════════════════════════════════
        # Phase 5: </story> — pack, store, next-round launch
        # ═══════════════════════════════════════════════════════════

        response = "".join(collected)
        parsed = state_mgr.get_result(
            bridge_found=parser.bridge_seen,
            parser_format_errors=list(parser.format_errors),
        )
        no_choices = not parsed.choices

        # ── Format errors ───────────────────────────────────────────
        # StateManager.get_result() already merged parser format errors
        # (post-bridge violations, unrecognized elements) into its own
        # _format_errors.  NNN| line-number mismatches were routed to
        # numbering_issues instead.
        self._format_error = (
            "; ".join(state_mgr.format_errors)
            if state_mgr.format_errors else None
        )

        # ── Sync state from StateManager → GameLoop ─────────────────
        current_branch = state_mgr.current_branch
        self._current_branch = current_branch
        self._rejected_changes = state_mgr.rejected_changes
        self.current_node = state_mgr.current_node or self.current_node
        self.goal = state_mgr.goal or self.goal
        self.ending_flag = state_mgr.ending_flag
        self._checkpoint_snapshots = state_mgr.checkpoint_snapshots
        self._last_scene = state_mgr.current_scene  # §7.7: persist for next save

        # ── Store round in context manager ──────────────────────────
        bridge_text = state_mgr.get_bridge_text(current_branch)
        self._context_mgr.add_round(
            user_content,
            response,
            bridge_text=bridge_text,
            selected_branch=(
                current_branch if current_branch != "main" else None
            ),
        )

        self.last_parsed = parsed

        # ── Ending: launch adventure log (concurrent per §5.2) ──────
        if self.ending_flag:
            def _fetch_adv() -> None:
                try:
                    self._adv_result = self.run_adventure_log()
                except Exception as exc:
                    self._adv_error = str(exc)

            self._adv_thread = threading.Thread(target=_fetch_adv, daemon=True)
            self._adv_thread.start()

            # ── Ending reached — clear retry state ────────────────
            self._retry_messages = None
            self._retry_user_content = ""
            self._active_queue = None

            yield {
                "type": "ending",
                "adventure_log": None,
                "final_state": self.game_state.state_vars,
                "summary": parsed.checkpoint_summary,
            }

            self._notify(RoundRecord(
                round_number=self._context_mgr.round_count,
                messages_sent=messages_sent,
                raw_response=response,
                parsed=parsed,
                ttft=ttft,
                tokens=tokens,
                timestamp=time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
                ),
                node="end",
                selected_branch=(
                    current_branch if current_branch != "main" else None
                ),
            ))

            yield {
                "type": "done",
                "node": "end",
                "state": self.game_state.state_vars,
            }
            return

        # ── Build next-round prompt → launch background API ─────────
        bridge_text_for_prompt = self._context_mgr.get_last_bridge_text()

        if self._roster is not None:
            rn_context = self._prompter.build_round_n_graph(
                outline_text=self.outline_text,
                current_node=self.current_node or "",
                goal=self.goal or "",
                state_vars=self.game_state.state_vars,
                variables=self.variables,
                bridge_text=bridge_text_for_prompt,
                current_scene=state_mgr.current_scene,
                rejected_changes=(
                    self._rejected_changes if self._rejected_changes else None
                ),
                format_error=self._format_error,
                no_choices_last_round=no_choices,
            )
        else:
            rn_context = self._prompter.build_round_n(
                outline_text=self.outline_text,
                current_node=self.current_node or "",
                goal=self.goal or "",
                state_vars=self.game_state.state_vars,
                variables=self.variables,
                bridge_text=bridge_text_for_prompt,
                rejected_changes=(
                    self._rejected_changes if self._rejected_changes else None
                ),
                format_error=self._format_error,
                no_choices_last_round=no_choices,
            )

        messages = self._context_mgr.get_messages()
        messages.append({"role": "user", "content": rn_context})

        self._launch_api(messages, rn_context)

        # ── Round succeeded — clear retry state ────────────────────
        self._retry_messages = None
        self._retry_user_content = ""

        # ── Notify observer ─────────────────────────────────────────
        self._notify(RoundRecord(
            round_number=self._context_mgr.round_count,
            messages_sent=messages_sent,
            raw_response=response,
            parsed=parsed,
            ttft=ttft,
            tokens=tokens,
            timestamp=time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            ),
            node=self.current_node,
            selected_branch=(
                current_branch if current_branch != "main" else None
            ),
        ))

        self._active_queue = None
        yield {
            "type": "done",
            "node": self.current_node,
            "state": self.game_state.state_vars,
        }

    # ── Background API ──────────────────────────────────────────────

    def _launch_api(self, messages: list[dict], user_content: str) -> None:
        """Start a background API call and store the result queue.

        Called by ``start_game()`` (Round 1) and by ``stream_round()``
        Phase 5 (every round).  The daemon thread streams API chunks
        into ``queue.Queue``; the next ``stream_round()`` call drains
        it.

        Args:
            messages: Full messages array to send.
            user_content: The user message content (stored for
                          ``add_round`` in the next round).
        """
        import os as _os

        from storyloom.io.thinking import get_thinking_params

        result_queue: queue.Queue = queue.Queue()
        extra_params = get_thinking_params(
            self.api_client.model, "enabled",
        )

        def _fetch() -> None:
            try:
                for chunk in self.api_client.stream_chat_iter(
                    messages, extra_params=extra_params,
                ):
                    result_queue.put(chunk)
            except Exception as exc:
                result_queue.put({"__api_error__": str(exc)})

        thread = threading.Thread(target=_fetch, daemon=True)
        thread.start()

        self._pending_queue = result_queue
        self._pending_user_content = user_content
        self._pending_messages = list(messages)

    def retry(self) -> None:
        """Re-launch the last failed round with the same messages.

        Call after receiving an ``{"type": "error", ...}`` event and
        the user has chosen to retry.  Must be followed by another
        ``stream_round()`` call to consume the new result queue.

        Raises:
            RuntimeError: If there is no failed round to retry
                          (i.e. the last round completed successfully).
        """
        if self._retry_messages is None:
            raise RuntimeError(
                "No failed round to retry — the last round completed "
                "successfully or retry() was already called."
            )
        self._launch_api(self._retry_messages, self._retry_user_content)

    def cancel(self) -> None:
        """Inject a cancellation sentinel into the active API queue.

        When the background daemon thread is blocked inside
        ``stream_round()`` waiting for the next API chunk, a stop
        signal alone cannot reach it — the check only happens at
        generator yield points.  This method puts a ``__cancel__``
        sentinel into both the active drain queue and the pending
        queue, covering the narrow window where ``_launch_api`` has
        set ``_pending_queue`` but ``stream_round()`` has not yet
        captured it into ``_active_queue``.

        Safe to call from any thread.  Idempotent — if no queue is
        active the call is a no-op.
        """
        if self._active_queue is not None:
            self._active_queue.put({"__cancel__": True})
        if self._pending_queue is not None:
            self._pending_queue.put({"__cancel__": True})

    # ── Save / Restore ─────────────────────────────────────────────

    def to_save_dict(self) -> dict:
        """Produce complete save dict per data-model.md §3.1 format."""
        # Convert outline nodes to save format (status + summary baked in)
        outline_for_save = []
        for node in self._outline_nodes:
            nid = node.get("id", "")
            outline_for_save.append({
                "node_id": nid,
                "title": node.get("title", ""),
                "goal": node.get("goal", ""),
                "status": node.get("status", "pending"),
                "summary": node.get("summary", ""),
                "branches": [
                    {"condition": r.get("condition"), "target": r.get("target", "")}
                    for r in node.get("routes", [])
                ],
            })

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        title = self.story_config.get("title", "untitled")

        # Preserve original created_at; set on first save only.
        if self._created_at is None:
            self._created_at = now

        # story_config: only persist the 4 canonical fields (plan D4/D9).
        sc = self.story_config
        canonical_sc = {
            "tier": sc.get("tier", ""),
            "title": sc.get("title", ""),
            "language": sc.get("language", ""),
            "premise": sc.get("premise", ""),
        }

        return {
            "version": SAVE_VERSION,
            "metadata": {
                "title": title,
                "created_at": self._created_at,
                "updated_at": now,
            },
            "config": {
                "temperature": getattr(self, "_temperature", None),
                "mode": self._game_mode,
            },
            "story_config": canonical_sc,
            "characters": copy.deepcopy(self.characters),
            "locations": copy.deepcopy(self.locations),
            "variables": copy.deepcopy(self.variables),
            "state_vars": self.game_state.state_vars,
            "outline": outline_for_save,
            "progress": {
                "current_node": self.current_node or "",
                "current_scene": self._last_scene or "",
                "checkpoint_snapshots": copy.deepcopy(self._checkpoint_snapshots),
            },
        }

    @classmethod
    def from_save_dict(
        cls,
        data: dict,
        api_client: "ApiClient",
    ) -> "GameLoop":
        """Restore GameLoop from save data.

        Outline nodes carry status and summary directly — no separate
        checkpoint_history or outline_text reconstruction needed.
        Supports old save format where nodes may lack summary field.
        """
        story_config = data["story_config"]
        characters = data.get("characters", [])
        locations = data.get("locations", [])
        variables = data.get("variables", [])
        state_vars_data = {"state_vars": data["state_vars"]}
        outline_nodes = data["outline"]

        # Ensure every node has status + summary (old saves may lack them)
        for node in outline_nodes:
            node.setdefault("status", "pending")
            node.setdefault("summary", "")

        game_state = GameState.from_dict(state_vars_data, variables)
        progress = data.get("progress", {})
        current_node = progress.get("current_node", "")

        # Find goal for current node
        goal = ""
        for node in outline_nodes:
            nid = node.get("node_id", node.get("id", ""))
            if nid == current_node:
                goal = node.get("goal", "")
                break

        gl = cls(
            story_config=story_config,
            api_client=api_client,
            game_state=game_state,
            current_node=current_node or None,
            goal=goal or None,
            outline_nodes=outline_nodes,
            characters=characters,
            locations=locations,
            variables=variables,
        )

        gl._checkpoint_snapshots = dict(progress.get("checkpoint_snapshots", {}))
        gl._last_scene = progress.get("current_scene") or None  # §7.7

        # Restore config — temperature, mode (§7.6)
        config = data.get("config", {})
        if "temperature" in config:
            gl._temperature = config["temperature"]
        gl._game_mode = config.get("mode", "text")  # absent in pre-§7.6 saves

        # Restore created_at (preserve original creation timestamp)
        metadata = data.get("metadata", {})
        if metadata.get("created_at"):
            gl._created_at = metadata["created_at"]

        return gl

    def set_save_manager(self, save_manager) -> None:
        """Configure auto-save on checkpoint."""
        self._save_manager = save_manager

    # ── Graph-mode pipeline (§7.6) ───────────────────────────────────

    def mount_graph_pipeline(self, game_id: str, saves_root: str) -> None:
        """Create and store graph-mode pipeline dependencies.

        Called by GameSession after construction but before
        ``stream_round()``.  Creates the per-game roster (loaded from
        ``_asset_roster.json``, or empty if no file), the Thread 4
        task pool, and a stub process factory (§7.8 replaces with real
        LLM matching / image generation).

        ``stream_round()`` reads ``self._roster`` — when set, it creates
        a TaskGenerator and injects it plus the shared task queue into
        the EventDispatcher.

        Idempotent — safe to call multiple times.

        Media directories are derived from *saves_root* (parent dir)
        so the asset pipeline works regardless of CWD.
        """
        if self._roster is not None:
            return  # already mounted

        from storyloom.assets import AssetLibrary, AssetType, GameAssetRoster
        from storyloom.config import DEFAULT_SYSTEM_MEDIA_DIR
        from storyloom.tasks import TaskPool

        # Derive media paths from saves_root so the asset pipeline works
        # regardless of CWD (e.g. double-click launch on Linux / macOS).
        _app_root = os.path.normpath(os.path.join(saves_root, ".."))
        _media_dir = os.path.join(_app_root, DEFAULT_MEDIA_DIR)
        _sys_media_dir = os.path.join(_app_root, DEFAULT_SYSTEM_MEDIA_DIR)

        self._game_mode = "graph"
        library = AssetLibrary.load(_media_dir)
        if self._save_manager is not None:
            self._roster_path = self._save_manager.roster_path
        else:
            self._roster_path = os.path.join(saves_root, game_id, "_asset_roster.json")
        self._roster = GameAssetRoster.load(self._roster_path, library, game_id)
        self._task_pool = TaskPool()

        # ── System assets (§7.8 framework) ──────────────────────────
        if os.path.isdir(_sys_media_dir):
            try:
                library.import_system_assets(_sys_media_dir)
                library.save()  # persist first-time import (was in stub block, lost in 456c114)
            except Exception as exc:
                # system_media/ exists but is broken — skip, don't block.
                logger.warning("Failed to import system assets: %s", exc)

        from storyloom.io._types import RemoveBgPolicy
        from storyloom.io.img_api_client import ImgApiClient
        from storyloom.tasks import GenerateProcessor, MatchProcessor

        self._match_processor = MatchProcessor(self.api_client)

        from storyloom.user_config import UserConfig
        raw_cfg = getattr(self.api_client, '_cfg', None)
        if raw_cfg is None or not isinstance(raw_cfg, UserConfig):
            raw_cfg = UserConfig()
        portrait_policy = RemoveBgPolicy(raw_cfg.portrait_remove_bg)
        img_enabled = raw_cfg.img_generation_enabled

        self._generate_processor = GenerateProcessor(
            api_client=self.api_client,
            img_client_portrait=ImgApiClient(raw_cfg, remove_bg=portrait_policy),
            img_client_background=ImgApiClient(raw_cfg, remove_bg=RemoveBgPolicy.NEVER),
            library=library,
            roster_path=self._roster_path,
            img_generation_enabled=img_enabled,
        )

    # ── Observer ──────────────────────────────────────────────────
    def _notify(self, record: RoundRecord) -> None:
        """Notify all observers of a completed round.

        Observer failures are silently ignored — they must not break
        the game loop.
        """
        for obs in self._observers:
            try:
                obs(record)
            except Exception:
                pass

    # ── Options ───────────────────────────────────────────────────

    def get_available_options(self) -> list[dict]:
        """Return available options from last parsed output.

        Returns:
            List of option dicts with 'branch' key.
            Empty list if no choice was presented.
        """
        if not self.last_parsed or not self.last_parsed.choice_id:
            return []
        return [
            {"branch": branch, "index": i + 1}
            for i, branch in enumerate(self.last_parsed.opt_branches)
        ]

    # ── Outline ───────────────────────────────────────────────────

    @staticmethod
    def _normalize_outline_nodes(nodes: list[dict]) -> list[dict]:
        """Normalize outline nodes to a single consistent internal format.

        The internal ``_outline_nodes`` can arrive in two shapes depending
        on creation path:

        * **Fresh** (``CoCreateFlow.generate()`` JSON outline):
          ``{id, title, goal, routes: [{condition, target}]}``
        * **Loaded** (``from_save_dict`` → save-file ``outline``):
          ``{node_id, title, goal, status, branches: [str|dict]}``
          (old saves: list of target strings; new saves: list of
          ``{condition, target}`` dicts).

        This method normalises both into the fresh format so that every
        downstream access site (checkpoint validation, ``to_save_dict``,
        ``_next_outline_node``, ``_accumulate_checkpoint``) works with a
        single key layout.

        Returns a **new** list — does not mutate the input.
        """
        normalized = []
        for node in nodes:
            nid = node.get("id") or node.get("node_id", "")
            routes = node.get("routes")
            if routes is None:
                # Loaded format: branches is a list of target strings
                # (old saves) or {condition, target} dicts (new saves).
                branches = node.get("branches", [])
                routes = []
                for b in branches:
                    if isinstance(b, dict):
                        routes.append({
                            "condition": b.get("condition"),
                            "target": b.get("target", ""),
                        })
                    elif b:
                        routes.append({"condition": None, "target": b})
            normalized.append({
                "id": nid,
                "title": node.get("title", ""),
                "goal": node.get("goal", ""),
                "status": node.get("status", "pending"),
                "summary": node.get("summary", ""),
                "routes": routes,
            })
        return normalized

    # ── Routes ────────────────────────────────────────────────────

    def evaluate_routes(self, choice_dict: dict[str, int]) -> str | None:
        """Evaluate route conditions from last parsed output.

        Public convenience wrapper around _evaluate_routes.

        Args:
            choice_dict: Player choice mapping.

        Returns:
            Target node ID if a route matches, None otherwise.
        """
        return self._evaluate_routes(choice_dict)

    def _evaluate_routes(
        self,
        choice_dict: dict[str, int],
        routes: list | None = None,
    ) -> str | None:
        """Evaluate route conditions.

        Per data-model.md §2 step 4:
        - First matching condition wins.
        - All conditions fail → fall back to first route's target.
        - No routes → advance to next node in outline sequence.

        Args:
            choice_dict: Player choice mapping.
            routes: Route list to evaluate.  When ``None``, reads from
                    ``self.last_parsed.routes`` (legacy path).
        """
        if routes is None:
            if not self.last_parsed:
                return None
            routes = self.last_parsed.routes

        for route in routes:
            if route.condition is None:
                return route.target
            if self.game_state.evaluate_condition(
                route.condition, choice_dict
            ):
                return route.target

        # Fallback 1: conditions exist but none matched → first route.
        if routes:
            return routes[0].target

        # Fallback 2: no routes → next node in outline sequence.
        return self._next_outline_node()

    def _next_outline_node(self) -> str | None:
        """Return the next node in outline sequence after current_node.

        Returns None if current_node is the last node or not found.
        """
        if not self._outline_nodes or not self.current_node:
            return None
        for i, node in enumerate(self._outline_nodes):
            nid = node.get("id", "")
            if nid == self.current_node and i + 1 < len(self._outline_nodes):
                return self._outline_nodes[i + 1].get("id")
        return None

    # ── Adventure Log ─────────────────────────────────────────────

    def run_adventure_log(self) -> str:
        """Generate adventure log / ending summary.

        Uses non-streaming chat with structured prompt per prompt-design.md §5.2.

        Saves the prompt to ``_adv_retry_prompt`` and clears ``_adv_error``
        so ``retry_adventure_log()`` can re-launch with the same prompt
        after a failure.

        Returns:
            Adventure log markdown text.
        """
        prompt = PromptBuilder.build_adventure_log_prompt(
            story_config=self.story_config,
            state_vars=self.game_state.state_vars,
            outline_text=self.outline_text,
            variables=self.variables,
            characters=self.characters,
            locations=self.locations,
        )
        self._adv_retry_prompt = prompt
        self._adv_error = None
        # Per exec-flow.md §5.4: independent LLM call — not part of the
        # narrative loop.  Send only the adventure-log prompt, not the
        # full conversation context (~50K tokens).
        return self.api_client.chat([{"role": "user", "content": prompt}])

    def get_adventure_log(self, timeout: float = 30.0) -> str | None:
        """Wait for the background adventure log thread and return the text.

        Called by the UI after receiving the ``ending`` event.
        The adventure log is fetched in a daemon thread (same pattern as
        bridge pre-fetch) so the generator is never blocked.

        Args:
            timeout: Maximum seconds to wait for the API response.

        Returns:
            Adventure log markdown text, or ``None`` on timeout / error.
        """
        if self._adv_thread is None:
            return None
        self._adv_thread.join(timeout=timeout)
        return self._adv_result

    def retry_adventure_log(self) -> None:
        """Re-launch the adventure log daemon thread with the same prompt.

        Call after ``adventure_log_error`` is set and the user has
        chosen to retry.  Must be followed by another
        ``get_adventure_log()`` call to retrieve the new result.

        Raises:
            RuntimeError: If there is no prompt to retry with (i.e.
                          ``run_adventure_log()`` was never called, or
                          the last call succeeded without saving a prompt).
        """
        if self._adv_retry_prompt is None:
            raise RuntimeError(
                "No failed adventure log to retry — run_adventure_log() "
                "was never called or succeeded without error."
            )
        self._adv_error = None
        self._adv_result = None

        def _fetch() -> None:
            try:
                self._adv_result = self.api_client.chat(
                    [{"role": "user", "content": self._adv_retry_prompt}]
                )
            except Exception as exc:
                self._adv_error = str(exc)

        self._adv_thread = threading.Thread(target=_fetch, daemon=True)
        self._adv_thread.start()

    @property
    def adventure_log_error(self) -> str | None:
        """Error message if adventure log generation failed, ``None`` otherwise.

        Check this after ``get_adventure_log()`` returns ``None`` to
        distinguish "API error" (this property is set) from "still
        waiting / timeout" (this property is ``None``).
        """
        return self._adv_error

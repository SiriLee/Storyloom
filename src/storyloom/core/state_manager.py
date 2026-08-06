"""State manager — processes Events through state logic.

Per design.md §3.2:
  SET / CHECKPOINT / BRANCH / BRIDGE handling, CHOICE_END blocking.
  SCENE events update ``current_scene`` state (Phase 2).

``process()`` is a generator — one Event in, zero or more Events out.
Never blocks directly; at CHOICE_END it sets ``needs_input = True`` and
lets the caller handle the generator pause.
"""

from collections.abc import Iterator

from storyloom.config import BRANCH_VAR_NAME
from storyloom.parser.stream_parser import Event, EventType
from storyloom.parser.stream_parser import (
    ParsedOutput,
    RouteTarget,
    Segment,
    SetOperation,
)


class StateManager:
    """Processes Events through state logic and accumulates business data.

    Per design.md §3.2 — the central state processor in the Event Pipe.
    Receives Events from StreamParser, applies state changes, filters by
    branch, accumulates structured data, and yields processed Events to
    EventDispatcher.

    Injection points (needed for CHECKPOINT processing):
      - ``set_outline()`` — outline nodes for validation and advancement.
      - ``set_save_callback()`` — auto-save on checkpoint (callable that
        receives ``(cp_node, cp_summary)`` and returns filename or None).
    """

    def __init__(self, game_state: "GameState"):  # noqa: F821
        self._game_state = game_state

        # ── Per-round mutable state ────────────────────────────────
        self._current_branch: str = "main"
        self._choice_dict: dict[str, int] = {}
        self._current_scene: str | None = None  # Phase 2 (§5.2, §7.5)

        # ── Accumulators (business data, moved from old parser) ────
        self._segments: list[Segment] = []
        self._sets: list[SetOperation] = []
        self._routes: list[RouteTarget] = []
        self._bridge_text_items: list[tuple[str, str | None]] = []
        self._pre_branches: list[str] = []
        self._post_branches: list[str] = []
        self._rejected_changes: list[str] = []
        self._format_errors: list[str] = []

        # ── Checkpoint state ───────────────────────────────────────
        self._pending_cp_node: str | None = None
        self._pending_cp_summary: str | None = None

        # ── Choice state ───────────────────────────────────────────
        self._last_choice_data: dict | None = None
        self.needs_input: bool = False

        # ── Injected dependencies ──────────────────────────────────
        self._outline_nodes: list[dict] = []
        self._save_callback = None  # Callable[[str, str], str | None]

        # ── Game progress (CHECKPOINT side effects) ────────────────
        self._current_node: str | None = None
        self._goal: str | None = None
        self._node_goals: dict[str, str] = {}
        self._checkpoint_snapshots: dict[str, dict] = {}
        self.ending_flag: bool = False

    # ── Injection ──────────────────────────────────────────────────

    def set_outline(self, nodes: list[dict]) -> None:
        """Inject outline nodes for checkpoint validation and advancement."""
        self._outline_nodes = nodes
        self._node_goals = {
            n.get("id", n.get("node_id", "")): n.get("goal", "")
            for n in nodes
            if n.get("goal")
        }

    def set_save_callback(self, callback) -> None:
        """Inject save callback for auto-save on checkpoint.

        The callback receives ``(cp_node, cp_summary)`` and must return
        the saved filename on success, or ``None`` on failure.
        StateManager does not own save-format knowledge — the callback
        is provided by GameLoop, which constructs the full save dict.
        """
        self._save_callback = callback

    def init_progress(self, current_node: str | None, goal: str | None) -> None:
        """Initialize game progress state (called at game start / load)."""
        self._current_node = current_node
        self._goal = goal

    # ── Event processing (generator) ───────────────────────────────

    def process(self, event: Event) -> Iterator[Event]:
        """Process one Event.  Yields zero or more processed Events.

        Per design.md §3.2-§3.3: streaming Event processing in the
        Event Pipe.  One Event enters StateManager, zero or more
        Events exit toward EventDispatcher.

        Never blocks — at CHOICE_END, sets ``self.needs_input = True``
        and stops yielding.  The caller handles the generator pause and
        calls ``apply_choice()`` to resume.
        """
        etype = event.type

        # ── Pass-through events (no state change, no accumulation) ─
        if etype in (
            EventType.STORY_BEGIN,
            EventType.STORY_END,
            EventType.BRIDGE,
            EventType.BRANCH_ENTER,
            EventType.BRANCH_EXIT,
            EventType.CHECKPOINT_END,
        ):
            if etype == EventType.BRANCH_ENTER:
                name = event.payload.get("name", "")
                if event.payload.get("position") == "post":
                    self._post_branches.append(name)
                else:
                    self._pre_branches.append(name)
            yield event
            return

        # ── SEGMENT + SCENE: branch filter ────────────────────────
        # SCENE (Phase 2) is same-level as SEGMENT — both are
        # narrative events subject to branch routing.
        if etype in (EventType.SEGMENT, EventType.SCENE):
            branch = event.payload.get("branch")
            if branch and branch != self._current_branch:
                return
            if etype == EventType.SEGMENT:
                self._segments.append(Segment(
                    text=event.payload.get("text", ""),
                    position=event.payload.get("position", "pre"),
                    branch=branch,
                ))
                if event.payload.get("position") == "post":
                    self._bridge_text_items.append(
                        (event.payload["text"], branch)
                    )
            else:
                self._current_scene = event.payload.get("val")
            yield event
            return

        # ── SET: branch filter + apply to GameState ────────────────
        if etype == EventType.SET:
            branch = event.payload.get("branch")
            if branch and branch != self._current_branch:
                return
            var = event.payload.get("var", "")
            val = event.payload.get("val", "")
            op = event.payload.get("op", "=")
            if_cond = event.payload.get("if")

            # BRANCH_VAR special handling (per block-spec.md §3)
            if var == BRANCH_VAR_NAME:
                if not if_cond or self._game_state.evaluate_condition(
                    if_cond, self._choice_dict
                ):
                    self._current_branch = val or "main"
            else:
                set_op = SetOperation(var=var, op=op, val=val, condition=if_cond)
                self._sets.append(set_op)
                result = self._game_state.apply_set(set_op, self._choice_dict)

                # Condition not met → skip, no UI event
                if result.reason and result.reason.startswith("skipped:"):
                    return

                change = {
                    "var": var,
                    "op": op,
                    "val": val,
                    "accepted": result.accepted,
                    "reason": result.reason,
                }
                if result.reason:
                    self._rejected_changes.append(result.reason)

                # Yield SET event enriched with state-change result
                event.payload["vars"] = self._game_state.state_vars
                event.payload["changes"] = [change]
                yield event
            return

        # ── CHOICE_BEGIN / OPT: consumed, branch-filtered ──────────
        # StreamParser reconstructs structured choice_data from the
        # streaming tags and embeds it in the CHOICE_END payload.
        # StateManager reads it from there — no need to re-accumulate.
        if etype in (EventType.CHOICE_BEGIN, EventType.OPT):
            branch = event.payload.get("branch")
            if branch and branch != self._current_branch:
                return
            return

        # ── CHOICE_END: branch filter + evaluate conditions ─────────
        if etype == EventType.CHOICE_END:
            branch = event.payload.get("branch")
            if branch and branch != self._current_branch:
                return
            choice_data = event.payload.get("choice_data")
            if choice_data:
                # Evaluate option conditions (engine responsibility,
                # per exec-flow.md §4.6)
                branches = choice_data.get("branches", [])
                conditions = choice_data.get("conditions", {})
                enabled = [
                    self._game_state.evaluate_condition(
                        conditions.get(b), {}
                    )
                    for b in branches
                ]
                # Fallback: all disabled → all enabled (prevents lockup)
                if enabled and not any(enabled):
                    enabled = [True] * len(enabled)
                choice_data["enabled"] = enabled

            self._last_choice_data = choice_data
            # Only pause if there are actual options to present.
            # An empty <choice> (no <opt> children) produces
            # choice_data=None — nothing to show the player.
            if choice_data is not None:
                self.needs_input = True
            return

        # ── CHECKPOINT / ROUTE: accumulate ─────────────────────────
        if etype == EventType.CHECKPOINT:
            self._pending_cp_node = event.payload.get("node")
            self._pending_cp_summary = event.payload.get("summary")
            return

        if etype == EventType.ROUTE:
            self._routes.append(RouteTarget(
                condition=event.payload.get("if"),
                target=event.payload.get("target", ""),
            ))
            return

        # ── Default: pass through unknown event types ──────────────
        # DECLARE never reaches here (Parser intercepts).  PARSE_ERROR
        # and genuinely unknown types are yielded so EventDispatcher
        # can surface them.
        yield event

    # ── Choice resolution ──────────────────────────────────────────

    def apply_choice(self, key: str) -> Iterator[Event]:
        """Apply the player's choice and resume processing.

        Called by the main loop after receiving the player's selected
        key via ``gen.send(key)``.  Updates ``current_branch`` and
        ``choice_dict``, then processes any deferred checkpoint if the
        parser was inside a self-closing ``<checkpoint/>``.

        Yields any follow-up Events (e.g. ``save`` from auto-save).
        """
        if self._last_choice_data is None:
            self.needs_input = False
            return

        try:
            idx = int(key) - 1
        except (ValueError, TypeError):
            self.needs_input = False
            return

        branches = self._last_choice_data.get("branches", [])
        cid = self._last_choice_data.get("id", "")
        if 0 <= idx < len(branches):
            branch = branches[idx]
            if branch:
                self._current_branch = branch
            self._choice_dict[cid] = int(key)

        self.needs_input = False
        # _last_choice_data is intentionally NOT cleared — it must
        # remain available for get_result().choices.  A subsequent
        # CHOICE_END in the same round would overwrite it.
        return
        yield  # make this a generator

    @property
    def choice_data(self) -> dict | None:
        """Accumulated choice data for the current CHOICE_END.

        Only valid when ``needs_input`` is True.
        """
        return self._last_choice_data

    # ── Checkpoint processing ──────────────────────────────────────

    def process_checkpoint(self) -> Iterator[Event]:
        """Process the accumulated checkpoint at CHECKPOINT_END.

        Called by the main loop when a CHECKPOINT_END event is received
        (or when a self-closing CHECKPOINT is detected).

        Performs: ending detection, route evaluation, node advancement,
        and auto-save.  Yields save Events if auto-save succeeds.
        """
        cp_node = self._pending_cp_node
        cp_summary = self._pending_cp_summary

        if not cp_node:
            return

        # Validate node exists in outline
        if self._outline_nodes:
            valid_ids = {n.get("id", n.get("node_id", ""))
                         for n in self._outline_nodes}
            if cp_node not in valid_ids:
                self._format_errors.append(
                    f"Unknown checkpoint node: {cp_node}"
                )
                return

        # Ending detection — consult outline definition
        outline_routes: list | None = None
        for n in self._outline_nodes:
            nid = n.get("id", n.get("node_id", ""))
            if nid == cp_node:
                outline_routes = n.get("routes", [])
                break

        is_ending = (
            outline_routes is not None and not outline_routes
        ) if self._outline_nodes else not self._routes

        if is_ending:
            self.ending_flag = True

        # Mark old node completed
        old_node = self._current_node
        if old_node:
            self._set_node_status(old_node, "completed")

        # Advance to target node
        node_advanced = False

        if self.ending_flag:
            self._set_node_status(cp_node, "completed")
            self._current_node = cp_node
            node_advanced = True
        elif self._routes:
            target = self._evaluate_routes(self._choice_dict, self._routes)
            if target:
                # Validate target exists in outline
                if self._outline_nodes:
                    valid_ids = {n.get("id", n.get("node_id", ""))
                                 for n in self._outline_nodes}
                    if target not in valid_ids:
                        self._format_errors.append(
                            f"Route target not in outline: {target}"
                        )
                        return
                self._set_node_status(cp_node, "completed")
                self._set_node_status(target, "active")
                self._current_node = target
                self._goal = self._node_goals.get(target, self._goal or "")
                node_advanced = True
        elif outline_routes:
            rt_routes = [
                RouteTarget(condition=r.get("condition"),
                            target=r.get("target", ""))
                for r in outline_routes
            ]
            target = self._evaluate_routes(self._choice_dict, rt_routes)
            if target:
                self._set_node_status(cp_node, "completed")
                self._set_node_status(target, "active")
                self._current_node = target
                self._goal = self._node_goals.get(target, self._goal or "")
                node_advanced = True
        else:
            target = self._next_outline_node()
            if target:
                self._set_node_status(cp_node, "completed")
                self._set_node_status(target, "active")
                self._current_node = target
                self._goal = self._node_goals.get(target, self._goal or "")
                node_advanced = True

        # Auto-save on successful advancement
        if node_advanced:
            saved = self._accumulate_checkpoint(cp_node, cp_summary or "")
            if saved:
                # Yield a synthetic save event
                yield Event(
                    type=EventType.CHECKPOINT_END,
                    line=0,
                    payload={
                        "save_filename": saved,
                        "checkpoint_node": cp_node,
                    },
                )

        # _pending_cp_node / _pending_cp_summary are intentionally NOT
        # cleared — they must remain available for get_result().
        # If multiple checkpoints appear in a round the last one
        # overwrites.

    # ── Route evaluation ───────────────────────────────────────────

    def _evaluate_routes(
        self,
        choice_dict: dict[str, int],
        routes: list[RouteTarget],
    ) -> str | None:
        """Evaluate route conditions.

        Per data-model.md §2 step 4:
        - First matching condition wins.
        - All conditions fail → fall back to first route's target.
        - No routes → None.
        """
        for route in routes:
            if route.condition is None:
                return route.target
            if self._game_state.evaluate_condition(
                route.condition, choice_dict
            ):
                return route.target

        if routes:
            return routes[0].target
        return None

    def _next_outline_node(self) -> str | None:
        """Return the next node in outline sequence after current_node."""
        if not self._outline_nodes or not self._current_node:
            return None
        for i, node in enumerate(self._outline_nodes):
            nid = node.get("id", node.get("node_id", ""))
            if nid == self._current_node and i + 1 < len(self._outline_nodes):
                return self._outline_nodes[i + 1].get(
                    "id", self._outline_nodes[i + 1].get("node_id", "")
                )
        return None

    def _set_node_status(self, node_id: str, status: str) -> None:
        """Set status on a node in _outline_nodes."""
        for node in self._outline_nodes:
            nid = node.get("id", node.get("node_id", ""))
            if nid == node_id:
                node["status"] = status
                return

    def _accumulate_checkpoint(
        self, cp_node: str, cp_summary: str
    ) -> str | None:
        """Accumulate checkpoint data and trigger auto-save.

        Returns the saved filename if auto-save succeeded, None otherwise.
        """
        cp_title = cp_node
        if cp_summary:
            for node in self._outline_nodes:
                nid = node.get("id", node.get("node_id", ""))
                if nid == cp_node:
                    node["summary"] = cp_summary
                    cp_title = node.get("title", cp_node)
                    break
        else:
            for node in self._outline_nodes:
                nid = node.get("id", node.get("node_id", ""))
                if nid == cp_node:
                    cp_title = node.get("title", cp_node)
                    break

        self._checkpoint_snapshots[cp_node] = dict(
            self._game_state.state_vars
        )

        if self._save_callback is not None:
            try:
                return self._save_callback(cp_node, cp_summary or "")
            except Exception:
                pass
        return None

    # ── Results ────────────────────────────────────────────────────

    def get_result(
        self,
        bridge_found: bool = False,
        parser_format_errors: list[str] | None = None,
    ) -> ParsedOutput:
        """Build ParsedOutput from accumulated data.

        Args:
            bridge_found: Whether ``<bridge/>`` was seen this round
                          (read from ``StreamParser.bridge_seen``).
            parser_format_errors: Format errors from StreamParser
                (post-bridge violations, unrecognized elements, NNN|
                line number mismatches).  Line-number errors are
                routed to ``numbering_issues``; the rest are merged
                into ``self._format_errors`` for LLM feedback.

        Returns:
            ParsedOutput compatible with existing downstream consumers.
        """
        pre_segments = sum(1 for s in self._segments
                           if s.position == "pre")
        post_segments = sum(1 for s in self._segments
                            if s.position == "post")

        # ── Classify parser format errors ──────────────────────────
        # NNN| line number mismatches → numbering_issues.
        # Everything else → merge into self._format_errors so
        # GameLoop can feed them back to the LLM next round.
        numbering_issues: list[str] = []
        if parser_format_errors:
            rest: list[str] = []
            for err in parser_format_errors:
                if "Line number mismatch" in err:
                    numbering_issues.append(err)
                else:
                    rest.append(err)
            self._format_errors.extend(rest)

        # Build choice fields from the last CHOICE_END's payload
        # (reconstructed by StreamParser, evaluated by StateManager).
        choice_id: str | None = None
        opt_branches: list[str] = []
        choices: list[dict] = []
        if self._last_choice_data is not None:
            choice_id = self._last_choice_data.get("id")
            opt_branches = list(self._last_choice_data.get("branches", []))
            choices = [self._last_choice_data]

        return ParsedOutput(
            segments=list(self._segments),
            total_segments=len(self._segments),
            pre_segments=pre_segments,
            post_segments=post_segments,
            choice_id=choice_id,
            opt_branches=opt_branches,
            choices=choices,
            sets=list(self._sets),
            checkpoint_node=self._pending_cp_node,
            checkpoint_summary=self._pending_cp_summary,
            routes=list(self._routes),
            bridge_found=bridge_found,
            bridge_text="\n".join(t for t, _ in self._bridge_text_items),
            numbering_issues=numbering_issues,
            pre_branches=list(self._pre_branches),
            post_branches=list(self._post_branches),
        )

    def get_bridge_text(self, branch_name: str | None = None) -> str:
        """Extract bridge text, optionally filtered by branch.

        Per block-spec.md §4: bare ``<seg>`` elements (branch=None) are
        the implicit "main" branch and are always included.  Named-branch
        ``<seg>`` elements are included only when *branch_name* matches.
        """
        if branch_name is None:
            return "\n".join(t for t, _ in self._bridge_text_items)
        texts: list[str] = []
        for text, br in self._bridge_text_items:
            if br is None or br == branch_name:
                texts.append(text)
        return "\n".join(texts)

    # ── State queries ──────────────────────────────────────────────

    @property
    def current_branch(self) -> str:
        """Active branch name (from player's last choice or default)."""
        return self._current_branch

    @property
    def current_scene(self) -> str | None:
        """Current scene name from last SCENE event (Phase 2)."""
        return self._current_scene

    @property
    def rejected_changes(self) -> list[str]:
        """Rejected state-change reasons for LLM feedback."""
        return list(self._rejected_changes)

    @property
    def routes(self) -> list[RouteTarget]:
        """Route targets accumulated from ``<route>`` elements (copy)."""
        return list(self._routes)

    @property
    def format_errors(self) -> list[str]:
        """Format errors accumulated during state processing."""
        return list(self._format_errors)

    @property
    def current_node(self) -> str | None:
        """Current active outline node ID."""
        return self._current_node

    @property
    def goal(self) -> str | None:
        """Current node's goal description."""
        return self._goal

    @property
    def checkpoint_snapshots(self) -> dict[str, dict]:
        """State snapshots keyed by checkpoint node ID."""
        return dict(self._checkpoint_snapshots)

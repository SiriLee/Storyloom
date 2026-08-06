"""Event dispatcher — converts Events to UI event dicts.

Per design.md §3.2: aligns Events with Tasks by line number, waits for
incomplete Tasks, binds assets, and pushes to the UI Event Queue.

Phase 1: simple Event → UI dict mapping (no Task Queue).
Phase 2: ``consume_event()`` implements the §4.3 algorithm with Task
Queue alignment and asset binding.
"""

from collections import deque
from typing import TYPE_CHECKING

from storyloom.parser.stream_parser import Event, EventType

if TYPE_CHECKING:
    from storyloom.assets import GameAssetRoster
    from storyloom.tasks import Task


class EventDispatcher:
    """Converts processed Events to UI event dicts.

    Per design.md §3.1 topology: the final pipeline stage before UI.

    Phase 1 — ``dispatch()``: pure Event → UI dict conversion.
    Phase 2 — ``consume_event()``: Task Queue alignment (§4.3 algorithm),
    asset binding via roster lookup, then dispatch to UI.

    Args:
        task_queue: FIFO deque of pending Tasks.  ``None`` in text mode.
        roster: Per-game asset roster for binding.  ``None`` in text mode.
            Must be both set (graph mode) or both ``None`` (text mode).
    """

    def __init__(self, task_queue: deque | None = None,
                 roster: "GameAssetRoster | None" = None):
        if (task_queue is None) != (roster is None):
            raise ValueError(
                "task_queue and roster must both be set (graph mode) "
                "or both be None (text mode)"
            )
        self._task_queue = task_queue
        self._roster = roster

    # ── Phase 1: dispatch ──────────────────────────────────────────

    def dispatch(self, event: Event) -> dict:
        """Convert a single Event to a UI event dict.

        Maps each EventType to its corresponding UI event format.
        Events that do not produce UI output (e.g. internal-only
        accumulators) return an empty dict — the caller should skip
        yielding them.
        """
        etype = event.type
        payload = event.payload

        if etype == EventType.STORY_BEGIN:
            return {"type": "story_begin"}

        if etype == EventType.STORY_END:
            return {"type": "story_end"}

        if etype == EventType.BRIDGE:
            return {"type": "bridge"}

        if etype == EventType.SEGMENT:
            result = {
                "type": "segment",
                "text": payload.get("text", ""),
                "n": payload.get("n", 0),
                "position": payload.get("position", "pre"),
                "branch": payload.get("branch"),
            }
            if "assets" in payload:
                result["assets"] = payload["assets"]
            return result

        if etype == EventType.SET:
            result = {
                "type": "state",
                "vars": payload.get("vars", {}),
                "changes": payload.get("changes", []),
            }
            if "assets" in payload:
                result["assets"] = payload["assets"]
            return result

        # Events that reach dispatch but have no UI representation.
        # StateManager passes them through but UI doesn't render them.
        if etype in (EventType.BRANCH_ENTER, EventType.BRANCH_EXIT,
                      EventType.CHECKPOINT_END):
            return {}

        # Events consumed upstream — should never reach dispatch.
        # Return empty dict as a safety net.
        if etype in (EventType.CHOICE_BEGIN, EventType.OPT,
                      EventType.CHOICE_END, EventType.CHECKPOINT,
                      EventType.ROUTE):
            return {}

        # PARSE_ERROR: LLM output error surfaced as a UI event.
        if etype == EventType.PARSE_ERROR:
            return {
                "type": "error",
                "message": payload.get("error", "Parse error"),
            }

        # Default: genuinely unknown event types (Phase 2 additions not
        # yet handled, program errors).  Never silently swallow.
        return {
            "type": "event",
            "event_type": etype.name,
            "payload": payload,
        }

    # ── Choice / Save helpers ──────────────────────────────────────

    def dispatch_choice(self, choice_data: dict) -> dict:
        """Build the ``options`` UI event from accumulated choice data.

        Called by the main loop when ``StateManager.needs_input`` is
        True (at CHOICE_END).
        """
        return {
            "type": "options",
            "choices": [choice_data],
        }

    def dispatch_save(self, filename: str, checkpoint_node: str) -> dict:
        """Build a ``save`` UI event after a successful auto-save.

        Args:
            filename: Saved file name.
            checkpoint_node: Node ID of the checkpoint.

        Returns:
            UI event dict: ``{"type": "save", "filename": ..., "checkpoint_node": ...}``.
        """
        return {
            "type": "save",
            "filename": filename,
            "checkpoint_node": checkpoint_node,
        }

    # ── Phase 2: consume_event (§4.3 algorithm) ──────────────────────

    def consume_event(self, event: Event) -> dict:
        """Phase 2 entry point — Task Queue alignment + asset binding.

        Per design.md §4.3::

            consume_event(event):
                while task_queue not empty and head.line < event.line:
                    task = pop()
                    if task.line == 0:
                        wait(task.completed)   # DECLARE: wait then discard
                    # else: orphan task, discard
                if task_queue not empty and head.line == event.line:
                    task = pop()
                    wait(task.completed)       # wait for match
                    asset_id = roster.lookup(...).target
                    event.payload["assets"] = {...}
                send_to_ui(event)

        In text mode (``_task_queue is None``), delegates to ``dispatch()``.
        """
        # Text mode / Phase 1: no task subsystem wired.
        if self._task_queue is None:
            return self.dispatch(event)

        q = self._task_queue

        # 1. Drain tasks strictly before this event's line.
        while q and q[0].line < event.line:
            task = q.popleft()
            if task.line == 0:
                task.wait()                    # DECLARE: wait then discard
            # else: orphan task, discard (no wait)

        # 2. Aligned task at this line → wait + lookup + bind.
        if q and q[0].line == event.line:
            task = q.popleft()
            task.wait()
            item = self._roster.lookup(task.asset_type, task.result)
            asset_id = item.target if item is not None else None
            if asset_id is not None:
                event.payload["assets"] = {task.asset_type.value: asset_id}
            # lookup failed or target=None → silent skip (no binding)

        # 3. Convert to UI dict.
        return self.dispatch(event)

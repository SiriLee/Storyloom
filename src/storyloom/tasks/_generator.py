"""TaskGenerator — builds Tasks, runs O(1) program match, submits to pool.

Per design.md §3.2 + §6.3-6.4.  Receives Event objects via ``enqueue()``,
dispatches by type, runs the program-match fast path, and submits async
processes to the Task Pool.

Parser never references this module (§7.4).
"""

from __future__ import annotations

from collections import deque

from storyloom.assets import AssetType, GameAssetRoster
from storyloom.parser.stream_parser import Event, EventType
from storyloom.tasks._pool import TaskPool
from storyloom.tasks._types import Task, TaskType


class TaskGenerator:
    """Builds Tasks from media Events and runs the O(1) program match.

    Args:
        task_queue: FIFO deque — tasks are appended immediately on creation.
        roster: Per-game asset roster for program-match lookups.
        match_processor: ``Callable[[AssetType, str, GameAssetRoster], Callable[[Task], None]] | None`` —
            returns a closure for ``Task.process`` when program match fails
            for MATCH tasks (§7.8a).  ``None`` → sync-complete as no-op.
        generate_processor: Same protocol for GENERATE tasks (§7.8b).
            ``None`` → sync-complete as no-op (placeholder still created).
        task_pool: Thread 4 executor.  If ``None``, async tasks are not
            submitted (useful for testing program match in isolation).
    """

    # Per design.md §2.1: "类型可扩展至特效、语音等".  Map DECLARE kind
    # strings to AssetType so new types only require adding an entry here.
    _DECLARE_KIND_MAP: dict[str, AssetType] = {
        "CHAR": AssetType.CHAR_PORTRAIT,
        "SCENE": AssetType.BACKGROUND,
    }

    def __init__(self, task_queue: deque[Task], roster: GameAssetRoster,
                 match_processor=None,
                 generate_processor=None,
                 task_pool: TaskPool | None = None,
                 roster_path: str | None = None):
        self._queue = task_queue
        self._roster = roster
        self._pool = task_pool
        self._match_processor = match_processor
        self._generate_processor = generate_processor
        self._roster_path = roster_path

    # ── Public API ───────────────────────────────────────────────────────

    def enqueue(self, event: Event) -> Task | None:
        """Dispatch by event type.  Returns the created Task, or ``None``
        if *event* is not a media event.

        Per design.md §4.1:
          - SCENE → MATCH (BACKGROUND)
          - SEGMENT with ``char`` → MATCH (CHAR_PORTRAIT)
          - DECLARE → GENERATE (line=0)
        """
        etype = event.type
        if etype == EventType.SCENE:
            return self._enqueue_match(event, AssetType.BACKGROUND)
        elif etype == EventType.SEGMENT and event.payload.get("char"):
            return self._enqueue_match(event, AssetType.CHAR_PORTRAIT)
        elif etype == EventType.DECLARE:
            return self._enqueue_generate(event)
        return None

    # ── MATCH ─────────────────────────────────────────────────────────────

    # Per design.md §4.1: MATCH keys by event type.
    _MATCH_KEY: dict[AssetType, str] = {
        AssetType.BACKGROUND: "val",        # SCENE event
        AssetType.CHAR_PORTRAIT: "char",    # SEGMENT event (with char attr)
    }

    def _enqueue_match(self, event: Event, asset_type: AssetType) -> Task:
        """Per design.md §6.3: create MATCH task, run O(1) roster lookup."""
        key = self._MATCH_KEY.get(asset_type, "")
        local_name = event.payload.get(key, "") if key else ""
        task = Task(TaskType.MATCH, event.line, asset_type)
        self._queue.append(task)

        if local_name and self._roster.lookup(asset_type, local_name) is not None:
            task.complete(result=local_name)          # O(1) hit
        elif local_name and self._match_processor is not None:
            task.process = self._match_processor(asset_type, local_name,
                                                           self._roster)
            if self._pool is not None:
                self._pool.submit(task)
        else:
            task.complete()                           # no processor or empty name → no-op
        return task

    # ── GENERATE ──────────────────────────────────────────────────────────

    def _enqueue_generate(self, event: Event) -> Task:
        """Per design.md §6.4: create GENERATE task (line=0), run O(1)
        roster lookup.  On miss, create a placeholder AssetItem BEFORE
        submitting to the pool (§6.4 step 3 — prevents duplicate
        declarations)."""
        kind = event.payload.get("kind", "CHAR").upper()
        # Unknown kinds fall back to BACKGROUND (safest default).
        # kind validation / format_error recording belongs in the Parser (§7.5),
        # not in TaskGenerator — this is the data layer, not the validation layer.
        asset_type = self._DECLARE_KIND_MAP.get(kind, AssetType.BACKGROUND)
        local_name = event.payload.get("name", "")
        desc = event.payload.get("desc", "")

        task = Task(TaskType.GENERATE, 0, asset_type)
        self._queue.append(task)

        if local_name and self._roster.lookup(asset_type, local_name) is not None:
            task.complete()                            # already declared
        elif local_name:
            # Placeholder first — sync, before pool submit (design.md §6.4)
            self._roster.add(asset_type, local_name, desc, target=None)
            if self._roster_path:
                self._roster.save(self._roster_path)
            if self._generate_processor is not None:
                task.process = self._generate_processor(asset_type, local_name,
                                                                  self._roster)
                if self._pool is not None:
                    self._pool.submit(task)
            else:
                task.complete()                        # no processor — placeholder stays
        # else: empty local_name → skip placeholder, sync-complete as no-op
        # (LLM output error — nothing meaningful to generate)
        else:
            task.complete()
        return task

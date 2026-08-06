"""Task data types — TaskType, Task, TaskTimeoutError.

Per design.md §4.2: Task model with cross-thread completion signalling.
Thread 4 (TaskPool) writes result + calls complete(); Thread 2
(EventDispatcher) calls wait() to block until done.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable

from storyloom.assets import AssetType


class TaskType(Enum):
    """Per design.md §4.2: MATCH (programmatic lookup) or GENERATE (AI generation)."""
    MATCH = auto()
    GENERATE = auto()


class TaskTimeoutError(RuntimeError):
    """Raised when ``Task.wait(timeout=...)`` expires before completion."""
    pass


@dataclass(eq=False)
class Task:
    """A media-production task aligned to an Event by line number.

    Per design.md §4.2:
      - *line* is the associated Event line; 0 for DECLARE-triggered tasks.
      - *process* is the async callable run by Thread 4; None = sync-completed.
      - *result* stores the matched local_name for MATCH tasks.
      - *error* is set by TaskPool if process raises (reserved, §7.8).

    Thread safety: *completed* is observable; *_done* (``threading.Event``)
    is the cross-thread signal.  Thread 4 writes *result* then calls
    ``complete()`` (release); Thread 2 ``wait()`` acquires then reads
    *result*.  All other fields are write-once at construction.
    """
    task_type: TaskType
    line: int                       # Event line; 0 for DECLARE
    asset_type: AssetType
    process: Callable[["Task"], None] | None = None  # None = sync-done
    result: str | None = None       # MATCH → local_name; GENERATE → unused
    completed: bool = field(default=False, init=False)
    error: str | None = field(default=None, init=False)   # reserved (§7.8)
    _done: threading.Event = field(default_factory=threading.Event,
                                   repr=False)

    def complete(self, result: str | None = None) -> None:
        """Mark the task as completed.  Idempotent — the only transition point.

        Sets *completed*, fires the ``threading.Event``, and sets *result*
        on the **first** call only (subsequent calls do not overwrite).
        """
        if self.completed:
            return
        self.completed = True
        if result is not None:
            self.result = result
        self._done.set()

    def wait(self, timeout: float | None = None) -> bool:
        """Block until ``complete()`` is called.

        Args:
            timeout: Seconds to wait, or ``None`` (block forever).

        Returns:
            ``True`` if completed, ``False`` if *timeout* expired.

        Raises:
            TaskTimeoutError: When *timeout* expires.  Callers that
                cannot recover should let this propagate.
        """
        if self._done.wait(timeout):
            return True
        raise TaskTimeoutError(
            f"Task(line={self.line}, type={self.task_type.name}) "
            f"not completed within timeout={timeout}"
        )

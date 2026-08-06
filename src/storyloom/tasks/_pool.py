"""TaskPool — ThreadPoolExecutor wrapper (design.md §3.3, Thread 4).

Executes ``Task.process`` for tasks that fail the O(1) program match.
Exception-safe: ``finally: task.complete()`` guarantees the EventDispatcher
never hangs on a failed process.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from storyloom.config import TASK_POOL_MAX_WORKERS
from storyloom.tasks._types import Task


class TaskPool:
    """Thread 4 — executes async Task.process closures.

    Usage::

        pool = TaskPool(max_workers=2)
        pool.submit(task)
        # ... later ...
        pool.shutdown()
    """

    def __init__(self, max_workers: int | None = None):
        n = max_workers if max_workers is not None else TASK_POOL_MAX_WORKERS
        self._executor = ThreadPoolExecutor(max_workers=n)

    # ── Public API ─────────────────────────────────────────────────────

    def submit(self, task: Task) -> None:
        """Submit *task.process* to the thread pool.

        No-op if the task is already completed or has no *process*
        (sync-completed via program match).
        """
        if task.completed or task.process is None:
            return
        self._executor.submit(self._run, task)

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the pool.  If *wait* is True, block until all
        running tasks finish."""
        self._executor.shutdown(wait=wait)

    # ── Context manager ─────────────────────────────────────────────────

    def __enter__(self) -> "TaskPool":
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()

    # ── Internal ────────────────────────────────────────────────────────

    @staticmethod
    def _run(task: Task) -> None:
        """Execute *task.process* with a safety net.

        ``finally: task.complete()`` is the architectural guarantee —
        the EventDispatcher (Thread 2) must never block forever waiting
        on a task whose process raised.  Exceptions are recorded in
        ``task.error`` for silent degradation (§7.8).
        """
        try:
            task.process(task)
        except Exception as e:
            task.error = f"{type(e).__name__}: {e}"
        finally:
            task.complete()

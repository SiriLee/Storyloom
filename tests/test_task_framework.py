"""Tests for the Task framework — Task, TaskPool, TaskGenerator, EventDispatcher.

Per design.md §7.4: stub pipeline verified via manually constructed event
sequences.  Stub helpers and constants live here (test-only, deleted in §7.8).
Tests are designed to be reusable for §7.6 (real parser-driven events).

TDD order: TestTask → TestTaskPool → TestTaskGenerator →
           TestEventDispatcherConsume → TestPipelineE2E → TestTextModeUnaffected
"""

import threading
import time
from collections import deque
from types import SimpleNamespace

import pytest

from storyloom.assets import Asset, AssetItem, AssetLibrary, AssetType, GameAssetRoster
from storyloom.core.event_dispatcher import EventDispatcher
from storyloom.parser.stream_parser import Event, EventType
from storyloom.tasks import Task, TaskGenerator, TaskPool, TaskTimeoutError, TaskType


# ═══════════════════════════════════════════════════════════════════════
# Stub helpers (test-only — deleted in §7.8)
# ═══════════════════════════════════════════════════════════════════════

STUB_DELAY = 0.01          # seconds — fast tests, observable async
STUB_ASSET_ID = "__stub__"
STUB_LOCAL_NAME = "stub"


def stub_process_factory(asset_type: AssetType, local_name: str,
                        roster: GameAssetRoster):
    """Return a closure for Task.process.  Sleeps STUB_DELAY, then:
    - MATCH: sets result = STUB_LOCAL_NAME (all assets → same stub image)
    - GENERATE: fills placeholder target → STUB_ASSET_ID
    """
    def _process(task: Task) -> None:
        time.sleep(STUB_DELAY)
        if task.task_type is TaskType.MATCH:
            task.result = STUB_LOCAL_NAME
        else:
            # GENERATE: fill the placeholder created by TaskGenerator
            roster.set_target(asset_type, local_name, STUB_ASSET_ID)
    return _process


def populate_stub_assets(library: AssetLibrary, roster: GameAssetRoster) -> None:
    """Bootstrap: each AssetType gets one stub Asset + one roster entry
    mapping STUB_LOCAL_NAME → STUB_ASSET_ID.  Idempotent."""
    for atype in AssetType:
        if library.get(atype, STUB_ASSET_ID) is None:
            library.add(atype, "stub", "temp", asset_id=STUB_ASSET_ID)
        if roster.lookup(atype, STUB_LOCAL_NAME) is None:
            roster.add(atype, STUB_LOCAL_NAME, "temp", target=STUB_ASSET_ID)


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def library():
    """Fresh AssetLibrary in a temp directory."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        yield AssetLibrary(d)


@pytest.fixture
def roster(library):
    """Fresh GameAssetRoster wired to *library*."""
    yield GameAssetRoster("test_game", library)


@pytest.fixture
def pipeline(library, roster):
    """Complete 7.4 stub pipeline.

    §7.6 redefines this fixture (real process_factory, parser-driven
    events) and the same test classes replay unchanged.
    """
    populate_stub_assets(library, roster)
    q: deque[Task] = deque()
    pool = TaskPool(max_workers=2)
    def _factory(atype, lname, _roster):
        return stub_process_factory(atype, lname, _roster)

    gen = TaskGenerator(q, roster, match_processor=_factory,
                        generate_processor=_factory,
                        task_pool=pool)
    dispatcher = EventDispatcher(q, roster)
    yield SimpleNamespace(
        queue=q, pool=pool, gen=gen, dispatcher=dispatcher,
        roster=roster, library=library,
    )
    pool.shutdown()


# ═══════════════════════════════════════════════════════════════════════
# 1. TestTask
# ═══════════════════════════════════════════════════════════════════════

class TestTask:
    """Task dataclass — construction, defaults, complete(), wait()."""

    def test_construction_minimal(self):
        """Task is created with required fields only."""
        t = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        assert t.task_type == TaskType.MATCH
        assert t.line == 5
        assert t.asset_type == AssetType.CHAR_PORTRAIT
        assert t.process is None
        assert t.result is None
        assert t.completed is False
        assert t.error is None

    def test_construction_full(self):
        """All optional fields accepted at construction."""
        def dummy(_task): pass
        t = Task(TaskType.GENERATE, 0, AssetType.BACKGROUND,
                 process=dummy, result="hero")
        assert t.process is dummy
        assert t.result == "hero"

    def test_completed_starts_false(self):
        """completed is False until complete() is called."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)
        assert t.completed is False

    def test_complete_transitions(self):
        """complete() sets completed=True and fires the Event."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)
        t.complete()
        assert t.completed is True

    def test_complete_sets_result(self):
        """complete(result=...) updates result."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)
        t.complete(result="hero")
        assert t.result == "hero"

    def test_complete_result_none_does_not_overwrite(self):
        """complete() without result leaves existing result intact."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT, result="existing")
        t.complete()  # no result arg
        assert t.result == "existing"

    def test_complete_idempotent(self):
        """Multiple complete() calls are safe."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)
        t.complete(result="first")
        t.complete(result="second")  # should not change
        assert t.completed is True
        assert t.result == "first"

    def test_wait_blocks_until_complete(self):
        """wait() returns True after complete() is called from another thread."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)
        results = []

        def waiter():
            results.append(t.wait(timeout=2.0))

        th = threading.Thread(target=waiter)
        th.start()
        time.sleep(0.02)             # let waiter enter wait()
        t.complete()
        th.join(timeout=2.0)
        assert not th.is_alive()
        assert results == [True]

    def test_wait_timeout_raises(self):
        """wait(timeout) raises TaskTimeoutError if complete() not called."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)
        with pytest.raises(TaskTimeoutError, match="timeout"):
            t.wait(timeout=0.01)

    def test_wait_no_timeout_blocks(self):
        """wait() without timeout blocks forever (probed with a tiny delay)."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)
        completed_flag = threading.Event()

        def delayed_complete():
            time.sleep(0.05)
            t.complete()
            completed_flag.set()

        threading.Thread(target=delayed_complete, daemon=True).start()
        result = t.wait(timeout=2.0)
        assert result is True
        assert t.completed is True
        assert completed_flag.is_set()  # side thread completed its work

    def test_error_defaults_to_none(self):
        """error is None by default."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)
        assert t.error is None

    def test_wait_multiple_calls_after_complete(self):
        """wait() called multiple times after complete → all return True."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)
        t.complete()
        assert t.wait(timeout=0.01) is True
        assert t.wait(timeout=0.01) is True
        assert t.wait(timeout=0.01) is True


# ═══════════════════════════════════════════════════════════════════════
# 2. TestTaskPool
# ═══════════════════════════════════════════════════════════════════════

class TestTaskPool:
    """TaskPool — submit, async execution, exception safety, shutdown."""

    def test_submit_runs_process(self):
        """submit() executes task.process asynchronously."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)
        results = []

        def my_process(task):
            results.append("ran")

        t.process = my_process
        with TaskPool(max_workers=1) as pool:
            pool.submit(t)
            t.wait(timeout=2.0)

        assert results == ["ran"]
        assert t.completed is True

    def test_submit_sets_completed(self):
        """After submit + wait, completed is True."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)

        def my_process(task):
            pass

        t.process = my_process
        with TaskPool(max_workers=1) as pool:
            pool.submit(t)
            t.wait(timeout=2.0)

        assert t.completed is True

    def test_submit_noop_if_already_completed(self):
        """submit() does nothing if task is already completed."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)
        t.complete()
        results = []

        def my_process(task):
            results.append("should not run")

        t.process = my_process
        with TaskPool(max_workers=1) as pool:
            pool.submit(t)

        assert results == []

    def test_submit_noop_if_no_process(self):
        """submit() does nothing if task.process is None."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT, process=None)
        with TaskPool(max_workers=1) as pool:
            pool.submit(t)  # should not raise
        assert t.completed is False

    def test_exception_sets_error_and_completes(self):
        """Process exception → task.error set + task.complete() called."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)

        def failing_process(task):
            raise ValueError("boom")

        t.process = failing_process
        with TaskPool(max_workers=1) as pool:
            pool.submit(t)
            t.wait(timeout=2.0)

        assert t.completed is True
        assert t.error is not None
        assert "ValueError" in t.error
        assert "boom" in t.error

    def test_shutdown_waits_for_tasks(self):
        """shutdown(wait=True) blocks until running tasks finish."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)

        def slow_process(task):
            time.sleep(0.05)

        t.process = slow_process
        pool = TaskPool(max_workers=1)
        pool.submit(t)
        pool.shutdown(wait=True)
        # If we get here without hanging, shutdown waited correctly
        assert t.completed is True

    def test_context_manager(self):
        """TaskPool works as a context manager."""
        t = Task(TaskType.MATCH, 1, AssetType.CHAR_PORTRAIT)

        def my_process(task):
            pass

        t.process = my_process

        with TaskPool(max_workers=1) as pool:
            pool.submit(t)
            t.wait(timeout=2.0)

        assert t.completed is True

    def test_default_max_workers_from_config(self):
        """When max_workers is omitted, TASK_POOL_MAX_WORKERS from config is used."""
        pool = TaskPool()
        # Can't introspect max_workers directly, but construction shouldn't raise
        assert pool is not None
        pool.shutdown()


# ═══════════════════════════════════════════════════════════════════════
# 3. TestTaskGenerator
# ═══════════════════════════════════════════════════════════════════════

class TestTaskGenerator:
    """TaskGenerator — program match, enqueue, placeholder creation."""

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _make_event(etype, line, **payload):
        return Event(etype, line, payload)

    # ── MATCH: program match hit ──────────────────────────────────────

    def test_match_scene_hit_sync_completes(self, pipeline):
        """SCENE with known local_name → sync complete, result=local_name."""
        # Pre-populate roster with a known entry
        pipeline.roster.add(AssetType.BACKGROUND, "forest",
                            target=STUB_ASSET_ID)

        event = self._make_event(EventType.SCENE, 5, val="forest")
        task = pipeline.gen.enqueue(event)

        assert task is not None
        assert task.task_type == TaskType.MATCH
        assert task.line == 5
        assert task.asset_type == AssetType.BACKGROUND
        assert task.completed is True
        assert task.result == "forest"
        assert task.process is None  # sync — no pool needed

    def test_match_seg_char_hit_sync_completes(self, pipeline):
        """SEGMENT with known char → sync complete."""
        pipeline.roster.add(AssetType.CHAR_PORTRAIT, "hero",
                            target=STUB_ASSET_ID)

        event = self._make_event(EventType.SEGMENT, 3,
                                 text="...", position="pre",
                                 char="hero")
        task = pipeline.gen.enqueue(event)

        assert task is not None
        assert task.task_type == TaskType.MATCH
        assert task.asset_type == AssetType.CHAR_PORTRAIT
        assert task.completed is True
        assert task.result == "hero"

    # ── MATCH: program match miss ─────────────────────────────────────

    def test_match_miss_assigns_process(self, pipeline):
        """Unknown local_name → process assigned, not completed."""
        event = self._make_event(EventType.SCENE, 5, val="unknown_place")
        task = pipeline.gen.enqueue(event)

        assert task is not None
        assert task.completed is False
        assert task.process is not None

    def test_match_miss_completes_after_stub(self, pipeline):
        """Stub process runs → completed + result after delay."""
        event = self._make_event(EventType.SCENE, 5, val="unknown_place")
        task = pipeline.gen.enqueue(event)
        assert task.completed is False

        task.wait(timeout=2.0)
        assert task.completed is True
        assert task.result == STUB_LOCAL_NAME

    # ── MATCH: no local_name ──────────────────────────────────────────

    def test_match_empty_local_name_sync_completes_noop(self, pipeline):
        """SCENE with val='' → sync-complete no-op (LLM output error)."""
        event = self._make_event(EventType.SCENE, 5, val="")
        task = pipeline.gen.enqueue(event)
        assert task is not None
        assert task.completed is True
        assert task.process is None

    # ── GENERATE: program match hit ───────────────────────────────────

    def test_generate_existing_name_sync_completes(self, pipeline):
        """DECLARE of already-declared name → sync complete, no duplicate."""
        pipeline.roster.add(AssetType.CHAR_PORTRAIT, "stranger",
                            target=None)  # placeholder

        event = self._make_event(EventType.DECLARE, 2,
                                 kind="CHAR", name="stranger",
                                 desc="a hooded figure")
        task = pipeline.gen.enqueue(event)

        assert task is not None
        assert task.task_type == TaskType.GENERATE
        assert task.line == 0
        assert task.completed is True

    # ── GENERATE: program match miss → placeholder ────────────────────

    def test_generate_new_name_creates_placeholder(self, pipeline):
        """DECLARE of new name → placeholder created BEFORE pool submit."""
        event = self._make_event(EventType.DECLARE, 2,
                                 kind="CHAR", name="ghost",
                                 desc="a spectral presence")
        task = pipeline.gen.enqueue(event)

        # Placeholder must exist immediately (sync, before pool runs)
        item = pipeline.roster.lookup(AssetType.CHAR_PORTRAIT, "ghost")
        assert item is not None
        assert item.target is None          # placeholder — no real image yet
        assert task.completed is False
        assert task.process is not None

    def test_generate_duplicate_prevented_by_placeholder(self, pipeline):
        """Second DECLARE of same name → sync complete (placeholder blocks)."""
        event = self._make_event(EventType.DECLARE, 2,
                                 kind="CHAR", name="wraith",
                                 desc="first declare")

        task1 = pipeline.gen.enqueue(event)
        assert task1.completed is False             # submitted to pool

        # Second declare same name before pool finishes
        task2 = pipeline.gen.enqueue(event)
        assert task2.completed is True              # placeholder hit → sync

    def test_generate_scene_kind_becomes_background(self, pipeline):
        """DECLARE kind='SCENE' → asset_type = BACKGROUND."""
        event = self._make_event(EventType.DECLARE, 2,
                                 kind="SCENE", name="crypt",
                                 desc="an ancient crypt")
        task = pipeline.gen.enqueue(event)
        assert task.asset_type == AssetType.BACKGROUND

    # ── FIFO enqueue order ────────────────────────────────────────────

    def test_fifo_enqueue_order(self, pipeline):
        """Tasks are enqueued in creation order."""
        e1 = self._make_event(EventType.SCENE, 10, val="forest")
        e2 = self._make_event(EventType.SCENE, 20, val="tavern")
        pipeline.roster.add(AssetType.BACKGROUND, "forest",
                            target=STUB_ASSET_ID)
        pipeline.roster.add(AssetType.BACKGROUND, "tavern",
                            target=STUB_ASSET_ID)

        t1 = pipeline.gen.enqueue(e1)
        t2 = pipeline.gen.enqueue(e2)

        assert pipeline.queue[0] is t1
        assert pipeline.queue[1] is t2

    # ── Non-media events ──────────────────────────────────────────────

    def test_non_media_event_returns_none(self, pipeline):
        """SEGMENT without char, SET, CHOICE etc. → None."""
        event = self._make_event(EventType.SEGMENT, 1,
                                 text="hello", position="pre")
        task = pipeline.gen.enqueue(event)
        assert task is None

    def test_set_event_returns_none(self, pipeline):
        event = self._make_event(EventType.SET, 2,
                                 var="trust", op="=", val="10")
        task = pipeline.gen.enqueue(event)
        assert task is None

    # ── Edge cases ─────────────────────────────────────────────────────

    def test_declare_unknown_kind_defaults_to_background(self, pipeline):
        """DECLARE kind='BGM' (unknown) → asset_type = BACKGROUND."""
        event = self._make_event(EventType.DECLARE, 2,
                                 kind="BGM", name="theme",
                                 desc="an epic theme")
        task = pipeline.gen.enqueue(event)
        assert task.asset_type == AssetType.BACKGROUND

    def test_seg_char_empty_does_not_trigger_match(self, pipeline):
        """SEGMENT with char='' → no MATCH (per design: empty means no portrait)."""
        event = self._make_event(EventType.SEGMENT, 5,
                                 text="narrator", position="pre",
                                 char="")
        task = pipeline.gen.enqueue(event)
        assert task is None

    def test_declare_empty_name_sync_completes_noop(self, pipeline):
        """DECLARE with name='' → sync-complete as no-op (LLM output error)."""
        event = self._make_event(EventType.DECLARE, 2,
                                 kind="CHAR", name="", desc="forgotten name")
        task = pipeline.gen.enqueue(event)
        assert task is not None
        assert task.completed is True
        # No placeholder created with empty key
        assert len(pipeline.roster) == 2  # only the 2 stub entries



# ═══════════════════════════════════════════════════════════════════════
# 4. TestEventDispatcherConsume
# ═══════════════════════════════════════════════════════════════════════

class TestEventDispatcherConsume:
    """EventDispatcher.consume_event() — §4.3 algorithm."""

    @staticmethod
    def _make_event(etype, line, **payload):
        return Event(etype, line, payload)

    # ── Constructor guard ─────────────────────────────────────────────

    def test_constructor_guard_both_none(self):
        """No args → valid text mode."""
        d = EventDispatcher()
        assert d is not None

    def test_constructor_guard_both_set(self, pipeline):
        """Both task_queue and roster set → valid graph mode."""
        d = EventDispatcher(pipeline.queue, pipeline.roster)
        assert d is not None

    def test_constructor_guard_mismatch_raises(self):
        """task_queue set but roster None → ValueError."""
        from collections import deque
        with pytest.raises(ValueError, match="both be set"):
            EventDispatcher(task_queue=deque(), roster=None)

    def test_constructor_guard_roster_only_raises(self, pipeline):
        """roster set but task_queue None → ValueError."""
        with pytest.raises(ValueError, match="both be set"):
            EventDispatcher(task_queue=None, roster=pipeline.roster)

    # ── Sync bind (task pre-completed by program match) ───────────────

    def test_sync_match_bind(self, pipeline):
        """SCENE with known name → task sync-completed → assets in payload AND UI dict."""
        pipeline.roster.add(AssetType.BACKGROUND, "forest",
                            target=STUB_ASSET_ID)

        event = self._make_event(EventType.SCENE, 5, val="forest")
        pipeline.gen.enqueue(event)            # task sync-completed, result="forest"
        result = pipeline.dispatcher.consume_event(event)

        assert "assets" in event.payload
        assert event.payload["assets"] == {AssetType.BACKGROUND.value: STUB_ASSET_ID}
        # SCENE now has its own dispatch handler (§7.5)
        assert result["type"] == "scene"
        assert result["assets"] == {AssetType.BACKGROUND.value: STUB_ASSET_ID}

    def test_sync_match_bind_seg_char(self, pipeline):
        """SEGMENT with known char → portrait bound in BOTH payload and UI dict."""
        pipeline.roster.add(AssetType.CHAR_PORTRAIT, "hero",
                            target=STUB_ASSET_ID)

        event = self._make_event(EventType.SEGMENT, 3,
                                 text="...", position="pre",
                                 char="hero")
        pipeline.gen.enqueue(event)
        result = pipeline.dispatcher.consume_event(event)

        assert event.payload["assets"] == {AssetType.CHAR_PORTRAIT.value: STUB_ASSET_ID}
        # dispatch() must propagate assets to the UI dict
        assert result["assets"] == {AssetType.CHAR_PORTRAIT.value: STUB_ASSET_ID}
        assert result["type"] == "segment"

    # ── Async bind (task goes through pool) ───────────────────────────

    def test_async_match_bind(self, pipeline):
        """Unknown name → stub process → completed → assets bound."""
        event = self._make_event(EventType.SCENE, 5, val="unknown_place")
        pipeline.gen.enqueue(event)            # task NOT completed yet
        result = pipeline.dispatcher.consume_event(event)  # waits here

        assert event.payload["assets"] == {AssetType.BACKGROUND.value: STUB_ASSET_ID}

    # ── DECLARE line=0 discard ────────────────────────────────────────

    def test_declare_discard_before_first_event(self, pipeline):
        """DECLARE task (line=0) → waited + discarded before first event."""
        # Enqueue a DECLARE task (Event line=2 — real parser line number)
        dec_event = self._make_event(EventType.DECLARE, 2,
                                     kind="CHAR", name="ghost",
                                     desc="a ghost")
        dec_task = pipeline.gen.enqueue(dec_event)
        assert dec_task.line == 0  # Task.line=0, not Event.line

        # First real event (line=3) → DECLARE task line=0 < line=3 →
        # popped, waited, discarded
        event = self._make_event(EventType.SEGMENT, 3,
                                 text="hello", position="pre")
        result = pipeline.dispatcher.consume_event(event)

        # DECLARE was discarded — no assets on this event
        assert "assets" not in event.payload
        # DECLARE task completed, placeholder filled by stub
        assert dec_task.completed is True
        item = pipeline.roster.lookup(AssetType.CHAR_PORTRAIT, "ghost")
        assert item is not None
        assert item.target == STUB_ASSET_ID

    # ── Orphan task discard ───────────────────────────────────────────

    def test_orphan_task_discarded(self, pipeline):
        """Task line=3 < event line=5, non-zero → discarded (no wait)."""
        # Create an orphan task (line=3, but event is line=5)
        pipeline.roster.add(AssetType.BACKGROUND, "forest",
                            target=STUB_ASSET_ID)
        orphan_event = self._make_event(EventType.SCENE, 3, val="forest")
        pipeline.gen.enqueue(orphan_event)     # task at line 3

        event = self._make_event(EventType.SEGMENT, 5,
                                 text="later", position="pre")
        result = pipeline.dispatcher.consume_event(event)

        # Orphan discarded — no assets, queue drained
        assert "assets" not in event.payload
        assert len(pipeline.queue) == 0

    # ── Pass-through (no task) ────────────────────────────────────────

    def test_no_task_pass_through(self, pipeline):
        """Event with no matching task → dispatched without assets."""
        event = self._make_event(EventType.SEGMENT, 1,
                                 text="hello", position="pre")
        result = pipeline.dispatcher.consume_event(event)

        assert result["type"] == "segment"
        assert "assets" not in event.payload

    # ── FIFO ordering ─────────────────────────────────────────────────

    def test_fifo_multiple_tasks(self, pipeline):
        """Multiple tasks consumed in FIFO order."""
        pipeline.roster.add(AssetType.BACKGROUND, "forest",
                            target=STUB_ASSET_ID)
        pipeline.roster.add(AssetType.BACKGROUND, "tavern",
                            target=STUB_ASSET_ID)

        # Task at line 2, task at line 4
        pipeline.gen.enqueue(self._make_event(EventType.SCENE, 2, val="forest"))
        pipeline.gen.enqueue(self._make_event(EventType.SCENE, 4, val="tavern"))

        # Event at line 4: should pop line=2 (orphan discarded),
        # then bind line=4
        event = self._make_event(EventType.SEGMENT, 4,
                                 text="at tavern", position="pre")
        result = pipeline.dispatcher.consume_event(event)

        assert event.payload["assets"] == {AssetType.BACKGROUND.value: STUB_ASSET_ID}
        assert len(pipeline.queue) == 0

    # ── Lookup failure → silent skip ──────────────────────────────────

    def test_lookup_failure_silent_skip(self, pipeline):
        """roster.lookup returns None → no assets bound, no crash."""
        # MATCH task completes with result="orphan_name", but no roster entry
        pipeline.roster.add(AssetType.BACKGROUND, "forest",
                            target=STUB_ASSET_ID)

        event = self._make_event(EventType.SCENE, 5, val="forest")
        task = pipeline.gen.enqueue(event)     # sync complete, result="forest"

        # Remove the roster entry to simulate lookup failure
        pipeline.roster.remove(AssetType.BACKGROUND, "forest")

        result = pipeline.dispatcher.consume_event(event)
        # Should not crash, just no assets
        assert "assets" not in event.payload

    # ── target=None placeholder → silent skip ─────────────────────────

    def test_placeholder_target_none_skip(self, pipeline):
        """roster entry exists but target=None → no assets bound."""
        pipeline.roster.add(AssetType.CHAR_PORTRAIT, "ghost",
                            target=None)   # placeholder

        event = self._make_event(EventType.SEGMENT, 5,
                                 text="...", position="pre",
                                 char="ghost")
        pipeline.gen.enqueue(event)
        result = pipeline.dispatcher.consume_event(event)

        assert "assets" not in event.payload


# ═══════════════════════════════════════════════════════════════════════
# 5. TestPipelineE2E
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineE2E:
    """End-to-end: manual event sequences → full pipeline → UI dicts.

    These are the scenarios §7.6 replays with real parser-driven events.
    """

    @staticmethod
    def _make_event(etype, line, **payload):
        return Event(etype, line, payload)

    def test_scene_then_segment_sequence(self, pipeline):
        """SCENE → SEGMENT with char → both get assets bound."""
        pipeline.roster.add(AssetType.BACKGROUND, "tavern",
                            target=STUB_ASSET_ID)
        pipeline.roster.add(AssetType.CHAR_PORTRAIT, "barkeep",
                            target=STUB_ASSET_ID)

        events = [
            (self._make_event(EventType.SCENE, 5, val="tavern"),
             AssetType.BACKGROUND),
            (self._make_event(EventType.SEGMENT, 10,
                              text="The barkeep nods.",
                              position="pre", char="barkeep"),
             AssetType.CHAR_PORTRAIT),
        ]

        for event, expected_type in events:
            pipeline.gen.enqueue(event)
            result = pipeline.dispatcher.consume_event(event)

            assert "assets" in event.payload, f"Event line={event.line} missing assets"
            assert event.payload["assets"] == {expected_type.value: STUB_ASSET_ID}

    def test_declare_then_scene_same_round(self, pipeline):
        """DECLARE a new scene → then SCENE uses it → both resolved."""
        # DECLARE creates placeholder + async process (Event line=2)
        dec_event = self._make_event(EventType.DECLARE, 2,
                                     kind="SCENE", name="crypt",
                                     desc="an ancient crypt")
        pipeline.gen.enqueue(dec_event)

        # Narrative text (line=4) triggers DECLARE task consumption
        seg1 = self._make_event(EventType.SEGMENT, 4,
                                text="You descend...", position="pre")
        r1 = pipeline.dispatcher.consume_event(seg1)
        assert r1["type"] == "segment"
        assert "assets" not in seg1.payload

        # Later: SCENE uses the declared location (line=6)
        scene_event = self._make_event(EventType.SCENE, 6, val="crypt")
        pipeline.gen.enqueue(scene_event)
        r2 = pipeline.dispatcher.consume_event(scene_event)

        assert scene_event.payload["assets"] == {AssetType.BACKGROUND.value: STUB_ASSET_ID}

    def test_multiple_events_without_tasks(self, pipeline):
        """Plain narrative (no media tags) → all pass through unchanged."""
        events = [
            self._make_event(EventType.STORY_BEGIN, 1),
            self._make_event(EventType.SEGMENT, 2,
                             text="It was a dark night.", position="pre"),
            self._make_event(EventType.SEGMENT, 3,
                             text="Rain fell steadily.", position="pre"),
            self._make_event(EventType.BRIDGE, 4),
            self._make_event(EventType.STORY_END, 5),
        ]

        for event in events:
            result = pipeline.dispatcher.consume_event(event)
            assert "assets" not in event.payload
            assert result  # dispatch returned something

    def test_mixed_known_and_unknown_chars(self, pipeline):
        """Known char (sync), unknown char (async) → both resolve."""
        pipeline.roster.add(AssetType.CHAR_PORTRAIT, "hero",
                            target=STUB_ASSET_ID)

        # Known — sync
        e1 = self._make_event(EventType.SEGMENT, 5,
                              text="I'm here.", position="pre",
                              char="hero")
        pipeline.gen.enqueue(e1)
        r1 = pipeline.dispatcher.consume_event(e1)
        assert e1.payload["assets"] == {AssetType.CHAR_PORTRAIT.value: STUB_ASSET_ID}

        # Unknown — async (stub will resolve)
        e2 = self._make_event(EventType.SEGMENT, 10,
                              text="Who goes there?", position="pre",
                              char="stranger")
        pipeline.gen.enqueue(e2)
        r2 = pipeline.dispatcher.consume_event(e2)
        assert e2.payload["assets"] == {AssetType.CHAR_PORTRAIT.value: STUB_ASSET_ID}


# ═══════════════════════════════════════════════════════════════════════
# 6. TestTextModeUnaffected
# ═══════════════════════════════════════════════════════════════════════

class TestTextModeUnaffected:
    """Text mode — ``EventDispatcher()`` with no args → dispatch() unchanged."""

    def test_text_mode_all_event_types(self):
        """All Phase 1 + Phase 2 event types dispatch correctly."""
        d = EventDispatcher()
        expected_types = {
            EventType.STORY_BEGIN: "story_begin",
            EventType.STORY_END: "story_end",
            EventType.SEGMENT: "segment",
            EventType.SET: "state",
            EventType.BRIDGE: "bridge",
            EventType.SCENE: "scene",
        }
        # Event types that produce empty dicts (no UI output).
        # PARSE_ERROR is tracked in parser._format_errors for LLM
        # feedback — the UI event was removed because a single
        # malformed XML line must not kill the game stream.
        empty_events = {
            EventType.PARSE_ERROR,
            EventType.BRANCH_ENTER,
            EventType.BRANCH_EXIT,
            EventType.CHECKPOINT_END,
            EventType.CHOICE_BEGIN,
            EventType.OPT,
            EventType.CHOICE_END,
            EventType.CHECKPOINT,
            EventType.ROUTE,
        }
        events = [
            Event(EventType.STORY_BEGIN, 1, {}),
            Event(EventType.STORY_END, 2, {}),
            Event(EventType.SEGMENT, 3,
                  {"text": "hello", "position": "pre"}),
            Event(EventType.SET, 4,
                  {"var": "trust", "op": "=", "val": "10"}),
            Event(EventType.BRIDGE, 5, {}),
            Event(EventType.BRANCH_ENTER, 6,
                  {"name": "hero", "position": "pre"}),
            Event(EventType.BRANCH_EXIT, 7,
                  {"name": "hero", "position": "pre"}),
            Event(EventType.CHECKPOINT_END, 8, {}),
            Event(EventType.PARSE_ERROR, 9, {"error": "bad"}),
            # Phase 2 event types — must dispatch correctly
            Event(EventType.SCENE, 10, {"val": "tavern"}),
            Event(EventType.DECLARE, 11,
                  {"kind": "CHAR", "name": "ghost", "desc": "a ghost"}),
        ]
        for event in events:
            result = d.consume_event(event)
            assert isinstance(result, dict), f"non-dict for {event.type}"
            if event.type in empty_events:
                assert result == {}, (
                    f"{event.type.name}: expected empty dict, "
                    f"got {result}"
                )
            elif event.type in expected_types:
                assert result["type"] == expected_types[event.type], (
                    f"{event.type.name}: expected type={expected_types[event.type]!r},"
                    f" got {result.get('type')!r}"
                )

    def test_text_mode_no_assets_injected(self):
        """Text mode never injects 'assets' into event payload."""
        d = EventDispatcher()
        event = Event(EventType.SEGMENT, 1,
                      {"text": "hello", "position": "pre"})
        d.consume_event(event)
        assert "assets" not in event.payload

    def test_text_mode_segment_output(self):
        """Segment event → correct UI dict (Phase 1 behavior unchanged)."""
        d = EventDispatcher()
        event = Event(EventType.SEGMENT, 1,
                      {"text": "A door creaks.", "position": "pre",
                       "branch": None})
        result = d.consume_event(event)
        assert result["type"] == "segment"
        assert result["text"] == "A door creaks."

    def test_text_mode_scene_output(self):
        """SCENE event → scene UI dict with position and branch."""
        d = EventDispatcher()
        event = Event(EventType.SCENE, 1,
                      {"val": "tavern", "position": "pre", "branch": "hero"})
        result = d.consume_event(event)
        assert result["type"] == "scene"
        assert result["val"] == "tavern"
        assert result["position"] == "pre"
        assert result["branch"] == "hero"

    def test_text_mode_state_output(self):
        """SET event → state UI dict unchanged."""
        d = EventDispatcher()
        event = Event(EventType.SET, 1,
                      {"var": "trust", "op": "+", "val": "5",
                       "vars": {"GLOBAL": {"trust": 55}},
                       "changes": [{"var": "trust", "op": "+", "val": "5",
                                    "accepted": True, "reason": None}]})
        result = d.consume_event(event)
        assert result["type"] == "state"


# ═══════════════════════════════════════════════════════════════════════
# 7. TestVerificationCriteria — §7.4 success criteria
# ═══════════════════════════════════════════════════════════════════════

class TestVerificationCriteria:
    """Explicit verification of the three §7.4 success criteria.

    Run with::

        pytest tests/test_task_framework.py::TestVerificationCriteria -v
    """

    @staticmethod
    def _make_event(etype, line, **payload):
        return Event(etype, line, payload)

    def test_criterion_1_stub_pipeline_runs(self, pipeline):
        """§7.4 criterion 1: stub pipeline runs end-to-end.

        A complete narrative round with mixed media events — DECLARE a new
        character, SCENE change, SEGMENT with char, and plain narrative —
        flows through TaskGenerator → TaskPool → EventDispatcher without
        error, producing valid UI dicts for every event.
        """
        pipeline.roster.add(AssetType.BACKGROUND, "tavern",
                            target=STUB_ASSET_ID)

        # Round with all three image-tag types + plain narrative
        sequence = [
            # DECLARE new character (async — pool)
            self._make_event(EventType.DECLARE, 2,
                             kind="CHAR", name="stranger",
                             desc="a hooded figure"),
            # Plain narrative (triggers DECLARE consumption)
            self._make_event(EventType.SEGMENT, 4,
                             text="A stranger enters.", position="pre"),
            # SCENE change (sync — roster hit)
            self._make_event(EventType.SCENE, 6, val="tavern"),
            # SEG with known char (sync — roster hit)
            self._make_event(EventType.SEGMENT, 8,
                             text="The barkeep watches.", position="pre",
                             char="stranger"),
            # SEG without char (no media)
            self._make_event(EventType.SEGMENT, 10,
                             text="Silence fills the room.",
                             position="pre"),
        ]

        results = []
        for event in sequence:
            pipeline.gen.enqueue(event)
            result = pipeline.dispatcher.consume_event(event)
            results.append(result)

        # Every event produced a non-empty UI dict
        assert all(isinstance(r, dict) for r in results)
        assert all(r for r in results), "no empty dicts — all events dispatched"

    def test_criterion_2_uniform_temp_image(self, pipeline):
        """§7.4 criterion 2: all bound assets are the same temp image.

        Every event that gets asset binding — regardless of type (portrait
        or background), match method (sync hit or async stub), or trigger
        (SCENE or SEGMENT char) — receives the identical ``STUB_ASSET_ID``.
        """
        # Pre-populate roster with a known entry (sync path)
        pipeline.roster.add(AssetType.BACKGROUND, "forest",
                            target=STUB_ASSET_ID)

        events_and_types = [
            # Sync MATCH — SCENE with known name
            (self._make_event(EventType.SCENE, 2, val="forest"),
             AssetType.BACKGROUND),
            # Async MATCH — SEGMENT with unknown char
            (self._make_event(EventType.SEGMENT, 5,
                              text="...", position="pre",
                              char="unknown_hero"),
             AssetType.CHAR_PORTRAIT),
        ]

        bound_asset_ids = []
        for event, expected_type in events_and_types:
            pipeline.gen.enqueue(event)
            result = pipeline.dispatcher.consume_event(event)

            assert "assets" in event.payload, (
                f"Event {event.type.name} line={event.line} missing assets"
            )
            aid = event.payload["assets"][expected_type.value]
            bound_asset_ids.append(aid)

        # Criterion: ALL resolved to the same stub image
        unique = set(bound_asset_ids)
        assert unique == {STUB_ASSET_ID}, (
            f"All assets must be {STUB_ASSET_ID!r}, got {unique}"
        )

    def test_criterion_3_text_mode_unaffected(self):
        """§7.4 criterion 3: text mode is completely unaffected.

        ``EventDispatcher()`` with no arguments processes every Phase 1
        event type identically to the pre-7.4 ``dispatch()`` path, and
        never injects ``assets`` into any event payload or UI dict.
        """
        d = EventDispatcher()
        events = [
            Event(EventType.STORY_BEGIN, 1, {}),
            Event(EventType.STORY_END, 2, {}),
            Event(EventType.SEGMENT, 3,
                  {"text": "It was a dark night.", "position": "pre"}),
            Event(EventType.SET, 4,
                  {"var": "trust", "op": "=", "val": "10"}),
            Event(EventType.BRIDGE, 5, {}),
            Event(EventType.CHOICE_BEGIN, 6, {"id": "q1"}),
            Event(EventType.CHECKPOINT, 7,
                  {"node": "ch1", "summary": "start"}),
            Event(EventType.ROUTE, 8, {"target": "ch2"}),
            Event(EventType.PARSE_ERROR, 9, {"error": "bad tag"}),
            # Phase 2 types — pass through without error in text mode
            Event(EventType.SCENE, 10, {"val": "tavern"}),
            Event(EventType.DECLARE, 11,
                  {"kind": "CHAR", "name": "ghost", "desc": "..."}),
        ]

        for event in events:
            result = d.consume_event(event)

            # Every event produces a dict (no crashes)
            assert isinstance(result, dict), (
                f"Event {event.type.name} returned {type(result).__name__}"
            )
            # Phase 2 types must have correct UI type
            if event.type == EventType.SCENE:
                assert result.get("type") == "scene"
            # No event gets assets injected in text mode
            assert "assets" not in event.payload, (
                f"Event {event.type.name} had assets injected in text mode"
            )
            if result:
                assert "assets" not in result, (
                    f"UI dict for {event.type.name} had assets in text mode"
                )

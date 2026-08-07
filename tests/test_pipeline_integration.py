"""§7.6 pipeline integration — real XML → full graph pipeline E2E.

Feeds XML through: StreamParser → StateManager → EventDispatcher,
with TaskGenerator triggered by Parser for image events.
Verifies that assets are bound to the correct UI dicts.

Reuses stub helpers from test_task_framework.py — all assets resolve
to ``__stub__`` (§7.8 replaces with real LLM / image generation).
"""

import time
from collections import deque

import pytest

from storyloom.assets import Asset, AssetItem, AssetLibrary, AssetType, GameAssetRoster
from storyloom.core.event_dispatcher import EventDispatcher
from storyloom.core.game_loop import GameState
from storyloom.core.state_manager import StateManager
from storyloom.parser.stream_parser import Event, EventType, StreamParser
from storyloom.tasks import Task, TaskGenerator, TaskPool, TaskType


# ═══════════════════════════════════════════════════════════════════════
# Stub helpers (mirror test_task_framework.py — deleted in §7.8)
# ═══════════════════════════════════════════════════════════════════════

STUB_DELAY = 0.01
STUB_ASSET_ID = "__stub__"
STUB_LOCAL_NAME = "stub"  # pre-populated roster key for all matches


def stub_process_factory(asset_type: AssetType, local_name: str,
                         roster: GameAssetRoster):
    """Return a Task.process closure.  MATCH → result='stub' (always
    resolves to pre-populated roster entry); GENERATE → fill placeholder
    with STUB_ASSET_ID."""
    def _process(task: Task) -> None:
        time.sleep(STUB_DELAY)
        if task.task_type is TaskType.MATCH:
            task.result = STUB_LOCAL_NAME
        else:
            roster.set_target(asset_type, local_name, STUB_ASSET_ID)
    return _process


def bootstrap_roster(roster: GameAssetRoster, library: AssetLibrary) -> None:
    """Pre-populate roster with one STUB_LOCAL_NAME entry per AssetType.
    Provides known targets for sync-match and async-match tests."""
    for atype in AssetType:
        if library.get(atype, STUB_ASSET_ID) is None:
            library.add(atype, STUB_LOCAL_NAME, "temp", asset_id=STUB_ASSET_ID)
        if roster.lookup(atype, STUB_LOCAL_NAME) is None:
            roster.add(atype, STUB_LOCAL_NAME, "temp", target=STUB_ASSET_ID)


# ═══════════════════════════════════════════════════════════════════════
# Pipeline fixture — mirrors stream_round() graph-mode assembly
# ═══════════════════════════════════════════════════════════════════════

class GraphPipeline:
    """Complete graph-mode pipeline: parser → state_mgr → dispatcher,
    with TaskGenerator triggered by parser for image events."""

    def __init__(self, tmp_path: str):
        import tempfile
        self._tmp = tempfile.mkdtemp(dir=tmp_path)
        self.library = AssetLibrary(self._tmp)
        self.roster = GameAssetRoster("test_game", self.library)
        bootstrap_roster(self.roster, self.library)

        self.task_queue: deque[Task] = deque()
        self.task_pool = TaskPool(max_workers=2)
        self.task_gen = TaskGenerator(
            self.task_queue, self.roster,
            process_factory=stub_process_factory,
            task_pool=self.task_pool,
        )

    def feed_xml(self, xml_text: str) -> list[dict]:
        """Feed multi-line XML through the full pipeline.  Returns UI dicts."""
        parser = StreamParser(task_gen=self.task_gen)
        state_mgr = StateManager(GameState([]))
        dispatcher = EventDispatcher(self.task_queue, self.roster)

        results: list[dict] = []
        for line in xml_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            for event in parser.feed_line(line):
                for processed in state_mgr.process(event):
                    # CHOICE_END pause — not tested here
                    if state_mgr.needs_input:
                        state_mgr.needs_input = False
                        continue
                    ui = dispatcher.consume_event(processed)
                    if ui:
                        results.append(ui)

        # Checkpoint processing
        for cp_evt in state_mgr.process_checkpoint():
            pass  # save events not relevant

        return results

    def shutdown(self):
        self.task_pool.shutdown()


@pytest.fixture
def pipeline(tmp_path):
    """Fresh graph pipeline for each test."""
    p = GraphPipeline(str(tmp_path))
    yield p
    p.shutdown()


# ═══════════════════════════════════════════════════════════════════════
# 1. DECLARE + SEG same round
# ═══════════════════════════════════════════════════════════════════════

class TestDeclareThenSeg:
    """DECLARE creates placeholder → SEG with same char → asset bound."""

    XML = (
        "001| <story>\n"
        '002| <declare kind="CHAR" name="ghost">a ghost</declare>\n'
        '003| <seg char="ghost">Boo!</seg>\n'
        "004| </story>"
    )

    def test_seg_has_asset_bound(self, pipeline):
        results = pipeline.feed_xml(self.XML)
        segs = [r for r in results if r["type"] == "segment"]
        assert len(segs) == 1
        assert "assets" in segs[0]
        assert segs[0]["assets"] == {AssetType.CHAR_PORTRAIT.value: STUB_ASSET_ID}

    def test_declare_not_in_results(self, pipeline):
        """DECLARE never reaches UI (consumed by TaskGen)."""
        results = pipeline.feed_xml(self.XML)
        types = {r["type"] for r in results}
        assert "declare" not in types

    def test_placeholder_filled(self, pipeline):
        """After pipeline, roster entry has real target (not None)."""
        pipeline.feed_xml(self.XML)
        item = pipeline.roster.lookup(AssetType.CHAR_PORTRAIT, "ghost")
        assert item is not None
        assert item.target == STUB_ASSET_ID


# ═══════════════════════════════════════════════════════════════════════
# 2. SCENE known match (sync)
# ═══════════════════════════════════════════════════════════════════════

class TestSceneKnownMatch:
    """SCENE val='stub' → roster hit → sync MATCH → asset bound."""

    XML = (
        "001| <story>\n"
        '002| <set var="SCENE" val="stub"/>\n'
        "003| </story>"
    )

    def test_scene_has_asset_bound(self, pipeline):
        results = pipeline.feed_xml(self.XML)
        scenes = [r for r in results if r["type"] == "scene"]
        assert len(scenes) == 1
        assert "assets" in scenes[0]
        assert scenes[0]["assets"] == {AssetType.BACKGROUND.value: STUB_ASSET_ID}


# ═══════════════════════════════════════════════════════════════════════
# 3. SEG char unknown (async stub)
# ═══════════════════════════════════════════════════════════════════════

class TestSegCharUnknown:
    """SEG with unknown char → async MATCH (stub) → asset bound."""

    XML = (
        "001| <story>\n"
        '002| <seg char="stranger">Who goes there?</seg>\n'
        "003| </story>"
    )

    def test_unknown_char_async_resolves(self, pipeline):
        results = pipeline.feed_xml(self.XML)
        segs = [r for r in results if r["type"] == "segment"]
        assert len(segs) == 1
        assert "assets" in segs[0]
        assert segs[0]["assets"] == {AssetType.CHAR_PORTRAIT.value: STUB_ASSET_ID}


# ═══════════════════════════════════════════════════════════════════════
# 4. Text mode — no task subsystem
# ═══════════════════════════════════════════════════════════════════════

class TestTextModeNoTasks:
    """Text mode pipeline (no TaskGen) — no assets, no tasks created."""

    XML = (
        "001| <story>\n"
        '002| <declare kind="CHAR" name="ghost">a ghost</declare>\n'
        '003| <set var="SCENE" val="tavern"/>\n'
        '004| <seg char="ghost">Boo!</seg>\n'
        "005| </story>"
    )

    @staticmethod
    def _feed_text_mode(xml_text: str) -> list[dict]:
        parser = StreamParser(task_gen=None)
        state_mgr = StateManager(GameState([]))
        dispatcher = EventDispatcher()  # text mode — no queue

        results = []
        for line in xml_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            for event in parser.feed_line(line):
                for processed in state_mgr.process(event):
                    ui = dispatcher.consume_event(processed)
                    if ui:
                        results.append(ui)
        return results

    def test_no_assets_in_any_event(self):
        results = self._feed_text_mode(self.XML)
        for r in results:
            assert "assets" not in r, (
                f"Event type={r['type']} should not have assets in text mode"
            )

    def test_declare_silently_dropped(self):
        """DECLARE not in results — parser drops it when task_gen is None."""
        results = self._feed_text_mode(self.XML)
        types = {r["type"] for r in results}
        assert "declare" not in types

    def test_story_begin_and_end_present(self):
        results = self._feed_text_mode(self.XML)
        types = {r["type"] for r in results}
        assert "story_begin" in types
        assert "story_end" in types


# ═══════════════════════════════════════════════════════════════════════
# 5. Mixed full-round sequence
# ═══════════════════════════════════════════════════════════════════════

class TestMixedSequence:
    """DECLARE → SEG → SCENE → SEG(char) → BRIDGE → SEG → STORY_END."""

    XML = (
        "001| <story>\n"
        '002| <set var="SCENE" val="stub"/>\n'
        '003| <seg>The tavern is quiet.</seg>\n'
        '004| <declare kind="CHAR" name="stranger">hooded</declare>\n'
        '005| <seg char="stranger">Evening.</seg>\n'
        "006| <bridge/>\n"
        '007| <seg>The stranger nods.</seg>\n'
        "008| </story>"
    )

    def test_all_events_dispatched(self, pipeline):
        results = pipeline.feed_xml(self.XML)
        types = {r["type"] for r in results}
        assert "story_begin" in types
        assert "scene" in types       # SCENE at line 2
        assert "segment" in types     # narration + dialogue
        assert "bridge" in types
        assert "story_end" in types

    def test_scene_has_background_asset(self, pipeline):
        results = pipeline.feed_xml(self.XML)
        scenes = [r for r in results if r["type"] == "scene"]
        assert len(scenes) >= 1
        assert scenes[0]["assets"] == {AssetType.BACKGROUND.value: STUB_ASSET_ID}

    def test_char_seg_has_portrait_asset(self, pipeline):
        results = pipeline.feed_xml(self.XML)
        char_segs = [r for r in results
                     if r["type"] == "segment" and "char" in r]
        assert len(char_segs) >= 1
        assert char_segs[0]["assets"] == {AssetType.CHAR_PORTRAIT.value: STUB_ASSET_ID}

    def test_narration_seg_no_assets(self, pipeline):
        """Narration segs (no char attr) have no assets."""
        results = pipeline.feed_xml(self.XML)
        bare_segs = [r for r in results
                     if r["type"] == "segment" and "char" not in r]
        assert len(bare_segs) >= 1
        for seg in bare_segs:
            assert "assets" not in seg

    def test_declare_not_in_results(self, pipeline):
        results = pipeline.feed_xml(self.XML)
        types = {r["type"] for r in results}
        assert "declare" not in types


# ═══════════════════════════════════════════════════════════════════════
# 6. Replay §7.4 scenarios with real XML
# ═══════════════════════════════════════════════════════════════════════

class TestReplay74Scenarios:
    """Replay the six §7.4 manual-event scenarios with real XML."""

    def test_scene_then_segment_sequence(self, pipeline):
        """SCENE → SEG(char) → both bound."""
        xml = (
            "001| <story>\n"
            '002| <set var="SCENE" val="stub"/>\n'
            '003| <seg char="stub">The barkeep nods.</seg>\n'
            "004| </story>"
        )
        results = pipeline.feed_xml(xml)
        scene = next(r for r in results if r["type"] == "scene")
        seg = next(r for r in results if r["type"] == "segment" and "char" in r)
        assert scene["assets"] == {AssetType.BACKGROUND.value: STUB_ASSET_ID}
        assert seg["assets"] == {AssetType.CHAR_PORTRAIT.value: STUB_ASSET_ID}

    def test_declare_then_scene_same_round(self, pipeline):
        """DECLARE crypt → SCENE val='crypt' → both resolve."""
        xml = (
            "001| <story>\n"
            '002| <declare kind="SCENE" name="crypt">ancient crypt</declare>\n'
            '003| <seg>You descend into darkness.</seg>\n'
            '004| <set var="SCENE" val="crypt"/>\n'
            "005| </story>"
        )
        results = pipeline.feed_xml(xml)
        scenes = [r for r in results if r["type"] == "scene"]
        assert len(scenes) == 1
        assert scenes[0]["assets"] == {AssetType.BACKGROUND.value: STUB_ASSET_ID}

    def test_multiple_events_without_tasks(self, pipeline):
        """Plain narrative — no media tags — all pass through."""
        xml = (
            "001| <story>\n"
            "002| <seg>It was a dark night.</seg>\n"
            "003| <seg>Rain fell steadily.</seg>\n"
            "004| <bridge/>\n"
            "005| </story>"
        )
        results = pipeline.feed_xml(xml)
        # No assets on any event
        for r in results:
            assert "assets" not in r

    def test_mixed_known_and_unknown_chars(self, pipeline):
        """Known char (sync hit) + unknown char (async stub) → both bound."""
        xml = (
            "001| <story>\n"
            '002| <seg char="stub">I am known.</seg>\n'
            '003| <seg char="newcomer">I am new.</seg>\n'
            "004| </story>"
        )
        results = pipeline.feed_xml(xml)
        char_segs = [r for r in results
                     if r["type"] == "segment" and "char" in r]
        assert len(char_segs) == 2
        for seg in char_segs:
            assert seg["assets"] == {AssetType.CHAR_PORTRAIT.value: STUB_ASSET_ID}


# ═══════════════════════════════════════════════════════════════════════
# 7. Edge cases
# ═══════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Boundary conditions for the integrated pipeline."""

    def test_declare_empty_name_no_crash(self, pipeline):
        """DECLARE with name='' → sync-complete no-op, no crash."""
        xml = (
            "001| <story>\n"
            '002| <declare kind="CHAR" name="">forgotten</declare>\n'
            '003| <seg>Nothing happens.</seg>\n'
            "004| </story>"
        )
        results = pipeline.feed_xml(xml)
        assert len(results) >= 2  # story_begin + seg + story_end

    def test_empty_story(self, pipeline):
        """Empty <story> — still processes correctly."""
        xml = "001| <story>\n002| </story>"
        results = pipeline.feed_xml(xml)
        types = {r["type"] for r in results}
        assert "story_begin" in types
        assert "story_end" in types

    def test_multiple_scenes_sequential(self, pipeline):
        """Multiple SCENE tags — each gets own MATCH task."""
        xml = (
            "001| <story>\n"
            '002| <set var="SCENE" val="stub"/>\n'
            '003| <set var="SCENE" val="stub"/>\n'
            "004| </story>"
        )
        results = pipeline.feed_xml(xml)
        scenes = [r for r in results if r["type"] == "scene"]
        assert len(scenes) == 2
        for s in scenes:
            assert s["assets"] == {AssetType.BACKGROUND.value: STUB_ASSET_ID}

    def test_declare_multiple_characters(self, pipeline):
        """Multiple DECLARE → all placeholders created and filled."""
        xml = (
            "001| <story>\n"
            '002| <declare kind="CHAR" name="alice">first</declare>\n'
            '003| <declare kind="CHAR" name="bob">second</declare>\n'
            '004| <seg char="alice">Hello</seg>\n'
            '005| <seg char="bob">Hi</seg>\n'
            "006| </story>"
        )
        results = pipeline.feed_xml(xml)
        char_segs = [r for r in results
                     if r["type"] == "segment" and "char" in r]
        assert len(char_segs) == 2
        for seg in char_segs:
            assert "assets" in seg

        # Both roster entries filled
        assert pipeline.roster.lookup(AssetType.CHAR_PORTRAIT, "alice").target == STUB_ASSET_ID
        assert pipeline.roster.lookup(AssetType.CHAR_PORTRAIT, "bob").target == STUB_ASSET_ID


# ═══════════════════════════════════════════════════════════════════════
# 8. Verification criteria (§7.6)
# ═══════════════════════════════════════════════════════════════════════

class TestVerificationCriteria:
    """Explicit verification of §7.6 success criteria."""

    XML_FULL_ROUND = (
        "001| <story>\n"
        '002| <set var="SCENE" val="stub"/>\n'
        '003| <declare kind="CHAR" name="mage">a wizard</declare>\n'
        '004| <seg>The tower looms.</seg>\n'
        '005| <seg char="mage">Welcome, traveler.</seg>\n'
        "006| <bridge/>\n"
        '007| <seg>The mage gestures inside.</seg>\n'
        "008| </story>"
    )

    def test_criterion_1_stub_pipeline_e2e(self, pipeline):
        """§7.6 criterion 1: stub pipeline + real events run end-to-end.

        A complete round with SCENE (sync), DECLARE (async), SEG(char)
        (async), narration, and bridge — flows through the full pipeline
        without error, producing valid UI dicts for every event.
        """
        results = pipeline.feed_xml(self.XML_FULL_ROUND)
        assert len(results) >= 5  # story_begin, scene, 2 segs, bridge, story_end
        assert all(isinstance(r, dict) for r in results)
        assert all(r for r in results)

    def test_criterion_2_uniform_stub_assets(self, pipeline):
        """§7.6 criterion 2: all bound assets are STUB_ASSET_ID.

        Every event that gets asset binding — regardless of type
        (portrait/background) or match method (sync/async) — receives
        the identical ``__stub__`` asset ID.
        """
        results = pipeline.feed_xml(self.XML_FULL_ROUND)
        bound_ids = set()
        for r in results:
            assets = r.get("assets", {})
            for aid in assets.values():
                bound_ids.add(aid)
        assert bound_ids == {STUB_ASSET_ID}

    def test_criterion_3_text_mode_unaffected(self, pipeline):
        """§7.6 criterion 3: text mode is unaffected.

        Same XML through text-mode pipeline — no assets injected,
        story events still produced correctly.
        """
        results = TestTextModeNoTasks._feed_text_mode(self.XML_FULL_ROUND)
        for r in results:
            assert "assets" not in r
        types = {r["type"] for r in results}
        assert "story_begin" in types
        assert "segment" in types
        assert "bridge" in types
        assert "story_end" in types

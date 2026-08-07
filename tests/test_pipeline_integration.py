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
                    if state_mgr.needs_input:
                        # Auto-resolve choice with key="1" (matches
                        # stream_round() gen.send(key) pattern).
                        results.append(
                            dispatcher.dispatch_choice(state_mgr.choice_data)
                        )
                        for evt in state_mgr.apply_choice("1"):
                            ui = dispatcher.dispatch(evt)
                            if ui:
                                results.append(ui)
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
                    if state_mgr.needs_input:
                        state_mgr.apply_choice("1")
                        continue
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


# ═══════════════════════════════════════════════════════════════════════
# 9. Prompt-driven E2E — Example 1 (The Drop) through full graph pipeline
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def example1_xml():
    """Extract Example 1 XML from the graph-mode prompt (same as §7.5)."""
    # Duplicate the extractor here to keep this file self-contained.
    # test_graph_mode_pipeline.py owns the canonical extractor.
    from storyloom.core.prompt_builder import GRAPH_ROUND1_PREFIX

    marker = "## Example 1"
    idx = GRAPH_ROUND1_PREFIX.find(marker)
    assert idx != -1, "Example 1 not found in prompt"

    rest = GRAPH_ROUND1_PREFIX[idx:]
    lines = rest.split("\n")
    xml_lines = []
    in_example = False
    for line in lines:
        if line.startswith("001| "):
            in_example = True
        if in_example:
            xml_lines.append(line)
            if line.strip().startswith("0") and "</story>" in line:
                break
    return "\n".join(xml_lines)


class TestExample1FullGraphPipeline:
    """Example 1 (The Drop) — full graph pipeline with assets."""

    @pytest.fixture(autouse=True)
    def run_pipeline(self, pipeline, example1_xml):
        self.results = pipeline.feed_xml(example1_xml)

    # ── No errors ──────────────────────────────────────────────────

    def test_no_parse_errors(self):
        errors = [r for r in self.results if r["type"] == "error"]
        assert errors == [], (
            f"Unexpected errors: {[e.get('message') for e in errors]}"
        )

    def test_declare_not_in_results(self):
        types = {r["type"] for r in self.results}
        assert "declare" not in types

    # ── Event type coverage ────────────────────────────────────────

    def test_required_event_types_present(self):
        types = {r["type"] for r in self.results}
        assert "story_begin" in types
        assert "story_end" in types
        assert "scene" in types
        assert "segment" in types
        assert "bridge" in types

    # ── SCENE → BACKGROUND asset ───────────────────────────────────

    def test_scene_has_background_asset(self):
        scenes = [r for r in self.results if r["type"] == "scene"]
        assert len(scenes) >= 1, "Expected at least one SCENE event"
        for s in scenes:
            assert "assets" in s, f"SCENE missing assets: {s}"
            assert s["assets"] == {AssetType.BACKGROUND.value: STUB_ASSET_ID}
            assert "val" in s  # scene name preserved

    def test_scene_val_is_grand_hotel_lobby(self):
        scenes = [r for r in self.results if r["type"] == "scene"]
        assert any(s.get("val") == "grand_hotel_lobby" for s in scenes)

    # ── SEG with char → CHAR_PORTRAIT asset ────────────────────────

    def test_char_segs_have_portrait_asset(self):
        char_segs = [r for r in self.results
                     if r["type"] == "segment" and "char" in r]
        assert len(char_segs) >= 1, "Expected at least one <seg char='...'>"
        for seg in char_segs:
            assert "assets" in seg, (
                f"SEG(char={seg.get('char')}) missing assets"
            )
            assert seg["assets"] == {AssetType.CHAR_PORTRAIT.value: STUB_ASSET_ID}

    def test_char_seg_names_preserved(self):
        char_segs = [r for r in self.results
                     if r["type"] == "segment" and "char" in r]
        names = {s["char"] for s in char_segs}
        assert "Alex" in names
        assert "Mira" in names
        assert "agent" in names

    def test_expression_variants_preserved(self):
        """char='Mira.angry', char='Alex.sad' — expression suffixes kept."""
        char_segs = [r for r in self.results
                     if r["type"] == "segment" and "char" in r]
        chars_with_expr = {s["char"] for s in char_segs if "." in s.get("char", "")}
        assert "Mira.angry" in chars_with_expr
        assert "Alex.sad" in chars_with_expr

    # ── Narration SEG → no assets ──────────────────────────────────

    def test_narration_segs_have_no_assets(self):
        bare_segs = [r for r in self.results
                     if r["type"] == "segment" and "char" not in r]
        assert len(bare_segs) >= 1, "Expected narration segs without char"
        for seg in bare_segs:
            assert "assets" not in seg, (
                f"Narration SEG should not have assets: text={seg.get('text', '')[:40]}"
            )

    # ── Position tracking ──────────────────────────────────────────

    def test_pre_and_post_bridge_segs(self):
        bridge_idx = next(
            i for i, r in enumerate(self.results) if r["type"] == "bridge"
        )
        pre_segs = [r for r in self.results[:bridge_idx]
                    if r["type"] == "segment"]
        post_segs = [r for r in self.results[bridge_idx + 1:]
                     if r["type"] == "segment"]
        assert all(r["position"] == "pre" for r in pre_segs)
        assert all(r["position"] == "post" for r in post_segs)

    # ── All assets are STUB_ASSET_ID ───────────────────────────────

    def test_all_assets_are_stub(self):
        bound_ids = set()
        for r in self.results:
            for aid in r.get("assets", {}).values():
                bound_ids.add(aid)
        assert bound_ids == {STUB_ASSET_ID} if bound_ids else True


# ═══════════════════════════════════════════════════════════════════════
# 10. Prompt-driven E2E — Example 2 (The Last Archive) through full graph pipeline
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def example2_xml():
    """Extract Example 2 XML from the graph-mode prompt."""
    from storyloom.core.prompt_builder import GRAPH_ROUND1_PREFIX

    marker = "## Example 2"
    idx = GRAPH_ROUND1_PREFIX.find(marker)
    assert idx != -1, "Example 2 not found in prompt"

    rest = GRAPH_ROUND1_PREFIX[idx:]
    lines = rest.split("\n")
    xml_lines = []
    in_example = False
    for line in lines:
        if line.startswith("001| "):
            in_example = True
        if in_example:
            xml_lines.append(line)
            if line.strip().startswith("0") and "</story>" in line:
                break
    return "\n".join(xml_lines)


class TestExample2FullGraphPipeline:
    """Example 2 (The Last Archive) — has SEG(char) but no SCENE/DECLARE."""

    @pytest.fixture(autouse=True)
    def run_pipeline(self, pipeline, example2_xml):
        self.results = pipeline.feed_xml(example2_xml)

    def test_no_parse_errors(self):
        errors = [r for r in self.results if r["type"] == "error"]
        assert errors == []

    def test_no_scene_events(self):
        """Example 2 intentionally excludes SCENE tags."""
        scenes = [r for r in self.results if r["type"] == "scene"]
        assert scenes == []

    def test_char_segs_have_portrait_asset(self):
        """Example 2 has SEG(char='Yara', 'Kai', ...) → portrait assets."""
        char_segs = [r for r in self.results
                     if r["type"] == "segment" and "char" in r]
        assert len(char_segs) >= 1, "Expected <seg char='...'> in Example 2"
        for seg in char_segs:
            assert "assets" in seg, (
                f"SEG(char={seg.get('char')}) missing assets"
            )
            assert seg["assets"] == {AssetType.CHAR_PORTRAIT.value: STUB_ASSET_ID}

    def test_narration_segs_have_no_assets(self):
        """Narration (no char) → no assets."""
        bare_segs = [r for r in self.results
                     if r["type"] == "segment" and "char" not in r]
        assert len(bare_segs) >= 1
        for seg in bare_segs:
            assert "assets" not in seg

    def test_declare_not_in_results(self):
        types = {r["type"] for r in self.results}
        assert "declare" not in types

    def test_required_event_types_present(self):
        types = {r["type"] for r in self.results}
        assert "story_begin" in types
        assert "story_end" in types
        assert "segment" in types
        assert "bridge" in types

    def test_all_background_assets_only_in_scene(self):
        """No SCENE events → no BACKGROUND assets anywhere."""
        for r in self.results:
            assets = r.get("assets", {})
            assert AssetType.BACKGROUND.value not in assets, (
                f"Event type={r['type']} should not have BACKGROUND asset"
            )

    def test_char_names_preserved(self):
        char_segs = [r for r in self.results
                     if r["type"] == "segment" and "char" in r]
        names = {s["char"] for s in char_segs}
        assert "Yara" in names
        assert "Kai" in names

    def test_expression_variants_branch_filtered(self):
        """Yara.angry/Kai.smile are in branch='expose' — filtered by auto-choice
        key='1' selecting branch='ally'.  Only basic char names appear."""
        char_segs = [r for r in self.results
                     if r["type"] == "segment" and "char" in r]
        chars = {s["char"] for s in char_segs}
        # ally branch: basic names only
        assert "Yara" in chars
        assert "Kai" in chars
        # expose branch (filtered): expression variants absent
        assert "Yara.angry" not in chars
        assert "Kai.smile" not in chars

    def test_pre_and_post_bridge_segs(self):
        bridge_idx = next(
            i for i, r in enumerate(self.results) if r["type"] == "bridge"
        )
        pre_segs = [r for r in self.results[:bridge_idx]
                    if r["type"] == "segment"]
        post_segs = [r for r in self.results[bridge_idx + 1:]
                     if r["type"] == "segment"]
        assert all(r["position"] == "pre" for r in pre_segs)
        assert all(r["position"] == "post" for r in post_segs)

    def test_all_assets_are_stub(self):
        bound_ids = set()
        for r in self.results:
            for aid in r.get("assets", {}).values():
                bound_ids.add(aid)
        assert bound_ids.issubset({STUB_ASSET_ID})

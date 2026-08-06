"""End-to-end pipeline tests for graph-mode Prompt examples.

Per design.md §7.5 verification: LLM output (Prompt examples) is correctly
parsed into DECLARE / SCENE / SEG events without affecting text mode.

Feeds Example 1 and Example 2 XML through:
    StreamParser → StateManager → EventDispatcher
"""

import pytest
from storyloom.parser.stream_parser import Event, EventType, StreamParser
from storyloom.core.state_manager import StateManager
from storyloom.core.event_dispatcher import EventDispatcher
from storyloom.core.game_loop import GameState
from storyloom.core.prompt_builder import GRAPH_ROUND1_PREFIX


# ── Extract example XML from the graph-mode Prompt ──────────────────

def _extract_example_xml(example_num: int) -> str:
    """Extract the complete XML block for one example from the prompt.

    The prompt contains ``NNN| <tag>...</tag>`` lines.  Returns the
    raw text (with ``NNN| `` prefix) ready for StreamParser input.
    """
    marker = f"## Example {example_num}"
    idx = GRAPH_ROUND1_PREFIX.find(marker)
    assert idx != -1, f"Example {example_num} not found in prompt"

    # Find the first NNN| line after the marker
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


# ── Helpers ─────────────────────────────────────────────────────────

def _feed_xml(parser: StreamParser, xml_text: str) -> list[Event]:
    """Feed multi-line XML through the parser, return all events."""
    events: list[Event] = []
    for line in xml_text.split("\n"):
        line = line.strip()
        if line:
            events.extend(parser.feed_line(line))
    return events


def _event_types(events: list[Event]) -> list[str]:
    """Return event type names for assertion messages."""
    return [e.type.name for e in events]


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def empty_gs():
    return GameState([])


@pytest.fixture
def sm(empty_gs):
    return StateManager(empty_gs)


@pytest.fixture
def dispatcher():
    return EventDispatcher()


# ── Example 1: The Drop ─────────────────────────────────────────────

class TestExample1Pipeline:
    """End-to-end: Example 1 (The Drop) through full pipeline."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.xml = _extract_example_xml(1)

    def test_no_parse_errors(self):
        """All lines must parse without errors."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        error_types = [e for e in events if e.type == EventType.PARSE_ERROR]
        assert error_types == [], (
            f"Unexpected PARSE_ERROR: {[(e.line, e.payload) for e in error_types]}"
        )

    def test_event_types_present(self):
        """All expected graph-mode event types appear."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        types = {e.type for e in events}

        # Must appear
        assert EventType.STORY_BEGIN in types
        assert EventType.STORY_END in types
        assert EventType.SEGMENT in types
        assert EventType.CHOICE_BEGIN in types
        assert EventType.OPT in types
        assert EventType.CHOICE_END in types
        assert EventType.SET in types
        assert EventType.BRANCH_ENTER in types
        assert EventType.BRANCH_EXIT in types
        assert EventType.BRIDGE in types
        assert EventType.SCENE in types
        # DECLARE must NOT appear in the event stream
        assert EventType.DECLARE not in types, (
            "DECLARE should not enter the event stream"
        )

    def test_declare_not_in_stream(self):
        """DECLARE is consumed by the parser — zero events yielded."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        declare_events = [e for e in events if e.type == EventType.DECLARE]
        assert declare_events == []

    def test_scene_event_payload(self):
        """SCENE event has val, position, branch."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        scene_events = [e for e in events if e.type == EventType.SCENE]
        assert len(scene_events) == 1
        s = scene_events[0]
        assert s.payload["val"] == "grand_hotel_lobby"
        assert s.payload["position"] == "pre"
        assert s.payload["branch"] is None   # outside <branch>

    def test_seg_with_char(self):
        """SEGMENT with char='...' carries the name in payload."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        char_segs = [
            e for e in events
            if e.type == EventType.SEGMENT and "char" in e.payload
        ]
        assert len(char_segs) > 0, "Expected at least one <seg char='...'>"
        char_names = {e.payload["char"] for e in char_segs}
        assert "Alex" in char_names
        assert "Mira" in char_names
        assert "agent" in char_names

    def test_seg_expression_variant(self):
        """Expression variants (e.g. Mira.angry, Alex.sad) are preserved."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        expr_segs = [
            e for e in events
            if e.type == EventType.SEGMENT
            and "char" in e.payload
            and "." in e.payload.get("char", "")
        ]
        chars_with_expr = {e.payload["char"] for e in expr_segs}
        assert "Mira.angry" in chars_with_expr
        assert "Alex.sad" in chars_with_expr

    def test_seg_without_char(self):
        """Narration segs have no 'char' key."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        bare_segs = [
            e for e in events
            if e.type == EventType.SEGMENT and "char" not in e.payload
        ]
        assert len(bare_segs) > 0, "Expected narration segs without char"

    def test_bridge_position_payload(self):
        """Pre-bridge segs have position='pre', post-bridge = 'post'."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        bridge_idx = next(
            i for i, e in enumerate(events) if e.type == EventType.BRIDGE
        )
        pre_segs = [
            e for e in events[:bridge_idx]
            if e.type == EventType.SEGMENT
        ]
        post_segs = [
            e for e in events[bridge_idx + 1:]
            if e.type == EventType.SEGMENT
        ]
        assert all(s.payload["position"] == "pre" for s in pre_segs)
        assert all(s.payload["position"] == "post" for s in post_segs)

    def test_choice_end_includes_choice_data(self):
        """CHOICE_END carries aggregated choice_data from parser."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        choice_ends = [e for e in events if e.type == EventType.CHOICE_END]
        assert len(choice_ends) == 1
        cd = choice_ends[0].payload["choice_data"]
        assert cd["id"] == "trust_check"
        assert len(cd["branches"]) == 2

    def test_sm_scene_updates_current_scene(self, empty_gs):
        """StateManager.current_scene is set from SCENE event."""
        sm = StateManager(empty_gs)
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        for e in events:
            list(sm.process(e))
        assert sm.current_scene == "grand_hotel_lobby"

    def test_dispatcher_scene_ui_dict(self, dispatcher):
        """SCENE → UI dict with type='scene'."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        scene_events = [e for e in events if e.type == EventType.SCENE]
        ui = dispatcher.dispatch(scene_events[0])
        assert ui["type"] == "scene"
        assert ui["val"] == "grand_hotel_lobby"

    def test_dispatcher_segment_ui_dict(self, dispatcher):
        """SEGMENT → UI dict with type='segment' and char."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        char_seg = next(
            e for e in events
            if e.type == EventType.SEGMENT and "char" in e.payload
        )
        ui = dispatcher.dispatch(char_seg)
        assert ui["type"] == "segment"
        assert "char" in ui
        assert ui["char"] == char_seg.payload["char"]

    def test_no_post_bridge_prohibited_tags(self):
        """No choice/set/checkpoint/declare after bridge."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        bridge_idx = next(
            i for i, e in enumerate(events) if e.type == EventType.BRIDGE
        )
        prohibited = {
            EventType.CHOICE_BEGIN, EventType.CHOICE_END,
            EventType.OPT, EventType.SET, EventType.CHECKPOINT,
            EventType.CHECKPOINT_END, EventType.ROUTE,
            EventType.SCENE, EventType.DECLARE,
        }
        post = events[bridge_idx + 1:]
        violations = [(e.line, e.type.name) for e in post if e.type in prohibited]
        assert violations == [], (
            f"Prohibited tags after bridge: {violations}"
        )


# ── Example 2: The Last Archive ─────────────────────────────────────

class TestExample2Pipeline:
    """End-to-end: Example 2 (The Last Archive) through full pipeline."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.xml = _extract_example_xml(2)

    def test_no_parse_errors(self):
        """All lines must parse without errors."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        error_types = [e for e in events if e.type == EventType.PARSE_ERROR]
        assert error_types == [], (
            f"Unexpected PARSE_ERROR: {[(e.line, e.payload) for e in error_types]}"
        )

    def test_event_types_present(self):
        """Checkpoint, route, and branch are present. No declare/scene."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        types = {e.type for e in events}

        assert EventType.CHECKPOINT in types
        assert EventType.ROUTE in types
        assert EventType.BRANCH_ENTER in types
        assert EventType.BRANCH_EXIT in types
        assert EventType.CHOICE_BEGIN in types
        assert EventType.CHOICE_END in types
        assert EventType.BRIDGE in types
        # These must NOT appear
        assert EventType.DECLARE not in types
        assert EventType.SCENE not in types

    def test_checkpoint_payload(self):
        """CHECKPOINT carries node, summary."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        cp_events = [e for e in events if e.type == EventType.CHECKPOINT]
        assert len(cp_events) == 1
        cp = cp_events[0]
        assert cp.payload["node"] == "ch2_confrontation"
        assert "Yara Voss confronted" in cp.payload["summary"]

    def test_route_payload(self):
        """ROUTE carries if and target."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        route_events = [e for e in events if e.type == EventType.ROUTE]
        assert len(route_events) == 2
        targets = {r.payload["target"] for r in route_events}
        assert targets == {"ch3_ally", "ch3_expose"}

    def test_two_choices(self):
        """Example 2 has two choices: flavor (no branch) + key (with branch)."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        choice_ends = [e for e in events if e.type == EventType.CHOICE_END]
        assert len(choice_ends) == 2

        # First choice (confront_style): no branch on opts
        cd0 = choice_ends[0].payload["choice_data"]
        assert cd0["id"] == "confront_style"
        # opts without branch should not have non-main branches
        # (they can be bare → implicit "main")

        # Second choice (deal_choice): has branch attrs on opts
        cd1 = choice_ends[1].payload["choice_data"]
        assert cd1["id"] == "deal_choice"
        assert len(cd1["branches"]) == 2

    def test_no_declare_no_scene_in_stream(self):
        """Example 2 intentionally excludes declare and SCENE."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        types = {e.type for e in events}
        assert EventType.DECLARE not in types
        assert EventType.SCENE not in types

    def test_sm_checkpoint_processed(self, empty_gs):
        """StateManager processes checkpoint and updates current_node."""
        sm = StateManager(empty_gs)
        sm.set_outline([
            {"id": "ch2_confrontation", "title": "C2", "goal": "Confront",
             "routes": [
                 {"condition": "deal_choice==1", "target": "ch3_ally"},
                 {"condition": "deal_choice==2", "target": "ch3_expose"},
             ]},
            {"id": "ch3_ally", "title": "C3a", "goal": "Ally", "routes": []},
            {"id": "ch3_expose", "title": "C3b", "goal": "Expose", "routes": []},
        ])
        sm.init_progress("ch2_confrontation", "Confront Kai")

        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        for e in events:
            list(sm.process(e))
        list(sm.process_checkpoint())
        # With deal_choice unset, both routes evaluate to no match
        # but the checkpoint should be processed without format errors
        result = sm.get_result()
        assert result.checkpoint_node == "ch2_confrontation"

    def test_dispatcher_ui_dicts(self, dispatcher):
        """All events with UI representation convert to dicts with 'type'."""
        parser = StreamParser()
        events = _feed_xml(parser, self.xml)
        # Events consumed upstream (choice, checkpoint internals) return {}
        no_ui = {EventType.CHOICE_BEGIN, EventType.OPT, EventType.CHOICE_END,
                 EventType.CHECKPOINT, EventType.ROUTE,
                 EventType.BRANCH_ENTER, EventType.BRANCH_EXIT,
                 EventType.CHECKPOINT_END}
        for e in events:
            ui = dispatcher.dispatch(e)
            assert isinstance(ui, dict)
            if e.type not in no_ui:
                assert "type" in ui, (
                    f"Event {e.type.name} should have 'type' in UI dict"
                )


# ── Text mode unaffected ────────────────────────────────────────────

class TestTextModeUnaffected:
    """Graph-mode Prompt examples must not affect text-mode behavior."""

    def test_text_mode_prefix_unchanged(self):
        """ROUND1_PREFIX (text mode) still uses old examples."""
        from storyloom.core.prompt_builder import ROUND1_PREFIX
        assert "Kael" in ROUND1_PREFIX
        assert "Greta" in ROUND1_PREFIX
        assert "Elena" in ROUND1_PREFIX
        # Graph-mode-only elements must NOT appear in text-mode prompt
        assert "<declare" not in ROUND1_PREFIX
        assert 'char="' not in ROUND1_PREFIX
        assert 'var="SCENE"' not in ROUND1_PREFIX

    def test_text_mode_round_template_unchanged(self):
        """ROUND_TEMPLATE (text mode) has no scene_line."""
        from storyloom.core.prompt_builder import ROUND_TEMPLATE
        assert "{scene_line}" not in ROUND_TEMPLATE
        assert "{bridge_text}" in ROUND_TEMPLATE

    def test_text_mode_builders_still_work(self):
        """build_round1 / build_round_n still return valid strings."""
        from storyloom.core.prompt_builder import PromptBuilder
        result = PromptBuilder.build_round1(
            story_config={"language": "en"},
            outline_text="ch1 [active]",
            current_node="ch1",
            goal="Start",
            state_vars={"GLOBAL": {"trust": 50}},
        )
        assert "Kael" in result
        assert len(result) > 0

        result_n = PromptBuilder.build_round_n(
            outline_text="ch1 [active]",
            current_node="ch1",
            goal="Continue",
            state_vars={"GLOBAL": {"trust": 50}},
            variables=[],
            bridge_text="He walked away.",
        )
        assert "He walked away." in result_n

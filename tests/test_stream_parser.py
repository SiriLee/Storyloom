"""Tests for StreamParser — pure line → Event conversion.

Per design.md §3.2: StreamParser produces Events from token lines.
Tests cover all Phase 1 event types.  Phase 2 can extend by adding new
entries to the parametrize tables.
"""

import pytest
from storyloom.parser.stream_parser import (
    Event,
    EventType,
    LineBuffer,
    StreamParser,
)


# ── Shared test data ──────────────────────────────────────────────
# Extensible: Phase 2 adds SCENE / DECLARE entries here.

# (xml_line, expected_event_type, expected_payload_subset)
TAG_EVENT_MAP = [
    # Container open/close
    ("<story>", EventType.STORY_BEGIN, {}),
    ("</story>", EventType.STORY_END, {}),
    # Segment
    ('<seg>rain hammers the awning.</seg>', EventType.SEGMENT,
     {"text": "rain hammers the awning.", "position": "pre"}),
    ('<seg>numbered seg</seg>', EventType.SEGMENT,
     {"text": "numbered seg"}),
    # Segment with optional char attribute (Phase 2)
    ('<seg char="hero">Hero speaks.</seg>', EventType.SEGMENT,
     {"text": "Hero speaks.", "char": "hero"}),
    # Choice
    ('<choice id="approach">', EventType.CHOICE_BEGIN,
     {"id": "approach"}),
    ('<opt key="1" branch="direct">Meet his gaze</opt>', EventType.OPT,
     {"key": "1", "target": "direct", "text": "Meet his gaze"}),
    ('<opt key="2" branch="cautious" if="trust>50">Look around</opt>',
     EventType.OPT,
     {"key": "2", "target": "cautious", "if": "trust>50",
      "text": "Look around"}),
    ("</choice>", EventType.CHOICE_END, {}),
    # SET
    ('<set var="trust" op="+" val="10"/>', EventType.SET,
     {"var": "trust", "op": "+", "val": "10"}),
    ('<set var="flag" val="activated"/>', EventType.SET,
     {"var": "flag", "op": "=", "val": "activated"}),
    ('<set var="hp" op="-" val="5" if="受伤==1"/>', EventType.SET,
     {"var": "hp", "op": "-", "val": "5", "if": "受伤==1"}),
    # Checkpoint
    ('<checkpoint node="ch2" summary="Contact made.">',
     EventType.CHECKPOINT,
     {"node": "ch2", "summary": "Contact made."}),
    ('<checkpoint node="ch3" summary="End."/>',
     EventType.CHECKPOINT,
     {"node": "ch3", "summary": "End."}),
    ("</checkpoint>", EventType.CHECKPOINT_END, {}),
    # Route
    ('<route target="ch3"/>', EventType.ROUTE,
     {"target": "ch3", "if": None}),
    ('<route if="trust>50" target="ch3_good"/>', EventType.ROUTE,
     {"if": "trust>50", "target": "ch3_good"}),
    # Bridge
    ("<bridge/>", EventType.BRIDGE, {}),
    # Branch
    ('<branch name="direct">', EventType.BRANCH_ENTER,
     {"name": "direct"}),
    ("</branch>", EventType.BRANCH_EXIT, {}),
]


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def parser():
    """Fresh StreamParser for each test."""
    return StreamParser()


def _parse_one(parser, line):
    """Feed one line inside <story>...</story>, return the event (or None)."""
    events = parser.feed_line(line)
    return events[0] if events else None


# ── LineBuffer tests ──────────────────────────────────────────────

class TestLineBuffer:
    """LineBuffer: token chunks → complete lines."""

    def test_feed_single_line(self):
        lb = LineBuffer()
        assert lb.feed("hello world\n") == ["hello world"]

    def test_feed_partial_then_complete(self):
        lb = LineBuffer()
        assert lb.feed("hel") == []
        assert lb.feed("lo w") == []
        assert lb.feed("orld\n") == ["hello world"]

    def test_feed_multiple_lines_in_one_chunk(self):
        lb = LineBuffer()
        assert lb.feed("line one\nline two\n") == ["line one", "line two"]

    def test_feed_whitespace_only_skipped(self):
        lb = LineBuffer()
        assert lb.feed("  \nreal\n\t\n") == ["real"]

    def test_flush_returns_remaining(self):
        lb = LineBuffer()
        lb.feed("partial line")
        assert lb.flush() == "partial line"

    def test_flush_empty_returns_none(self):
        lb = LineBuffer()
        assert lb.flush() is None


# ── StreamParser: tag → event ─────────────────────────────────────

class TestStreamParserTags:
    """Every XML tag produces the correct Event with correct payload."""

    @pytest.mark.parametrize("line,expected_type,expected_payload", [
        (f"<story>\n{tag_line}\n</story>", etype, payload)
        if etype not in (EventType.STORY_BEGIN, EventType.STORY_END)
        else (tag_line, etype, payload)
        for tag_line, etype, payload in TAG_EVENT_MAP
    ])
    def test_tag_produces_correct_event(
        self, parser, line, expected_type, expected_payload
    ):
        """Parametrized: each tag → correct EventType + payload subset."""
        events = []
        for ln in line.split("\n"):
            events.extend(parser.feed_line(ln))
        matching = [e for e in events if e.type == expected_type]
        assert len(matching) >= 1, (
            f"Expected {expected_type.name} event, got {[e.type.name for e in events]}"
        )
        event = matching[0]
        for key, val in expected_payload.items():
            assert event.payload.get(key) == val, (
                f"payload['{key}']: expected {val!r}, got {event.payload.get(key)!r}"
            )

    def test_every_event_has_line_number(self, parser):
        """Per design.md §4.1: every Event has a line field."""
        events = []
        for ln in [
            "<story>", "<seg>hello</seg>", "<bridge/>",
            "<seg>world</seg>", "</story>",
        ]:
            events.extend(parser.feed_line(ln))
        for e in events:
            assert e.line > 0, f"{e.type.name} has line={e.line}"


# ── StreamParser: SEG char attribute ────────────────────────────────

class TestSegCharAttribute:
    """SEGMENT ``char`` attribute — optional, empty = absent (Phase 2)."""

    def test_char_present_when_non_empty(self, parser):
        parser.feed_line("<story>")
        evt = _parse_one(parser, '<seg char="hero">Hero speaks.</seg>')
        assert evt.payload["char"] == "hero"

    def test_no_char_key_when_absent(self, parser):
        parser.feed_line("<story>")
        evt = _parse_one(parser, "<seg>plain text</seg>")
        assert "char" not in evt.payload

    def test_no_char_key_when_empty(self, parser):
        parser.feed_line("<story>")
        evt = _parse_one(parser, '<seg char="">text</seg>')
        assert "char" not in evt.payload


# ── StreamParser: DECLARE parsing ────────────────────────────────────

class TestDeclareParsing:
    """``<declare>`` → validated, NOT in event stream (§7.5)."""

    def test_declare_not_in_event_stream(self, parser):
        parser.feed_line("<story>")
        events = parser.feed_line(
            '<declare kind="CHAR" name="ghost">a ghost</declare>')
        assert events == []
        assert parser.format_errors == []  # valid = no error

    def test_declare_scene_kind_accepted(self, parser):
        parser.feed_line("<story>")
        events = parser.feed_line(
            '<declare kind="SCENE" name="crypt">ancient crypt</declare>')
        assert events == []

    def test_declare_kind_case_insensitive(self, parser):
        parser.feed_line("<story>")
        events = parser.feed_line(
            '<declare kind="char" name="ghost">desc</declare>')
        assert events == []
        assert parser.format_errors == []  # no error = accepted

    def test_declare_invalid_kind_parse_error(self, parser):
        parser.feed_line("<story>")
        events = parser.feed_line(
            '<declare kind="BGM" name="theme">epic</declare>')
        assert len(events) == 1
        assert events[0].type == EventType.PARSE_ERROR

    def test_declare_after_bridge_format_error(self, parser):
        parser.feed_line("<story>")
        parser.feed_line("<bridge/>")
        events = parser.feed_line(
            '<declare kind="CHAR" name="ghost">desc</declare>')
        assert events == []
        assert any("declare" in e.lower() for e in parser.format_errors)

    def test_declare_dispatches_to_task_gen(self, parser):
        """DECLARE triggers task_gen.enqueue() synchronously."""
        dispatched = []
        parser.task_gen = _FakeTaskGen(dispatched)
        parser.feed_line("<story>")
        events = parser.feed_line(
            '<declare kind="CHAR" name="ghost">a ghost</declare>')
        assert events == []
        assert len(dispatched) == 1
        e = dispatched[0]
        assert e.type == EventType.DECLARE
        assert e.payload["kind"] == "CHAR"
        assert e.payload["name"] == "ghost"
        assert e.payload["desc"] == "a ghost"


class _FakeTaskGen:
    """Records enqueue() calls.  duck-types TaskGenerator for tests."""
    def __init__(self, sink: list):
        self._sink = sink
    def enqueue(self, event):
        self._sink.append(event)
        return None


# ── StreamParser: branch injection ───────────────────────────────────

class TestBranchInjection:
    """SET, CHOICE, OPT events inside a <branch> carry branch name."""

    def test_set_in_branch(self, parser):
        parser.feed_line("<story>")
        parser.feed_line('<branch name="hero">')
        evt = _parse_one(parser, '<set var="trust" val="10"/>')
        assert evt.payload["branch"] == "hero"

    def test_choice_begin_in_branch(self, parser):
        parser.feed_line("<story>")
        parser.feed_line('<branch name="hero">')
        evt = _parse_one(parser, '<choice id="q1">')
        assert evt.payload["branch"] == "hero"

    def test_opt_in_branch(self, parser):
        """OPT carries both target (opt's own branch) and container."""
        parser.feed_line("<story>")
        parser.feed_line('<branch name="hero">')
        evt = _parse_one(parser,
                         '<opt key="1" branch="x">Go</opt>')
        assert evt.payload["target"] == "x"    # opt's own branch attr
        assert evt.payload["branch"] == "hero" # container branch

    def test_choice_end_in_branch(self, parser):
        parser.feed_line("<story>")
        parser.feed_line('<branch name="hero">')
        parser.feed_line('<choice id="q1">')
        parser.feed_line('<opt key="1" branch="x">Go</opt>')
        evt = _parse_one(parser, '</choice>')
        assert evt.payload["branch"] == "hero"

    def test_set_outside_branch(self, parser):
        parser.feed_line("<story>")
        evt = _parse_one(parser, '<set var="trust" val="10"/>')
        assert evt.payload["branch"] is None

    def test_choice_begin_outside_branch(self, parser):
        parser.feed_line("<story>")
        evt = _parse_one(parser, '<choice id="q1">')
        assert evt.payload["branch"] is None

    def test_opt_outside_branch(self, parser):
        parser.feed_line("<story>")
        evt = _parse_one(parser,
                         '<opt key="1" branch="x">Go</opt>')
        assert evt.payload["branch"] is None

    def test_choice_end_outside_branch(self, parser):
        parser.feed_line("<story>")
        parser.feed_line('<choice id="q1">')
        parser.feed_line('<opt key="1" branch="x">Go</opt>')
        evt = _parse_one(parser, '</choice>')
        assert evt.payload["branch"] is None


# ── StreamParser: post-bridge suppress ───────────────────────────────

class TestPostBridgeSuppress:
    """Prohibited tags after <bridge/> → format_error + return []."""

    PROHIBITED = [
        ('<set var="x" val="1"/>', "set"),
        ('<choice id="bad">', "choice"),
        ('</choice>', "choice"),
        ('<opt key="1" branch="x">o</opt>', "opt"),
        ('<checkpoint node="ch1" summary="s">', "checkpoint"),
        ('<checkpoint node="ch1" summary="s"/>', "checkpoint"),
        ('</checkpoint>', "checkpoint"),
        ('<route target="ch2"/>', "route"),
    ]

    @pytest.mark.parametrize("line,tag_name", PROHIBITED)
    def test_prohibited_tag_suppressed(self, parser, line, tag_name):
        parser.feed_line("<story>")
        parser.feed_line("<bridge/>")
        events = parser.feed_line(line)
        assert events == [], f"{tag_name} after bridge should return []"
        assert any(tag_name in e.lower() for e in parser.format_errors), (
            f"format_errors should mention '{tag_name}'"
        )

    def test_allowed_tags_still_pass(self, parser):
        """<seg>, <branch>, </branch> still emit after bridge."""
        parser.feed_line("<story>")
        parser.feed_line("<bridge/>")
        evt = _parse_one(parser, "<seg>after bridge</seg>")
        assert evt.type == EventType.SEGMENT
        evt = _parse_one(parser, '<branch name="epilogue">')
        assert evt.type == EventType.BRANCH_ENTER
        evt = _parse_one(parser, '</branch>')
        assert evt.type == EventType.BRANCH_EXIT


# ── StreamParser: SCENE parsing ─────────────────────────────────────

class TestSceneParsing:
    """``<set var="SCENE" val="...">`` → SCENE event, not SET (Phase 2)."""

    def test_scene_produces_scene_event(self, parser):
        parser.feed_line("<story>")
        evt = _parse_one(parser, '<set var="SCENE" val="tavern"/>')
        assert evt.type == EventType.SCENE
        assert evt.payload["val"] == "tavern"

    def test_scene_with_if_condition(self, parser):
        parser.feed_line("<story>")
        evt = _parse_one(parser,
                         '<set var="SCENE" val="forest" if="x>1"/>')
        assert evt.type == EventType.SCENE
        assert evt.payload["if"] == "x>1"

    def test_scene_op_equals_accepted(self, parser):
        """Explicit op='=' is valid for SCENE (same as default)."""
        parser.feed_line("<story>")
        evt = _parse_one(parser,
                         '<set var="SCENE" op="=" val="tavern"/>')
        assert evt.type == EventType.SCENE

    def test_scene_op_ignored_always_sets(self, parser):
        """op='+' is ignored for SCENE — treated as plain assignment."""
        parser.feed_line("<story>")
        evt = _parse_one(parser, '<set var="SCENE" op="+" val="tavern"/>')
        assert evt.type == EventType.SCENE
        assert evt.payload["val"] == "tavern"

    def test_scene_has_position(self, parser):
        parser.feed_line("<story>")
        evt = _parse_one(parser, '<set var="SCENE" val="tavern"/>')
        assert evt.payload["position"] == "pre"

    def test_scene_outside_branch_branch_none(self, parser):
        parser.feed_line("<story>")
        evt = _parse_one(parser, '<set var="SCENE" val="tavern"/>')
        assert evt.payload["branch"] is None

    def test_scene_after_bridge_suppressed(self, parser):
        parser.feed_line("<story>")
        parser.feed_line("<bridge/>")
        events = parser.feed_line('<set var="SCENE" val="tavern"/>')
        assert events == []
        assert any("SCENE" in e for e in parser.format_errors)

    def test_scene_in_branch_has_branch_name(self, parser):
        parser.feed_line("<story>")
        parser.feed_line('<branch name="hero">')
        evt = _parse_one(parser, '<set var="SCENE" val="tavern"/>')
        assert evt.payload["branch"] == "hero"


# ── StreamParser: position tracking ───────────────────────────────

class TestStreamParserPosition:
    """Position tracking: pre-bridge vs post-bridge."""

    def test_pre_bridge_position(self, parser):
        parser.feed_line("<story>")
        evt = _parse_one(parser, "<seg>before bridge</seg>")
        assert evt.payload["position"] == "pre"

    def test_post_bridge_position(self, parser):
        parser.feed_line("<story>")
        parser.feed_line("<bridge/>")
        evt = _parse_one(parser, "<seg>after bridge</seg>")
        assert evt.payload["position"] == "post"

    def test_segment_in_branch_has_branch_name(self, parser):
        parser.feed_line("<story>")
        parser.feed_line('<branch name="hero">')
        evt = _parse_one(parser, "<seg>hero text</seg>")
        assert evt.payload["branch"] == "hero"


# ── StreamParser: edge cases ──────────────────────────────────────

class TestStreamParserEdgeCases:
    """Edge cases: empty input, comments, content before story."""

    def test_empty_input(self, parser):
        assert parser.feed_line("") == []
        assert parser.feed_line("   ") == []

    def test_xml_comment_skipped(self, parser):
        assert parser.feed_line("<!-- comment -->") == []

    def test_content_before_story_ignored(self, parser):
        events = parser.feed_line("preamble text")
        assert events == []
        parser.feed_line("<story>")
        evt = _parse_one(parser, "<seg>ok</seg>")
        assert evt.type == EventType.SEGMENT

    def test_line_number_prefix_stripped(self, parser):
        """NNN| prefix is stripped before matching."""
        evt = _parse_one(parser, '001| <story>')
        assert evt.type == EventType.STORY_BEGIN
        assert evt.line == 1

    def test_never_blocks(self, parser):
        """Per design.md §3.5: feed_line is synchronous, never blocks."""
        import time
        parser.feed_line("<story>")
        start = time.perf_counter()
        for _ in range(1000):
            parser.feed_line("<seg>test</seg>")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, f"1000 calls took {elapsed*1000:.1f}ms"

    def test_bridge_seen_property(self, parser):
        assert not parser.bridge_seen
        parser.feed_line("<story>")
        parser.feed_line("<bridge/>")
        assert parser.bridge_seen

    def test_format_error_choice_after_bridge(self, parser):
        parser.feed_line("<story>")
        parser.feed_line("<bridge/>")
        parser.feed_line('<choice id="bad">')
        assert len(parser.format_errors) >= 1
        assert any("choice" in e.lower() for e in parser.format_errors)

    def test_format_error_set_after_bridge(self, parser):
        parser.feed_line("<story>")
        parser.feed_line("<bridge/>")
        parser.feed_line('<set var="x" val="1"/>')
        assert any("set" in e.lower() for e in parser.format_errors)

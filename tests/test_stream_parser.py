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
    ('<seg n="5">numbered seg</seg>', EventType.SEGMENT,
     {"text": "numbered seg", "n": 5}),
    # Choice
    ('<choice id="approach">', EventType.CHOICE_BEGIN,
     {"id": "approach"}),
    ('<opt key="1" branch="direct">Meet his gaze</opt>', EventType.OPT,
     {"key": "1", "branch": "direct", "text": "Meet his gaze"}),
    ('<opt key="2" branch="cautious" if="trust>50">Look around</opt>',
     EventType.OPT,
     {"key": "2", "branch": "cautious", "if": "trust>50",
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

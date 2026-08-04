"""Tests for StateManager — Event processing and state logic.

Per design.md §3.2: StateManager handles SET / CHECKPOINT / BRANCH /
BRIDGE processing and CHOICE_END blocking.

Tests are structured for Phase 2 extensibility:
- Parametrized event processing tests (add new Phase 2 types here).
- Shared GameState fixtures in parametrize decorators.
- Clear arrange/act/assert pattern for each design requirement.
"""

import pytest
from storyloom.parser.stream_parser import Event, EventType
from storyloom.core.state_manager import StateManager
from storyloom.core.game_loop import GameState


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def empty_gs():
    """GameState with no variables."""
    return GameState([])


@pytest.fixture
def num_gs():
    """GameState with a numeric 'trust' variable."""
    return GameState([{"name": "trust", "type": "number", "initial": "50"}])


@pytest.fixture
def sm(empty_gs):
    """Fresh StateManager with empty GameState."""
    return StateManager(empty_gs)


@pytest.fixture
def sm_num(num_gs):
    """Fresh StateManager with numeric GameState."""
    return StateManager(num_gs)


# ── Pass-through events ───────────────────────────────────────────
# Phase 2: add SCENE / DECLARE handling parametrize entries.

PASSTHROUGH_TYPES = [
    EventType.STORY_BEGIN,
    EventType.STORY_END,
    EventType.BRIDGE,
    EventType.CHECKPOINT_END,
]


class TestPassThrough:
    """Events that StateManager forwards unchanged."""

    @pytest.mark.parametrize("etype", PASSTHROUGH_TYPES)
    def test_passthrough(self, sm, etype):
        """Per design.md §4.1: all Phase 1 events pass through StateManager."""
        event = Event(etype, 1, {})
        results = list(sm.process(event))
        assert len(results) == 1
        assert results[0].type == etype

    def test_branch_enter_accumulates_name(self, sm):
        event = Event(EventType.BRANCH_ENTER, 1,
                      {"name": "hero", "position": "pre"})
        results = list(sm.process(event))
        assert len(results) == 1
        result = sm.get_result()
        assert "hero" in result.pre_branches

    def test_branch_exit_passthrough(self, sm):
        event = Event(EventType.BRANCH_EXIT, 1,
                      {"name": "hero", "position": "pre"})
        results = list(sm.process(event))
        assert len(results) == 1
        assert results[0].type == EventType.BRANCH_EXIT


# ── SET handling ──────────────────────────────────────────────────

class TestSetHandling:
    """SET event application and rejection."""

    def test_set_applies_to_gamestate(self, sm_num):
        event = Event(EventType.SET, 1,
                      {"var": "trust", "op": "+", "val": "10", "if": None})
        results = list(sm_num.process(event))
        assert len(results) == 1
        assert results[0].type == EventType.SET
        assert sm_num._game_state.state_vars["GLOBAL"]["trust"] == 60

    def test_set_with_condition_met(self, sm_num):
        event = Event(EventType.SET, 1,
                      {"var": "trust", "op": "=", "val": "100",
                       "if": "trust>=30"})
        results = list(sm_num.process(event))
        assert len(results) == 1
        assert sm_num._game_state.state_vars["GLOBAL"]["trust"] == 100

    def test_set_with_condition_not_met_skipped(self, sm_num):
        event = Event(EventType.SET, 1,
                      {"var": "trust", "op": "=", "val": "100",
                       "if": "trust>90"})
        results = list(sm_num.process(event))
        assert len(results) == 0  # skipped, no event yielded

    def test_set_unknown_variable_rejected(self, sm):
        event = Event(EventType.SET, 1,
                      {"var": "nonexistent", "op": "=", "val": "x",
                       "if": None})
        results = list(sm.process(event))
        assert len(results) == 1  # still yields event
        assert len(sm.rejected_changes) == 1
        assert "unknown variable" in sm.rejected_changes[0]

    def test_set_branch_var(self, sm):
        """BRANCH_VAR special handling: updates current_branch directly."""
        from storyloom.config import BRANCH_VAR_NAME
        event = Event(EventType.SET, 1,
                      {"var": BRANCH_VAR_NAME, "op": "=", "val": "hero",
                       "if": None})
        list(sm.process(event))
        assert sm.current_branch == "hero"

    def test_set_accumulates_in_result(self, sm_num):
        event = Event(EventType.SET, 1,
                      {"var": "trust", "op": "+", "val": "5", "if": None})
        list(sm_num.process(event))
        result = sm_num.get_result()
        assert len(result.sets) == 1
        assert result.sets[0].var == "trust"
        assert result.sets[0].op == "+"
        assert result.sets[0].val == "5"


# ── Branch filtering ──────────────────────────────────────────────

class TestBranchFiltering:
    """SEGMENT events are filtered by current_branch."""

    def test_bare_seg_always_passes(self, sm):
        """Bare <seg> (no branch attr) always yields regardless of branch."""
        event = Event(EventType.SEGMENT, 1,
                      {"text": "narration", "branch": None,
                       "position": "pre", "n": 1})
        results = list(sm.process(event))
        assert len(results) == 1

    def test_matching_branch_passes(self, sm):
        sm._current_branch = "hero"
        event = Event(EventType.SEGMENT, 1,
                      {"text": "hero text", "branch": "hero",
                       "position": "pre", "n": 1})
        results = list(sm.process(event))
        assert len(results) == 1

    def test_non_matching_branch_filtered(self, sm):
        sm._current_branch = "hero"
        event = Event(EventType.SEGMENT, 1,
                      {"text": "villain text", "branch": "villain",
                       "position": "pre", "n": 1})
        results = list(sm.process(event))
        assert len(results) == 0


# ── CHOICE handling ───────────────────────────────────────────────

class TestChoiceHandling:
    """CHOICE_BEGIN / OPT / CHOICE_END lifecycle."""

    def test_choice_data_from_choice_end(self, sm):
        """Choice data is read from the CHOICE_END payload, not re-accumulated."""
        list(sm.process(Event(EventType.CHOICE_BEGIN, 1, {"id": "path"})))
        list(sm.process(Event(EventType.OPT, 2,
                              {"key": "1", "branch": "hero",
                               "text": "Hero path", "if": None})))
        # CHOICE_END carries the aggregated choice_data from StreamParser
        list(sm.process(Event(EventType.CHOICE_END, 3,
                              {"choice_data": {
                                  "id": "path",
                                  "branches": ["hero"],
                                  "labels": ["Hero path"],
                                  "conditions": {},
                              }})))
        result = sm.get_result()
        assert len(result.choices) == 1
        assert result.choices[0]["id"] == "path"
        assert result.choices[0]["branches"] == ["hero"]

    def test_choice_end_sets_needs_input(self, sm):
        list(sm.process(Event(EventType.CHOICE_BEGIN, 1, {"id": "c1"})))
        list(sm.process(Event(EventType.OPT, 2,
                              {"key": "1", "branch": "b1", "text": "opt",
                               "if": None})))
        list(sm.process(Event(EventType.CHOICE_END, 3,
                              {"choice_data": {
                                  "id": "c1", "branches": ["b1"],
                                  "labels": ["opt"], "conditions": {},
                              }})))
        assert sm.needs_input
        assert sm.choice_data is not None

    def test_apply_choice_updates_branch(self, sm):
        list(sm.process(Event(EventType.CHOICE_BEGIN, 1, {"id": "c1"})))
        list(sm.process(Event(EventType.OPT, 2,
                              {"key": "1", "branch": "hero", "text": "opt",
                               "if": None})))
        list(sm.process(Event(EventType.CHOICE_END, 3,
                              {"choice_data": {
                                  "id": "c1", "branches": ["hero"],
                                  "labels": ["opt"], "conditions": {},
                              }})))
        list(sm.apply_choice("1"))
        assert sm.current_branch == "hero"
        assert not sm.needs_input

    def test_choice_conditions_evaluated(self, sm):
        """OPT with if=... condition is evaluated."""
        gs = GameState([{"name": "score", "type": "number", "initial": "30"}])
        sm2 = StateManager(gs)
        list(sm2.process(Event(EventType.CHOICE_BEGIN, 1, {"id": "c1"})))
        list(sm2.process(Event(EventType.OPT, 2,
                               {"key": "1", "branch": "easy", "text": "Easy",
                                "if": None})))
        list(sm2.process(Event(EventType.OPT, 3,
                               {"key": "2", "branch": "hard", "text": "Hard",
                                "if": "score>=50"})))
        # CHOICE_END event with choice_data from parser
        list(sm2.process(Event(EventType.CHOICE_END, 4,
                               {"choice_data": {
                                   "id": "c1",
                                   "branches": ["easy", "hard"],
                                   "labels": ["Easy", "Hard"],
                                   "conditions": {"hard": "score>=50"},
                               }})))
        assert sm2.choice_data["enabled"] == [True, False]

    def test_all_disabled_fallback(self, sm):
        """When all options are disabled, all become enabled (lockup prevention)."""
        gs = GameState([{"name": "score", "type": "number", "initial": "0"}])
        sm2 = StateManager(gs)
        list(sm2.process(Event(EventType.CHOICE_BEGIN, 1, {"id": "c1"})))
        for i, b in enumerate(["a", "b"]):
            list(sm2.process(Event(EventType.OPT, i + 2,
                                   {"key": str(i + 1), "branch": b,
                                    "text": b, "if": "score>=100"})))
        list(sm2.process(Event(EventType.CHOICE_END, 5,
                               {"choice_data": {
                                   "id": "c1",
                                   "branches": ["a", "b"],
                                   "labels": ["a", "b"],
                                   "conditions": {"a": "score>=100",
                                                  "b": "score>=100"},
                               }})))
        assert sm2.choice_data["enabled"] == [True, True]


# ── Bridge text ───────────────────────────────────────────────────

class TestBridgeText:
    """Bridge text accumulation and filtering (per block-spec.md)."""

    def test_accumulates_post_bridge_segments(self, sm):
        list(sm.process(Event(EventType.SEGMENT, 1,
                              {"text": "pre", "branch": None,
                               "position": "pre", "n": 1})))
        list(sm.process(Event(EventType.SEGMENT, 2,
                              {"text": "post bare", "branch": None,
                               "position": "post", "n": 2})))
        bt = sm.get_bridge_text()
        assert "post bare" in bt
        assert "pre" not in bt

    def test_filters_by_branch(self, sm):
        sm._current_branch = "hero"
        list(sm.process(Event(EventType.SEGMENT, 1,
                              {"text": "bare", "branch": None,
                               "position": "post", "n": 1})))
        list(sm.process(Event(EventType.SEGMENT, 2,
                              {"text": "hero text", "branch": "hero",
                               "position": "post", "n": 2})))
        list(sm.process(Event(EventType.SEGMENT, 3,
                              {"text": "villain text", "branch": "villain",
                               "position": "post", "n": 3})))
        bt = sm.get_bridge_text("hero")
        assert "bare" in bt
        assert "hero text" in bt
        assert "villain text" not in bt

    def test_get_bridge_text_none_returns_accumulated(self, sm):
        """get_bridge_text(None) returns all accumulated post-bridge items.

        Accumulation already filters by current_branch during processing,
        so non-matching branch segments are never stored.
        """
        sm._current_branch = "hero"
        for i, (text, branch) in enumerate([
            ("bare", None), ("hero", "hero"), ("villain", "villain"),
        ]):
            list(sm.process(Event(EventType.SEGMENT, i + 1,
                                  {"text": text, "branch": branch,
                                   "position": "post", "n": i + 1})))
        bt = sm.get_bridge_text()
        assert "bare" in bt
        assert "hero" in bt
        # villain branch != current_branch → filtered during accumulation
        assert "villain" not in bt


# ── Checkpoint handling ───────────────────────────────────────────

class TestCheckpointHandling:
    """Checkpoint processing: validation, ending detection, advancement."""

    @pytest.fixture
    def sm_with_outline(self, empty_gs):
        """StateManager with a simple 2-node outline."""
        sm = StateManager(empty_gs)
        sm.set_outline([
            {"id": "ch1", "title": "Chapter 1", "goal": "Meet the contact",
             "routes": [{"target": "ch2"}]},
            {"id": "ch2", "title": "Chapter 2", "goal": "The end",
             "routes": []},  # empty routes = ending
        ])
        sm.init_progress("ch1", "Meet the contact")
        return sm

    def test_checkpoint_advances_node(self, sm_with_outline):
        sm = sm_with_outline
        list(sm.process(Event(EventType.CHECKPOINT, 1,
                              {"node": "ch1", "summary": "Done."})))
        list(sm.process_checkpoint())
        assert sm.current_node == "ch2"

    def test_ending_detection(self, sm_with_outline):
        sm = sm_with_outline
        sm._current_node = "ch2"  # simulate advancing to ending node
        list(sm.process(Event(EventType.CHECKPOINT, 1,
                              {"node": "ch2", "summary": "The end."})))
        list(sm.process_checkpoint())
        assert sm.ending_flag

    def test_unknown_checkpoint_tracks_error(self, sm_with_outline):
        sm = sm_with_outline
        list(sm.process(Event(EventType.CHECKPOINT, 1,
                              {"node": "unknown_node", "summary": "bad"})))
        list(sm.process_checkpoint())
        assert len(sm.format_errors) >= 1
        assert "unknown_node" in sm.format_errors[0]

    def test_checkpoint_preserved_in_get_result(self, sm_with_outline):
        sm = sm_with_outline
        list(sm.process(Event(EventType.CHECKPOINT, 1,
                              {"node": "ch1", "summary": "Done."})))
        list(sm.process_checkpoint())
        result = sm.get_result()
        assert result.checkpoint_node == "ch1"
        assert "Done" in (result.checkpoint_summary or "")


# ── State queries ─────────────────────────────────────────────────

class TestStateQueries:
    """Properties expose correct state for GameLoop sync."""

    def test_current_branch_default(self, sm):
        assert sm.current_branch == "main"

    def test_rejected_changes_initially_empty(self, sm):
        assert sm.rejected_changes == []

    def test_routes_initially_empty(self, sm):
        assert sm.routes == []

    def test_format_errors_initially_empty(self, sm):
        assert sm.format_errors == []

    def test_ending_flag_initially_false(self, sm):
        assert not sm.ending_flag

"""Tests for context_manager module."""

import pytest
from storyloom.core.context_manager import ContextManager
from storyloom.config import WINDOW_SIZE, FIRST_COMPRESSION_AT


class TestContextManagerInit:
    def test_initial_state_has_no_messages(self):
        cm = ContextManager()
        assert cm.round_count == 0
        assert len(cm.get_messages()) == 0

    def test_initial_state_has_no_compressed_rounds(self):
        cm = ContextManager()
        assert cm.get_compressed_rounds() == []

    def test_initial_state_window_is_empty(self):
        cm = ContextManager()
        assert cm.get_window_rounds() == []


class TestSystemPrompt:
    def test_system_prompt_is_first_message(self):
        cm = ContextManager()
        cm.set_system_prompt("You are the director...")
        cm.add_round(
            user_content="Round 1 context",
            assistant_content="<story>...</story>",
        )
        assert cm.round_count == 1
        msgs = cm.get_messages()
        assert len(msgs) >= 3  # system + user(r1) + assistant(r1)
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are the director..."

    def test_set_system_prompt_raises_if_already_set(self):
        cm = ContextManager()
        cm.set_system_prompt("prompt")
        with pytest.raises(RuntimeError, match="System prompt already set"):
            cm.set_system_prompt("prompt2")

    def test_system_prompt_is_never_compressed(self):
        cm = ContextManager()
        cm.set_system_prompt("permanent system prompt")
        for _ in range(10):
            cm.add_round(
                "ctx",
                "<story><bridge/><seg>t</seg></story>",
            )
        msgs = cm.get_messages()
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "permanent system prompt"


class TestAddRound:
    def test_add_round_increments_count(self):
        cm = ContextManager()
        cm.set_system_prompt("sys")
        cm.add_round("Round 1 context", "<story><bridge/><seg>t</seg></story>")
        assert cm.round_count == 1
        cm.add_round("Round 2 context", "<story><bridge/><seg>t</seg></story>")
        assert cm.round_count == 2

    def test_add_round_appends_user_message(self):
        cm = ContextManager()
        cm.set_system_prompt("sys")
        cm.add_round("Round 1 context", "<story><bridge/><seg>t</seg></story>")
        msgs = cm.get_messages()
        user_messages = [m for m in msgs if m["role"] == "user"]
        assert any("Round 1 context" in m["content"] for m in user_messages)

    def test_add_round_raises_without_system_prompt(self):
        cm = ContextManager()
        with pytest.raises(RuntimeError, match="System prompt not set"):
            cm.add_round("ctx", "<story><bridge/><seg>t</seg></story>")


class TestSlidingWindow:
    def test_no_compression_before_threshold(self):
        cm = ContextManager()
        cm.set_system_prompt("sys")
        cm.add_round("r1", "<story><bridge/><seg>t</seg></story>")
        cm.add_round("r2", "<story><bridge/><seg>t</seg></story>")
        cm.add_round("r3", "<story><bridge/><seg>t</seg></story>")
        cm.add_round("r4", "<story><bridge/><seg>t</seg></story>")
        assert cm.get_compressed_rounds() == []

    def test_compression_starts_at_round_5(self):
        cm = ContextManager()
        cm.set_system_prompt("sys")
        cm.add_round(
            "r1",
            '<story><checkpoint node="ch1" summary="开局"/><bridge/><seg>t</seg></story>',
        )
        cm.add_round(
            "r2",
            '<story><checkpoint node="ch2" summary="接头"/><bridge/><seg>t</seg></story>',
        )
        cm.add_round("r3", '<story><bridge/><seg>t</seg></story>')
        cm.add_round("r4", '<story><bridge/><seg>t</seg></story>')
        cm.add_round("r5", '<story><bridge/><seg>t</seg></story>')
        compressed = cm.get_compressed_rounds()
        # 5 rounds total — keep WINDOW_SIZE=3, compress the first 2
        assert len(compressed) >= 1


class TestWindowRounds:
    def test_window_contains_last_n_rounds(self):
        cm = ContextManager()
        cm.set_system_prompt("sys")
        for i in range(1, 8):
            cm.add_round(f"r{i}", "<story><bridge/><seg>t</seg></story>")
        window = cm.get_window_rounds()
        assert len(window) <= WINDOW_SIZE


class TestCheckpointExtraction:
    def test_extract_checkpoint_summaries_from_output(self):
        cm = ContextManager()
        xml = (
            '<story>'
            '<checkpoint node="ch2" summary="在旅店接头。"/>'
            '<bridge/>'
            '<seg>tail text</seg>'
            '</story>'
        )
        summaries = cm._extract_checkpoint_summaries(xml)
        assert "在旅店接头" in summaries

    def test_extract_returns_empty_for_no_checkpoint(self):
        cm = ContextManager()
        xml = '<story><bridge/><seg>t</seg></story>'
        summaries = cm._extract_checkpoint_summaries(xml)
        assert summaries == ""


class TestCompressionFormat:
    def test_build_compression_message(self):
        cm = ContextManager()
        summaries = ["在旅店接头", "完成芯片交易", "选择信任耗子"]
        user_msg, asst_msg = cm._build_compression_messages(summaries)
        assert "Key events so far" in user_msg
        assert "在旅店接头" in user_msg
        assert "完成芯片交易" in user_msg
        assert asst_msg == "(Summary of previous events. The story continues.)"


class TestGetMessagesForRound:
    def test_returns_messages_array_for_api_call(self):
        cm = ContextManager()
        cm.set_system_prompt("system prompt")
        cm.add_round(
            "Round 1 context",
            '<story><checkpoint node="c1" summary="接头"/><bridge/><seg>t</seg></story>',
        )
        msgs = cm.get_messages()
        assert len(msgs) >= 3  # system + user + assistant
        assert msgs[0]["role"] == "system"


class TestBridgeText:
    def test_bridge_text_is_stored_for_next_round(self):
        from storyloom.parser.stream_parser import StreamParser
        from storyloom.core.state_manager import StateManager
        from storyloom.core.game_loop import GameState

        cm = ContextManager()
        cm.set_system_prompt("sys")
        xml = (
            '<story>\n'
            '<bridge/>\n'
            '<seg>你对耗子点了点头。</seg>\n'
            '<seg>耗子: 跟我来。</seg>\n'
            '</story>'
        )
        # GameLoop extracts bridge_text via StateManager after
        # processing events through the pipeline.
        parser = StreamParser()
        sm = StateManager(GameState([]))
        for line in xml.split("\n"):
            for event in parser.feed_line(line):
                list(sm.process(event))
        bridge_text = sm.get_bridge_text()
        cm.add_round("r1 context", xml, bridge_text=bridge_text)
        bridge = cm.get_last_bridge_text()
        assert "你对耗子点了点头" in bridge
        assert "耗子: 跟我来" in bridge

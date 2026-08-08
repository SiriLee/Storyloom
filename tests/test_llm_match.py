"""Tests for §7.8a LLM matching — ThinkingPreset, build_match_messages,
response parsing, MatchProcessor, and TaskPool integration.

TDD order (matches plan):
  1. TestThinkingPresets
  2. TestBuildMatchMessages
  3. TestParseMatchResponse
  4. TestMatchProcessor        (mock ApiClient)
  5. TestMatchProcessorIntegration  (real TaskPool)
"""

import threading
from collections import deque

import pytest

from storyloom.assets import AssetItem, AssetLibrary, AssetType, GameAssetRoster
from storyloom.io.api_client import ApiClient, ApiError
from storyloom.tasks import Task, TaskGenerator, TaskPool, TaskType


# ═══════════════════════════════════════════════════════════════════════
# FakeApiClient — controllable mock for MatchProcessor tests
# ═══════════════════════════════════════════════════════════════════════

class FakeApiClient:
    """Mock ApiClient that records calls and returns configurable responses.

    Args:
        responses: List of return values or exceptions to raise.
            Each ``chat()`` call pops the first item.
        model: Model string returned by the ``model`` property.
    """

    def __init__(self, responses=None, model="deepseek-v4-pro"):
        self.responses = list(responses) if responses else []
        self.calls: list[dict] = []
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def chat(self, messages, max_tokens=None, response_format=None,
             extra_params=None):
        """Record the call, return/pop the next response."""
        self.calls.append({
            "messages": messages,
            "max_tokens": max_tokens,
            "response_format": response_format,
            "extra_params": extra_params,
        })
        if not self.responses:
            return '{"selected": "hero"}'
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


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
    """Fresh GameAssetRoster with test entries."""
    r = GameAssetRoster("test_match", library)
    return r


@pytest.fixture
def roster_with_entries(roster):
    """Roster pre-populated with CHAR_PORTRAIT and BACKGROUND entries."""
    roster.add(AssetType.CHAR_PORTRAIT, "hero", "A brave knight in silver armor")
    roster.add(AssetType.CHAR_PORTRAIT, "mage", "A wise old wizard with a staff")
    roster.add(AssetType.CHAR_PORTRAIT, "ghost", "")  # no description
    roster.add(AssetType.BACKGROUND, "tavern", "A dimly lit medieval tavern")
    roster.add(AssetType.BACKGROUND, "forest", "A dark enchanted forest")
    return roster


# ═══════════════════════════════════════════════════════════════════════
# 1. TestThinkingPresets
# ═══════════════════════════════════════════════════════════════════════

class TestThinkingPresets:
    """get_thinking_params — model → extra_params mapping."""

    # ── DeepSeek ──────────────────────────────────────────────────────

    def test_deepseek_disabled(self):
        """DeepSeek model + disabled → thinking.type=disabled."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("deepseek-v4-pro", "disabled")
        assert params == {"thinking": {"type": "disabled"}}

    def test_deepseek_light(self):
        """DeepSeek model + light → thinking.type=enabled."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("deepseek-chat", "light")
        assert params == {"thinking": {"type": "enabled"}}

    def test_deepseek_enabled_is_empty(self):
        """DeepSeek enabled mode → empty (API default)."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("deepseek-v4-pro", "enabled")
        assert params == {}

    # ── Claude ────────────────────────────────────────────────────────

    def test_claude_disabled(self):
        """Claude model + disabled → thinking.type=disabled."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("claude-sonnet-5", "disabled")
        assert params == {"thinking": {"type": "disabled"}}

    def test_claude_light(self):
        """Claude model + light → includes budget_tokens=1024."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("claude-opus-4-8", "light")
        assert params["thinking"]["type"] == "enabled"
        assert params["thinking"]["budget_tokens"] == 1024

    def test_claude_enabled(self):
        """Claude model + enabled → includes budget_tokens=4096."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("claude-haiku-4-5", "enabled")
        assert params["thinking"]["type"] == "enabled"
        assert params["thinking"]["budget_tokens"] == 4096

    # ── Gemini ────────────────────────────────────────────────────────

    def test_gemini_disabled(self):
        """Gemini model + disabled → thinking_budget=0."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("gemini-2.5-pro", "disabled")
        assert params == {"thinking_config": {"thinking_budget": 0}}

    def test_gemini_light(self):
        """Gemini model + light → thinking_budget=512."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("gemini-2.0-flash", "light")
        assert params == {"thinking_config": {"thinking_budget": 512}}

    def test_gemini_enabled_is_empty(self):
        """Gemini enabled mode → empty (API default)."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("gemini-pro", "enabled")
        assert params == {}

    # ── Qwen ──────────────────────────────────────────────────────────

    def test_qwen_disabled(self):
        """Qwen model + disabled → enable_thinking=False (top-level, official API)."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("qwen-max", "disabled")
        assert params == {"enable_thinking": False}

    def test_qwen_light_is_empty(self):
        """Qwen light mode → empty (no specific param)."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("qwen-plus", "light")
        assert params == {}

    # ── GLM ───────────────────────────────────────────────────────────

    def test_glm_disabled(self):
        """GLM model + disabled → thinking.type=disabled."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("glm-4-plus", "disabled")
        assert params == {"thinking": {"type": "disabled"}}

    def test_glm_light(self):
        """GLM model + light → thinking.type=enabled."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("glm-4-flash", "light")
        assert params == {"thinking": {"type": "enabled"}}

    # ── OpenAI ────────────────────────────────────────────────────────

    def test_openai_disabled(self):
        """OpenAI GPT-5 + disabled → reasoning_effort=none."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("gpt-5.2", "disabled")
        assert params == {"reasoning_effort": "none"}

    def test_openai_light(self):
        """OpenAI GPT-5 + light → reasoning_effort=minimal."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("gpt-5-mini", "light")
        assert params == {"reasoning_effort": "minimal"}

    # ── Kimi / Moonshot ────────────────────────────────────────────────

    def test_kimi_disabled(self):
        """Kimi K2 + disabled → thinking.type=disabled."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("kimi-k2.6", "disabled")
        assert params == {"thinking": {"type": "disabled"}}

    def test_kimi_light(self):
        """Kimi K2 + light → thinking.type=enabled."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("kimi-k2.5", "light")
        assert params == {"thinking": {"type": "enabled"}}

    # ── Grok / xAI ─────────────────────────────────────────────────────

    def test_grok_disabled(self):
        """Grok + disabled → reasoning.enabled=false (boolean, not string)."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("grok-4.20", "disabled")
        assert params == {"reasoning": {"enabled": False}}

    def test_grok_light_is_empty(self):
        """Grok light mode → empty (API choice)."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("grok-3", "light")
        assert params == {}

    # ── Doubao / ByteDance ─────────────────────────────────────────────

    def test_doubao_disabled(self):
        """Doubao + disabled → thinking.type=disabled."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("doubao-seed-1.6", "disabled")
        assert params == {"thinking": {"type": "disabled"}}

    def test_doubao_light_is_auto(self):
        """Doubao light → thinking.type=auto (unique model-decides mode)."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("doubao-1.5-thinking-vision-pro", "light")
        assert params == {"thinking": {"type": "auto"}}

    # ── Unknown / edge cases ──────────────────────────────────────────

    def test_unknown_model_returns_empty(self):
        """Unknown model → empty params for all modes."""
        from storyloom.io.thinking import get_thinking_params
        assert get_thinking_params("some-unknown-model", "disabled") == {}
        assert get_thinking_params("some-unknown-model", "light") == {}
        assert get_thinking_params("some-unknown-model", "enabled") == {}

    def test_case_insensitive_match(self):
        """Model name matching is case-insensitive."""
        from storyloom.io.thinking import get_thinking_params
        params = get_thinking_params("DeepSeek-V4-Pro", "disabled")
        assert params == {"thinking": {"type": "disabled"}}

    def test_substring_match(self):
        """Model prefix can appear anywhere in the model string."""
        from storyloom.io.thinking import get_thinking_params
        # "deepseek" appears in the middle
        params = get_thinking_params("my-deepseek-model", "disabled")
        assert params == {"thinking": {"type": "disabled"}}


# ═══════════════════════════════════════════════════════════════════════
# 2. TestBuildMatchMessages
# ═══════════════════════════════════════════════════════════════════════

class TestBuildMatchMessages:
    """build_match_messages — prompt construction for LLM matching."""

    def test_returns_system_and_user(self, roster_with_entries):
        """Returns [system_msg, user_msg] with correct roles."""
        from storyloom.tasks._llm_match import build_match_messages
        msgs = build_match_messages(
            AssetType.CHAR_PORTRAIT, "hero", roster_with_entries,
        )
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"

    def test_user_message_includes_target_name(self, roster_with_entries):
        """Target name appears in the user message."""
        from storyloom.tasks._llm_match import build_match_messages
        msgs = build_match_messages(
            AssetType.CHAR_PORTRAIT, "Jack.smile", roster_with_entries,
        )
        assert "Jack.smile" in msgs[1]["content"]

    def test_includes_all_roster_entries(self, roster_with_entries):
        """Every roster entry's local_name appears in the user message."""
        from storyloom.tasks._llm_match import build_match_messages
        msgs = build_match_messages(
            AssetType.CHAR_PORTRAIT, "hero", roster_with_entries,
        )
        content = msgs[1]["content"]
        assert '"hero"' in content
        assert '"mage"' in content
        assert '"ghost"' in content

    def test_includes_local_descriptions(self, roster_with_entries):
        """Entries with descriptions include them in the message."""
        from storyloom.tasks._llm_match import build_match_messages
        msgs = build_match_messages(
            AssetType.CHAR_PORTRAIT, "hero", roster_with_entries,
        )
        content = msgs[1]["content"]
        assert "silver armor" in content
        assert "old wizard" in content

    def test_empty_description_shows_placeholder(self, roster_with_entries):
        """Entry with no description shows a placeholder text."""
        from storyloom.tasks._llm_match import build_match_messages
        msgs = build_match_messages(
            AssetType.CHAR_PORTRAIT, "hero", roster_with_entries,
        )
        content = msgs[1]["content"]
        # ghost has "" description → placeholder text replaces empty string
        assert '"ghost"' in content
        assert "(no description)" in content

    def test_only_same_asset_type_entries(self, roster_with_entries):
        """CHAR match only lists CHAR entries, not BACKGROUND."""
        from storyloom.tasks._llm_match import build_match_messages
        msgs = build_match_messages(
            AssetType.CHAR_PORTRAIT, "hero", roster_with_entries,
        )
        content = msgs[1]["content"]
        # BACKGROUND entries should NOT appear
        assert '"tavern"' not in content
        assert '"forest"' not in content

    def test_empty_roster_returns_empty_list(self, roster):
        """Empty roster → empty list (caller should handle)."""
        from storyloom.tasks._llm_match import build_match_messages
        msgs = build_match_messages(
            AssetType.CHAR_PORTRAIT, "hero", roster,
        )
        assert msgs == []

    def test_background_uses_scene_prompt(self, roster_with_entries):
        """BACKGROUND system prompt targets scene/location."""
        from storyloom.tasks._llm_match import build_match_messages
        msgs = build_match_messages(
            AssetType.BACKGROUND, "tavern", roster_with_entries,
        )
        assert "target scene name" in msgs[0]["content"]

    def test_char_portrait_uses_character_prompt(self, roster_with_entries):
        """CHAR_PORTRAIT system prompt targets character/portrait."""
        from storyloom.tasks._llm_match import build_match_messages
        msgs = build_match_messages(
            AssetType.CHAR_PORTRAIT, "hero", roster_with_entries,
        )
        assert "target character name" in msgs[0]["content"]


# ═══════════════════════════════════════════════════════════════════════
# 3. TestParseMatchResponse
# ═══════════════════════════════════════════════════════════════════════

class TestParseMatchResponse:
    """_parse_match_response — LLM response → local_name extraction."""

    @staticmethod
    def _entries(**kwargs):
        """Build a minimal entries dict for testing."""
        return kwargs

    def test_valid_json_matching_name(self):
        """Valid JSON with name in entries → returns the name."""
        from storyloom.tasks._llm_match import _parse_match_response
        entries = self._entries(hero=..., mage=...)
        result = _parse_match_response('{"selected": "hero"}', entries)
        assert result == "hero"

    def test_valid_json_non_matching_name_returns_none(self):
        """Valid JSON but selected name not in entries → None (triggers retry)."""
        from storyloom.tasks._llm_match import _parse_match_response
        entries = self._entries(hero=..., mage=...)
        result = _parse_match_response('{"selected": "villain"}', entries)
        assert result is None

    def test_invalid_json_finds_name_in_raw_text(self):
        """Non-JSON response that contains an entry name → extract it."""
        from storyloom.tasks._llm_match import _parse_match_response
        entries = self._entries(hero=..., mage=...)
        result = _parse_match_response('I think "hero" is the best match.', entries)
        assert result == "hero"

    def test_invalid_json_finds_substring_name(self):
        """Entry name appears as substring in raw text → found."""
        from storyloom.tasks._llm_match import _parse_match_response
        entries = self._entries(jack_smile=..., jack_frown=...)
        result = _parse_match_response(
            'The name jack_smile matches closely.', entries,
        )
        assert result == "jack_smile"

    def test_no_usable_name_returns_none(self):
        """Response contains no entry name → None."""
        from storyloom.tasks._llm_match import _parse_match_response
        entries = self._entries(hero=..., mage=...)
        result = _parse_match_response('garbage text with no match', entries)
        assert result is None

    def test_empty_entries_returns_none(self):
        """Empty entries dict → always None."""
        from storyloom.tasks._llm_match import _parse_match_response
        result = _parse_match_response('{"selected": "anything"}', {})
        assert result is None

    def test_partial_json_with_correct_name(self):
        """JSON-like text with the right name somewhere → found via substring."""
        from storyloom.tasks._llm_match import _parse_match_response
        entries = self._entries(forest=...)
        result = _parse_match_response(
            '{"selected": forest}', entries,
        )
        assert result == "forest"

    def test_json_extra_fields_ignored(self):
        """Extra JSON fields don't break parsing."""
        from storyloom.tasks._llm_match import _parse_match_response
        entries = self._entries(hero=...)
        result = _parse_match_response(
            '{"selected": "hero", "confidence": 0.95, "reason": "exact match"}',
            entries,
        )
        assert result == "hero"


# ═══════════════════════════════════════════════════════════════════════
# 4. TestMatchProcessor
# ═══════════════════════════════════════════════════════════════════════

class TestMatchProcessor:
    """MatchProcessor — LLM matching with retry and fallback."""

    # ── Successful match ──────────────────────────────────────────────

    def test_successful_match_sets_result(self, roster_with_entries):
        """LLM returns a valid name → task.result set, task completed."""
        from storyloom.tasks._llm_match import MatchProcessor

        api = FakeApiClient(responses=['{"selected": "hero"}'])
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        process = processor(AssetType.CHAR_PORTRAIT, "hero", roster_with_entries)
        process(task)

        assert task.result == "hero"
        assert task.completed is True

    def test_successful_match_uses_no_thinking(self, roster_with_entries):
        """First attempt uses disabled thinking mode."""
        from storyloom.tasks._llm_match import MatchProcessor

        api = FakeApiClient(responses=['{"selected": "hero"}'])
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        process = processor(AssetType.CHAR_PORTRAIT, "hero", roster_with_entries)
        process(task)

        # Verify the extra_params sent to the API
        assert len(api.calls) == 1
        extra = api.calls[0]["extra_params"]
        assert extra.get("thinking", {}).get("type") == "disabled"

    def test_fuzzy_match_via_llm(self, roster_with_entries):
        """LLM handles fuzzy match: "Jack.smile" → "jack_smile"."""
        from storyloom.tasks._llm_match import MatchProcessor

        roster_with_entries.add(
            AssetType.CHAR_PORTRAIT, "jack_smile",
            "Jack with a friendly smile",
        )

        api = FakeApiClient(responses=['{"selected": "jack_smile"}'])
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        process = processor(AssetType.CHAR_PORTRAIT, "Jack.smile",
                           roster_with_entries)
        process(task)

        assert task.result == "jack_smile"
        assert task.completed is True

    # ── API error → retry → success ──────────────────────────────────

    def test_api_error_retries_with_light_thinking(self, roster_with_entries):
        """First call raises ApiError → retry with light thinking → success."""
        from storyloom.tasks._llm_match import MatchProcessor

        api = FakeApiClient(responses=[
            ApiError("timeout"),                     # first attempt fails
            '{"selected": "mage"}',                  # retry succeeds
        ])
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        process = processor(AssetType.CHAR_PORTRAIT, "mage", roster_with_entries)
        process(task)

        assert task.result == "mage"
        assert task.completed is True
        # Two API calls were made
        assert len(api.calls) == 2
        # First call: disabled thinking
        assert api.calls[0]["extra_params"]["thinking"]["type"] == "disabled"
        # Second call: light thinking
        assert api.calls[1]["extra_params"]["thinking"]["type"] == "enabled"

    def test_invalid_response_retries_with_light(self, roster_with_entries):
        """LLM returns invalid name → retry with light thinking → success."""
        from storyloom.tasks._llm_match import MatchProcessor

        api = FakeApiClient(responses=[
            '{"selected": "nonexistent"}',           # invalid — not in roster
            '{"selected": "mage"}',                  # retry succeeds
        ])
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        process = processor(AssetType.CHAR_PORTRAIT, "wizard", roster_with_entries)
        process(task)

        assert task.result == "mage"
        assert len(api.calls) == 2
        # First call: disabled thinking
        assert api.calls[0]["extra_params"]["thinking"]["type"] == "disabled"
        # Retry: light thinking
        assert api.calls[1]["extra_params"]["thinking"]["type"] == "enabled"

    # ── Both attempts fail ────────────────────────────────────────────

    def test_both_api_errors_give_up(self, roster_with_entries):
        """Both attempts raise ApiError → task completes without result."""
        from storyloom.tasks._llm_match import MatchProcessor

        api = FakeApiClient(responses=[
            ApiError("network error"),
            ApiError("timeout"),
        ])
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        process = processor(AssetType.CHAR_PORTRAIT, "hero", roster_with_entries)
        process(task)

        assert task.completed is True
        assert task.result is None       # UI will display no asset (silent degradation)
        assert task.error is not None    # failure must be recorded

    def test_both_invalid_responses_give_up(self, roster_with_entries):
        """Both LLM responses return invalid names → give up."""
        from storyloom.tasks._llm_match import MatchProcessor

        api = FakeApiClient(responses=[
            '{"selected": "villain"}',               # invalid
            '{"selected": "dragon"}',                # also invalid
        ])
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        process = processor(AssetType.CHAR_PORTRAIT, "hero", roster_with_entries)
        process(task)

        assert task.completed is True
        assert task.result is None
        assert task.error is not None    # failure must be recorded
        assert len(api.calls) == 2

    def test_mixed_api_error_then_invalid_give_up(self, roster_with_entries):
        """ApiError then invalid response → give up."""
        from storyloom.tasks._llm_match import MatchProcessor

        api = FakeApiClient(responses=[
            ApiError("server error"),
            '{"selected": "dragon"}',                # invalid
        ])
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        process = processor(AssetType.CHAR_PORTRAIT, "hero", roster_with_entries)
        process(task)

        assert task.completed is True
        assert task.result is None
        assert task.error is not None    # failure must be recorded
        assert len(api.calls) == 2

    # ── Empty roster ──────────────────────────────────────────────────

    def test_empty_roster_completes_immediately(self, roster):
        """Empty roster → complete immediately, no API call."""
        from storyloom.tasks._llm_match import MatchProcessor

        api = FakeApiClient()
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        process = processor(AssetType.CHAR_PORTRAIT, "hero", roster)
        process(task)

        assert task.completed is True
        assert task.result is None
        assert len(api.calls) == 0            # never called

    # ── Background matching ───────────────────────────────────────────

    def test_background_match_success(self, roster_with_entries):
        """BACKGROUND type matching works the same as CHAR."""
        from storyloom.tasks._llm_match import MatchProcessor

        api = FakeApiClient(responses=['{"selected": "tavern"}'])
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 10, AssetType.BACKGROUND)
        process = processor(AssetType.BACKGROUND, "tavern_inn",
                           roster_with_entries)
        process(task)

        assert task.result == "tavern"
        assert task.completed is True

    # ── ApiClient.model property used for thinking params ─────────────

    def test_claude_model_uses_claude_thinking_params(self, roster_with_entries):
        """When ApiClient.model is a Claude model, use Claude thinking params."""
        from storyloom.tasks._llm_match import MatchProcessor

        api = FakeApiClient(
            responses=['{"selected": "hero"}'],
            model="claude-sonnet-5",
        )
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        process = processor(AssetType.CHAR_PORTRAIT, "hero", roster_with_entries)
        process(task)

        # Claude disabled → should have thinking.type=disabled (no budget)
        extra = api.calls[0]["extra_params"]
        assert extra == {"thinking": {"type": "disabled"}}


# ═══════════════════════════════════════════════════════════════════════
# 5. TestMatchProcessorIntegration
# ═══════════════════════════════════════════════════════════════════════

class TestMatchProcessorIntegration:
    """MatchProcessor via TaskPool — full async pipeline."""

    def test_full_match_via_task_pool(self, roster_with_entries):
        """Task submitted to TaskPool → MatchProcessor runs → result set."""
        from storyloom.tasks._llm_match import MatchProcessor

        api = FakeApiClient(responses=['{"selected": "mage"}'])
        processor = MatchProcessor(api)

        task = Task(TaskType.MATCH, 5, AssetType.CHAR_PORTRAIT)
        process = processor(AssetType.CHAR_PORTRAIT, "old wizard",
                           roster_with_entries)
        task.process = process

        with TaskPool(max_workers=1) as pool:
            pool.submit(task)
            task.wait(timeout=2.0)

        assert task.completed is True
        assert task.result == "mage"
        assert task.error is None

    def test_match_via_task_generator_pipeline(self, roster_with_entries):
        """Full pipeline: TaskGenerator enqueue → TaskPool → EventDispatcher.

        This is the actual production flow — verifies that MatchProcessor
        works as a drop-in replacement for the stub process_factory.
        """
        from storyloom.tasks._llm_match import MatchProcessor
        from storyloom.core.event_dispatcher import EventDispatcher
        from storyloom.parser.stream_parser import Event, EventType

        # Bootstrap: add stub asset to library so binding works
        roster_with_entries._library.add(
            AssetType.CHAR_PORTRAIT, "stub", "temp",
            asset_id="__stub__",
        )
        roster_with_entries.set_target(
            AssetType.CHAR_PORTRAIT, "hero", "__stub__",
        )

        api = FakeApiClient(responses=['{"selected": "hero"}'])
        match_proc = MatchProcessor(api)

        q: deque[Task] = deque()
        pool = TaskPool(max_workers=2)

        # stub for GENERATE (not exercised in this test)
        def _stub_generate(atype, lname, _roster):
            def _p(task):
                pass
            return _p

        gen = TaskGenerator(q, roster_with_entries,
                           match_processor=match_proc,
                           generate_processor=_stub_generate,
                           task_pool=pool)
        dispatcher = EventDispatcher(q, roster_with_entries)

        # Simulate: SEGMENT with unknown char → program match fails → LLM match
        event = Event(EventType.SEGMENT, 5, {
            "text": "A hero appears.",
            "position": "pre",
            "char": "hero_knight",      # not exact — needs LLM match
        })

        gen.enqueue(event)
        result = dispatcher.consume_event(event)

        assert result["type"] == "segment"
        assert "assets" in event.payload
        assert event.payload["assets"] == {
            AssetType.CHAR_PORTRAIT.value: "__stub__",
        }

        pool.shutdown()

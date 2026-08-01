"""Tests for co-create validator and flow."""
import pytest
from storyloom.core.co_create import CoCreateValidator, CoCreateFlow, CoCreateError
from storyloom.io.api_client import ApiError
from storyloom.i18n import init_i18n
init_i18n("en")  # Use English for deterministic test output


# ══════════════════════════════════════════════════════════════════════════
# Full JSON generation response (v2 format)
# ══════════════════════════════════════════════════════════════════════════

FULL_GENERATION_RESPONSE = """{
  "story_config": {
    "tier": "medium",
    "title": "Neon Depths",
    "language": "zh-CN",
    "premise": "2087年新东京，数据是唯一货币。林焰，前荒坂安全顾问转自由佣兵，卷入了一场争夺被盗生物芯片的追逐。"
  },
  "characters": [
    {
      "name": "林焰",
      "role": "protagonist",
      "description": "前荒坂安全顾问，现自由佣兵。冷静、道德灰色、 fiercely loyal",
      "appearance": "身材高大，眼神锐利，黑色短发，下颌有一道淡淡的疤痕。穿着磨损的合成皮外套搭配战术装备。"
    },
    {
      "name": "耗子",
      "role": "supporting",
      "description": "地下情报贩子，有旧债未清。滑头、足智多谋、偏执",
      "appearance": "矮小精瘦，动作敏捷，增强眼睛扫描数据流时闪烁蓝光。穿着褪色的街头时尚。"
    },
    {
      "name": "美智子",
      "role": "supporting",
      "description": "荒坂安全主管，前导师。忠于职责与旧日情谊之间挣扎",
      "appearance": "穿着无可挑剔的黑色西装，银发紧束。冷笑中带着洞察一切的眼神。"
    }
  ],
  "locations": [
    {
      "id": "neo_tokyo_streets",
      "name": "新东京街头",
      "description": "午夜霓虹闪烁的街道，全息广告在摩天大楼表面闪烁。"
    },
    {
      "id": "underground_bar",
      "name": "鼠巢酒吧",
      "description": "面馆下方的昏暗地下酒吧，闪烁的霓虹招牌。"
    }
  ],
  "variables": [
    {"name": "体力", "type": "number", "initial": 80},
    {"name": "信任度", "type": "number", "initial": 10},
    {"name": "所属势力", "type": "string", "initial": "自由佣兵"}
  ],
  "outline": [
    {
      "id": "ch1_intro",
      "title": "霓虹深渊",
      "goal": "在地下城酒吧感受氛围，获取情报",
      "routes": [
        {"condition": null, "target": "ch2_meeting"}
      ]
    },
    {
      "id": "ch2_meeting",
      "title": "地下交易",
      "goal": "与耗子会面完成芯片交易",
      "routes": [
        {"condition": "信任度 >= 30", "target": "ch3_ally"},
        {"condition": "信任度 < 30", "target": "ch3_betrayal"}
      ]
    },
    {
      "id": "ch3_ally",
      "title": "盟友之路",
      "goal": "通过地下网络逃离",
      "routes": [
        {"condition": null, "target": "ch4_safehouse"}
      ]
    },
    {
      "id": "ch3_betrayal",
      "title": "背叛之路",
      "goal": "杀出重围",
      "routes": [
        {"condition": null, "target": "ch4_safehouse"}
      ]
    },
    {
      "id": "ch4_safehouse",
      "title": "安全屋",
      "goal": "揭开芯片秘密",
      "routes": []
    }
  ]
}"""


# ══════════════════════════════════════════════════════════════════════════
# CoCreateValidator tests
# ══════════════════════════════════════════════════════════════════════════

class TestCoCreateValidatorJson:
    """Tests for validate_json()."""

    def test_valid_json_returns_dict(self):
        data, error = CoCreateValidator.validate_json('{"a": 1}')
        assert data == {"a": 1}
        assert error is None

    def test_invalid_json_returns_error(self):
        data, error = CoCreateValidator.validate_json("not json")
        assert data is None
        assert error is not None
        assert "Invalid JSON format" in error

    def test_markdown_fence_is_stripped(self):
        text = '```json\n{"a": 1}\n```'
        data, error = CoCreateValidator.validate_json(text)
        assert data == {"a": 1}
        assert error is None

    def test_markdown_fence_no_lang_tag(self):
        text = '```\n{"a": 1}\n```'
        data, error = CoCreateValidator.validate_json(text)
        assert data == {"a": 1}
        assert error is None

    def test_array_root_is_rejected(self):
        data, error = CoCreateValidator.validate_json('[1, 2, 3]')
        assert data is None
        assert error is not None
        assert "object" in error.lower()

    def test_string_root_is_rejected(self):
        data, error = CoCreateValidator.validate_json('"hello"')
        assert data is None
        assert error is not None

    def test_empty_string_is_invalid_json(self):
        data, error = CoCreateValidator.validate_json("")
        assert data is None
        assert error is not None


class TestCoCreateValidatorStoryConfig:
    """Tests for validate_story_config()."""

    def test_valid_story_config_passes(self):
        data = {
            "story_config": {
                "tier": "medium",
                "title": "霓虹深渊",
                "language": "zh-CN",
                "premise": "一个赛博朋克故事",
            }
        }
        errors = CoCreateValidator.validate_story_config(data)
        assert errors == []

    def test_invalid_tier(self):
        data = {"story_config": {"tier": "epic", "title": "测试", "language": "en", "premise": "test"}}
        errors = CoCreateValidator.validate_story_config(data)
        assert any("tier" in e for e in errors)

    def test_title_too_long(self):
        data = {"story_config": {"tier": "short", "title": "a" * 31, "language": "en", "premise": "test"}}
        errors = CoCreateValidator.validate_story_config(data)
        assert any("title" in e.lower() and "long" in e.lower() for e in errors)

    def test_empty_title(self):
        data = {"story_config": {"tier": "short", "title": "", "language": "en", "premise": "test"}}
        errors = CoCreateValidator.validate_story_config(data)
        assert any("title" in e.lower() for e in errors)

    def test_invalid_language(self):
        data = {"story_config": {"tier": "short", "title": "测试", "language": "fr", "premise": "test"}}
        errors = CoCreateValidator.validate_story_config(data)
        assert any("language" in e for e in errors)

    def test_empty_premise(self):
        data = {"story_config": {"tier": "short", "title": "测试", "language": "en", "premise": ""}}
        errors = CoCreateValidator.validate_story_config(data)
        assert any("premise" in e.lower() for e in errors)

    def test_missing_story_config_key(self):
        data = {}
        errors = CoCreateValidator.validate_story_config(data)
        assert len(errors) == 1
        assert "object" in errors[0].lower()


class TestCoCreateValidatorCharacters:
    """Tests for validate_characters()."""

    def test_valid_characters_passes(self):
        data = {
            "characters": [
                {"name": "林焰", "role": "protagonist", "description": "佣兵", "appearance": "高大"},
                {"name": "耗子", "role": "supporting", "description": "情报贩子", "appearance": "矮小"},
            ]
        }
        errors = CoCreateValidator.validate_characters(data)
        assert errors == []

    def test_antagonist_role_is_valid(self):
        data = {
            "characters": [
                {"name": "Hero", "role": "protagonist", "description": "hero desc", "appearance": "tall"},
                {"name": "Villain", "role": "antagonist", "description": "villain desc", "appearance": "dark"},
            ]
        }
        errors = CoCreateValidator.validate_characters(data)
        assert errors == []

    def test_empty_array_is_rejected(self):
        data = {"characters": []}
        errors = CoCreateValidator.validate_characters(data)
        assert len(errors) >= 1

    def test_missing_protagonist(self):
        data = {
            "characters": [
                {"name": "NPC", "role": "supporting", "description": "someone", "appearance": "plain"},
            ]
        }
        errors = CoCreateValidator.validate_characters(data)
        assert any("protagonist" in e.lower() for e in errors)

    def test_multiple_protagonists(self):
        data = {
            "characters": [
                {"name": "A", "role": "protagonist", "description": "d", "appearance": "a"},
                {"name": "B", "role": "protagonist", "description": "d", "appearance": "b"},
            ]
        }
        errors = CoCreateValidator.validate_characters(data)
        assert any("2" in e or "exactly 1" in e.lower() for e in errors)

    def test_invalid_role(self):
        data = {
            "characters": [
                {"name": "Hero", "role": "protagonist", "description": "d", "appearance": "a"},
                {"name": "NPC", "role": "extra", "description": "d", "appearance": "b"},
            ]
        }
        errors = CoCreateValidator.validate_characters(data)
        assert any("role" in e for e in errors)

    def test_missing_required_field(self):
        data = {
            "characters": [
                {"name": "Hero", "role": "protagonist", "description": "", "appearance": "tall"},
            ]
        }
        errors = CoCreateValidator.validate_characters(data)
        assert any("description" in e for e in errors)

    def test_missing_name(self):
        data = {
            "characters": [
                {"name": "", "role": "protagonist", "description": "someone", "appearance": "tall"},
            ]
        }
        errors = CoCreateValidator.validate_characters(data)
        assert any("name" in e for e in errors)


class TestCoCreateValidatorLocations:
    """Tests for validate_locations()."""

    def test_valid_locations_passes(self):
        data = {
            "locations": [
                {"id": "neo_tokyo_streets", "name": "新东京街头", "description": "霓虹街道"},
                {"id": "underground_bar", "name": "鼠巢", "description": "地下酒吧"},
            ]
        }
        errors = CoCreateValidator.validate_locations(data)
        assert errors == []

    def test_empty_array_is_rejected(self):
        data = {"locations": []}
        errors = CoCreateValidator.validate_locations(data)
        assert len(errors) >= 1

    def test_non_snake_case_id(self):
        data = {
            "locations": [
                {"id": "Neo Tokyo", "name": "新东京", "description": "desc"},
            ]
        }
        errors = CoCreateValidator.validate_locations(data)
        assert any("snake_case" in e for e in errors)

    def test_empty_id(self):
        data = {
            "locations": [
                {"id": "", "name": "某地", "description": "desc"},
            ]
        }
        errors = CoCreateValidator.validate_locations(data)
        assert any("id" in e for e in errors)

    def test_duplicate_id(self):
        data = {
            "locations": [
                {"id": "same_id", "name": "A", "description": "desc a"},
                {"id": "same_id", "name": "B", "description": "desc b"},
            ]
        }
        errors = CoCreateValidator.validate_locations(data)
        assert any("unique" in e for e in errors)

    def test_missing_name(self):
        data = {
            "locations": [
                {"id": "test_loc", "name": "", "description": "desc"},
            ]
        }
        errors = CoCreateValidator.validate_locations(data)
        assert any("name" in e for e in errors)

    def test_missing_description(self):
        data = {
            "locations": [
                {"id": "test_loc", "name": "某地", "description": ""},
            ]
        }
        errors = CoCreateValidator.validate_locations(data)
        assert any("description" in e for e in errors)


class TestCoCreateValidatorVariables:
    """Tests for validate_variables()."""

    def test_valid_variables_passes(self):
        data = {
            "variables": [
                {"name": "体力", "type": "number", "initial": 80},
                {"name": "信任度", "type": "number", "initial": 10},
                {"name": "所属势力", "type": "string", "initial": "自由佣兵"},
            ]
        }
        errors = CoCreateValidator.validate_variables(data)
        assert errors == []

    def test_count_exceeds_cap(self):
        data = {
            "variables": [
                {"name": f"var{i}", "type": "number", "initial": 50}
                for i in range(7)
            ]
        }
        errors = CoCreateValidator.validate_variables(data)
        assert any("exceeds maximum 6" in e for e in errors)

    def test_duplicate_in_same_scope(self):
        data = {
            "variables": [
                {"name": "体力", "type": "number", "initial": 80},
                {"name": "体力", "type": "number", "initial": 50},
            ]
        }
        errors = CoCreateValidator.validate_variables(data)
        assert any("Duplicate" in e for e in errors)

    def test_duplicate_across_scopes_ok(self):
        data = {
            "variables": [
                {"scope": "Alice", "name": "好感度", "type": "number", "initial": 50},
                {"scope": "Bob", "name": "好感度", "type": "number", "initial": 30},
            ]
        }
        errors = CoCreateValidator.validate_variables(data)
        assert errors == []

    def test_number_out_of_bounds(self):
        data = {
            "variables": [
                {"name": "体力", "type": "number", "initial": 150},
            ]
        }
        errors = CoCreateValidator.validate_variables(data)
        assert any("out of range" in e for e in errors)

    def test_number_below_zero(self):
        data = {
            "variables": [
                {"name": "体力", "type": "number", "initial": -10},
            ]
        }
        errors = CoCreateValidator.validate_variables(data)
        assert any("out of range" in e for e in errors)

    def test_bool_rejected_for_number(self):
        """bool is an int subclass — must be rejected per plan §A.5."""
        data = {
            "variables": [
                {"name": "flag", "type": "number", "initial": True},
            ]
        }
        errors = CoCreateValidator.validate_variables(data)
        assert any("integer" in e.lower() or "bool" in str(e).lower() for e in errors)

    def test_string_empty_initial(self):
        data = {
            "variables": [
                {"name": "tag", "type": "string", "initial": ""},
            ]
        }
        errors = CoCreateValidator.validate_variables(data)
        assert any("empty" in e.lower() or "non-empty" in e.lower() for e in errors)

    def test_duplicate_names(self):
        data = {
            "variables": [
                {"name": "体力", "type": "number", "initial": 80},
                {"name": "体力", "type": "number", "initial": 50},
            ]
        }
        errors = CoCreateValidator.validate_variables(data)
        assert any("duplicate" in e.lower() for e in errors)

    def test_invalid_type(self):
        data = {
            "variables": [
                {"name": "x", "type": "boolean", "initial": True},
            ]
        }
        errors = CoCreateValidator.validate_variables(data)
        assert any("type" in e for e in errors)

    def test_empty_variables_array_passes(self):
        data = {"variables": []}
        errors = CoCreateValidator.validate_variables(data)
        assert errors == []


class TestCoCreateValidatorOutline:
    """Tests for validate_outline_cross_ref()."""

    def test_valid_outline_passes(self):
        outline = [
            {"id": "ch1", "title": "开始", "goal": "start", "routes": [
                {"condition": None, "target": "ch2"},
            ]},
            {"id": "ch2", "title": "结束", "goal": "end", "routes": []},
        ]
        errors = CoCreateValidator.validate_outline_cross_ref(outline, ["hp"])
        assert errors == []

    def test_empty_array_is_rejected(self):
        errors = CoCreateValidator.validate_outline_cross_ref([], [])
        assert len(errors) >= 1

    def test_route_target_missing(self):
        outline = [
            {"id": "ch1", "title": "t", "goal": "g", "routes": [
                {"condition": None, "target": "ch99"},
            ]},
            {"id": "ch2", "title": "t", "goal": "g", "routes": []},
        ]
        errors = CoCreateValidator.validate_outline_cross_ref(outline, [])
        assert any("ch99" in e for e in errors)

    def test_final_node_has_branches(self):
        outline = [
            {"id": "ch1", "title": "t", "goal": "g", "routes": [
                {"condition": None, "target": "ch2"},
            ]},
            {"id": "ch2", "title": "t", "goal": "g", "routes": [
                {"condition": None, "target": "ch1"},
            ]},
        ]
        errors = CoCreateValidator.validate_outline_cross_ref(outline, [])
        assert any("final" in e.lower() for e in errors)

    def test_duplicate_node_ids(self):
        outline = [
            {"id": "ch1", "title": "a", "goal": "g", "routes": []},
            {"id": "ch1", "title": "b", "goal": "g", "routes": []},
        ]
        errors = CoCreateValidator.validate_outline_cross_ref(outline, [])
        assert any("duplicate" in e.lower() for e in errors)


# ══════════════════════════════════════════════════════════════════════════
# Integration helpers
# ══════════════════════════════════════════════════════════════════════════

class MockApiClient:
    """Mock API client that returns predefined responses."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.messages_history = []

    def chat(self, messages, max_tokens=None, response_format=None, extra_params=None):
        self.messages_history.append(messages)
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        if self.responses:
            return self.responses[-1]
        return ""

    def stream_chat(self, messages, max_tokens=None, response_format=None, extra_params=None):
        return self.chat(messages)


def make_mock_api_client():
    """Create a bare MockApiClient for send() error tests."""
    return MockApiClient()


# ══════════════════════════════════════════════════════════════════════════
# CoCreateFlow state machine tests
# ══════════════════════════════════════════════════════════════════════════

class TestCoCreateFlowStateMachineProperties:
    """Tests for phase, result properties."""

    def test_initial_phase_is_init(self):
        api = MockApiClient()
        flow = CoCreateFlow(api)
        assert flow.phase == "init"

    def test_result_is_none_initially(self):
        api = MockApiClient()
        flow = CoCreateFlow(api)
        assert flow.result is None

    def test_phase_transitions_after_start(self):
        api = MockApiClient()
        flow = CoCreateFlow(api)
        flow.start()
        assert flow.phase == "awaiting_idea"

    def test_abort_changes_phase(self):
        api = MockApiClient()
        flow = CoCreateFlow(api)
        flow.abort()
        assert flow.phase == "aborted"


class TestCoCreateFlowStart:
    """Tests for start() method."""

    def test_start_returns_awaiting_idea_event(self):
        api = MockApiClient()
        flow = CoCreateFlow(api)
        event = flow.start()
        assert event["phase"] == "awaiting_idea"
        assert "prompt" in event
        assert isinstance(event["prompt"], str)
        assert len(event["prompt"]) > 0

    def test_start_sets_phase(self):
        api = MockApiClient()
        flow = CoCreateFlow(api)
        assert flow.phase == "init"
        flow.start()
        assert flow.phase == "awaiting_idea"

    def test_start_raises_if_already_started(self):
        api = MockApiClient()
        flow = CoCreateFlow(api)
        flow.start()
        with pytest.raises(RuntimeError, match="already started"):
            flow.start()


class TestCoCreateFlowSend:
    """Tests for send() method — pure message forward, returns str."""

    def test_send_before_start_raises(self):
        api = MockApiClient()
        flow = CoCreateFlow(api)
        with pytest.raises(RuntimeError, match="call start\\(\\) first"):
            flow.send("anything")

    def test_send_after_abort_raises(self):
        api = MockApiClient()
        flow = CoCreateFlow(api)
        flow._phase = "aborted"
        with pytest.raises(RuntimeError, match="was aborted"):
            flow.send("anything")

    def test_send_empty_input_raises_value_error(self):
        api = MockApiClient()
        flow = CoCreateFlow(api)
        flow.start()
        with pytest.raises(ValueError, match="cannot be empty"):
            flow.send("")

    def test_send_returns_str_not_dict(self):
        api = MockApiClient()
        api.chat = lambda msgs: "What era would you like?"
        flow = CoCreateFlow(api)
        flow.start()

        reply = flow.send("A cyberpunk romance in Neo Tokyo")

        assert isinstance(reply, str)
        assert reply == "What era would you like?"
        assert flow.phase == "awaiting_answer"

    def test_send_from_awaiting_idea_transitions_to_awaiting_answer(self):
        api = MockApiClient()
        api.chat = lambda msgs: "First question?"
        flow = CoCreateFlow(api)
        assert flow.phase == "init"
        flow.start()
        assert flow.phase == "awaiting_idea"
        flow.send("my idea")
        assert flow.phase == "awaiting_answer"

    def test_send_no_keyword_detection(self):
        """send() does NOT parse user input for start/quit keywords."""
        api = MockApiClient()
        api.chat = lambda msgs: "Interesting, tell me more."
        flow = CoCreateFlow(api)
        flow._phase = "awaiting_answer"
        flow._messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "idea"},
            {"role": "assistant", "content": "q"},
        ]

        # "开始" is just forwarded as text — no generation triggered
        reply = flow.send("开始")
        assert isinstance(reply, str)
        assert reply == "Interesting, tell me more."
        assert flow.phase == "awaiting_answer"

    def test_send_appends_to_messages(self):
        api = MockApiClient()
        api.chat = lambda msgs: "reply"
        flow = CoCreateFlow(api)
        flow._phase = "awaiting_answer"
        flow._messages = [
            {"role": "system", "content": "test"},
        ]

        flow.send("hello")

        user_msgs = [m for m in flow._messages if m["role"] == "user"]
        assert any("hello" in m["content"] for m in user_msgs)
        assistant_msgs = [m for m in flow._messages if m["role"] == "assistant"]
        assert any("reply" in m["content"] for m in assistant_msgs)


class TestCoCreateFlowSendEndToEnd:
    """End-to-end tests — start → send → generate → complete."""

    def test_full_flow_success(self):
        """Idea → Q&A → generate → complete."""
        api = MockApiClient(responses=[
            "你想玩什么题材的故事？",
            FULL_GENERATION_RESPONSE,
        ])
        flow = CoCreateFlow(api)
        flow.start()
        reply = flow.send("赛博朋克冒险")
        assert reply == "你想玩什么题材的故事？"

        result = flow.generate()
        assert result["story_config"]["tier"] == "medium"
        assert result["story_config"]["title"] == "Neon Depths"
        assert len(result["variables"]) == 3
        assert len(result["outline"]) == 5
        assert "ch1_intro [active]" in result["outline_text"]
        assert flow.phase == "complete"
        assert flow.result is result

    def test_multi_turn_qa_before_generate(self):
        """Multiple Q&A rounds, then generate."""
        api = MockApiClient(responses=[
            "Q1: What genre?",
            "Q2: What era?",
            FULL_GENERATION_RESPONSE,
        ])
        flow = CoCreateFlow(api)
        flow.start()

        r1 = flow.send("idea")
        assert r1 == "Q1: What genre?"

        r2 = flow.send("cyberpunk")
        assert r2 == "Q2: What era?"

        result = flow.generate()
        assert result["story_config"]["title"] == "Neon Depths"

    def test_user_aborts_during_qa(self):
        """abort() changes phase, independent of send()."""
        api = MockApiClient(responses=["What genre?"])
        flow = CoCreateFlow(api)
        flow.start()
        flow.send("科幻")

        flow.abort()
        assert flow.phase == "aborted"

    def test_generate_validation_fails_raises_cocreate_error(self):
        """Parse validation failure → CoCreateError with phase='generate_parse'."""
        api = make_mock_api_client()
        # Return invalid JSON (array instead of object)
        api.chat = lambda msgs, **kw: '[1, 2, 3]'
        flow = CoCreateFlow(api)
        flow._messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "idea"},
            {"role": "assistant", "content": "q"},
        ]
        flow._phase = "awaiting_answer"

        with pytest.raises(CoCreateError) as exc_info:
            flow.generate()
        assert exc_info.value.phase == "generate_parse"
        assert flow._retry_state is not None
        assert flow._retry_state[0] == "generate_parse"

    def test_generate_field_validation_fails(self):
        """Field validation errors → CoCreateError with phase='generate_parse'."""
        api = make_mock_api_client()
        # Return JSON with invalid tier
        api.chat = lambda msgs, **kw: (
            '{"story_config":{"tier":"epic","title":"Test","language":"en","premise":"p"},'
            '"characters":[{"name":"Hero","role":"protagonist","description":"d","appearance":"a"}],'
            '"locations":[{"id":"test","name":"Test","description":"desc"}],'
            '"variables":[],'
            '"outline":[{"id":"ch1","title":"Start","goal":"Begin","routes":[]}]}'
        )
        flow = CoCreateFlow(api)
        flow._messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "idea"},
            {"role": "assistant", "content": "q"},
        ]
        flow._phase = "awaiting_answer"

        with pytest.raises(CoCreateError) as exc_info:
            flow.generate()
        assert exc_info.value.phase == "generate_parse"
        assert "tier" in exc_info.value.message.lower()

    def test_retry_generate_after_parse_failure(self):
        """After parse failure, retry_generate() adds correction, re-calls API."""
        BAD_JSON = '{"bad": "json"}'
        api = MockApiClient(responses=[BAD_JSON, FULL_GENERATION_RESPONSE])
        flow = CoCreateFlow(api)
        flow._messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "idea"},
            {"role": "assistant", "content": "q"},
        ]
        flow._phase = "awaiting_answer"

        # First generate() fails on parse → CoCreateError
        try:
            flow.generate()
        except CoCreateError:
            pass

        # retry_generate() adds correction, calls API, succeeds
        result = flow.retry_generate()
        assert result["story_config"]["tier"] == "medium"
        assert flow.phase == "complete"
        assert flow._retry_state is None

    def test_retry_generate_raises_when_no_failure(self):
        """retry_generate() raises RuntimeError when no previous failure."""
        api = make_mock_api_client()
        flow = CoCreateFlow(api)
        flow._phase = "awaiting_answer"

        with pytest.raises(RuntimeError, match="No failed generate"):
            flow.retry_generate()

    def test_generate_before_first_send_raises(self):
        """generate() before any Q&A raises RuntimeError."""
        api = MockApiClient()
        flow = CoCreateFlow(api)
        flow.start()

        with pytest.raises(RuntimeError, match="Cannot generate"):
            flow.generate()


class TestCoCreateFlowSendErrors:
    """Tests for send() error handling — raises CoCreateError, manual retry."""

    def test_send_raises_cocreate_error_on_api_failure(self):
        """API fails → CoCreateError raised with phase='send'."""
        api = make_mock_api_client()
        api.chat = lambda msgs: (_ for _ in ()).throw(ApiError("fail"))
        flow = CoCreateFlow(api)
        flow.start()

        with pytest.raises(CoCreateError) as exc_info:
            flow.send("idea")
        assert exc_info.value.phase == "send"
        assert "fail" in exc_info.value.message
        # Phase unchanged — user can retry
        assert flow.phase == "awaiting_idea"

    def test_send_preserves_message_on_failure(self):
        """API failure keeps user message in _messages for retry."""
        api = make_mock_api_client()
        api.chat = lambda msgs: (_ for _ in ()).throw(ApiError("fail"))
        flow = CoCreateFlow(api)
        flow.start()

        try:
            flow.send("retry me")
        except CoCreateError:
            pass

        # User message must remain for manual retry
        user_msgs = [m for m in flow._messages if m["role"] == "user"]
        assert any("retry me" in m.get("content", "") for m in user_msgs)

    def test_send_sets_retry_state_on_failure(self):
        """API failure sets _retry_state to ('send', user_input)."""
        api = make_mock_api_client()
        api.chat = lambda msgs: (_ for _ in ()).throw(ApiError("fail"))
        flow = CoCreateFlow(api)
        flow.start()

        try:
            flow.send("my idea")
        except CoCreateError:
            pass

        assert flow._retry_state is not None
        assert flow._retry_state[0] == "send"
        assert flow._retry_state[1] == "my idea"

    def test_retry_send_raises_when_no_failure(self):
        """retry_send() raises RuntimeError when no previous failure."""
        api = make_mock_api_client()
        flow = CoCreateFlow(api)
        flow.start()

        with pytest.raises(RuntimeError, match="No failed send"):
            flow.retry_send()

    def test_retry_send_reattempts_api(self):
        """After send fails, retry_send() re-calls API and returns reply."""
        api = make_mock_api_client()
        api.chat = lambda msgs: "Hello from retry!"
        flow = CoCreateFlow(api)
        flow.start()

        # Simulate a failed send
        flow._retry_state = ("send", "idea")
        flow._messages.append({"role": "user", "content": "idea"})

        reply = flow.retry_send()
        assert reply == "Hello from retry!"
        assert flow.phase == "awaiting_answer"
        assert flow._retry_state is None  # cleared

    def test_retry_send_clears_state_on_success(self):
        """retry_send() clears _retry_state after success."""
        api = make_mock_api_client()
        api.chat = lambda msgs: "ok"
        flow = CoCreateFlow(api)
        flow.start()
        flow._retry_state = ("send", "idea")
        flow._messages.append({"role": "user", "content": "idea"})

        flow.retry_send()
        assert flow._retry_state is None

    def test_retry_send_reraises_api_error(self):
        """retry_send() raises CoCreateError again if API still fails."""
        api = make_mock_api_client()
        api.chat = lambda msgs: (_ for _ in ()).throw(ApiError("still broken"))
        flow = CoCreateFlow(api)
        flow.start()
        flow._retry_state = ("send", "idea")
        flow._messages.append({"role": "user", "content": "idea"})

        with pytest.raises(CoCreateError) as exc_info:
            flow.retry_send()
        assert "still broken" in exc_info.value.message
        # _retry_state preserved for another attempt
        assert flow._retry_state is not None


class TestGenerate:
    """Tests for generate() — JSON prompt, parse, validate, return dict."""

    def test_generate_success(self):
        api = MockApiClient(responses=[FULL_GENERATION_RESPONSE])
        flow = CoCreateFlow(api)
        flow._messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "idea"},
            {"role": "assistant", "content": "q"},
        ]
        flow._phase = "awaiting_answer"

        result = flow.generate()
        assert isinstance(result, dict)
        assert result["story_config"]["tier"] == "medium"
        assert len(result["outline"]) == 5
        assert "outline_text" in result
        assert flow.phase == "complete"

    def test_generate_returns_dict_with_all_keys(self):
        api = MockApiClient(responses=[FULL_GENERATION_RESPONSE])
        flow = CoCreateFlow(api)
        flow._messages = [
            {"role": "system", "content": "test"},
            {"role": "user", "content": "idea"},
            {"role": "assistant", "content": "q"},
        ]
        flow._phase = "awaiting_answer"

        result = flow.generate()
        expected_keys = {"story_config", "characters", "locations", "variables", "outline", "outline_text"}
        assert set(result.keys()) == expected_keys

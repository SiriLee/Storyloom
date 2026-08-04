"""Integration tests for conversation-based prompt architecture."""

from storyloom.core.context_manager import ContextManager
from storyloom.core.prompt_builder import PromptBuilder
from storyloom.parser.stream_parser import StreamParser
from storyloom.core.state_manager import StateManager
from storyloom.core.game_loop import GameState


def _parse_bridge_text(xml_text):
    """Parse XML through the full pipeline, return branch-filtered bridge_text.

    Processes choices (defaulting to option 1) so ``current_branch``
    reflects the player's selection before post-bridge segments are
    accumulated.  Returns bridge_text filtered by ``current_branch``,
    matching the real GameLoop behavior.
    """
    from storyloom.parser.stream_parser import EventType as ET

    parser = StreamParser()
    sm = StateManager(GameState([]))
    for line in xml_text.split("\n"):
        for event in parser.feed_line(line):
            list(sm.process(event))
            if sm.needs_input:
                list(sm.apply_choice("1"))
            if event.type == ET.CHECKPOINT and not parser.in_checkpoint:
                list(sm.process_checkpoint())
            elif event.type == ET.CHECKPOINT_END:
                list(sm.process_checkpoint())
    return sm.get_bridge_text(sm.current_branch)


SAMPLE_STORY = {
    "tier": "medium",
    "title": "霓虹深渊",
    "language": "zh-CN",
    "premise": "2087年新东京地下城，前荒坂安全顾问林焰被卷入一场围绕神秘芯片的暗战。",
}

SAMPLE_CHARACTERS = [
    {"name": "林焰", "role": "protagonist", "description": "前荒坂安全顾问，冷静、道德灰色", "appearance": "高瘦，短发，眼神锐利"},
]

SAMPLE_LOCATIONS = [
    {"id": "neo_tokyo_streets", "name": "新东京地下城", "description": "霓虹灯闪烁的潮湿巷道"},
]

SAMPLE_VARIABLES = [
    {"name": "体力", "type": "number", "initial": 80},
    {"name": "信任度", "type": "number", "initial": 10},
]

SAMPLE_OUTLINE = """ch1_bar [active] — 霓虹深渊
  → ch2_confrontation [pending]
ch2_confrontation [pending] — 地下交易
  ├→ ch3_ally [pending]
  └→ ch3_betrayal [pending]
ch3_ally [pending] — 盟友之路
ch3_betrayal [pending] — 背叛之路
ch4_safehouse [pending] — 安全屋"""

ROUND1_OUTPUT = """<story>
<seg>霓虹灯在潮湿的巷道地面上投下破碎的倒影。</seg>
<seg>耗子的酒吧藏在第三层地下通道的尽头。</seg>
<seg>林焰: 芯片在哪儿？</seg>
<choice id="approach">
  <opt key="1" branch="direct">直接问价</opt>
  <opt key="2" branch="careful">先探口风</opt>
</choice>
<set var="信任度" op="+" val="5" if="approach==1"/>
<set var="信任度" op="-" val="5" if="approach==2"/>
<checkpoint node="ch2_confrontation" summary="在霓虹深渊酒吧与耗子接头，选择了接触策略。">
  <route if="approach==1" target="ch3_ally"/>
  <route if="approach==2" target="ch3_betrayal"/>
</checkpoint>
<bridge/>
<branch name="direct">
<seg>你把信用棒拍在吧台上。</seg>
<seg>耗子: 痛快。不过我得提醒你——荒坂的人在找你。</seg>
</branch>
<branch name="careful">
<seg>你先要了杯酒，耗子在你身边坐下。</seg>
<seg>耗子: 最近生意不好做啊。</seg>
</branch>
</story>"""

ROUND2_OUTPUT = """<story>
<seg>耗子领着你穿过酒吧后厨，推开一扇标着"员工通道"的门。</seg>
<seg>门后是一条狭窄的走廊，荧光灯管嗡嗡作响。</seg>
<seg>耗子: 芯片在安全屋里。不过去之前——我们得谈谈价。</seg>
<choice id="negotiation">
  <opt key="1" branch="pay">按原价支付</opt>
  <opt key="2" branch="haggle">讨价还价</opt>
</choice>
<set var="信任度" op="+" val="5" if="negotiation==1"/>
<set var="体力" op="-" val="10" if="negotiation==2"/>
<checkpoint node="ch3_ally" summary="与耗子前往安全屋，途中谈判交易价格。">
</checkpoint>
<bridge/>
<branch name="pay">
<seg>你点头同意，耗子咧嘴一笑。</seg>
</branch>
<branch name="haggle">
<seg>你皱起眉头，耗子的义眼红光闪烁了一下。</seg>
</branch>
</story>"""


class TestIntegration:
    def test_full_5_round_conversation_flow(self):
        """Simulate 5 rounds and verify message structure at each step."""
        pb = PromptBuilder()
        cm = ContextManager()

        # Round 1
        r1_prompt = pb.build_round1(
            SAMPLE_STORY, SAMPLE_OUTLINE, "ch2_confrontation", "与耗子完成交易",
            {"GLOBAL": {"体力": 80, "信任度": 10}},
            characters=SAMPLE_CHARACTERS, locations=SAMPLE_LOCATIONS,
            variables=SAMPLE_VARIABLES,
        )
        cm.set_round1(r1_prompt, ROUND1_OUTPUT,
                      bridge_text=_parse_bridge_text(ROUND1_OUTPUT))
        msgs = cm.get_messages()
        assert len(msgs) == 2
        assert cm.round_count == 1
        assert cm.get_compressed_rounds() == []

        # Round 2
        bridge1 = cm.get_last_bridge_text()
        assert len(bridge1) > 0
        r2_prompt = pb.build_round_n(
            outline_text=SAMPLE_OUTLINE,
            current_node="ch3_ally",
            goal="与耗子前往安全屋",
            state_vars={"GLOBAL": {"体力": 80, "信任度": 15}},
            variables=SAMPLE_VARIABLES,
            bridge_text=bridge1,
        )
        cm.add_round(r2_prompt, ROUND2_OUTPUT,
                     bridge_text=_parse_bridge_text(ROUND2_OUTPUT))
        assert cm.round_count == 2
        assert cm.get_compressed_rounds() == []

        # Round 3
        cm.add_round("r3 context", ROUND2_OUTPUT,
                     bridge_text=_parse_bridge_text(ROUND2_OUTPUT))
        assert cm.round_count == 3

        # Round 4
        cm.add_round("r4 context", ROUND2_OUTPUT,
                     bridge_text=_parse_bridge_text(ROUND2_OUTPUT))
        assert cm.round_count == 4
        assert cm.get_compressed_rounds() == []

        # Round 5 — triggers compression
        cm.add_round("r5 context", ROUND2_OUTPUT,
                     bridge_text=_parse_bridge_text(ROUND2_OUTPUT))
        assert cm.round_count == 5
        compressed = cm.get_compressed_rounds()
        assert len(compressed) >= 1

        msgs = cm.get_messages()
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_context_manager_preserves_round1(self):
        """Round 1 messages should never be removed."""
        pb = PromptBuilder()
        cm = ContextManager()

        r1 = pb.build_round1(
            SAMPLE_STORY, SAMPLE_OUTLINE, "ch2_confrontation", "与耗子交易",
            {"GLOBAL": {"体力": 80, "信任度": 10}},
            characters=SAMPLE_CHARACTERS, locations=SAMPLE_LOCATIONS,
            variables=SAMPLE_VARIABLES,
        )
        cm.set_round1(r1, ROUND1_OUTPUT)

        for i in range(2, 10):
            cm.add_round(f"r{i}", ROUND2_OUTPUT)

        msgs = cm.get_messages()
        assert msgs[0]["content"] == r1
        assert "text adventure game" in msgs[0]["content"]
        assert "<story>" in msgs[0]["content"]

    def test_bridge_text_flows_between_rounds(self):
        """Bridge text extracted from round N feeds into round N+1 context."""
        pb = PromptBuilder()
        cm = ContextManager()

        cm.set_round1(
            pb.build_round1(SAMPLE_STORY, SAMPLE_OUTLINE, "ch2", "交易", {"GLOBAL": {"体力": 80, "信任度": 10}}, characters=SAMPLE_CHARACTERS, locations=SAMPLE_LOCATIONS, variables=SAMPLE_VARIABLES),
            ROUND1_OUTPUT,
            bridge_text=_parse_bridge_text(ROUND1_OUTPUT),
        )

        bridge1 = cm.get_last_bridge_text()
        r2 = pb.build_round_n(
            outline_text=SAMPLE_OUTLINE,
            current_node="ch3",
            goal="前往安全屋",
            state_vars={"GLOBAL": {"体力": 80, "信任度": 15}},
            variables=SAMPLE_VARIABLES,
            bridge_text=bridge1,
        )
        assert "信用棒" in r2 or "耗子" in r2

    def test_compression_format(self):
        """Compressed messages use the correct format."""
        pb = PromptBuilder()
        cm = ContextManager()

        cm.set_round1(
            pb.build_round1(SAMPLE_STORY, SAMPLE_OUTLINE, "ch2", "交易", {"GLOBAL": {"体力": 80, "信任度": 10}}, characters=SAMPLE_CHARACTERS, locations=SAMPLE_LOCATIONS, variables=SAMPLE_VARIABLES),
            ROUND1_OUTPUT,
            bridge_text=_parse_bridge_text(ROUND1_OUTPUT),
        )

        for i in range(2, 6):
            cm.add_round(f"r{i}", ROUND2_OUTPUT,
                         bridge_text=_parse_bridge_text(ROUND2_OUTPUT))

        msgs = cm.get_messages()
        contents = [m["content"] for m in msgs]
        has_summary = any("Key events so far" in c for c in contents)
        assert has_summary or cm.round_count < 5

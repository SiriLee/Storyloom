#!/usr/bin/env python3
"""Integration test: LLM GENERATE selection prompts against real API.

Usage:
  python3 tests/prompt_lab/test_llm_generate.py

Uses the app's own ApiClient + UserConfig — reads API key, base URL, and
model from the configured profile.  Override via LLM_API_KEY / LLM_BASE_URL
/ LLM_MODEL environment variables.

Design:
  - Roster entries in Chinese (simulating a real game's declared assets)
  - Library entries from system_media/ (English, top 20 by usage)
  - Tests normal mode (can return null) and forced mode (must pick)
  - Realistic probability weighting: library match / null are the common
    cases; roster match is rare (re-declaration of similar entity)

Edit TEST_CASES below to add/remove test scenarios.
"""

import json as _json
import sys
import time
from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from storyloom.assets import AssetLibrary, AssetType, GameAssetRoster
from storyloom.config import DEFAULT_MEDIA_DIR, GENERATE_LIBRARY_TOP_N
from storyloom.io.api_client import ApiClient
from storyloom.tasks._llm_generate import (
    _parse_selection_response,
    build_selection_prompt,
)
from storyloom.user_config import UserConfig


# ═══════════════════════════════════════════════════════════════════════
# Roster data — Chinese names/descriptions (simulating a game in progress)
# ═══════════════════════════════════════════════════════════════════════

_CHAR_ROSTER = [
    ("爱丽丝", "银色长发、深红眼眸的年轻女子，身穿白色连衣裙"),
    ("数学老师", "穿白衬衫戴眼镜的中年男教师，神情严肃"),
    ("酒馆老板", "秃顶的胖老头，围着沾满油渍的围裙，笑容可掬"),
    ("骑士团长", "金色短发、银色盔甲的女骑士，目光锐利"),
]

_BG_ROSTER = [
    ("大图书馆", "宏伟的双层图书馆，从地板到天花板的橡木书架，阳光透过彩绘玻璃窗洒落"),
    ("河畔集市", "沿河而建的露天市场，五颜六色的布棚下摆满各色货物，人声鼎沸"),
    ("废弃工坊", "布满灰尘和蛛网的老旧工坊，墙角堆着生锈的工具和破碎的陶罐"),
]

# Sets populated at runtime from the library
CHAR_IDS: set[str] = set()
BG_IDS: set[str] = set()


# ═══════════════════════════════════════════════════════════════════════
# Test cases
#
# Probability distribution in a real game:
#   - Roster match  ~10%  (LLM re-declares an entity similar to an
#                          already-declared one in the same game)
#   - Library match ~60%  (system assets cover common archetypes)
#   - Null          ~30%  (genuinely novel entity, no good analogue)
#
# accept: for 'game' scope — set of acceptable roster names.
#         for 'global' scope — set of acceptable library asset IDs.
#         for 'null' scope — {None}.
#         None means "accept any" (pre-populated at runtime).
# ═══════════════════════════════════════════════════════════════════════

TEST_CASES: list[dict] = [
    # ── Roster match ~10% ────────────────────────────────────────────
    {
        "label": "Roaster — 老师 → 数学老师",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "老师",
        "target_desc": "一个秃顶戴眼镜的老头，穿着黑色长袍，手持教鞭",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "expect": {"scope": "game", "accept": {"数学老师"}},
        "note": "LLM重新声明了一个已存在于名册中的角色——名称重叠触发名册优先匹配",
    },
    # ── Library match ~60% — CHAR ─────────────────────────────────────
    {
        "label": "Lib — 年轻女法师",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "年轻女法师",
        "target_desc": "一个十七八岁的少女，身穿深蓝色法师长袍，手持橡木法杖，法杖顶端镶嵌着发光的蓝宝石",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "expect": {"scope": "global", "accept": None},  # any CHAR lib ID
        "note": "常见角色原型——年轻女性在系统素材中覆盖良好",
    },
    {
        "label": "Lib — 铁匠老王",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "铁匠老王",
        "target_desc": "一个五十多岁的壮汉，光着膀子，肌肉结实，围着皮围裙，手里拿着铁锤，满脸煤灰",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "expect": {"scope": "global", "accept": None},
        "note": "手工艺人原型——中年男性角色在系统中常见",
    },
    {
        "label": "Lib — 精灵弓箭手",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "精灵弓箭手莉娜",
        "target_desc": "一个身材纤细的女性精灵，一头金色长发，翠绿色的眼睛，身穿绿色斗篷，背着精致的长弓",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "expect": {"scope": "global", "accept": None},
        "note": "精灵角色——系统素材中有精灵弓箭手",
    },
    # ── Library match ~60% — BG ───────────────────────────────────────
    {
        "label": "Lib — 阴森地下牢房",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "阴森地下牢房",
        "target_desc": "一间阴暗潮湿的地下牢房，墙壁上挂着生锈的铁链和镣铐，唯一的光源是走廊上摇曳的火把",
        "roster": _BG_ROSTER,
        "forced": False,
        "expect": {"scope": "global", "accept": None},  # any BG lib ID
        "note": "地牢场景——系统素材中 dungeon 类背景可能匹配",
    },
    {
        "label": "Lib — 月光森林小径",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "月光森林小径",
        "target_desc": "一条穿过茂密森林的蜿蜒小径，月光透过层层树叶洒下斑驳光影，路旁长满了发光蘑菇",
        "roster": _BG_ROSTER,
        "forced": False,
        "expect": {"scope": "global", "accept": None},
        "note": "森林/自然场景——常见背景原型",
    },
    {
        "label": "Lib — 圣玛丽乡村教堂",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "圣玛丽乡村教堂",
        "target_desc": "一座简朴的石砌小教堂，木制长椅上摆着破旧的赞美诗集，阳光透过彩色玻璃窗洒在圣坛上",
        "roster": _BG_ROSTER,
        "forced": False,
        "expect": {"scope": "global", "accept": None},
        "note": "宗教建筑——系统素材中 temple 可能匹配",
    },
    # ── Null ~30% ─────────────────────────────────────────────────────
    {
        "label": "Null — 虚空之影（外星触手怪）",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "虚空之影",
        "target_desc": "一团不定形的暗影，由无数蠕动的触手和若隐若现的眼睛组成，来自维度之外的存在",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "expect": {"scope": "null", "accept": {None}},
        "note": "完全超出素材库覆盖范围",
    },
    {
        "label": "Null — 星际巡洋舰指挥室",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "星际巡洋舰指挥室",
        "target_desc": "一艘先进外星战舰的指挥中心，弧形全景屏幕显示星空，全息投影操作台发出淡蓝色光芒",
        "roster": _BG_ROSTER,
        "forced": False,
        "expect": {"scope": "null", "accept": {None}},
        "note": "科幻场景——视觉小说素材库不覆盖",
    },
    {
        "label": "Null — 赛博朋克霓虹酒吧",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "霓虹深渊酒吧",
        "target_desc": "一个赛博朋克风格的地下酒吧，霓虹灯管闪烁，全息广告投射在烟雾中，改造人酒保擦拭吧台",
        "roster": _BG_ROSTER,
        "forced": False,
        "expect": {"scope": "null", "accept": {None}},
        "note": "赛博朋克场景——画风与系统素材完全不兼容",
    },
    # ── Forced ~10% ───────────────────────────────────────────────────
    {
        "label": "Forced — 虚空之影 must pick",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "虚空之影",
        "target_desc": "一团不定形的暗影，由无数蠕动的触手和若隐若现的眼睛组成",
        "roster": _CHAR_ROSTER,
        "forced": True,
        "expect": {"scope": "global", "accept": None},
        "note": "强制模式——必须从素材库选一个，即使没有合理匹配",
    },
]


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    global CHAR_IDS, BG_IDS

    cfg = UserConfig(str(PROJECT_ROOT))
    api = ApiClient(config=cfg)
    model = api.model
    base_url = api.base_url
    print(f"Model : {model}")
    print(f"Base  : {base_url}")
    print(f"Think : light (single call)")
    print("=" * 72)

    # ── Build library from system_media ──────────────────────────────
    lib = AssetLibrary(DEFAULT_MEDIA_DIR)
    system_dir = str(PROJECT_ROOT / "system_media")
    import os as _os
    if _os.path.isdir(system_dir):
        try:
            lib.import_system_assets(system_dir)
        except Exception as exc:
            print(f"WARNING: system_media import failed: {exc}")
    else:
        print("WARNING: system_media/ not found — library will be empty")

    char_lib = lib.get_sorted_by_usage(AssetType.CHAR_PORTRAIT, GENERATE_LIBRARY_TOP_N)
    bg_lib = lib.get_sorted_by_usage(AssetType.BACKGROUND, GENERATE_LIBRARY_TOP_N)
    CHAR_IDS = {a.id for a in char_lib}
    BG_IDS = {a.id for a in bg_lib}
    print(f"Library CHAR : {len(char_lib)} entries")
    print(f"Library BG   : {len(bg_lib)} entries")
    print()

    # ── Resolve accept=None in test cases ────────────────────────────
    for case in TEST_CASES:
        accept = case["expect"].get("accept")
        if accept is not None:
            continue
        scope = case["expect"]["scope"]
        atype = case["asset_type"]
        if scope == "global":
            case["expect"]["accept"] = CHAR_IDS if atype == AssetType.CHAR_PORTRAIT else BG_IDS
        elif scope == "game":
            # Build the set of roster names for this case
            names = {name for name, _desc in case["roster"]}
            case["expect"]["accept"] = names

    # ── Run tests ────────────────────────────────────────────────────
    passed = 0
    failed = 0
    results: list[dict] = []

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_lib = AssetLibrary(tmpdir)

        for i, case in enumerate(TEST_CASES):
            label = case["label"]
            asset_type = case["asset_type"]
            target_name = case["target_name"]
            target_desc = case["target_desc"]
            roster_data = case["roster"]
            forced = case["forced"]
            expect = case["expect"]
            expect_scope = expect["scope"]
            accept_set = expect.get("accept", set())
            note = case.get("note", "")

            # Build roster (placeholders — declared but not generated)
            roster = GameAssetRoster("lab_generate", tmp_lib)
            for name, desc in roster_data:
                roster.add(asset_type, name, desc, target=None)

            # Build prompt
            prompt = build_selection_prompt(
                asset_type, target_name, target_desc,
                roster, lib, forced=forced,
            )
            messages = [{"role": "user", "content": prompt}]

            # ── API call ──────────────────────────────────────────────
            t_start = time.perf_counter()
            try:
                result = api.stream_chat(
                    messages=messages,
                    max_tokens=128,
                    response_format={"type": "json_object"},
                )
                elapsed = time.perf_counter() - t_start
                raw = result.content
                ttft = result.ttft
            except Exception as exc:
                elapsed = time.perf_counter() - t_start
                results.append({"case": label, "error": str(exc), "elapsed": elapsed,
                                "ok": False, "scope": None, "forced": forced,
                                "target": target_name, "selected": None,
                                "parsed_id": None})
                print(f"\n[{i + 1}] {label}")
                print(f"  \033[31mAPI ERROR\033[0m ({elapsed:.1f}s): {exc}")
                failed += 1
                continue

            # ── Parse ─────────────────────────────────────────────────
            parsed_scope, parsed_selected = _extract_scope_and_selected(raw)
            roster_entries = roster.list_by_type(asset_type)
            lib_entries = lib.list_by_type(asset_type)
            parsed_id = _parse_selection_response(raw, roster_entries, lib_entries)

            # ── Validate ──────────────────────────────────────────────
            scope_ok = (parsed_scope == expect_scope)
            if accept_set == {None}:
                # null case — expect parsed_id is None
                id_ok = parsed_id is None
            else:
                # roster / library / forced — check selected or parsed_id is in accept set
                id_ok = (parsed_selected in accept_set or
                         parsed_id in accept_set)

            ok = scope_ok and id_ok
            if ok:
                passed += 1
                verdict = "\033[32mPASS\033[0m"
            else:
                failed += 1
                issues = []
                if not scope_ok:
                    issues.append(f"scope={parsed_scope!r} (expected {expect_scope!r})")
                if not id_ok:
                    issues.append(f"selected={parsed_selected!r} not in accept set")
                verdict = f"\033[31mFAIL ({'; '.join(issues)})\033[0m"

            # ── Display — target vs selection ─────────────────────────
            scope_tag = {"game": "ROSTER", "global": "LIB", "null": "NULL",
                         None: "??"}.get(parsed_scope, str(parsed_scope))
            mode_tag = "FORCED" if forced else "normal"

            print(f"\n[{i + 1}] [{mode_tag}] [{scope_tag}] {label}")
            print(f"  Target   : {target_name!r}")
            print(f"            {target_desc[:80]}...")
            print(f"  Selected : {parsed_scope!r} → {parsed_selected!r}")
            if parsed_id and parsed_id != parsed_selected:
                print(f"            resolved to asset_id: {parsed_id}")
            print(f"  Roster   : {list(roster_entries.keys())}")
            print(f"  Accept   : {_describe_accept(accept_set, asset_type)}")
            print(f"  TTFT     : {ttft:.2f}s  |  Total: {elapsed:.1f}s  |  {verdict}")
            if note:
                print(f"  Note     : {note}")

            results.append({
                "case": label, "forced": forced, "scope": parsed_scope,
                "selected": parsed_selected, "parsed_id": parsed_id,
                "ttft": ttft, "elapsed": elapsed, "ok": ok,
                "target": target_name,
            })

            # Show prompt on first case
            if i == 0:
                print(f"\n{'─' * 60}")
                print("  [FULL PROMPT (first case)]:")
                for line in prompt.splitlines():
                    print(f"    | {line}")
                print(f"{'─' * 60}")

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'=' * 72}")
    print(f"Results: {passed}/{passed + failed} passed")
    if failed:
        print(f"         {failed} failed")

    scope_counts: dict[str, int] = {}
    for r in results:
        scope = r.get("scope", "error")
        scope_counts[scope] = scope_counts.get(scope, 0) + 1
    print(f"\nScope distribution:")
    for scope, count in sorted(scope_counts.items()):
        print(f"  {scope}: {count}")

    # ── Target → Selection map ───────────────────────────────────────
    print(f"\n{'─' * 72}")
    print(f"Target → Selection map:")
    for r in results:
        status = "\033[32m✓\033[0m" if r["ok"] else "\033[31m✗\033[0m"
        err = r.get("error", "")
        if err:
            print(f"  {status} {r['case']}")
            print(f"         Target: {r['target']!r}  →  ERROR: {err}")
        else:
            selected_str = r.get('selected')
            parsed_str = r.get('parsed_id')
            extra = f"  →  {parsed_str!r}" if parsed_str and parsed_str != str(selected_str) else ""
            print(f"  {status} {r['case']}")
            print(f"         Target: {r['target']!r}  →  {r['scope']!r} / {selected_str!r}{extra}")

    print("Done.")


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _extract_scope_and_selected(raw: str) -> tuple[str | None, str | None]:
    """Extract scope and selected fields from LLM JSON response."""
    try:
        data = _json.loads(raw)
        scope = data.get("scope")
        selected = data.get("selected")
        if selected is None:
            return (scope, None)
        return (scope, str(selected))
    except (_json.JSONDecodeError, TypeError):
        return (None, None)


def _describe_accept(accept_set: set, asset_type: AssetType) -> str:
    """Human-readable description of the accept set."""
    if accept_set == {None}:
        return "null only"
    size = len(accept_set)
    if size <= 5:
        return f"{{{', '.join(sorted(str(x) for x in accept_set))}}}"
    return f"<any of {size} {asset_type.value} library IDs>"


if __name__ == "__main__":
    main()

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
# Test cases
#
# Probability distribution in a real game:
#   - Roster match  ~10%  (LLM re-declares an entity similar to an
#                          already-declared one in the same game)
#   - Library match ~60%  (system assets cover common character/scene
#                          archetypes well)
#   - Null (no match) ~30% (genuinely novel entity with no good analogue
#                           in the library)
# ═══════════════════════════════════════════════════════════════════════

# Shared roster entries — simulate a game in progress with a few
# already-declared entities.  All are placeholders (target=None).
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

# Precomputed library IDs for flexible matching
_LIB_CHAR_IDS: set[str] | None = None
_LIB_BG_IDS: set[str] | None = None

TEST_CASES: list[dict] = [
    # ═══════════════════════════════════════════════════════════════════
    # Roster match (~10% — re-declaration of a similar entity)
    # ═══════════════════════════════════════════════════════════════════
    {
        "label": "Roaster — 老师 → 数学老师 (re-declare 同一角色)",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "老师",
        "target_desc": "一个秃顶戴眼镜的老头，穿着黑色长袍，手持教鞭",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "expect": {
            "scope": "game",
            "accept": None,  # accept any valid roster name
            "note": "LLM重新声明了一个已存在于名册中的角色（可能是前面提到过的配角，本轮首次正式登场）",
        },
    },
    # ═══════════════════════════════════════════════════════════════════
    # Library match (~60% — common archetype covered by system assets)
    # ═══════════════════════════════════════════════════════════════════
    {
        "label": "Lib — 年轻女法师 (Female mage archetype)",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "年轻女法师",
        "target_desc": "一个十七八岁的少女，身穿深蓝色法师长袍，手持橡木法杖，法杖顶端镶嵌着发光的蓝宝石",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "expect": {
            "scope": "global",
            "accept": None,  # accept any valid library ID
            "note": "常见角色原型——系统素材库中的年轻女性可能匹配",
        },
    },
    {
        "label": "Lib — 中年男铁匠 (Middle-aged male artisan)",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "铁匠老王",
        "target_desc": "一个五十多岁的壮汉，光着膀子，肌肉结实，围着皮围裙，手里拿着铁锤，满脸煤灰",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "expect": {
            "scope": "global",
            "accept": None,
            "note": "手工艺人原型——中年男性角色在系统中常见",
        },
    },
    {
        "label": "Lib — 阴森地下牢房 (Dungeon scene)",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "阴森地下牢房",
        "target_desc": "一间阴暗潮湿的地下牢房，墙壁上挂着生锈的铁链和镣铐，墙角堆着干草，唯一的光源是走廊上摇曳的火把",
        "roster": _BG_ROSTER,
        "forced": False,
        "expect": {
            "scope": "global",
            "accept": None,
            "note": "地牢场景——系统素材中有对应背景",
        },
    },
    {
        "label": "Lib — 森林小径 (Forest path)",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "森林小径",
        "target_desc": "一条穿过茂密森林的蜿蜒小径，阳光透过层层树叶洒下斑驳光影，路旁长满了野花和蘑菇",
        "roster": _BG_ROSTER,
        "forced": False,
        "expect": {
            "scope": "global",
            "accept": None,
            "note": "森林/自然场景——常见背景原型",
        },
    },
    {
        "label": "Lib — 港口码头 (Harbor scene)",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "港口码头",
        "target_desc": "一个繁忙的海港码头，停泊着数艘大型帆船，水手们在装卸货物，海鸥在天空盘旋",
        "roster": _BG_ROSTER,
        "forced": False,
        "expect": {
            "scope": "global",
            "accept": None,
            "note": "测试LLM是否能在素材库中找到最接近的场景",
        },
    },
    # ═══════════════════════════════════════════════════════════════════
    # Null / no match (~30% — genuinely novel, no good analogue)
    # ═══════════════════════════════════════════════════════════════════
    {
        "label": "Null — 外星触手怪 (Lovecraftian horror)",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "虚空之影",
        "target_desc": "一团不定形的暗影，由无数蠕动的触手和若隐若现的眼睛组成，来自维度之外的存在",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "expect": {
            "scope": "null",
            "accept": None,
            "note": "完全超出素材库覆盖范围——任何匹配都是不合理的强制选择",
        },
    },
    {
        "label": "Null — 外星飞船指挥室 (Sci-fi bridge)",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "星际巡洋舰指挥室",
        "target_desc": "一艘先进外星战舰的指挥中心，弧形全景屏幕显示星空，全息投影的操作台发出淡蓝色光芒，舰长座椅悬浮在中央",
        "roster": _BG_ROSTER,
        "forced": False,
        "expect": {
            "scope": "null",
            "accept": None,
            "note": "科幻场景——视觉小说素材库不覆盖此类型",
        },
    },
    {
        "label": "Null — 赛博朋克酒吧 (Cyberpunk tavern)",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "霓虹深渊酒吧",
        "target_desc": "一个赛博朋克风格的地下酒吧，霓虹灯管在黑暗中闪烁，全息广告投射在烟雾中，改造人酒保擦拭着吧台",
        "roster": _BG_ROSTER,
        "forced": False,
        "expect": {
            "scope": "null",
            "accept": None,
            "note": "赛博朋克场景——与系统素材库的画风完全不同",
        },
    },
    # ═══════════════════════════════════════════════════════════════════
    # Forced mode — must pick even for poor matches
    # ═══════════════════════════════════════════════════════════════════
    {
        "label": "Forced — 外星触手怪 must pick",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "虚空之影",
        "target_desc": "一团不定形的暗影，由无数蠕动的触手和若隐若现的眼睛组成",
        "roster": _CHAR_ROSTER,
        "forced": True,
        "expect": {
            "scope": "global",  # forced picks from library as last resort
            "accept": None,
            "note": "强制模式——即使没有合理匹配也必须从素材库选一个",
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    global _LIB_CHAR_IDS, _LIB_BG_IDS

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
    _LIB_CHAR_IDS = {a.id for a in char_lib}
    _LIB_BG_IDS = {a.id for a in bg_lib}
    print(f"Library CHAR : {len(char_lib)} entries")
    print(f"Library BG   : {len(bg_lib)} entries")
    print()

    # ── Results summary for analysis ─────────────────────────────────
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
            expected_accept = expect.get("accept")

            # Build roster (all placeholders — simulating declared entities
            # that haven't been generated yet)
            roster = GameAssetRoster("lab_generate", tmp_lib)
            for name, desc in roster_data:
                roster.add(asset_type, name, desc, target=None)

            # Build prompt
            prompt = build_selection_prompt(
                asset_type, target_name, target_desc,
                roster, lib, forced=forced,
            )
            messages = [{"role": "user", "content": prompt}]

            # Call API
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
                results.append({"case": label, "error": str(exc), "elapsed": elapsed})
                print(f"\n[{i + 1}] {label}")
                print(f"  \033[31mAPI ERROR\033[0m ({elapsed:.1f}s): {exc}")
                failed += 1
                continue

            # Extract scope and selected from raw response
            parsed_scope, parsed_selected = _extract_scope_and_selected(raw)

            # Resolve parsed value through the standard parser
            roster_entries = roster.list_by_type(asset_type)
            lib_entries = lib.list_by_type(asset_type)
            parsed_id = _parse_selection_response(raw, roster_entries, lib_entries)

            # ── Validate ────────────────────────────────────────────
            scope_ok = (parsed_scope == expect_scope)
            lib_ids = _LIB_CHAR_IDS if asset_type == AssetType.CHAR_PORTRAIT else _LIB_BG_IDS

            # For 'game' scope: verify selected is in roster
            # For 'global' scope: verify selected is a valid library ID
            # For 'null' scope: verify selected is null/None
            if expect_scope == "null":
                id_ok = parsed_id is None
            elif expect_scope == "game":
                id_ok = parsed_selected in roster_entries if parsed_selected else False
            elif expect_scope == "global":
                id_ok = parsed_id is not None and parsed_id in lib_ids
            else:
                id_ok = False

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
                    issues.append(f"selected={parsed_selected!r} parsed_id={parsed_id!r}")
                verdict = f"\033[31mFAIL ({'; '.join(issues)})\033[0m"

            # ── Display ──────────────────────────────────────────────
            mode_tag = "FORCED" if forced else "normal"
            print(f"\n[{i + 1}] [{mode_tag}] {label}")
            print(f"  Target   : {target_name!r}")
            print(f"  Desc     : {target_desc[:80]}...")
            print(f"  Roster   : {list(roster_entries.keys())}")
            print(f"  TTFT     : {ttft:.2f}s" if ttft else "  TTFT     : —")
            print(f"  Total    : {elapsed:.1f}s")
            print(f"  Raw      : {raw.strip()}")
            print(f"  Scope    : {parsed_scope!r}  Selected: {parsed_selected!r}  "
                  f"Parsed ID: {parsed_id!r}  {verdict}")
            if expect.get("note"):
                print(f"  Note     : {expect['note']}")

            results.append({
                "case": label,
                "forced": forced,
                "scope": parsed_scope,
                "selected": parsed_selected,
                "parsed_id": parsed_id,
                "ttft": ttft,
                "elapsed": elapsed,
                "ok": ok,
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

    # ── Analysis ─────────────────────────────────────────────────────
    scope_counts: dict[str, int] = {}
    for r in results:
        scope = r.get("scope", "error")
        scope_counts[scope] = scope_counts.get(scope, 0) + 1

    print(f"\nScope distribution:")
    for scope, count in sorted(scope_counts.items()):
        print(f"  {scope}: {count}")

    # Show detailed selections for library matches (most interesting)
    print(f"\nLibrary selections (scope=global):")
    for r in results:
        if r.get("scope") == "global" and r.get("parsed_id"):
            print(f"  {r['case']}")
            print(f"    → {r['selected']!r}  (parsed: {r['parsed_id']!r})")

    print(f"\nAll results:")
    for r in results:
        status = "PASS" if r["ok"] else "FAIL"
        err = r.get("error", "")
        if err:
            print(f"  [{status}] {r['case']} — {err}")
        else:
            print(f"  [{status}] {r['case']} — scope={r.get('scope')}, "
                  f"selected={r.get('selected')!r}")

    print("Done.")


def _extract_scope_and_selected(raw: str) -> tuple[str | None, str | None]:
    """Extract scope and selected fields from LLM JSON response."""
    try:
        data = _json.loads(raw)
        scope = data.get("scope")
        selected = data.get("selected")
        # Normalise: JSON null → Python None
        if selected is None:
            return (scope, None)
        return (scope, str(selected) if selected is not None else None)
    except (_json.JSONDecodeError, TypeError):
        return (None, None)


if __name__ == "__main__":
    main()

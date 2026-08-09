#!/usr/bin/env python3
"""Integration test: LLM GENERATE selection pipeline against real API.

Usage:
  python3 tests/prompt_lab/test_llm_generate.py

Tests the actual production code paths (_select / _select_forced) with
real API calls.  Uses UserConfig for credentials.  Override via
LLM_API_KEY / LLM_BASE_URL / LLM_MODEL environment variables.

Design:
  - Roster entries in Chinese (simulating declared-but-not-generated entities)
  - Library entries from system_media/ (English, top 20 by usage)
  - Normal mode: _select() — can return null
  - Forced mode: _select_forced() — must return an asset_id
  - No image generation — tests the LLM selection prompt only

Edit TEST_CASES below to add/remove test scenarios.
"""

import json as _json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from storyloom.assets import AssetLibrary, AssetType, GameAssetRoster
from storyloom.config import DEFAULT_MEDIA_DIR, GENERATE_LIBRARY_TOP_N
from storyloom.io.api_client import ApiClient
from storyloom.tasks._llm_generate import _select, _select_forced
from storyloom.user_config import UserConfig

# ═══════════════════════════════════════════════════════════════════════
# Roster data — Chinese (simulating a game in progress)
# ═══════════════════════════════════════════════════════════════════════

# (local_name, description, target_id)
# local_name is what the LLM sees and matches against.
# target_id is the internal library asset ID (invisible to LLM).
_CHAR_ROSTER = [
    ("爱丽丝", "银色长发、深红眼眸的年轻女子，身穿白色连衣裙", "roster_alice"),
    ("数学老师", "穿白衬衫戴眼镜的中年男教师，神情严肃", "roster_math_teacher"),
    ("酒馆老板", "秃顶的胖老头，围着沾满油渍的围裙，笑容可掬", "roster_innkeeper"),
    ("骑士团长", "金色短发、银色盔甲的女骑士，目光锐利", "roster_knight"),
]

_BG_ROSTER = [
    ("大图书馆", "宏伟的双层图书馆，从地板到天花板的橡木书架，阳光透过彩绘玻璃窗洒落", "roster_library"),
    ("河畔集市", "沿河而建的露天市场，五颜六色的布棚下摆满各色货物，人声鼎沸", "roster_market"),
    ("废弃工坊", "布满灰尘和蛛网的老旧工坊，墙角堆着生锈的工具和破碎的陶罐", "roster_workshop"),
]

CHAR_IDS: set[str] = set()
BG_IDS: set[str] = set()

# ═══════════════════════════════════════════════════════════════════════
# Test cases
#
# accept: set of acceptable parsed_id values.
#   - {None} means expect null.
#   - None means resolve at runtime from CHAR_IDS / BG_IDS.
#   - Concrete set like {"数学老师"} means exact roster match.
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
        "accept": {"roster_数学老师"},
        "note": "LLM 重新声明了已存在于名册中的角色——名称重叠触发名册优先匹配",
    },
    # ── Library match ~60% — CHAR ─────────────────────────────────────
    {
        "label": "Lib — 年轻女法师",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "年轻女法师",
        "target_desc": "一个十七八岁的少女，身穿深蓝色法师长袍，手持橡木法杖，法杖顶端镶嵌着发光的蓝宝石",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "accept": None,  # → CHAR_IDS at runtime
        "note": "常见角色原型——年轻女性在系统素材中覆盖良好",
    },
    {
        "label": "Lib — 铁匠老王",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "铁匠老王",
        "target_desc": "一个五十多岁的壮汉，光着膀子，肌肉结实，围着皮围裙，手里拿着铁锤，满脸煤灰",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "accept": None,
        "note": "手工艺人原型——中年男性角色在系统中常见",
    },
    {
        "label": "Lib — 精灵弓箭手莉娜",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target_name": "精灵弓箭手莉娜",
        "target_desc": "一个身材纤细的女性精灵，一头金色长发，翠绿色的眼睛，身穿绿色斗篷，背着精致的长弓",
        "roster": _CHAR_ROSTER,
        "forced": False,
        "accept": None,
        "note": "精灵角色——系统素材中有精灵弓箭手",
    },
    # ── Library match — BG ───────────────────────────────────────────
    {
        "label": "Lib — 阴森地下牢房",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "阴森地下牢房",
        "target_desc": "一间阴暗潮湿的地下牢房，墙壁上挂着生锈的铁链和镣铐，唯一的光源是走廊上摇曳的火把",
        "roster": _BG_ROSTER,
        "forced": False,
        "accept": None,  # → BG_IDS at runtime
        "note": "地牢场景——系统素材中 dungeon 类背景可能匹配",
    },
    {
        "label": "Lib — 月光森林小径",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "月光森林小径",
        "target_desc": "一条穿过茂密森林的蜿蜒小径，月光透过层层树叶洒下斑驳光影，路旁长满了发光蘑菇",
        "roster": _BG_ROSTER,
        "forced": False,
        "accept": None,
        "note": "森林/自然场景——常见背景原型",
    },
    {
        "label": "Lib — 圣玛丽乡村教堂",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "圣玛丽乡村教堂",
        "target_desc": "一座简朴的石砌小教堂，木制长椅上摆着破旧的赞美诗集，阳光透过彩色玻璃窗洒在圣坛上",
        "roster": _BG_ROSTER,
        "forced": False,
        "accept": None,
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
        "accept": {None},
        "note": "完全超出素材库覆盖范围",
    },
    {
        "label": "Null — 星际巡洋舰指挥室",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "星际巡洋舰指挥室",
        "target_desc": "一艘先进外星战舰的指挥中心，弧形全景屏幕显示星空，全息投影操作台发出淡蓝色光芒",
        "roster": _BG_ROSTER,
        "forced": False,
        "accept": {None},
        "note": "科幻场景——视觉小说素材库不覆盖",
    },
    {
        "label": "Null — 赛博朋克霓虹酒吧",
        "asset_type": AssetType.BACKGROUND,
        "target_name": "霓虹深渊酒吧",
        "target_desc": "一个赛博朋克风格的地下酒吧，霓虹灯管闪烁，全息广告投射在烟雾中，改造人酒保擦拭吧台",
        "roster": _BG_ROSTER,
        "forced": False,
        "accept": {None},
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
        "accept": None,  # → CHAR_IDS at runtime (forced must pick from library)
        "note": "强制模式——即使没有合理匹配也必须从素材库选一个",
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
    print(f"Think : light (single call, via _select / _select_forced)")
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
    # accept uses full library (not just top-N) — _select_forced's
    # programmatic fallback scans all entries
    CHAR_IDS = set(lib.list_by_type(AssetType.CHAR_PORTRAIT).keys())
    BG_IDS = set(lib.list_by_type(AssetType.BACKGROUND).keys())
    print(f"Library CHAR : {len(CHAR_IDS)} total, top {len(char_lib)} used in prompt")
    print(f"Library BG   : {len(BG_IDS)} total, top {len(bg_lib)} used in prompt")
    print()

    # ── Resolve accept=None in test cases ────────────────────────────
    for case in TEST_CASES:
        if case["accept"] is not None:
            continue
        atype = case["asset_type"]
        case["accept"] = CHAR_IDS if atype == AssetType.CHAR_PORTRAIT else BG_IDS

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
            accept_set = case["accept"]
            note = case.get("note", "")

            # Build roster — existing entries have real targets (simulating
            # already-generated assets from previous rounds).  Only the
            # current DECLARE's own entry is a placeholder (target=None).
            roster = GameAssetRoster("lab_generate", tmp_lib)
            for local_name, desc, aid in roster_data:
                if tmp_lib.get(asset_type, aid) is None:
                    tmp_lib.add(asset_type, local_name, desc, asset_id=aid)
                roster.add(asset_type, local_name, desc, target=aid)
            # TaskGenerator creates a placeholder for the current DECLARE
            roster.add(asset_type, target_name, target_desc, target=None)

            # ── Call the real production function ────────────────────
            t_start = time.perf_counter()
            try:
                if forced:
                    parsed_id = _select_forced(
                        api, asset_type, target_name, target_desc,
                        roster, lib,
                    )
                else:
                    parsed_id = _select(
                        api, asset_type, target_name, target_desc,
                        roster, lib, forced=False,
                    )
                elapsed = time.perf_counter() - t_start
            except Exception as exc:
                elapsed = time.perf_counter() - t_start
                results.append({
                    "case": label, "error": str(exc), "elapsed": elapsed,
                    "ok": False, "forced": forced, "target": target_name,
                    "parsed_id": None,
                })
                print(f"\n[{i + 1}] {label}")
                print(f"  \033[31mERROR\033[0m ({elapsed:.1f}s): {exc}")
                failed += 1
                continue

            # ── Validate ──────────────────────────────────────────────
            if accept_set == {None}:
                ok = parsed_id is None
            else:
                ok = parsed_id in accept_set

            if ok:
                passed += 1
                verdict = "\033[32mPASS\033[0m"
            else:
                failed += 1
                verdict = f"\033[31mFAIL (parsed_id={parsed_id!r} not in accept)\033[0m"

            # ── Display — target vs selection ─────────────────────────
            mode_tag = "FORCED" if forced else "normal"
            roster_entries = roster.list_by_type(asset_type)

            print(f"\n[{i + 1}] [{mode_tag}] {label}")
            print(f"  Target   : {target_name!r}")
            print(f"            {target_desc[:80]}...")
            print(f"  Selected : {parsed_id!r}")
            print(f"  Roster   : {list(roster_entries.keys())}")
            print(f"  Accept   : {_describe_accept(accept_set, asset_type)}")
            print(f"  Total    : {elapsed:.1f}s  |  {verdict}")
            if note:
                print(f"  Note     : {note}")

            results.append({
                "case": label, "forced": forced,
                "parsed_id": parsed_id, "elapsed": elapsed, "ok": ok,
                "target": target_name,
            })

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'=' * 72}")
    print(f"Results: {passed}/{passed + failed} passed")
    if failed:
        print(f"         {failed} failed")

    # Scope distribution
    null_count = sum(1 for r in results if r.get("parsed_id") is None)
    lib_count = sum(1 for r in results if r.get("parsed_id") and r.get("parsed_id") in (CHAR_IDS | BG_IDS))
    roster_count = sum(1 for r in results if r.get("parsed_id") and r.get("parsed_id") not in (CHAR_IDS | BG_IDS | {None}))
    print(f"\nSelection distribution:")
    print(f"  roster (game): {roster_count}")
    print(f"  library:       {lib_count}")
    print(f"  null:          {null_count}")
    if sum(1 for r in results if r.get("error")):
        print(f"  error:         {sum(1 for r in results if r.get('error'))}")

    # Target → Selection map
    print(f"\n{'─' * 72}")
    print("Target → Selection map:")
    for r in results:
        status = "\033[32m✓\033[0m" if r["ok"] else "\033[31m✗\033[0m"
        err = r.get("error", "")
        if err:
            print(f"  {status} {r['case']}")
            print(f"         Target: {r['target']!r}  →  ERROR: {err}")
        else:
            print(f"  {status} {r['case']}")
            print(f"         Target: {r['target']!r}  →  {r['parsed_id']!r}")

    print("Done.")


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _describe_accept(accept_set: set, asset_type: AssetType) -> str:
    if accept_set == {None}:
        return "null only"
    size = len(accept_set)
    if size <= 6:
        return f"{{{', '.join(sorted(str(x) for x in accept_set))}}}"
    return f"<any of {size} {asset_type.value} library IDs>"


if __name__ == "__main__":
    main()

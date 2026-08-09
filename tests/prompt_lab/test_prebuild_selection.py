#!/usr/bin/env python3
"""Integration test: §7.8c pre-build batch selection prompts against real API.

Usage:
  python3 tests/prompt_lab/test_prebuild_selection.py

Tests the production ``build_batch_selection_messages()`` and
``parse_batch_selection_response()`` with real LLM calls.  Uses system
media assets as the global library.  Override via LLM_API_KEY /
LLM_BASE_URL / LLM_MODEL environment variables.

Design:
  - Library: system_media/ assets imported via AssetLibrary
  - Entities: realistic story_config characters / locations
  - Languages: zh-CN + en
  - Modes: normal (match|generate) + forced (match-only)
  - Full thinking mode (batch selection needs quality decisions)
  - No image generation — tests the LLM selection prompt only

Edit TEST_SCENARIOS below to add/remove scenarios.
"""

import json as _json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from storyloom.assets import AssetLibrary, AssetType
from storyloom.config import DEFAULT_SYSTEM_MEDIA_DIR
from storyloom.core.prebuild import (
    EntitySpec,
    run_batch_selection,
)
from storyloom.io.api_client import ApiClient
from storyloom.user_config import UserConfig


# ═══════════════════════════════════════════════════════════════════════
# Library — system media assets
# ═══════════════════════════════════════════════════════════════════════

def load_system_library() -> AssetLibrary:
    """Load the global library from system_media/ and return it."""
    import os as _os
    lib = AssetLibrary("media")
    if _os.path.isdir(DEFAULT_SYSTEM_MEDIA_DIR):
        report = lib.import_system_assets(DEFAULT_SYSTEM_MEDIA_DIR)
        print(f"System assets imported: v{report.version}")
        print(f"  Added:   {len(report.added)}")
        print(f"  Removed: {len(report.removed)}")
        print(f"  Updated: {len(report.updated)}")
        print(f"  Unchanged: {report.unchanged}")
    else:
        print("WARNING: system_media/ not found — library will be empty")
    return lib


# ═══════════════════════════════════════════════════════════════════════
# Test scenarios
# ═══════════════════════════════════════════════════════════════════════
#
# accept: dict[str, str | set] — per-entity expected result.
#   "generate"     → must have action="generate"
#   "matched"      → must have action="matched" (forced mode, any asset)
#   {"id", ...}    → must have action="matched" AND asset_id in this set
#   None           → accept anything (not validated)

def _make_scenarios(library: AssetLibrary) -> list[dict]:
    """Build test scenarios using real library data."""

    # ── zh-CN: realistic characters (from actual saves) ─────────────
    # System has: sys_student_male, sys_student_female → should match
    # students.  But wuxia outfits don't match neutral system portraits.
    scenarios: list[dict] = []

    scenarios.append({
        "label": "zh-CN CHAR normal — 校园角色",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "mode": "normal",
        "entities": [
            EntitySpec("林逸", "高二学生，性格懒散但心地善良，喜欢穿宽松的校服",
                       "黑色短发，略显凌乱，中等身高，眼神慵懒",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("苏小晚", "高二转学生，活泼开朗，有点小刁蛮，扎着高马尾",
                       "明亮的眼睛，常穿浅色卫衣和短裙，笑起来有酒窝",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("陈浩", "林逸的好友，搞笑担当，微胖",
                       "圆脸，戴黑框眼镜，总是笑嘻嘻的，穿着宽大的运动服",
                       AssetType.CHAR_PORTRAIT),
        ],
        # Students should match student assets; library is neutral so
        # generate is also acceptable (conservative preference).
        "accept": {
            "林逸": {"sys_student_male", "sys_young_male", "generate"},
            "苏小晚": {"sys_student_female", "sys_young_female", "generate"},
            "陈浩": {"sys_student_male", "sys_young_male", "generate"},
        },
    })

    scenarios.append({
        "label": "zh-CN CHAR forced — 校园角色",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "mode": "forced",
        "entities": [
            EntitySpec("林逸", "高二学生，性格懒散但心地善良", "黑色短发，略显凌乱",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("苏小晚", "高二转学生，活泼开朗", "高马尾，明亮眼睛",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("陈浩", "林逸的好友", "圆脸，黑框眼镜",
                       AssetType.CHAR_PORTRAIT),
        ],
        "accept": {
            "林逸": {"sys_student_male", "sys_young_male"},
            "苏小晚": {"sys_student_female", "sys_young_female"},
            "陈浩": {"sys_student_male", "sys_young_male"},
        },
    })

    # ── zh-CN: realistic locations ─────────────────────────────────
    scenarios.append({
        "label": "zh-CN BG normal — 校园场景",
        "asset_type": AssetType.BACKGROUND,
        "mode": "normal",
        "entities": [
            EntitySpec("学校天台", "空旷的楼顶，生锈的铁丝网，破旧桌椅，午后阳光",
                       "", AssetType.BACKGROUND),
            EntitySpec("高二教室", "普通教室，课桌上刻着涂鸦，窗台绿萝垂下",
                       "", AssetType.BACKGROUND),
            EntitySpec("教学楼走廊", "长长的走廊，墙上贴着通知，学生们三三两两经过",
                       "", AssetType.BACKGROUND),
            EntitySpec("校园操场", "宽阔的操场，红色跑道，远处有篮球场和旗杆",
                       "", AssetType.BACKGROUND),
        ],
        "accept": {
            "学校天台": {"sys_rooftop", "generate"},
            "高二教室": {"sys_classroom", "generate"},
            "教学楼走廊": {"sys_corridor", "generate"},
            "校园操场": {"sys_playground", "generate"},
        },
    })

    scenarios.append({
        "label": "zh-CN BG forced — 校园场景",
        "asset_type": AssetType.BACKGROUND,
        "mode": "forced",
        "entities": [
            EntitySpec("学校天台", "楼顶，铁丝网，午后的阳光", "",
                       AssetType.BACKGROUND),
            EntitySpec("高二教室", "普通教室，课桌，绿萝", "",
                       AssetType.BACKGROUND),
            EntitySpec("教学楼走廊", "长长的走廊，通知，学生们经过", "",
                       AssetType.BACKGROUND),
            EntitySpec("校园操场", "宽阔的操场，跑道，篮球场", "",
                       AssetType.BACKGROUND),
        ],
        "accept": {
            "学校天台": {"sys_rooftop"},
            "高二教室": {"sys_classroom"},
            "教学楼走廊": {"sys_corridor"},
            "校园操场": {"sys_playground"},
        },
    })

    # ── zh-CN: wuxia style — no matching system assets ──────────────
    scenarios.append({
        "label": "zh-CN CHAR normal — 武侠角色",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "mode": "normal",
        "entities": [
            EntitySpec("柳如烟", "二十出头的女侠，轻功卓绝，性格冷傲",
                       "一袭白衣，长发及腰，面若冰霜，腰间悬着一柄青色长剑",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("铁无双", "四十岁的丐帮长老，豪迈仗义",
                       "身材魁梧，满脸胡茬，穿着打满补丁的灰布衣，手持打狗棒",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("慕容秋水", "江南慕容世家的少主，温文尔雅",
                       "白衣胜雪，手持折扇，眉目如画，举止从容不迫",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("黑袍老祖", "魔教教主，阴鸷狠辣",
                       "全身笼罩在黑袍之中，只露出一双泛着绿光的眼睛",
                       AssetType.CHAR_PORTRAIT),
        ],
        # Wuxia outfits/clans → no match in neutral system portraits.
        # Conservative LLM should return "generate" for all.
        "accept": {
            "柳如烟": {"generate"},
            "铁无双": {"generate"},
            "慕容秋水": {"generate"},
            "黑袍老祖": {"generate"},
        },
    })

    scenarios.append({
        "label": "zh-CN BG normal — 武侠场景",
        "asset_type": AssetType.BACKGROUND,
        "mode": "normal",
        "entities": [
            EntitySpec("断魂崖", "万丈悬崖之巅，云雾缭绕，传说中高手决战的圣地",
                       "", AssetType.BACKGROUND),
            EntitySpec("醉仙楼", "京城最繁华的酒楼，雕梁画栋，笙歌不断",
                       "", AssetType.BACKGROUND),
            EntitySpec("竹林深处", "一片幽静的紫竹林，阳光透过竹叶洒下斑驳光影",
                       "", AssetType.BACKGROUND),
            EntitySpec("地下密室", "阴暗潮湿的地下密室，墙上挂着各种刑具，烛火摇曳",
                       "", AssetType.BACKGROUND),
        ],
        "accept": {
            "断魂崖": {"sys_cliff", "sys_mountain", "generate"},
            "醉仙楼": {"sys_tavern", "sys_restaurant", "generate"},
            "竹林深处": {"sys_forest", "sys_garden", "generate"},
            "地下密室": {"sys_dungeon", "sys_basement", "generate"},
        },
    })

    # ── en: fantasy / RPG style ────────────────────────────────────
    scenarios.append({
        "label": "en CHAR normal — fantasy party",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "mode": "normal",
        "entities": [
            EntitySpec("Aldric", "A veteran knight captain, scarred but noble, fiercely protective of his comrades",
                       "Tall, broad-shouldered, with silver-streaked hair and a weathered face. Wears battered steel plate armor.",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("Lyra", "A young elven archer, quiet and observant, with a dry sense of humor",
                       "Slim and graceful, with long silver-blonde hair and pointed ears. Wears a green cloak over leather armor.",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("Grimm", "A dwarven runesmith, gruff and stubborn, but warm-hearted beneath the bluster",
                       "Short and stocky, with a braided copper beard, soot-stained hands. Carries a massive rune-inscribed hammer.",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("Morgana", "A mysterious sorceress with a dark past, seeking redemption",
                       "Pale skin, raven-black hair streaked with silver, violet eyes. Wears flowing dark robes with arcane symbols.",
                       AssetType.CHAR_PORTRAIT),
        ],
        # Fantasy races (elf, dwarf) + specific gear → no neutral match.
        # Morgana's "dark robes" might loosely match sys_adult_female.
        "accept": {
            "Aldric": {"sys_officer_male", "sys_middle_male", "generate"},
            "Lyra": {"generate"},
            "Grimm": {"generate"},
            "Morgana": {"sys_adult_female", "sys_middle_female", "generate"},
        },
    })

    scenarios.append({
        "label": "en BG normal — fantasy locations",
        "asset_type": AssetType.BACKGROUND,
        "mode": "normal",
        "entities": [
            EntitySpec("The Iron Keep", "A massive stone fortress perched on a volcanic cliff, black banners fluttering in the hot wind",
                       "", AssetType.BACKGROUND),
            EntitySpec("Whispering Woods", "An ancient forest where the trees glow faintly with bioluminescent moss, ethereal and quiet",
                       "", AssetType.BACKGROUND),
            EntitySpec("Dragon's Rest Tavern", "A cozy but rowdy inn with a massive fireplace, mounted monster heads, and oak tables scarred by countless brawls",
                       "", AssetType.BACKGROUND),
            EntitySpec("Sunken Cathedral", "The ruined remains of a grand cathedral, half-submerged in a misty lake, stained glass still glinting",
                       "", AssetType.BACKGROUND),
        ],
        "accept": {
            "The Iron Keep": {"sys_castle", "sys_fortress", "generate"},
            "Whispering Woods": {"sys_forest", "generate"},
            "Dragon's Rest Tavern": {"sys_tavern", "generate"},
            "Sunken Cathedral": {"sys_ruins", "sys_church", "generate"},
        },
    })

    # ── en: forced mode ────────────────────────────────────────────
    scenarios.append({
        "label": "en CHAR forced — fantasy party",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "mode": "forced",
        "entities": [
            EntitySpec("Aldric", "Veteran knight, scarred, protective", "Tall, silver-streaked hair, steel armor",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("Lyra", "Young elf archer, quiet, observant", "Slim, silver-blonde hair, green cloak",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("Grimm", "Dwarf runesmith, gruff, stubborn", "Short, stocky, copper beard, hammer",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("Morgana", "Sorceress, dark past, mysterious", "Pale, raven-black hair, violet eyes, dark robes",
                       AssetType.CHAR_PORTRAIT),
        ],
        # Forced must pick SOMETHING — verify plausible choices.
        "accept": {
            "Aldric": {"sys_officer_male", "sys_middle_male", "sys_adult_male", "sys_elderly_male"},
            "Lyra": {"sys_young_female", "sys_adult_female"},
            "Grimm": {"sys_worker_male", "sys_middle_male", "sys_adult_male"},
            "Morgana": {"sys_adult_female", "sys_middle_female", "sys_young_female", "sys_noble_female"},
        },
    })

    scenarios.append({
        "label": "en BG forced — fantasy locations",
        "asset_type": AssetType.BACKGROUND,
        "mode": "forced",
        "entities": [
            EntitySpec("The Iron Keep", "Massive stone fortress on a volcanic cliff", "",
                       AssetType.BACKGROUND),
            EntitySpec("Whispering Woods", "Ancient forest with glowing bioluminescent moss", "",
                       AssetType.BACKGROUND),
            EntitySpec("Dragon's Rest Tavern", "Cozy inn with massive fireplace", "",
                       AssetType.BACKGROUND),
            EntitySpec("Sunken Cathedral", "Ruined cathedral half-submerged in a misty lake", "",
                       AssetType.BACKGROUND),
        ],
        "accept": {
            "The Iron Keep": {"sys_castle", "sys_fortress"},
            "Whispering Woods": {"sys_forest"},
            "Dragon's Rest Tavern": {"sys_tavern", "sys_restaurant"},
            "Sunken Cathedral": {"sys_ruins", "sys_church"},
        },
    })

    return scenarios


# ═══════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════

def validate_results(
    results, entities: list[EntitySpec], accept: dict, mode: str,
) -> list[str]:
    """Validate batch selection results against expected answers.

    *accept* maps entity_name → expected:
      - ``"generate"`` → entity must have action="generate"
      - ``"matched"`` → entity must have action="matched" (any asset_id)
      - ``{id, ...}`` → entity must match one of these asset_ids
        (the string ``"generate"`` in the set means generate is also OK)

    Returns list of error strings (empty = all passed).
    """
    errors: list[str] = []
    result_map = {r.entity_name: r for r in results}

    for name, expected in accept.items():
        r = result_map.get(name)
        if r is None:
            errors.append(f"{name}: missing from response")
            continue

        if isinstance(expected, str):
            # Single expected action: "generate" or "matched"
            if expected == "generate" and r.action != "generate":
                errors.append(
                    f"{name}: expected generate, got {r.action}→{r.asset_id}"
                )
            elif expected == "matched" and r.action != "matched":
                errors.append(
                    f"{name}: expected matched, got {r.action}"
                )
        elif isinstance(expected, set):
            # Set of acceptable values — "generate" string = action OK,
            # other strings = asset_id must be one of these
            if "generate" in expected:
                if r.action == "generate":
                    continue  # OK — generate is acceptable
                # Must match one of the asset_ids
                if r.asset_id not in expected:
                    errors.append(
                        f"{name}: asset_id {r.asset_id!r} not in {expected}"
                    )
            else:
                # All entries are asset_ids — must match one
                if r.action != "matched":
                    errors.append(
                        f"{name}: expected matched, got {r.action}"
                    )
                elif r.asset_id not in expected:
                    errors.append(
                        f"{name}: asset_id {r.asset_id!r} not in {expected}"
                    )

    return errors


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    cfg = UserConfig(str(PROJECT_ROOT))
    api = ApiClient(config=cfg)
    model = api.model
    base_url = api.base_url

    print(f"Model      : {model}")
    print(f"Base URL   : {base_url}")
    import os as _os
    mode = _os.environ.get("LLM_SELECT_THINKING", "light")
    print(f"Thinking   : {mode} (LLM_SELECT_THINKING env, via run_batch_selection)")
    print("=" * 72)

    library = load_system_library()
    print("=" * 72)

    scenarios = _make_scenarios(library)

    passed = 0
    failed = 0
    total_elapsed = 0.0

    for i, sc in enumerate(scenarios):
        label = sc["label"]
        asset_type = sc["asset_type"]
        mode = sc["mode"]
        entities = sc["entities"]
        forced = (mode == "forced")

        # ── Call production function (handles prompt + API + parse) ──
        t_start = time.perf_counter()
        results, error = run_batch_selection(
            api, asset_type, entities, library,
            forced=forced, thinking_mode="light",
        )
        elapsed = time.perf_counter() - t_start
        total_elapsed += elapsed

        # ── Validate ────────────────────────────────────────────────
        accept = sc.get("accept", {})
        if error is not None:
            validation_errors = [error]
        elif accept:
            validation_errors = validate_results(results, entities, accept, mode)
        else:
            validation_errors = []  # no accept = format-only (already parsed OK)

        ok = len(validation_errors) == 0
        if ok:
            passed += 1
            verdict = "\033[32mPASS\033[0m"
        else:
            failed += 1
            verdict = "\033[31mFAIL\033[0m"

        # ── Display ─────────────────────────────────────────────────
        n_entities = len(entities)
        n_lib = len(library.list_by_type(asset_type))

        print(f"\n[{i + 1}] {label}")
        print(f"  Mode      : {mode} ({n_entities} entities, {n_lib} in library)")
        print(f"  Total     : {elapsed:.1f}s")

        if results:
            actions = [f"{r.entity_name}={r.action}" for r in results]
            print(f"  Actions   : {', '.join(actions)}")
            assets = [
                f"{r.entity_name}→{r.asset_id}" for r in results
                if r.asset_id is not None
            ]
            if assets:
                print(f"  Assets    : {', '.join(assets)}")

        if validation_errors:
            for err in validation_errors:
                print(f"  \033[31mERROR: {err}\033[0m")

        print(f"  {verdict}")

    # ── Summary ─────────────────────────────────────────────────────
    n_total = passed + failed
    print(f"\n{'=' * 72}")
    print(f"Passed : {passed}/{n_total}")
    if failed:
        print(f"Failed : {failed}/{n_total}")
    if n_total > 0:
        print(f"Avg    : {total_elapsed / n_total:.1f}s per call")
    print("Done.")


if __name__ == "__main__":
    main()

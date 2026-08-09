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

from storyloom.assets import AssetLibrary, AssetType, GameAssetRoster
from storyloom.config import DEFAULT_SYSTEM_MEDIA_DIR
from storyloom.core.prebuild import (
    EntitySpec,
    build_batch_selection_messages,
    parse_batch_selection_response,
)
from storyloom.io.api_client import ApiClient
from storyloom.io.thinking import get_thinking_params
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
# Each scenario: (label, asset_type, entities, mode, language)
#   entities: list of (name, description, appearance_or_empty)
#   mode: "normal" | "forced"
#   language: "zh-CN" | "en" (informational, not injected into prompt)

def _make_scenarios(library: AssetLibrary) -> list[dict]:
    """Build test scenarios using real library data."""

    # Quick sanity: count available assets per type
    char_count = len(library.list_by_type(AssetType.CHAR_PORTRAIT))
    bg_count = len(library.list_by_type(AssetType.BACKGROUND))

    scenarios: list[dict] = []

    # ── zh-CN: realistic characters (from actual saves) ─────────────
    scenarios.append({
        "label": "zh-CN CHAR normal — 校园角色 (3 entities, library has 25)",
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
    })

    scenarios.append({
        "label": "zh-CN CHAR forced — 校园角色 (3 entities, must match all)",
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
    })

    # ── zh-CN: realistic locations ─────────────────────────────────
    scenarios.append({
        "label": "zh-CN BG normal — 校园场景 (4 entities, library has 26)",
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
    })

    scenarios.append({
        "label": "zh-CN BG forced — 校园场景 (4 entities, must match all)",
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
    })

    # ── zh-CN: wuxia/xianxia style ─────────────────────────────────
    scenarios.append({
        "label": "zh-CN CHAR normal — 武侠角色 (4 entities)",
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
    })

    scenarios.append({
        "label": "zh-CN BG normal — 武侠场景 (4 entities)",
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
    })

    # ── en: fantasy / RPG style ────────────────────────────────────
    scenarios.append({
        "label": "en CHAR normal — fantasy party (4 entities)",
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
    })

    scenarios.append({
        "label": "en BG normal — fantasy locations (4 entities)",
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
    })

    # ── en: forced mode ────────────────────────────────────────────
    scenarios.append({
        "label": "en CHAR forced — fantasy party (4 entities, must match all)",
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
    })

    scenarios.append({
        "label": "en BG forced — fantasy locations (4 entities, must match all)",
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
    })

    return scenarios


# ═══════════════════════════════════════════════════════════════════════
# Validation
# ═══════════════════════════════════════════════════════════════════════

def validate_normal_response(
    results, entities: list[EntitySpec], library: AssetLibrary,
) -> list[str]:
    """Validate a normal-mode batch selection response.  Returns errors."""
    errors: list[str] = []
    entity_names = {e.name for e in entities}

    result_names = {r.entity_name for r in results}
    missing = entity_names - result_names
    extra = result_names - entity_names

    if missing:
        errors.append(f"Missing entities in response: {missing}")
    if extra:
        errors.append(f"Extra entities in response: {extra}")

    for r in results:
        if r.action == "matched":
            if r.asset_id is None:
                errors.append(f"{r.entity_name}: matched but asset_id is None")
            elif library.get(entities[0].asset_type, r.asset_id) is None:
                errors.append(
                    f"{r.entity_name}: asset_id {r.asset_id!r} not in library"
                )
        elif r.action == "generate":
            if r.asset_id is not None:
                errors.append(
                    f"{r.entity_name}: generate but asset_id is not None"
                )
        else:
            errors.append(f"{r.entity_name}: unknown action {r.action!r}")

    return errors


def validate_forced_response(
    results, entities: list[EntitySpec], library: AssetLibrary,
) -> list[str]:
    """Validate a forced-mode batch selection response.  Returns errors."""
    errors: list[str] = []
    entity_names = {e.name for e in entities}

    result_names = {r.entity_name for r in results}
    missing = entity_names - result_names
    extra = result_names - entity_names

    if missing:
        errors.append(f"Missing entities in response: {missing}")
    if extra:
        errors.append(f"Extra entities in response: {extra}")

    for r in results:
        # Forced mode: every entry must be "matched"
        if r.action != "matched":
            errors.append(
                f"{r.entity_name}: forced mode but action is {r.action!r}"
            )
        if r.asset_id is None:
            errors.append(f"{r.entity_name}: forced mode but asset_id is None")
        elif library.get(entities[0].asset_type, r.asset_id) is None:
            errors.append(
                f"{r.entity_name}: asset_id {r.asset_id!r} not in library"
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
    print(f"Thinking   : enabled (full — batch selection needs quality)")
    print("=" * 72)

    library = load_system_library()
    print("=" * 72)

    scenarios = _make_scenarios(library)

    passed = 0
    failed = 0
    total_elapsed = 0.0
    shown_prompt = {"normal": False, "forced": False}

    for i, sc in enumerate(scenarios):
        label = sc["label"]
        asset_type = sc["asset_type"]
        mode = sc["mode"]
        entities = sc["entities"]
        forced = (mode == "forced")

        # ── Build messages ──────────────────────────────────────────
        messages = build_batch_selection_messages(
            asset_type, entities, library, forced=forced,
        )
        if not messages:
            print(f"\n[{i + 1}] {label}")
            print("  SKIP: no entities for this type")
            continue

        # ── Call API (non-streaming — matches production _select_type) ──
        thinking_params = get_thinking_params(model, "enabled")
        t_start = time.perf_counter()
        try:
            raw = api.chat(
                messages=messages,
                max_tokens=1024,
                response_format={"type": "json_object"},
                extra_params=thinking_params,
            )
            elapsed = time.perf_counter() - t_start
            ttft = None  # chat() is non-streaming, no TTFT
        except Exception as exc:
            elapsed = time.perf_counter() - t_start
            print(f"\n[{i + 1}] {label}")
            print(f"  API ERROR ({elapsed:.1f}s): {exc}")
            failed += 1
            continue

        total_elapsed += elapsed

        # ── Parse ───────────────────────────────────────────────────
        parsed = parse_batch_selection_response(raw, entities, library)

        # ── Validate ────────────────────────────────────────────────
        if parsed is None:
            validation_errors = ["parse_batch_selection_response returned None"]
        elif forced:
            validation_errors = validate_forced_response(parsed, entities, library)
        else:
            validation_errors = validate_normal_response(parsed, entities, library)

        ok = len(validation_errors) == 0
        if ok:
            passed += 1
            verdict = "\033[32mPASS\033[0m"
        else:
            failed += 1
            verdict = "\033[31mFAIL\033[0m"

        # ── Display ─────────────────────────────────────────────────
        at_label = asset_type.value
        n_entities = len(entities)
        n_lib = len(library.list_by_type(asset_type))

        print(f"\n[{i + 1}] {label}")
        print(f"  Mode      : {mode} ({n_entities} entities, {n_lib} in library)")
        print(f"  Total     : {elapsed:.1f}s")
        print(f"  Raw       : {raw.strip()[:200]}{'...' if len(raw) > 200 else ''}")

        if parsed is not None:
            actions = [f"{r.entity_name}={r.action}" for r in parsed]
            print(f"  Actions   : {', '.join(actions)}")
            assets = [
                f"{r.entity_name}→{r.asset_id}" for r in parsed
                if r.asset_id is not None
            ]
            if assets:
                print(f"  Assets    : {', '.join(assets)}")

        if validation_errors:
            for err in validation_errors:
                print(f"  \033[31mERROR: {err}\033[0m")

        print(f"  {verdict}")

        # ── Show prompt on first case of each mode ──────────────────
        first_key = "forced" if forced else "normal"
        if not shown_prompt[first_key]:
            shown_prompt[first_key] = True
            print(f"\n{'─' * 60}")
            print(f"  [{mode.upper()} MODE SYSTEM PROMPT]:")
            for line in messages[0]["content"].splitlines():
                print(f"    | {line}")
            print(f"\n  [{mode.upper()} MODE USER MESSAGE (first {n_entities} entities)]:")
            for line in messages[1]["content"].splitlines()[:30]:
                print(f"    | {line}")
            if len(messages[1]["content"].splitlines()) > 30:
                print(f"    | ... ({len(messages[1]['content'].splitlines()) - 30} more lines)")
            print(f"{'─' * 60}")

    # ── Summary ─────────────────────────────────────────────────────
    n_total = passed + failed
    print(f"\n{'=' * 72}")
    print(f"Passed : {passed}/{n_total}")
    if failed:
        print(f"Failed : {failed}/{n_total}")
    if n_total > 0:
        print(f"Avg    : {total_elapsed / n_total:.1f}s per call")
    print(f"Mode   : enabled (full) thinking")
    print("Done.")


if __name__ == "__main__":
    main()

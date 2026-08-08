#!/usr/bin/env python3
"""Quick test: LLM match prompts against real API (disabled thinking mode).

Usage:
  python3 tests/prompt_lab/test_llm_match.py

Uses the app's own ApiClient + UserConfig — reads API key, base URL, and
model from the configured profile.  Override via LLM_API_KEY / LLM_BASE_URL
/ LLM_MODEL environment variables.

Edit TEST_CASES below to add/remove test scenarios.
"""

import sys
import time
from pathlib import Path

# ── Project root ─────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from storyloom.assets import AssetLibrary, AssetType, GameAssetRoster
from storyloom.io.api_client import ApiClient
from storyloom.io.thinking import get_thinking_params
from storyloom.tasks._llm_match import build_match_messages, _parse_match_response
from storyloom.user_config import UserConfig


# ═══════════════════════════════════════════════════════════════════════
# Test cases
# ═══════════════════════════════════════════════════════════════════════

TEST_CASES: list[dict] = [
    # ── CHAR_PORTRAIT ──────────────────────────────────────────────────
    {
        "label": "CHAR — exact (hero vs hero)",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target": "hero",
        "expected": "hero",
        "entries": [
            ("hero", "A brave knight in silver armor"),
            ("mage", "A wise old wizard with a staff"),
            ("rogue", "A shadowy figure in a dark cloak"),
        ],
    },
    {
        "label": "CHAR — variant (hero_hurt vs hero)",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target": "hero_hurt",
        "expected": "hero",
        "entries": [
            ("hero", "A brave knight in silver armor"),
            ("mage", "A wise old wizard with a staff"),
            ("rogue", "A shadowy figure in a dark cloak"),
        ],
    },
    {
        "label": "CHAR — variant with dot (Jack.smile vs jack_smile)",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target": "Jack.smile",
        "expected": "jack_smile",
        "entries": [
            ("jack_smile", "Jack with a warm, friendly smile"),
            ("jack_angry", "Jack with a furious scowl, fists clenched"),
            ("jack_neutral", "Jack with a blank, unreadable expression"),
            ("anna", "A mysterious woman in a red dress"),
        ],
    },
    {
        "label": "CHAR — semantic (Alice.happy matches smile, not sad/base)",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target": "Alice.happy",
        "expected": "Alice.smile",
        "entries": [
            ("Alice", "A young woman with blue hair and a gentle expression"),
            ("Alice.sad", "A young woman with blue hair, looking down with sorrow"),
            ("Alice.smile", "A young woman with blue hair and a gentle smile"),
            ("Bob", "A tall warrior in plate armor"),
        ],
    },
    # ── BACKGROUND ────────────────────────────────────────────────────
    {
        "label": "BG — exact (tavern vs tavern)",
        "asset_type": AssetType.BACKGROUND,
        "target": "tavern",
        "expected": "tavern",
        "entries": [
            ("tavern", "A dimly lit medieval tavern"),
            ("forest", "A dark enchanted forest"),
            ("castle", "An ancient stone fortress on a windswept cliff"),
        ],
    },
    {
        "label": "BG — variant (forest_night vs forest, not castle/town)",
        "asset_type": AssetType.BACKGROUND,
        "target": "forest_night",
        "expected": "forest",
        "entries": [
            ("forest", "A dark enchanted forest with towering ancient trees"),
            ("castle", "An ancient stone fortress on a windswept cliff"),
            ("town", "A bustling medieval market town at noon"),
        ],
    },
    {
        "label": "BG — semantic (grove vs forest)",
        "asset_type": AssetType.BACKGROUND,
        "target": "grove",
        "expected": "forest",
        "entries": [
            ("beach", "A sunny tropical beach with turquoise water"),
            ("forest", "A dark enchanted forest with towering ancient trees"),
            ("cave", "A damp underground cavern with glowing crystals"),
        ],
    },
    # ── Realistic roster (10 entries) ──────────────────────────────────
    {
        "label": "CHAR — large roster (hero_hurt among 10 entries)",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target": "hero_hurt",
        "expected": "hero",
        "entries": [
            ("hero", "A brave knight in silver armor, scarred but noble"),
            ("mage", "A wise old wizard with a long white beard and oak staff"),
            ("rogue", "A shadowy figure in a dark cloak, daggers at the belt"),
            ("blacksmith", "A burly woman with soot-stained hands and a leather apron"),
            ("innkeeper", "A portly man with a warm smile and a stained apron"),
            ("guard_captain", "A stern woman in polished steel plate, spear in hand"),
            ("priestess", "A serene young woman in white robes, golden amulet glowing"),
            ("merchant", "A nervous man in fine silks, counting coins obsessively"),
            ("bard", "A flamboyant elf with a lute and a mischievous grin"),
            ("alchemist", "A hunched figure in stained robes, surrounded by vials"),
        ],
    },
    # ── Chinese language ──────────────────────────────────────────────
    {
        "label": "CHAR — zh-CN variant (小明.生气 → 小明)",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target": "小明.生气",
        "expected": "小明",
        "entries": [
            ("小明", "一个戴眼镜的初中男生，穿着蓝色校服"),
            ("小红", "一个扎马尾的初中女生，性格开朗"),
            ("班主任", "一位严肃的中年女教师，戴着金丝眼镜"),
            ("校长", "一位慈祥的老人，头发花白"),
        ],
    },
    {
        "label": "CHAR — zh-CN semantic (神秘女子.微笑 → 老板娘)",
        "asset_type": AssetType.CHAR_PORTRAIT,
        "target": "神秘女子.微笑",
        "expected": "老板娘",
        "entries": [
            ("老板娘", "一位神秘而优雅的女子，嘴角挂着若有若无的微笑，穿着暗红色旗袍"),
            ("店小二", "一个瘦小的少年，动作麻利，总是低着头"),
            ("老顾客", "一位白发苍苍的老者，总是坐在角落的位置"),
            ("说书人", "一个留着山羊胡的中年人，声音洪亮"),
        ],
    },
    {
        "label": "BG — zh-CN variant (桃花林.夜晚 → 桃花林)",
        "asset_type": AssetType.BACKGROUND,
        "target": "桃花林.夜晚",
        "expected": "桃花林",
        "entries": [
            ("桃花林", "一片盛开的桃花林，粉色花瓣随风飘落"),
            ("山洞", "一个幽深的山洞，洞壁上闪烁着微弱的磷光"),
            ("古镇街道", "青石板铺成的古街，两旁是木质阁楼，挂着红灯笼"),
            ("竹林", "一片茂密的翠绿竹林，阳光透过竹叶洒下斑驳光影"),
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════

def main():
    cfg = UserConfig(str(PROJECT_ROOT))
    api = ApiClient(config=cfg)
    model = api.model
    base_url = api.base_url
    print(f"Model : {model}")
    print(f"Base  : {base_url}")
    print(f"Mode  : disabled thinking")
    print("=" * 72)

    disabled_params = get_thinking_params(model, "disabled")
    passed = 0
    failed = 0

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        library = AssetLibrary(tmpdir)

        for i, case in enumerate(TEST_CASES):
            label = case["label"]
            asset_type = case["asset_type"]
            target = case["target"]
            expected = case["expected"]
            entries_data = case["entries"]

            # Build roster
            roster = GameAssetRoster("lab", library)
            for name, desc in entries_data:
                roster.add(asset_type, name, desc)

            # Build messages
            messages = build_match_messages(asset_type, target, roster)
            if not messages:
                print(f"\n[{i + 1}] {label}")
                print("  SKIP: empty roster")
                continue

            # Call API (streaming — to measure TTFT)
            t_start = time.perf_counter()
            try:
                result = api.stream_chat(
                    messages=messages,
                    max_tokens=64,
                    response_format={"type": "json_object"},
                    extra_params=disabled_params,
                )
                elapsed = time.perf_counter() - t_start
                raw = result.content
                ttft = result.ttft
            except Exception as exc:
                elapsed = time.perf_counter() - t_start
                print(f"\n[{i + 1}] {label}")
                print(f"  API ERROR ({elapsed:.1f}s): {exc}")
                failed += 1
                continue

            # Parse
            entries = roster.list_by_type(asset_type)
            parsed = _parse_match_response(raw, entries)
            ok = (parsed == expected)

            if ok:
                passed += 1
                verdict = "\033[32mPASS\033[0m"
            else:
                failed += 1
                verdict = f"\033[31mFAIL (expected {expected!r})\033[0m"

            # Display
            print(f"\n[{i + 1}] {label}")
            print(f"  Target   : {target!r}")
            print(f"  Entries  : {list(entries.keys())}")
            print(f"  TTFT     : {ttft:.2f}s" if ttft else "  TTFT     : —")
            print(f"  Total    : {elapsed:.1f}s")
            print(f"  Raw      : {raw.strip()}")
            print(f"  Parsed   : {parsed!r}  {verdict}")

            # Show full prompt on first case only
            if i == 0:
                print(f"\n{'─' * 60}")
                print("  [SYSTEM PROMPT (first case)]:")
                for line in messages[0]["content"].splitlines():
                    print(f"    | {line}")
                print(f"\n  [USER MESSAGE (first case)]:")
                for line in messages[1]["content"].splitlines():
                    print(f"    | {line}")
                print(f"{'─' * 60}")

    print(f"\n{'=' * 72}")
    print(f"Passed: {passed}/{passed + failed}")
    if failed:
        print(f"Failed: {failed}/{passed + failed}")
    print("Done.")


if __name__ == "__main__":
    main()

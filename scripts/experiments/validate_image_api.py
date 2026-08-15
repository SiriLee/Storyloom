#!/usr/bin/env python3
"""Image generation validation tool for Storyloom Phase 2.

Tests text-to-image + character consistency + background generation
using the PRODUCTION ImgApiClient (``storyloom.io.img_api_client``) and
UserConfig (``storyloom.user_config``).

This script is the integration-test counterpart to the unit tests in
``tests/test_img_api_client.py`` — it validates that the real API call
chain works end-to-end with live credentials.

Unlike the earlier prototype (which duplicated detect_format, detect_alpha,
remove_background, etc.), this version delegates entirely to the production
modules added in 7.3:

    ImgApiClient  →  storyloom.io.img_api_client.ImgApiClient
    ImageResult   →  storyloom.io.img_api_client.ImageResult
    ImageSize     →  storyloom.io.img_api_client.ImageSize
    img_utils     →  storyloom.io.img_utils (maybe_remove_background, etc.)
    UserConfig    →  storyloom.user_config.UserConfig

Config resolution (matches 7.3 design):
    Priority: env var → UserConfig field → default in config.py
    Key:      IMAGE_API_KEY → img_api_key → LLM_API_KEY → api_key
    URL:      IMAGE_BASE_URL → img_api_base_url → DEFAULT_IMG_BASE_URL
    Model:    IMAGE_MODEL → img_api_model → DEFAULT_IMG_MODEL
    RemBG:    portrait_remove_bg (config.json) → "auto"

============================================================================
Usage:
    # Use config.json from project root (default)
    python scripts/experiments/validate_image_api.py

    # Explicit app directory
    python scripts/experiments/validate_image_api.py --app-dir ~/.storyloom

    # Env var overrides (same pattern as LLM)
    IMAGE_API_KEY=sk-xxx python scripts/experiments/validate_image_api.py
    IMAGE_MODEL=seedream-5-0-260128 python scripts/experiments/validate_image_api.py

    # WSL2 with proxy (httpx reads HTTP_PROXY/HTTPS_PROXY automatically)
    python scripts/experiments/validate_image_api.py
============================================================================
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

# Ensure the project root is on sys.path so storyloom is importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from storyloom.io._types import ImageResult, ImageSize, RemoveBgPolicy
from storyloom.io.img_api_client import (
    MODEL_PRESETS,
    ImageApiError,
    ImgApiClient,
)
from storyloom.io.img_utils import (
    check_model,
    detect_alpha,
    detect_format,
    get_dimensions,
    maybe_remove_background,
)
from storyloom.user_config import UserConfig


# ══════════════════════════════════════════════════════════════════════
#  Prompts — anime visual novel style
# ══════════════════════════════════════════════════════════════════════

PORTRAIT_PROMPT = (
    "A young female warrior with silver hair and blue eyes, "
    "wearing simple leather armor. "
    "Anime art style, soft cel shading, waist-up portrait, "
    "clean lines, transparent background, no background, "
    "isolated character on white."
)

CONSISTENCY_PROMPT = (
    "Same character as the reference image: a young female warrior "
    "with silver hair and blue eyes, wearing simple leather armor. "
    "Now she has a gentle smile and a slightly tilted head. "
    "Keep the character appearance identical to the reference image. "
    "Anime art style, soft cel shading, waist-up portrait, "
    "transparent background, no background, isolated character on white."
)

BACKGROUND_PROMPT = (
    "A medieval fantasy tavern interior, warm candlelight, "
    "wooden tables and chairs, a fireplace on the wall, "
    "wide establishing shot, atmospheric, anime art style, "
    "simple and clean composition."
)


# ══════════════════════════════════════════════════════════════════════
#  Output
# ══════════════════════════════════════════════════════════════════════

OUTPUT_DIR = _PROJECT_ROOT / "temp" / "image_api_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save(result: ImageResult | None, stem: str) -> None:
    """Write to OUTPUT_DIR with format-aware extension and alpha tag."""
    if result is None:
        return
    ext = result.format if result.format in ("png", "webp", "jpeg") else "png"
    tag = "_rgba" if result.has_alpha else ""
    path = OUTPUT_DIR / f"{stem}{tag}.{ext}"
    path.write_bytes(result.bytes)
    size_kb = len(result.bytes) // 1024
    print(f"    -> {path.name}  ({size_kb} KB)")


def divider(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


# ══════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate image generation API using production ImgApiClient",
    )
    parser.add_argument(
        "--app-dir", type=str, default=str(_PROJECT_ROOT),
        help="Directory containing config.json (default: project root)",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Override model (env: IMAGE_MODEL)",
    )
    parser.add_argument(
        "--base-url", type=str, default=None,
        help="Override base URL (env: IMAGE_BASE_URL)",
    )
    parser.add_argument(
        "--api-key", type=str, default=None,
        help="Override API key (env: IMAGE_API_KEY)",
    )
    parser.add_argument(
        "--remove-bg", type=str, default=None,
        choices=["auto", "always", "never"],
        help="Override portrait background removal policy (config: portrait_remove_bg)",
    )
    parser.add_argument(
        "--skip-consistency", action="store_true",
        help="Skip the character consistency test",
    )
    parser.add_argument(
        "--skip-background", action="store_true",
        help="Skip the background generation test",
    )
    args = parser.parse_args()

    # Apply CLI overrides via env vars (so ImgApiClient picks them up)
    if args.model:
        os.environ["IMAGE_MODEL"] = args.model
    if args.base_url:
        os.environ["IMAGE_BASE_URL"] = args.base_url
    if args.api_key:
        os.environ["IMAGE_API_KEY"] = args.api_key
    # ── Load config ──────────────────────────────────────────────────
    app_dir = Path(args.app_dir)
    cfg = UserConfig(app_dir)

    # CLI override for bg removal (applied after config load so
    # config.json is not mutated — --remove-bg affects this run only).
    if args.remove_bg:
        cfg.portrait_remove_bg = args.remove_bg

    if cfg.needs_migration:
        print(f"⚠  Config version mismatch (file v{cfg._version}, "
              f"expected v{UserConfig._DEFAULTS['version']})")
        print("   Old values loaded in memory; image key falls back to LLM key.")
        print()

    # ── Create client ─────────────────────────────────────────────────
    portrait_policy = RemoveBgPolicy(cfg.portrait_remove_bg)
    client = ImgApiClient(cfg, remove_bg=portrait_policy)

    if not client.api_key:
        print("ERROR: No image API key configured.")
        print()
        print("Set any of:")
        print("  - IMAGE_API_KEY environment variable")
        print("  - img_api_key in config.json (Settings page)")
        print("  - LLM_API_KEY environment variable (fallback)")
        print("  - api_key in config.json (fallback)")
        sys.exit(1)

    # ── Config summary ───────────────────────────────────────────────
    preset = MODEL_PRESETS.get(client.model)
    label = preset.label if preset else client.model
    p_size = client._resolve_size(ImageSize.PORTRAIT)
    b_size = client._resolve_size(ImageSize.BACKGROUND)

    print(client.config_summary)
    print(f"Preset:           {label}")
    print(f"Portrait size:    {p_size}")
    print(f"Background size:  {b_size}")
    print(f"Model available:  {check_model()}")
    print(f"Output:           {OUTPUT_DIR}")

    # Wall-clock for all tests
    t_start = time.perf_counter()
    results: list[ImageResult] = []

    # ── Portrait ─────────────────────────────────────────────────────
    divider(f"Portrait  ({p_size}) — waist-up, transparent bg prompt")
    try:
        portrait = client.generate(
            PORTRAIT_PROMPT, ImageSize.PORTRAIT,
        )
        print(f"    {portrait.format}  {portrait.width}x{portrait.height}  "
              f"alpha={portrait.has_alpha}  ({len(portrait.bytes)} bytes, "
              f"{portrait.elapsed_ms:.0f}ms)")
        save(portrait, "01_portrait")
        results.append(portrait)
    except (ImageApiError, ValueError) as e:
        print(f"    FAILED: {e}")
        portrait = None

    # ── Consistency ─────────────────────────────────────────────────
    consistent = None
    ref_url = portrait.url if portrait and portrait.url else None
    if ref_url and not args.skip_consistency:
        divider(f"Consistency  ({p_size}) — same char, different pose")
        try:
            consistent = client.generate(
                CONSISTENCY_PROMPT, ImageSize.PORTRAIT,
                image_urls=[ref_url],
            )
            print(f"    {consistent.format}  "
                  f"{consistent.width}x{consistent.height}  "
                  f"alpha={consistent.has_alpha}  "
                  f"({len(consistent.bytes)} bytes, "
                  f"{consistent.elapsed_ms:.0f}ms)")
            save(consistent, "02_consistent")
            results.append(consistent)
        except (ImageApiError, ValueError) as e:
            print(f"    FAILED: {e}")
    elif not ref_url:
        print("\n  SKIP: consistency — no URL from portrait (model may use b64)")

    # ── Background ──────────────────────────────────────────────────
    if not args.skip_background:
        divider(f"Background  ({b_size}) — 16:9 scene")
        try:
            bg = client.generate(
                BACKGROUND_PROMPT, ImageSize.BACKGROUND,
                remove_bg=RemoveBgPolicy.NEVER,
            )
            print(f"    {bg.format}  {bg.width}x{bg.height}  "
                  f"alpha={bg.has_alpha}  ({len(bg.bytes)} bytes, "
                  f"{bg.elapsed_ms:.0f}ms)")
            save(bg, "03_background")
            results.append(bg)
        except (ImageApiError, ValueError) as e:
            print(f"    FAILED: {e}")

    # ── Summary ─────────────────────────────────────────────────────
    divider("Summary")
    total_time = time.perf_counter() - t_start
    total_api_ms = sum(r.elapsed_ms for r in results) / 1000

    _MODEL_PRICES = {
        "flux-2-pro": 0.03,
        "seedream-5-0-260128": 0.035,
        "gemini-3.1-flash-lite-image": 0.025,
    }
    unit_price = _MODEL_PRICES.get(client.model, 0.03)
    total_cost = unit_price * len(results)

    print(f"  Model:     {label} ({client.model})")
    print(f"  Results:   {len(results)} generated")
    print(f"  API time:  {total_api_ms:.0f}s total")
    print(f"  Wall time: {total_time:.0f}s total")
    print(f"  Cost:      ~${total_cost:.2f}  (${unit_price}/image)")

    alpha_count = sum(1 for r in results if r.has_alpha)
    print(f"  Alpha:     {alpha_count}/{len(results)} have transparency")
    if alpha_count == 0 and client.remove_bg_policy == RemoveBgPolicy.AUTO:
        print("             (none — rembg applied to portraits automatically)")

    print(f"\n  Files:")
    for f in sorted(OUTPUT_DIR.iterdir()):
        size_kb = f.stat().st_size // 1024
        print(f"    {f.name:40s} {size_kb:>5} KB")

    print(f"\n  Run: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Config: {app_dir / 'config.json'}")


if __name__ == "__main__":
    main()

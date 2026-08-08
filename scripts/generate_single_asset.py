"""Generate a single system asset for testing and iteration.

Reads API configuration from ``UserConfig`` at runtime (no hardcoded keys).
Uses the prompt from ``system_media_src/{type}.json``.

Usage::

    python scripts/generate_single_asset.py sys_student_female
    python scripts/generate_single_asset.py sys_classroom --dry-run
    python scripts/generate_single_asset.py sys_doctor_male --model flux-2-pro
    python scripts/generate_single_asset.py sys_tavern --force --app-dir ~/.storyloom
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts._sysgen_utils import (
    find_asset,
    get_image_size,
    get_remove_bg,
    normalize_background,
    output_path,
)
from storyloom.assets._types import AssetType
from storyloom.io._types import ImageSize, RemoveBgPolicy
from storyloom.io.img_api_client import ImageApiError, ImgApiClient
from storyloom.user_config import UserConfig


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a single system asset"
    )
    parser.add_argument(
        "asset_id",
        help="Asset ID to generate (e.g. sys_student_female, sys_classroom)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be generated without making API calls",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing file if present",
    )
    parser.add_argument(
        "--model", type=str, default=None,
        help="Override image model (default: from UserConfig)",
    )
    parser.add_argument(
        "--base-url", type=str, default=None,
        help="Override image API base URL (default: from UserConfig)",
    )
    parser.add_argument(
        "--app-dir", type=str, default=str(_PROJECT_ROOT),
        help="Directory containing config.json (default: project root)",
    )
    args = parser.parse_args()

    # ── Find asset ────────────────────────────────────────────────────
    result = find_asset(args.asset_id)
    if result is None:
        print(f"ERROR: Asset not found: {args.asset_id}")
        print("Run with just the asset ID (no path), e.g.:")
        print("  python scripts/generate_single_asset.py sys_student_female")
        sys.exit(1)

    asset_type, entry = result
    name = entry["name"]
    desc = entry["description"]
    prompt = entry["prompt"]
    out = output_path(asset_type, args.asset_id)
    size = get_image_size(asset_type)

    # ── Load config ───────────────────────────────────────────────────
    cfg = UserConfig(Path(args.app_dir))
    if args.model:
        cfg.img_api_model = args.model
    if args.base_url:
        cfg.img_api_base_url = args.base_url

    # ── Resolve bg removal policy ─────────────────────────────────────
    remove_bg = get_remove_bg(asset_type)
    if remove_bg is None:
        # CHAR_PORTRAIT — read from user config
        remove_bg = RemoveBgPolicy(cfg.portrait_remove_bg)

    client = ImgApiClient(cfg, remove_bg=remove_bg)

    # ── Dry run ───────────────────────────────────────────────────────
    if args.dry_run:
        print(f"Asset:    {args.asset_id}")
        print(f"Name:     {name}")
        print(f"Type:     {asset_type.value}")
        print(f"Size:     {client._resolve_size(size)}  ({size.value})")
        print(f"RemoveBG: {remove_bg.value}")
        print(f"Model:    {client.model}")
        print(f"Base URL: {client.base_url}")
        print(f"Output:   {out}")
        print(f"Exists:   {'yes (use --force to overwrite)' if out.exists() else 'no'}")
        print(f"\nPrompt ({len(prompt)} chars):")
        print(prompt)
        return

    # ── Check existing ────────────────────────────────────────────────
    if out.exists() and not args.force:
        print(f"SKIP: {out} already exists (use --force to overwrite)")
        return

    # ── Generate ──────────────────────────────────────────────────────
    print(f"Generating: {args.asset_id}  ({name})")
    print(f"  Type:     {asset_type.value}")
    print(f"  Size:     {client._resolve_size(size)}")
    print(f"  Model:    {client.model}")
    print(f"  RemoveBG: {remove_bg.value}")
    print(f"  Prompt:   {prompt[:100]}...")

    t0 = time.perf_counter()
    try:
        result = client.generate(prompt, size, remove_bg=remove_bg)
    except (ImageApiError, ValueError) as e:
        print(f"  FAILED: {e}")
        sys.exit(1)

    elapsed_s = time.perf_counter() - t0

    # ── Post-process: enforce 16:9 aspect ratio for backgrounds ──────
    raw = result.bytes
    if asset_type is AssetType.BACKGROUND:
        raw = normalize_background(raw)

    # ── Save ──────────────────────────────────────────────────────────
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)

    print(f"  Saved:    {out}  ({len(result.bytes)} bytes)")
    print(f"  Format:   {result.format}  {result.width}x{result.height}")
    print(f"  Alpha:    {result.has_alpha}")
    print(f"  Time:     {result.elapsed_ms:.0f}ms API  /  {elapsed_s:.1f}s wall")


if __name__ == "__main__":
    main()

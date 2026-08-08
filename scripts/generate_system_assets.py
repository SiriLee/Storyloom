"""Batch generate all system assets from ``system_media_src/`` sources.

Reads API configuration from ``UserConfig`` at runtime.  Assets that
already exist on disk are skipped unless ``--force`` is passed.

Usage::

    python scripts/generate_system_assets.py
    python scripts/generate_system_assets.py --type char_portrait
    python scripts/generate_system_assets.py --dry-run
    python scripts/generate_system_assets.py --force
    python scripts/generate_system_assets.py --start sys_classroom
    python scripts/generate_system_assets.py --only sys_student_female,sys_classroom
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
    get_image_size,
    get_remove_bg,
    load_source,
    normalize_background,
    output_dir,
    output_path,
)
from storyloom.assets._types import AssetType
from storyloom.io._types import RemoveBgPolicy
from storyloom.io.img_api_client import ImageApiError, ImgApiClient
from storyloom.user_config import UserConfig


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch generate system assets"
    )
    parser.add_argument(
        "--type", type=str, default=None,
        choices=["char_portrait", "background_img"],
        help="Only generate assets of this type",
    )
    parser.add_argument(
        "--only", type=str, default=None,
        help="Comma-separated asset IDs to generate (ignores --type and --start)",
    )
    parser.add_argument(
        "--start", type=str, default=None,
        help="Resume generation from this asset ID (inclusive)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="List assets without generating",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Overwrite existing files",
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

    # ── Load config ───────────────────────────────────────────────────
    cfg = UserConfig(Path(args.app_dir))
    if args.model:
        cfg.img_api_model = args.model
    if args.base_url:
        cfg.img_api_base_url = args.base_url

    portrait_policy = RemoveBgPolicy(cfg.portrait_remove_bg)

    # ── Build asset list ──────────────────────────────────────────────
    asset_types: list[AssetType]
    if args.type:
        atype = AssetType(args.type)
        asset_types = [atype]
    else:
        asset_types = [AssetType.CHAR_PORTRAIT, AssetType.BACKGROUND]

    tasks: list[tuple[AssetType, str, dict]] = []
    for atype in asset_types:
        source = load_source(atype)
        for asset_id, entry in source.items():
            if args.only:
                allowed = set(args.only.split(","))
                if asset_id not in allowed:
                    continue
            tasks.append((atype, asset_id, entry))

    # Respect --start (skipped when --only is set — see docs)
    if args.start and not args.only:
        filtered = []
        found = False
        for t in tasks:
            if t[1] == args.start:
                found = True
            if found:
                filtered.append(t)
        tasks = filtered
        if not found:
            print(f"WARNING: --start {args.start} not found, nothing to generate")

    if not tasks:
        print("No assets to generate.")
        return

    # ── Dry run ───────────────────────────────────────────────────────
    if args.dry_run:
        print(f"Would generate {len(tasks)} asset(s):\n")
        for atype, aid, entry in tasks:
            out = output_path(atype, aid)
            exists = "EXISTS" if out.exists() else "new"
            print(f"  {aid:30s}  {atype.value:16s}  {exists}")
        return

    # ── Generate ──────────────────────────────────────────────────────
    output_dir().mkdir(parents=True, exist_ok=True)

    ok, skipped, failed = 0, 0, 0
    t_start = time.perf_counter()
    total_bytes = 0

    for atype, aid, entry in tasks:
        out = output_path(atype, aid)
        name = entry["name"]
        prompt = entry["prompt"]
        size = get_image_size(atype)
        remove_bg = get_remove_bg(atype)
        if remove_bg is None:
            remove_bg = portrait_policy

        # Skip existing
        if out.exists() and not args.force:
            print(f"SKIP  {aid}  (already exists)")
            skipped += 1
            continue

        # Create client (per-thread model for potential future parallelism)
        client = ImgApiClient(cfg, remove_bg=remove_bg)

        status = f"[{ok + skipped + failed + 1}/{len(tasks)}]"
        print(f"{status} {aid}  ({name}) ... ", end="", flush=True)

        try:
            result = client.generate(prompt, size, remove_bg=remove_bg)
        except (ImageApiError, ValueError) as e:
            print(f"FAILED: {e}")
            failed += 1
            continue

        # Post-process: enforce 16:9 aspect ratio for backgrounds
        raw = result.bytes
        if atype is AssetType.BACKGROUND:
            raw = normalize_background(raw)

        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(raw)
        total_bytes += len(result.bytes)

        print(f"OK  {result.width}x{result.height}  "
              f"{result.elapsed_ms:.0f}ms  "
              f"alpha={result.has_alpha}")
        ok += 1

    # ── Summary ───────────────────────────────────────────────────────
    elapsed = time.perf_counter() - t_start
    print(f"\n{'='*50}")
    print(f"Done: {ok} OK, {skipped} skipped, {failed} failed"
          f"  ({elapsed:.0f}s wall)")
    if ok:
        print(f"Output: {total_bytes / 1024:.0f} KiB total"
              f"  ({output_dir()})")


if __name__ == "__main__":
    main()

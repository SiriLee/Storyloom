#!/usr/bin/env python3
"""Concurrent image generation stress test — diagnose apiyi rate limiting.

============================================================================
Results (2026-08-11, apiyi + flux-2-pro, zero reference images)
============================================================================

  workers=6 (default), 8 images, zero-ref prompts:
    min=10.8s  p50=12.8s  p95=14.6s  max=14.6s  wall=24s  errors=0
    ✅ No slowdown — concurrency is safe at 6.

  workers=8, 8 images, zero-ref prompts:
    min=22.9s  p50=23.7s  p95=24.1s  max=24.1s  wall=24s  errors=1/8
    ⚠️  2x slowdown + connection resets — apiyi throttles at 8.

Key findings:
  1. apiyi concurrency limit for a single API key is ~6.
     Beyond 6, per-call latency doubles (13s→23s) and
     connection-reset errors appear (~12%).
  2. At workers≤6, per-call latency matches serial baseline.
     No penalty for concurrency at safe levels.
  3. Even with 2x slowdown at 8 workers, total wall time
     (24s for 8 images) still beats serial (8×13=104s).

Implications for Storyloom:
  - Prebuilder max_workers set to 6 (prebuild.py).
  - Gameplay DECLARE triggers are typically 1-2 at a time
    → naturally serial, no concurrency concern.

Note: this test used zero reference images. The dominant
speed factor is reference images, NOT concurrency.
See bench_ref_images.py for reference-image benchmark.

Usage:
    IMAGE_API_KEY=sk-xxx python scripts/stress_test_image_api.py [--workers N] [--count N]
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from storyloom.io.img_api_client import ImgApiClient
from storyloom.io._types import ImageSize, RemoveBgPolicy
from storyloom.user_config import UserConfig

API_KEY = os.environ.get("IMAGE_API_KEY", "")
BASE_URL = os.environ.get("IMAGE_BASE_URL", "https://api.apiyi.com/v1")
MODEL = os.environ.get("IMAGE_MODEL", "flux-2-pro")

COUNT = 4
WORKERS = 6
i = 1
while i < len(sys.argv):
    if sys.argv[i] == "--count" and i + 1 < len(sys.argv):
        COUNT = int(sys.argv[i + 1]); i += 2
    elif sys.argv[i] == "--workers" and i + 1 < len(sys.argv):
        WORKERS = int(sys.argv[i + 1]); i += 2
    else:
        i += 1

P_PORTRAIT = (
    "A young female warrior with silver hair and blue eyes, "
    "wearing simple leather armor. Anime art style, soft cel shading, "
    "waist-up portrait, clean lines, isolated character on white."
)
P_BG = (
    "A medieval fantasy tavern interior, warm candlelight, "
    "wooden tables and chairs, fireplace on the wall, "
    "wide establishing shot, atmospheric, anime art style."
)


def _cfg() -> UserConfig:
    """Build a minimal headless config for testing."""
    c = UserConfig()
    c._api_key = API_KEY
    c._img_api_key = API_KEY
    c._img_api_base_url = BASE_URL
    c._img_api_model = MODEL
    return c


def client_portrait() -> ImgApiClient:
    return ImgApiClient(_cfg(), remove_bg=RemoveBgPolicy.AUTO)

def client_bg() -> ImgApiClient:
    return ImgApiClient(_cfg(), remove_bg=RemoveBgPolicy.NEVER)


def one(kind: str, i: int) -> dict:
    if kind == "P":
        size, prompt, cl = ImageSize.PORTRAIT, P_PORTRAIT, client_portrait()
    else:
        size, prompt, cl = ImageSize.BACKGROUND, P_BG, client_bg()
    label = f"{kind}{i}"
    t0 = time.perf_counter()
    try:
        r = cl.generate(prompt, size)
        t = time.perf_counter() - t0
        return {"label": label, "ok": True, "elapsed": t}
    except Exception as e:
        return {"label": label, "ok": False, "elapsed": time.perf_counter() - t0, "error": str(e)[:120]}


def main() -> None:
    if not API_KEY:
        print("ERROR: IMAGE_API_KEY not set."); sys.exit(1)

    total = COUNT * 2
    workers = min(WORKERS, total)
    print(f"Model: {MODEL}  |  {total} images  |  {workers} workers")
    print(f"  ({COUNT} portraits + {COUNT} backgrounds)")
    print()

    tasks = [(kind, i) for kind in ("P", "B") for i in range(1, COUNT + 1)]
    results: list[dict] = []

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(one, kind, i): f"{kind}{i}" for kind, i in tasks}
        for f in as_completed(futures):
            r = f.result()
            results.append(r)
            status = "OK" if r["ok"] else "FAIL"
            print(f"  [{r['label']}] {status}  {r['elapsed']:.1f}s", end="")
            if not r["ok"]:
                print(f"  {r.get('error', '')}", end="")
            print()

    wall = time.perf_counter() - t0

    ok = [r for r in results if r["ok"]]
    fail = [r for r in results if not r["ok"]]
    times = sorted(r["elapsed"] for r in ok)

    print(f"\n{'='*60}")
    print(f"  Submitted: {len(tasks)}   OK: {len(ok)}   FAIL: {len(fail)}")
    print(f"  Wall time: {wall:.0f}s  (all at once)")
    if times:
        print(f"  Per-call:  min={times[0]:.1f}s  p50={times[len(times)//2]:.1f}s  "
              f"p95={times[int(len(times)*0.9)]:.1f}s  max={times[-1]:.1f}s")
        if times[-1] < 20:
            print("  ✅  No slowdown — concurrency is safe.")
        elif times[-1] < 35:
            print("  ⚡  Mild slowdown — still acceptable.")
        else:
            print("  ⚠️  Significant slowdown under concurrency — reduce max_workers.")


if __name__ == "__main__":
    main()

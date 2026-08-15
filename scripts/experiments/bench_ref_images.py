#!/usr/bin/env python3
"""Benchmark reference-image impact on FLUX.2 Pro generation speed.

============================================================================
Results (2026-08-11, apiyi + flux-2-pro, production build_generation_prompt)
============================================================================

    Scenario    Avg       Values
    ─────────────────────────────────────────
    0 ref       14.6s     16.6s  12.7s
    1 ref       31.6s     32.9s  30.4s       (+17s,  2.2x)
    3 refs      63.8s     50.9s  76.6s       (+49s,  4.4x)

Key findings:
  1. Reference images massively slow down FLUX.2 Pro on apiyi.
     Each reference adds ~15-20s of processing time.
  2. This is the ROOT CAUSE of the ">1 minute per image" issue
     in co-creation prebuild — system_media reference images
     were being passed via _collect_library_refs().
  3. Zero-reference generation is consistently 13-17s, matching
     the original serial validation test.
  4. The slowdown is server-side (model processing), not network
     I/O — base64 upload is sub-second, extra time is inference.

Implications for Storyloom:
  - _collect_library_refs() in prebuild.py passes up to 3
    reference images per entity → each entity takes 50-77s.
  - _collect_reference_images() in _llm_generate.py does the
    same during gameplay DECLARE → same slowdown.
  - Fix: reduce GENERATE_REF_IMAGE_COUNT (config.py) or disable
    reference images entirely for speed-prioritized models.

Reference images: system_media/char_portrait/*.png (3 PNG files).
Prompt: build_generation_prompt(AssetType.CHAR_PORTRAIT, ...) —
       identical to production co-creation code path.
Timing: client.generate() wall-clock (API + download + rembg).

Usage:
    IMAGE_API_KEY=sk-xxx python scripts/experiments/bench_ref_images.py
"""

from __future__ import annotations

import base64
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from storyloom.assets import AssetType
from storyloom.io._types import ImageSize, RemoveBgPolicy
from storyloom.io.img_api_client import ImgApiClient
from storyloom.io.img_prompts import build_generation_prompt
from storyloom.user_config import UserConfig

# ── Config ─────────────────────────────────────────────────────────
API_KEY = os.environ.get("IMAGE_API_KEY", "")
MODEL = os.environ.get("IMAGE_MODEL", "flux-2-pro")
BASE_URL = os.environ.get("IMAGE_BASE_URL", "https://api.apiyi.com/v1")
ITERATIONS = 2

# ── Reference images from system_media ─────────────────────────────
_SYS = ROOT / "system_media" / "char_portrait"
REF_CANDIDATES = sorted(_SYS.glob("*.png"))[:3]  # first 3 PNG only
REFS: list[str] = []
for p in REF_CANDIDATES:
    raw = p.read_bytes()
    REFS.append(f"data:image/png;base64,{base64.b64encode(raw).decode()}")

# ── Production prompt (same string template as co-creation) ───────
CHAR_NAME = "Elara"
CHAR_DESC = (
    "A fierce yet kind warrior princess with flowing silver hair, "
    "piercing blue eyes, and a determined expression. She wears "
    "ornate silver armor over a deep blue tunic."
)

P0 = build_generation_prompt(AssetType.CHAR_PORTRAIT, CHAR_NAME, CHAR_DESC, has_reference=False)
P1 = build_generation_prompt(AssetType.CHAR_PORTRAIT, CHAR_NAME, CHAR_DESC, has_reference=True)
# same prompt for 1 ref and 3 refs


def client() -> ImgApiClient:
    c = UserConfig()
    c._api_key = API_KEY
    c._img_api_key = API_KEY
    c._img_api_base_url = BASE_URL
    c._img_api_model = MODEL
    return ImgApiClient(c, remove_bg=RemoveBgPolicy.AUTO)


def run(label: str, prompt: str, refs: list[str] | None) -> list[float]:
    times: list[float] = []
    for i in range(ITERATIONS):
        cl = client()
        t0 = time.perf_counter()
        try:
            r = cl.generate(prompt, ImageSize.PORTRAIT, image_urls=refs or None)
            t = time.perf_counter() - t0
            status = "OK" if r else "FAIL"
            print(f"  [{label} #{i+1}] {status}  {t:.1f}s")
            if r:
                times.append(t)
        except Exception as e:
            print(f"  [{label} #{i+1}] FAIL  {time.perf_counter() - t0:.1f}s  {e!s:.120}")
    return times


def main() -> None:
    if not API_KEY:
        print("ERROR: IMAGE_API_KEY not set."); sys.exit(1)

    print(f"Model:  {MODEL}")
    print(f"Refs:   {len(REFS)} images from system_media ({', '.join(p.name for p in REF_CANDIDATES)})")
    print(f"Prompt: production build_generation_prompt (same as co-creation)")
    print(f"Iterations: {ITERATIONS} per scenario")
    print()

    # ── 0 ref ─────────────────────────────────────────────────────
    print("[0 ref] No reference image")
    t0 = run("0ref", P0, None)

    # ── 1 ref ─────────────────────────────────────────────────────
    print("[1 ref] One system_media image as style reference")
    t1 = run("1ref", P1, REFS[:1])

    # ── 3 refs ────────────────────────────────────────────────────
    print("[3 refs] Three system_media images as style reference")
    t3 = run("3ref", P1, REFS[:3])

    # ── Summary ───────────────────────────────────────────────────
    def avg(times: list[float]) -> float:
        return sum(times) / len(times) if times else 0

    print(f"\n{'='*50}")
    print(f"  Scenario    Avg     Values")
    print(f"  {'─'*45}")
    for label, times in [("0 ref", t0), ("1 ref", t1), ("3 refs", t3)]:
        vals = "  ".join(f"{t:.1f}s" for t in times)
        print(f"  {label:10s}  {avg(times):.1f}s    {vals}")

    if t0 and t3:
        a0, a3 = avg(t0), avg(t3)
        diff = a3 - a0
        print(f"\n  3 refs vs 0 ref: +{diff:.1f}s  ({diff/a0*100:.0f}%)")
        if diff < 3:
            print("  ✅ Negligible — reference images don't matter for speed.")
        else:
            print(f"  ⚠️  Noticeable — {diff:.0f}s overhead for 3 reference images.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Image generation validation tool for Storyloom Phase 2.

Tests text-to-image + character consistency + background generation
with configurable models and automatic alpha-channel detection.

============================================================================
Architecture (aligned with 7.3 design)
============================================================================

This script mirrors the planned ImgApiClient interface:

    ImgApiClient.generate(prompt, size, image_urls=None) -> ImageResult
    ImageResult.bytes        — raw image data
    ImageResult.has_alpha    — whether the returned image has RGBA
    ImageResult.format       — "png" | "webp" | "jpeg"

    maybe_remove_background(result, policy="auto") -> ImageResult
        policy: "auto"   → remove bg if no alpha channel (default)
                "always" → force removal
                "never"  → skip removal

Config in UserConfig (planned):
    game_mode       — "text" | "graph"
    img_api_key     — "" = reuse api_key
    img_api_base_url — "" = auto-derive
    img_api_model   — "flux-2-pro" (default recommendation)
    img_remove_bg   — "auto" | "always" | "never"

Env var overrides (same pattern as LLM):
    IMAGE_API_KEY   IMAGE_BASE_URL   IMAGE_MODEL   IMAGE_REMOVE_BG

============================================================================
Default model: FLUX.2 Pro (Black Forest Labs, via apiyi)

Full test results across 3 models (2026-08-05):

    Model                   Price   Portrait     BG         Alpha?   Verdict
    ───────────────────────────────────────────────────────────────────────
    FLUX.2 Pro              $0.030  1024² ~15s   1280 ~10s   No       ✓ BEST
    Nano Banana Lite        $0.025  1024² ~10s   1024 ~10s   No       Style weaker
    Seedream 5.0 Lite       $0.035  2048² ~27s   2560 ~33s   No*      Too slow

    * Seedream docs claim PNG alpha support; apiyi returns RGB only.
      Native BytePlus API may differ.

Resolution rationale:
    Portrait  1024x1024 — square gives model best composition freedom;
              768x1024 tall cropped weirdly in tests.
    Background 1280x720 — 16:9 wide, ~1 MP, matches portrait height.

RemBG overhead (background removal):
    Cold: ~28s (one-time 176 MB model download)
    Warm: ~0.7s per image

Cost estimate per game (~20 images):
    ~$0.60 total ($0.03 × 20)

============================================================================
Usage:
    # Default model (FLUX.2 Pro)
    IMAGE_API_KEY=sk-xxx python scripts/validate_image_api.py

    # Switch model via env
    IMAGE_API_KEY=sk-xxx IMAGE_MODEL=seedream-5-0-260128 python scripts/validate_image_api.py

    # Force background removal on/off
    IMAGE_REMOVE_BG=always python scripts/validate_image_api.py
    IMAGE_REMOVE_BG=never  python scripts/validate_image_api.py

    # WSL2 with proxy
    IMAGE_API_KEY=sk-xxx \
    HTTP_PROXY=http://127.0.0.1:19828 \
    HTTPS_PROXY=http://127.0.0.1:19828 \
    python scripts/validate_image_api.py
============================================================================
"""

from __future__ import annotations

import base64
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import httpx


# ══════════════════════════════════════════════════════════════════════
#  User-configurable settings — change these to test different models
# ══════════════════════════════════════════════════════════════════════

# Default model (overridable via IMAGE_MODEL env var)
DEFAULT_MODEL = "flux-2-pro"

# Platform (overridable via IMAGE_BASE_URL env var)
DEFAULT_BASE_URL = "https://api.apiyi.com/v1"

# Resolution per image type (overridable per-model via PRESETS)
PORTRAIT_SIZE = "1024x1024"
BACKGROUND_SIZE = "1280x720"
CONSISTENCY_SIZE = "1024x1024"

# Background removal policy (overridable via IMAGE_REMOVE_BG env var)
REMOVE_BG: Literal["auto", "always", "never"] = "auto"

# ── Model presets ──────────────────────────────────────────────────

PRESETS: dict[str, dict] = {
    "flux-2-pro": {
        "label": "FLUX.2 Pro",
        "extra": {},
        # no "sizes" → uses defaults (1024x1024, 1280x720)
        "notes": "Best quality/style. No alpha. ~11s portrait, ~17s bg.",
    },
    "seedream-5-0-260128": {
        "label": "Seedream 5.0 Lite",
        "extra": {},
        "sizes": {
            "portrait": "2048x2048",       # min 3,686,400 px → 2048² = 4.2 MP
            "background": "2560x1440",      # 16:9 at 3.7 MP
            "consistency": "2048x2048",
        },
        "notes": "2K min → 25-47s. No alpha on apiyi (may differ on BytePlus).",
    },
    "gemini-3.1-flash-lite-image": {
        "label": "Nano Banana Lite",
        "extra": {},
        # no "sizes" → uses defaults (1K)
        "notes": "Fastest (~10s). Style weaker than FLUX. No alpha.",
    },
}

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
#  Data types — mirrors planned 7.3 ImgApiClient return type
# ══════════════════════════════════════════════════════════════════════

@dataclass
class ImageResult:
    """Result from ImgApiClient.generate().

    Mirrors the planned 7.3 return type — same fields the engine will use.
    """
    bytes: bytes
    format: str          # "png" | "webp" | "jpeg"
    has_alpha: bool      # True if RGBA / VP8X-alpha
    width: int
    height: int
    url: str             # original URL (may expire)
    elapsed: float       # generation time in seconds


# ══════════════════════════════════════════════════════════════════════
#  Image utilities — format detection, alpha check, background removal
# ══════════════════════════════════════════════════════════════════════

def detect_format(raw: bytes) -> str:
    """Detect image format from magic bytes."""
    if raw[:4] == b"RIFF" and len(raw) > 11 and raw[8:12] == b"WEBP":
        return "webp"
    if raw[:2] == b"\xff\xd8":
        return "jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    return "unknown"


def detect_alpha(raw: bytes, fmt: str) -> bool:
    """Check if image has an alpha channel.

    Detects:
      - PNG:  color type 6 (RGBA) or 4 (grayscale+alpha)
      - WebP: VP8X alpha flag (bit 4)
      - JPEG: always False
    """
    if fmt == "png":
        if len(raw) > 25:
            color_type = raw[25]
            return color_type in (4, 6)
        return False
    if fmt == "webp":
        # VP8X chunk: RIFF(12) + "VP8X"(4) + flags(4)
        if len(raw) > 21 and raw[12:16] == b"VP8X":
            return bool(raw[20] & 0x10)
        return False
    return False  # jpeg = no alpha


def get_dimensions(raw: bytes, fmt: str) -> tuple[int, int]:
    """Extract image width and height from headers.

    Returns (0, 0) on failure (caller should handle gracefully).
    """
    try:
        import struct
        if fmt == "png":
            return struct.unpack(">II", raw[16:24])
        if fmt == "webp":
            if raw[12:16] == b"VP8X":
                w = struct.unpack_from("<I", raw, 24)[0] & 0xFFFFFF
                h = struct.unpack_from("<I", raw, 27)[0] & 0xFFFFFF
                return w, h
            if raw[12:16] == b"VP8 ":
                return struct.unpack_from("<HH", raw, 26)
        if fmt == "jpeg":
            pos = 2
            max_pos = min(len(raw) - 9, 65536)  # scan first 64K only
            while pos < max_pos:
                if raw[pos] != 0xFF:
                    pos += 1
                    continue
                marker = raw[pos + 1]
                if marker in (0xC0, 0xC2, 0xC1):
                    return struct.unpack(">HH", raw[pos + 5: pos + 9])
                length = struct.unpack(">H", raw[pos + 2: pos + 4])[0]
                if length < 2:
                    break
                pos += 2 + length
    except Exception:
        pass
    return 0, 0


def remove_background(raw: bytes, fmt: str) -> bytes | None:
    """Run rembg on the image. Returns PNG bytes with RGBA, or None on failure.

    Cold: ~28s (model download). Warm: ~0.7s.
    """
    try:
        from rembg import remove
        from PIL import Image
        from io import BytesIO
        img = Image.open(BytesIO(raw))
        result = remove(img)
        buf = BytesIO()
        result.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        print("    WARNING: rembg not installed. pip install 'rembg[cpu]'")
        return None
    except Exception as e:
        print(f"    WARNING: rembg failed: {e}")
        return None


def maybe_remove_background(
    result: ImageResult,
    policy: Literal["auto", "always", "never"] = "auto",
) -> ImageResult:
    """Apply background removal based on policy and alpha detection.

    Policy:
      "auto"   — remove bg only if image has no alpha channel (default)
      "always" — force removal regardless
      "never"  — skip removal
    """
    if policy == "never":
        return result
    if policy == "auto" and result.has_alpha:
        print("    (alpha detected, skipping rembg)")
        return result

    print(f"    Removing background (policy={policy}, has_alpha={result.has_alpha})...")
    t0 = time.perf_counter()
    new_bytes = remove_background(result.bytes, result.format)
    if new_bytes is None:
        return result  # fall back to original
    elapsed = time.perf_counter() - t0
    print(f"    RemBG: {elapsed:.1f}s  ({len(new_bytes)} bytes)")

    return ImageResult(
        bytes=new_bytes,
        format="png",          # rembg always outputs PNG
        has_alpha=True,         # rembg output is always RGBA
        width=result.width,
        height=result.height,
        url=result.url,
        elapsed=result.elapsed,
    )


# ══════════════════════════════════════════════════════════════════════
#  API client — mirrors planned 7.3 ImgApiClient
# ══════════════════════════════════════════════════════════════════════

class ImgApiClient:
    """OpenAI-compatible image generation client.

    Mirrors the planned 7.3 production class. Reads config from env vars
    with sensible defaults — same pattern as the existing ApiClient for LLM.
    """

    def __init__(self) -> None:
        self.api_key = os.environ.get("IMAGE_API_KEY", "")
        self.base_url = (
            os.environ.get("IMAGE_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.model = os.environ.get("IMAGE_MODEL") or DEFAULT_MODEL
        self.remove_bg: Literal["auto", "always", "never"] = (
            os.environ.get("IMAGE_REMOVE_BG") or REMOVE_BG  # type: ignore[assignment]
        )

    # ── public API ──────────────────────────────────────────────────

    def generate(
        self,
        prompt: str,
        size: str,
        image_urls: list[str] | None = None,
        remove_bg: Literal["auto", "always", "never"] | None = None,
    ) -> ImageResult | None:
        """Generate one image. Returns ImageResult with format/alpha metadata.

        remove_bg: per-call override of self.remove_bg policy.
                   None → use instance default. "never" → skip for backgrounds.
        """
        if not self.api_key:
            raise RuntimeError("IMAGE_API_KEY not set")

        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "output_format": "png",
            "watermark": False,
        }
        if image_urls:
            payload["image_urls"] = image_urls

        t0 = time.perf_counter()
        with httpx.Client(timeout=httpx.Timeout(120, connect=30)) as client:
            resp = client.post(
                f"{self.base_url}/images/generations",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                json=payload,
            )
        elapsed = time.perf_counter() - t0

        print(f"    HTTP {resp.status_code}  ({elapsed:.1f}s)")

        if resp.status_code != 200:
            try:
                msg = resp.json().get("error", {}).get("message", resp.text[:200])
            except Exception:
                msg = resp.text[:300]
            print(f"    ERROR: {msg}")
            return None

        data = resp.json()
        img = data.get("data", [{}])[0]
        url = img.get("url", "")
        b64 = img.get("b64_json", "")

        raw: bytes | None = None
        if url:
            dl = httpx.get(url, timeout=60)
            if dl.status_code != 200:
                print(f"    WARNING: image download failed HTTP {dl.status_code}")
                return None
            raw = dl.content
        elif b64:
            raw = base64.b64decode(b64)

        if not raw:
            print("    WARNING: no url or b64_json in response")
            return None

        fmt = detect_format(raw)
        has_alpha = detect_alpha(raw, fmt)
        w, h = get_dimensions(raw, fmt)

        result = ImageResult(
            bytes=raw, format=fmt, has_alpha=has_alpha,
            width=w, height=h, url=url, elapsed=elapsed,
        )

        print(f"    {fmt}  {w}x{h}  alpha={has_alpha}  "
              f"({len(raw)} bytes)")

        # Apply background removal policy (per-call override or instance default)
        policy = remove_bg if remove_bg is not None else self.remove_bg
        result = maybe_remove_background(result, policy=policy)

        return result

    @property
    def config_summary(self) -> str:
        return (
            f"Model:  {self.model}\n"
            f"Base:   {self.base_url}\n"
            f"Remove bg: {self.remove_bg}"
        )


# ══════════════════════════════════════════════════════════════════════
#  Save helper
# ══════════════════════════════════════════════════════════════════════

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "temp" / "image_api_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def save(result: ImageResult | None, stem: str) -> None:
    """Write to OUTPUT_DIR with format-aware extension and alpha tag."""
    if not result:
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
    api = ImgApiClient()

    if not api.api_key:
        print("ERROR: IMAGE_API_KEY environment variable not set.")
        print("Usage: IMAGE_API_KEY=sk-xxx python scripts/validate_image_api.py")
        print()
        print("Environment variables:")
        print("  IMAGE_API_KEY     — required")
        print("  IMAGE_MODEL       — default: " + DEFAULT_MODEL)
        print("  IMAGE_BASE_URL    — default: " + DEFAULT_BASE_URL)
        print("  IMAGE_REMOVE_BG   — auto | always | never  (default: auto)")
        print()
        print("Presets (set IMAGE_MODEL to one of):")
        for k, v in PRESETS.items():
            print(f"  {k:40s} — {v['label']}: {v['notes']}")
        sys.exit(1)

    # Detect if using a known preset — apply size overrides if present
    preset = PRESETS.get(api.model, {})
    label = preset.get("label", api.model)
    sizes = preset.get("sizes", {})
    p_size = sizes.get("portrait", PORTRAIT_SIZE)
    b_size = sizes.get("background", BACKGROUND_SIZE)
    c_size = sizes.get("consistency", CONSISTENCY_SIZE)

    print(api.config_summary)
    print(f"Preset:  {label}" + (f"  ({preset['notes']})" if preset else ""))
    print(f"Portrait size:     {p_size}")
    print(f"Consistency size:  {c_size}")
    print(f"Background size:   {b_size}")
    print(f"Output:            {OUTPUT_DIR}")

    # ── Portrait ─────────────────────────────────────────────────
    divider(f"Portrait  ({p_size}) — waist-up, transparent bg prompt")
    portrait = api.generate(PORTRAIT_PROMPT, p_size)
    save(portrait, "01_portrait")

    # ── Consistency ─────────────────────────────────────────────
    consistent = None
    ref_url = portrait.url if portrait and portrait.url else None
    if ref_url:
        divider(f"Consistency  ({c_size}) — same char, different pose")
        consistent = api.generate(
            CONSISTENCY_PROMPT, c_size, image_urls=[ref_url],
        )
        save(consistent, "02_consistent")
    else:
        print("\n  SKIP: consistency — no URL from portrait (model may use b64)")

    # ── Background ──────────────────────────────────────────────
    divider(f"Background  ({b_size}) — 16:9 scene")
    bg = api.generate(BACKGROUND_PROMPT, b_size, remove_bg="never")
    save(bg, "03_background")

    # ── Summary ─────────────────────────────────────────────────
    divider("Summary")
    results = [r for r in [portrait, consistent, bg] if r]
    total_time = sum(r.elapsed for r in results)
    # Approximate cost per model (apiyi pricing, 2026-08)
    _MODEL_PRICES = {
        "flux-2-pro": 0.03,
        "seedream-5-0-260128": 0.035,
        "gemini-3.1-flash-lite-image": 0.025,
    }
    unit_price = _MODEL_PRICES.get(api.model, 0.03)
    total_cost = unit_price * len(results)
    print(f"  Model:   {label} ({api.model})")
    print(f"  Results: {len(results)}/3 generated")
    print(f"  Time:    {total_time:.0f}s total")
    print(f"  Cost:    ~${total_cost:.2f}  (${unit_price}/image)")

    # Alpha audit
    alpha_count = sum(1 for r in results if r.has_alpha)
    print(f"  Alpha:   {alpha_count}/{len(results)} have transparency")
    if alpha_count == 0 and api.remove_bg == "auto":
        print("           (none — rembg applied to portraits automatically)")
    print(f"\n  Files:")
    for f in sorted(OUTPUT_DIR.iterdir()):
        size_kb = f.stat().st_size // 1024
        print(f"    {f.name:40s} {size_kb:>5} KB")


if __name__ == "__main__":
    main()

"""Thinking-mode presets for LLM API calls.

Produces ``extra_params`` dicts consumed by ``ApiClient.chat()``.
Used by the Task subsystem (§7.8a match, §7.8b selection) and any
future pipeline stage that needs to control model reasoning.

Each preset entry maps a model family to three modes:

  disabled — no thinking (fast, cheap — for match)
  light    — minimal thinking (for retry / selection)
  enabled  — full thinking (API default, for generation)

Model families are matched by case-insensitive substring against
``ApiClient.model``.  First match wins.  Unknown models → ``{}``.

Preset reference (verified Aug 2026):
  DeepSeek:   https://api-docs.deepseek.com/guides/thinking_mode/
  Claude:     https://platform.claude.com/docs/en/build-with-claude/extended-thinking
  Gemini:     https://discuss.google.dev/t/how-can-i-set-0-thinkingbudget/189244
  Qwen:       https://www.alibabacloud.com/help/en/model-studio/deep-thinking
  GLM:        https://docs.bigmodel.cn/cn/guide/capabilities/thinking
  OpenAI:     https://community.openai.com/t/switching-apis-from-4-1-mini-to-5-1-mini/1376136
  Kimi:       https://platform.kimi.ai/docs/api/models-overview
  Grok:       https://writingmate.ai/models/x-ai/grok-4.20
  Doubao:     https://help.now.cn/aimodel/interface/20260320174138/
"""

from __future__ import annotations

# Ordered list of (model_substring, disabled_params, light_params, enabled_params).
# First match wins (case-insensitive).  Append new entries; never reorder.

_THINKING_PRESETS: list[tuple[str, dict, dict, dict]] = [
    # ── DeepSeek ──────────────────────────────────────────────────────
    # Verified Aug 2026.  thinking.type is the official API parameter.
    # Default is thinking ON — explicit disabled is needed to skip CoT.
    (
        "deepseek",
        {"thinking": {"type": "disabled"}},
        {"thinking": {"type": "enabled"}},
        {},                                              # enabled = API default
    ),
    # ── Anthropic Claude ──────────────────────────────────────────────
    # Per official docs (platform.claude.com, Aug 2026):
    #   ≤ 4.5: extended thinking ONLY — {"thinking": {"type": "enabled", "budget_tokens": N}}
    #   4.6:   extended deprecated, adaptive available
    #   ≥ 4.7: extended REMOVED — {"thinking": {"type": "enabled", "budget_tokens": N}} → 400
    #          Must use {"thinking": {"type": "adaptive"}} + {"output_config": {"effort": "..."}}
    #
    # disabled: {"thinking": {"type": "disabled"}} works for ≤ 4.6.
    #   On ≥ 4.7 this parameter is not recognised (extended thinking
    #   doesn't exist) — likely silently ignored, but adaptive thinking
    #   may still engage.  No perfect "off" switch exists for ≥ 4.7.
    # light/enabled: budget_tokens format works for ≤ 4.6 only.
    #   On ≥ 4.7 these will 400 — the ApiError is caught and the caller
    #   retries or degrades gracefully.
    # TODO: add version-aware Claude entries when §7.8b needs reliable
    #   light thinking on ≥ 4.7 models.
    (
        "claude",
        {"thinking": {"type": "disabled"}},
        {"thinking": {"type": "enabled", "budget_tokens": 1024}},
        {"thinking": {"type": "enabled", "budget_tokens": 4096}},
    ),
    # ── Google Gemini ─────────────────────────────────────────────────
    # Per discuss.google.dev (Aug 2026):
    #   2.5 Flash: thinking_budget range 0–24576 (0 = disabled).
    #   2.5 Pro:   min is 128, CANNOT disable.  thinking_budget=0 → 400.
    #   3.x:       uses thinking_level string instead (none/minimal/low/…).
    # Current disabled preset will 400 on 2.5 Pro — the ApiError is
    # caught and the caller retries or degrades gracefully.
    # TODO: split Gemini entries by version when §7.8b needs reliable disabling.
    (
        "gemini",
        {"thinking_config": {"thinking_budget": 0}},
        {"thinking_config": {"thinking_budget": 512}},
        {},                                              # enabled = API default
    ),
    # ── Alibaba Qwen ──────────────────────────────────────────────────
    # Per official docs (alibabacloud.com, Aug 2026):
    #   DashScope / official API: enable_thinking is a top-level field.
    #   Self-hosted vLLM/SGLang: use chat_template_kwargs nesting instead.
    # We target the official API format; users on self-hosted endpoints
    # should change api_base_url or adjust the preset.
    # Qwen3 hybrid models require this to avoid burning tokens on <think>.
    (
        "qwen",
        {"enable_thinking": False},
        {},                                              # light = default (no override)
        {},                                              # enabled = default
    ),
    # ── Zhipu GLM ─────────────────────────────────────────────────────
    # Verified Aug 2026.  Native Zhipu API uses thinking.type.
    # CAUTION: some third-party proxies (SiliconFlow, Z.ai) expect
    # enable_thinking: false instead — the thinking object is silently
    # ignored, and the model still thinks.
    (
        "glm",
        {"thinking": {"type": "disabled"}},
        {"thinking": {"type": "enabled"}},
        {},                                              # enabled = API default
    ),
    # ── OpenAI (GPT-5 / o-series) ─────────────────────────────────────
    # Matches "gpt" prefix (model names: gpt-5.2, gpt-5-mini, etc.).
    # Per community.openai.com (2026):
    #   reasoning_effort values: none / minimal / low / medium / high.
    #   gpt-5-mini rejects "none" with 400 → use "minimal" as fallback.
    #   gpt-5.1+ defaults to "none" (reasoning off by default).
    #   gpt-5 / pro / 5.5 default to "medium".
    # NOTE: gpt-5-mini + disabled → 400; caught as ApiError, caller retries.
    (
        "gpt",
        {"reasoning_effort": "none"},
        {"reasoning_effort": "minimal"},
        {},                                              # enabled = API default
    ),
    # ── Moonshot Kimi ─────────────────────────────────────────────────
    # K2.x hybrid models use thinking.type (same wire shape as DeepSeek/GLM).
    # K3 always reasons — thinking param is ignored, only reasoning_effort
    # controls depth.  Disabling is best-effort.
    (
        "kimi",
        {"thinking": {"type": "disabled"}},
        {"thinking": {"type": "enabled"}},
        {},                                              # enabled = API default
    ),
    # ── xAI Grok ──────────────────────────────────────────────────────
    # Grok uses reasoning.enabled (boolean), NOT thinking.type.
    # This is a unique format — different from all other providers.
    (
        "grok",
        {"reasoning": {"enabled": False}},
        {},                                              # light = default (API choice)
        {},                                              # enabled = default
    ),
    # ── ByteDance Doubao (豆包) ──────────────────────────────────────
    # Same wire shape as DeepSeek/GLM.  Has a unique "auto" mode
    # (model decides) which we don't use — we want explicit control.
    (
        "doubao",
        {"thinking": {"type": "disabled"}},
        {"thinking": {"type": "auto"}},                  # light = auto (model decides)
        {},                                              # enabled = API default
    ),
]


def get_thinking_params(model: str, mode: str = "disabled") -> dict:
    """Return ``extra_params`` dict for controlling thinking on *model*.

    Args:
        model: Model identifier string (e.g. ``"deepseek-v4-pro"``).
        mode: ``"disabled"`` | ``"light"`` | ``"enabled"``.

    Returns:
        Dict suitable as ``extra_params`` for ``ApiClient.chat()``.
        Empty dict for unknown models (no thinking control attempted).
    """
    model_lower = model.lower()
    for prefix, disabled, light, enabled in _THINKING_PRESETS:
        if prefix in model_lower:
            if mode == "disabled":
                return disabled
            elif mode == "light":
                return light
            else:
                return enabled
    return {}


# ═══════════════════════════════════════════════════════════════════════
# Image API thinking presets (separate from chat — different wire format)
# ═══════════════════════════════════════════════════════════════════════
#
# Image generation models use POST /images/generations, not /chat/completions.
# Thinking/reasoning parameters are NOT part of the OpenAI image API spec —
# they only apply to models whose native API supports reasoning control.
#
# Wire-format assumption: the project uses an OpenAI-compatible unified proxy.
# Parameters are passed as top-level JSON fields merged into the request body.
# The proxy is expected to forward unknown fields (standard API gateway behaviour)
# — models that don't support thinking will silently ignore them.
#
# Each entry MUST cite a URL showing the native API supports the parameter.

_IMAGE_THINKING_PRESETS: list[tuple[str, dict, dict, dict]] = [
    # ── Gemini 3.x Image (nano-banana-pro, nano-banana-2) ─────────────
    # Native API: generationConfig.thinkingConfig.thinkingLevel
    #   = "minimal" (default) | "high".
    # OpenAI-compatible proxy: thinking_config.thinking_level (consistent
    #   with the text API's thinking_config.thinking_budget wrapper).
    # "minimal" is the lightest setting; there is no true "off" for image
    #   models — some base reasoning always runs.
    # Ref: https://discuss.ai.google.dev/t/145830
    #   "For image generation models …, the relevant parameter is
    #    thinkingLevel, nested inside generationConfig.thinkingConfig"
    # Ref: https://help.apiyi.com/en/gemini-3-1-flash-lite-image-thinking-mode-guide-en.html
    #   "thinking_level — values: minimal (default) and high"
    (
        "nano-banana-pro",
        {"thinking_config": {"thinking_level": "minimal"}},
        {"thinking_config": {"thinking_level": "minimal"}},
        {},                                              # enabled = API default (high)
    ),
    (
        "nano-banana-2",
        {"thinking_config": {"thinking_level": "minimal"}},
        {"thinking_config": {"thinking_level": "minimal"}},
        {},
    ),
    (
        "gemini-3",
        {"thinking_config": {"thinking_level": "minimal"}},
        {"thinking_config": {"thinking_level": "minimal"}},
        {},
    ),
    # ── Gemini 2.5 Image (nano-banana) ────────────────────────────────
    # Native API: generationConfig.thinkingConfig.thinkingBudget
    #   = integer 0–24576 (0 = minimal, Flash only; Pro min is 128).
    # OpenAI-compatible proxy: thinking_config.thinking_budget
    #   (same wrapper as the text API entry above).
    # Ref: https://discuss.ai.google.dev/t/145830
    #   "2.5 Flash: thinking_budget range 0–24576 (0 = disabled)"
    (
        "nano-banana",
        {"thinking_config": {"thinking_budget": 0}},
        {"thinking_config": {"thinking_budget": 0}},
        {},
    ),
    (
        "gemini-2.5",
        {"thinking_config": {"thinking_budget": 0}},
        {"thinking_config": {"thinking_budget": 0}},
        {},
    ),
    # ── Gemini generic fallback ───────────────────────────────────────
    # Unknown Gemini variant — assume 3.x format (newer API generation).
    (
        "gemini",
        {"thinking_config": {"thinking_level": "minimal"}},
        {"thinking_config": {"thinking_level": "minimal"}},
        {},
    ),
    # ── GPT Image 2 ───────────────────────────────────────────────────
    # Third-party developer guides document a top-level "thinking"
    # parameter on /v1/images/generations: off | low | medium | high.
    # CAUTION: the official OpenAI API reference (developers.openai.com,
    # Aug 2026) does NOT document this parameter.  It may be:
    #   (a) an undocumented API feature,
    #   (b) a proxy-specific extension, or
    #   (c) planned but not yet in the public reference.
    # Included here on a best-effort basis — if unsupported, the field
    # is silently ignored by the API.
    # Ref: https://apidog.com/blog/gpt-image-2-api/
    #   "thinking — off | low | medium | high"
    # Ref: https://lushbinary.com/blog/chatgpt-images-2-developer-guide-gpt-image-2-api-pricing/
    #   "thinking mode adds reasoning tokens … budget 1.2–2× baseline"
    (
        "gpt-image-2",
        {"thinking": "off"},
        {"thinking": "low"},
        {},                                              # enabled = API default (medium)
    ),
    # NOTE: gpt-image-1 and earlier do NOT support the thinking
    # parameter (it was introduced with gpt-image-2, April 2026).
    # "gpt-image-2" does NOT match "gpt-image-1" (substring check).
    #
    # NOTE: Seedream, FLUX, and other diffusion-based image models
    # have no thinking/reasoning mechanism.  They don't match any
    # prefix above → get_image_thinking_params returns {}.
]


def get_image_thinking_params(model: str, mode: str = "light") -> dict:
    """Return ``extra_body`` dict for controlling thinking on image *model*.

    Only applies to models whose native API supports reasoning control
    (Gemini image, GPT Image 2).  For dedicated diffusion models
    (Seedream, FLUX) the function returns ``{}`` — a no-op.

    Args:
        model: Image model identifier (e.g. ``"gemini-3.1-flash-image"``).
        mode: ``"disabled"`` | ``"light"`` | ``"enabled"``.

    Returns:
        Dict suitable for merging into the ``/images/generations``
        request body.  Empty dict when the model doesn't support
        thinking control.
    """
    model_lower = model.lower()
    for prefix, disabled, light, enabled in _IMAGE_THINKING_PRESETS:
        if prefix in model_lower:
            if mode == "disabled":
                return disabled
            elif mode == "light":
                return light
            else:
                return enabled
    return {}

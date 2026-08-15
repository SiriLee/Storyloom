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
    # Official API (api-docs.deepseek.com, Aug 2026).  Two independent
    # controls: thinking.type (on/off toggle) and reasoning_effort
    # (top-level intensity — low/high/max).  Thinking defaults to ON
    # with effort=high.  Since 2026-08-13 (V4-Pro-0813 GA), the default
    # high effort emits a long chain-of-thought (reasoning_content)
    # before content — long enough to trip the streaming stall timeout.
    # So we pin light/enabled to low effort.  (disabled must NOT also
    # send reasoning_effort — the API rejects that combination.)
    (
        "deepseek",
        {"thinking": {"type": "disabled"}},
        {"thinking": {"type": "enabled"}, "reasoning_effort": "low"},
        {"thinking": {"type": "enabled"}, "reasoning_effort": "low"},
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
# Image generation uses POST /images/generations.  Only add entries when
# the provider's OWN official documentation confirms the parameter exists.
#
# Wire-format assumption: the project uses an OpenAI-compatible unified
# proxy.  Parameters are passed as top-level JSON fields merged into the
# request body — the proxy translates them to the native format.
#
# Models NOT listed below (Seedream, FLUX, GPT Image, DeepSeek, Gemini
# 2.5/pro image) have no officially documented thinking control on the
# /images/generations endpoint → get_image_thinking_params returns {}.

_IMAGE_THINKING_PRESETS: list[tuple[str, dict, dict, dict]] = [
    # ── Gemini 3.1 Flash / Flash Lite Image ────────────────────────────
    # Official Google AI docs (ai.google.dev, Aug 2026):
    #   generationConfig.thinkingConfig.thinkingLevel
    #     = "minimal" (default) | "high"
    #   Only supported on gemini-3.1-flash-image and
    #   gemini-3.1-flash-lite-image.
    #   gemini-3-pro-image does NOT support thinkingLevel control.
    #   Thinking is "enabled by default and cannot be disabled."
    #
    # OpenAI-compatible proxy format: thinking_config.thinking_level
    # (consistent with the text API's thinking_config wrapper).
    #
    # Source (official):
    #   https://ai.google.dev/gemini-api/docs/generate-content/image-generation
    #   → "thinkingConfig: {thinkingLevel: 'minimal' | 'high'}"
    #   → "Only supported on gemini-3.1-flash-image and
    #       gemini-3.1-flash-lite-image."
    #
    # nano-banana-2 is the same model family as gemini-3.1-flash-image.
    (
        "nano-banana-2",
        {"thinking_config": {"thinking_level": "minimal"}},
        {"thinking_config": {"thinking_level": "minimal"}},
        {},                                              # enabled = API default (high)
    ),
    (
        "gemini-3.1",
        {"thinking_config": {"thinking_level": "minimal"}},
        {"thinking_config": {"thinking_level": "minimal"}},
        {},
    ),
    # NOTE: The following models are intentionally absent — their
    # official docs do NOT confirm thinking control on the image endpoint:
    #   • gpt-image-* — OpenAI /v1/images/generations ref has no
    #     "thinking" parameter (verified Aug 2026).
    #   • gemini-3-pro-image / nano-banana-pro — official docs list
    #     only flash-image and flash-lite-image as supported.
    #   • gemini-2.5-flash-image / nano-banana (v1) — official image
    #     gen docs use thinkingLevel, not the text-model thinkingBudget.
    #   • seedream-*, flux-*, doubao-* — diffusion models, no reasoning.
]


def get_image_thinking_params(model: str, mode: str = "light") -> dict:
    """Return ``extra_body`` dict for controlling thinking on image *model*.

    Only applies to models whose official API docs confirm thinking
    control on the images endpoint.  Currently only Gemini 3.1 Flash /
    Flash Lite Image (including nano-banana-2) — all other models
    return ``{}``.

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

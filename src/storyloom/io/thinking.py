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
    # NOTE: budget_tokens format works for Claude ≤ 4.6 only.
    # Claude ≥ 4.7 (Opus 5, Sonnet 5) requires adaptive thinking:
    #   disabled → {} (extended thinking doesn't exist on ≥ 4.7)
    #   light    → {"thinking": {"type": "adaptive"}, "output_config": {"effort": "low"}}
    # TODO: add version-aware Claude entries when §7.8b needs light thinking.
    (
        "claude",
        {"thinking": {"type": "disabled"}},
        {"thinking": {"type": "enabled", "budget_tokens": 1024}},
        {"thinking": {"type": "enabled", "budget_tokens": 4096}},
    ),
    # ── Google Gemini ─────────────────────────────────────────────────
    # NOTE: Gemini 2.5 Pro rejects thinking_budget=0 (min is 128).
    # Flash accepts 0–24576.  Gemini 3 uses thinking_level string instead.
    # Current disabled preset may 400 on 2.5 Pro — the API will reject
    # and the caller's exception handler catches it as an ApiError.
    (
        "gemini",
        {"thinking_config": {"thinking_budget": 0}},
        {"thinking_config": {"thinking_budget": 512}},
        {},                                              # enabled = API default
    ),
    # ── Alibaba Qwen ──────────────────────────────────────────────────
    # Two wire formats exist:
    #   DashScope (native):     enable_thinking: false  (top-level)
    #   OpenAI-compatible:      chat_template_kwargs: {enable_thinking: false}
    # We target OpenAI-compatible endpoints (what ApiClient speaks).
    # Qwen3 hybrid models require this to avoid burning tokens on <think>.
    (
        "qwen",
        {"chat_template_kwargs": {"enable_thinking": False}},
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
    # Matches "gpt-" prefix (OpenAI model names: gpt-5.2, gpt-5-mini, etc.).
    # GPT-5 uses reasoning_effort to control thinking depth.
    # NOTE: gpt-5-mini rejects "none" with 400 — when that happens the
    # ApiError is caught and the caller retries or degrades gracefully.
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

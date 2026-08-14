# API Setup Guide

Storyloom needs an API to run. This guide covers the practical essentials — for detailed pricing and full model lists, check each provider's official website.

## 1. Overview

### Text API — required

Drives the story. OpenAI-compatible `/v1/chat/completions`. Settings: `API Base URL` · `API Key` · `Model`.

### Image API — optional

Generates character portraits and scene backgrounds. **Not required to play** — the game ships with a built-in system media library. Interface: `/v1/images/generations`. Settings: `Image API URL` · `Image API Key` · `Image Model`.

> 💡 If `Image API Key` is left empty, Storyloom falls back to your text `API Key`. Most of the time you only need one set of credentials.

## 2. Quick Start

An **API aggregation platform** is the simplest path — one key, one URL, access to dozens of providers.

Example with [OpenRouter](https://openrouter.ai):

1. Sign up at [openrouter.ai](https://openrouter.ai), create an API key
2. Top up via credit card to access paid models (free models available without deposit)
3. Fill in Storyloom's Settings:

| Setting | Value |
|---------|-------|
| API Base URL | `https://openrouter.ai/api/v1` |
| API Key | `sk-or-v1-your-key` |
| Model | `deepseek/deepseek-v4-pro` |
| Image API URL | `https://openrouter.ai/api/v1` |
| Image API Key | *leave empty* |
| Image Model | `black-forest-labs/flux-2-pro` |

> Same pattern works for any OpenAI-compatible platform — just swap the URL and key. Some platforms require model prefixes (e.g. `openai/gpt-5.2` on OpenRouter).

## 3. Text Model Recommendations

> ⚠️ **Quality floor:** Avoid models older than 2024 or below ~20B parameters. They tend to produce formatting errors that break the game.

Models we've tested and can recommend:

| Tier | Model | Notes |
|------|-------|-------|
| <span class="guide-badge best">Best</span> | `deepseek-v4-pro` | Top-tier reasoning, excellent structured output. Storyloom's default. |
| <span class="guide-badge best">Best</span> | `claude-sonnet-5` | Strong creative writing, reliable formatting. Higher cost. |
| <span class="guide-badge best">Best</span> | `gpt-5.2` | Excellent instruction following, very stable formatting. |
| <span class="guide-badge best">Best</span> | `gemini-3-pro` | 1M context window, great for long-form narrative. |
| <span class="guide-badge good">Good</span> | `deepseek-v4-flash` | Budget DeepSeek. Adequate for most use. |
| <span class="guide-badge good">Good</span> | `qwen3-max` | Alibaba flagship. Good Chinese/English bilingual quality. |
| <span class="guide-badge good">Good</span> | `glm-4.6` | Zhipu's latest. Competitive quality. |
| <span class="guide-badge usable">Usable</span> | `gpt-5-mini` | Cheapest GPT-5 tier. May occasionally produce formatting errors. |

> Check each provider's website for the full model list and real-time pricing (§7).

## 4. Image Model Recommendations

> 🎭 Image generation is optional. When turned off, the game uses its built-in library.

| Use case | Recommended | Budget pick |
|----------|------------|-------------|
| Character portraits | `flux-2-pro` / `seedream-4-5-251128` | `flux-2-klein-4b` |
| Scene backgrounds | `flux-2-pro` | `flux-2-klein-9b` |
| Fastest generation | `flux-2-klein-4b` | `nano-banana-2` |

> 💡 Storyloom always prompts for anime visual novel art style regardless of model choice. FLUX excels at skin, fabric, and lighting; Seedream 4.x is purpose-built for anime art — but the output style is driven by the prompt, not the model.

> ⚠️ **Avoid Seedream 5.0.** It has a built-in visual "deep thinking" step that cannot be disabled via API parameters (and Storyloom provides no override for it). Real-world generation takes 35–140 seconds (Lite median ~52s). Storyloom's image timeout is 300s total. **Seedream 4.x has no such issue** — it's a standard diffusion model. Use 4.5 or 4.0.

> See provider websites for detailed specs (resolution, reference image support, etc.).

## 5. Background Removal

Storyloom bundles a local AI model (**U²-Net**, ~4.4 MB) that removes backgrounds from character portraits. Runs entirely on your device — no network, no extra cost. Applies to portraits only.

| Mode | Behavior | When to choose |
|------|----------|---------------|
| <span class="guide-badge best">Auto</span> | Removes background only if the image lacks built-in transparency. | **Default. Recommended.** |
| <span class="guide-badge good">Always</span> | Runs on every portrait. Adds ~1–2s each. | Use when model transparency is inconsistent. |
| <span class="guide-badge usable">Never</span> | Skips removal. Portraits shown as-is. | For speed, or models with perfect built-in transparency. |

## 6. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `401` / `403` | Invalid key or insufficient balance | Verify your key starts with `sk-`; check account balance |
| `404 Not Found` | Wrong URL or model name | Double-check spelling. Some platforms need prefixes like `openai/gpt-5.2` |
| Output format errors | Model quality too low | Switch to a Best-tier model (§3). Avoid models below ~20B params |
| Image generation times out | Model too slow (esp. Seedream 5.0) | Switch to FLUX or Seedream 4.x |
| Cutout looks rough | Complex hair or translucent edges | Try `Auto` mode, or switch to `Never` for full-image portraits |

## 7. Platforms & Official Links

### Aggregation Platforms

| Platform | Highlights | Payment |
|----------|-----------|---------|
| [OpenRouter](https://openrouter.ai) | 200+ models, 30+ image models. Free tier available | Credit card |
| [APIYI](https://apiyi.com) | 400+ models, full image stack. Also supports Alipay/WeChat | Credit card / Alipay |
| [SiliconFlow](https://siliconflow.cn) | Best FLUX pricing. Free credit for new users | Credit card / Alipay |
| [Lumenfall](https://lumenfall.ai) | Image generation specialist. Zero markup | Credit card |
| [CometAPI](https://cometapi.com) | 500+ models, largest catalog | Credit card / crypto |
| [TokenMix](https://tokenmix.ai) | Zero platform fee. Wide intl + China coverage | Credit card / Stripe |
| [ofox](https://ofox.ai) | Claude/GPT/Gemini specialist | Credit card |

### Official APIs

| Provider | Text API | Image API | Pricing |
|----------|---------|-----------|---------|
| DeepSeek | [API docs](https://api-docs.deepseek.com) | — | [Pricing](https://api-docs.deepseek.com/quick_start/pricing) |
| OpenAI | [Platform docs](https://platform.openai.com/docs) | [Image guide](https://platform.openai.com/docs/guides/images) | [Pricing](https://openai.com/api/pricing) |
| Anthropic | [API docs](https://docs.anthropic.com) | — | [Pricing](https://www.anthropic.com/pricing) |
| Google | [Gemini API](https://ai.google.dev/gemini-api/docs) | [Image gen](https://ai.google.dev/gemini-api/docs/image-generation) | [Pricing](https://ai.google.dev/pricing) |
| Black Forest Labs | — | [FLUX API](https://docs.bfl.ml) | [Pricing](https://docs.bfl.ml/quick_start/pricing) |
| ByteDance | [Volcengine](https://www.volcengine.com/docs/82379) | [Image docs](https://www.volcengine.com/docs/6791) | Check console |
| Alibaba | [Model Studio](https://www.alibabacloud.com/help/en/model-studio) | — | Check console |
| Zhipu | [API docs](https://docs.bigmodel.cn/en) | — | Check console |
| Moonshot | [API docs](https://platform.kimi.ai/docs) | — | Check console |
| xAI | [API docs](https://x.ai/docs) | — | Check website |

---

*Last updated August 2026. Pricing and model availability change frequently — always check provider websites for current information.*

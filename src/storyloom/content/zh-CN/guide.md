# API 设置指南

Storyloom 需要配置 API 才能运行。这里只提供实用经验；详细价格、完整模型列表请到各平台官网查阅。

## 1. 概述

### 文本 API — 必须

驱动故事剧情。接口为 OpenAI 兼容的 `/v1/chat/completions`。设置项：`API 地址` · `API Key` · `模型`。

### 图片 API — 可选

生成角色立绘和场景背景。**不开也能玩**——游戏内置了系统素材库。接口为 `/v1/images/generations`。设置项：`图片 API 地址` · `图片 API Key` · `图片模型`。

> 💡 图片 API Key 留空会自动使用文本 API Key。多数情况只需填一套地址和 Key。

## 2. 快速上手

推荐用 **API 聚合平台**（一个 Key 通吃几十家模型）。以 [APIYI](https://apiyi.com) 为例：

1. 注册并充值（支持支付宝/微信，具体金额见官网）
2. 复制 API Key（`sk-` 开头）
3. 填入设置：

| 设置项 | 值 |
|--------|-----|
| API 地址 | `https://api.apiyi.com` |
| API Key | `sk-你的key` |
| 模型 | `deepseek-v4-pro` |
| 图片 API 地址 | `https://api.apiyi.com` |
| 图片 API Key | *留空* |
| 图片模型 | `flux-2-pro` |

其他聚合平台用法相同，换地址和 Key 即可。模型名在所有 OpenAI 兼容平台通用。

## 3. 文本模型选择

> ⚠️ **质量底线：** 避免 2024 年以前的老模型或参数太小的模型（<20B），容易出现格式错误导致游戏无法继续。

以下是实际使用中表现稳定的模型：

| 推荐 | 模型 | 说明 |
|------|------|------|
| <span class="guide-badge best">首选</span> | `deepseek-v4-flash` | 速度快、延迟低，推荐用于流式叙事。 |
| <span class="guide-badge best">首选</span> | `claude-sonnet-5` | 创意写作优秀，格式可靠。价格较高。 |
| <span class="guide-badge best">首选</span> | `gpt-5.2` | 指令遵循能力强，格式非常稳定。 |
| <span class="guide-badge best">首选</span> | `gemini-3-pro` | 百万上下文窗口，长故事首选。 |
| <span class="guide-badge good">不错</span> | `deepseek-v4-pro` | 输出强，但 08-13 更新后思考耗时过长。 |
| <span class="guide-badge good">不错</span> | `qwen3-max` | 阿里旗舰，中英双语质量好。 |
| <span class="guide-badge good">不错</span> | `glm-4.6` | 智谱最新，中文内容质量好。 |
| <span class="guide-badge usable">可用</span> | `gpt-5-mini` | GPT-5 最便宜档，偶尔格式错误。 |

> 更多模型和实时价格见各平台官网（§7）。

## 4. 图片模型选择

> 🎭 图片生成是可选的。关闭后游戏自动使用内置素材库。

| 用途 | 推荐 | 备选 |
|------|------|------|
| 角色立绘 | `flux-2-pro` / `seedream-4-5-251128` | `flux-2-klein-4b` |
| 场景背景 | `flux-2-pro` | `flux-2-klein-9b` |
| 追求速度 | `flux-2-klein-4b` | `nano-banana-2` |

> 💡 Storyloom 统一使用日式 AVG 立绘画风（anime visual novel style），不区分写实/二次元。画风由 prompt 控制，不完全由模型决定。

> ⚠️ **不要用 Seedream 5.0。** 5.0 内置了不可关闭的视觉"深度思考"步骤（API 无参数可控，程序也不提供调控），实际出图 35–140 秒（Lite 版实测中位数 ~52 秒）。Storyloom 图片生成总超时仅 300 秒。**Seedream 4.x 没有这个问题**——它是标准扩散模型，无思考步骤，出图快。用 4.5 或 4.0。

> 各模型详细规格（分辨率、参考图支持等）见平台官网。

## 5. 背景移除（立绘抠图）

Storyloom 内置本地 AI 抠图模型（U²-Net，约 4.4 MB），在本地运行，不联网不花钱。仅对角色立绘生效。

| 模式 | 行为 | 建议 |
|------|------|------|
| <span class="guide-badge best">自动</span> | 只在图片没有自带透明背景时抠图 | **推荐，默认** |
| <span class="guide-badge good">总是</span> | 每张立绘都抠，多花 1–2 秒 | 模型出图透明不稳定时用 |
| <span class="guide-badge usable">从不</span> | 不抠，原图直接用 | 追求速度，或模型自带完美透明背景 |

## 6. 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| `401` / `403` | Key 无效或余额不足 | 检查 Key 是否以 `sk-` 开头；检查账户余额 |
| `404 Not Found` | 地址或模型名写错 | 检查拼写。某些平台需加前缀如 `openai/gpt-5.2` |
| 输出格式错误 | 模型质量不够 | 换 §3 首选模型，别用太老或太小的模型 |
| 图片生成超时 | 模型太慢（尤其 Seedream 5.0） | 换 FLUX 或 Seedream 4.x |
| 抠图效果粗糙 | 复杂发型或半透明边缘 | 试试「自动」模式，或换「从不」 |

## 7. 推荐平台 & 官方链接

### 聚合平台

| 平台 | 特点 | 支付 |
|------|------|------|
| [APIYI](https://apiyi.com) | 400+ 模型，图片模型全。**国内用户首选** | 支付宝/微信 |
| [OpenRouter](https://openrouter.ai) | 200+ 模型，国际最知名 | 信用卡 |
| [SiliconFlow](https://siliconflow.cn) | FLUX 最优价，新用户送免费额度 | 支付宝/微信 |
| [TokenMix](https://tokenmix.ai) | 零平台费，中英文全覆盖 | 支付宝/微信/Stripe |
| [Lumenfall](https://lumenfall.ai) | 图片生成专精，零加价 | 信用卡 |
| [CometAPI](https://cometapi.com) | 500+ 模型，品类最全 | 信用卡/加密货币 |
| [ofox](https://ofox.ai) | Claude/GPT/Gemini 专精 | 支付宝/微信 |

### 官方 API

| 厂商 | 文本 API | 图片 API | 定价 |
|------|---------|---------|------|
| DeepSeek | [API 文档](https://api-docs.deepseek.com) | — | [定价](https://api-docs.deepseek.com/quick_start/pricing) |
| OpenAI | [平台文档](https://platform.openai.com/docs) | [图片指南](https://platform.openai.com/docs/guides/images) | [定价](https://openai.com/api/pricing) |
| Anthropic | [API 文档](https://docs.anthropic.com) | — | [定价](https://www.anthropic.com/pricing) |
| Google | [Gemini API](https://ai.google.dev/gemini-api/docs) | [图片生成](https://ai.google.dev/gemini-api/docs/image-generation) | [定价](https://ai.google.dev/pricing) |
| Black Forest Labs | — | [FLUX API](https://docs.bfl.ml) | [定价](https://docs.bfl.ml/quick_start/pricing) |
| 字节跳动 | [火山引擎](https://www.volcengine.com/docs/82379) | [图片文档](https://www.volcengine.com/docs/6791) | 控制台内查看 |
| 阿里云 | [模型服务](https://www.alibabacloud.com/help/en/model-studio) | — | 控制台内查看 |
| 智谱 | [API 文档](https://docs.bigmodel.cn) | — | 控制台内查看 |
| 月之暗面 | [API 文档](https://platform.kimi.ai/docs) | — | 控制台内查看 |
| xAI | [API 文档](https://x.ai/docs) | — | 官网查看 |

---

*最后更新 2026 年 8 月。价格和模型随时变化，请以各平台官网为准。*

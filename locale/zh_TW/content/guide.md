# API 設定指南

Storyloom 需要設定 API 才能執行。這裡只提供實用經驗；詳細價格、完整模型列表請到各平台官網查閱。

## 1. 概述

### 文本 API — 必須

驅動故事劇情。介面為 OpenAI 相容的 `/v1/chat/completions`。設定項：`API 位址` · `API Key` · `模型`。

### 圖片 API — 可選

生成角色立繪和場景背景。**不開也能玩**——遊戲內建了系統素材庫。介面為 `/v1/images/generations`。設定項：`圖片 API 位址` · `圖片 API Key` · `圖片模型`。

> 💡 圖片 API Key 留空會自動使用文字 API Key。多數情況只需填一套位址和 Key。

## 2. 快速上手

推薦用 **API 聚合平台**（一個 Key 通吃幾十家模型）。以 [APIYI](https://apiyi.com) 為例：

1. 註冊並充值（支援支付寶/微信，具體金額見官網）
2. 複製 API Key（`sk-` 開頭）
3. 填入設定：

| 設定項 | 值 |
|--------|-----|
| API 位址 | `https://api.apiyi.com` |
| API Key | `sk-你的key` |
| 模型 | `deepseek-v4-pro` |
| 圖片 API 位址 | `https://api.apiyi.com` |
| 圖片 API Key | *留空* |
| 圖片模型 | `flux-2-pro` |

其他聚合平台用法相同，換位址和 Key 即可。模型名在所有 OpenAI 相容平台通用。

## 3. 文字模型選擇

> ⚠️ **品質底線：** 避免 2024 年以前的老模型或參數太小的模型（<20B），容易出現格式錯誤導致遊戲無法繼續。

以下是實際使用中表現穩定的模型：

| 推薦 | 模型 | 說明 |
|------|------|------|
| <span class="guide-badge best">首選</span> | `deepseek-v4-pro` | 綜合最佳，Storyloom 預設。結構化輸出強，CP 值高。 |
| <span class="guide-badge best">首選</span> | `claude-sonnet-5` | 創意寫作優秀，格式可靠。價格較高。 |
| <span class="guide-badge best">首選</span> | `gpt-5.2` | 指令遵循能力強，格式非常穩定。 |
| <span class="guide-badge best">首選</span> | `gemini-3-pro` | 百萬上下文視窗，長故事首選。 |
| <span class="guide-badge good">不錯</span> | `deepseek-v4-flash` | DeepSeek 經濟版，大多數場景夠用。 |
| <span class="guide-badge good">不錯</span> | `qwen3-max` | 阿里旗艦，中英雙語品質好。 |
| <span class="guide-badge good">不錯</span> | `glm-4.6` | 智譜最新，中文內容品質好。 |
| <span class="guide-badge usable">可用</span> | `gpt-5-mini` | GPT-5 最便宜檔，偶爾格式錯誤。 |

> 更多模型和即時價格見各平台官網（§7）。

## 4. 圖片模型選擇

> 🎭 圖片生成是可選的。關閉後遊戲自動使用內建素材庫。

| 用途 | 推薦 | 備選 |
|------|------|------|
| 角色立繪 | `flux-2-pro` / `seedream-4-5-251128` | `flux-2-klein-4b` |
| 場景背景 | `flux-2-pro` | `flux-2-klein-9b` |
| 追求速度 | `flux-2-klein-4b` | `nano-banana-2` |

> 💡 Storyloom 統一使用日式 AVG 立繪畫風（anime visual novel style），不區分寫實/二次元。畫風由 prompt 控制，不完全由模型決定。

> ⚠️ **不要用 Seedream 5.0。** 5.0 內建了不可關閉的視覺「深度思考」步驟（API 無參數可控，程式也不提供調控），實際出圖 35–140 秒（Lite 版實測中位數 ~52 秒）。Storyloom 圖片生成總逾時僅 300 秒。**Seedream 4.x 沒有這個問題**——它是標準擴散模型，無思考步驟，出圖快。用 4.5 或 4.0。

> 各模型詳細規格（解析度、參考圖支援等）見平台官網。

## 5. 背景移除（立繪摳圖）

Storyloom 內建本地 AI 摳圖模型（U²-Net，約 4.4 MB），在本機執行，不連網不收費。僅對角色立繪生效。

| 模式 | 行為 | 建議 |
|------|------|------|
| <span class="guide-badge best">自動</span> | 只在圖片沒有自帶透明背景時摳圖 | **推薦，預設** |
| <span class="guide-badge good">總是</span> | 每張立繪都摳，多花 1–2 秒 | 模型出圖透明不穩定時用 |
| <span class="guide-badge usable">從不</span> | 不摳，原圖直接用 | 追求速度，或模型自帶完美透明背景 |

## 6. 常見問題

| 現象 | 原因 | 解決 |
|------|------|------|
| `401` / `403` | Key 無效或餘額不足 | 檢查 Key 是否以 `sk-` 開頭；檢查帳戶餘額 |
| `404 Not Found` | 位址或模型名寫錯 | 檢查拼寫。某些平台需加前綴如 `openai/gpt-5.2` |
| 輸出格式錯誤 | 模型品質不夠 | 換 §3 首選模型，別用太老或太小的模型 |
| 圖片生成逾時 | 模型太慢（尤其 Seedream 5.0） | 換 FLUX 或 Seedream 4.x |
| 摳圖效果粗糙 | 複雜髮型或半透明邊緣 | 試試「自動」模式，或換「從不」 |

## 7. 推薦平台 & 官方連結

### 聚合平台

| 平台 | 特點 | 支付 |
|------|------|------|
| [APIYI](https://apiyi.com) | 400+ 模型，圖片模型全。**華語用戶首選** | 支付寶/微信 |
| [OpenRouter](https://openrouter.ai) | 200+ 模型，國際最知名 | 信用卡 |
| [SiliconFlow](https://siliconflow.cn) | FLUX 最優價，新用戶送免費額度 | 支付寶/微信 |
| [TokenMix](https://tokenmix.ai) | 零平台費，中英文全覆蓋 | 支付寶/微信/Stripe |
| [Lumenfall](https://lumenfall.ai) | 圖片生成專精，零加價 | 信用卡 |
| [CometAPI](https://cometapi.com) | 500+ 模型，品類最全 | 信用卡/加密貨幣 |
| [ofox](https://ofox.ai) | Claude/GPT/Gemini 專精 | 支付寶/微信 |

### 官方 API

| 廠商 | 文字 API | 圖片 API | 定價 |
|------|---------|---------|------|
| DeepSeek | [API 文件](https://api-docs.deepseek.com) | — | [定價](https://api-docs.deepseek.com/quick_start/pricing) |
| OpenAI | [平台文件](https://platform.openai.com/docs) | [圖片指南](https://platform.openai.com/docs/guides/images) | [定價](https://openai.com/api/pricing) |
| Anthropic | [API 文件](https://docs.anthropic.com) | — | [定價](https://www.anthropic.com/pricing) |
| Google | [Gemini API](https://ai.google.dev/gemini-api/docs) | [圖片生成](https://ai.google.dev/gemini-api/docs/image-generation) | [定價](https://ai.google.dev/pricing) |
| Black Forest Labs | — | [FLUX API](https://docs.bfl.ml) | [定價](https://docs.bfl.ml/quick_start/pricing) |
| 字節跳動 | [火山引擎](https://www.volcengine.com/docs/82379) | [圖片文件](https://www.volcengine.com/docs/6791) | 控制台內查看 |
| 阿里雲 | [模型服務](https://www.alibabacloud.com/help/en/model-studio) | — | 控制台內查看 |
| 智譜 | [API 文件](https://docs.bigmodel.cn) | — | 控制台內查看 |
| 月之暗面 | [API 文件](https://platform.kimi.ai/docs) | — | 控制台內查看 |
| xAI | [API 文件](https://x.ai/docs) | — | 官網查看 |

---

*最後更新 2026 年 8 月。價格和模型隨時變化，請以各平台官網為準。*

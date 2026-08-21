# 竞品分析：AI 实时互动叙事项目全景

> **配套详解**：[`mechanism-mapping.md`](./mechanism-mapping.md) —— 三个高价值项目（Ars Fabula VN、
> Ephemeral Hearts、InfiPlot）的**代码级实现拆解**，逐条映射到 Storyloom 的实现，含术语"人话"解释。
> 本报告偏结论与机制分类，实现细节见配套文档。

> 分析日期：2026-08（基于各仓库最新提交：Ephemeral Hearts 2026-06-15、Ars Fabula VN 2026-06-13、
> InfiPlot 2026-07-02、ArtiMeow v1.2.0、LangStory 2026-06-06；Storyloom v2.3.3）。
> 分析基准：Storyloom 设计体系（`docs/theory/`）——桥接机制、流式解析、素材异步生成。

## 目录

1. [Storyloom 设计体系回顾（分析基准）](#1-storyloom-设计体系回顾)
2. [竞品全景总览](#2-竞品全景总览)
3. [深入分析](#3-深入分析)
4. [浅析与舍弃](#4-浅析与舍弃)
5. [实时驱动与无缝体验的机制分类](#5-实时驱动与无缝体验的机制分类)
6. [结论与启示](#6-结论与启示)

---

## 1. Storyloom 设计体系回顾

> 权威来源：`docs/theory/first-principles.md`、`bridge-mechanism.md`、`streaming-parse.md`、
> `asset-generation.md`、`docs/spec/exec-flow.md`、`docs/graph-mode-spec/design.md`、`docs/engineering-journal.md`

### 1.1 定位：第三种范式——流水线生成

交互式 AI 内容的根本矛盾：**生成需要时间，交互不应该等。** 两种既有范式各自回避矛盾的一侧：

- **批量预生成**：延迟为零，但选择无法改变已生成内容 → 自由度受限于预生成边界
- **纯实时交互**：自由度极高，但每次响应前用户被动等待 → 体验从"交互"退化为"等待生成"

Storyloom 探索第三种方向：**流水线生成**——生成不发生在等待期间，而发生在用户消费当前内容的期间。通过桥接机制在生成与消费之间创造时间重叠，同时具备高自由度和低感知延迟。

### 1.2 两个公理与一个目标

- **公理 1 — 生成有时延**：AI 生成耗时 > 0 且不可消除（物理约束，非工程问题）
- **公理 2 — 交互含不确定**：后续内容由前置交互结果决定，交互前不可确定（定义性事实）
- **目标 — 隐藏等待**：用户感知延迟应压缩到交互容忍范围内

### 1.3 推导出的三大机制

**桥接机制（结构性必需）**：由公理 1+2，交互后必须等待生成；唯一出路是生成与消费重叠。
每轮内容被 `<bridge/>` 标记分为交互区（叙事+交互元素）与缓冲区（纯叙事无交互）。
程序解析到 `</story>` 的瞬间在后台发起下一轮 API 调用；用户消费完缓冲区时下一轮已就绪或接近就绪。
约束：每轮恰好一个标记；标记后无交互元素；标记前完成所有交互声明。
桥接是结构性必需——只要延迟存在、交互存在不确定性，就必须有某种形式的桥接。

**流式解析（高效优化）**：不流式则首展示时间 = 总生成时间；流式将首展示时间压缩到 TTFT。
对格式的两条要求：增量可解析（不完整输入下产出有效单元）+ 位置可追踪（NNN| 行号前缀）。
工程教训（journal 07-11）：度量指标必须是"首段可展示时间"而非"解析吞吐量"——曾因 ElementTree
全量解析仅 234μs 而删除流式解析器，随后推翻：正确指标是 pre-fetch 启动到首个可展示内容就绪的墙上时间。

**素材异步生成（同一重叠原则）**：素材生成属于程序处理层，公理 1 同样适用。
需求被识别的时刻 ≠ 素材被展示的时刻，两者之间的消费窗口即生成可用窗口。
"选择优先于生成"：程序 O(1) 匹配 → LLM 匹配兜底 → AI 生成；DECLARE 占位优先，异步填充。

### 1.4 核心方程

```
实际等待 = TTFT + 素材剩余生成时间 − 消费覆盖时间
```

目标：使该值 ≤ 交互容忍阈值。桥接提供消费覆盖时间，流式压缩 TTFT，素材并行化缩短剩余生成时间。

### 1.5 三层流与双队列

```
生成（AI）→ 处理（程序）→ 消费（用户）
慢/不可控    快/可控        人因节奏
```

层间速度差达数量级 → 两个速度断层 → 两个解耦队列（生成↔处理、处理↔消费）。物理推论，非设计选择。

图模式（Phase 2）扩展为四线程：Server Main / Event Pipe / API Reader / Task Pool；
三队列：Token Queue / Task Queue / UI Event Queue。EventDispatcher 按行号对齐 Task 与 Event（§4.3 算法）。

### 1.6 哲学：LLM 建议者，程序裁决者

LLM 输出结构化 XML（`<seg>/<choice>/<set>/<checkpoint>/<branch>/<bridge/>`），程序逐行解析、
状态校验后才应用。LLM 从不直接改状态——这是"剧情可控"与"格式可靠"的根本保证。

---

## 2. 竞品全景总览

| 项目 | 类型 | 实时性机制 | 价值评级 | 深入与否 |
|------|------|-----------|---------|---------|
| Ephemeral Hearts | 本地多 AI 即兴 VN | 两阶段回合（文本先行→图像后补）+ 渲染缓存 | 高 | ✅ 深入 |
| Ars Fabula VN | 本地 AI 实时编剧 VN | 回合内流式+缓冲；回合间硬等待 | 高 | ✅ 深入 |
| InfiPlot | 云端多智能体互动剧情 | 预测式预生成下一幕 | 高 | ✅ 深入 |
| ArtiMeow RT | Electron VN 框架 | 无（同步等待） | 中 | ⚠️ 浅析 |
| LangStory | Next.js 交互叙事 | 无（同步等待） | 低-中 | ❌ 舍弃 |
| Ciallo Engine | Web VN 编辑器/播放器 | 传统引擎 + AI 辅助决策 | 低-中 | ❌ 舍弃（源码不可得） |

---

## 3. 深入分析

### 3.1 Ars Fabula VN（2026-06-13，GitHub ArsVie/ars-fabula-vn）

**做什么**：完全本地运行的 AI 驱动校园恋爱 VN。玩家选择/自定义 3-4 名角色的 cast，每回合由本地小 LLM 实时编写叙述+对话+舞台指令，驱动立绘表情、背景、配音和分支选项。
**技术栈**：Gradio 单体应用；llama.cpp llama-server（默认 Gemma 4 26B-A4B MoE，`--reasoning off` 降时延）；ComfyUI + Anima 生成立绘（SAM + FaceDetailer）；rembg 抠图；Kokoro/Chatterbox 配音（选择性）；Modal 云端 QLoRA 微调。

**实时驱动机制**：
- **回合内流式**：`LlamaServerClient.stream()` 走 OpenAI SSE 逐行读 `data:` 帧（`model_client.py:114-156`）；`run_turn_stream()` 行缓冲流式生成器（`vn_engine.py:135-168`），括号深度+引号感知切行，首 beat 就绪立即渲染（TTFT 压缩）
- **输出协议**：自定义 DSL 混合流——叙述文本与 `[TOOL: name ...]` 行内标记交错，对话用 `[角色名]: "台词"`；解析器设计主题是"宽容弱模型"（`_loads_lenient` 多级容错）
- **程序裁决**：`validate_turn()` 是协议合规唯一真源，且**直接复用引擎自己的解析器**（`vn_validate.py:8-13`）——"通过校验" ≡ "引擎能接受"
- **素材全预生成**：选角 beat 交互式确认 base 立绘后一次性 bake 7 表情（落盘缓存）；背景非预设 key 现场生成但同步阻塞 120s（`providers.py:220-262`，限定 beat 边界调用）

**无缝体验机制**：行级流式 + 缓冲增长（后续 beat 不重渲染屏幕）+ 读速追平生成速时显示 ✦ pulse；**无跨回合预生成/桥接**——下一轮严格在玩家点选后启动，回合间是硬等待。图像全部转 data URI 内嵌（lru_cache）。推理加速：MTP drafter、`--reasoning off`。

**状态与一致性**：SceneState + 文本滑动窗口（尾部 4 回合/1200 字符注入 prompt）；**cast-lock 三重复合**（prompt 强令 + 引擎清洗非 cast 台词 + 回合结束全量复查注记）——与 Storyloom"程序裁决"哲学同构且更激进。

**对比洞见**：
- 独特/可借鉴：① **验证器驱动的自举微调闭环**（运行时 trace → validate 门控 → SFT 数据集 → QLoRA → 同校验器评估，"引擎自己的解析器成为数据集质量闸门"——Storyloom 可把 StreamParser 复用到训练数据门控）；② 表情资产管线（FaceDetailer 面部重绘保身份、三轴差异化、seed 锚定防漂移）；③ 选择性配音（只为情绪节拍配音）；④ VRAM 编排（杀 LLM 进程→bake→重启+轮询）
- 缺失：回合间硬等待（无桥接，用"本地小模型快+全预生成素材"绕开而非解决）；无字节级流式；无三层流/双队列；记忆单薄（无压缩）

**价值评级：高**。实时性上落后于 Storyloom，但"程序裁决 + 自举数据 + 资产管线"三个方向是高质量参照。

### 3.2 Ephemeral Hearts（2026-06-15，HF build-small-hackathon/Hackathon-IA-VisualNovel）

**做什么**：AI 即兴动漫视觉小说（Build Small 黑客松）。故事、角色、对话、艺术资产、语音全部由小型本地模型实时生成，无预写剧本。五个 AI 角色在 <18B 参数预算内协作：Weaver（导演/GM，结构化 directives）+ Voices（对话，共享权重）+ Painter（SDXL-Turbo 图像）+ Ear（Whisper STT）+ Voice（Kokoro TTS）。
**技术栈**：Gradio 自定义前端；Qwen3-14B（llama.cpp grammar / transformers / Modal 三后端）；SDXL + anime LoRA；uv。一仓库三运行时（本地离线 / Modal GPU / ZeroGPU Space）。

**实时驱动机制**（关键澄清：**它不是流式的**）：
- LLM 调用全部阻塞式（`llm.py:81-99` llama.cpp、`llm.py:144-208` transformers，无 stream=True）；README 声称的 "text streams first" 实为前端打字机装饰（`index.html:1011-1019`，16ms/字符），TTFT = 完整生成时间
- **"实时"靠三件事**：
  1. **回合内两阶段拆分**：`/turn_text` 先返回无图 ViewState 显示对话（`engine.py:260-345`），`/turn_images` 再补图 + TTS（`app.py:237-247`、`index.html:1653-1658`）——文本立即可见，图像/音频后补
  2. **重度缓存**：Painter 按 `sha1(kind|prompt|seed)` 磁盘缓存（`painter.py:169-198`），场景/情绪不变则图片阶段 ≈ 0ms；seed 按实体固定 → 同一角色永远同一张脸
  3. **语法约束**：llama-cpp-python 把 Pydantic schema 编译成 GBNF grammar（`llm.py:81-99`），并把 emotion/relationship_delta 提升为 required（`prompts.py:238-243`）；"grammar is a constraint, prompting is a suggestion"（BLOG.md:384）
- **"model proposes, code disposes"**：`state.apply_directives` 是唯一 mutator（`state.py:25-140`），clamp/校验/静默忽略不可能请求；LLM 只读 `memory.assemble_context` 快照

**无缝体验机制**：**无桥接、无跨回合重叠**——`busy(true)` 锁输入到图片阶段结束（`index.html:1651,1661`），下一回合不能提前生成；speculative paint 仅存在于文档（ARCHITECTURE.md:224）未实现。等效等待 = LLM 完整生成 + 图片未命中(1-5s) − 打字机覆盖(≈1-2s)，靠**缓存回避**而非"生成消费重叠"。

**状态与一致性**：上下文 = 滚动 summary + 仅在场角色 sheets + 最近 6 回合，3500 token 预算（`config.py:102`），超预算触发 LLM 压缩（`/no_think` 防 think 块）；close_truncated_json 修复截断（`utils.py:34-70`）；anti-repeat 热重试（`orchestrator.py:154-176`）。

**对比洞见**：
- 独有/可借鉴：① **grammar-constrained decoding**（Pydantic → GBNF，格式可靠性从 prompt 层提升到解码层）；② TTS/STT 语音全链路（MediaRecorder→/transcribe→Whisper；Kokoro 按角色冻结音色 `tts.py:117-136`）；③ ZeroGPU 无状态 worker（/tmp 共享状态文件 + 原子写 + 懒加载，`engine.py:35-57,321-341`）；④ Modal keep-warm；⑤ mock-first 出厂模式（`config.py:42`，零模型可跑通全循环）
- 缺失：非流式（首展示 = 完整生成时间）；无桥接（回合间硬等待，靠缓存回避）；输入在图片阶段全程锁定

**价值评级：高**。哲学同源（LLM 提议/程序裁决）但路线分岔：EH **藏延迟**（缓存+少改动），Storyloom **填延迟**（流式+bridge 提前生成）——反向确认 Storyloom 的"生成与消费重叠"公理仍是差异化空白。可移植项优先级：grammar 约束 → 语音链路 → 无状态会话。

### 3.3 InfiPlot（2026-07-02，GitHub zonghaoyuan/infiplot）

**做什么**：AI 实时生成全部图文内容的互动剧情游戏（"用 AI 实时生成内容的《完蛋！我被美女包围了！》"）。玩家输入世界观+画风 → 引擎现场生成整部剧情；每个 scene = 1 张 AI 绘背景图 + 一棵 beat（节拍）树（旁白/对白/选项）。
**技术栈**：Next.js 16 App Router；**服务器刻意无状态**——客户端携带完整 Session 随每次请求往返（AGENTS.md:13）；持久化 IndexedDB + 可选 Supabase 云同步；LLM 走 OpenAI 兼容协议（推荐 deepseek-v4-flash）；图像 Runware（FLUX.2 9B KV，4 步出图）或 OpenAI gpt-image；TTS 小米 MiMo/StepFun；双运行模式（服务器 API / BYO 浏览器直连，引擎整体在浏览器内运行）。

**多智能体架构**：Writer（唯一内容大脑，单次流式调用产出 `<plan>→<story>→<choices>` 三段标签输出）；CharacterDesigner（每新角色一次 LLM 调用产出视觉+音色文本卡 → 头像图 + 配音）；Cinematographer（sceneSummary → FLUX 构图 prompt）；Painter（用 referenceImages ≤4 张生成场景背景）；StyleSelector / Vision 点击解读 / InsertBeat 探索。

**实时驱动机制（核心：预测式生成 = 全枚举分支预生成）**：
- **触发**：场景提交（`currentScene?.id` 变化）即触发——玩家开始读新一幕的同时，把所有 `change-scene` 选项逐一预生成完整场景（含绘图）（`page.tsx:2007-2036`）——**阅读窗口与生成窗口天然重叠**
- **算法**：L1 全枚举本幕所有 change-scene 选项（`page.tsx:387-401`）；L2/L3 对"恰好只有 1 个出口"的必经节点递归前视（`page.tsx:403-406,452-483`），深度上限 `PREFETCH_MAX_DEPTH = 3`（`page.tsx:296`）。**无概率、无预测模型**——"预测"靠枚举覆盖
- **缓存键**：选择 id 路径（`"C1"`、`"C1/C2"`，`page.tsx:361-363`），服务端强制全局唯一（`writer.ts:308-326`）；消费时命中即零等待切换，非后裔分支 abort（`page.tsx:505-522`）
- **成本洞**：abort 只停客户端等待，服务端 `/api/scene` 继续跑完（AbortController 未传入 fetch，`page.tsx:428-432`）——被弃分支的绘图成本照付
- **LLM 流式的真实用途 = 管线加速**：`StreamRouter` 标签状态机，`</plan>` 关闭即解锁图像管线与 `<story>` 并行（`director.ts:228-241,200-206`）；SSE 渐进事件已建好但 play 页未接线 → 玩家看到整段文本 + 客户端打字机（假流式）

**无缝体验机制**：
| 机制 | 证据 |
|------|------|
| Writer 拆分：plan 先出 → 图像与文本重叠，地板 max(beats, image) | `director.ts:60-63` |
| 图片预加载+解码（Image()+decode() 提前暖 HTTP 缓存） | `page.tsx:175-196` |
| 图片就绪闸门（transitioning 遮罩保持到真解码完成） | `page.tsx:138-142` |
| **IMAGE_HEDGE_MS 双请求竞速**（同 prompt 两腿，先到胜者） | `painter.ts:153-224` |
| **sceneKey 参考图闭环**（img2img 锚定，同空间光照/布局连续） | `director.ts:128-143` |
| **prompt 前缀缓存**（稳定前缀+动态后缀，SENTINEL append-only 保字节稳定） | `context/index.ts:84-134` |
| 预烘焙首幕（构建期预生成精选卡 JSON，`?card=` 启动零引擎调用） | `page.tsx:1691-1698` |
| 角色卡∥分镜 → 入场头像 → Painter → 其余头像+配音重叠（Promise DAG） | `director.ts:42-72,319-457` |

**状态与一致性**：共享记忆 = 客户端 Session（worldSetting/styleGuide/history/characters/storyState）；StoryState 双层（稳定主轴 storyBible 不可改写 + 易变区每幕 patch）；角色以 name 为键注册表 + mergeCharacters 保留旧字段；POV 硬编码"你"；输出治理四层 raw→coerce→repair→fallback；预测分支用构造的"投机 Session"生成。

**对比洞见**：
- 同源哲学：LLM 建议者/程序裁决（coerce/repair/degrade）；"生成与消费重叠"是零等待唯一出路
- 可借鉴（★）：① 场景粒度全枚举预生成 + 必经节点前视——在**分支维度**重叠，与 Storyloom 的**轮内流式**重叠互补；② Writer 单流分标签 + `</plan>` 早解锁下游——一个调用同时完成快速骨架与慢速正文；③ 参考图闭环——UUID/URL 闭环比纯文字 prompt 一致性强得多；④ 客户端图片三级预取；⑤ 文档范式（AGENTS.md 不变量/依赖图/缓存敏感区）
- 缺失/劣势（Storyloom 差异点）：① "预测式"名不副实——全枚举无概率加权，成本线性膨胀、被弃分支无法取消；② 客户端无真流式文本（SSE 未接线，打字机模拟）——Storyloom 逐行流式解析在 TTFT 维度领先；③ freeform/点击探索永远冷启动（clearPool 全弃）——Storyloom 的 bridge 机制天然覆盖自由输入；④ 无跨会话内容缓存（sceneKey 只做 img2img 锚定）——Storyloom 的 AssetLibrary 可跨局复用

**价值评级：高**。Scene 级重叠的教科书实现，但文本流式/概率预取/跨会话缓存三项恰好是 Storyloom 的立足点。

---

## 4. 浅析与舍弃

### 4.1 ArtiMeow AI GalGamer RT（v1.2.0，Electron VN 框架）

**判定：完全"等待生成"型，舍弃深入分析。** 全非流式（`ai-service.js:655,669` `stream: false`）；无预取/预生成（`isGenerating` 互斥锁禁止并行，`game-engine.js:712-713`）；图像生成以 promise 启动但**在显示对话前被 await 阻塞**（`game-engine.js:835-857`），与阅读时间零重叠；每节点延迟 = 文本+图像全串行。
**可借鉴点（仅数据层）**：① 时间线+检查点回档（回档时后续章节移入 backup 而非删除，`project-manager.js:609-618`）；② 知识库增量更新协议（`knowledgeUpdates` 点路径式增量 + `charactersDelta` create/update/append-event 操作符，`ai-service.js:953-1104`）；③ 一次调用产出完整结构化 JSON（对话/选项/图像提示词/知识更新一次成型）。
**价值评级：中**（实时机制为零，数据模型可浅读）。

### 4.2 LangStory（2026-06-06，Next.js 交互叙事）

**判定：可舍弃。** `llm.ts:32` 用 `generateText`（非流式，同步等待完整输出）；前端在当前节点指令队列耗尽后才发起下一请求（`page.tsx:256-265`）；无预取/并行/缓存；history 全量重发（`prompt.ts:105-109`），连滑动窗口都没有。
**可借鉴点（仅形式）**：Ren'Pro DSL（精简 Ren'Py 子集 `scene/show/say/menu/jump`）作为 AI 输出格式 + 线性指令队列消费，节点内多条对白天然"无缝"；解析器容错降级渲染。
**价值评级：低-中**（纯同步等待，无任何重叠机制）。

### 4.3 Ciallo Galgame Engine（Gitee rtccn_mc/ciallo-galgame-engine）

**判定：舍弃（源码不可得）。** Gitee 仓库已不可公开访问（API 返回 Not Found Project / 403），git clone 需认证，无 GitHub 镜像、无 Wayback 存档。基于公开信息（Gitee 页面 + 搜索引擎摘要）：
- 基于 GLM AI（GLM-4-Flash）的 Web 视觉小说引擎，支持场景、角色、表情与 AI 决策
- API 形如 `POST /api/character/get_state`（获取角色状态）——AI 是**决策/状态引擎**（传统 VN 引擎 + AI 辅助），而非"实时生成全部内容"型
**价值评级：低-中**。与"实时生成+桥接"体系不直接对标，不构成分析价值。

---

## 5. 实时驱动与无缝体验的机制分类

对全部 6 个竞品 + Storyloom 的机制做归约，所有"无缝"手段可归入四种模式：

### 模式 A：流式 + 桥接（生成与消费重叠）— Storyloom 独有

LLM 输出逐行流式解析（TTFT 压缩），每轮内容尾部带缓冲区（`<bridge/>` 后纯叙事），程序在解析完成瞬间后台发起下一轮生成。**生成发生在用户消费期间，等待被结构性消除**（核心方程：实际等待 = TTFT + 素材剩余 − 消费覆盖）。

- 采用者：**Storyloom**（文本模式轮内重叠 + 图模式事件级异步素材）
- 竞品中无一家完整实现此模式（InfiPlot 的枚举预生成是"场景级"变体，见模式 C）

### 模式 B：回合内流式 + 缓冲（等待压缩，不消除）

回合内：LLM 流式输出 → 边生成边展示（TTFT ≈ 首行），缓冲增长供点读。回合间：硬等待整轮生成。**重叠只发生在"生成流"与"阅读流"之间，不跨回合**。

- 采用者：**Ars Fabula VN**（`run_turn_stream` 行缓冲 + 首 beat 即渲染）；**Ephemeral Hearts** 的近似形态（文本阶段先行，但 LLM 本身非流式）
- 特征：本地小模型快 + 素材预生成来压缩等待，不解决等待本身

### 模式 C：分支枚举预生成（消费窗口覆盖下一分支生成）— InfiPlot 独有

玩家读一幕时，把该幕所有 change-scene 选项的完整下一幕（含绘图）全部预生成，缓存键 = 选择路径；命中即零等待切换。**重叠发生在"消费当前幕"与"生成所有下一幕分支"之间**，是桥接的"分支维度"泛化。

- 采用者：**InfiPlot**（全枚举无概率 + 必经节点前视 2 层 + PREFETCH_MAX_DEPTH=3）
- 特征：零等待体验最好，但成本随分支数线性膨胀、被弃分支无法取消

### 模式 D：缓存回避（复用替代生成）

不追求重叠，而是让生成尽量不发生：素材按内容哈希缓存（同 prompt 同 seed 复用）、角色/场景预烘焙、音色冻结。适用于"内容重复率高"的场景（固定角色/固定情绪）。

- 采用者：**Ephemeral Hearts**（sha1 磁盘缓存 + seed 固定）、**Ars Fabula VN**（7 表情预生成落盘）、**InfiPlot**（预烘焙首幕、prompt 前缀缓存）
- 特征：与重叠正交——缓存解决"再次生成"，重叠解决"首次生成"

### 无任何机制（纯同步等待）

- **ArtiMeow**（stream:false + 图像阻塞展示）、**LangStory**（generateText 同步）、**Ciallo**（传统引擎 + AI 辅助决策，非实时生成型）

---

## 6. 结论与启示

### 6.1 竞品对"实时驱动"的三种回答

| 项目 | 无缝机制 | 首展示延迟 | 跨回合重叠 | 素材策略 |
|------|---------|-----------|-----------|---------|
| Storyloom | 流式解析 + bridge 预取 | TTFT（首 token） | ✅ 结构性 | 选择优先 + 异步任务池 |
| InfiPlot | 分支枚举预生成 | 整幕（打字机模拟） | ✅ 分支级（场景粒度） | 参考图闭环 + 双请求竞速 |
| Ars Fabula VN | 回合内流式 + 缓冲 | TTFT（首行） | ❌ 回合间硬等待 | 全预生成 + 同步兜底 |
| Ephemeral Hearts | 两阶段回合 + 重度缓存 | 完整生成时间 | ❌ 无 | 缓存回避（sha1） |
| ArtiMeow / LangStory / Ciallo | 无 | 完整生成时间 | ❌ 无 | 无 |

### 6.2 关键发现

1. **"AI 实时生成互动叙事"已是一个拥挤赛道**，但**没有一家实现了 Storyloom 的"轮内流式 + bridge 重叠"组合**。最接近的 InfiPlot 做的是场景级枚举预生成（分支维度），Ephemeral Hearts 做的是缓存回避，Ars Fabula VN 做的是回合内缓冲——三者都在"隐藏等待"，而 Storyloom 是唯一在"结构性消除轮内等待"（流式 + 标记驱动预取）的方向上做出完整体系的项目。

2. **哲学同源是普遍现象**："LLM 提议、程序裁决"（Ephemeral Hearts 的 apply_directives、Ars Fabula 的 cast-lock、InfiPlot 的 coerce/repair/degrade）已成为该领域的共识。Storyloom 的差异化不在哲学，而在**执行深度**：结构化 XML + 行号 + 状态校验 + 双队列 + 事件任务管线的组合复杂度。

3. **流式是分水岭**：真流式（Storyloom、Ars Fabula）与假流式（Ephemeral Hearts 打字机、InfiPlot 未接线的 SSE）的体验差距，正是"首展示时间 = TTFT vs 完整生成时间"的理论差距。

### 6.3 可移植的借鉴项（按优先级）

1. **grammar-constrained decoding**（Ephemeral Hearts，llama-cpp GBNF）：把格式可靠性从 prompt 层提升到解码层，LLM 无法输出非法结构——可解决 Storyloom 的 XML 格式错误问题（当前靠格式错误反馈循环）
2. **验证器驱动的自举微调闭环**（Ars Fabula）：把 StreamParser 复用到训练数据门控——运行时 trace → 校验 → SFT → 微调 → 同校验器评估
3. **TTS/STT 语音全链路**（Ephemeral Hearts，Kokoro 按角色冻结音色）——Phase 3 路线图已有 TTS，可参考其按角色冻结音色的做法
4. **参考图闭环**（InfiPlot，img2img 锚定）：素材一致性强于纯文字 prompt——Storyloom 曾因参考图 4.4× 减速而禁用（GENERATE_REF_IMAGE_COUNT 3→0），未来模型提速后可恢复
5. **prompt 前缀缓存**（InfiPlot，SENTINEL append-only）：LLM 侧 prompt 缓存命中率优化
6. **数据层**：ArtiMeow 的增量知识库协议（knowledgeUpdates/charactersDelta）与检查点回档"移动而非删除"

### 6.4 需警惕的教训（反向参照）

1. **全枚举预生成的成本膨胀**（InfiPlot）：无概率加权 + 服务端不可取消 → 分支数线性成本。若做分支级预生成，必须配概率/预算控制与服务端取消
2. **假流式**（Ephemeral Hearts / InfiPlot）：前端打字机模拟渐进，掩盖的是"首展示 = 完整生成"的事实——体验上限受制于后端
3. **素材僵硬**（Ars Fabula）：全量预生成（数分钟）或同步阻塞（120s）都不可取，"选择优先于生成 + 异步任务池"是正解
4. **"预测式"的诚实性问题**（InfiPlot）：营销声称 vs 实现真相（枚举非预测）——Storyloom 对外表述应保持"桥接/重叠"的准确语义

### 6.5 一句话总结

> 竞品赛道拥挤但无重叠：InfiPlot 用"分支枚举预生成"在场景粒度实现重叠（成本高、假流式），
> Ephemeral Hearts 用"缓存回避 + grammar 约束"藏延迟（非流式、无桥接），
> Ars Fabula 用"回合内流式缓冲"压缩等待（回合间硬等待），
> ArtiMeow/LangStory/Ciallo 纯同步等待无机制。
> **Storyloom 的"流式解析 + bridge 标记驱动预取 + 素材异步管线"组合在竞品中独此一家**——
> 它是唯一把"生成与消费重叠"做到轮内结构性实现（而非场景级枚举/缓存回避/回合内缓冲）的引擎。

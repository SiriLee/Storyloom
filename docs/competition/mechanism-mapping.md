# 竞品实现机制详解：三个高价值项目"到底怎么做的"，对照 Storyloom

> 本文是 [`competitor-analysis.md`](./competitor-analysis.md) 的配套详解。那份报告偏结论、偏抽象，
> 本文把它提到的每个机制拆到**代码行**，用"人话"讲清实现路径，并逐条映射到 Storyloom 的对应实现，
> 方便你用自己的代码体系去理解别人做了什么。
>
> 覆盖范围：**Ars Fabula VN**（回合内流式+缓冲）、**Ephemeral Hearts**（两阶段回合+缓存回避+grammar）、
> **InfiPlot**（分支枚举预生成）。ArtiMeow / LangStory / Ciallo 无实时机制，不在此详解（见分析报告 §4）。
>
> 证据格式：`仓库路径:行号`（仓库位于 `../../oss/`），Storyloom 侧引用 `src/storyloom/...:行号` 或规范文档。
> 所有引用均经核实。

---

## 0. 阅读指南：先把"黑话"翻译成人话

分析报告里反复出现的术语，先用 Storyloom 的语言对一遍。**每回合（round）**＝Storyloom 里一次
LLM 调用产出的一整段 `<story>` 输出（含交互区 + 缓冲区）。竞品叫法不同（Ars Fabula 叫 turn，
InfiPlot 叫 scene/beat），但都是"一次生成 + 一次消费 + 一次交互"的基本单元。

| 术语 | 人话解释 | Storyloom 对应物 |
|------|---------|-----------------|
| **TTFT**（Time To First Token） | 从发出请求到收到**第一个 token** 的时间。模型"思考"和网络传输都算在里面，通常占生成时间的相当比例。 | `docs/theory/streaming-parse.md`：不流式则首展示 = 总生成时间，流式则首展示 ≈ TTFT |
| **流式（streaming）** | LLM 不是一次性吐完整段文字，而是边生成边把 token 逐个/逐块发过来。程序可以"边收边解析边展示"。 | Storyloom 的 `StreamParser.feed_line()`（`stream_parser.py:177`）逐行消费 token 流 |
| **假流式** | 后端其实**一次性**返回完整文本，前端用打字机效果逐字显示，造成"在生成"的错觉。体验上限被后端锁死。 | Storyloom 无此物——逐行解析是真流式 |
| **缓冲（buffer）** | 生成器把已收到的文本攒起来，攒到"完整一行/完整一段"再交给 UI。UI 端也有缓冲队列，按自己的节奏消费。 | Storyloom 的 `LineBuffer`（`stream_parser.py:577`）；UI 队列缓冲模式（`exec-flow.md` §4.5） |
| **重叠（overlap）** | 生成与消费同时进行：用户在读上一段时，程序在生成下一段。这是所有"无缝"机制的本质。 | Storyloom 的桥接机制（`bridge-mechanism.md`）：`<bridge/>` 之后的缓冲区消费时间 = 下一轮生成时间 |
| **回合内 vs 跨回合** | 回合内＝一轮生成的过程中边生成边展示（只压缩了这一轮内部的等待）；跨回合＝这一轮还没读完就开始生成下一轮（消除轮与轮之间的等待）。 | Storyloom 两者都有：回合内流式 + 跨回合 bridge 预取 |
| **程序裁决** | LLM 只"提议"，所有状态变更/内容合法性由程序代码最终把关，LLM 从不直接改状态。 | Storyloom 的"LLM 建议者，程序裁决者"（`first-principles.md` §1.6）；`StateManager` 校验 + `rejected_changes` |
| **素材（asset）** | 图、音、3D 等非文本媒体。生成耗时同样受"公理 1"约束。 | Storyloom 的 `AssetLibrary` / `GameAssetRoster`（`assets/_library.py`、`assets/_roster.py`） |
| **素材缓存/回避** | 不重新生成，而是把生成结果按内容哈希存盘，同需求直接复用（"再次生成"变 0）。 | Storyloom 的 `AssetLibrary.use_count` 复用机制（有引用计数的全局素材库，跨局可复用） |
| **grammar 约束解码** | 在模型解码层直接约束输出必须符合某个语法（如 JSON schema 编译成的 GBNF），模型"想输出非法结构都不可能"。 | Storyloom 目前无——格式可靠性靠 prompt 规范 + 格式错误反馈循环（见 §2.3.4 分析） |
| **预生成/预取（prefetch）** | 在玩家还没做出选择时，就把"可能的下一个内容"先生成好，命中即零等待。 | Storyloom 的 bridge 预取（确定性的下一轮）；InfiPlot 的枚举预生成是它的"分支维度"版本（见 §3.3.2） |

一句话记住各家的路线：**Storyloom 用"流式 + bridge"在轮内结构性消除等待；InfiPlot 用"枚举预生成"在
场景粒度隐藏等待；Ars Fabula 用"回合内流式缓冲"压缩等待；Ephemeral Hearts 用"缓存回避"让等待尽量不发生。**

---

## 1. Ars Fabula VN —— 回合内流式 + 缓冲（本地小模型，实时编剧校园恋爱 VN）

> 仓库：`../../oss/ars-fabula-vn`（Gradio 单体应用；llama.cpp llama-server 本地推理；
> ComfyUI + Anima 生成立绘；rembg 抠图；Kokoro/Chatterbox 可选配音）。

### 1.1 它是什么

完全本地运行的 AI 校园恋爱视觉小说。玩家先选 3-4 名角色组成 cast，之后每回合由本地小 LLM
**实时**写叙述 + 对话 + 舞台指令（驱动立绘表情、背景、配音、分支选项）。没有预写剧本。

### 1.2 一回合"从头到尾"怎么走（时序）

```
玩家点选选项
  │
  ▼
run_turn() 组装 prompt（SceneState + 最近 4 回合/1200 字符滑动窗口）
  │
  ▼
LlamaServerClient.stream()  ←── 对 llama-server 发 OpenAI 兼容请求（stream=true）
  │                            逐 token 收到增量文本
  ▼
run_turn_stream() 生成器：_split_complete_lines() 按"括号深度 + 引号感知"攒出完整行
  │                            攒到一行才 yield；多行 [TOOL: ...] 不会被劈开
  ▼
解析器：叙述文本 / [TOOL: name ...] 工具调用 / [角色名]: "台词" 三路分发
  │
  ▼
UI：首段（第一个 beat）一就绪立即渲染 ←── TTFT 后马上有字可看
  │    后续行 gr.skip() 不重绘屏幕，只往缓冲区里追加 beats
  ▼
玩家继续阅读（读速追平生成速时显示 ✦ pulse 提示"还在写"）
  │
  ▼
回合结束 → validate_turn() 全量复查（cast-lock 第三重）→ 下一轮等玩家点选才启动
```

**关键结论：回合内是流式的（首行即显示），回合间是硬等待的（无任何跨回合预生成）。**

### 1.3 关键机制拆解

#### 1.3.1 回合内流式：SSE 逐 token 读取 + 行缓冲切行

**是什么**：调用本地 llama-server 时用 `stream=true`，通过 OpenAI 兼容 SSE 逐块收 token，
程序攒行、切行、逐行解析，首行就绪就渲染。

**怎么实现**：
- `model_client.py:114-156` `LlamaServerClient.stream()`：对 llama-server 发 `stream=true` 请求，
  用 `iter_lines()` 逐行读 `data:` 帧，遇到 `[DONE]` 结束，每收到一段增量就 `yield` 给上层。
- `vn_engine.py:135-168` `_split_complete_lines()`：把增量文本攒进 `pending`，只在**括号深度为 0
  且不在双引号字符串内**的换行处切行——这样 LLM 把 `[TOOL: ... choices=[{...}]]` 换行排版时，
  一个工具调用不会被切成两半（`depth`/`in_str`/`esc` 三个计数器跟踪 `[ {`、`] }`、`"`、`\`）。
- `vn_engine.py:796-813` `run_turn_stream()` 主循环：每得到一条完整行就解析、yield 给 UI；
  行不完整就继续攒。
- UI 端 `ui/callbacks.py:392-411`：收到第一个完整 beat 立即 `render`，后续行走 `gr.skip()`
  只往缓冲追加，不重绘整个屏幕。

**和 Storyloom 的对应**：
- 等价物是 Storyloom 的 `LineBuffer` + `StreamParser.feed_line()`（`stream_parser.py:177`）——
  都是"攒行 → 切行 → 逐行解析 → 事件流"。
- **关键差异在切行策略**：Ars Fabula 用**语法结构**（括号/引号）判断行边界，因为它的 DSL
  是自由文本；Storyloom 用 **`NNN| ` 行号前缀**（`stream_parser.py:189-195`）让每行自包含，
  解析器不依赖括号状态。行号前缀还带来额外能力：**位置可追踪**（line 字段贯穿 Event/Task，
  图模式的行号对齐全靠它）——Ars Fabula 没有这个，所以它做不了"素材任务绑定到内容位置"。
- 另一个差异：Storyloom 的解析器会**校验 LLM 行号连续性**（`stream_parser.py:193-208`，
  本地计数为准、LLM 行号只做校验），格式错误记入 `format_errors` 下一轮反馈（`exec-flow.md` §4.1）；
  Ars Fabula 对行号无此概念。

#### 1.3.2 输出协议 DSL：叙述与工具调用混流

**是什么**：LLM 输出不是单一 XML 文档，而是"叙述文本 + `[TOOL: name ...]` 行内标记 + `[角色名]: "台词"`
交错"的混合流。解析器的设计主题是"宽容弱模型"——容错多级降级。

**怎么实现**：
- 格式契约定义在 `vn_prompt.py:49-88`（prompt 里教 LLM 怎么输出）；解析器在 `vn_engine.py`
  （`[TOOL:` 正则 + 括号平衡解析工具参数；台词用 `^\[(\w+)\]:\s*"..."` 正则识别）。
- `vn_engine.py:542-577` `_loads_lenient()` 四级容错：严格 JSON → `ast.literal_eval`（接受 Python repr）
  → 给裸 key 补引号 → 再试一次。模型输出不规范的代价被逐级兜住。

**和 Storyloom 的对应**：
- Storyloom 的对应物是**结构化 XML**（`<seg>/<choice>/<set>/<checkpoint>/<bridge/>`，`block-spec.md`）。
  Storyloom 走的是"**格式先结构化**"路线：XML + 行号前缀让每行可独立解析、状态校验前置；
  Ars Fabula 走的是"**格式后容错**"路线：自由文本 + 多级修复。二者哲学相反但互补——
  Storyloom 的 `_RE_*` 正则（`stream_parser.py:95-120`）逐行精确匹配，靠 prompt 约束格式；
  Ars Fabula 靠解析器兜底。
- Storyloom 的"位置可追踪"（行号）是 Ars Fabula 的 DSL 完全缺失的——这是它做不了
  "素材任务与内容位置绑定"（Storyloom 图模式 §4.3 行号对齐）的根本原因。

#### 1.3.3 程序裁决：validate_turn 与"通过校验 ≡ 引擎能接受"

**是什么**：回合输出在交给玩家前要过校验。最精彩的一点：**校验器复用引擎自己的解析器**，
所以"通过校验"与"引擎能真正消费这段输出"是完全等价的——校验不是另写一套规则，而是
"引擎能不能接受"的直接测量。

**怎么实现**（注意：比原分析报告更精确——`validate_turn` **不在运行时被引擎调用**，它是
**训练数据过滤器 + 评测指标**，运行时靠的是引擎内的行级清洗 + 回合末复查）：
- `vn_validate.py:22-23`：校验器直接 import 引擎的解析器函数。
- `vn_validate.py:123-244` `validate_turn()`：校验"工具调用可解析 / 枚举值合法 / choices 结构 /
  cast-lock（无 cast 外角色台词）/ 至少有叙述或 choices"。
- 运行时程序裁决另有其路（见 1.3.4 cast-lock 的引擎侧两道）。

**和 Storyloom 的对应**：
- 校验器复用引擎解析器 ≡ Storyloom 的 **`StreamParser` 本身就是唯一真源**：`StateManager`
  处理状态（`SET`/`CHECKPOINT`/`BRANCH`），非法变更进 `rejected_changes`（`block-spec.md` §3），
  下一轮反馈给 LLM——同一"引擎裁决"哲学。
- **可移植点（分析报告 §6.3-2）**：Ars Fabula 把"运行时 trace → validate 门控 → SFT 数据集 → 微调 →
  同校验器评估"做成了自举闭环（`trace_log.py` 收集 trace，`vn_engine.py:820-842` 写入）。
  Storyloom 完全可以把 `StreamParser` 复用为训练数据质量闸门。

#### 1.3.4 cast-lock 三重复合：prompt 强令 + 引擎清洗 + 回合末复查

**是什么**：cast 锁定后，LLM 不允许写 cast 之外的角色台词。三道防线，一道比一道硬。

**怎么实现**：
1. **prompt 强令**（`vn_prompt.py:45-47`）：prompt 明确"只能使用这些角色"。
2. **引擎行级清洗**（`vn_engine.py:394-412`）：解析时发现非 cast 台词，直接清洗/改写。
3. **回合末全量复查**（`vn_engine.py:816-850`）：整回合结束后再扫一遍，残留违规记入 trace。

**和 Storyloom 的对应**：同构且更激进。Storyloom 的对应物是 `StateManager` 对 `<set>` 的状态
校验 + `rejected_changes`（`block-spec.md`）——但 Storyloom 只管状态变量，不管"文本内容里
不许出现某角色"这类语义约束。若未来要做角色白名单，cast-lock 的三层结构可直接照搬。

#### 1.3.5 素材生成：全预生成 + 同步阻塞兜底（素材"僵硬"的典型案例）

**是什么**：立绘走"选角时一次烘焙"，背景走"现场生成但同步阻塞"。素材不异步，是它的短板，
也是理解 Storyloom 素材管线价值的反例。

**怎么实现**：
- **选角烘焙**：Gradio 状态机（`ui/callbacks.py` 的 `on_start`/`on_casting_confirm`/`redo`）——
  生成 base 立绘 → 用户确认 → **一次 bake 7 个标准表情**（`neutral/smile/laugh/sad/angry/
  surprised/embarrassed`，`vn_contracts.py:12-16` 定义）落盘缓存。此时 VRAM 要换手：
  杀 LLM 进程 → bake → 重启 LLM（`model_client.py:343-518` VRAM 编排 + `callbacks.py:82,273-274`）。
- **背景现场生成**：`providers.py:250` 对非预设 key 调用 `_comfy_wait(timeout=120)`——
  **同步阻塞最长 120 秒**；按设计只在 beat 边界调用（不打断文本流）。
- 图像转 data URI 内嵌 + `lru_cache`（`ui/media.py:12-43`），避免重复加载。
- `cast_pipeline.py`：人脸检测门 → FaceDetailer 逐表情重绘保身份 → rembg 抠图 → 统一裁切。

**和 Storyloom 的对应**：
- "选角烘焙 7 表情" ≈ Storyloom 的**共创阶段素材预构建**（`graph-mode-spec/design.md` §5.3/§6.1：
  共创时对 locations/characters 预生成初始素材，填充名册）。但 Storyloom 是异步并发的，
  Ars Fabula 是同步阻塞的（VRAM 换手）。
- "背景同步阻塞 120s" 是 Storyloom 明确反对的（分析报告 §6.4-3：全量预生成数分钟 /
  同步阻塞 120s 都不可取，"选择优先于生成 + 异步任务池"是正解）。对应实现：`TaskGenerator`
  O(1) 匹配 → `TaskPool` 异步生成（`tasks/_generator.py:82-140`）。
- "data URI + lru_cache" ≈ Storyloom 的 `media/` 文件 + `AssetLibrary`（`assets/_library.py:40`），
  但 Storyloom 是磁盘级持久复用（跨局可复用），Ars Fabula 是内存级会话内缓存。

#### 1.3.6 状态与记忆：SceneState + 文本滑动窗口

**是什么**：`SceneState`（`vn_contracts.py:124-168`）是回合间传递的结构化状态；记忆是
"尾部 4 回合 / 1200 字符"的纯文本滑动窗口，直接拼进 prompt。

**怎么实现**：`vn_prompt.py:256-289` `build_recent_history(max_turns=4, max_chars=1200)` 截取
最近历史，注入 prompt 的 RECENT STORY 块（`vn_prompt.py:317-320`）。无摘要压缩——旧内容
直接滑出窗口丢失。

**和 Storyloom 的对应**：Storyloom 的 `ContextManager`（`context_manager.py`）是**滑动窗口 +
摘要压缩**：WINDOW_SIZE=3 完整保留 + 滑出窗口的轮次压缩为 checkpoint summary 注入
（`prompt-design.md` §4.1）。Storyloom 有压缩、Ars Fabula 没有（记忆单薄，分析报告原话）。

### 1.4 与 Storyloom 的机制对照表

| 维度 | Ars Fabula VN | Storyloom |
|------|--------------|-----------|
| 流式读取 | OpenAI SSE 逐 token（`model_client.py:114-156`） | OpenAI 兼容流式 + `LineBuffer`（`stream_parser.py:577`） |
| 行切分 | 括号深度 + 引号感知（`vn_engine.py:135-168`） | `NNN\| ` 行号前缀，每行自包含（`stream_parser.py:189-195`） |
| 位置追踪 | ❌ 无 | ✅ 行号贯穿 Event/Task，图模式行号对齐（`event_dispatcher.py:164`） |
| 输出格式 | 自由 DSL 混流 + 多级容错（`vn_engine.py:542-577`） | 结构化 XML + 逐行正则（`stream_parser.py:95-120`） |
| 程序裁决 | cast-lock 三重 + validate（运行时清洗 + 回合末复查） | `StateManager` 状态校验 + `rejected_changes`（`block-spec.md`） |
| 跨回合重叠 | ❌ 无（回合间硬等待） | ✅ bridge 预取（`game_loop.py:929-966` Phase 5 触发） |
| 素材 | 全预生成（bake）+ 同步阻塞 120s（`providers.py:250`） | 选择优先 + 异步任务池（`tasks/_generator.py`） |
| 素材复用 | data URI + 内存 lru_cache | 磁盘 `AssetLibrary` + `use_count` 引用计数（`assets/_library.py:292`） |
| 记忆 | 4 回合/1200 字符滑动窗口，无压缩 | 3 轮窗口 + checkpoint summary 压缩（`context_manager.py`） |
| 自举数据 | trace → validate 门控 → SFT（`trace_log.py`） | 无（可移植） |

**价值评级**：高（实时性落后于 Storyloom，但"程序裁决 + 自举数据 + 资产管线"三个方向是高质量参照）。

---

## 2. Ephemeral Hearts —— 两阶段回合 + 缓存回避 + grammar 约束（多角色协作 AI 即兴 VN）

> 仓库：`../../oss/ephemeral-hearts`（Gradio 前端；Qwen3-14B 经 llama.cpp / transformers / Modal 三后端；
> SDXL + anime LoRA 绘图；Whisper STT + Kokoro TTS；一仓库三运行时：本地 / Modal / ZeroGPU Space）。

### 2.1 它是什么

五个 AI 角色在 <18B 参数预算内协作：**Weaver**（导演/GM，输出结构化 directives）、**Voices**
（对话，共享权重）、**Painter**（SDXL-Turbo 图像）、**Ear**（Whisper 语音识别）、**Voice**
（Kokoro TTS）。核心口号：**"The model proposes, code disposes"**（模型提议，代码裁决）——
与 Storyloom 的"LLM 建议者，程序裁决者"同源。

### 2.2 一回合"从头到尾"怎么走（时序）

```
玩家输入（文本或语音）
  │
  ▼
/turn_text（engine.py:260-333）
  │   ① Ear（Whisper）转写语音（如需要）
  │   ② Weaver 阻塞式 LLM 调用 ←── 注意：非流式！等完整输出
  │   ③ state.apply_directives() 应用状态变更（唯一 mutator）
  │   ④ 返回"无图 ViewState"（文本 + 立绘 + 情绪 + 选项）
  ▼
前端先渲染文本（打字机效果，16ms/字符）
  │
  ▼
/turn_images（engine.py:335-345）独立调用
  │   ① Painter 查 sha1 磁盘缓存 → 命中 ≈0ms，未命中生成 1-5s
  │   ② Voice（Kokoro）按角色冻结音色合成 TTS
  │   ③ 返回图片 + 音频，前端后补渲染
  ▼
busy(true) 锁住输入直到图片阶段结束 → 下一回合
```

**关键结论：LLM 调用全程阻塞（无 stream）；"实时感"靠①文本阶段先行、②重度缓存、③前端打字机。**

### 2.3 关键机制拆解

#### 2.3.1 它为什么"非流式"（重要澄清）

**是什么**：README 声称 "text streams first"，但那是**前端打字机装饰**——后端其实是
一次性返回完整文本的。

**怎么实现**：
- `visualnovel/llm.py:75-100`：llama.cpp 后端 `complete()`/`complete_json()` 都是
  `create_chat_completion()` **阻塞调用**，无 `stream=True`；transformers 后端（`llm.py:140`）同理。
- 前端 `frontend/index.html:1011-1019`：`setInterval` 每 16ms 追加一个字符——纯装饰。
- 后果（分析报告 §3.2）：TTFT = 完整生成时间，首展示时间不压缩。

**和 Storyloom 的对应**：这是 Storyloom 流式解析要解决的问题本身。Storyloom 的
`GameLoop.stream_round()`（`game_loop.py:700`）消费 token 队列，解析器逐行产出事件
（`stream_parser.py:177`），首段展示时间 ≈ TTFT（`exec-flow.md` §4.3）。假流式 vs 真流式
的差距正是"完整生成时间 vs TTFT"。

#### 2.3.2 两阶段回合：文本先行，图像/音频后补

**是什么**：把"一回合"拆成两个 HTTP 调用——先返回**不含图**的文本 ViewState，用户立刻能读；
图像和语音作为第二阶段异步补齐。阅读文本的时间 = 图像生成的时间（重叠！）。

**怎么实现**：
- `visualnovel/engine.py:260-333` `/turn_text`：STT + LLM + 状态变更，返回无图 ViewState
  （含文本、立绘名、情绪、选项）。
- `visualnovel/engine.py:335-345` `/turn_images`：Painter 出图 + TTS 合成，返回图片/音频。
- 前端 `frontend/index.html:1654-1658`：先渲染文本，再异步请求 `/turn_images` 补图。
- 两阶段之间靠落盘状态文件衔接（ZeroGPU 无状态 worker 场景，`/tmp` 共享文件 + 原子写，
  `engine.py:35-57,321-341`）。

**和 Storyloom 的对应**：
- 这是 Storyloom 素材异步生成的**回合粒度简化版**。Storyloom 图模式（`graph-mode-spec/design.md`
  §3.1）：`StreamParser` 解析到 `<declare>`/`<set var="SCENE">`/`<seg char=...>` 即触发
  `TaskGenerator`（`tasks/_generator.py:56-72`），素材任务在**文本事件流中**异步执行，
  `EventDispatcher` 按行号对齐后绑定（`event_dispatcher.py:164`）。
- 差异：EH 是"整回合文本先出，整回合图像后补"（粒度=回合）；Storyloom 是"事件级管线并行"
  （粒度=事件/行号，素材按内容位置就绪，UI 消费到哪个位置就补哪个素材）。粒度越细，
  重叠窗口越大、等待越少。
- EH 用**落盘状态文件**跨 worker 衔接两个阶段——这是 ZeroGPU 无状态架构的妥协；
  Storyloom 单应用内用队列（Token Queue / Task Queue / UI Event Queue，`design.md` §3.3）
  不需要落盘。

#### 2.3.3 重度缓存：sha1 磁盘缓存 + seed 固定（"藏延迟"路线的核心）

**是什么**：Painter 每次生成前先按内容哈希查磁盘；同一角色同一情绪永远复用同一张图。
生成尽量"不发生"，等待自然消失。

**怎么实现**：
- `visualnovel/painter.py:180-198`：缓存键 = `sha1(kind|prompt|negative|seed|guidance)`，
  命中直接跳过 GPU 返回缓存文件。
- seed 按实体固定（`_seed_for`）：同一角色永远同一张脸 → 同一 prompt + seed 必命中缓存，
  图片阶段 ≈ 0ms。

**和 Storyloom 的对应**：
- Storyloom 的 `AssetLibrary`（`assets/_library.py:40`）是**全局素材库**：`add`/`get`/
  `increase_usage`/`decrease_usage`/`get_sorted_by_usage`/`clean`，跨局持久复用；
  `GameAssetRoster`（`assets/_roster.py:21`）是单局映射（local_name → Asset.target）。
- 差异：EH 缓存键 = **生成请求的哈希**（同请求必同结果）；Storyloom 缓存键 = **素材实体
  （类型+ID）**，靠"选择优先于生成"（O(1) 匹配 → LLM 匹配兜底 → AI 生成，`design.md` §5）复用。
  Storyloom 不哈希 prompt——因为同一需求（local_name）在不同轮次可能被描述得更详细，
  Storyloom 按实体去重而不是按 prompt 去重，复用面更宽；EH 的哈希法在同实体但描述
  措辞不同时会 miss，需要 seed 固定来强制对齐。

#### 2.3.4 grammar 约束解码：格式可靠性从 prompt 层提升到解码层

**是什么**：不让 LLM "尽量"输出合法 JSON，而是让解码器**只能**输出合法 JSON——用
GBNF grammar 约束采样过程，模型想输出非法结构都不可能。

**怎么实现**：
- `visualnovel/llm.py:81-99`：`complete_json()` 传 `response_format={"type": "json_object",
  "schema": schema}`——llama-cpp-python 自动把 Pydantic/JSON schema 编译成 GBNF grammar
  作为解码约束。
- `visualnovel/prompts.py:238-243`：把 `emotion`、`relationship_delta` 提升为 **required** 字段——
  不是靠 prompt 语气要求，而是靠 schema 强制，缺了解码根本过不去。
- 名句在 `BLOG.md:384`："grammar is a constraint, prompting is a suggestion"。
- `visualnovel/utils.py:34-70` `close_truncated_json()`：即便有 grammar，`max_tokens` 截断
  仍可能留下未闭合 JSON，做最后一层修复。
- **跨后端降级**（重要边界）：grammar 只在 llama.cpp 后端可用（`llm.py:84-92`）。
  transformers 后端无 grammar 支持，退化为"骨架注入 + 3 次重试"（`llm.py:168-208`）——
  同一份代码在不同推理后端上，格式可靠性的等级不同。这对 Storyloom 的启示：
  grammar 约束不能作为**唯一**防线，prompt 规范 + 解析容错 + 反馈循环的"事后防线"
  仍然必须有（对应 Storyloom 三层防线，见下）。

**和 Storyloom 的对应**：
- Storyloom 的格式可靠性靠：① prompt 规范（`prompt-design.md` §4.2 首轮前缀 + XML 格式示例）；
  ② 流式解析容错（`stream_parser.py` 逐行正则，宽容原则 `block-spec.md` §2.4）；
  ③ 格式错误反馈循环（`format_errors` → 下一轮 prompt 追加 "Format reminder"，`prompt-design.md` §4.1）。
- **可移植点（分析报告 §6.3-1，优先级最高）**：把 `<story>` 的 XML 结构约束到解码层。
  Storyloom 走 OpenAI 兼容 API，大部分供应商（OpenAI/DeepSeek 等）不支持 GBNF，但支持
  `response_format={"type": "json_object"}` 等约束；本地部署（llama.cpp）路径则可以完整
  落地 GBNF。分析报告原文：可解决 Storyloom 的 XML 格式错误问题（当前靠反馈循环，是
  "事后纠错"；grammar 是"事前禁止"）。

#### 2.3.5 model proposes, code disposes：apply_directives 唯一 mutator

**是什么**：LLM 输出是"提议"（directives），程序是唯一能改状态的地方。程序对提议做
clamp/白名单/节流/静默忽略，LLM 从不直接写状态。

**怎么实现**：
- `visualnovel/state.py:25-140` `apply_directives()` 是**唯一 mutator**（头注释即声明此约定，
  `state.py:1-9`）：LLM 建议 `emotion`/`relationship_delta`/`location` 等，程序校验范围、
  clamp 到合法值（如关系值 clamp ±100，`:65`）、白名单外情绪静默忽略（`:114-117`）、
  不在场角色的 exit 忽略（`:97`）、facts 上限 8 条（`:80`）、beat 最少间隔 4 回合节流
  （`:126-131`）。
- LLM 只读 `memory.assemble_context()` 生成的**字符串快照**（`memory.py:26-126`）——
  拿不到状态对象，改不了状态；`load_from_md` 直接 `NotImplementedError`（`state.py:206-210`），
  从根上禁止外部改状态。
- **第二道裁决**：`orchestrator.py:276-308` `_repair` 在应用前再钳一遍 speaker/delta/字段词数。
- **anti-repeat 热重试**（`orchestrator.py:152-177`）：新回合内容与历史用 `difflib` 比较，
  相似度 ≥ 0.95 判定为复读，立即用更高 temperature（0.9）+ presence_penalty（0.8）重试——
  这是"程序裁决"在**内容层**（而非状态层）的应用：LLM 想复读，程序不让。

**和 Storyloom 的对应**：
- 完全同构：Storyloom 的 `StateManager` 是状态唯一处理者，`<set>` 经校验后才应用，
  拒绝的变更进 `rejected_changes`（`block-spec.md` §3）；LLM 永远拿不到状态对象，
  只看到 prompt 里的状态文本。两家的哲学是同一个："程序裁决"。
- EH 的 clamp/静默忽略与 Storyloom 的"拒绝 + 反馈"略不同：EH 静默修正（不告诉 LLM），
  Storyloom 把拒绝记入 `rejected_changes` 反馈给 LLM 帮助学习（`prompt-design.md` §4.1 边界情况）。
  Storyloom 的反馈回路更利于模型收敛，EH 的静默修正更省 token——可对比取舍。

#### 2.3.6 状态与记忆：summary + 在场角色 sheets + token 预算压缩

**是什么**：上下文 = 滚动 summary + 仅在场角色的 sheets + 最近 6 回合，3500 token 预算，
超预算触发 LLM 压缩。

**怎么实现**：
- `visualnovel/config.py:102`：3500 token 预算；`:103` `RECENT_TURNS_K=6`（最近 6 回合完整保留）。
- `visualnovel/memory.py:135-162`：按 角色数×4 粗略估算每回合 token 占用，超预算就从
  **最旧的回合开始逐条丢弃**（不是一次性截断，而是渐进腾挪）。
- `memory.py:129-132` `should_compact`：回合数 > 12 时触发压缩 `compact_memory`
  （`orchestrator.py:183-214`）：LLM 用 `max_tokens=320` 的自由文本调用把历史压成摘要，
  消息尾追加 `/no_think` 指令防 Qwen3 输出 think 块（`:201`）+ `strip_think` 清理。
- `visualnovel/utils.py:34-70`：截断 JSON 修复（见 2.3.4，调用点 `llm.py:96-99`）。

**和 Storyloom 的对应**：与 Storyloom 的 `ContextManager`（`context_manager.py`）几乎一一对应：
系统 prompt 永不压缩（`context_manager.py:16-17`）+ 滑动窗口 3 轮完整保留 + 滑出窗口轮次
压缩为 checkpoint summary（`prompt-design.md` §4.1）。差异：Storyloom 的压缩源是
`<checkpoint summary="...">` 属性（程序结构化提取），EH 是 LLM 再生成一遍摘要；
Storyloom 的压缩源是"已发生事实的结晶体"，EH 是"模型转述"，前者更可靠、更省 token。

### 2.4 与 Storyloom 的机制对照表

| 维度 | Ephemeral Hearts | Storyloom |
|------|-----------------|-----------|
| LLM 流式 | ❌ 阻塞式（`llm.py:75-100`），前端打字机装饰（`frontend/index.html:1011-1019`） | ✅ 真流式逐行解析（`stream_parser.py:177`） |
| 回合结构 | 两阶段：文本先行 → 图像后补（`engine.py:260-345`） | 事件级管线并行：素材任务在文本流中异步（`design.md` §3.1） |
| 跨回合重叠 | ❌ 无（busy 锁输入，`frontend/index.html:1651,1661`） | ✅ bridge 预取（`game_loop.py:929-966`） |
| 素材复用 | sha1(prompt+seed) 磁盘缓存（`painter.py:180-198`） | AssetLibrary 实体复用 + use_count（`assets/_library.py`） |
| 格式约束 | grammar 解码约束（`llm.py:81-99`） | prompt 规范 + 反馈循环（`prompt-design.md` §4.1） |
| 程序裁决 | apply_directives 唯一 mutator，静默修正（`state.py:25-140`）；anti-repeat 内容层重试（`orchestrator.py:152-177`） | StateManager 校验 + rejected_changes 反馈（`block-spec.md`） |
| 记忆 | summary + 在场角色 + 6 回合，3500 token（`config.py:102`） | 系统 prompt 锚定 + 3 轮窗口 + checkpoint 摘要压缩（`context_manager.py`） |
| 出厂模式 | mock-first 零模型可跑通（`config.py:42`） | 测试全 mock（`tests/`），无 mock 运行模式（可借鉴） |
| 语音链路 | Whisper STT + Kokoro TTS 按角色冻结音色（`tts.py:117-136`） | 无（Phase 3 路线图；可借鉴音色冻结） |

**价值评级**：高。哲学同源但路线分岔：EH **藏延迟**（缓存+少改动），Storyloom **填延迟**
（流式+bridge 提前生成）。可移植项优先级：grammar 约束 → 语音链路 → 无状态会话。

---

## 3. InfiPlot —— 分支枚举预生成（场景级重叠，多智能体云端互动剧情）

> 仓库：`../../oss/infiplot`（Next.js 16 App Router；服务器刻意无状态，客户端携带完整 Session
> 随每次请求往返；LLM 走 OpenAI 兼容协议；图像 Runware FLUX.2；TTS 小米 MiMo / StepFun；
> 双运行模式：服务器 API / BYO 浏览器直连）。

### 3.1 它是什么

"用 AI 实时生成内容的《完蛋！我被美女包围了！》"——玩家输入世界观+画风，引擎现场生成整部
剧情。每个 scene = 1 张 AI 背景图 + 一棵 beat（节拍）树（旁白/对白/选项）。多智能体分工：
**Writer**（唯一内容大脑）、**CharacterDesigner**（角色视觉+音色卡）、**Cinematographer**
（构图 prompt）、**Painter**（背景图）、StyleSelector / Vision / InsertBeat（辅助）。

### 3.2 一次场景"从头到尾"怎么走（时序）

```
玩家进入/切换到一个 scene
  │
  ▼
① Writer 单次流式调用：输出 <plan> → <story> → <choices> 三段标签流（director.ts:210）
  │    </plan> 一关闭 → 下游图像管线解锁（resolvePlan, director.ts:236）
  │    <story> 仍在流式 → 边流边拆 beat（onStoryComplete, director.ts:242-252）
  ▼
② 并行阶段：角色卡 ∥ 分镜（Promise.all, director.ts:341-344）
  │    CharacterDesigner 出视觉/音色文本卡；Cinematographer 出 FLUX 构图 prompt
  ▼
③ 串行依赖：入场角色头像（await）→ Painter 出场景背景图（await）→ 其余头像+配音并行
  ▼
④ 玩家开始读（打字机效果）；同时 useEffect 触发"预测式预生成"：
  │    枚举本场景全部 change-scene 选项 → 每个选项预生成完整下一场景（含绘图）
  ▼
⑤ 玩家做选择 → 查预取缓存：
  │    命中 → 零等待切换（图已就绪）；未命中 → 现场生成
  ▼
⑥ 被弃分支 abort（只停客户端等待，服务端成本照付）
```

**关键结论：玩家阅读一幕的时间 = 所有下一幕分支的生成时间（场景级重叠）。文本不是真流式
（SSE 未接线，打字机），但"选择即零等待"的体验确实做到了——靠的是枚举预生成 + 图片预取。**

### 3.3 关键机制拆解

#### 3.3.1 多智能体编排：Promise DAG（有依赖就串行，无依赖就并行）

**是什么**：一次场景生成不是顺序跑 5 个智能体，而是按数据依赖拼成一张执行图：
能并行的并行，有依赖的等待。

**怎么实现**（`lib/engine/director.ts`）：
- Writer 是唯一内容源：`runWriterStream`（`agents/writer.ts:443-452`，单次 LLM 流式调用）
  → 标签流交给 `routeTaggedStream`（`director.ts:228`）。
- 角色卡 ∥ 分镜：`Promise.all([Promise.all(cardPromises), cinemaPromise])`（`director.ts:341-344`）——
  CharacterDesigner 出文本卡（`characterDesigner.ts:164-188`）与 Cinematographer 出构图
  prompt（`cinematographer.ts:50-86`）互不依赖，先并行。
- 然后按依赖串行/并行：`entryNames`（入场角色集合，`director.ts:359-365`）→ 入场头像 await
  （407-417）→ Painter 出场景图 await（424-435，因为背景图要参考角色图）→ 其余头像 + 配音
  `Promise.all`（444-447，藏在 Painter 背后偷偷做完）。
- 数据流闭环：plan → 角色卡 → 头像 → `mergeCharacters`（86-117）→ referenceImages → 场景图。

**和 Storyloom 的对应**：Storyloom 图模式的并行骨架是 **TaskPool 线程池 + 任务流水线**
（`design.md` §3.3：Token Queue / Task Queue / UI Event Queue 三队列 + 四线程）。
InfiPlot 的 Promise DAG 是"前端编排"（一个场景内多智能体的依赖图），Storyloom 的 TaskPool
是"引擎侧编排"（一个文本流内多个素材任务的并发执行）。二者解决不同层的问题：
InfiPlot 编排**谁生成什么**（多智能体分工），Storyloom 编排**素材何时就绪**（事件-任务绑定）。

#### 3.3.2 预测式预生成：全枚举 + 必经节点前视（核心机制）

**是什么**："预测"不是概率预测——是把本场景**所有**换场选项的下一场景**全部真实生成一遍**
（L1）；如果某个生成结果的场景恰好只有 1 个换场出口（必经节点），就递归再预生成它的下一幕
（L2/L3）。缓存键 = 选择路径。命中即零等待。

**怎么实现**：
- **触发**：`useEffect(..., [currentScene?.id, session?.id])`（`app/[locale]/play/page.tsx:2008-2036`）
  ——玩家一进入新场景就触发，阅读窗口与生成窗口天然重叠。
- **L1 全枚举**：`findAllChangeSceneChoices()`（`page.tsx:387-401`）收集本场景所有
  `change-scene` 选项，逐个 `prefetchScenePath(..., depth=0)`（`page.tsx:408-503`），
  每个都真实调用一次 `requestScene()`（431）——**含绘图**。
- **L2/L3 前视**：预生成结果返回后，`findSoleChangeSceneChoice()`（`page.tsx:403-406`，
  恰好 1 个换场出口）且 `depth+1 < PREFETCH_MAX_DEPTH`（452）→ 递归（474-481）；
  `PREFETCH_MAX_DEPTH = 3`（`page.tsx:296`）深度上限。
- **缓存键**：`pathKey` = 各步 choiceId 用 `/` 拼接（`page.tsx:361-363`），如 `"C1"`、`"C1/C2"`；
  `pool` Map 按 key 去重（425、502）。服务端 `writer.ts:312-326` `ensureUniqueChoiceIds()`
  强制 choiceId 全局唯一（注释明说 id 是前端预取缓存键）。
- **消费**：玩家选 C1 → `consumeChoice`（`page.tsx:505-522`）：`pool.get(choiceId)` 命中直接转场；
  以 `choiceId + "/"` 开头的后裔 key（C1/C2 等）**去前缀重挂**（514，预生成成果不浪费）；
  其余 entry `abort()`（516）。自由输入走 `clearPool` 全杀（`page.tsx:2397,524-527`）。
- **投机 Session**：预生成用的是 `buildSpeculativeSession`（`page.tsx:365-385`）构造的假 Session
  （真实 Session 去掉最后一条 history、把假想选择塞进去），服务端无法分辨，照常生成。
- **成本洞**：`prefetchScenePath` 的 `requestScene` 不传 signal（`page.tsx:431`），
  `lib/ai-client/chat.ts:174-180` 的 SDK 调用也不接受 AbortSignal——abort 只停客户端等待，
  **服务端 Writer+角色卡+分镜+Painter 全流程照跑，成本照付**。

**和 Storyloom 的对应**：
- 这是 bridge 的**分支维度泛化**（分析报告 §5 模式 C）：Storyloom 的 bridge 是"当前轮的
  尾部缓冲区覆盖**确定的一条**下一轮路径"；InfiPlot 是"当前场景的阅读时间覆盖**所有可能的**
  下一场景"。前者确定性、成本低；后者体验上限高（选择即零等待）但成本随分支数线性膨胀。
- Storyloom 的对应能力：`GameLoop` Phase 5 在 `</story>` 处组装下一轮 prompt 并后台启动
  API 调用（`game_loop.py:929-966` + `_launch_api` 1086）——但只预取**一条**（bridge 之后
  的衔接是确定的）。
- **可借鉴（分析报告 ★）**：若做分支级预生成，必须配概率/预算控制与服务端取消——
  InfiPlot 两项都没有（§6.4-1 教训）。Storyloom 若将来在 checkpoint 路由处做多分支预生成，
  应在 `evaluate_routes`（`game_loop.py:1444`）之后枚举候选路由、按大纲概率预算上限。

#### 3.3.3 Writer 单流分标签 + StreamRouter：一个调用同时出骨架和正文

**是什么**：不让"规划"和"正文"分成两次 LLM 调用——一次流式调用按
`<plan> → <story> → <choices>` 顺序输出，程序在流中实时切标签。`</plan>` 一关闭，
图像管线就解锁，与还在流的 `<story>` 并行——**快速骨架和慢速正文在时间上重叠**。

**怎么实现**：
- `lib/engine/stream/index.ts:85-181` `scan()` 状态机：无标签时找最早 open 标签（87-113），
  标签内找 close（116-160）；"半截标签跨 chunk"时回退光标（104、177-178）。
  `</plan>` → `onPlan`（123-131）；`</story>` → 存原文 + `onStoryComplete`（132-148）；
  `</choices>` → `onChoices`（149-155）。
- `director.ts:236` `resolvePlan(coerced)` 让 `await planPromise`（286）立即返回，而
  `routeTaggedStream` 本身是独立 Promise（228-283）继续跑，与图像管线并发，464 行才收尾。

**和 Storyloom 的对应**：结构上非常接近 Storyloom 的流式解析——都是"边收边解析、标签驱动"。
但用途不同：
- InfiPlot 的 StreamRouter 切的是**同一调用内的三段标签**，用 `</plan>` 提前解锁**下游智能体**；
- Storyloom 的 StreamParser 切的是**结构元素**（`<seg>/<choice>/<bridge/>`），用 `<bridge/>`
  提前解锁**下一轮调用** + 图模式里用 `<declare>/<seg char>` 提前触发**素材任务**。
- 共同点：**"早期信号提前启动下游"**。Storyloom 的对应实现是 `TaskGenerator.enqueue()`
  （`tasks/_generator.py:56-72`）在解析到 SCENE/SEG-with-char/DECLARE 时立刻构造任务，
  以及 bridge 处切换 post-bridge 快速模式（`stream_parser.py:545` bridge_seen）。

#### 3.3.4 假流式：SSE 已建好但没接线，打字机冒充

**是什么**：服务端 SSE、客户端解析器**都写好了**，但 play 页从未把 `emit` 回调接进
`requestScene`——实际全部走 JSON 整包返回，"渐进"是打字机装出来的。

**怎么实现**：
- 服务端已实现：`app/api/scene/route.ts:37` 检测 `Accept: text/event-stream` → 59-93
  `ReadableStream` 用 `formatSSE`（16-18）推 `plan/beat/background/voice/done` 事件。
- 客户端已实现但没接线：`lib/engineClient.ts:111-174` `fetchSSE`（135-137 无 emit 或非 SSE
  直接 `res.json()`）；但 play 页全部 `requestScene`/`startSession` 调用（431、1927、2357、
  2409、2537）**均不传 emit** → 恒走 JSON 整包。
- 打字机：`components/PlayCanvas.tsx:37-107` `useTypewriter`，`setInterval` 逐字
  `text.slice(0, i)`（79-86），`targetDurationMs` 按音频时长调速（73-76），skip 立即补全（93-100）。

**和 Storyloom 的对应**：分析报告 §6.4-2 的"假流式"教训——前端打字机掩盖"首展示 = 完整生成"
的事实。Storyloom 是逐行真流式（`stream_parser.py`），TTFT 维度领先（§6.2-3 分水岭）。
InfiPlot 的 SSE 管线是"写了没接"，若未来接线，其 `formatSSE` 事件（plan/beat/background）
与 Storyloom 的 `stream_round()` 事件（`game_loop.py:700` 的 token/segment/bridge/options）
是同构的。

#### 3.3.5 无缝体验机制清单（每个机制在哪、怎么工作）

| 机制 | 实现位置 | 怎么工作 |
|------|---------|---------|
| 图片预加载+解码 | `play/page.tsx:175-196` `preloadImage` | `new Image()` 加载 + `img.decode()`（191）强制解码完成再 resolve，提前暖 HTTP 缓存 |
| 图片就绪闸门 | `play/page.tsx:838-850` `waitForImageReady` + `PlayCanvas.tsx:359,723-727` | `phase==="transitioning"` 时整图 `opacity-40` + 遮罩，真解码完成才 `setPhase("ready")`（2122-2126） |
| 双请求竞速 | `lib/engine/agents/painter.ts:153-224` `tryGenerateHedged` | 先发 leg1，`setTimeout(hedgeMs)`（181-183）后 `Promise.race`（185），超时未决再发 leg2（196）再 race（198），胜者返回、败者 abort（209）；`IMAGE_HEDGE_MS` 环境变量开启（`config.ts:93`） |
| 参考图闭环 | `writer.ts:332-341`（sceneKey 归一化）→ `director.ts:128-143` `pickPriorSceneReference` → `painter.ts:91-93` → `image.ts:445-447` | 同 sceneKey 的旧场景图作为 `referenceImages` 传入 img2img，空间/光照/布局连续 |
| prompt 前缀缓存 | `lib/engine/context/index.ts:14-22` + `chat.ts:85-98` | 稳定前缀（角色卡 82-92、prior-sceneKeys 108-114）append-only 追加，SENTINEL 保字节稳定；读 `cached_tokens` 统计命中率 |
| 预烘焙首幕 | `play/page.tsx:1699,1898-1925` | `?card=` 参数直接 fetch 预烘焙 JSON（`/home/firstact/{cardName}.json`），零引擎调用启动 |

**和 Storyloom 的对应**：
- 图片预加载/就绪闸门 ≈ Storyloom UI 的"占位优先"：`GameAssetRoster` 中 `target=None` 的
  占位条目用默认占位图（`design.md` §2.3），素材就绪后替换。
- 双请求竞速：Storyloom 无——是"宁可多花一腿钱也要快"的激进策略（可借鉴但需预算控制）。
- 参考图闭环：Storyloom 曾启用后禁用（`GENERATE_REF_IMAGE_COUNT` 3→0，因 4.4× 减速，
  分析报告 §6.3-4）——模型提速后可恢复，InfiPlot 的实现（`referenceImages` ≤4 张 + slot
  优先级）是恢复时的参考。
- prompt 前缀缓存：与 Storyloom 的"Round 1 前缀永久锚定"（`prompt-design.md` §4.2）目的
  相同（让 LLM 侧 prompt 缓存命中），但 Storyloom 是消息结构层面保证，InfiPlot 是字节层面
  保证（SENTINEL append-only）——后者更细，可参考其字节稳定性做法。
- 预烘焙首幕 ≈ Storyloom 共创阶段的**素材预构建**（`design.md` §5.3：共创时预生成初始素材）+
  **预烘焙卡**概念；Storyloom 的 `SystemManifest`（`assets/_manifest.py`）加载系统素材可视为
  同思路。

#### 3.3.6 状态与一致性：客户端 Session 全量往返 + 双层 StoryState + 四层治理

**是什么**：服务器无状态——客户端把完整 Session（worldSetting/styleGuide/history/characters/
storyState）随每次请求上传。StoryState 分两层：稳定主轴（storyBible）不可改写 + 易变区每幕
patch。所有 LLM 输出过"raw → coerce → repair → fallback"四层治理。

**怎么实现**：
- Session 结构：`lib/types/index.ts:367-415`（id/worldSetting/styleGuide/history/characters/
  storyState/styleReferenceImage/orientation/playerName/language/worldBooks）。
- StoryState 双层：`types/index.ts:302-334` 稳定区（logline/genreTags/protagonist/castNotes）
  + 易变区（synopsis/openThreads/relationships/nextHook，patch 329-334）；
  `applyStoryStatePatch`（`director.ts:151-165`）只覆盖 patch 提供的易变字段；首幕由
  `<plan>.storyBible` 播种（`director.ts:564-573`）。
- 角色注册表：`mergeCharacters` 按 name 合并、保留旧 voice/portrait/persona
  （`director.ts:86-117`）。
- 四层治理：raw（`writer.ts:39-86` Raw* 类型）→ coerce（`coerceBeat` 175-206、
  `coercePlanFromRaw` 458-532、`coerceBeatsFromRaw` 540-582）→ repair（`ensureUniqueBeatIds`
  224-255、`repairBeats` 262-306 保证可逃离、`ensureUniqueChoiceIds` 312-326、`renameBeatId`
  389-408）→ fallback（`synthesizeFallbackBeats` 413-426、`minimalFallbackPlan`
  `director.ts:176-185`、StreamRouter degrade 207-244）。

**和 Storyloom 的对应**：
- **无状态 Session 往返 vs 本地 GameState**：这是两家最大的架构分叉。Storyloom 是
  **单应用本地真相源**（`exec-flow.md` §1.3："本地数据为唯一真相源"），存档落盘
  （`save_manager.py` 原子 JSON）；InfiPlot 是**客户端无状态 + 每次全量上传**（可水平扩展
  服务器，但传输/序列化成本高，且浏览器是唯一真相源）。Storyloom 的取舍更适合单机引擎。
- **双层 StoryState** ≈ Storyloom 的 **outline（大纲，稳定）+ state_vars（状态变量，易变）**
  分离（`data-model.md`）：storyBible ≈ 大纲/故事设定不可改写，易变区 ≈ 状态变量每轮 patch。
- **四层治理 raw→coerce→repair→fallback** ≈ Storyloom 的两级错误处理
  （`exec-flow.md` §4.1.1：严重=用户决策 / 普通=程序内部处理）+ 格式错误反馈循环。
  差异：InfiPlot 当场修复降级（coerce/repair/fallback 全自动），Storyloom 把普通错误
  **反馈给 LLM 下轮自纠**（`format_errors` → prompt 追加）。InfiPlot 更"自动驾驶"、
  容错更强，Storyloom 更"教学式"、模型收敛更好——可对比取舍。
- mergeCharacters 按 name 合并 ≈ Storyloom 的 `GameAssetRoster` 按 local_name 注册
  （`assets/_roster.py:21`），都是"名称 → 实体"注册表 + 保留旧字段。

### 3.4 与 Storyloom 的机制对照表

| 维度 | InfiPlot | Storyloom |
|------|---------|-----------|
| 重叠粒度 | 场景级：阅读一幕 = 生成所有下一幕分支（`page.tsx:2008-2036`） | 轮内流式 + bridge 确定路径预取（`game_loop.py:929-966`） |
| 预生成策略 | 全枚举无概率（L1）+ 必经节点前视 L2/L3（`page.tsx:408-503`） | 单一确定路径（bridge 衔接） |
| 成本控制 | ❌ 无预算/概率控制，服务端不可取消（`page.tsx:431`、`chat.ts:174-180`） | ✅ 单次预取，成本恒定 |
| 文本流式 | ❌ SSE 未接线，打字机（`engineClient.ts:111-174` vs `PlayCanvas.tsx:37-107`） | ✅ 真流式逐行（`stream_parser.py:177`） |
| 多智能体 | Writer/CharacterDesigner/Cinematographer/Painter（Promise DAG，`director.ts`） | 导演 LLM + 匹配/生成 AI（`design.md` §5），TaskPool 并发 |
| 格式治理 | 四层 raw→coerce→repair→fallback（`writer.ts`） | 两级错误处理 + 反馈循环（`exec-flow.md` §4.1.1） |
| 状态真相源 | 客户端 Session 全量往返（`types/index.ts:367-415`） | 本地 GameState + 存档（`save_manager.py`） |
| 素材一致 | 参考图闭环 img2img（`director.ts:128-143`） | 曾启用后禁用（`GENERATE_REF_IMAGE_COUNT` 3→0） |
| 首幕启动 | 预烘焙卡 `?card=`（`page.tsx:1699`） | 共创预构建素材（`design.md` §5.3） |

**价值评级**：高。场景级重叠的教科书实现，但文本流式/概率预取/跨会话缓存三项恰好是
Storyloom 的立足点。

---

## 4. 三种"藏等待"路线 vs Storyloom：总对照

把三家的核心机制放在一张图上，看它们各自在"实际等待 = TTFT + 素材剩余 − 消费覆盖"
（`first-principles.md` 核心方程）里动了哪一项：

| 项目 | 路线 | 压缩的项 | 未解决的项 | 一句话本质 |
|------|------|---------|-----------|-----------|
| **Storyloom** | 流式 + bridge 重叠 | TTFT（流式）+ 跨回合生成（bridge 消费覆盖）+ 素材（异步任务池） | 缓冲不足时的差额等待 | **结构性消除轮内/轮间等待** |
| **InfiPlot** | 分支枚举预生成 | 场景切换等待（阅读一幕 = 生成所有下一幕） | 文本首展示（假流式）、预生成成本膨胀、自由输入冷启动 | **消费当前幕覆盖生成所有分支** |
| **Ars Fabula VN** | 回合内流式 + 缓冲 | 回合内首行等待（TTFT 即显示） | 回合间硬等待、素材同步阻塞 | **压缩轮内等待，不消除轮间等待** |
| **Ephemeral Hearts** | 两阶段 + 缓存回避 | 图像阶段（缓存命中 ≈0ms）+ 文本先行 | LLM 全程阻塞（非流式）、无跨回合重叠 | **让生成尽量不发生（缓存）+ 文本先行** |

四个项目都遵守同一个哲学（LLM 提议、程序裁决），差异全在"怎么处理生成时间"上——
这反向印证了 Storyloom 的公理推导：**只要延迟存在、交互存在不确定性，就必须有某种形式的
重叠，只是各家重叠的维度不同**（Storyloom 轮内轮间、InfiPlot 场景分支、Ars Fabula 轮内
文本流、EH 回合内文本/图像两阶段）。

### 各项目在"三层流与双队列"上的位置

```
生成（AI）→ 处理（程序）→ 消费（用户）
```

| 项目 | 层间解耦情况 |
|------|-------------|
| Storyloom | 完整三层 + 双队列（Token/Task/UI Event Queue，`design.md` §3.3） |
| InfiPlot | 有生成/消费重叠（场景粒度），但客户端无真流式 → 生成→处理间无队列缓冲 |
| Ars Fabula | 生成→消费有行缓冲（`vn_engine.py:135-168`），无跨回合队列 |
| Ephemeral Hearts | 两阶段调用间靠落盘文件衔接（ZeroGPU），无内存队列 |

---

## 5. 结论：可借鉴项与需警惕项（带 Storyloom 落地提示）

### 5.1 值得借鉴（按优先级，源自分析报告 §6.3 + 本文代码级确认）

1. **grammar 约束解码**（Ephemeral Hearts，`llm.py:81-99`）：把 `<story>` XML 格式可靠性
   从"prompt 规范 + 事后反馈"提升到"解码层禁止非法"。落地提示：OpenAI 兼容 API 用
   `response_format` 类约束，本地 llama.cpp 路径可用 GBNF 完整落地。
2. **验证器驱动的自举微调闭环**（Ars Fabula，`trace_log.py` + `vn_validate.py:22-23`）：
   把 `StreamParser` 复用为训练数据质量闸门（运行时 trace → 校验 → SFT → 同校验器评估）。
3. **参考图闭环**（InfiPlot，`director.ts:128-143` + `painter.ts:91-93`）：模型提速后可恢复
   Storyloom 曾禁用的 `GENERATE_REF_IMAGE_COUNT`，参考其 `referenceImages` ≤4 张 + slot 优先级。
4. **TTS/STT 语音链路**（Ephemeral Hearts，`tts.py:117-136`）：按角色冻结音色。
5. **prompt 前缀字节稳定性**（InfiPlot，`context/index.ts:14-22` SENTINEL append-only）：
   Storyloom 的 Round 1 前缀永久锚定已是同思路，可补字节级保证。
6. **双请求竞速**（InfiPlot，`painter.ts:153-224`）：需配预算控制，仅对关键素材启用。
7. **mock-first 出厂模式**（Ephemeral Hearts，`config.py:42`）：零模型可跑通全循环，
   可借鉴为 Storyloom 的演示/自测模式。
8. **数据层**（ArtiMeow，浅析）：增量知识库协议 + 检查点回档"移动而非删除"。

### 5.2 需警惕（反向参照，源自分析报告 §6.4）

1. **全枚举预生成的成本膨胀**（InfiPlot）：无概率加权 + 服务端不可取消 → 分支数线性成本。
   若做分支级预生成，必须配预算上限与服务端取消（`page.tsx:431` 不传 signal 是反面教材）。
2. **假流式**（EH / InfiPlot）：打字机掩盖"首展示 = 完整生成"。前端渐进效果必须有后端真流式支撑。
3. **素材僵硬**（Ars Fabula）：全量预生成数分钟或同步阻塞 120s 都不可取；
   "选择优先于生成 + 异步任务池"（Storyloom TaskGenerator）是正解。
4. **"预测式"的诚实性问题**（InfiPlot）：营销声称 vs 实现真相（枚举非预测）——
   Storyloom 对外表述应保持"桥接/重叠"的准确语义。

### 5.3 一句话总结

> 三家竞品分别用**场景枚举**（InfiPlot）、**轮内流式缓冲**（Ars Fabula）、**缓存回避**（EH）
> 在各自维度隐藏等待，哲学同源（LLM 提议、程序裁决）但都不具备 Storyloom
> "**轮内流式解析 + bridge 标记驱动预取 + 素材异步管线**"的组合——竞品没有一家把
> "生成与消费重叠"做到轮内结构性实现，这正是 Storyloom 的差异化立足点。

---

## 附录：三家仓库的关键文件索引（快速跳转）

| 项目 | 关键文件 | 内容 |
|------|---------|------|
| Ars Fabula VN | `model_client.py` | SSE 流式客户端、VRAM 编排 |
| | `vn_engine.py` | 行缓冲切行、DSL 解析、cast-lock、回合主循环 |
| | `vn_validate.py` | 校验器（复用引擎解析器） |
| | `vn_prompt.py` | 格式契约、滑动窗口 prompt |
| | `providers.py` | 背景图生成（同步阻塞 120s） |
| Ephemeral Hearts | `visualnovel/llm.py` | 阻塞调用 + grammar 约束解码 |
| | `visualnovel/state.py` | apply_directives 唯一 mutator |
| | `visualnovel/painter.py` | sha1 磁盘缓存、seed 固定 |
| | `visualnovel/engine.py` | 两阶段回合（turn_text / turn_images） |
| | `frontend/index.html` | 前端打字机、busy 锁 |
| InfiPlot | `app/[locale]/play/page.tsx` | 预生成触发/算法/缓存键/abort、图片预取、预烘焙卡 |
| | `lib/engine/director.ts` | 多智能体 Promise DAG、plan 解锁、mergeCharacters |
| | `lib/engine/stream/index.ts` | StreamRouter 标签状态机 |
| | `lib/engine/agents/painter.ts` | 双请求竞速、参考图 |
| | `lib/engineClient.ts` | fetchSSE（未接线） |
| | `lib/types/index.ts` | Session / StoryState 双层结构 |




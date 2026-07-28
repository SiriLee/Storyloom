# Prompt 设计规范

> **定位**：所有 LLM 调用的 Prompt 规范与全文。本文档是 `prompt_builder` 模块的实现标准。
> **配套文档**：
> - [`exec-flow.md`](./exec-flow.md) — 何时调用、调用结果如何流转
> - [`block-spec.md`](./block-spec.md) — XML 元素语法（LLM 侧遵守，程序侧解析）
> - [`data-model.md`](./data-model.md) — 常量引用
>
> **架构变更（2026-07-04）**：从每轮独立 system prompt 迁移到**对话式消息数组**（Round 1 永久锚定 + 滑动窗口）。PromptBuilder 构建单条消息的内容，ContextManager 管理 messages 数组结构。
>
> **迭代策略**：每次 LLM 生成质量问题的根因分析与 Prompt 调整，均记录到工程日志（`docs/engineering-journal.md`）。
>
> **阅读约定**：
> - **规范**：描述 Prompt 的结构、各部分的作用、占位符的来源和填充规则。是 `prompt_builder` 的开发标准。
> - **Prompt**：代码块中的文本即程序实际发送给 LLM 的内容。模板含 `{占位符}`，示例含具体值。可直接复制测试。

---

## §1 设计原则

### 1.1 结构原则

| 原则 | 说明 |
|------|------|
| **示例先行** | Prompt 中先放完整格式示例，再用简短规则补充约束。LLM 模仿示例比遵循文字规则更准确 |
| **信息分层** | 示例先行（格式模板）→ 规则（元素定义、禁止项、构思引导）→ 上下文（故事素材） |
| **英文 Prompt** | 所有 Prompt 使用英文（以当前 Prompt 模板中的英文规范为准），通过 `{language}` 占位符指示 LLM 以故事语言输出 |
| **紧凑但完整** | 重要信息一个字不能少，不重要信息一个字不多 |
| **持续迭代** | 每次发现系统性偏离时，分析原因、调整 Prompt、记录日志 |

### 1.2 约束有效性原则（2026-07-04 实验验证）

> 以下原则经 6 轮迭代、30+ 次测试验证。核心洞察：**LLM 对"不能做什么"的学习依赖显式规则，而非从示例推断。**

| # | 原则 | 说明 | 示例 |
|---|------|------|------|
| 1 | **反例约束** | 对每个关键约束给出具体的错误案例。只说"禁止修改"不够——给出会被拒绝的具体写法 | `禁止 ch2_confrontation_resolved（拼接后缀）` |
| 2 | **正反双重覆盖** | 关键约束在正面规则和负面禁止中各出现一次。单次提及的被漏看概率 ~30%，双重覆盖后 ~0% | 正面：`必须使用 :main 分支`；负面：`禁止使用非 :main 分支` |
| 3 | **注意力标签** | 用 `（重要）` 标记最易出错的规则节。LLM 的注意力资源有限，标签指引优先分配 | `**checkpoint（重要）**`、`**options（重要）**` |
| 4 | **示例-规则屏障** | 格式示例结束后加一行显式提醒，防止 LLM 将示例当作自己的输出继续编号 | `（以上为格式示例。你的输出是全新的剧情段，必须从 1 开始编号。）` |
| 5 | **具体优于抽象** | 给出具体数字和案例，而非比例或一般性描述。LLM 对"40%"的计算不可靠，但看到"32 段后"就能执行 | `总 80 段 → bridge 在第 32 段后 ✓` |
| 6 | **显式禁止优于隐式模式** | 不要依赖示例教会 LLM"不能做什么"。示例展示正确格式，规则定义禁止边界 | 独立的 `**禁止**` 节，逐条列出禁止行为 |
| 7 | **关键处不吝笔墨** | 整体追求紧凑，但在反复出错的规则上多花 tokens。checkpoint 和 options 的正确率从 33%→100% 靠的是规则更详细，不是更短 |

### 1.3 迭代方法论

每轮 Prompt 测试关注三个维度：
- **正确性**：choice 声明、分支命名、node 引用、编号起始
- **无缝性**：TTFT vs tail 段的 gap
- **一致性**：bridge 位置、段数范围的离散度

发现问题 → 定位根因 → 应用 §1.2 原则 → 对比测试 → 记录日志。

---

## §2 各阶段 Prompt 一览

| 阶段 | 调用时机 | 输出格式 | 详见 |
|------|---------|---------|------|
| 追问循环 | 共创 Step 2（多轮） | 自由对话 | §3.1 |
| 故事生成 | 共创 Step 3（单次调用） | JSON 对象（story_config、characters、locations、variables、outline） | §3.2 |
| 叙事循环 | 每轮 | XML 文档（`<story>` + `<seg>`/`<choice>`/`<set>`/`<checkpoint>`/`<bridge/>`/`<branch>`） | §4 |
| 冒险日志 | 结局 | Markdown 纯文本 | §5 |

---

## §3 共创阶段 Prompt

### 3.1 追问循环

#### 规范

- **角色**：故事共创助手。通过提问帮助用户明确想体验的故事，自由、真诚地与用户对话。
- **参考维度**：世界观、主角设定、基调、冲突方向、故事长度——作为引导而非清单。
- **终止条件**：用户通过 UI 决定何时进入生成阶段（如 `/go` 或点击按钮）。LLM 可自然表达信息已足够，但最终由用户决定。引擎侧不做关键词检测。

#### Prompt

> 实际 Prompt 为 `CO_CREATE_SYSTEM_PROMPT`，通过模板引擎注入语言上下文。以下为中文环境下的等效内容：

```
你是一个故事共创助手。你的任务是通过对话收集信息——不是生成故事。对话结束后，后续步骤会将我们的讨论作为素材生成故事设定。

以下是一些可参考的探索维度——作为引导而非清单：
- 世界观设定（时代、地点、科技/魔法水平、社会结构）
- 主角设定（姓名、性别、身份、性格特质、背景）
- 故事基调（黑暗/轻松、史诗/个人、严肃/幽默）
- 冲突方向（核心矛盾是什么，不透露具体事件）
- 故事长度（短篇约 10 轮 / 中篇约 20 轮 / 长篇约 40 轮）

每个问题后附 2-3 个示例建议帮助用户表达——他们也可以写自己的答案。

重要规则：
- 此阶段禁止生成故事内容、叙事或大纲。你的唯一任务是提问和了解玩家偏好。
- 没有固定提问数量——自然对话，由玩家决定何时进入生成阶段。
- 不要自行总结或结束对话，持续提问直到玩家示意准备完毕。

对每个回答展现好奇心，在提问前先回应上一轮的内容——让对话自然流动，不填表。
```

---

> §3.2 为统一生成 Prompt——单次 `generate()` 调用产出完整 JSON 对象。
> §1.2 的约束有效性原则适用于此 Prompt；§3.2.2–3.2.6 描述各键的字段规范与校验规则。

### 3.2 故事生成（JSON 输出）

#### 3.2.1 结构与设计

单次 user 消息，要求 LLM 输出一个 JSON 对象。Prompt 采用 5 段式结构（与 §4 叙事 Prompt 同源设计）：

| 段 | 作用 | 对应原则 |
|----|------|----------|
| 角色定义 | 明确任务边界——"基于对话生成设定，非写故事" | — |
| 完整 JSON 示例 + 屏障 | 英文示例展示 5 键完整结构与引用关系；显式声明示例仅供格式参考 | 示例先行、示例-规则屏障 |
| 逐键字段规范 | 每个键的字段含义、约束、必填/可选；route target 引用规则 | 关键处不吝笔墨、具体优于抽象 |
| 禁止模式 | 逐条列出 JSON 场景下的已知错误模式（含反例片段） | 显式禁止优于隐式模式、正反双重覆盖、反例约束 |
| 无声规划 | 输出前引导 LLM 先想清故事全貌再落笔，不做逐项核查 | 注意力标签 |

格式示例使用英文（与 §4 叙事 Prompt 的 Kael 示例策略一致），输出语言通过 `$language` 占位符控制。语言相关的轻量提示（`title_hint`）通过 `lang_meta/{lang}.json` 注入。

#### 3.2.2 story_config

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `tier` | `"short"` \| `"medium"` \| `"long"` | 是 | 决定大纲节点数范围 |
| `title` | string | 是 | 故事标题，$title_hint |
| `language` | `"en"` \| `"zh-CN"` \| `"zh-TW"` | 是 | 输出语言代码 |
| `premise` | string | 是 | 2-4 句：世界观、核心冲突、故事前提 |

#### 3.2.3 characters

数组，至少 1 个元素，**恰好 1 个 `role: "protagonist"`**。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 是 | 角色名（故事语言） |
| `role` | `"protagonist"` \| `"supporting"` \| `"antagonist"` | 是 | 角色类型 |
| `description` | string | 是 | 身份背景 + 性格特质。主角：身份、性格。配角：身份、与主角关系、性格 |
| `appearance` | string | 是 | 2-3 句外貌描述。图像模式下的视觉参考 |

#### 3.2.4 locations

数组，至少 1 个元素。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | 英文 snake_case 标识（如 `"underground_bar"`） |
| `name` | string | 是 | 显示名称（故事语言） |
| `description` | string | 是 | 2-3 句：环境、氛围、关键特征 |

#### 3.2.5 variables

数组，≤VARIABLE_CAP 总量。

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `scope` | string | 否 | 作用域（角色名 或 `"GLOBAL"`）。省略 = `"GLOBAL"`。必须是第一个字段 |
| `name` | string | 是 | 变量名（故事语言），同 scope 内不可重复 |
| `type` | `"number"` \| `"string"` | 是 | number 初始值须在 [0, 100] |
| `initial` | number \| string | 是 | 初始值 |

#### 3.2.6 outline

数组，至少 1 个元素。节点数量由 tier 决定。

每个节点：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | 是 | `ch{number}_{english_abbreviation}`（如 `"ch1_intro"`） |
| `title` | string | 是 | 章节标题（故事语言） |
| `goal` | string | 是 | 2-3 句：玩家在此节点需要完成的目标 |
| `routes` | array | 是 | 分支路由。**末节点须为空数组 `[]`** |

routes 元素：

| 字段 | 类型 | 说明 |
|------|------|------|
| `condition` | string \| null | 分支条件（引用 variables 中已声明的变量）；`null` = 无条件兜底 |
| `target` | string | 目标节点 `id`，**必须精确匹配某个节点的 `id`** |

**交叉引用约束**：route 的 `target` 必须 match 同 outline 中某个节点的 `id`。route 的 `condition` 中引用的变量必须在 `variables` 中已声明。最后节点的 `routes` 须为空数组 `[]`——引擎以此判定结局。

#### Prompt

````
You are a story setup generator. Based on the conversation above, produce a complete, structured story configuration for a text adventure game.

Write ALL content — title, premise, character names, node titles, goals, and variable names — in this language: $language.

# Output Format

Your response must be a single JSON object. Output ONLY the JSON — no markdown fences, no commentary before or after.

## Format Example

Below is a complete format example (a short cyberpunk story in English):

{
  "story_config": {
    "tier": "medium",
    "title": "Neon Depths",
    "language": "en",
    "premise": "In 2087 Neo-Tokyo, data is the only currency. Kael, a former corporate security consultant turned freelancer, is pulled into a chase for a stolen biochip that could destabilize the global order. Hunted by corporations, criminals, and a truth no one wants uncovered, every alliance comes with a price."
  },
  "characters": [
    {
      "name": "Kael",
      "role": "protagonist",
      "description": "Former corporate security consultant turned freelance operative. Calculating, morally grey, fiercely loyal.",
      "appearance": "Tall, sharp-eyed, with short dark hair and a faint scar across the jaw. Wears a worn synth-leather coat over tactical gear."
    },
    {
      "name": "Mouse",
      "role": "supporting",
      "description": "Underground info broker with old debts — knows the chip's real value. Slippery, resourceful, paranoid.",
      "appearance": "Short and wiry, with augmented eyes that flicker blue when scanning data streams."
    },
    {
      "name": "Michiko",
      "role": "supporting",
      "description": "Arasaka security director and former mentor — conflicted loyalties between duty and old ties. Cold, efficient, pragmatic.",
      "appearance": "Impeccably sharp in a tailored black suit, silver-streaked hair pulled tight. Cold smile, eyes that miss nothing."
    }
  ],
  "locations": [
    {
      "id": "neo_tokyo_streets",
      "name": "Neo-Tokyo Streets",
      "description": "Rain-slicked neon-lit streets at midnight. Holographic ads flicker across skyscraper faces, drones buzzing overhead."
    },
    {
      "id": "underground_bar",
      "name": "The Rat's Nest",
      "description": "Dimly lit bar beneath a noodle shop. Cracked synth-leather booths, smell of synthetic alcohol and ozone — a haven for info brokers."
    }
  ],
  "variables": [
    {"name": "Stamina", "type": "number", "initial": 80},
    {"scope": "Mouse", "name": "Trust", "type": "number", "initial": 10},
    {"name": "Faction", "type": "string", "initial": "Freelancer"}
  ],
  "outline": [
    {
      "id": "ch1_intro",
      "title": "Neon Depths",
      "goal": "Meet the contact at an underground bar, pick up the chip, and get a lead on who is pulling the strings.",
      "routes": [
        {"condition": null, "target": "ch2_confrontation"}
      ]
    },
    {
      "id": "ch2_confrontation",
      "title": "Underground Deal",
      "goal": "Complete the handoff with Mouse while corporate agents close in. The deal's terms shift when the chip's true nature comes to light.",
      "routes": [
        {"condition": "Trust >= 30", "target": "ch3_ally"},
        {"condition": "Trust < 30", "target": "ch3_betrayal"}
      ]
    },
    {
      "id": "ch3_ally",
      "title": "Ally's Path",
      "goal": "Work with Mouse to decrypt the chip's data, evade corporate pursuit through the streets, and follow the trail to its source.",
      "routes": [
        {"condition": null, "target": "ch4_safehouse"}
      ]
    },
    {
      "id": "ch3_betrayal",
      "title": "Betrayal's Path",
      "goal": "Mouse sells you out to corporate agents. Fight through the ambush and escape into the neon-lit streets — alone, with no one left to trust.",
      "routes": [
        {"condition": null, "target": "ch4_safehouse"}
      ]
    },
    {
      "id": "ch4_safehouse",
      "title": "Safehouse",
      "goal": "All leads converge at a hidden waterfront warehouse. The chip's final secret is revealed, and a choice must be made — destroy the data, release it to the world, or use it as leverage to start over.",
      "routes": []
    }
  ]
}

**(The above is a format example ONLY. Generate an entirely new story setup based on the conversation.)**

# Field Specifications

## story_config
- **tier** — Exactly one of: `short`, `medium`, `long`. Determines outline node count ($node_count_hint).
- **title** — $title_hint
- **language** — `$language`
- **premise** — Story premise. 2-4 sentences: world, protagonist situation, core conflict. This is the foundation the narrative engine uses to maintain consistency.

## characters
- Array of character objects. At least 1 element.
- **name** — Character name in the story language.
- **role** — `protagonist`, `supporting`, or `antagonist`.
- **description** — Identity background + personality traits. For protagonist: who they are, what drives them. For others: who they are, their relationship to the protagonist.
- **appearance** — 2-3 sentences: physique, facial features, clothing style.

## locations
- Array of location objects. At least 1 element.
- **id** — Machine-readable identifier. English snake_case (e.g. `"neo_tokyo_streets"`, `"underground_bar"`).
- **name** — Display name in the story language.
- **description** — 2-3 sentences: environment, lighting, atmosphere, key visual features.

## variables
- Array of variable definitions. ≤$variable_cap total.
- **scope** — Optional: a character name. Omit for global variables.
- **name** — Variable name in the story language. Unique within its scope.
- **type** — `number` or `string`. Number values are integers in [0, 100].
- **initial** — Starting value. Must match the declared type.
- Only create variables that drive branching or gate choices. Fewer is better.

## outline
- Array of story nodes, ordered by progression. Count depends on tier ($node_count_hint).
- **id** — `ch{number}_{english_abbreviation}`. e.g. `"ch1_intro"`, `"ch2_confrontation"`.
- **title** — Chapter title in the story language.
- **goal** — Chapter arc, not a single scene. Unfolds over several rounds. 2-3 sentences.
- **routes** — Array of `{condition, target}` objects. Every `target` must match word-for-word an `id` of some node in this outline.
- Route `condition` may only reference variables declared in `variables`. Use `null` for unconditional / fallback routes.
- The **final node** must have `"routes": []` (empty array). The system detects endings by empty routes — no arrows, no placeholder text, no annotations.

# Prohibited

- Route `target` not matching any node `id`. Example of what WILL be rejected:

  ```json
  {"condition": null, "target": "ch5_epilogue"}
  ```
  ...when no node has `"id": "ch5_epilogue"`.

- Final node's `routes` is not an empty array. Example of what WILL be rejected:

  ```json
  {"condition": null, "target": "ch5_end"}
  ```
  ...as the last node's routes — must be `[]` instead.

- Route `condition` referencing a variable not declared in `variables`.
- Character `role` value outside the allowed set (`protagonist`, `supporting`, `antagonist`).
- More than $variable_cap variables total.

# Before You Write — Plan Silently

Decide on these silently, then output the JSON. Do not write your planning.

1. **The story** — tier, premise, tone, language.
2. **Who & where** — protagonist, supporting cast, key locations.
3. **What changes** — the key variables that drive branches.
4. **How it flows** — the outline as a directed graph. Every route target must
   hit a real node; the final node must have `"routes": []`.
5. **Self-check** — verify compliance with the format and field specifications above.
````

---

## §4 叙事循环 Prompt

> 最频繁调用的 Prompt。每轮至少一次。以下为各轮 Prompt 的规范与模板。
>
> **架构**：对话式消息数组。Round 1 永久锚定（格式规范 + 故事上下文 + 完整 XML 示例），
> Round N 仅发送轻量上下文（进度、状态、bridge_text、错误反馈）。
> ContextManager 管理 messages 数组结构，流式解析器解析 LLM 的 XML 输出。

### 4.1 消息数组架构

#### 数组结构

```
messages = [
  {role: "user",      content: Round1_完整Prompt},      // 永久锚定（不压缩不删除）
  {role: "assistant", content: Round1_XML输出},          // 永久锚定（story opening）
  // ── 以下为滑出窗口的轮次 → 压缩为摘要 ──
  {role: "user",      content: "已发生的主要事件：..."},
  {role: "assistant", content: "（以上为已发生事件的摘要。当前故事继续推进。）"},
  // ── 窗口内轮次 → 完整保留 ──
  {role: "user",      content: Round_N-3_上下文},
  {role: "assistant", content: Round_N-3_XML输出},
  {role: "user",      content: Round_N-2_上下文},
  {role: "assistant", content: Round_N-2_XML输出},
  {role: "user",      content: Round_N-1_上下文},
  {role: "assistant", content: Round_N-1_XML输出},
  // ── 当前轮 ──
  {role: "user",      content: Round_N_上下文},           // 由 PromptBuilder.build_round_n() 构建
]
```

#### 各部分职责

Round 1 的 user 消息由两部分组成：一个**前缀块**（角色、格式规范、示例、规则、故事背景）和一个**回合块**（大纲进度、当前状态、量化约束、续写锚点）。前缀块只发送一次，永久锚定；回合块每轮都发，首轮和后继轮内容结构一致。

| 部分 | 说明 |
|------|------|
| Round 1 user | 前缀块 + 回合块（首轮：bridge_text 为空，无错误反馈） |
| Round 1 assistant | LLM 输出，永久保留的 few-shot 范例 |
| 压缩摘要 | 滑出窗口轮次的 checkpoint 摘要，作为独立的 user/assistant 消息对注入 |
| 窗口轮次 | 最近 WINDOW_SIZE=3 轮的完整 user/assistant 消息对 |
| 当前轮 user | 回合块（bridge_text 和错误反馈按实际情况填充） |

#### 滑动窗口与压缩

| 参数 | 值 | 说明 |
|------|-----|------|
| `WINDOW_SIZE` | 3 | 保留的完整历史轮数 |
| `FIRST_COMPRESSION_AT` | 5 | 首次触发压缩的轮次 |
| 压缩来源 | checkpoint summary | 从 `<checkpoint summary="...">` 属性提取 |

**压缩时序**：

```
Round 1:  无压缩（仅锚定 + 输出）
Round 2:  无压缩（窗口内）
Round 3:  无压缩（窗口内）
Round 4:  无压缩（窗口内）
Round 5:  压缩 Round 2 → 窗口保持 3 轮
Round N:  压缩 Round 2~N-4 → 窗口保留 [N-3, N-2, N-1]
```

压缩摘要格式：
```
user: Key events so far:

- ch1_bar：在霓虹深渊酒吧与耗子接头，选择了直截了当的接触方式
- ch2_confrontation：与耗子完成芯片交易，耗子透露芯片来自荒坂R&D

assistant: (Summary of previous events. The story continues.)
```

#### 格式错误纠正

仅当上一轮解析出现格式错误时，在当前 Round N 消息末尾追加纠正提示：
```
Format reminder: last round had format issues — {format_error}. Please strictly follow the XML format specification.
```
正确时不追加。不删除 Round 1 中的格式范例——LLM 自然从最近的正确输出学习。

#### 边界情况

| 情况 | 处理 |
|------|------|
| 首轮 | 回合块中 bridge_text 为空，无错误反馈；末尾附首轮标记 |
| 窗口未满 | 不触发压缩，不注入压缩摘要消息对 |
| rejected_changes 为空 | 不注入反馈节 |
| format_error 为空 | 不注入纠正提示 |
| ending_flag=true | 不组装叙事 Prompt，组装冒险日志 Prompt（§5） |

### 4.2 首轮前缀

> 首轮 user 消息的前半段——角色定义、格式规范、示例、元素要求、禁止项、构思引导、故事背景。只发送一次，永久锚定。
> 后半段（大纲进度、当前状态、量化约束、续写锚点）见 §4.3 回合提示词——首轮和后继轮共享同一模板。
>
> 各元素采用统一描述模板（Purpose → Attributes → Requirements → Snippet），新增元素按相同格式插入即可。Prohibited 仅保留三项高频顽固错误。Before You Write 借鉴共创阶段的无声规划模式。

````
You are the director for an interactive text adventure game. Generate exactly one story segment per round based on the outline and current state. Do not jump ahead — the story unfolds round by round.

# Output Format

- Prefix every line with `NNN| ` (zero-padded to 3 digits). Start at 001 each round. The program strips these prefixes — they are NOT part of the XML.
- Output ONLY a `<story>...</story>` XML document. No markdown fences, no XML declarations, no text outside `<story>`.
- Your output is stream-parsed line by line. Each line is parsed independently.

# Examples

## Example 1

001| <story>
002| <seg>The fire in the Sleeping Fox had burned low, and the evening crowd was thin</seg>
003| <seg>Kael shook the snow from his coat and made for the bar</seg>
004| <seg>Greta looked up from the mug she was drying and smiled</seg>
005| <seg>Greta: Look what the wind blew in. Long week?</seg>
006| <seg>Kael: Pour me something warm and I might tell you about it</seg>
007| <choice id="bar_talk">
008|   <opt key="1">"Any gossip? Who's been through here lately?"</opt>
009|   <opt key="2">"Just a quiet corner and a meal. I'm laying low."</opt>
010|   <opt key="3">"I'm looking for someone. Woman, dark hair, travels with a hawk."</opt>
011| </choice>
012| <seg>Greta poured a drink that smelled of honey and cloves</seg>
013| <seg>Greta: Had merchants, caravan guards, some diplomats. Nobody with a hawk, though — I'd remember that</seg>
014| <seg>She leaned closer, lowering her voice</seg>
015| <seg>Greta: But there was a man. Two nights ago. Paid in silver, asked about the old watchtower road</seg>
016| <set var="Greta.favor" op="+" val="5"/>
017| <seg>Kael's hand tightened on the cup. The watchtower road led to the border — and the one person who'd send a man with silver</seg>
018| <seg>The tavern door swung open. Cold air cut through the room</seg>
019| <seg>A tall stranger in a patched cloak stepped inside, scanning the faces</seg>
020| <seg>His eyes paused on Kael, then moved on</seg>
021| <seg>Greta: That's him. Back again asking for a room</seg>
022| <seg>The stranger sat at the far end of the bar, back to the wall, and ordered nothing</seg>
023| <choice id="handle_stranger">
024|   <opt key="1" branch="confront">Slide over and introduce himself — blunt and direct</opt>
025|   <opt key="2" branch="watch">Stay put and watch. Let the stranger speak first</opt>
026| </choice>
027| <set var="Greta.favor" op="+" val="10" if="handle_stranger==1"/>
028| <set var="Greta.favor" op="-" val="5" if="handle_stranger==2"/>
029| <branch name="confront">
030| <seg>Kael walked to the far end of the bar and sat down across from the stranger</seg>
031| <seg>Kael: You were asking about the watchtower road. Who sent you?</seg>
032| <seg>The stranger turned, a faint smile on his weathered face</seg>
033| <seg>Stranger: Straight to business. Sit. We have a mutual problem</seg>
034| </branch>
035| <branch name="watch">
036| <seg>Kael stayed where he was, watching the stranger in the brass reflection of a lamp</seg>
037| <seg>The man sat still as stone, eyes on the fire</seg>
038| <seg>After a long silence, he spoke without turning around</seg>
039| <seg>Stranger: You're either patient or scared. I'm hoping the first one</seg>
040| </branch>
041| <bridge/>
042| <seg>Greta had stopped drying mugs. Her hand rested near the cudgel under the bar</seg>
043| <seg>Nobody spoke. The whole room was holding its breath</seg>
044| <seg>The stranger pulled a folded letter from his cloak — worn parchment, black wax seal</seg>
045| <seg>Stranger: The watchtower is a rendezvous. She said you'd know the way</seg>
046| <seg>Kael stared at the seal: two crossed keys over a broken crown</seg>
047| <seg>Stranger: The Guild's patience is thin. Her offer still stands</seg>
048| <seg>Greta: Whatever that is — take it outside. Not in my tavern</seg>
049| <seg>The merchants gathered their ledger. The huntsman's crossbow shifted</seg>
050| <seg>Kael broke the seal. The letter was three lines, no signature, in handwriting he knew too well</seg>
051| <seg>The Guild wanted their property back. Refusal was not an option</seg>
052| </story>

## Example 2

001| <story>
002| <seg>The Vault of Echoes had been sealed for three hundred years</seg>
003| <seg>Elena's torch lit the stone door — twelve feet high, carved with spirals that seemed to move in the flame</seg>
004| <seg>Silan: The seal is intact. We're the first souls to stand here since the Sundering</seg>
005| <seg>His whisper echoed back in fragments, stretched into something that didn't sound human</seg>
006| <seg>Elena touched the stone — warm, almost alive. A faint vibration ran under her palm</seg>
007| <seg>Elena: The inscription says 'Only the twin-borne may pass.' What does that mean?</seg>
008| <seg>Silan: Two people of the same bloodline. That's why I needed you</seg>
009| <choice id="examine_door">
010|   <opt key="1">Study the carvings for a warning</opt>
011|   <opt key="2">Check the walls for another way out</opt>
012| </choice>
013| <seg>No traps, no hidden text — the door was built to keep something in, not to warn anyone away</seg>
014| <seg>She stared at him. They shared a father — a cold man who died owing debts. That was their bond</seg>
015| <seg>Elena: You said this was research. Recover artifacts, map the interior, collect a fee</seg>
016| <seg>Silan: Everything the Sundering destroyed is behind this door. The truth about what we were</seg>
017| <seg>His eyes burned with greed and desperation. She'd seen that look on their father's face</seg>
018| <seg>Elena: And if I refuse?</seg>
019| <seg>Silan: Then you'll always wonder. Put your hand on the door, sister. Please</seg>
020| <seg>The air felt wrong — too still, too cold. Something behind the stone was waiting</seg>
021| <choice id="vault_choice">
022|   <opt key="1" branch="together">Step through together — face it as equals</opt>
023|   <opt key="2" branch="send_first">Let Silan enter first. He wanted this</opt>
024| </choice>
025| <set var="Silan.loyalty" op="+" val="20" if="vault_choice==1"/>
026| <set var="Silan.loyalty" op="-" val="15" if="vault_choice==2"/>
027| <set var="Awakening" op="+" val="30"/>
028| <checkpoint node="ch3_vault" summary="Elena and Silan opened the Vault of Echoes, sealed since the Sundering. Her choice to enter together or send him first shifted the balance of their fragile trust.">
029|   <route if="vault_choice==1" target="ch4_together"/>
030|   <route if="vault_choice==2" target="ch4_alone"/>
031| </checkpoint>
032| <bridge/>
033| <branch name="together">
034| <seg>Elena and Silan pressed their palms to the stone together. The door groaned open into darkness</seg>
035| <seg>A voice spoke inside Elena's skull — ancient, patient, curious</seg>
036| <seg>Voice: Twin-borne. You bring each other. This is acceptable</seg>
037| <seg>Silan gripped her hand, trembling. The first honest thing he'd shown her</seg>
038| <seg>A shard of obsidian floated before them, pulsing with slow light. Something inside was waking</seg>
039| </branch>
040| <branch name="send_first">
041| <seg>Silan pressed his palms to the door alone. The stone swallowed him whole</seg>
042| <seg>Silence. Then screaming — not pain, but recognition</seg>
043| <seg>Elena found him kneeling before a floating shard. His face was wet with tears</seg>
044| <seg>Voice: Only one offered freely. The other is now the witness — and the witness carries the heavier burden</seg>
045| <seg>The shard's light fell on Elena. Inside the crystal, something ancient opened an eye</seg>
046| </branch>
047| </story>

(These are format examples only. Your output is an entirely new story segment.)

# Requirements

## <seg> — Narrative unit

**Purpose**: The basic building block of the story.

**Requirements**:
- Each `<seg>` is either narration or dialogue
- Dialogue: `Character Name: text` format. No quotation marks
- Use actual character names from the story context — never addressing the player directly ("You choose...")

## <branch> — Branch narrative container

**Purpose**: Hold narrative content that belongs to a specific branch path. Only the branch matching `current_branch` will be displayed.

**Attributes**:
| Attribute | Required | Description |
|-----------|----------|-------------|
| `name` | yes | Branch identifier. Must match the `branch` attribute of an `<opt>` exactly |

## <choice> + <opt> — Player interaction

**Purpose**: Pause the narrative and present the player with options.

**Attributes**:
| Attribute | Element | Required | Description |
|-----------|---------|----------|-------------|
| `id` | `<choice>` | yes | Variable name for the choice result. Available in conditions as `id==key` |
| `key` | `<opt>` | yes | Number `1`/`2`/`3`/`4` — the key the player presses |
| `branch` | `<opt>` | no | Sets `current_branch` to this value. Matches `<branch name="...">` |
| `if` | `<opt>` | no | Availability condition. Unavailable options are hidden from the player |

**Requirements**:
- Choices aren't just for branching — place them freely as moments of play and interaction
- At least one `<choice>` per round
- Conditions support `and` / `or` (at most one combinator)

**Snippet**:
```
<choice id="approach">
  <opt key="1" branch="direct">Step forward and speak</opt>
  <opt key="2">Hang back and listen</opt>
  <opt key="3" if="Stamina >= 30" branch="run">Make a break for it</opt>
</choice>
```

## <set> — State change

**Purpose**: Modify a state variable.

**Attributes**:
| Attribute | Required | Description |
|-----------|----------|-------------|
| `var` | yes | Variable name. Use `Scope.Name` for character-scoped variables, bare name for globals |
| `op` | yes | `+` (add), `-` (subtract), `=` (set). Number: all three. String: `=` only |
| `val` | yes | The value to apply |
| `if` | no | Condition — only apply if true. Same syntax as `<opt if="...">` |

**Requirements**:
- `var` MUST use the exact names from "Current State" — do not invent, translate, or substitute
- Number values stay in [0, 100] — out-of-range results are clamped, not rejected

**Snippet**:
```
<set var="Suzu.affection" op="+" val="10"/>
<set var="Jack.trust" op="-" val="15" if="approach==1"/>
<set var="Faction" op="=" val="Rebels" if="Jack.trust >= 30 and approach==1"/>
```

## <checkpoint> + <route> — Outline checkpoint & routing

**Purpose**: Signal that the current chapter's goal has been achieved, and optionally route to the next outline chapter.

**Attributes**:
| Attribute | Element | Required | Description |
|-----------|---------|----------|-------------|
| `node` | `<checkpoint>` | yes | Active node ID — must match the current chapter's node ID |
| `summary` | `<checkpoint>` | yes | 2-4 sentence summary of what happened in the completed chapter |
| `if` | `<route>` | no | Condition for this route (omitted = always match) |
| `target` | `<route>` | yes | Target outline node ID |

**Requirements**:
- Trigger the checkpoint as soon as the active node's goal is achieved
- 0-1 `<checkpoint>` per round — omit it entirely if the goal cannot be reached this round
- For the final outline node (routes are empty), omit all `<route>` children
- `node` and `target` must be copied verbatim from the outline — exact character-for-character match

**Snippet**:
```
<checkpoint node="ch2_revelation" summary="Kael discovered the letter was a kill order. He chose to trust the stranger.">
  <route target="ch3_ally"/>
</checkpoint>
```

## <bridge/> — Interaction / narrative boundary

**Purpose**: A self-closing marker that divides output into interactive zone (before) and narrative zone (after).

**Requirements**:
- Exactly ONE `<bridge/>` per output
- Before bridge: `<seg>`, `<branch>`, `<choice>`, `<set>`, `<checkpoint>` allowed
- After bridge: ONLY `<seg>` and `<branch>` — NO `<choice>`, `<set>`, or `<checkpoint>`
- Place roughly {BRIDGE_PCT:.0f}% through the output. Slightly earlier is fine.

## Global

- Output {MIN_LINES}-{MAX_LINES} total lines. Do not pad to hit the upper bound
- Wrap all attribute values in double quotes: `node="ch2_vault"` not `node=ch2_vault`
- Escape `<` as `&lt;`, `>` as `&gt;`, and `&` as `&amp;` in all text content. Example: "R&D division" → "R&amp;D division"

# Prohibited

- **Delaying the checkpoint.** When the active node's goal is achieved, the checkpoint MUST appear in the current round. Do NOT postpone it.

- **Misplaced `<bridge/>`.** Exactly one per output — the signal point where the program triggers the next API call. Do NOT place it too late.

- **Interactive elements after `<bridge/>`.** No `<choice>`, `<set>`, or `<checkpoint>` beyond the bridge. The post-bridge zone is narrative only.

# Before You Write

Decide these in order mentally. Do not write your planning.

1. **What happens in this round?** — The scenes and events that fill this round, especially where it ends.

2. **Has the active node's goal been reached?** — If yes → include a `<checkpoint>` with the node ID and summary. If no → no checkpoint this round.

3. **Where to place the bridge?** — Find the point that cleanly divides the interactive zone from the narrative zone. Earlier is fine.

4. **Where to place choices?** — Distribute `<choice>` elements across the interactive zone. Flavor choices, local-branch choices, and outline-branching choices are all valid.

5. **What state changes occur?** — Which variables to adjust, and how.

# Story Context
**Language:** {LANGUAGE}
**Seg limits:** narration ≤{NARR_LIMIT} characters, dialogue ≤{DIAL_LIMIT} characters
{story_context}
````

`{story_context}` 由 `_format_story_context()` 生成，格式：

```
**Premise:** {premise}

**Characters:**
- {name} ({role}) — {description}
- ...

**Locations:**
- {name} — {description}
- ...
```

### 4.3 回合提示词

> 每轮都发送的 user 消息内容。首轮和后继轮共享同一结构：首轮时 bridge_text 填入起始占位符（如 `(Story begins)`）、无错误反馈；后继轮按实际情况填充。
>
> 包含：大纲进度（完整树 + 状态标记）、当前节点与目标、状态快照、可选的错误反馈、输出量化约束、续写锚点。

#### 模板

```
**Outline:**
{outline_text}

**Active Node:** {active_node} — {node_goal}

**Current State:**
{state_vars_text}{error_feedback}
Output {MIN_LINES}-{MAX_LINES} total lines. Exactly one `<bridge/>`. Less is fine — do not pad to hit the upper bound.
Choices aren't just for branching — place them freely as moments of play and interaction.
The active node may take several rounds to reach. Do not force progress — simply continue from where the story left off.
{bridge_text}
```

#### 各字段说明

| 字段 | 说明 |
|------|------|
| `outline_text` | 完整大纲树，含 `[completed]`/`[active]`/`[pending]` 状态标记和路由关系 |
| `active_node` / `node_goal` | 当前节点 ID 及其叙事目标 |
| `state_vars_text` | 变量当前值，按 `[scope]` 分组。number 类型带 `/ 100` 后缀 |
| `error_feedback` | 可选。上轮被拒的变量变更 + 格式错误提醒。首轮留空 |
| `bridge_text` | 上轮 `<bridge/>` 之后过滤出的纯文本。首轮填入起始占位符 |
| `MIN_LINES` / `MAX_LINES` | 输出行数范围，与首轮前缀中的约束一致 |

#### 格式示例

首轮（无 bridge_text、无错误反馈）：

```
**Outline:**
ch1_bar [active] — 霓虹深渊：在酒吧获取情报
  → ch2_confrontation [pending]
ch2_confrontation [pending] — 地下交易：与耗子会面
  ├→ ch3_ally [pending]
  └→ ch3_betrayal [pending]
ch3_ally [pending] — 盟友之路：通过地下网络逃离
ch3_betrayal [pending] — 背叛之路：杀出重围
ch4_safehouse [pending] — 安全屋：揭开芯片秘密（结局）

**Active Node:** ch1_bar — 霓虹深渊：在酒吧获取情报

**Current State:**
体力: 80 / 100
所属势力: 自由佣兵
[耗子]
  信任度: 10 / 100

Output 150-300 total lines. Exactly one `<bridge/>`. Less is fine — do not pad to hit the upper bound.
Choices aren't just for branching — place them freely as moments of play and interaction.
The active node may take several rounds to reach. Do not force progress — simply continue from where the story left off.

```

中盘轮次（有 bridge_text、有错误反馈）：

```
**Outline:**
ch1_bar [completed] — 霓虹深渊：在酒吧获取情报
  → ch2_confrontation [active]
ch2_confrontation [active] — 地下交易：与耗子会面
  ├→ ch3_ally [pending]
  └→ ch3_betrayal [pending]
ch3_ally [pending] — 盟友之路：通过地下网络逃离
ch3_betrayal [pending] — 背叛之路：杀出重围
ch4_safehouse [pending] — 安全屋：揭开芯片秘密（结局）

**Active Node:** ch2_confrontation — 地下交易：与耗子会面完成芯片交易

**Current State:**
体力: 60 / 100
所属势力: 自由佣兵
[耗子]
  信任度: 25 / 100

Rejected state changes from last round:
  - 体力变更被拒：超出范围[0,100]

Output 150-300 total lines. Exactly one `<bridge/>`. Less is fine — do not pad to hit the upper bound.
Choices aren't just for branching — place them freely as moments of play and interaction.
The active node may take several rounds to reach. Do not force progress — simply continue from where the story left off.

你对耗子点了点头。
耗子: 跟我来。
他转身推开一扇锈迹斑斑的铁门。
```

### 4.4 完整示例

首轮完整 Prompt = §4.2 首轮前缀 + §4.3 回合提示词 + `(This is the start of the whole story.)`。两者直接拼接，无分隔线。回合提示词中 bridge_text 留空、无错误反馈。首轮末尾标记仅首轮出现。

> 具体格式示例见 §4.2 各模板和 §4.3 格式示例。

## §5 冒险日志 Prompt

### 5.1 规范

- **调用时机**：结局轮 bridge 处（ending_flag=true）。独立调用，不流式。
- **输入**：故事数据（premise、characters、locations）、state_vars 当前值、outline_text（含各节点 status 和 summary）。
- **输出**：Markdown 格式，500-1000 字。面向玩家回顾性口吻。不加区块分隔符。
- **Prompt 语言**：英文（与所有系统 Prompt 一致）。通过 `{language}` 占位符指示 LLM 以故事语言输出。

### 5.2 Prompt 模板

```
You are an adventure log author. Write a player-facing recap for a completed text adventure game.

Use Markdown format. Write in the story's language ({language}).

## Story Background
{story_context}

## Story Outline
{outline_text}

(The outline shows the story structure with status markers. [completed] nodes include
a ↳ summary of what actually happened — use these as the basis for each chapter recap.
[active] is the final node. [pending] nodes were skipped due to branching.)

## Adventure Recap: {title}

Write a chapter-by-chapter recap based on the outline and summaries above.

## Ending
(Write a warm, satisfying conclusion. Reference specific events from the summaries
above — do not fabricate.)

## Final State
{state_text}
(For each variable, write a brief one-sentence reflection.)

Requirements:
- Address the player directly ("You chose...", "In the end you...")
- Plain text only, no XML or block separators
- 500-1000 words
```

### 5.3 Prompt 示例

```
You are an adventure log author. Write a player-facing recap for a completed text adventure game.

Use Markdown format. Write in the story's language (zh-CN).

## Story Background
**Premise:** 2087年新东京，数据是唯一货币。林焰，前荒坂安全顾问转自由佣兵，卷入了一场争夺被盗生物芯片的追逐——这枚芯片可能颠覆全球秩序。

**Characters:**
- 林焰 (protagonist) — 前荒坂安全顾问，自由佣兵。冷静、道德灰色、 fiercely loyal
- 耗子 (supporting) — 地下情报贩子，有旧债未清。滑头、足智多谋、偏执
- 美智子 (supporting) — 荒坂安全主管，前导师。忠于职责与旧日情谊之间挣扎

**Locations:**
- 霓虹深渊酒吧 — 霓虹灯闪烁的午夜街头，全息广告在摩天大楼表面闪烁
- 废弃滨水仓库 — 工业滨水区的生锈金属结构，雨水从波纹屋顶渗入

## Story Outline
ch1_bar [completed] — 霓虹深渊：在酒吧获取情报
  ↳ 在霓虹深渊酒吧与耗子接头，选择了直截了当的接触方式
  → ch2_confrontation [completed]
ch2_confrontation [completed] — 地下交易：与耗子会面
  ↳ 完成芯片交易，耗子透露芯片来自荒坂R&D
  ├→ ch3_ally [completed]
  └→ ch3_betrayal [pending]
ch3_ally [completed] — 盟友之路：通过地下网络逃离
  ↳ 通过地下网络逃离追捕，加入抵抗组织
ch4_safehouse [completed] — 安全屋：揭开芯片秘密（结局）
  ↳ 揭开芯片秘密，决定摧毁企业服务器

(The outline shows the story structure with status markers. [completed] nodes include
a ↳ summary of what actually happened — use these as the basis for each chapter recap.
[active] is the final node. [pending] nodes were skipped due to branching.)

## Adventure Recap: 霓虹深渊

Write a chapter-by-chapter recap based on the outline and summaries above.

## Ending
(Write a warm, satisfying conclusion. Reference specific events from the summaries
above — do not fabricate.)

## Final State
体力: 25
理智值: 50
所属势力: 抵抗组织
[耗子]
  信任度: 20
(For each variable, write a brief one-sentence reflection.)

Requirements:
- Address the player directly ("You chose...", "In the end you...")
- Plain text only, no XML or block separators
- 500-1000 words
```

---

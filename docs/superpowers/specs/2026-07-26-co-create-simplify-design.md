# 共创阶段数据模型重构

> 状态：设计完成，待实现  
> 核心思想：共创 LLM 承担"剧作家"角色，输出人物、地点、事件三要素。LLM 直接输出 JSON，消除自定义解析中间层，输出格式即存档格式。

---

## §1 设计目标

| 目标 | 说明 |
|------|------|
| story_config 11 字段 → 4 字段 | 消除冗余，提升 LLM 生成正确率 |
| 角色抽离为独立集合 | characters 从 story_config 的字符串字段升级为结构化数组 |
| 新增 locations | 关键场景/地点定义。当前为文本描述，图像模式下提供视觉参考 |
| 氛围合并为 premise | `genre`、`setting`、`tone`、`conflict` 合并为一个 `premise` 字段 |
| label → title | 语义更自然 |
| JSON 输出 | LLM 直接输出 JSON，`json.loads()` 替代全部自定义解析逻辑。输出格式 = 存档格式，零转换 |
| 全链路更新 | 存档格式、Prompt 模板、解析器、校验器、下游消费方全部跟随新结构 |

---

## §2 预期 LLM 输出

生成阶段单次 LLM 调用产出一个 JSON 对象，包含 5 个顶层键：

```json
{
  "story_config": { … },
  "characters": [ … ],
  "locations": [ … ],
  "variables": [ … ],
  "outline": [ … ]
}
```

### 完整输出示例

```json
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
      "description": "Former corporate security consultant turned freelance operative",
      "appearance": "Tall, sharp-eyed, with short dark hair and a faint scar across the jaw. Wears a worn synth-leather coat over tactical gear.",
      "traits": "Calculating, morally grey, fiercely loyal"
    },
    {
      "name": "Mouse",
      "role": "supporting",
      "description": "Underground info broker. Uneasy ally with old debts — knows the chip's real value.",
      "appearance": "Short and wiry, with nervous hands and augmented eyes that flicker blue when scanning data streams. Dresses in layers of faded street fashion.",
      "traits": "Slippery, resourceful, paranoid"
    },
    {
      "name": "Michiko",
      "role": "supporting",
      "description": "Arasaka security director. Former mentor — conflicted loyalties between duty and old ties.",
      "appearance": "Impeccably sharp in a tailored black suit, silver-streaked hair pulled tight. Cold smile, eyes that miss nothing.",
      "traits": "Cold, efficient, pragmatic"
    }
  ],
  "locations": [
    {
      "id": "neo_tokyo_streets",
      "name": "Neo-Tokyo Streets",
      "description": "Rain-slicked neon-lit streets at midnight. Holographic ads flicker across skyscraper faces. Crowded walkways filled with augmented humans, drones buzzing overhead. The air smells of ozone and street food."
    },
    {
      "id": "underground_bar",
      "name": "The Rat's Nest",
      "description": "Dimly lit underground bar beneath a noodle shop. Flickering neon sign, cracked synth-leather booths, smell of synthetic alcohol and ozone. A haven for info brokers and mercenaries — nobody asks questions here."
    },
    {
      "id": "corp_tower",
      "name": "Arasaka Tower",
      "description": "Gleaming black glass monolith piercing the skyline. Sterile marble interiors, armed guards at every checkpoint, silent elevators. The air is filtered and cold. Every surface reflects someone watching."
    },
    {
      "id": "waterfront_warehouse",
      "name": "Abandoned Waterfront Warehouse",
      "description": "Rusted metal structure on the industrial waterfront. Inside: makeshift living quarters filled with salvaged tech, flickering monitors, and tangled cables. Rain leaks through the corrugated roof."
    }
  ],
  "variables": [
    {"name": "Stamina", "type": "number", "initial": 80},
    {"name": "Trust", "type": "number", "initial": 10},
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
```

---

## §3 各字段规范

### 3.1 story_config

| 字段 | 类型 | 说明 |
|------|------|------|
| `tier` | `"short"` \| `"medium"` \| `"long"` | 决定 outline 节点数量范围 |
| `title` | string | 故事标题，1-30 字符，用作存档目录名前缀 |
| `language` | `"en"` \| `"zh-CN"` \| `"zh-TW"` | 输出语言代码 |
| `premise` | string | 故事前提。2-4 句：世界观、主角、核心冲突。同时作为 LLM 参考素材和玩家可见的故事简介 |

### 3.2 characters（数组）

每个元素：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 角色名（故事语言） |
| `role` | `"protagonist"` \| `"supporting"` \| `"antagonist"` | ✅ | 角色类型 |
| `description` | string | ✅ | 身份介绍说明。主角：身份背景；其他角色：身份 + 与主角的关系 |
| `appearance` | string | ✅ | 外貌描述。2-3 句：体态、面容、着装风格。图像模式的角色立绘生成参考 |
| `traits` | string | ✅ | 2-3 个核心性格特质，逗号分隔 |

至少 1 个元素，其中恰好 1 个 `role: "protagonist"`。

### 3.3 locations（数组）

每个元素：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 机器引用标识，英文 snake_case（如 `"underground_bar"`） |
| `name` | string | ✅ | 显示名称（故事语言） |
| `description` | string | ✅ | 视觉描述。2-3 句：环境、光线、氛围、关键特征。图像模式下的画面生成参考 |

至少 1 个元素。

### 3.4 variables（数组）

每个元素：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 变量名（故事语言） |
| `type` | `"number"` \| `"string"` | ✅ | 变量类型 |
| `initial` | number \| string | ✅ | 初始值。number: [0, 100]；string: 非空 |

校验规则：≤3 总量、≤2 number、≤1 string。

### 3.5 outline（数组）

每个元素（节点）：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 节点 ID，格式 `ch{number}_{english_abbreviation}` |
| `title` | string | ✅ | 章节标题（故事语言） |
| `goal` | string | ✅ | 章节目标。2-3 句：玩家在此节点需要完成什么 |
| `summary` | string \| null | — | 章节完成摘要。LLM 不输出此字段。引擎初始化时补 `null`，到达 checkpoint 时填充 |
| `routes` | array | ✅ | 分支路由。最后节点为空数组 `[]` |

routes 数组每个元素：

| 字段 | 类型 | 说明 |
|------|------|------|
| `condition` | string \| null | 分支条件，`null` = 无条件/兜底。可引用 variables 中定义的变量 |
| `target` | string | 目标节点 `id`，必须匹配某个 outline 元素的 `id` |

---

## §4 存档格式

LLM JSON 输出经过校验后直接作为 `CoCreationResult` 的数据部分，写入存档时即为 GameState 的初始数据。**输出格式 = 内存结构 = 存档格式，三步一致。**

```json
{
  "save_version": 2,
  "game_id": "neon_depths_20260726T120000Z",
  "story_config": { … },
  "characters": [ … ],
  "locations": [ … ],
  "variables": [ … ],
  "outline": [ … ],
  "state_vars": {
    "Stamina": 80,
    "Trust": 10,
    "Faction": "Freelancer"
  },
  "current_node": "ch1_intro",
  "checkpoint_snapshots": {},
  "bridge_text": "",
  "rejected_changes": []
}
```

### 与旧版存档的结构差异

| 维度 | 旧版 (save_version 1) | 新版 (save_version 2) |
|------|----------------------|----------------------|
| LLM 输出格式 | 自定义 `=== block ===` 分隔 | JSON |
| 解析方式 | 5 套手动解析器 | `json.loads()` |
| story_config 字段数 | 11（含 variables 嵌套） | 4 |
| characters | story_config 内字符串字段 | 顶层数组，结构化子字段 |
| characters 字段 | `name \| role \| relationship` 管道格式 | `name`, `role`, `description`, `appearance`, `traits` |
| locations | 不存在 | 顶层数组 |
| variables | `story_config.variables` 嵌套 | 顶层数组 |
| protagonist | story_config 内 3 个独立字段 | `characters` 中 `role: "protagonist"` 识别 |
| genre / tone / conflict | story_config 内独立字段 | 全部合并到 `premise` |
| outline 节点字段 | id / title / goal / routes | 新增 `summary`（引擎补，LLM 不输出） |
| outline routes 格式 | 自定义 DSL（`if cond → target`） | JSON 结构化 `{"condition": …, "target": …}` |

---

## §5 GameState 初始化

共创完成后，引擎从 LLM JSON 输出初始化 GameState：

```
game_state = GameState()
game_state.story_config   = {tier, title, language, premise}    ← 4 fields
game_state.characters     = [{name, role, description, appearance, traits}, ...]  ← NEW
game_state.locations      = [{id, name, description}, ...]      ← NEW
game_state.variables      = [{name, type, initial}, ...]        ← MOVED: was nested in story_config
game_state.state_vars     = init_from_variables(variables)
game_state.outline        = [{id, title, goal, routes, +status, +summary}, ...]
                              ↑ LLM output              ↑ engine-added
game_state.current_node   = outline[0].id
game_state.checkpoint_snapshots = {}    ← deep copy of state_vars at each checkpoint (for future rollback)
game_state.bridge_text    = ""
game_state.rejected_changes = []
```

引擎附加的运行时字段：
- `status`：`"active"` / `"pending"` / `"completed"`。初始化时首节点 `"active"`，其余 `"pending"`。到达 checkpoint 时推进。
- `summary`：初始化时补 `null`。到达 checkpoint 时引擎将 LLM 输出的 checkpoint summary 写入对应节点。
- `checkpoint_snapshots`：每次 checkpoint 时对当前 `state_vars` 深拷贝存档，为未来回档功能预留数据。

### 与旧版 GameState 的结构差异

| 属性 | 旧版 | 新版 |
|------|------|------|
| `story_config` | 11 字段 + variables 嵌套 | 4 字段，不含 variables |
| `characters` | 不存在（嵌在 story_config 内） | 顶层数组 |
| `locations` | 不存在 | 顶层数组 |
| `variables` | `story_config["variables"]` | 顶层 `game_state.variables` |
| `outline` 节点 | id / title / goal / routes | 引擎补 `status`、`summary` |
| protagonist | `story_config` 中 3 个字段 | `characters` 中按 `role: "protagonist"` 查找 |

---

## §6 实现范围

### 6.1 受影响文件

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `src/storyloom/core/co_create.py` | 重写 | `CoCreateParser` → JSON 解析+校验；`CoCreationResult` 数据结构更新；`CO_CREATE_GENERATION_PROMPT` 重写 |
| `src/storyloom/core/prompt_builder.py` | 修改 | `build_round1()` / `build_round_n()` / `build_adventure_log_prompt()` 适配新字段名；protagonist 从 characters 中提取；移除 genre/tone/conflict 拼接 |
| `src/storyloom/core/game_loop.py` | 修改 | `GameState` 新增 `characters`、`locations` 属性；`state_vars` 初始化来源变更 |
| `src/storyloom/core/save_manager.py` | 修改 | 存档格式 `save_version` 升至 2；序列化/反序列化适配新字段 |
| `src/storyloom/core/session.py` | 修改 | `start_game()` 参数适配新 `CoCreationResult` |
| `src/storyloom/config.py` | 微调 | 可能需要调整 `STORY_LABEL_MAX_CHARS` 等常量（title 字段） |
| `tests/test_co_create.py` | 重写 | 旧 block 解析测试 → JSON 解析+校验测试 |
| `tests/test_prompt_builder.py` | 修改 | 适配新字段名 |
| `tests/test_game_loop.py` | 修改 | 适配新 GameState 结构 |
| `tests/test_session.py` | 修改 | 适配新 CoCreationResult |
| `tests/test_integration.py` | 修改 | 适配新数据结构 |
| `docs/spec/data-model.md` | 修改 | §1 GameState 初始化同步更新 |
| `docs/spec/prompt-design.md` | 修改 | §3 共创 Prompt 同步更新 |
| `docs/spec/exec-flow.md` | 修改 | §3 共创阶段同步更新 |
| `docs/api/co-create.md` | 修改 | API 文档同步 |

### 6.2 删除清单

| 删除项 | 位置 | 原因 |
|--------|------|------|
| `CoCreateParser.split_blocks()` | `co_create.py` | JSON 无 block 分隔符，不再需要 |
| `CoCreateParser.parse_story_config()` | `co_create.py` | 替换为 JSON 校验 |
| `CoCreateParser.parse_variables()` | `co_create.py` | 替换为 JSON 校验 |
| `CoCreateParser.parse_outline()` | `co_create.py` | 替换为 JSON 校验 |
| `CoCreateParser.validate_variables()` | `co_create.py` | 替换为 JSON Schema 校验 |
| `CoCreateParser.validate_outline()` | `co_create.py` | 替换为 JSON Schema 校验 |
| `CoCreateParser.format_outline()` | `co_create.py` | 格式化逻辑移到 `PromptBuilder` |
| `CoCreateParser.REQUIRED_CONFIG_FIELDS` | `co_create.py` | 字段列表大幅缩减，在新校验中重新定义 |
| `CoCreateParser.VALID_TIERS` | `co_create.py` | 内联到 JSON Schema |
| `CoCreateParser.VAR_LINE_RE` | `co_create.py` | 不再需要正则解析变量行 |
| `CoCreateParser.BLOCK_DELIMITER` | `co_create.py` | 不再需要分隔符匹配 |
| `CoCreationResult.outline_text` | `co_create.py` | `PromptBuilder` 自行格式化 outline |

### 6.3 Prompt 模板变更概述

`CO_CREATE_GENERATION_PROMPT` 从"三 block 分隔 + INI 微格式"改为"单一 JSON 输出"：

- 移除 `=== story_config ===` / `=== variables ===` / `=== outline ===` 分隔符说明
- 移除 INI-style `key: value` 格式、缩进续行规则、`[node]` 块语法、routes DSL
- 新增 JSON 格式说明，嵌入 §2 完整输出示例作为格式模板
- 字段规范部分按 §3 逐表描述，强调必填/可选和约束
- 校验清单更新为新字段集合

`ROUND1_PREFIX`（`prompt_builder.py`）：
- 移除 `{background}`（`f"{genre} · {setting}"`）→ 直接用 `premise`
- 移除 `{protagonist}`（三点拼接）→ 从 `characters` 中提取 `role: "protagonist"` 的角色信息
- 移除 `{tone}`、`{conflict}` 独立占位符 → 已在 `premise` 中
- `{characters}` 格式化方式变更：结构化数组 → 文本呈现

### 6.4 校验规则汇总

| 校验项 | 规则 |
|--------|------|
| JSON 格式 | `json.loads()` 成功。失败则向 LLM 反馈行列号 |
| 顶层键 | 必须包含且仅包含 `story_config`、`characters`、`locations`、`variables`、`outline` |
| `story_config.tier` | `"short"` / `"medium"` / `"long"` |
| `story_config.title` | 1-30 字符 |
| `story_config.language` | `"en"` / `"zh-CN"` / `"zh-TW"` |
| `story_config.premise` | 非空字符串 |
| `characters` | 非空数组，恰好 1 个 `role: "protagonist"` |
| `characters[].role` | `"protagonist"` / `"supporting"` / `"antagonist"` |
| `characters[].name/description/appearance/traits` | 非空字符串 |
| `locations` | 非空数组 |
| `locations[].id` | 非空，英文 snake_case |
| `locations[].name/description` | 非空字符串 |
| `variables` | ≤3 总量，≤2 number，≤1 string |
| `variables[].type` | `"number"` / `"string"` |
| `variables[].initial` | number: [0, 100] 整数；string: 非空 |
| `outline` | 非空数组 |
| `outline[].id` | 非空，唯一 |
| `outline[].routes[].target` | 必须匹配某个 `outline[].id` |
| `outline` 最后节点 | `routes` 为空数组 `[]` |
| `outline[].routes[].condition` 中的变量 | 必须在 `variables` 中声明。不存在的变量 = 条件求值为 false |

---

## §7 拓展性设计

### 图像模式（未来）

激活图像模式时：
- `characters[].appearance` → 角色立绘生成（当前已必填）
- `locations[].description` → 场景背景生成（当前已必填）

### 其他可能拓展

| 未来功能 | 拓展方式 |
|----------|---------|
| 音频层（BGM / 环境音） | JSON 顶层新增 `audio` 键 |
| 道具/物品系统 | JSON 顶层新增 `items` 键 |
| 多主角 | `characters` 中允许多个 `role: "protagonist"` |
| 角色关系图 | `characters` 中 `description` 引用其他角色 `name` |

新增功能 = JSON 顶层新增键，不影响现有键的解析和校验。

---

## §8 与自定义 Block 格式的对比

| 维度 | 自定义 Block（旧） | JSON（新） |
|------|-------------------|-----------|
| 解析代码 | 5 套微格式解析器，~300 行 | `json.loads()` |
| 失败模式 | 分隔符遗漏、字段缺失、续行错误、DSL 语法错误 | `JSONDecodeError` 一种 |
| LLM 正确率 | 依赖 prompt 示例覆盖每种微格式 | 现代 LLM JSON 输出 >99%；支持 JSON mode 时 100% |
| 与存档关系 | 解析 → 转换 → 存档 | **直接一致**，零转换 |
| 校验提示 | "找不到 `=== variables ===` 分隔符" | `json.loads()` 定位到行列号，精确 |
| 拓展 | 新字段需改解析器 + prompt | 新字段只改校验逻辑 + prompt |
| 人类可读 | 较好 | 稍差（非目标受众） |

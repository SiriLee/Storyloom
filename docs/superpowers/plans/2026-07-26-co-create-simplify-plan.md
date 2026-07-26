# 共创阶段数据模型重构 — 实现计划

> 基于设计文档 `docs/superpowers/specs/2026-07-26-co-create-simplify-design.md`  
> 计划生成：2026-07-26  
> 状态：已确认，待执行  
> 协作模式：引擎开发者独立执行全部阶段（Web 已合并入主仓库）

---

## §0 核心设计决策速查

| # | 决策 | 依据 |
|---|------|------|
| D1 | 旧存档破坏性升级，不写迁移（SAVE_VERSION 1→2） | Phase 1 无生产用户 |
| D2 | `label` → `title` 全链路重命名（字段、常量、metadata key、`list_games()` 返回值） | 语义更自然 |
| D3 | `outline_text` 保留于产出数据中，从 outline_nodes 即时格式化生成 | Prompt 构建的唯一桥梁 |
| D4 | `CoCreationResult` dataclass 删除，`generate()` 直接返回校验后的 dict | 输出即存档，零中间态 |
| D5 | `CoCreateParser` 类保留，改名 `CoCreateValidator`，旧方法全部替换为 JSON 校验 | 沿用错误处理模式 |
| D6 | `characters[].appearance` 保持必填 | 为图像模式准备数据 |
| D7 | `locations` 当前仅为静态初始集合；运行时动态追加机制后续实现 | 分层，当前 scope 不膨胀 |
| D8 | JSON 解析失败与校验失败分离——前者笼统提示（"Invalid JSON format"），后者具体描述字段问题 | LLM 可看自己上一轮输出定位错误 |
| D9 | Prompt Story Context 精简为 Premise + Characters + Locations 三块；删除 Protagonist 独立行 | 角色信息自包含于 Characters |
| D10 | Characters 字段 5→4：`traits` 合并入 `description` | 语义无重叠 |
| D11 | `variables` 从 `story_config["variables"]` 移到顶层，全链路独立传递 | LLM 输出中本就独立 |
| D12 | `list_games()` 返回值 `label`→`title`，`genre`→`premise` | 对齐新字段结构 |
| D13 | `_build_init_dict` 接收 dict，机械补 engine 字段即可 | 输出即存档 |
| D14 | LLM 产出校验与存档加载校验分离——`CoCreateValidator` 管前者，`SaveManager` 管后者 | 职责不同、信任级别不同 |
| D15 | `PromptBuilder` 新增 `_format_story_context()` 共用方法，同时服务 round1 + adventure log | 消除重复格式化 |
| D16 | `lang_meta/*.json` 中 `label_hint` → `title_hint`，内容不变 | 仅改名 |

---

## §1 总体结构

```
Phase 1: 文档先行
    ├── 1.1 data-model.md
    ├── 1.2 prompt-design.md
    ├── 1.3 exec-flow.md
    └── 1.4 api/co-create.md

Phase 2: 基础层
    ├── 2.1 config.py 常量更新
    ├── 2.2 lang_meta/*.json 字段改名
    └── 2.3 CoCreateParser → CoCreateValidator

Phase 3: 共创引擎
    ├── 3.1 CO_CREATE_GENERATION_PROMPT 重写
    ├── 3.2 CoCreateFlow 适配 JSON 路径
    └── 3.3 label → title 全链路替换

Phase 4: 叙事引擎适配
    ├── 4.1 GameState + GameLoop 数据结构更新
    └── 4.2 PromptBuilder 重构

Phase 5: 存储层适配
    ├── 5.1 SaveManager
    └── 5.2 GameSession

Phase 6: Web + CLI 适配
    ├── 6.1 web/server.py
    ├── 6.2 web/static/js/
    ├── 6.3 dev_cli/observer.py
    └── 6.4 dev_cli/game_driver.py

Phase 7: 测试重写
    ├── 7.1 test_co_create.py
    ├── 7.2 test_prompt_builder.py
    ├── 7.3 test_session.py + test_game_loop.py
    ├── 7.4 test_integration.py
    └── 7.5 test_web_server.py

Phase 8: 全面验证
```

**每步完成后立即 git commit（约定式提交格式）。**

---

## Phase 1: 文档先行

> 文档驱动实现——先定义数据契约，代码遵从文档。

### 1.1 `docs/spec/data-model.md`

**§1 GameState 初始化**：

- 新增 `characters`、`locations` 属性（与 `story_config` 平级）
- `variables` 从 `story_config.variables` 改为独立属性
- `story_config` 只含 4 字段：`tier`、`title`、`language`、`premise`
- 更新初始化代码块示例

**§3 存档系统**：

- 存档内容结构更新为 v2 格式（顶层新增 `characters`、`locations`、`variables`，移除 `story_config.variables`）
- `metadata.label` → `metadata.title`
- `SAVE_VERSION` 更新为 2
- 移除"`story_config` 含 `variables`"的校验描述（改为顶层校验）

**§A.2 常量**：

- `STORY_LABEL_MIN_CHARS` / `STORY_LABEL_MAX_CHARS` → `STORY_TITLE_MIN_CHARS` / `STORY_TITLE_MAX_CHARS`
- `SAVE_VERSION` → 2
- `SUPPORTED_LANGUAGES` 新增 `"zh-TW"`（如已存在于代码）

### 1.2 `docs/spec/prompt-design.md`

**§3 共创阶段 Prompt 全部重写**：

- §3.1 追问循环基本不变（只改 `label_hint` → `title_hint` 模板变量名）
- §3.2 故事生成：三 block 分隔格式 → 单一 JSON 输出格式
  - 删除 INI-style `key: value` 规范
  - 删除 `=== block ===` 分隔符说明
  - 新增 JSON Schema 规范（字段表、类型约束、必填/可选）
  - 格式示例替换为 JSON 示例（引用设计文档 §2）
  - 自检清单更新为新字段集合

**§4 叙事循环 Prompt — Story Context 区域**：

- 旧格式（Background / Protagonist / Tone / Conflict / Characters）替换为：
  ```
  **Premise:** {premise}
  **Characters:**
  - {name} ({role}) — {description}
  **Locations:**
  - {name} — {description}
  ```
- Protagonist 不再独立列出——Characters 中通过 role 标识

**§5 冒险日志 Prompt**：

- "Story Background" 区域同 §4 的 Story Context 格式
- `story_label` 占位符改为 `title`

### 1.3 `docs/spec/exec-flow.md`

**§1.1 术语速查表**：

- `story_config` 定义更新为 4 字段
- 新增 `characters`、`locations` 术语条目
- `label` → `title`

**§3.4 Step 3**：

- 三 block 分隔 → JSON 输出描述
- `CoCreationResult` → dict
- 解析/校验错误分类更新（JSON 解析失败 vs 字段校验失败）

**§3.5 Step 4**：

- 初始化逻辑更新（顶层 fields）

### 1.4 `docs/api/co-create.md`

- `CoCreationResult` 章节替换为 dict 返回值说明
- `generate() → dict` 签名更新
- 校验规则汇总更新
- Usage Example 适配新 API
- `story_config` 结构说明更新为 4 字段

---

## Phase 2: 基础层

### 2.1 `src/storyloom/config.py`

**变更方向**：

- `SAVE_VERSION = 1` → `SAVE_VERSION = 2`
- `STORY_LABEL_MIN_CHARS` → `STORY_TITLE_MIN_CHARS`
- `STORY_LABEL_MAX_CHARS` → `STORY_TITLE_MAX_CHARS`

**需排查**：搜索所有引用旧常量名的文件，统一替换（`co_create.py`、`test_co_create.py` 等）。

### 2.2 `src/storyloom/core/lang_meta/*.json`

- 各语言文件中的 `label_hint` key → `title_hint`
- 值不变
- 检查文件：`en.json`、`zh-CN.json`（以及 `zh-TW.json` 如存在）

### 2.3 `src/storyloom/core/co_create.py` — CoCreateParser → CoCreateValidator

**删除项**：

| 成员 | 类型 | 原因 |
|------|------|------|
| `BLOCK_DELIMITER` | 正则 | block 分隔符不再需要 |
| `REQUIRED_CONFIG_FIELDS` | 列表 | 字段集完全变了 |
| `VALID_TIERS` | 集合 | 移入 JSON Schema |
| `VAR_LINE_RE` | 正则 | 变量不再用正则解析 |
| `split_blocks()` | 静态方法 | JSON 无 block |
| `parse_story_config()` | 静态方法 | 替换为 JSON 校验 |
| `parse_variables()` | 静态方法 | 替换为 JSON 校验 |
| `validate_variables()` | 静态方法 | 替换为 JSON Schema 校验 |
| `parse_outline()` | 静态方法 | 替换为 JSON 校验 |
| `validate_outline()` | 静态方法 | 替换为 JSON Schema 校验 |
| `format_outline()` | 静态方法 | 格式化逻辑移入 PromptBuilder |

**新增项**（类改名 `CoCreateValidator`）：

需新增以下静态校验方法：

| 方法 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `validate_json(raw: str) -> tuple[dict | None, str | None]` | LLM 原始响应 | `(parsed_dict, error_message)` | `json.loads()` 封装；成功返回 dict，失败返回行列号+笼统提示 |
| `validate_story_config(d: dict) -> list[str]` | JSON dict 的 `story_config` 部分 | 错误列表 | tier 枚举、title 长度、language 枚举、premise 非空 |
| `validate_characters(d: dict) -> list[str]` | JSON dict 的 `characters` 部分 | 错误列表 | 非空数组、恰好 1 个 protagonist、role 枚举、必填字段非空 |
| `validate_locations(d: dict) -> list[str]` | JSON dict 的 `locations` 部分 | 错误列表 | 非空数组、id snake_case、name/description 非空 |
| `validate_variables(d: dict) -> list[str]` | JSON dict 的 `variables` 部分 | 错误列表 | 总量 ≤3、number ≤2、string ≤1、类型枚举、初始值范围、名称唯一 |
| `validate_outline_cross_ref(outline_nodes: list, variable_names: list) -> list[str]` | outline 数组 + 已声明变量名列表 | 错误列表 | route target 存在性、末节点 routes 为空、condition 变量已声明 |

**设计要点**：

- 所有校验方法返回 `list[str]`（空 = 通过），不抛异常
- `_parse_generation` 收集所有方法的错误，合并后决定是否抛 `CoCreateError`
- 与 `SaveManager.load()` 的校验完全分离——后者只做 version / 顶层键存在性 / `current_node` 引用有效性检查

---

## Phase 3: 共创引擎

### 3.1 `CO_CREATE_GENERATION_PROMPT` 重写

> 这是本次重构的**核心产出**。设计文档 §6.3 给出了变更方向，此处补充具体的 Prompt 设计原则。

**当前 Prompt 结构**（5 段式）：

1. 角色定义（"you are a story setup generator"）
2. 完整格式示例（三 block 分隔 + INI 微格式 + `[node]` DSL）
3. 逐 block 字段规范（story_config 11 字段、variables 格式、outline 格式）
4. 禁止模式（逐条列出 7 项已知错误）
5. 自检清单

**新 Prompt 结构**（保持 5 段式，内容全面替换）：

1. **角色定义** — 不变，仅更新输出格式引用（"produce a JSON object"）
2. **完整 JSON 格式示例** — 引用设计文档 §2 的示例（英文 story、包含 characters[Kael/Mouse/Michiko] + locations[4 个] + variables[3 个] + outline[5 节点]）
   - 示例之后加屏障声明："This is a format example ONLY. Generate an entirely new story setup based on the conversation."
3. **逐字段 JSON Schema 规范** — 按 `story_config` → `characters` → `locations` → `variables` → `outline` 顺序描述
   - 每个字段的约束、枚举值、必填/可选标注
   - Outline routes 的 target 引用规则（必须 match node id）、末节点 routes 必须为 `[]`
   - Variables 数量限制与类型约束
   - Characters 恰好 1 个 protagonist 约束
4. **禁止模式** — 更新为 JSON 场景下的已知错误模式：
   - Markdown 围栏（`` ```json ``）包裹 JSON
   - 根不是 JSON object（数组或其他）
   - 顶层键缺失或多余（精确 5 键）
   - route target 匹配不到任何 outline node id
   - 末节点 routes 非空数组
   - condition 引用未声明的 variable
   - 角色 role 枚举取值非法
5. **自检清单** — 按新字段集合逐项列出

**Prompt 设计原则（继承 `prompt-design.md` §1.2 约束有效性原则）**：

- **示例先行**：JSON 示例放在规则之前
- **正反双重覆盖**：关键约束（route target 引用、末节点 routes 为空）在"规范"和"禁止"中各出现一次
- **反例约束**：对每个关键约束给出具体的错误 JSON 片段
- **注意力标签**：用 `**(重要)**` 标记最容易出错的规则
- **示例-规则屏障**：显式声明示例仅供格式参考

**语言控制**：Prompt 英文书写。`story_config.language` 控制字段值（角色名、地名、variable 名、node title/goal）的输出语言。

### 3.2 `CoCreateFlow` 适配 JSON 路径

**3.2.1 `_parse_generation()` 重写**

旧流程：
```
response → split_blocks() → parse_story_config + parse_variables + validate_variables
+ parse_outline + validate_outline → format_outline() → CoCreationResult
```

新流程：
```
response → CoCreateValidator.validate_json(response) → 成功得到 dict
→ CoCreateValidator.validate_story_config(dict)
+ CoCreateValidator.validate_characters(dict)
+ CoCreateValidator.validate_locations(dict)
+ CoCreateValidator.validate_variables(dict)
+ CoCreateValidator.validate_outline_cross_ref(...)
→ 全部通过 → 格式化 outline_text（从 outline_nodes 生成）→ 返回 dict
```

**3.2.2 `generate()` 返回值变更**

- 返回类型：`CoCreationResult` → `dict`
- 返回的 dict 即完整存档数据（含 story_config / characters / locations / variables / outline / state_vars 初始值）
- `outline_text` 作为 dict 的键之一（`data["outline_text"]`），在 `_parse_generation` 中生成

**3.2.3 `_parse_generation` 中的 outline_text 生成**

从 JSON `outline` 数组生成格式化文本。逻辑与当前 `CoCreateParser.format_outline()` 等效，但在 `CoCreateFlow` 内部执行（不单独暴露为 public 方法）。

**3.2.4 `retry_generate()` 适配**

- JSON 解析失败（`json.JSONDecodeError`）→ 纠正提示："Invalid JSON format. Please strictly follow the JSON specification. Regenerate the entire JSON object."
- 字段校验失败 → 纠正提示：列举具体错误字段和原因（如 `story_config.tier must be one of: short, medium, long`）

**3.2.5 `CoCreateError` 保留**

- phase 保持不变：`"send"` / `"generate_api"` / `"generate_parse"`
- `"generate_parse"` 覆盖 JSON 解析失败 + 字段校验失败两种情况（纠正提示区分即可）

### 3.3 `label` → `title` 全链路替换

**涉及文件与位置**：

| 文件 | 变更 |
|------|------|
| `co_create.py` | Prompt 模板中所有 `label` 引用 → `title`；`label_hint` → `title_hint` |
| `game_loop.py:1092` | `story_config.get("label", ...)` → `get("title", ...)` |
| `prompt_builder.py:403` | `story_label` → 从 `story_config.get("title", ...)` 获取 |
| `save_manager.py:100, 373` | metadata 的 `"label"` key → `"title"`；`list_games()` 返回值的 `"label"` → `"title"` |
| `session.py:63, 100, 176` | `label` 变量名 + dict key → `title` |
| `observer.py:95` | `story_config.get('label', ...)` → `get('title', ...)` |
| `game_driver.py:219, 508, 520, 656` | `.get('label', ...)` → `.get('title', ...)` |
| `web/server.py:623, 658` | 视 `story_config` 返回内容而定（现行为透传，字段名随源变） |

**策略**：工具辅助批量替换（`sed` 或 IDE find-replace），但需逐个文件验证——`label` 在 choice/locations/story_config 中有多种语义，避免误伤（如 choice 的 `labels` 选项标签数组不应被替换）。

---

## Phase 4: 叙事引擎适配

### 4.1 `GameState` + `GameLoop` 数据结构更新

**4.1.1 `GameState.__init__`**

- 当前签名：`__init__(self, story_config: dict)`，从 `story_config.get("variables", [])` 读取变量定义
- 新签名：`__init__(self, variables: list[dict])`，直接接收变量定义数组
- 内部 `_var_types` 构建逻辑不变

**4.1.2 `GameState.from_dict()`**

- 当前：`from_dict(cls, data: dict, story_config: dict)`
- 新：`from_dict(cls, data: dict, variables: list[dict])`，从顶层 `variables` 获取类型定义替代从 `story_config` 中取

**4.1.3 `GameLoop.__init__`**

新增参数：
- `characters: list[dict]` — 角色数组
- `locations: list[dict]` — 地点数组
- `variables: list[dict]` — 变量定义（独立于 story_config）

新增属性：
- `self.characters`
- `self.locations`
- `self.variables`

`self.game_state` 初始化改为 `GameState(variables)`

**4.1.4 `GameLoop.to_save_dict()`**

- `metadata["label"]` → `metadata["title"]`
- `"story_config"` 只存 4 字段（tier, title, language, premise）
- 新增 `"characters"` / `"locations"` / `"variables"` 顶层键
- `"variables"` 存储完整定义数组（含 type/initial），不再嵌套在 story_config 内

**4.1.5 `GameLoop.from_save_dict()`**

- 新增从 `data["characters"]` / `data["locations"]` / `data["variables"]` 读取
- `GameState.from_dict()` 调用改为传递顶层 `variables`
- `outline` 字段中 `branches`/`routes` 统一处理逻辑不变

**4.1.6 `stream_round()` 第 960 行**

- `variables=self.story_config.get("variables", [])` → `variables=self.variables`

**4.1.7 `GameLoop._normalize_outline_nodes()`**

- 逻辑不变（仅处理 save 格式与 fresh 格式的兼容）
- 从 `game_loop.py:1236` 注释中移除 `CoCreateParser.parse_outline` 引用（类已改名）

### 4.2 `PromptBuilder` 重构

**4.2.1 新增 `_format_story_context()`**

静态方法，签名：

```python
@staticmethod
def _format_story_context(premise: str, characters: list[dict], locations: list[dict]) -> str:
```

生成格式：

```
**Premise:** {premise}

**Characters:**
- {name} ({role}) — {description}
- ...

**Locations:**
- {name} — {description}
- ...
```

**4.2.2 `build_round1()`**

Story Context 区域的变更：

- 删除旧字段提取：`protagonist_name` / `protagonist_identity` / `protagonist_traits` / `genre` / `setting` / `tone` / `conflict` 的 `.get()` 调用
- 改为：从参数中获取 `premise`（来自 `story_config`）、`characters`、`locations`，调 `_format_story_context()`
- `ROUND1_PREFIX` 模板中删除 `{background}`、`{protagonist}`、`{tone}`、`{conflict}` 占位符，替换为 `{story_context}`
- `{characters}` 占位符删除（已合入 `{story_context}`）
- 新增参数：`characters: list[dict]`、`locations: list[dict]`

**4.2.3 `build_round_n()`**

- `variables` 参数来源从 `story_config["variables"]` 改为独立传递
- 签名增加 `variables: list[dict]` 参数

**4.2.4 `build_adventure_log_prompt()`**

- Story Background 区域调用 `_format_story_context()`，格式与 round1 一致
- `story_label` → `story_config.get("title", "Untitled Adventure")`
- 删除逐字段拼接 genre/setting/protagonist/tone/conflict/characters 的代码块（约 20 行）

**4.2.5 `_format_current_state()`**

- 逻辑不变（通过 `variables` 数组做 type lookup）
- 仅参数来源变更（已在 4.2.3 覆盖）

---

## Phase 5: 存储层适配

### 5.1 `SaveManager`

**5.1.1 `REQUIRED_FIELDS`**

```python
# 旧
REQUIRED_FIELDS = ["story_config", "state_vars", "outline", "progress"]

# 新
REQUIRED_FIELDS = [
    "story_config", "characters", "locations", "variables",
    "state_vars", "outline", "progress",
]
```

**5.1.2 `load()` 校验**

- 移除 `"variables" not in data["story_config"]` 校验（variables 已移到顶层）
- 新增 `"variables" in data` 校验（已是 `REQUIRED_FIELDS` 的一部分）
- 不重复 LLM 产出层的字段级校验（如 characters 的 role 枚举、variables 的类型约束等）
- `current_node` 引用有效性校验保留

**5.1.3 `list_games()`**

返回值重构：

```python
# 旧
{"game_id": ..., "label": ..., "language": ..., "genre": ..., "tier": ..., "created_at": ..., "save_count": ...}

# 新
{"game_id": ..., "title": ..., "language": ..., "tier": ..., "premise": ..., "created_at": ..., "save_count": ...}
```

- `meta.get("label", ...)` → `meta.get("title", ...)`
- `sc.get("genre", "")` → `sc.get("premise", "")`（如需截取长度，可在 UI 层处理）

**5.1.4 `write_last_played()`**

- `label` 参数 + metadata key → `title`

**5.1.5 `create_game()` + `_sanitize()`**

- 目录名使用 `title` 替代 `label`

### 5.2 `GameSession`

**5.2.1 `start_game()` 签名变更**

```python
# 旧
def start_game(self, result: CoCreationResult) -> tuple[GameLoop, str]:

# 新
def start_game(self, data: dict) -> tuple[GameLoop, str]:
```

- `data` 即 `CoCreateFlow.generate()` 返回的 dict
- 内部调 `_build_init_dict(data, created_at)` 补 engine 字段

**5.2.2 `_build_init_dict()` 简化**

当前逻辑：手动从 `CoCreationResult` 搬运每个字段到存档 dict（~35 行代码）。

新逻辑：
1. 从 `data` 深拷贝所有 LLM 产出字段（story_config / characters / locations / variables / outline）
2. 遍历 variables 生成 `state_vars` 初始值
3. 补 `progress.current_node`（取 outline[0].id）
4. 补 `progress.checkpoint_snapshots`（空 dict）
5. 补 `config.temperature`
6. 补 `metadata`（从 `story_config.title` 获取 label、写入 created_at/updated_at）

**5.2.3 `load_game()` + `_load_from_data()`**

- 对外 API 不变
- `GameLoop.from_save_dict()` 调用已适配新字段（Phase 4.1.5）
- `label` → `title` 的 last_played 追踪更新

**5.2.4 `list_games()`**

- 透传 `SaveManager.list_games()`，返回值字段名随 SaveManager 更新

---

## Phase 6: Web + CLI 适配

### 6.1 `src/storyloom/web/server.py`

**需要修改的端点**：

**`POST /api/co-create/generate`（约 line 238-247）**：

- `result.story_config` → `data["story_config"]`
- `result.outline_text` → `data["outline_text"]`
- `result` 类型从 `CoCreationResult` → `dict`

**`POST /api/co-create/retry-generate`（约 line 257-272）**：

- 同上

**`GET /api/saves/{game_id}/preview`（约 line 623）**：

- 视返回值字段变更（当前透传 story_config），字段名随源更新

**`POST /api/saves/{game_id}/start`（约 line 658）**：

- 同上

**导入语句**：

- 移除 `CoCreationResult` 导入（如仅从 `sessions.py` 间接使用则无需处理）

**`sessions.py`**：

- `_co_create_result` 的类型注解：`CoCreationResult | None` → `dict | None`
- `store_co_create_result()` 参数类型同理
- `get_co_create_result()` 返回类型同理
- 移除 `CoCreationResult` 导入

### 6.2 `src/storyloom/web/static/js/`

**`router.js`**（已确认的变更点）：

| 行号 | 当前代码 | 改为 |
|------|---------|------|
| 527 | `config.label` | `config.title` |
| 528 | `config.setting` | `config.premise`（game preview 页面：删除 setting 展示或用 premise 替代） |
| 558 | `GameState.storyConfig.label` | `GameState.storyConfig.title` |
| 607 | `g.label` | `g.title`（save list 卡片） |
| 609 | `g.genre` | `g.premise`（save list 元信息；如需截取长度，JS 端处理） |
| 787 | `GameState.storyConfig.label` | `GameState.storyConfig.title` |

### 6.3 `src/storyloom/dev_cli/observer.py`

**`record_co_create_result()` 约 line 90-98**：

- 签名：`(self, story_config: dict, outline_text: str)` → `(self, data: dict)`
- 内部从 `data["story_config"]` / `data["outline_text"]` 读取
- `story_config.get('label', ...)` → `get('title', ...)`
- `story_config.get('genre', ...)` → `get('premise', ...)`

### 6.4 `src/storyloom/dev_cli/game_driver.py`

**`run_co_create()` 约 line 132-222**：

- 返回类型：`CoCreationResult | None` → `dict | None`
- `result.story_config.get('label', ...)` → `result["story_config"].get('title', ...)`
- `result.story_config.get('genre', ...)` → `result["story_config"].get('premise', ...)`
- `len(result.outline_nodes)` → `len(result["outline"])`
- `observer.record_co_create_result(result.story_config, result.outline_text)` → `observer.record_co_create_result(result)`

**`run_game()` 约 line 427**：

- `outline_text=game_loop.outline_text` 逻辑不变（`outline_text` property 仍在 GameLoop 上）

**游戏存档列表展示 约 line 508-526**：

- `g.get('label', ...)` → `g.get('title', ...)`
- `g.get('genre', ...)` → `g.get('premise', ...)`

**导入语句**：

- 移除 `CoCreationResult` 导入

---

## Phase 7: 测试重写

> 当前共 293 个测试。Phase 7 完成后全量绿色才进入 Phase 8。

### 7.1 `tests/test_co_create.py`

**全量重写**。

**删除的测试类**（旧解析逻辑全部失效）：

- `TestSplitBlocks` — block 分隔逻辑废弃
- `TestParseStoryConfig` — INI 解析废弃
- `TestParseVariables` — 正则解析废弃
- `TestValidateVariables` — 合并入新校验
- `TestParseOutline` — `[node]` DSL 解析废弃
- `TestValidateOutline` — 合并入新校验
- `TestFormatOutline` — 格式化移入 PromptBuilder

**保留但需适配**：

- `TestCoCreateFlowStateMachineProperties` — `CoCreationResult` 类型注解变为 `dict`
- `TestCoCreateFlowStart` — 基本不变（`start()` 不改）
- `TestCoCreateFlowSend` — 基本不变
- `TestCoCreateFlowSendEndToEnd` — `result.story_config[...]` → `result["story_config"][...]`；`result.outline_text` → `result["outline_text"]`；`result.outline_nodes` → `result["outline"]`
- `TestCoCreateFlowSendErrors` — 基本不变
- `TestGenerate` — `result.story_config[...]` 适配 dict 访问

**新增测试类**：

| 测试类 | 覆盖内容 |
|--------|---------|
| `TestCoCreateValidatorJson` | `validate_json()` — 合法 JSON、非法 JSON（行列号）、非 object JSON、markdown 围栏包裹 |
| `TestCoCreateValidatorStoryConfig` | `validate_story_config()` — 完整合法、tier 枚举非法、title 过短/过长、language 非法、premise 为空 |
| `TestCoCreateValidatorCharacters` | `validate_characters()` — 无 protagonist、多 protagonist、role 枚举非法、必填字段缺失、空数组 |
| `TestCoCreateValidatorLocations` | `validate_locations()` — 空数组、非 snake_case id、必填字段缺失 |
| `TestCoCreateValidatorVariables` | `validate_variables()` — 超过 3 个、number 超过 2、string 超过 1、初始值越界、名称重复、非法类型 |
| `TestCoCreateValidatorOutline` | `validate_outline_cross_ref()` — route target 不存在、末节点 routes 非空、condition 引用未声明变量 |

**`FULL_GENERATION_RESPONSE` 全局变量**：

- 更改为完整 JSON 示例（基于设计文档 §2）

### 7.2 `tests/test_prompt_builder.py`

**`SAMPLE_STORY_CONFIG`**：

```python
# 旧（11字段）
SAMPLE_STORY_CONFIG = {
    "genre": "赛博朋克冒险", "tier": "medium", "label": "霓虹深渊",
    "setting": "...", "protagonist_name": "...", ...
}

# 新（4字段）
SAMPLE_STORY_CONFIG = {
    "tier": "medium", "title": "霓虹深渊", "language": "zh-CN",
    "premise": "2087年新东京，数据是唯一货币。林焰，前企业安全顾问..."
}
```

**新增 `SAMPLE_CHARACTERS` / `SAMPLE_LOCATIONS`**：

测试用角色数组和地点数组，供 `build_round1()` 和 `build_adventure_log_prompt()` 测试。

**测试方法变更**：

- `TestBuildRound1`：验证输出含 `**Premise:**` 而非 `**Background:**` / `**Protagonist:**` / `**Tone:**` / `**Conflict:**`
- `TestBuildRoundN`：`variables` 参数来源变更
- 新增 `TestFormatStoryContext`：验证 `_format_story_context()` 输出格式

### 7.3 `test_session.py` + `test_game_loop.py`

**`test_session.py`**：

- `SAMPLE_STORY_CONFIG` 精简为 4 字段
- `SAMPLE_RESULT`：从 `CoCreationResult(...)` 改为 dict 字面量，字段结构对齐 v2 存档
- `TestGameSessionLifecycle.test_start_game_returns_game_loop_and_game_id`：`SAMPLE_RESULT` 类型变更
- 新增 `SAMPLE_CHARACTERS` / `SAMPLE_LOCATIONS`

**`test_game_loop.py`**：

- `SAMPLE_STORY_CONFIG` 精简
- `GameState()` 构造调用：`GameState(story_config)` → `GameState(variables)`
- `GameLoop()` 构造调用：新增 `characters` / `locations` / `variables` 参数
- `TestGameLoopSaveLoad`：验证存档 dict 含顶层 `characters` / `locations` / `variables` 键
- `TestGameLoopOutlineNodes`：逻辑不变（outline 内部结构兼容）

### 7.4 `test_integration.py`

- `SAMPLE_STORY_CONFIG` 精简
- `GameLoop()` 构造调用适配新参数

### 7.5 `test_web_server.py`

- `SAMPLE_RESULT`：从 `CoCreationResult(...)` 改为 dict
- 移除 `CoCreationResult` 导入
- 相关 mock 返回值适配

---

## Phase 8: 全面验证

1. **全量测试**：`pytest --ignore=tests/test_api_client.py` — 确认全部 293+ 测试绿色
2. **类型检查**：`python -m py_compile src/storyloom/core/co_create.py` 等逐个文件语法验证
3. **手动功能冒烟**：
   - 启动 CLI `storyloom-dev` → 新游戏 → 完整共创流程 → 生成 → 走一轮叙事 → 存档 → 退出
   - 启动 CLI → 继续 → 选档 → 走一轮 → 退出
   - 启动 Web `storyloom-web` → 共创 → 存档列表展示 → 读档 → 叙事 → 退出
4. **旧存档验证**：尝试加载 v1 存档 → 确认"损坏"判定 + 自动删除（验证版本检测功能）

---

## §A 风险点与注意事项

### A.1 `label` 命名冲突

`label` 在代码库中有多重语义：
- **story label**（存档目录名）— 需改
- **choice labels**（选项文本数组）— **不能改**
- **UI label**（CSS class / 设置项显示名）— **不能改**

批量替换时务必区分上下文，建议分文件手动确认而非全局 `sed`。

### A.2 `story_config` 在存档中的兼容性

`to_save_dict()` 中的 `story_config` 当前存储完整 11 字段（含 variables 嵌套）。新版本只存 4 字段。`from_save_dict()` 从 `data["variables"]` 读取变量定义——需要确认**无其他代码直接读取 `data["story_config"]["variables"]`**。

### A.3 Web 前端的 `storyConfig` 消费

`GameState.storyConfig` 是前端 JS 对象，来源于 API 返回。字段名随后端变更后，前端所有 `.label` / `.setting` 引用需同步改。Phase 6.2 已覆盖已知引用点，但需排查 `game.js` 和 `state.js` 中是否有其他对 `storyConfig` 深层字段的引用。

### A.4 Prompt 迭代验证

Phase 3.1 的 Prompt 重写是最关键且最难一次到位的部分。建议：
- 先用设计文档 §2 的 JSON 示例在 prompt lab 中验证 LLM 能否正确产出
- 故意给模糊输入测试 LLM 是否遵守字段约束
- 记录到 `prompt-design.md` §6 迭代日志

### A.5 变量校验的初始值类型

`json.loads()` 后，JSON 中的 `80` 自动为 Python `int`，`"Freelancer"` 为 `str`。校验逻辑需注意 `isinstance(initial, int)` 的行为（Python int 继承自 `numbers.Integral`，但 `bool` 也是 int 子类——需排除 `bool` 干扰）。

---

## §B 文件影响总表

| 文件 | 阶段 | 变更级别 | 关键操作 |
|------|------|---------|---------|
| `docs/spec/data-model.md` | 1.1 | 大改 | §1/§3/§A 重写 |
| `docs/spec/prompt-design.md` | 1.2 | 大改 | §3 重写，§4/§5 Story Context 更新 |
| `docs/spec/exec-flow.md` | 1.3 | 中改 | §1/§3 更新 |
| `docs/api/co-create.md` | 1.4 | 大改 | 全文更新 |
| `src/storyloom/config.py` | 2.1 | 小改 | 常量更新 |
| `src/storyloom/core/lang_meta/*.json` | 2.2 | 小改 | key 改名 |
| `src/storyloom/core/co_create.py` | 2.3 + 3.1 + 3.2 + 3.3 | **重写** | CoCreateParser→CoCreateValidator + Prompt + JSON 路径 + label→title |
| `src/storyloom/core/game_loop.py` | 4.1 + 3.3 | 大改 | GameState/GameLoop 新字段 + label→title |
| `src/storyloom/core/prompt_builder.py` | 4.2 + 3.3 | 大改 | _format_story_context + 全 prompt 适配 + label→title |
| `src/storyloom/core/save_manager.py` | 5.1 + 3.3 | 中改 | REQUIRED_FIELDS + load 校验 + list_games + label→title |
| `src/storyloom/core/session.py` | 5.2 + 3.3 | 中改 | start_game/_build_init_dict + CoCreationResult 移除 + label→title |
| `src/storyloom/core/__init__.py` | 3.2 | 小改 | 移除 CoCreationResult 导出 |
| `src/storyloom/web/server.py` | 6.1 | 小改 | CoCreationResult → dict，outline_text 来源变更 |
| `src/storyloom/web/sessions.py` | 6.1 | 小改 | CoCreationResult 类型注解 → dict |
| `src/storyloom/web/static/js/router.js` | 6.2 | 小改 | label→title，genre→premise，setting→premise |
| `src/storyloom/dev_cli/observer.py` | 6.3 | 小改 | record_co_create_result 签名 + label→title + genre→premise |
| `src/storyloom/dev_cli/game_driver.py` | 6.4 | 小改 | CoCreationResult→dict + label→title + genre→premise |
| `tests/test_co_create.py` | 7.1 | **重写** | 全部测试类 |
| `tests/test_prompt_builder.py` | 7.2 | 大改 | SAMPLE_STORY_CONFIG + 测试用例更新 |
| `tests/test_session.py` | 7.3 | 中改 | SAMPLE_STORY_CONFIG + SAMPLE_RESULT 更新 |
| `tests/test_game_loop.py` | 7.3 | 中改 | SAMPLE_STORY_CONFIG + 构造参数更新 |
| `tests/test_integration.py` | 7.4 | 小改 | SAMPLE_STORY_CONFIG + 构造参数更新 |
| `tests/test_web_server.py` | 7.5 | 小改 | SAMPLE_RESULT 更新 |

**总计：24 个文件 / 3 个重写 / 18 个修改 / 3 个小改**

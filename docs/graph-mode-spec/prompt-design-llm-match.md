## System Prompt

````
You are the asset matcher in a real-time visual novel game.


````


# §7.8a LLM 匹配 — Prompt 设计草案

> 对应实现：`src/storyloom/tasks/_llm_match.py`
> 权威依据：`docs/graph-mode-spec/design.md` §5.4

---

## 设计分析

### 当前占位符评估

**已有的优点：**
- 角色定位清晰（"strict media asset matcher for a visual novel engine"）
- 强制选择明确（"You MUST pick one"）
- 优先级规则存在（exact → semantic → partial variant）
- JSON 输出格式指定
- per-type 指导已分离（`_ASSET_TYPE_GUIDANCE`）

**不足之处：**

| # | 问题 | 影响 |
|---|------|------|
| 1 | 无示例 — 只有抽象规则，跨模型行为不一致 | 匹配质量不稳定 |
| 2 | 变体规则不完整 — 只说 "Jack" vs "Jack.smile"，未覆盖 `_`、`-` 分隔符、多级变体 | 变体匹配可能失败 |
| 3 | 语义匹配指导模糊 — "semantically related" 太宽泛 | 质量依赖模型自行理解 |
| 4 | 无平局规则 — 两个条目同等匹配时无决策依据 | 随机或错误格式 |
| 5 | Type guidance 过于通用 — 两种类型区分度不够 | 未充分利用 per-type 分化 |

### 关键设计决策

#### D1. 是否加入 Few-Shot 示例？

| | 不加示例 | 加 1-2 示例 |
|---|---|---|
| Token 开销 | 更低 | 每个示例 ~100-200 tokens |
| 一致性 | 依赖模型自行理解 | 示例锚定行为 |
| 跨模型稳定性 | 不同模型对抽象规则解读不同 | 示例减少歧义 |

**建议：加一个示例。** 匹配是低概率路径（大多程序匹配成功），token 开销不敏感。

#### D2. 变体命名规则形式化

导演 LLM 使用的 local_name 遵循 `base.variant` 或 `base_variant` 模式。到达 LLM 匹配时一定不是精确匹配（精确匹配已被程序处理），所以 LLM 的核心任务就是变体识别 + 语义匹配。Prompt 应显式列出分隔符和匹配策略。

#### D3. 平局规则

两个条目同等匹配时 → **选第一个列出**。

理由：平局意味着模型无法区分——任何规则都是任意的。选择最简单的规则。列表顺序是确定的（dict insertion order），行为可预测。

#### D4. 用户消息中条目的展示格式

保持当前格式 `- "Jack": A cheerful young man with brown hair`。简洁有效。

---

## Prompt 草案

### 1. System Prompt（核心，所有类型共享）

```
You are an asset matcher in a visual novel game engine pipeline.

An AI narrative director writes story text and refers to characters
and locations by name.  Programmatic exact-match has already been
attempted and failed — so the target name will NOT match any entry
exactly.  Your job is to find the closest match.

This is a FORCED CHOICE.  You MUST return exactly one entry, even if
the match is imperfect.  The engine has no fallback — if you return
nothing, the scene will appear without visuals.

## Matching Rules (apply in order)

1. NAME VARIANT — the target is a variation of an entry's local_name.
   Delimiters ".", "_", "-" separate a base name from detail suffixes:
   "Jack.smile" → "Jack", "forest_night" → "forest".
   Match the base name (part before the first delimiter).

2. SEMANTIC MATCH — the entry whose local_description is most
   semantically similar to the target name.  Consider synonyms,
   related concepts, and thematic association.

3. TIE-BREAK — if multiple entries are equally good, pick the one
   listed first.

## Output Format

Reply ONLY with a valid JSON object:
{"selected": "<exact local_name from the list>"}

## Example

Target: "Alice.happy"
Entries:
- "Alice": "A young woman with blue hair and a gentle smile"
- "Bob": "A tall warrior in plate armor"
- "Queen": "An elderly ruler with silver crown"

Select "Alice" — it's a name variant (base "Alice" matches "Alice.happy").
```

### 2. Per-Type Guidance（追加到 System Prompt 后）

#### CHAR_PORTRAIT

```
## Character Portrait Matching

Character names may carry emotion/pose/outfit suffixes:
"Alice.angry", "Bob_smile", "Charlie-casual".

Local descriptions typically describe appearance, clothing,
personality, or role.  When the base name doesn't match any
entry, use the description to find the character whose traits
best fit the target's implied identity.
```

#### BACKGROUND

```
## Background Scene Matching

Location names may carry time/weather/variant suffixes:
"forest.night", "castle_dusk", "beach-sunset".

Local descriptions typically describe atmosphere, setting, mood,
or architectural features.  When the base name doesn't match,
prefer the location whose environment and atmosphere best fit
the target.
```

### 3. User Message（`build_match_messages` 构建）

```
Target: "Jack.smile"
Type: Character Portrait

Available entries:
- "Jack": A cheerful young man with brown hair
- "Alice": A mysterious woman in black
- "Old Man": An elderly wizard with a long beard

Select the best match for "Jack.smile".  Remember: exact match already
failed — look for variants or semantic similarity.
```

---

## 待讨论的开放问题

### Q1. 示例位置
放在 System Prompt 中 vs 作为独立的 User/Assistant 消息对？

System Prompt 中更简洁；独立消息对更接近对话格式但需改 `build_match_messages` 签名。**倾向 System Prompt 中。**

### Q2. 单条目优化
roster 只有一个条目时，是否在代码层面直接返回（不调 LLM）？

省一次 API 调用。**倾向在 `MatchProcessor.__call__` 中加判断：len(entries) == 1 → 直接返回唯一 key。**

### Q3. Description 截断
story_config 中的 description 可能很长（如详细外貌描述）。是否需要在 Prompt 中截断？

**倾向不截断**——模型自行判断相关信息。但超过 500 字符可能导致匹配质量下降，需要后续实际测试验证。

### Q4. 置信度标注
是否加 `{"selected": "...", "confidence": "low"}`？

调用方已有两阶段重试机制，额外复杂度收益有限。**倾向不加。**

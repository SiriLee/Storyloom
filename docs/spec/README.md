# Text Mode Spec — 文本模式规范索引

> Phase 1 文本模式的权威实现规范。与 `docs/graph-mode-spec/`（Phase 2 图像模式规范）对等权威。

## 文档地图

| 文档 | 内容 | 受众 |
|------|------|------|
| [`exec-flow.md`](./exec-flow.md) | 程序执行管线（启动→结局）——主文档 | 开发者、AI 工具 |
| [`block-spec.md`](./block-spec.md) | XML 元素语法、编号规范、分支路由、状态校验 | 开发者 |
| [`prompt-design.md`](./prompt-design.md) | 全阶段 Prompt 模板、对话式消息数组架构 | 开发者、调试者 |
| [`data-model.md`](./data-model.md) | GameState、存档系统、常量、约定 | 开发者 |

## 阅读顺序

### 首次了解
1. [`exec-flow.md`](./exec-flow.md) — 理解程序执行管线
2. [`block-spec.md`](./block-spec.md) — 理解 XML 输出格式
3. [`prompt-design.md`](./prompt-design.md) — 理解 Prompt 模板和对话架构

### 开始实现
1. [`exec-flow.md`](./exec-flow.md) — 执行管线（主文档）
2. [`block-spec.md`](./block-spec.md) — XML 格式（实现解析器时参考）
3. [`prompt-design.md`](./prompt-design.md) — Prompt 模板（实现 prompt_builder 时参考）
4. [`data-model.md`](./data-model.md) — 数据结构（实现 GameState 和存档时参考）

## 权威层级

```
spec/exec-flow.md        ──── 执行流程 — 回答"怎么做"（权威）
spec/block-spec.md       ──── XML 元素规范（权威）
spec/prompt-design.md    ──── Prompt 模板（权威）
spec/data-model.md       ──── 数据模型（权威）
```

**与 theory 的关系**：`docs/theory/` 定义设计原则与约束（从第一性原理推导），spec 定义满足这些约束的具体实现。两者同等权威——theory 回答"为什么这样设计"，spec 回答"如何实现这个设计"。若 spec 与 theory 冲突，以 theory 为准（theory 是更根本的约束）。

**冲突解决**：Prompt 格式以 `prompt-design.md` 中的当前模板为最终标准。engineering-journal 记录历史决策，spec 和 theory 反映当前规范——如不一致，以 spec / theory 为准。

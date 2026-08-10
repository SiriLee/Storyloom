# Graph Mode Spec — 图像模式规范索引

> Phase 2 图像模式的完整程序设计文档。与 `docs/spec/`（Phase 1 文本模式规范）对等权威。

## 文档地图

| 文档 | 内容 | 状态 |
|------|------|------|
| [`design.md`](./design.md) | 图像模式完整程序设计——数据模型、管线架构、事件/任务系统、AI 角色、流程定义、实现方案 | **权威** |
| [`design-draft.md`](./design-draft.md) | 设计草稿——早期探索版本，部分内容与权威版不一致 | 参考 |
| [`prompt-design.md`](./prompt-design.md) | 图像模式叙事 Prompt 模板（ROUND1 / CONTINUE） | 权威 |
| [`prompt-design-llm-match.md`](./prompt-design-llm-match.md) | §7.8a LLM 素材匹配 Prompt | 权威 |
| [`prompt-design-llm-generate.md`](./prompt-design-llm-generate.md) | §7.8b LLM 素材生成选择 + AI 图像生成 Prompt | 权威 |

## 与 Phase 1 文档的关系

- **理论层**（`docs/theory/`）：共享。`first-principles.md`、`bridge-mechanism.md`、`streaming-parse.md`、`asset-generation.md` 对两模式同等适用。
- **规范层**：`docs/spec/` 定义 Phase 1 文本模式。`docs/graph-mode-spec/` 定义 Phase 2 图像模式。两者对等权威。
- **API 层**（`docs/api/`）：共享。核心 API（`GameSession`、`CoCreateFlow`）不变，图像模式通过 `game_mode` 配置切换。

## 阅读顺序

### 首次了解图像模式
1. [`design.md`](./design.md) §1 — 概述与设计目标
2. [`design.md`](./design.md) §3 — 管线架构（核心变更）
3. [`design.md`](./design.md) §4 — 事件与任务系统
4. [`design.md`](./design.md) §6 — 流程解析

### 开始实现
1. [`design.md`](./design.md) §7 — 实现方案（9 步分阶段方案）
2. [`design.md`](./design.md) §2 — 素材数据模型（数据层实现）
3. [`design.md`](./design.md) §5 — AI 角色与提示词（Prompt 实现）

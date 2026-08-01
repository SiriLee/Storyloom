# Storyloom 文档索引

## 文档地图

| 文档 | 内容 | 受众 | 权威性 |
|------|------|------|--------|
| [`theory/`](./theory/) | 设计理论基础——第一性原理、桥接机制、流式解析、素材生成 | 所有开发者 | **权威** |
| [`spec/exec-flow.md`](./spec/exec-flow.md) | Phase 1 程序执行管线（启动→结局） | 开发者、AI 工具 | **权威** |
| [`spec/block-spec.md`](./spec/block-spec.md) | XML 元素语法、编号规范、分支路由、状态校验 | 开发者 | **权威** |
| [`spec/data-model.md`](./spec/data-model.md) | GameState、存档系统、常量、约定 | 开发者 | **权威** |
| [`spec/prompt-design.md`](./spec/prompt-design.md) | 全阶段 Prompt 模板、对话式消息数组架构 | 开发者、调试者 | **权威** |
| [`engineering-journal.md`](./engineering-journal.md) | 工程日志——完整设计决策时间线（2026-07-02 → 至今） | 开发者、审查者 | 参考 |
| [`api/co-create.md`](./api/co-create.md) | 共创 API 参考（供界面层开发者） | 界面层开发者 | 参考 |
| [`api/session.md`](./api/session.md) | GameSession 集成 API 参考（供界面层开发者） | 界面层开发者 | 参考 |
| [`superpowers/specs/2026-07-17-user-config-design.md`](./superpowers/specs/2026-07-17-user-config-design.md) | UserConfig 模块设计 | 开发者 | 设计 |
| [`superpowers/specs/2026-07-20-web-packaging-design.md`](./superpowers/specs/2026-07-20-web-packaging-design.md) | Web UI 打包方案设计 | 开发者 | 设计 |
| [`superpowers/plans/2026-07-17-user-config-implementation.md`](./superpowers/plans/2026-07-17-user-config-implementation.md) | UserConfig 实现计划 | 实现者 | 计划 |
| [`superpowers/plans/2026-07-20-web-packaging.md`](./superpowers/plans/2026-07-20-web-packaging.md) | Web UI 打包实现计划 | 实现者 | 计划 |
| [`superpowers/specs/2026-07-07-api-audit-and-interface-design.md`](./superpowers/specs/2026-07-07-api-audit-and-interface-design.md) | API 审计与界面集成设计 | 界面层开发者 | 设计 |
| [`superpowers/plans/2026-07-07-api-interface-implementation.md`](./superpowers/plans/2026-07-07-api-interface-implementation.md) | API 接口实现计划 | 实现者 | 计划 |
| [`superpowers/specs/`](./superpowers/specs/) | 功能设计规格（按日期归档） | 设计者、审查者 | 参考 |
| [`superpowers/plans/`](./superpowers/plans/) | 实现计划（按日期归档） | 实现者 | 参考 |

## 推荐阅读顺序

### 首次了解项目
1. [`theory/README.md`](./theory/README.md) — 理解项目核心问题与设计哲学
2. [`spec/exec-flow.md`](./spec/exec-flow.md) — 理解程序执行管线
3. [`spec/block-spec.md`](./spec/block-spec.md) — 理解 XML 输出格式
4. [`spec/prompt-design.md`](./spec/prompt-design.md) — 理解 Prompt 模板和对话架构

### 开始实现
1. [`spec/exec-flow.md`](./spec/exec-flow.md) — 执行管线（主文档）
2. [`spec/block-spec.md`](./spec/block-spec.md) — XML 格式（实现解析器时参考）
3. [`spec/prompt-design.md`](./spec/prompt-design.md) — Prompt 模板（实现 prompt_builder 时参考）
4. [`spec/data-model.md`](./spec/data-model.md) — 数据结构（实现 GameState 和存档时参考）

### 审查设计
1. [`spec/exec-flow.md`](./spec/exec-flow.md) + 配套 spec — 完整规范
2. [`engineering-journal.md`](./engineering-journal.md) — 按时间线追踪每个设计决策的背景与依据
3. [`superpowers/specs/`](./superpowers/specs/) — 历史设计决策和演变过程

## 权威层级

```
theory/                  ──── 设计理论 — 回答"为什么"（同等权威）
spec/exec-flow.md        ──── 执行流程 — 回答"怎么做"（同等权威）
spec/block-spec.md       ──── XML 元素规范（同等权威）
spec/prompt-design.md    ──── Prompt 模板（同等权威）
spec/data-model.md       ──── 数据模型（同等权威）
```

**theory 与 spec 的关系**：theory 定义设计的原则与约束（从第一性原理推导），spec 定义满足这些约束的具体实现。两者同等权威——theory 回答"为什么这样设计"，spec 回答"如何实现这个设计"。实现必须同时满足 spec 的规定和 theory 的约束。

**冲突解决**：spec 文档之间应保持一致。Prompt 格式以 `prompt-design.md` 中的当前模板为最终标准。engineering-journal 记录历史决策，spec 和 theory 反映当前规范——如不一致，以 spec / theory 为准。若 spec 与 theory 冲突，以 theory 为准（theory 是更根本的约束）。

## 扩展路线

### Phase 1 — CLI 纯文本 MVP（核心引擎 + Web UI 已实现）
终端 CLI、LLM 自定义变量、共创阶段变量定义、固定选项、自动存档。Web 界面（FastAPI + SSE + SPA）已提前完成——主菜单、共创聊天、游戏视图、冒险日志、设置、鸣谢。独立二进制打包（PyInstaller）+ pip wheel。版本 1.0.0。
> **注意**：Web 界面原属 Phase 2，已被提前实现并完全功能化。

### Phase 2 — 动态系统增强
- **变量系统增强**：可用变量数扩展至 10+，支持更复杂的数值约束
- **向量记忆**：角色/地点/事件 embed 存储，每轮检索注入 Prompt
- **多模型**：叙事用主力模型，审查/追问用便宜模型
- **图像模式**：静态背景 + 角色立绘，共创预设 + 部分实时生成

### Phase 3 — 完整体验
- **图像生成** — 关键场景异步生成插画
- **云同步** — 存档加密上传，跨设备同步
- **TTS** — 可选角色语音朗读
- **剧本导出** — 冒险历史格式化为 Markdown/PDF
- **多人模式** — 不同玩家扮演不同角色，AI 居中叙述协调

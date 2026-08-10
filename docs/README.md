# Storyloom 文档索引

## 目录结构

| 目录 | 内容 | 入口 |
|------|------|------|
| [`theory/`](./theory/) | 设计理论基础——第一性原理、桥接机制、流式解析、素材生成 | [`README`](./theory/README.md) |
| [`spec/`](./spec/) | Phase 1 文本模式权威规范——管线、XML 格式、Prompt、数据模型 | [`README`](./spec/README.md) |
| [`graph-mode-spec/`](./graph-mode-spec/) | Phase 2 图像模式权威规范——管线、事件/任务系统、AI 角色、素材模型 | [`README`](./graph-mode-spec/README.md) |
| [`api/`](./api/) | API 参考——CoCreateFlow、GameSession（供界面层开发者） | — |
| [`engineering-journal.md`](./engineering-journal.md) | 工程日志——完整设计决策时间线 | — |
| [`superpowers/`](./superpowers/) | 历史归档——设计规格与实现计划（按日期） | — |

## 权威层级

```
theory/              ──── 设计理论 — "为什么"（权威）
spec/                ──── 文本模式规范 — "怎么做"（权威）
graph-mode-spec/     ──── 图像模式规范 — "怎么做"（权威）
```

**theory 与 spec 的关系**：theory 定义设计原则与约束（从第一性原理推导），spec 定义满足这些约束的具体实现。两者同等权威。若冲突，以 theory 为准。

**spec 与 graph-mode-spec 的关系**：两个 mode 的规范互相独立、对等权威。核心引擎共享，差别在于管线组件和 Prompt。

## 扩展路线

### Phase 1 — 文本模式 ✅
终端 CLI、LLM 自定义变量、共创阶段变量定义、固定选项、自动存档。Web 界面（FastAPI + SSE + SPA）。独立二进制打包（PyInstaller）+ pip wheel。

### Phase 2 — 图像模式 ✅
静态角色立绘 + 背景图片，视觉小说演出效果。素材管线（匹配 + 生成 + 预构建）、事件-任务系统、AI 角色扩展、自动更新。规范见 `graph-mode-spec/`。版本 2.0.0。

### Phase 3 — 完整体验（规划中）
- 变量系统增强、向量记忆、多模型
- 云同步、TTS、剧本导出、多人模式

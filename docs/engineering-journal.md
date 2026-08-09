# Storyloom 工程日志

> 按时间线记录每个设计决策的背景、动机与依据。倒序排列（最新在前），新日志插入文首。
>
> 格式约定：**背景**（为什么此时需要决策）→ **决策**（做了什么选择）→ **依据**（commit / spec 章节 / memory 文件）。

---

## 2026-08-09（周六）

> **概述**：§7.8c Pre-build 全栈实现 + §7.8b 收尾审查 + 稳定性修复 + 游戏模式徽章 UI。核心工作是将素材预构建管道从 spec 推进到完整可用的全栈实现——批量选择提示词设计、Prebuilder 管道（parse → 2× batch selection → concurrent generation → force-select fallback）、GameSession 集成（删除 `_init_stub_roster`）、SSE 流式端点、前端卡片网格 UI。共 **51 commits**，**36 files**，**+4,186/-427 lines**，测试从 993 增至 **1,030**（+37）。

### §7.8b 收尾 — Code Review 第三轮 + 重构

**背景**：§7.8b GenerateProcessor 前一日完成但遗留了若干代码质量问题——重复逻辑、dead code、API 边界模糊。需要在进入 §7.8c 之前做最终清理。

**决策**（commits `ee40d60` → `fbc180a` → `9b22782`，3 commits）：

1. **参考图收集统一**（`ee40d60`）：`collect_reference_data_urls()` 从 `_llm_generate.py` 内联实现 → `io/img_utils.py` 公共函数——供后续 Prebuilder 复用。
2. **第三轮审查修复**（`fbc180a`）：删除 dead code、补充缺失的 `warnings` 字段、移除未使用的 import。
3. **Task import 修复**（`9b22782`）：`_llm_generate.py` 缺少 `Task` 导入，导致运行时 `NameError`。

**依据**：`io/img_utils.py`；`tasks/_llm_generate.py`。

### §7.8c Pre-build — 批量选择提示词设计与验证

**背景**：`graph-mode-spec/design.md` §7.8c 定义 pre-build 管道的第一步是"批量 LLM 选择"——将 `story_config` 中的所有角色和场景一次性发给 LLM，从素材库中选出最佳匹配。这不同于 §7.8a 的逐条 MATCH（每个实体单独调用 LLM），需要设计全新的提示词模板和响应格式。

**决策**（commits `11c7c66` → `caee1fb` → `c2cb843` → `17d2ed4` → `ff718f0`，~15 commits）：

1. **四种独立提示词模板**（`11c7c66`）：`prebuild.py:build_batch_selection_messages()`——normal-CHAR、normal-BG、forced-CHAR、forced-BG，各自独立系统提示词 + 用户消息。模板使用真实 `sys_` ID 作为示例（如 `sys_knight`、`sys_temple`），避免 LLM 产生幻觉 ID。
2. **`run_batch_selection()` 独立函数**（`c2cb843`）：从 Prebuilder 类中抽出为模块级函数——build messages → call LLM → parse response。独立于 Prebuilder 生命周期，可在 prompt_lab 中直接导入测试。
3. **双格式自动检测**（`11c7c66`）：`parse_batch_selection_response()` 自动检测 forced 格式（无 `action` 字段，所有实体必须选 `selected_id`）vs normal 格式（有 `action` 字段，可选 `generate`）。
4. **`LLM_SELECT_THINKING` 环境变量覆盖**（`70f276e`）：匹配 `_select()` 中的同名机制——允许 prompt_lab 脚本在不修改代码的情况下切换 thinking 模式进行 A/B 对比。
5. **移除所有 `max_tokens` 限制**（`f7a715b`）：从 `run_batch_selection`、`_call_llm`（match）、prompt_lab 测试中全部移除——默认 API 限制足以防止 thinking token 消耗导致的空响应。
6. **解析错误诊断**（`581c78f`）：`parse_batch_selection_response()` 在解析失败时附带原始响应片段（前 200 字符），便于调试 LLM 输出格式问题。
7. **Semantic accept-sets 验证**（`53de7b7`）：prompt_lab 测试使用 per-entity `accept` 集合验证语义正确性——匹配 `test_llm_generate.py` 的测试模式。

**Prompt_lab 验证结果**（`tests/prompt_lab/test_prebuild_selection.py`，472 行）：
- 10 个场景：zh-CN 校园/武侠 + en fantasy，normal + forced 模式
- **disabled thinking: 17/20 PASS**（2 轮平均），与 light 模式质量相当
- 每次调用 ~1.5s（disabled）vs ~12s（light）——**8 倍速度差**
- 使用真实 system_media 素材（25 portraits + 26 backgrounds）

**依据**：`core/prebuild.py`（909 行）；`tests/prompt_lab/test_prebuild_selection.py`；[[2026-08-09-7.8c-prebuild-implementation]]。

### §7.8c Pre-build — Prebuilder 管道与会话集成

**背景**：批量选择只是第一步。完整的 pre-build 管道需要：parse entities → batch selection → seed roster → concurrent image generation → force-select fallback → hard verification → persist。此外需要删除旧的 `_init_stub_roster()` stub 实现，将 Prebuilder 挂入 GameSession 生命周期。

**决策**（commits `e793dd2` → `3cec691`，~8 commits）：

1. **`generate_asset_image()` 抽离**（`e793dd2`）：从 `GenerateProcessor._generate()` 中提取为独立函数——供 Prebuilder 在线程池中并发调用图像生成。
2. **`select_forced` 公共 API**（隐式，`tasks/__init__.py`）：`select_forced` 提升为 `tasks` 包公开导出——P rebuild 的 force-select fallback 需要直接调用。
3. **`img_prompts.py` 提取**（同前）：`build_generation_prompt()` 从 `_llm_generate.py` → `io/img_prompts.py`——分离提示词构建与处理器逻辑。
4. **P rebuild 管道**（`11c7c66`）：`Prebuilder.build()` 完整管道：
   - Phase 1: `parse_entities()` — 从 `story_config` 提取角色/场景
   - Phase 2: 2 个并发 `run_batch_selection()` — CHAR 和 BG 独立
   - Phase 3: `_seed_roster()` — 将选中素材注册到 GameAssetRoster
   - Phase 4: `_concurrent_generate()` — ThreadPoolExecutor 并发图像生成
   - Phase 5: `_force_select_all()` — 生成失败项的强制选择回退
   - Phase 6: `_hard_verify()` — 最终验证，失败项静默降级
   - 单次 `library.save()` 在管道末尾（线程池外部——避免 P0 竞态条件）
5. **Phase 事件**（`3cec691`）：添加 `"seeded"` phase——在 batch selection 完成、roster 种子化后触发，让 UI 在图像生成开始前展示选中结果。
6. **`_init_stub_roster()` 删除**（`caee1fb`）：P rebuild 替代了 stub 实现。`GameSession.prebuilt_assets()` 重写为生成器（曾为同步 stub）。
7. **Roster 预清除**（`e0cd4ba`）：prebuild 开始前清除 roster——防止重启 prebuild 时的陈旧条目残留。
8. **P rebuild 完成前持久化**（`5d45985`）：在 `yield prebuild_complete` 之前保存 roster——确保 SSE 客户端收到完成事件时数据已落地。
9. **GameLoop 复用**（`bbe2e29`）：`prebuild_assets()` 复用已存储的 `GameLoop` 实例而非创建新的——添加公开 `library` 属性供 Prebuilder 访问。

**测试**：`tests/test_prebuild.py`（1,086 行，44 tests）——EntitySpec 解析（9）、消息构建（6）、响应解析（10）、P rebuild 管道（11）、集成（8）。全部 mock API，零网络依赖。

**依据**：`core/prebuild.py`；`core/session.py:81-143`；`core/game_loop.py`；`tests/test_prebuild.py`；[[2026-08-09-7.8c-prebuild-implementation]]。

### §7.8c Pre-build — SSE 流式端点 + 前端卡片网格

**背景**：prebuild 管道涉及多个 LLM 调用 + 图像生成，总耗时可能 30-60 秒。同步 HTTP 端点会导致前端超时，用户看不到进度。需要 SSE 流式端点逐 phase 推送状态更新，前端以卡片网格形式展示实时进度。

**决策**（commits `0dc8a94` → `64676fb`，4 commits）：

1. **SSE 端点转换**（`0dc8a94`）：`POST /api/co-create/prebuild` → `StreamingResponse`——`asyncio.Queue` + 后台线程消费 `prebuild_assets()` 生成器，逐事件推送到 SSE。格式：`data: {"phase": "...", ...}\n\n`。
2. **生成端点数据透传**（`0ce778a`）：`/api/co-create/generate` 和 `/api/co-create/generate-stream` 在响应中返回 `characters` 和 `locations`——prebuild 端点需要这些数据构建 `story_config`。
3. **卡片网格 UI**（`c1e30c6`）：`co-create.js` 新增 prebuild 卡片网格——每张卡片对应一个实体（角色/场景），显示名称 + 匹配/生成状态 + 缩略图。SSE 事件驱动状态更新（`prebuild_progress` → 更新卡片，`prebuild_complete` → 全部就绪）。
4. **HTML + 错误传播加固**（`64676fb`）：卡片 HTML 模板容错（缺失字段不回退为空字符串），SSE 错误事件正确传播到前端 toast。

**依据**：`web/server.py:348-357` → SSE；`web/static/js/co-create.js`；`web/static/css/main.css`。

### Thinking 模式决策最终化

**背景**：§7.8a/§7.8b 使用 LLM 进行素材选择和匹配。需要在速度和质量之间做权衡——light thinking 提供推理链但增加 8-12 倍延迟，disabled thinking 速度快但缺少推理步骤。

**决策**（commits `ec4e51c` → `104c80b` → `4e25192` → `33ad106`，4 commits）：

| 调用场景 | 模式 | 理由 |
|----------|------|------|
| `run_batch_selection`（prebuild Step 1） | **disabled** | 简单描述比较任务，light 增加 8x 延迟无质量增益 |
| `_select`（DECLARE 游戏内选择） | **disabled** | 现有默认值 |
| `_select_forced`（回退选择） | disabled → enabled → **程序化** | 沿用 `_llm_generate.py` 现有两阶段模式 |

**关键**：`33ad106` 从生产代码中移除了 `LLM_SELECT_THINKING` 环境变量覆盖——env var 仅限 prompt_lab 脚本使用，生产代码走硬编码默认值。这避免了用户意外切换 thinking 模式导致行为不一致。

**依据**：`tasks/_llm_generate.py`；`core/prebuild.py`；[[2026-08-09-7.8c-prebuild-implementation]]。

### 系统素材工具链收尾

**背景**：系统素材需要工作流文档 + 额外预设。

**决策**（commits `fd97e10`，1 commit）：
1. **工作流 README**：`system_media_src/README.md`（69 行）——素材生成→打包→集成的完整工作流文档
2. **新增预设**：`sys_temple` 精修 + `sys_church` 新增——背景库从 25 增至 26 个

**依据**：`system_media_src/README.md`；`system_media_src/background_img.json`。

### 稳定性修复

**背景**：多个独立 bug 在 prebuild 集成测试和日常使用中发现。

**决策**（commits `5bbac39` → `ef2f877`，7 commits）：

1. **PARSE_ERROR 非致命**（`5bbac39`）：LLM 返回无法解析的 XML 时，`StreamParser` 发送 `PARSE_ERROR` 事件但不应杀死游戏流——改为记录服务端日志 + 继续流式传输剩余内容。
2. **Delete game 加载已有库**（`f2e13c9`）：`delete_game()` 错误地创建空 `AssetLibrary` 而非加载已有文件——导致删除操作覆盖了其他游戏的素材注册。修复为加载已有库后移除目标游戏条目。
3. **统一媒体服务**（`bd59815` → `c0c590c`）：重构 FastAPI 静态文件挂载——`/media/` 端点使用 type 驱动的扩展名解析（`AssetType.default_extension`），`/media/system/` 新增 system_media 目录服务——`sys_` 素材图片可在 UI 中显示。
4. **Typewriter 跳过修复**（`97bf03d`）：`_skipTypewriter` 显示部分文本而非完整文本——原因是跳过逻辑在文本完全累积前就截断了。修复为跳过时立即显示全部已缓冲文本。
5. **Roster 持久化**（`ef2f877`）：`GameAssetRoster` 在每次变更（`set_target`、`clear` 等）后持久化到磁盘——匹配 `AssetLibrary` 的即时保存模式——防止进程崩溃时丢失素材映射。

**依据**：`web/server.py`；`core/save_manager.py`；`assets/_roster.py`；`web/static/js/graph-renderer.js`。

6. **CI 测试自包含修复**（`c29c7b7`）：`test_game_loop.py` 中 2 个 GraphPipeline 测试依赖 `system_media/` 目录（生成产物，不入库），导致 CI 上 1028/1030 失败。修复：`test_mount_registers_system_assets` 构建临时 manifest + patch `DEFAULT_SYSTEM_MEDIA_DIR`；`test_mount_sets_process_factory` 用 `fake_global` 素材种子库替代对 `sys_adult_female` 的外部依赖。

### UI 改进 — 游戏模式徽章

**背景**：用户需要在保存列表和游戏预览中看到每个存档的游戏模式（文本/图模式），以便区分不同类型的游戏体验。

**决策**（commits `2a84920` → `3db3ee6`，5 commits）：

1. **徽章组件**（`2a84920`）：保存列表卡片 + 游戏预览界面显示模式徽章——文本模式显示 `TXT`，图模式显示 `VN`。通过 `game_mode` 字段从后端传递到前端。
2. **位置迭代**（`c7c2fab` → `da7a156`）：保存列表中徽章固定在标题右侧，游戏预览中徽章放在 premise 文本之后——经过 3 轮位置调整找到最优布局。
3. **尺寸平衡**（`3db3ee6`）：缩减徽章尺寸 + 调整间距——避免徽章过于突兀，与整体卡片布局保持视觉平衡。

**依据**：`web/static/css/main.css`；`web/static/js/co-create.js`；`web/static/js/state.js`。

---

## 2026-08-08（周六）

> **概述**：§7.8a LLM Match 全栈实现 + §7.8b LLM Generate 全栈实现 + CI/CD 基础设施 + 系统素材工具链收尾。MatchProcessor 和 GenerateProcessor 是两个独立的 LLM 驱动任务处理器，分别负责素材匹配和素材生成选择，构成图模式素材管道的最后两块拼图。thinking presets 从任务模块抽离到 I/O 层作为共享基础设施。共 **43 commits**，**29 files**，**+3,992/-412 lines**，测试从 847 增至 **993**（+146）。

### §7.8a MatchProcessor — LLM 素材匹配

**背景**：`graph-mode-spec/design.md` §5.4 定义 MATCH 任务需要 LLM 从 roster 中选择最佳素材。此前只有 stub 实现（无操作），需要一个完整的 LLM 驱动匹配器：支持 thinking 预设、两阶段重试、解析容错、静默降级。

**决策**（commits `c86bacb` → `5d02b51` → `dbfc64e` → `0d5c902` → `f6fdc59` → `c6fdce6` → `c4d5553`，7 commits）：

1. **MatchProcessor 实现**（`c86bacb`）：`src/storyloom/tasks/_llm_match.py`（261 行）——实现 `__call__(asset_type, local_name, roster)` 协议。两阶段匹配：禁用 thinking → 轻量 thinking → 静默降级。解析容错三级：JSON → 子串扫描 → None（无需 "first entry" fallback）。范围仅限 roster，不查 AssetLibrary（per design.md §5.4）。

2. **TaskGenerator 接口拆分**（`c86bacb`）：`__init__` 改为接受 `match_processor=` 和 `generate_processor=`（替代旧的 `process_factory=`），两者默认 `None`——无处理器时任务同步完成为 no-op。

3. **Thinking Presets 抽离**（`dbfc64e`, `0d5c902`）：从 `_llm_match.py` 内联实现 → `src/storyloom/io/thinking.py`（168 行）——I/O 层的规范位置。9 个模型家族：deepseek、claude、gemini、qwen、glm、gpt（OpenAI）、kimi（Moonshot）、grok（xAI）、doubao（ByteDance）。全部验证自官方 API 文档（2026-08）。

4. **Thinking 预设修正**（`0d5c902`）：Qwen 格式从 `enable_thinking` 修正为 `thinking_enabled`（与官方文档一致）。已知限制以代码注释记录：Claude ≥4.7 `budget_tokens→400`，Gemini 2.5 Pro `thinking_budget=0→400`，gpt-5-mini `reasoning_effort="none"→400`。

5. **Match 提示词定稿**（`f6fdc59`）：四种素材类型各自系统提示词 + 统一用户消息模板。新增 `docs/graph-mode-spec/prompt-design-llm-match.md`（72 行）。

6. **提示词实验室脚本**（`c6fdce6`）：`tests/prompt_lab/test_llm_match.py`（274 行）——11 个测试用例，流式 TTFT 测量，中文场景覆盖。

7. **GameLoop 集成**（`c4d5553`）：`game_loop.py:757-760` 创建 MatchProcessor 并传入 TaskGenerator——完成 §7.8a 全链路。

**测试**：`tests/test_llm_match.py`（733 行，54 tests）——ThinkingPresets（16）、BuildMatchMessages（9）、ParseMatchResponse（8）、MatchProcessor（14）、Integration（2）。

**依据**：`graph-mode-spec/design.md` §5.4；[[2026-08-08-7.8a-llm-match-implementation]]；prompt-design-llm-match.md。

### §7.8b GenerateProcessor — LLM 素材生成选择

**背景**：当 MatchProcessor 找不到匹配素材时，需要 LLM 决定是回退到已有素材（forced match）还是触发 AI 图像生成。`graph-mode-spec/design.md` §7.8b 定义了 GENERATE 任务的双模式：正常选择 + forced 选择（MatchProcessor 失败后的回退）。

**决策**（commits `abbe87a` → `ebc360c` → `e54b5f8` → `29ed172` → `456c114` → `301ca22` → `88ac329` → `441b087` → `9371b17` → `6c293ab` → `713110a`，11 commits）：

1. **提示词设计文档**（`abbe87a`）：`docs/graph-mode-spec/prompt-design-llm-generate.md`（150 行）——定义三组提示词模板：正常选择（CHAR_PORTRAIT / SCENE_BG / DECORATIVE）、forced 选择（LLM must choose）、AI 图像生成（CHAR_PORTRAIT / SCENE_BG）。

2. **配置常量化**（`ebc360c`）：`GENERATE_LIBRARY_TOP_N`（global library top-N 截断）、`GENERATE_REF_IMAGE_COUNT`（参考图数量）加入 `config.py`。

3. **normalize_background 迁移**（`e54b5f8`）：从 `scripts/_sysgen_utils.py` → `src/storyloom/io/img_utils.py`——进入生产代码路径，供 GenerateProcessor 的图像 pipeline 使用。新增 `test_img_utils.py` 测试（82 行）。

4. **GenerateProcessor 实现**（`29ed172`）：`src/storyloom/tasks/_llm_generate.py`（609 行）——核心结构：
   - `_select_normal()` — 正常模式：LLM 自由选择（可选 AI 生成）
   - `_select_forced()` — 强制模式：LLM 必须选择（MatchProcessor 失败后）
   - `_collect_reference_images()` — 收集参考图（从 roster target 获取图片数据，推导 MIME 类型）
   - `_generate_image()` — 调用 ImgApiClient 生成图像
   - `_post_generate()` — 注册到 AssetLibrary + roster.set_target()
   - 解析容错：JSON → fallback（随机 library top-1）

5. **GameLoop 集成**（`456c114`）：`game_loop.py` 创建 GenerateProcessor 并传入 TaskGenerator，完成 §7.8b 全链路。

6. **§7.8b 审计修复**（`301ca22`）：移除 dead `media_dir` 参数，补充 test coverage 缺口。

7. **Bug 修复链**（`88ac329` → `713110a`）：
   - `88ac329`：添加 Task import，消除 `_select_forced` 中重复的 LLM 调用逻辑
   - `441b087`：reference image 的 MIME 类型从实际图片格式推导（非硬编码）
   - `9371b17`：使用 `AssetType.default_extension` 作为 MIME fallback
   - `713110a`：`_post_generate` 中 `roster.set_target()` 后持久化 AssetLibrary——防止素材注册丢失

**测试**：`tests/test_llm_generate.py`（1075 行，51 tests）。

**依据**：`graph-mode-spec/design.md` §7.8b；`config.py` GENERATE 常量；prompt-design-llm-generate.md；test_llm_generate.py。

### CI/CD 基础设施

**背景**：项目此前无 CI，测试仅在本地运行。需要自动化的测试验证 + 动态徽章展示。

**决策**（commits `1632647` → `a9f2d13` → `467a0ed` → `ca19d6c`，4 commits）：

1. **README 架构图**（`1632647`）：mermaid 流程图替代纯文本描述
2. **硬编码徽章移除**（`a9f2d13`）：删除 README 中手动维护的 tests badge
3. **GitHub Actions 测试工作流**（`467a0ed`）：`.github/workflows/test.yml`（73 行）——`ubuntu-latest`，Python 3.11，pytest 全量 + 动态徽章（`badges/tests-badge.svg`）
4. **CI 修复**（`ca19d6c`）：修复 CI 中 `pytest: command not found`——改用 `python -m pytest`

**依据**：`.github/workflows/test.yml`。

### 系统素材工具链收尾

**背景**：系统素材（预置背景/立绘）需要完整的生成→打包→分发工具链，集成到 PyInstaller 构建流程。

**决策**（commits `f925c44` → `376e5c5`，含中间修复，~10 commits）：

1. **Prompt 源 + Manifest 生成器**（`f925c44`）：`system_media_src/` 目录结构——提示词模板 + `generate_manifest.py` 清单生成器
2. **素材生成脚本**（`1a9dad6`）：`generate_single_asset.py`（单素材）+ `generate_system_assets.py`（批量）——从 manifest 读取预设，调用 ImgApiClient 生成
3. **批量修复**（`bdba432`）：修复双重 UserConfig 实例化、`--only`/`--start` 参数交互、模型预设扩展
4. **Aspect Ratio 强制**（`7a9c376`）：所有背景预设强制 16:9 + 后裁剪安全网
5. **打包脚本重写**（`8f58bec`, `7a8b2b9`, `376e5c5`）：`pack_system_media.sh`（155 行）替代废弃的 `setup_system_media.sh`——生成 ZIP 包→`build.sh` PyInstaller 集成
6. **ImgApiClient 重构**（`f0133f3`）：`img_remove_bg` → `portrait_remove_bg`（语义明确），`remove_bg` 参数改为显式传入

**依据**：`pack_system_media.sh`；`build.sh`；`config.py`。

### UI 改进

1. **图像生成开关**（`1c60839`, `446e7d8`）：设置页面新增 `img_generation_enabled` 复选框 + 可折叠 API 设置组——控制是否允许 AI 图像生成（成本控制）
2. **README 文档**（`d6ff233`）：补充 `[bg]` extra 标签使用说明 + 模型下载链接

**依据**：UserConfig `img_generation_enabled`；web UI settings。

---

## 2026-08-07（周五）

> **概述**：§7.6 Pipeline 集成收尾 + §7.7 图模式 UI 全栈实现 + 素材管理 UI 起步。一天内完成从 spec 撰写到可玩 VN 原型的完整闭环——后端 event→task 管道、前端 graph-renderer.js 渲染模块、游戏模式选择器、队列共享架构、自动/手动速度系统、场景过渡动画、最终审计与 33 项 bug 修复。共 61 commits，51 files，+9443/-282 lines，测试从 744 增至 847（+103）。

### §7.6 Pipeline 集成 — Event→Task 管道上线

**背景**：`graph-mode-spec/design.md` §3-4 定义 StreamParser→TaskGenerator→TaskPool 管道，§7.6 要求将其接入真实 GameLoop 流程。此前 §7.4 stub 框架和 §7.5 parser 扩展已就位，但 GameLoop 尚未调用 `consume_event()`。

**决策**（commits `475c6e3` → `05937d6` → `9888ebb` → `c739c41` → `8c320ed` → `450ea13` → `052f081` → `8de6c63`）：

1. **场景跨轮次连续性测试**（`475c6e3`）：Round 1→StateManager→Round 2 链条——验证 SCENE 事件在跨轮次时正确保留 `current_scene`

2. **§7.6 Pipeline 集成**（`9888ebb`）：GameLoop 的 `stream_round()` 调用 `consume_event()` 处理 SCENE/DECLARE 图像事件，TaskGenerator 产出 Task→TaskPool 异步执行→结果通过 `assets` key 传播到 UI dict

3. **Prompt 驱动 E2E 测试**（`c739c41`）：`tests/test_pipeline_integration.py`（766 行）——完整模拟 LLM 返回图像标签→parser→TaskGenerator→TaskPool→EventDispatcher 全链路

4. **§7.6 Review 硬化**（`8c320ed`）：11 项 source review findings 修复——GENERATE stub 行为、注释准确性、幂等性边缘情况

5. **Graph-mode PromptBuilder 接入**（`052f081`）：`build_round1_graph()` / `build_continue_graph()` 接入 GameLoop，图模式与文本模式共享 `stream_round()` 主循环

6. **配置常量化**（`8de6c63`）：`DEFAULT_MEDIA_DIR` / `DEFAULT_SAVES_DIR` 加入 `config.py`——消除硬编码路径

### §7.7 图模式 UI — 从 Spec 到可玩原型

**背景**：Phase 2 图模式最后一环——将引擎侧的图像事件管道对接到用户可见的视觉小说界面。需要全新的前端渲染模块（graph-renderer.js）、样式系统（graph.css）、游戏模式选择与传递机制。

#### Spec 撰写（commits `183bada` → `b62a3b7`，7 commits）

1. **§7.7 UI 设计 spec**（`183bada`）：定义 VN 界面布局、事件类型映射、模式传递链
2. **迭代修订**（`8dc8c42`→`bcb30b2`→`2cc6954`→`158c9b2`→`780bf0b`）：补充 e2e 流程、事件处理、素材预构建、结局流程、i18n spec、手动素材库设计
3. **TDD 实现计划**（`b62a3b7`）：10 任务 15 文件

#### 后端实现（commits `0cbda7f` → `15c3a6c`）

1. **Stub 名册初始化**（`0cbda7f`, `96f9166`, `ff09880`）：`_init_stub_roster()` 从 `story_config` 提取角色名→预注册到 GameAssetRoster，替换硬编码 `__stub__` 占位符

2. **Static 路由**（`48d1ca9`）：FastAPI mount `/media/` 静态目录，`game_mode` 加入 API 响应

3. **素材预构建两阶段分离**（`15c3a6c`）：`/api/generate`（故事生成）→ `/api/prebuild`（素材预构建）——各自有引擎信号，解决前端无法区分生成失败和素材失败的问题

#### 前端实现

4. **前端基础设施**（`6d248c8`）：路由占位、CSS/JS 加载、模块入口

5. **graph.css**（`b2decb0`）：视觉小说样式表——固定视口、角色立绘层、场景背景层、打字机文本框、选择面板、沉浸模式

6. **graph-renderer.js**（`b82f8e7`）：VN 渲染模块——事件消费者（`showSegment`, `showScene`, `showChoices`, `showEnding`）、打字机效果、自动/手动模式、素材管理（`applyBackground`, `applySprite`, `clearSprite`）、回看面板、沉浸模式

7. **Graph mode 集成**（`e5aef7e`）：`game.js` 按 `game_mode` 分支到 `TextRenderer` 或 `GraphRenderer`；`router.js` 添加 `/play/graph` 路由；`co-create.js` 传递模式参数

#### 队列共享与 UX 迭代（commits `2a36e58` → `4cc94ea`）

8. **Save 端点 game_mode**（`2a36e58`）：save/load 端点写入/读取 `game_mode`，客户端 `localStorage` 存储

9. **移除重复代码**（`13f987d`）：`graph-renderer.js` 中重复的 `_flattenChoices` → 统一用 `TextRenderer._flattenChoices`

10. **测试硬化**（`b9423d4`, `5573949`）：3 个覆盖率缺口修复 + 服务端预构建/save game_mode 测试

11. **加载指示器统一**（`d2c43a3`）：1s 加载动画，graph 模式新增重试按钮

12. **游戏模式选择器**（`ea077bc`）：设置页面新增"游戏模式"下拉框——文本冒险 / 视觉小说（graph）

13. **模式标签 i18n**（`00bb295`）：Graph/Text 模式名走 gettext

14. **样式隔离**（`2f013e7`）：graph.css 全局样式 → scoped 到 `.vn-scene`，防止污染文本模式页面

15. **队列共享架构**（`b5468a9`）：文本和图模式共用 `_eventQueue` + `_displayTick`，仅渲染函数不同——核心设计决策（详见 [[2026-08-07-7-7-ui-implementation-session]]）

16. **SCENE 事件走队列**（`0fb026a`, `212d5a5`）：SCENE 从 SSE handler 直接应用改为入队→`_displayTick` 消费——与文本段同步（`6ba0300` 后续修复了 `clearSprite` 被 assets block 误包裹的问题）

17. **场景过渡动画**（`cdb3aeb`）：crossfade 过渡 + pacing 对齐

18. **长度自适应自动延迟**（`4cc94ea`）：根据文本长度动态计算 display time

19. **速度分档统一**（`e36d65a`）：3 档——慢(50ms/字)/中(15ms/字)/快(5ms/字)——共享常量，文本和 graph 模式一致

#### 最终审计与 33 项修复（commits `1549615` → `c59d8d2`）

20. **视口固定**（`1549615`, `d637b48`）：`position: fixed` 防止双滚动条；assets 应用时机从 SSE handler 移到 `_displayTick`

21. **i18n 补全**（`9d22b34`）：设置标签缺失项补充

22. **UX 打磨**（`215a318`）：场景延迟、存档筛选、文字稳定性、背景占位图

23. **背景渐变**（`340601e`）：默认 placeholder 背景调暗

24. **清除立绘修复**（`6ba0300`）：`clearSprite()` 移到 assets block 外部

25. **Mode 同步**（`40d2ac5`）：P1 修复——`graph-renderer.js._mode` 和 `game.js._mode` 双变量不同步导致自动模式永久卡死。新增 `onModeChange` 回调

26. **3 项 P2 打磨**（`9fa01d4`）：graph-renderer 小问题修复

27. **自动模式首段跳过**（`083bc02`）：P2 修复——`_currentText` 为空时不设 autoTimer，防止 timer 在打字机运行中触发跳过

28. **Stub MATCH 修复**（`18faedd`）：P2 修复——MATCH stub 路径不加入名册导致 LLM 即兴角色立绘消失

29. **打字机速度调整**（`e4b9139`）：快档 8→5 ms/字

30. **设置面板简化**（`08a3dc5`, `0281ddf`）：移除"文字速度"（打字机硬编码中速）；"自动延迟"→"显示速度"（快/中/慢），按钮顺序慢→中→快

31. **i18n 编译**（`e83dbb9`, `a734215`）：编译 .po→.mo + JS i18n dict；`i18n_compile.py` 新增 `__main__` 入口

32. **场景持久化**（`262ef94`）：`to_save_dict()`/`from_save_dict()` 写/读 `current_scene`；首轮 yield SCENE 恢复背景

33. **Overlay 简化**（`5351193`）：`showBacklog/showSettings/setImmersive(true)` 直接切手动不恢复——移除 `_pausedAuto` 标志

34. **Init 状态重置**（`c59d8d2`）：P2 修复——`_currentText` 在 `init()` 时重置，初始 scene 绕过队列直接应用

**重要经验教训**（详见 [[2026-08-07-7-7-ui-implementation-session]]、[[2026-08-07-7-7-final-audit-and-fixes]]）：
- 队列消费者（`_displayTick`）和打字机（`onAdvance`）职责边界必须清晰——打字机是纯展示层
- 不能改 `onAdvance` 回调指向——会破坏自动模式
- 跨模块状态同步使用回调模式（`onAdvance`, `onModeChange`）
- CSS 变量和 JS 常量不硬编码
- graph-renderer.js 的模块级变量在 `init()` 时必须手动重置

### 素材管理 UI 起步

**背景**：[[2026-08-07-7-7-final-audit-and-fixes]] 指出下一阶段为素材管理——浏览/管理 `media/` 下素材、`_asset_lib.json` CRUD、`use_count` 清理。用户直接开始了实现。

**决策**（commit `9d8b7aa`）：
- 14 files，+1029/-60 lines
- 后端：`/api/assets` CRUD 端点（`server.py` +74 行），`_library.py` 新增 API
- 前端：`assets.js`（298 行）素材浏览/管理界面，`main.css`（334 行）素材面板样式
- 路由：`router.js` 重构——支持 `/assets` 页面
- i18n：zh_CN/zh_TW .po 各 +44 行
- 测试：`test_web_server.py` +153 行

**依据**：
- commits: `9d8b7aa`
- memory: [[2026-08-07-7-7-final-audit-and-fixes]] §下一阶段
- `docs/graph-mode-spec/design.md`：§2.2 (AssetLibrary)、§9 (存储与文件)

### 关键数据

| 指标 | 值 |
|------|-----|
| 今日 commits | 61 |
| 文件变更 | 51 files, +9443/-282 |
| 测试数量 | 744 → 847 (+103) |
| 新建文件 | `graph-renderer.js`, `graph.css`, `assets.js`, `main.css`, `test_pipeline_integration.py` 等 |
| 两日合计（8/6-8/7） | 84 commits, ~78 files, ~+12.7k lines |

**依据**：
- memory: [[2026-08-07-7-7-ui-implementation-session]]、[[2026-08-07-7-7-final-audit-and-fixes]]
- 61 commits on 2026-08-07 (see `git log --since=2026-08-07`)
- pytest: 847 passed

---

## 2026-08-06（周四）

> **概述**：Phase 2 引擎侧核心实现日——§7.4 Task 框架 stub + §7.5 StreamParser 图模式扩展 + graph-mode PromptBuilder 三模块落地。同步完成 prompt-design 基线文档、两轮 test hardening、§7.5 E2E pipeline 测试。共 23 commits，27 files，+3216/-107 lines，测试从 720 增至 744。

### §7.4 Task 框架 Stub——TaskPool + TaskGenerator + consume_event

**背景**：`graph-mode-spec/design.md` §3-4 定义了 Event→Task 调度架构——StreamParser 产出 Event，EventDispatcher 通过 `consume_event()` 将其对齐到素材槽位并触发异步任务。§7.4 要求先以 stub 实现落地框架（`time.sleep` 模拟处理，所有素材映射到同一临时图片），为 §7.5（真实 parser 标签）和 §7.6（真实图像生成）提供可测试的骨架。

**决策**（commits `3aee07d` → `de7ad00` → `8565aa2` → `da9d8fc` → `c68d20f` → `558e3f5`）：

1. **数据类型**（`tasks/_types.py`，94 行）：
   - `TaskType` 枚举：`GENERATE` / `MATCH`——两种素材获取路径（生成新素材 vs 匹配已有素材）
   - `Task` dataclass：11 字段（task_type, asset_type, local_name, local_description, target, error, _done, _event, _lock, _condition, _pool），`wait(timeout)` 阻塞等待完成（`threading.Condition`），`complete()` 单写者线程安全（D50）——只有创建者线程调用
   - `TaskTimeoutError`：`wait()` 超时时抛出（永不返回 False——修复了初始 docstring 矛盾，commit `8565aa2`）
   - `TaskQueue` = `queue.Queue[Task]`——线程安全队列，单消费者语义

2. **TaskGenerator**（`tasks/_generator.py`，126 行）：
   - `consume_event(event, line_number, outline, task_gen, roster)` → `list[Task]`——核心调度算法（§4.3）
   - 算法：行号对齐（`_current_line_number` 单调递增，确保素材与叙事位置对应）→ asset 绑定（`_story_assets` dict 跟踪 `asset_type:local_name:asset_id` 映射）→ `_enqueue_generate()` / `_enqueue_match()`
   - `_DECLARE_KIND_MAP`：CHAR → CHAR_PORTRAIT, SCENE → BACKGROUND——可扩展 dict 替代 if/else（commit `da9d8fc`）
   - 空 `local_name` 防护：GENERATE 和 MATCH 路径均将空字符串视为 no-op（commit `c68d20f`）——防止无效占位符条目
   - `_task_gen_ref`：StreamParser 注入 TaskGenerator 引用，DECLARE 事件在 parse 时同步触发 `enqueue()`（commit `09933eb`）
   - 单线程队列访问：`consume_event()` 假设由主线程独占调用（commit `da9d8fc` 文档化）

3. **TaskPool**（`tasks/_pool.py`，72 行）：
   - `ThreadPoolExecutor` 包装——`submit(task, process_fn)` → `Future`，回调链自动调用 `task.complete()`
   - `TASK_POOL_MAX_WORKERS` 配置常量（`config.py`）——默认 `min(4, os.cpu_count() or 2)`
   - `shutdown(wait)` 委托给 executor——优雅关闭，等待进行中任务完成
   - Stub `process_fn`：`time.sleep(0.01)` + 返回固定 `stub_asset` 临时图片——§7.6 替换为真实 API 调用

4. **EventDispatcher consume_event 集成**（`event_dispatcher.py`）：
   - `dispatch()` 改为 `consume_event()`——文本模式 Event 直接转 UI dict（零行为变化），图像 Event（SCENE、DECLARE）委托给 TaskGenerator
   - `assets` key 传播：SEGMENT 和 SET UI dict 中注入 `assets` 字段（commit `8565aa2`）——消费端可据此显示生成的素材
   - SCENE handler：`{"type": "scene", ...}` + position/branch 字段（commit `09933eb`）——与 SEGMENT 同级叙事事件

5. **测试**（`test_task_framework.py`，1031 行，+ `test_graph_mode_pipeline.py`，420 行）：
   - Task 生命周期：create → submit → wait → complete（含超时和异常路径）
   - Program match：GENERATE（未知 local_name 触发生成）、MATCH（已知 local_name 匹配已有素材）、DECLARE 各 kind
   - §4.3 算法：行号对齐、asset 绑定、重复 DECLARE 幂等、orphan task 丢弃
   - E2E pipeline：完整 round 模拟——所有图像标签 → stub 处理 → UI dict 输出（`test_graph_mode_pipeline.py`）
   - 验证标准（commit `558e3f5`）：三条成功标准直接映射到 `TestVerificationCriteria`——stub pipeline 运行、统一临时图片、文本模式零影响（11 种 EventType）

**依据**：
- commits: `3aee07d`（实现）、`de7ad00`（测试硬化 round 1）、`8565aa2`（assets 传播 + docstring 修复）、`da9d8fc`（round 2 audit 修复）、`c68d20f`（空名防护 + §7.6 注释）、`558e3f5`（验证标准测试）
- `docs/graph-mode-spec/design.md`：§3（Event→Task 调度）、§4（Task 数据类型）、§7.4（Stub 实现要求）
- 新建文件：`src/storyloom/tasks/__init__.py`、`_types.py`、`_generator.py`、`_pool.py`；`tests/test_task_framework.py`、`tests/test_graph_mode_pipeline.py`

### §7.5 StreamParser 图模式扩展——新标签 + 分支过滤全覆盖

**背景**：`graph-mode-spec/design.md` §5 定义了图模式新增的 XML 标签（`<seg char="...">`、`<set var="SCENE">`、`<declare kind="CHAR/SCENE">`）。同时 `block-spec.md` 要求 post-bridge 禁止标签全面抑制（此前仅记录不丢弃），分支过滤需覆盖所有叙事级事件类型。§7.5 在 §7.4 Task stub 就位后实施——parser 产出的 DECLARE Event 同步触发 TaskGenerator。

**决策**（commits `707fed9` → `1bbcd18` → `09933eb` → `73db3c9` → `8b68b67`）：

1. **Parser 扩展**（`stream_parser.py`，+154/-104 行）：
   - `<seg char="...">`：可选属性，绑定角色立绘——存入 Segment.char 字段，传播到 UI dict
   - `<set var="SCENE">` → SCENE Event 拦截：SET 标签当 var="SCENE" 时产生 SCENE 事件而非 SET——`op` 属性被忽略，始终视为赋值（commit `73db3c9`）
   - `<declare kind="CHAR/SCENE">`：kind 校验（未知 kind → FORMAT_ERROR），大小写不敏感（commit `1bbcd18` 强化测试）
   - 分支注入：SET / CHOICE_BEGIN / OPT / CHOICE_END 的 payload 中注入 `branch` 字段（此前缺失——导致分支过滤对这些事件类型无效）
   - Post-bridge 禁止标签：从"仅记录不丢弃"改为"完全丢弃"——符合 `block-spec.md` 硬约束
   - 清理：移除废弃的 `<seg n="N">` 属性解析、`Segment.n` 字段、`_seg_count` 自动编号——均已迁移到 `NNN|` line prefix

2. **StateManager 分支过滤扩展**（`state_manager.py`，+51/-16 行）：
   - SEGMENT + SCENE 合并分支过滤——同级叙事事件，统一处理
   - SET / CHOICE_BEGIN / OPT / CHOICE_END 新增分支过滤——此前这些事件类型不受 `current_branch` 约束
   - ROUTE target 验证：检查目标节点是否存在于 outline 中（commit `707fed9`）
   - `current_scene` 追踪：StateManager 维护当前场景状态（commit `09933eb`）——Phase 2 后续使用

3. **EventDispatcher SCENE 处理**（`event_dispatcher.py`）：
   - SCENE 从通用 default handler 提升为专用 handler——`{"type": "scene", ...}` + position/branch 字段（与 SEGMENT 同级）
   - 移除 SEGMENT UI dict 中已死的 `n` 字段

4. **测试硬化**（`test_stream_parser.py` +249 行，`test_state_manager.py` +107 行，`test_game_loop.py` +42 行）：
   - 两轮 code review 修复（commit `1bbcd18` P1+P2 覆盖缺口，commit `09933eb` P2×6）
   - SCENE op='=' 显式接受、bare SCENE/CHOICE_BEGIN/OPT/CHOICE_END branch=None
   - DECLARE 大小写不敏感验证、SET bare-filter 实际应用验证
   - §7.5 E2E pipeline 测试（commit `8b68b67`）：24 tests——`TestGraphModeE2E` 完整 round 模拟，修复 seg char UI dict 传播 + 缺失 `</seg>` 闭合标签
   - 712 tests passed，零回归

**依据**：
- commits: `707fed9`（实现）、`1bbcd18`（测试硬化）、`09933eb`（review 修复）、`73db3c9`（SCENE op 忽略）、`8b68b67`（E2E pipeline 测试）
- `docs/graph-mode-spec/design.md`：§5（XML 标签扩展）
- `docs/spec/block-spec.md`：post-bridge 禁止标签约束
- `docs/spec/data-model.md`：分支过滤规则

### Graph-Mode Prompt——基线文档 + PromptBuilder 实现

**背景**：图模式需要独立的 prompt 模板——与文本模式共享核心结构（ROUND1 + ROUND_TEMPLATE）但包含素材声明语法（`<declare>`）、场景行（`{scene_line}`）、角色-立绘绑定等图模式特有元素。`docs/graph-mode-spec/prompt-design.md` 作为权威 prompt 规范，`PromptBuilder` 的 graph 方法将其编译为实际发送给 LLM 的字符串。

**决策**（commits `a023559` → `b3b0b4e` → `3396a92`）：

1. **Prompt 规范文档**（`docs/graph-mode-spec/prompt-design.md`，316 行）：
   - 从文本模式 `docs/spec/prompt-design.md` 复制基线（commit `a023559`）
   - 用户精修 Requirements 章节（commit `abdadb1`）
   - 替换示例为"The Drop"和"The Last Archive"（commit `f3f41ca`）——更贴合图模式叙事风格
   - 示例 1 post-bridge 添加角色属性：Alex×5、greycoat×1（commit `ccc994b`）
   - 表达式变体：Mira.angry、Alex.sad、Yara.angry、Kai.smile（commit `c6d232a`）
   - `<declare>` 标签位置调整（commit `69441f9`）
   - `{scene_line}` 占位符加入 ROUND_TEMPLATE（commit `0dd9674`）
   - 示例 1 拆分过长 seg——强制 1-2 句限制（commit `7397945`）

2. **PromptBuilder 实现**（`prompt_builder.py`，+451 行）：
   - `GRAPH_ROUND1_PREFIX`：首轮图模式前缀——包含素材声明语法说明、场景描述要求
   - `GRAPH_ROUND_TEMPLATE`：后续轮模板——`{scene_line}` + `{outline_block}` + `{choice_block}`
   - `build_round1_graph(config, story_config, outline, scene_line, char_roster)` → 完整首轮 prompt
   - `build_round_n_graph(config, story_config, context, scene_line, outline_block, choice_block)` → 完整续轮 prompt
   - 行顺序与 `prompt-design.md` 严格对齐（commit `3396a92` 修复两处顺序偏差）

**依据**：
- commits: `a023559`（基线文档）、`abdadb1`（Requirements 精修）、`f3f41ca`（示例替换）、`b3b0b4e`（PromptBuilder 实现）、`3396a92`（行顺序对齐）
- `docs/graph-mode-spec/prompt-design.md`：Graph prompt 权威规范
- `docs/spec/prompt-design.md`：Text prompt 模板参考

### 配置迁移修复——重启要求 + 背景去除默认值

**背景**：上一日（08-05）实现了配置版本迁移（v1→v2）和 onnxruntime 背景去除。两个遗留问题：① 配置重置后面临"新配置 + 旧 session 状态"不一致窗口——UI 应提示重启而非继续；② 模型现已内置（随 PyInstaller 打包），背景去除默认值无需保持 NEVER——可改为 AUTO。

**决策**（commit `180c234`）：
- 重命名按钮：Reset and Continue → Reset and Restart
- 新增 i18n key：`Configuration reset. Please restart the application.`
- 默认值变更：`img_remove_bg` NEVER → AUTO（模型始终可用，不再需要按需下载）
- `config.example.json` + 全部测试断言同步更新

**依据**：
- commit: `180c234`
- 上一日 memory：`2026-08-05-7.3-image-api.md`（背景去除实现决策）
- 8 files changed，+34/-16 lines

---

## 2026-08-05（周三）

> **概述**：§7.2 素材数据库 + §7.3 图像 API 双模块落地——从 spec 到完整实现 + 测试 + code review 四轮硬化。同步完成配置版本迁移（v1→v2）、背景去除（onnxruntime 直推替代 rembg/pip）、Web 设置页扩展。共 28 commits，+5454/-61 lines，39 files。

### §7.2 素材数据库——AssetLibrary + GameAssetRoster

**背景**：`graph-mode-spec/design.md` §2 定义了三层素材数据模型——`Asset`（物理文件 + 元数据）、`AssetLibrary`（全局注册表，跨存档复用）、`GameAssetRoster`（单局游戏 local_name → asset_id 映射）。§7.2 标记为与 §7.3（图像 API）可并行实现的独立模块。需要先于 §7.4（Task stub）到位。

**决策**（commits `48b2a12` → `2c35483` → `92287c6` → `be9ea67`）：

1. **数据类型**（`assets/_types.py`，148 行）：
   - `AssetType` 枚举：`CHAR_PORTRAIT` / `BACKGROUND`，value 为 media/ 子目录名（D2），每类型携带 `default_extension`（D3）
   - `Asset` dataclass：6 字段（asset_type, id, name, description, use_count, serial），相等性仅由 (asset_type, id) 决定——可变字段（use_count, serial）不参与（D49）
   - `AssetItem` dataclass：3 字段（local_name, local_description, target），相等性仅由 local_name 决定（D49）。`target=None` 表示占位符——素材尚未生成（D36）
   - 序列化遵循 D5 设计：asset_type/id/local_name 为结构键（外层 dict key），不存入内层 dict

2. **AssetLibrary**（`assets/_library.py`，306 行）：
   - 全局注册表，线程安全（所有公开方法持 `self._lock`），单例语义——应用级唯一实例
   - CRUD：`add()`（缺省 uuid4().hex 生成 asset_id，D4）、`get()`（D46）、`remove()`（use_count>0 时拒绝，D25）
   - 引用计数：`increase_usage()` / `decrease_usage()`——与 GameAssetRoster 协调（D20），`set_target` 重排操作顺序确保异常安全（先增新后减旧，commit `be9ea67`）
   - 查询：`list_all()`（全类型 flat list）、`list_by_type()`（返回副本）、`get_sorted_by_usage()`（`heapq.nlargest`，O(n log k)，D10/D51）
   - 清理：`clean(keep_count)`——use_count>0 的资产永不删除，use_count==0 的按 (use_count, serial) 升序淘汰（D45）。当活跃资产已超 keep_count 时仍会清空所有闲置资产（docs 明确此行为）
   - 持久化：`save()` / `load()` 原子写入（`.tmp` + `os.replace`，D16/D41），版本校验（D42），未知 AssetType 跳过（前向兼容 §2.1）

3. **GameAssetRoster**（`assets/_roster.py`，247 行）：
   - 单局映射表，线程安全，注入 AssetLibrary 实例以协调引用计数（D20）
   - CRUD：`add()`（target 非 None 时自动 `library.increase_usage`，D38）、`set_target()`（异常安全——先增新后减旧，None↔real 过渡）、`remove()` / `clear()`（自动 `decrease_usage`，D48）
   - `lookup()`：精确字符串匹配——无模糊搜索（D9），返回 AssetItem 或 None
   - 持久化：`save(filepath)` / `load(filepath, library, game_id)`——原子写入 + 版本校验 + game_id 交叉验证

4. **测试**（`test_assets.py`，1541 行）：覆盖所有 CRUD 操作、引用计数协调（add/remove/set_target/clear 后 library.use_count 验证）、并发安全（多线程 add + increase + decrease）、序列化往返、边界条件（重复 add 报错、remove 不存在的 key、use_count>0 拒绝删除、decrease 低于 0 拒绝）

**依据**：
- commits: `48b2a12`（实现）、`2c35483`（测试硬化）、`92287c6`（review 修复）、`be9ea67`（set_target 异常安全 + clean docs）
- `docs/graph-mode-spec/design.md`：§2.2（AssetLibrary）、§2.3（GameAssetRoster）、§9（持久化格式）
- 新建文件：`src/storyloom/assets/__init__.py`、`_types.py`、`_library.py`、`_roster.py`

### §7.3 图像 API 客户端——ImgApiClient + img_utils

**背景**：`graph-mode-spec/design.md` §7.3 要求实现图像生成 API 客户端——与 LLM API 客户端平行设计（UserConfig 读取 + os.environ 覆盖），支持多模型预设，为 §7.4 Task Pool 的图像生成任务提供底层能力。同时 `design-draft.md` §E 提出背景去除需求——最初考虑 rembg（pip 依赖 + ~1GB PyTorch 重量级），后决策为 onnxruntime 直推。

**决策**（commits `c22d88c` → `3e81d08` → 四轮 review → `19aaa2b`）：

1. **ImgApiClient**（`io/img_api_client.py`，397 行）：
   - OpenAI-compatible `/images/generations` 端点——httpx 同步客户端，`generate(prompt, size, image_urls?, remove_bg?)` → `ImageResult`
   - 配置链路：`IMAGE_API_KEY` env → `img_api_key` config → `LLM_API_KEY` env → `api_key` config（key fallback）；同理 `IMAGE_BASE_URL` / img_api_base_url / DEFAULT_IMG_BASE_URL
   - 线程安全（commit `1338ddb`）：`threading.local()` 每线程独立 `httpx.Client`——httpx 默认 transport 非线程安全，Task Pool（§7.4）将在多线程调用 `generate()`
   - 模型预设（`MODEL_PRESETS` dict）：FLUX.2 Pro（1024² / 1280×720）、Seedream 5.0 Lite（2048² / 2560×1440）、Nano Banana Lite（1024² / 1024²），各带 `default_sizes` + `supports_reference` + `extra_body`
   - 尺寸解析：`_resolve_size(ImageSize)` → 查模型预设 → 缺省 fallback（1024² / 1280×720）
   - 错误处理：`ImageApiError`（与 `ApiError` 区分——图像错误降级处理，不中止叙事流）；HTTP 错误解析 JSON error message（commit `fbc54f1`）；base64 解码异常包装为 ImageApiError（commit `ceb6b24`，`binascii.Error` 非 ValueError 子类）；连接错误、下载失败、空响应统一处理
   - key masking（commit `282bc35`）：API key 显示与 LLM key 同策略——前 4 + `****` + 后 4

2. **img_utils——零依赖图像检测**（`io/img_utils.py`，412 行）：
   - `detect_format()`：magic bytes 检测——RIFF+WEBP / JFIF / PNG，纯 bytes 操作无外部依赖
   - `detect_alpha()`：PNG color type 6（RGBA）/ 4（grayscale+alpha）；WebP VP8X flags bit 4
   - `get_dimensions()`：PNG（struct，IHDR offset）、WebP（VP8X canvas_width-1）、JPEG（SOF marker 扫描，限 64KB 防恶意文件）
   - 全函数纯 bytes → Python 类型，无 IO/网络——安全用于热路径

3. **背景去除——onnxruntime 直推替代 rembg**（commit `60566bc`）：
   - **核心决策**：不使用 rembg（pip install ≈ 1GB PyTorch + 复杂的依赖树）→ 直接 onnxruntime inference。U²-Net ONNX 模型（~168 MB）从 GitHub Releases 按需下载，缓存在 `<app>/models/` 目录
   - `check_model()`：SHA256 校验确保文件完整性（commit `6800083`）
   - `download_model(on_progress)`：httpx stream GET → 分块写入 `.tmp` → SHA256 验证 → `os.replace` 原子替换。支持进度回调（commit `9f9802b` 的 SSE 进度条依赖此接口）
   - 模型目录解析：`STORYLOOM_MODEL_DIR` env → `STORYLOOM_APP_DIR/models/` → PyInstaller `sys.executable` 旁 → `cwd/models/`。自包含设计——删除程序目录即清除所有残留（commit `6800083`）
   - `remove_background(raw, fmt)`：PIL 解码 → 320² 预处理（规范化 + NCHW）→ onnxruntime 推理 → mask 双线性上采样至原始尺寸 → RGBA 合成 → PNG 字节输出。任何失败返回 None（优雅降级）
   - `maybe_remove_background(result, policy)`：AUTO（无 alpha 才去背）/ ALWAYS（强制）/ NEVER（跳过）。策略默认值设为 NEVER（commit `4c5d38f`）——去背是可选优化，不应默认触发下载
   - `_get_session()` 模块级缓存 + lazy import onnxruntime——不配置去背的用户永远不会触发 onnxruntime import

4. **共享类型提取**（commit `19aaa2b`，`io/_types.py`，55 行）：
   - `ImageResult` dataclass、`ImageSize` enum、`RemoveBgPolicy` enum 从各模块抽到共享层
   - 依赖 DAG：`_types.py` ← `img_utils.py` + `img_api_client.py`——两模块互不 import（lazy import 打破循环），结构上不可能形成循环

5. **四轮 code review 硬化**：
   - Round 1（`0e3d636` → `60140e8`）：测试矩阵扩展（grayscale-alpha PNG、VP8X lossy WebP）、`ImageApiError` 统一使用、`ValueError` on missing key
   - Round 2（`fbc54f1`）：HTTP 错误体非 JSON 时安全截断（500 字符）、download 超时独立于 gen 超时
   - Round 3（`1338ddb`）：`threading.local()` 替代共享 `httpx.Client`——Task Pool 多线程安全；`MODEL_PRESETS` 标注为 read-only
   - Round 4（`ceb6b24`）：`base64.b64decode` 的 `binascii.Error`（Exception 子类非 ValueError）统一包装为 `ImageApiError`；删除测试中未使用的 mock fixture

**依据**：
- commits: `c22d88c`（验证脚本）、`3e81d08`（API client 实现）、`0e3d636`+`60140e8`+`fbc54f1`+`1338ddb`+`ceb6b24`（四轮 review）、`60566bc`（onnxruntime 去背）、`19aaa2b`（类型提取）
- `docs/graph-mode-spec/design.md`：§7.3（image API）、§7.2（可并行）
- `docs/graph-mode-spec/design-draft.md`：§E（背景去除需求来源）
- 新建文件：`src/storyloom/io/img_api_client.py`、`img_utils.py`、`_types.py`；`scripts/validate_image_api.py`
- 测试：`tests/test_img_api_client.py`（438 行）、`tests/test_img_utils.py`（421 行）

### 配置版本迁移——UserConfig v1→v2 + Web UI

**背景**：§7.3 引入 5 个新配置字段（`game_mode`、`img_api_key`、`img_api_base_url`、`img_api_model`、`img_remove_bg`），`UserConfig._DEFAULTS.version: 1→2`。旧用户的 `config.json`（v1 schema，无 image 字段）启动时需平滑处理——不能静默失败，也不能强制丢失旧设置。

**决策**（commits `c3d5511` → `d8b5607`，5 commits）：

1. **UserConfig 新增 5 个属性**：`game_mode`（"text"/"graph"）、`img_api_key`、`img_api_base_url`、`img_api_model`、`img_remove_bg`（"auto"/"always"/"never"），均带 setter 校验。key masking 统一应用于 img_api_key（commit `282bc35`）

2. **版本迁移策略**：`_load()` 检测 `version != DEFAULTS["version"]` → 设置 `_needs_migration = True`。旧值仍在内存中（如 language 供 i18n 使用），但 API 返回 `needs_migration: true` 触发前端确认弹窗。用户确认后 `reset_to_defaults()` 清空所有字段为出厂默认并保存——简单、安全、无字段级迁移逻辑

3. **Web API 扩展**：
   - `GET /api/config` 返回全部 9 个字段（含 masked keys）
   - `POST /api/config` 支持 4 个新字段更新
   - `GET /api/config/version-status` ——检查是否需要迁移（`needs_migration` + `current_version` + `expected_version`）
   - `POST /api/config/migrate` ——用户确认后重置为默认值，切换 i18n
   - `GET /api/config/bg-removal-status` ——检查 onnx 模型是否已下载（`check_model()`）
   - `GET /api/config/bg-removal-install` ——SSE 流式下载进度（progress→done/error），`run_in_executor` + `asyncio.Queue` 桥接同步下载与异步事件循环

4. **Web 前端设置页**：新增 Image API 设置区（4 字段 + 背景去除 select + 模型下载按钮+进度条）、game_mode select。CSS 设置面板宽度放宽（640→700px，label 90→130px，input 420→480px，行间距 lg→xl）

5. **config.example.json 同步**：补充 `img_api_base_url` 默认值（apyi）、`game_mode`、image API 字段；`config.py` 新增 `DEFAULT_IMG_BASE_URL` 常量供 server.py 使用

**依据**：
- commits: `c3d5511`（Web UI + session）、`d5d2f5b`（config.example.json）、`5d00176`（version bump）、`e38e265`（default URL）、`d8b5607`（migration flow）、`f4625f5`（i18n labels + CSS）、`282bc35`（key masking）
- `src/storyloom/user_config.py`（+101 lines）、`src/storyloom/web/server.py`（+146 lines）
- `src/storyloom/config.py`（+19 lines，DEFAULT_IMG_BASE_URL + 背景去除常量）

### 杂项修复与重构

1. **移除死引用**（commit `c244b53`）：`test_session.py` 删除未使用的 `SaveManager` import
2. **测试命令清理**（commit `73bda21`）：移除 `--ignore=tests/test_api_client.py`（该文件已不存在，`ApiClient` 测试在 `tests/test_stream_parser.py` 中）
3. **验证脚本重写**（commit `55f4d56`）：`scripts/validate_image_api.py` 改用生产 `ImgApiClient` 替代临时 httpx 调用——验证脚本即文档
4. **公开 API 重命名**（commit `c908df6`）：`_check_model` → `check_model`——该函数在 `io/__init__.py` 中导出，应为公开 API

### 背景移除模型精简：u2net（168 MB）→ u2netp（4.4 MB）内嵌

**背景**：背景移除使用 u2net.onnx（168 MB），运行时从 GitHub Releases 惰性下载——用户首次启用时需要 SSE 进度条等待下载完成。打包分发面临两难：168 MB 太大不适合内嵌（PyInstaller 二进制 23 MB → 191 MB），下载流程又增加 UX 摩擦。同时 `download_model()`、SSE 下载端点、下载模态框等约 240 行代码完全服务于这个惰性下载流程。

u2netp 是 U²-Net 的轻量变体（rembg 默认模型），4.4 MB，质量在 320×320 预处理分辨率下与 u2net 无差异。

**决策**（commit `b4e8b90`）：

1. **模型替换**：`u2net.onnx`（168 MB）→ `u2netp.onnx`（4.4 MB），SHA256 验证通过，推理速度 ~28% 更快
2. **内嵌分发**：模型作为 package data 打入 wheel + PyInstaller 二进制——用户首次启用背景移除时零等待、零下载
3. **setup.py build hook**：新增 `_download_model()`，纯 stdlib（`urllib.request` + `hashlib`），幂等（SHA256 匹配则跳过），网络失败 WARNING 不中断安装。三个 cmdclass（`build_py` / `develop` / `editable_wheel`）各加一行调用——`pip install -e .` 一步到位
4. **`_model_dir()` 路径重构**：插入包内嵌路径为优先级 2（`Path(__file__).parent.parent / "models"`），同时覆盖 wheel、PyInstaller（`sys._MEIPASS`）、dev source tree 三种场景
5. **移除运行时下载**：删除 `download_model()` 函数、SSE 端点 `/api/config/bg-removal-install`、下载模态框 `_showRembgInstallModal()`、3 个下载相关 i18n key
6. **删除的常量**：`BG_REMOVAL_DOWNLOAD_TIMEOUT_SEC`（仅 `download_model()` 使用）、`BG_REMOVAL_MODEL_URL`（移入 setup.py hook 就地硬编码）

**净变更**：14 files，+142/-401 lines。614 tests pass。

**依据**：
- commit: `b4e8b90`
- `src/storyloom/io/img_utils.py`：`_model_dir()` 包路径优先 + `check_model()` 保留
- `setup.py`：`_download_model()` — 与 `_compile_mo_files()` 平行的 stdlib-only hook
- `src/storyloom/config.py`：仅保留 `BG_REMOVAL_MODEL_FILENAME` + `BG_REMOVAL_MODEL_SHA256`（`check_model()` 运行时使用）
- 模型来源：`https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx`

### 图像 IO 模块循环依赖消除

**背景**：`img_api_client.py` ↔ `img_utils.py` 存在模块级循环依赖——`img_utils` 从 `img_api_client` import `ImageResult` / `RemoveBgPolicy`，`img_api_client` 在 `generate()` 方法内惰性 import `img_utils`（`detect_format` / `maybe_remove_background`）。虽未触发 `ImportError`（惰性 import 绕过了问题），但这意味着两者的依赖方向取决于运行时调用顺序——任何人在 `img_api_client` 模块级加 `from img_utils import ...` 即崩溃。根本原因是 `ImageResult` / `RemoveBgPolicy` / `ImageSize` 属于共享类型，不属于任何一方。

**决策**（commit `19aaa2b`）：提取共享类型（`ImageResult`、`RemoveBgPolicy`、`ImageSize`）到独立模块 `io/_types.py`——零依赖的纯数据层。形成干净 DAG：`_types ← img_utils` + `_types ← img_api_client`，两者永不在模块级交叉 import。

**依据**：
- commit: `19aaa2b`（+60/-50 lines, 5 files）
- 新增文件：`src/storyloom/io/_types.py`（55 行）
- Acyclic Dependencies Principle（Bob Martin）：包的依赖图必须无环

---

## 2026-08-04（周二）——下午：管线重构与 v1.3.0

> **概述**：Phase 1 管线核心重构——`StreamingXmlParser` 拆分为 `StreamParser` + `StateManager` + `EventDispatcher` 三组件架构，为 Phase 2 图形模式管线扩展铺路。伴随 3 个 bug 修复 + 1 个前端修复 + v1.3.0 发布。

### 管线三组件重构（§7.1 第一步）

**背景**：旧 `StreamingXmlParser` 承担了三项职责——原始 XML 行解析（LineBuffer + 行号计数 + Event 生成）、状态管理（SET 处理、checkpoint 累积、CHOICE_END 阻塞、分支选择、node_goals 构建）、以及 UI 事件转换（Event → Dict → Observer）。这三项职责耦合在一个类中，GameLoop 需要直接调用解析器的状态方法（`_handle_set_event`、`_handle_checkpoint`、`_set_node_status`、`_accumulate_checkpoint`、`_get_selected_branch`、`_build_node_goals`），导致 GameLoop 膨胀至 ~500 行业务逻辑。按 `graph-mode-spec/design.md` §7.1 的要求，Phase 2 管线需要在 Event 流中插入素材相关的 Task 生成与消费，现有架构无法支持。

**决策**（commit `0bc37be`，+2066/-1452 lines across 12 files）：

1. **`StreamParser`**（`parser/stream_parser.py`，569 行）：承担纯解析职责——`LineBuffer` 缓冲 + 行号计数 + `NNN|` 前缀校验 + `parse_line()` → `list[Event]`。同时承载共享数据类型（`Event`、`EventType`）——原 `streaming_parser.py` 中的 `ParseEvent` 和 dataclass 全部迁入此处。不再包含任何状态逻辑。

2. **`StateManager`**（`core/state_manager.py`，584 行）：承担流式事件处理——`process(event)` 是生成器，一个 Event 进 → 零或多个 Event 出。内部管理所有游戏状态：SET 变量、checkpoint 累积（nodes、routes、ending_flag）、CHOICE_END 阻塞标记（`needs_input`）、分支选择算法（`*default` + `current_branch` 匹配）、node_goals 构建。`get_result()` 返回本轮累积的所有数据（nodes、routes、choices、segment_text 等）。

3. **`EventDispatcher`**（`core/event_dispatcher.py`，141 行）：承担 Event → UI Dict 转换——`dispatch(event)` → `dict`，供 Observer 和 Web UI 使用。预留 `consume_event()` 空方法作为 Phase 2 扩展点——子类覆写后可在 Event 流中插入素材消费逻辑（如 SEG 事件触发 Task 校验）。

4. **GameLoop 精简**：`stream_round()` 使用新管线 `StreamParser → StateManager → EventDispatcher`——删除了 `_handle_set_event`、`_handle_checkpoint`、`_set_node_status`、`_accumulate_checkpoint`、`_get_selected_branch`、`_build_node_goals` 六个方法（-498 行）。Flush 事件现在通过完整管线路由；`checkpoint_snapshots` 从 StateManager 同步；`format_errors` 合并到 `StateManager.get_result()`。

**设计合规性**：
- `Event.payload: dict` — 符合设计规范 §4.1
- `Event.line: int` — 本地行号计数器（权威来源），含 `NNN|` 前缀校验
- 所有 Event 经 StateManager 流转 — 符合 §4.1 事件表
- `process()` 生成器：单 Event 入 → 零/多 Event 出
- 错误处理：程序 bug 直接修复（非 LLM 输出问题），LLM 输出错误记录为 `format_error` 供下一轮反馈，未知类型透传默认分支

**测试**：新增 `test_stream_parser.py`（231 行）+ `test_state_manager.py`（382 行），更新 `test_integration.py`（81 行变更），删除旧的 `test_streaming_parser.py`（424 行）。全量 353 测试通过，零回归。

**依据**：
- commit: `0bc37be`（+2066/-1452 across 12 files）
- `docs/graph-mode-spec/design.md`：§7.1（管线重构作为全部后续步骤的前置）
- `docs/graph-mode-spec/design.md`：§4.1（事件类型表）、§4.3（EventDispatcher 算法）

### 规范文档澄清——bridge_text 多分支提取

**背景**：`block-spec.md` 中 bridge_text 提取逻辑的描述在旧版中不够精确——"提取其中 `<seg>` 和 `<branch>` 内的 `<seg>` 的文本节点"未区分裸 seg 与 branch 内 seg，也未明确说明非 current_branch 的 branch 如何处理。

**决策**（commit `d1ddf60`）：
1. 裸 seg（不在任何 `<branch>` 内）始终提取
2. `<branch>` 内的 seg 仅提取 `name` 匹配 `current_branch` 的分支
3. 未命中的 branch 不提取、不注入下一轮

**依据**：
- commit: `d1ddf60`（+7/-6 in `docs/spec/block-spec.md`）
- `docs/spec/block-spec.md`：bridge_text 提取章节

### 重构后 Bug 修复

**背景**：管线重构后立即发现 2 个回归问题 + 1 个 spec 合规缺口。

**决策**（3 个修复 commits）：

1. **choice_data 生命周期修正**（commit `cd2d764`）：`apply_choice()` 不再清除 `_last_choice_data`——该字段必须在整个轮次内保持，因为 `get_result().choices` 依赖最后一次 CHOICE_END 的 payload 构建 choices / choice_id / opt_branches 字段。下一轮 CHOICE_END 会自然覆盖。

2. **PARSE_ERROR 事件发射**（commit `b96a970`）：旧代码中无法识别的 XML 行仅记录 `format_error`，不产生 Event——不符合设计规范 §4.1 事件表（每个错误行应产生 PARSE_ERROR 事件）。`StreamParser.parse_line()` 现在同时记录 `format_error` 并返回 `Event(type=PARSE_ERROR, ...)`。

3. **空 `<choice>` 防护**（commit `b96a970`）：`StateManager` 的 CHOICE_END 处理器仅在 `choice_data is not None`（即存在 `<opt>` 子元素）时设置 `needs_input=True`——空 `<choice>` 标签（无 `<opt>` 子元素）不再触发 UI 等待，避免前端崩溃。

**依据**：
- commits: `cd2d764`、`b96a970`
- `src/storyloom/core/state_manager.py`、`src/storyloom/parser/stream_parser.py`

### 前端修复——手动模式加载指示器卡死

**背景**：Web 前端在自动滚动模式下手动切换至手动模式时，加载指示器（"加载中..."）会永久卡住。根因：`_wakeDisplay()` 仅在 `_isPolling=True` 时隐藏加载指示器；用户切换到手动模式时 `_toggleMode()` 设置 `_isPolling=False`，导致后续数据到达时 `_wakeDisplay()` 跳过清除逻辑。

**决策**（commit `2bba85c`）：`_wakeDisplay()` 将 `_cancelLoading()` + `Display.hideLoading()` 提升到 `_isPolling` 判断之外——无论轮询状态如何，只要新 SSE 数据到达就清除加载指示器。同时在 `_toggleMode()` 中也加入加载状态清理，双重保险。

**依据**：
- commit: `2bba85c`（+4 lines in `src/storyloom/web/static/js/game.js`）

### v1.3.0 发布

**背景**：管线三组件重构完成，Phase 1 架构已为 Phase 2 图形模式做好准备。向后兼容——所有 Phase 1 测试通过。

**决策**（commits `b1d29dd` + `740bb8c`）：版本从 1.2.1 → 1.3.0（小版本号，因为架构重构属于内部改进且保持向后兼容）。同步更新 `pyproject.toml` 和 `src/storyloom/__init__.py` 两处版本号。

**依据**：
- commits: `b1d29dd`（pyproject.toml）、`740bb8c`（__init__.py）
- `docs/graph-mode-spec/design.md`：§7.1 管线重构步骤完成

---

## 2026-08-04（周二）

> **概述**：Phase 2 文档目录重组——图形模式规范从 `docs/spec/` 迁入独立 `docs/graph-mode-spec/`；Task 生命周期三处关键修正（入队时机、线程池更新方式、GENERATE 选择范围）。

### 图形模式文档目录重组

**背景**：图形模式规范在 `docs/spec/` 下共存于 Phase 1 文本模式规范旁，两份 `design.md`（Phase 1 `graph-mode-design.md` + draft `graph-mode-design-draft.md`）混在一起，CLAUDE.md 也过于冗长（~160 行）。随着图形模式规范体量增大（正式设计 + 草案共 ~850 行），需要独立的文档空间。

**决策**：

1. **新建 `docs/graph-mode-spec/` 目录**：`design.md`（正式规范）与 `design-draft.md`（早期草案，参考）迁入独立目录，各配 `README.md` 导航。
2. **`docs/spec/` 专注 Phase 1**：仅保留文本模式规范（`exec-flow.md`、`block-spec.md`、`prompt-design.md`、`data-model.md`），新增 `README.md`。
3. **CLAUDE.md 精简**：从 ~160 行压至 ~65 行——删除冗长的"Core Design Concepts"章节（已在 theory/ 和 spec/ 中维护），文档表增加 `docs/graph-mode-spec/` 行，状态描述简化。

**依据**：
- commit: `8738d35`（+126/-179 lines across 6 files）
- `docs/graph-mode-spec/README.md`、`docs/spec/README.md`（新建）
- `CLAUDE.md`（重构）

### Task 生命周期三处修正

**背景**：图形模式正式规范 `graph-mode-design.md` 初版中存在三处 Task 模型语义不精确的问题：(1) Task 入队时机不明确——"process 非 None 则入队"还是"创建即入队"？(2) Task Pool 线程池如何更新 Task——dequeue → 执行 → enqueue 还是原地标记？(3) GENERATE 任务中 LLM 选择阶段的输入是否包含游戏素材名册（GameAssetRoster）？

**决策**：

1. **Task 创建即入队**（commit `290a88b`）：Task 在构造完成、放入 Task Queue 的那一刻即为"已在队列中"——无论 `process` 是否为 None。`completed=True`（程序匹配成功）时跳过 Task Pool 提交，但 Task 仍在队列中供 EventDispatcher 按行号消费。此修正统一了 MATCH 和 GENERATE 两种类型的入队语义。

2. **Task Pool 原地更新 Task**（commit `454c3c8`）：线程池取出 Task 后直接设置 `task.completed = True` 和 `task.result`，不执行 dequeue→重新 enqueue。EventDispatcher 通过检查 `task.completed` 标记判断是否等待——Task 始终在队列中，线程池和 EventDispatcher 共享同一引用。避免了 dequeue/enqueue 期间 EventDispatcher 漏读 Task 的竞态窗口。

3. **GENERATE 的 LLM 选择必须包含名册**（commit `130033f`）：GENERATE 任务中 LLM 选择阶段（Material Selection LLM）的输入范围应包含游戏素材名册——如果名册中已有合适的 local_name（由预构建或之前的 DECLARE 创建），LLM 应返回该条目而非调用 AI 生成。防止重复生成已存在的素材。

此外，补充了 LLM 推理深度对照表——匹配类 LLM 用"无思考"（快速选择），生成类用"默认"（创造需要推理），选择类用"低/关闭"（二元判断）。

**依据**：
- commits: `290a88b`、`454c3c8`、`130033f`（仅修改 `graph-mode-design.md`）
- `docs/graph-mode-spec/design.md`：§4.2 Task 模型 + §4.3 EventDispatcher 算法

---

## 2026-08-03（周一）

> **概述**：Phase 2 图形模式正式设计规范创建（480 行）——数据模型、管线架构、事件/任务系统、AI 角色、流程定义与分阶段实现方案。随后经历两轮规范精炼：命名统一、错误修复、实现方案重构。

### 图形模式正式设计规范

**背景**：设计草稿 `graph-mode-design-draft.md` 经过 2026-07-31 和 2026-08-01 两轮重构（统一 `<declare>` 标签、素材管线拆分）后，结构和语义已趋于稳定，需要一份正式的、可直接指导实现的程序设计规范。草稿侧重于"提案与讨论"，正式规范侧重于"定义与实现"。

**决策**：创建 `docs/spec/graph-mode-design.md`（480 行），包含 7 个章节：

- **§1 概述与设计目标**：图像模式定位（视觉小说演出）、与 Phase 1 的关系（共享核心引擎，管线分道）
- **§2 素材数据模型**：三层抽象（故事设定 → 导演调度 → 素材存储）、AssetLibrary（全局注册表）、GameAssetRoster（单局映射表）
- **§3 管线架构**：组件拓扑（StreamParser → StateManager → EventDispatcher + TaskGenerator）、线程与队列模型、阻塞点分析、时序模型
- **§4 事件与任务系统**：5 种事件类型（SEG/SCENE/DECLARE + Phase 1 事件）、Task 模型（MATCH/GENERATE + 生命周期）、EventDispatcher 按行号对齐算法
- **§5 AI 角色与提示词**：7 种 AI 角色（共创/设定/预构建/导演/匹配/生成/日志）、各 Prompt 要点
- **§6 流程解析**：共创流程（含素材预构建）、单轮叙事流程（7 阶段完整序列图）
- **§7 实现方案**：分 8 步实现（管线重构 → 数据库 → API → Task stub → XML/Prompt → 真实管线 → 预构建 → UI），含验证标准和并行标记

**依据**：
- commit: `35a650c`（+483 insertions）
- 前置工作：`11746e4`（统一 `<declare>`）、`0b5bc8c`（管线拆分）
- `docs/graph-mode-spec/design.md`（最终位置）

### 规范精炼——命名、错误修复、Task 字段细化

**背景**：正式规范初稿完成后，进行了一轮全面的自审和修正，涉及命名一致性、术语准确性、Task 字段语义。

**决策**（三轮修正，commits `72f197a` → `f49e5d3` → `07201cc` → `8c436d1`）：

1. **命名修正**：`GameAssetList` → `GameAssetRoster`（"名册"比"列表"更准确描述 local_name→AssetItem 的映射语义）；中文术语"素材列表"→"素材名册"全面同步。
2. **错误与歧义修复**：修正了管线架构图中的数据流方向、事件类型表中 SEG/SCENE 的触发条件描述、Task 生命周期步骤编号。
3. **Task 字段细化**：
   - `asset_type: AssetType` — 显式声明素材类型，使 MATCH 和 GENERATE 的 Prompt 可根据类型区分
   - `result` 字段语义明确——MATCH 返回 `local_name`（供 EventDispatcher 绑定），GENERATE 不绑定（`result` 仅用于日志）
   - 程序匹配描述从"O(1)名称精确匹配"改为更准确的"在名册中查找 local_name 精确匹配"

**依据**：
- commits: `72f197a`、`f49e5d3`、`07201cc`、`8c436d1`
- `docs/graph-mode-spec/design.md`：§2.3（名册）、§4.2（Task 模型）

### 实现方案重构与 EventDispatcher 单源原则

**背景**：§7 实现方案的初稿按"逻辑分组"排列步骤，未充分考虑步骤间的依赖关系。同时 EventDispatcher 中的 `local_name` → `asset_id` 解析位置未明确——是在 Task 完成时解析还是 EventDispatcher 消费时解析？涉及"谁持有映射权威"的架构问题。

**决策**（commit `9281e03` + `7efb934`）：

1. **实现步骤按依赖链重排**：8 步明确依赖方向——7.1（管线重构）是全部后续步骤的前置；7.2（素材数据库）和 7.3（图像 API）可并行；7.4（Task stub）依赖 7.1+7.2；7.5（XML/Prompt）依赖 7.1 但不依赖 7.2~7.4，可与 7.4 并行（标注 ∥）。每步明确验证标准，通过即锁定该维度正确性，后续不返工。

2. **测试设计可复用**：7.4 的集成测试用例设计为后续步骤复用——7.6 用真实 Task 重放同一套用例，验证行为一致性。

3. **EventDispatcher 单源原则**：`local_name` → `asset_id` 的解析在 EventDispatcher 中完成——游戏素材名册是唯一映射权威。Task 完成时返回 `local_name`（字符串），EventDispatcher 通过 `roster.lookup(local_name)` 解析为 `asset_id` 并绑定到事件。避免 Task 和 EventDispatcher 各自维护映射逻辑导致的不一致。

**依据**：
- commits: `9281e03`、`7efb934`
- `docs/graph-mode-spec/design.md`：§7（实现方案结构）+ §4.3（EventDispatcher 算法中 `roster.lookup()` 调用）

---

## 2026-08-01（周六）续

> **概述**：理论文档重写——`first-principles.md` 从零重建为公理-推导体系；桥接机制补充交互边界分析；理论与规范并列为权威。

### 理论文档重建

**背景**：Phase 1 期间积累的设计理论（first-principles、bridge-mechanism、streaming-parse、timing-model）体例不统一，部分为早期探索笔记。进入 Phase 2 图形模式设计前，需要清晰的理论基础来约束设计决策——素材管线是否阻塞叙事流、预构建的时序依据、生成时延模型等。

**决策**（commits `deb7487` → `7190fcf` → `3a14524`）：

1. **`first-principles.md` 从零重写**（+70 lines）：建立公理→推导体系：
   - 公理 1（生成有时延）、公理 2（叙事流优先）、公理 3（状态在本地）
   - 从公理推导出桥接预取、素材预处理、单源权威等设计原则
   - 删除旧的 `timing-model.md`——其内容合并入 first-principles 和 bridge-mechanism

2. **`bridge-mechanism.md` 补充交互边界**：新增"交互边界"分析——桥接机制的本质是"在人类阅读时间窗口内隐藏 LLM 生成延迟"，边界条件包括：choice 回合不可预取（等待玩家输入）、seg 长度影响桥接覆盖、极端短 seg 的降级策略。

3. **`streaming-parse.md` 重写**：从实现记录转为原理阐述——为什么行级流式解析优于块级缓冲、NNN| 前缀的单字符触发效率、解析器与状态管理器拆分的理论依据。

4. **`asset-generation.md` 新建**（+38 lines）：素材生成服从公理 1（生成有时延）→ 需求识别 ≠ 展示时刻 → 预声明是纯时序优化 → DECLARE 的 line=0 阻塞机制理论依据。

5. **Theory 与 Spec 并列权威**：更新 `CLAUDE.md` 和 `docs/README.md`——theory/ 定义"为什么"，spec/ 定义"怎么做"，二者具有同等权威性。设计决策需同时符合理论约束与实现规范。

**依据**：
- commits: `deb7487`、`7190fcf`、`3a14524`
- `docs/theory/first-principles.md`、`bridge-mechanism.md`、`streaming-parse.md`、`asset-generation.md`
- `docs/theory/README.md`（更新）
- 删除 `docs/theory/timing-model.md`（内容已合并）

### 图形模式设计草稿——编者提问精炼

**背景**：设计草稿附录中的"编者提问"（对设计未决问题的自问自答）初稿措辞偏学术化，部分问题表述冗长，不利于快速定位未决项。

**决策**（commits `5e0b80c` → `67eee0c` → `2d0f52c`）：三轮措辞精炼——简化问题表述、统一问答格式、每个问题增加"当前倾向"标注。共涉及 ~15 个问题，涵盖管线阻塞语义、Task 优先级、名册持久化、UI 缓冲区策略等。

**依据**：
- commits: `5e0b80c`、`67eee0c`、`2d0f52c`
- `docs/graph-mode-spec/design-draft.md` 附录

---

## 2026-08-01（周六）

> **概述**：`ApiClient` 新增 `response_format` 与 `extra_params` 参数支持；图形模式设计草稿重构——素材管线拆分为匹配/生成两条独立路径。

### 图形模式设计：素材管线拆分

**背景**：`graph-mode-design-draft.md` 初稿中，所有图像需求（SCENE 切换、SEG 角色立绘、DECLARE 新素材声明）走同一套"程序匹配 → LLM 选择 → AI 生成"三步管线。这导致两个问题：(1) 高频的 SCENE/SEG 事件可能触发图像生成，叙事流延迟不可预测；(2) 不同事件类型的语义（"使用已有素材"vs"引入新素材"）被模糊处理。

**决策**：

1. **素材匹配与素材生成彻底拆分**：
   - **匹配**（SCENE / SEG(char) 触发）：仅从游戏素材列表中强制选择，绝不走生成。程序匹配（名称精确匹配）为前置保底，失败则由 LLM 从列表中语义选择最贴合者。
   - **生成**（DECLARE / 共创预构建触发）：先 LLM 选择（查游戏列表 + 全局素材库），若无合适素材则调用 AI 生成。

2. **DECLARE 的"先占位、后填充"策略**：程序匹配失败时立即在游戏素材列表创建 AssetItem（暂不设 target），后续 LLM 选择或 AI 生成完成后通过 `set_target` 赋值。这防止了后续 SCENE/SEG 匹配任务等待 DECLARE 生成完成时的逻辑顺序冲突——AssetItem 立即可见，EventDispatcher 的 `line=0` 阻塞机制保证 UI 收到事件时素材已就绪。

3. **导演 LLM 的名称约束**：SCENE/SEG 使用的素材名称必须在 `locations/characters` 或 `<declare>` 中出现过。引擎层保证"声明过的必可用"，使用层保证"只使用已声明的"。

4. **数据结构三层模型**：`Asset`（物理文件 + 元数据）→ `AssetLibrary`（程序全局，按类型 + ID 索引）→ `GameAssetList`（单局游戏，按类型 + local_name 索引，通过 `AssetItem.target` 间接引用 Asset ID）。

**依据**：
- commit: `0b5bc8c` — `docs/spec/graph-mode-design-draft.md` 全文重构（132 insertions, 75 deletions）
- `docs/theory/asset-generation.md`：素材生成服从公理 1（生成有时延），需求识别 ≠ 展示时刻，预声明是纯时序优化
- 关键术语统一：素材/素材库/素材列表、匹配/生成、绑定（EventDispatcher）

### ApiClient 参数扩展机制

**背景**：共创阶段 `generate()` 调用 LLM 生成 JSON 设定，此前完全依赖 prompt engineering 约束输出格式，但 API 本身支持 `response_format={"type": "json_object"}` 强制 JSON 输出。此外，图形模式设计草稿提出"通过 `extra_body` 关闭 LLM 思考以加快素材选择响应"（graph-mode-design-draft.md §E），未来还可能涉及 `temperature`、`top_p` 等参数控制。需要一个统一的参数扩展入口。

**决策**：

1. **两层参数设计**：
   - `response_format` 一等公民——OpenAI 官方 API 标准字段，类型明确（`{"type": "json_object"}`），共创 JSON 生成必传。
   - `extra_params` 通用 escape hatch——任意顶层 JSON 字段的 dict，合并到请求体中。覆盖 `temperature`、DeepSeek `thinking`、OpenAI `reasoning_effort` 等现在及未来的提供商特有参数。
   - 命名选择 `extra_params` 而非设计草稿中的 `extra_body`：本项目直接构建 HTTP JSON body（无 OpenAI SDK 层），`extra_params` 更准确描述"额外的顶层 JSON 字段"。

2. **改动集中**：`_build_payload()` 新增两个可选参数（默认 `None`），三个公开方法（`chat` / `stream_chat_iter` / `stream_chat`）签名同步扩展。所有现有调用方零影响。

3. **共创 Prompt 简化**：Output Format 指令从 "no markdown fences, no commentary" 简化为 "containing all sections below"——API 层负责硬约束（合法 JSON），Prompt 负责软引导（字段语义），`validate_json` 的 markdown fence 清理保留作为最后兜底。

**依据**：
- `src/storyloom/io/api_client.py`：`_build_payload` + 3 个公开方法
- `src/storyloom/core/co_create.py`：`generate()` / `retry_generate()` 传入 `response_format`；`CO_CREATE_GENERATION_PROMPT` §Output Format；`validate_json()` 错误提示
- `docs/spec/prompt-design.md` §3.2.1：Prompt Output Format 同步
- `docs/spec/graph-mode-design-draft.md` §E（extra_body 需求来源）
- 325 全量测试通过

---

## 2026-07-31（周五）

> **概述**：实现 `<set>` 驱动的数据分支控制——`BRANCH` 保留变量允许 LLM 根据 state_vars 条件自动切换 `current_branch`，无需玩家选项介入。同时使 `<set>` 的 `op` 属性可选化，缺省为 `=`。

### `<set>` 驱动的分支控制

**背景**：剧情的分支走向理应根据数据决定（如好感度>50走路线A，<50走路线B）。已有机制中，`checkpoint` + `<route>` 只能在大纲层级路由，而内容层级的 `<branch>` 切换仅能通过玩家选项 (`<opt branch="...">`) 实现——无法表达"根据数据条件自动选择分支"的需求。原始设计意图中 `<set>` 应能设置 `current_branch`，但实施时未包含。

**决策**：

1. **引入 `BRANCH` 保留变量**（`BRANCH_VAR_NAME = "BRANCH"`，放在 `config.py` 全局常量）：`<set var="BRANCH" val="分支名"/>` 在 `stream_round()` 的 SET 事件处理中被拦截，通过 `evaluate_condition` 评估 `if` 条件后直接更新 `current_branch`——不经过 `GameState.apply_set()`，无需注册为 state variable，不产生 "unknown variable" 拒绝。

2. **`op` 属性可选化**：`_RE_SET` 正则将 `op` 改为可选组，解析时缺省为 `"="`。向后兼容——已有显式 `op` 的 `<set>` 不受影响。

3. **Prompt 全面同步**：Example 1 替换为含 `BRANCH` 用法的完整故事（Greta/Kael/stranger），展示 pre-bridge 条件分支；Example 2 使用无 `op` 写法；`<set>` 文档更新 `op` 为可选，补充 `BRANCH` 保留变量说明和 snippet。

4. **规范更新**：`block-spec.md` §3 新增数据驱动来源，§4 `op` 改为可选；`data-model.md` §A.2 补充 `BRANCH_VAR_NAME` 常量。

**依据**：
- commits：`efa3f0f`（解析器+引擎）、`bd9cb0b`（常量表）、`db63993`（prompt 同步）
- `docs/spec/block-spec.md` §3-4、`docs/spec/data-model.md` §A.2
- 测试：`TestBranchSetControl`（6 个）+ `test_set_without_op_defaults_to_assign`（3 个）+ `test_round1_contains_branch_var_in_prompt`
- 325 全量测试通过

### 图形模式标签设计——从专用标签到统一声明

**背景**：原设计草稿为场景和角色各自定义了专用标签（`<scene>` / `<character>`），其中 `<scene>` 身兼"描述背景 + 切换场景"双重职责，`<character>` 只描述不切换——同一维度的两种类型行为不一致。此外每新增一种媒体类型都需新标签+新解析规则+新事件，扩展成本高。

**决策**：采用统一声明 + SET 驱动的设计：

1. **`<declare kind="CHAR/SCENE" name="...">desc</declare>`** — 统一声明标签，仅触发素材制作 Task，不产生 UI 事件、不影响内容展示。`kind` 属性区分类型（可扩展）。
2. **`<set var="SCENE" val="..."/>`** — 场景切换复用现有 SET 机制，与 `BRANCH` 保留变量对称（`SCENE` 同为保留变量）。
3. **`<seg char="...">`** — 角色立绘切换保持为 seg 属性（语义微调：`character` → `char`）。
4. **三种事件类型**：`SEG`、`SCENE`（同级，发 UI）、`DECLARE`（仅引擎内部，不发 UI/StateMng）。
5. **DECLARE Task 特殊处理**：`line=0` 不参与行号匹配，但必须等待完成才能消费后续事件。

**依据**：
- commit：`11746e4`（设计草稿全面重写，+83/-68 lines）
- `docs/spec/graph-mode-design-draft.md`

### 并发模型全面审计与修复

**背景**：图形模式设计草稿中管线涉及线程、生成器链、异步等多层并发机制，需要先厘清当前项目的并发现状，再评估设计草稿中并发方案的合理性和可行性。

**决策**：

1. **当前并发模型梳理**：项目以多线程为主，asyncio 仅用于 Web 层 SSE 轮询。核心 4 线程——主线程（asyncio 事件循环）、游戏循环守护线程（同步生成器）、API 预取守护线程（每轮一个）、冒险日志线程（结局时）。引擎核心零 async，全部同步生成器 + 后台线程。

2. **两处代码修复**：
   - **共创端点阻塞事件循环**（P1）：4 个 `async def` 端点内部调用同步 `api.chat()` 阻塞 10-60s。改为 `def` 让 FastAPI 自动线程池执行。commit `d2abb53`
   - **SSE 忙轮询 → 事件驱动**（P2）：`queue.Queue.get_nowait()` + `sleep(0.1)` 轮询 → `asyncio.Queue` + `await q.get()` + `call_soon_threadsafe`。消费者零 CPU 唤醒，生产者线程安全投递。commit `6fdd123`

3. **Phase 2 并发方案选择**：共创阶段 15-30 个并发素材制作 Task，叙事阶段每轮 1-3 个。对比 ThreadPoolExecutor vs asyncio，选择 asyncio——15-30 个 IO 等待型协程远轻于同等数量线程，且 Task 的"发射后不管"语义与 `asyncio.create_task()` 天然匹配。游戏循环保持同步生成器（`gen.send` 需求），Task 执行在独立事件循环上异步并发。

4. **设计文档线程/异步章节**：补充线程模型（事件线程 + API 线程的两线程布局）和异步并发（SSE 推送 + Task 制作两处异步）说明，修正数据流描述中队列与生成器 `yield` 的区分。commit `2841c9d`

**依据**：
- commits：`d2abb53`、`6fdd123`、`2841c9d`
- `docs/spec/graph-mode-design-draft.md` §线程模型、§异步并发
- 315 全量测试通过

---

## 2026-07-30（周四）

> **概述**：Phase 2 图形模式管道架构深度讨论与设计优化——bridge 机制分析、解析/匹配分离、行号匹配算法、Event 三态命名。设计草稿经历多轮迭代重构。

### 图形模式管道架构——设计优化

**背景**：07-29 的设计草稿初版包含两段式解析器（Line Generator + Event Generator）+ Task Generator + Tasks Buffer 的管道架构，但在 bridge pre-fetch 时序、中间数据类型、匹配算法等方面存在模糊地带。本日对管道架构做了系统性评审和重新设计。

**决策**（`docs/spec/graph-mode-design-draft.md` 多轮迭代）：

1. **管道四段式架构**：

```
LLM → StreamParser → StateManager → EventDispatcher → UI
         │                                 ↑
         └──→ TaskGenerator ──Task─────────┘
```

| 组件 | 职责 | 阻塞行为 |
|------|------|---------|
| **StreamParser** | token → Event(unhandled)，检测媒体标签时 fire-and-forget 触发 TaskGen | 从不阻塞 |
| **StateManager** | SET/CHECKPOINT 应用、BRANCH 过滤、CHOICE 等待、BRIDGE → pre-fetch | CHOICE 处阻塞 |
| **TaskGenerator** | 构造并发图像制作 Task，有序队列，pull 模型出队 | 不阻塞 |
| **EventDispatcher** | 文本模式透传，图形模式按行号匹配 Task → 组装后发送 UI | 图像等待处阻塞 |

2. **bridge pre-fetch 时序分析**：图形模式下 bridge 后可能出现图像任务等待，但下一轮 Prompt 仅需文本内容（bridge_text），不需图像数据。StreamParser 在 `</story>` 前已完成全部文本提取，StateManager 在 `</story>` 处触发 pre-fetch——不受 EventDispatcher 图像阻塞影响。CHOICE 阻塞影响 bridge 触发（正确且不可避免），图像阻塞不影响。

3. **行号匹配替代分支匹配**：Task 与 Event 通过 LLM 输出行号对位——`while Task.line < Event.line: consume`。分支匹配不可行的根因：(a) BRANCH 事件在 StateManager 中被消费，无法到达下游；(b) current_branch 是动态状态，匹配器无法复现；(c) Event 不携带 branch 信息。行号作为全局唯一、单调递增的标识，自动处理孤 Task 清理和分支过滤。

4. **Event 三态命名**：同类型贯穿管线——`Event(unhandled)` → `Event(unmatched)` → `Event`，完整性递增。StreamParser 产出 unhandled（字段完整但 SET 未应用），StateManager 产出 unmatched（状态已应用但媒体未附加），EventDispatcher 产出最终的 Event（媒体已附加）。

5. **EventDispatcher 命名**：原设计称 MediaMatcher，因文本模式复用该模块（仅透传事件，无 Task 处理）而改为通用名称。两种模式差异收敛在构造时——传入 TaskGen 或 None。

6. **与现有代码对应**：StreamParser ≈ `StreamingXmlParser`，StateManager ≈ `GameLoop`。重构在 Phase 1 内完成（Parser + StateManager + EventDispatcher），Phase 2 在其上增量添加 TaskGen + 媒体制作管线。

**依据**：`docs/spec/graph-mode-design-draft.md` §流程解析。

---

## 2026-07-29（周三）

> **概述**：12 次提交，Story Context 架构拆分、冒险日志 Prompt 重设计、四个阶段 Prompt 全面审查与措辞修复、Phase 2 图像生成模式设计草稿。315 测试全绿。

### Phase 2 图像生成模式——设计草稿

**背景**：Phase 1 核心引擎已稳定（v1.2.0），下一阶段自然方向是为纯文本互动小说添加视觉表现层——传统 Galgame/视觉小说式的角色立绘 + 背景图像。这项功能涉及 LLM Prompt 扩展、解析器架构重构、新媒体数据库、图像 API 集成、UI 新界面等多个子系统，需要先有完整设计草稿再进入实现。

**决策**（`docs/spec/graph-mode-design-draft.md`）：

1. **媒体数据库分层**：全局库（Storyloom 级，跨存档复用）+ 游戏库（单局作用域，存档时持久化）。使用计数 + 总量阈值自动清理低频素材。角色立绘与背景图像为不同数据类，均可按命名空间分类（支持未来 "小明.微笑" 形式）。

2. **"选择"优先于"生成"**：每次需要媒体数据时，先按名称/描述在库中匹配（"选择"，零 API 调用）；匹配不到才调用图像生成 API。未配置图像 API 时强制走选择模式。

3. **AI 角色六分法**：A. 共创聊天 LLM / B. 大纲生成 LLM / C. 素材预构建 AI（新增——基于设定中的地点角色预生成初始素材库，支持 1-3 个变体方向）/ D. 叙事导演 LLM（修改——仍输出纯文本 XML，新增 `<scene>` 和 `<character>`/`<seg character>` 标签进行视觉编排）/ E. 媒体实时制作 AI（新增——无"思考"快速匹配 + 图像生成 API）/ F. 冒险日志 LLM。

4. **解析器两段式重构**：Line Generator（预处理：截行、分行号、判标签类型，几乎零延迟）+ Event Generator（Line → Event，含 SET/CHECKPOINT/BRIDGE 应用），中间用线程安全 Line Buffer 连接。Line Generator 检测到媒体标签时立即向 Task Generator 发送 Requirement 启动后台制作任务。

5. **异步时序模型**：`LLM 生成 ≥ 程序流式解析/媒体数据制作 ≥ UI 展示`。Tasks Buffer 独立于 Lines Buffer 运行——图像制作与叙事解析并行，Event Generator 消费到 SCENE/CHARACTER 事件时从 Tasks Buffer 取结果，未完成则等待。

6. **实现分 8 个阶段**：解析器重构（验证 Phase 1 无回归）→ 图像 API 模块 → scene/character 标签（纯文本模式兼容） → 媒体数据库 → 共创预构建流程 → 叙事实时制作流程 → Task Buffer 集成 → 图像模式新 UI。

**架构意义**：延续 Phase 1 核心哲学——LLM 只是建议者/编排者，程序做最终裁决和资源管理；异步预取隐藏延迟（bridge pre-fetch 思路的泛化）；关注点分离（导演只管编排，制作 AI 只管执行）。文本模式作为独立路径保留，不与图像模式耦合。

**依据**：`docs/spec/graph-mode-design-draft.md`。

### Story Context 架构拆分——ROUND1_PREFIX 与 ROUND_TEMPLATE 解耦

**背景**：07-28 的首轮 Prompt 重设计留下两个遗留问题：（1）`_format_story_context` 方法将 characters/locations 拼成一个 `{story_context}` 占位符，同时出现在 ROUND1_PREFIX 和冒险日志 Prompt 中——复用方式模糊，两端需求不完全相同；（2）`error_feedback` 为空时使用空字符串 `"\n"`，换行控制逻辑分散在代码和模板之间；（3）`appearance` 字段被 `_format_story_context` 静默丢弃——共创输出中的 required 字段从未进入 Prompt。

**决策**（commits `27f3445` → `2d04973`，6 次迭代）：

1. **`_format_story_context` 拆分为 `_format_characters` + `_format_locations`**（`faf1ecf`）：
   - 删除聚合方法，两个调用点各自控制 `##` 标题和顺序
   - 模板中 `{story_context}` 占位符拆为 `{premise}`、`{characters}`、`{locations}`——每个对应一个明确的 `_format_*` 返回值

2. **`appearance` 字段修复**（`27f3445`）：字符行格式从 `{name} ({role}) — {desc}` 扩展为 `{name} ({role}) — {desc} ({appearance})`——共创阶段的必填字段不再被丢弃。

3. **`error_feedback` 占位符化**（`9bf731a` + `0314e6e`）：
   - 空反馈从 `"\n"` 改为 `"(No issues)"`——统一占位符语义
   - 模板中 `\n{error_feedback}` 尾随换行由 build 方法拼接，模板不再控制间距

4. **命名体系统一**（`c45966c` + `2d04973`）：
   - `ROUND1_PREFIX`：`# Story Context` → `# Story Setting`（与 spec §4.2 一致）
   - `ROUND_TEMPLATE`：flat `**Bold:**` → `# Current Status` + `##` 子章节（`## Outline`/`## Variables`/`## Feedback`/`## Continue From`）
   - 移除 ROUND_TEMPLATE 中冗余的 `MIN_LINES`/`MAX_LINES`（已在 ROUND1_PREFIX 约束）
   - 删除未使用的 `NARR_LIMIT`/`DIAL_LIMIT` 占位符和 `LANGUAGE_SEG_LIMITS` 导入
   - 尾部指令：`Plan silently using "Before You Write". Satisfy every rule in "Requirements". Follow "Story Setting" and "Current Status".`

**架构意义**：ROUND1_PREFIX 持有 Story Setting（一次发送，永久锚定），ROUND_TEMPLATE 持有 Current Status（每轮更新）——职责清晰，独立修改。

**依据**：commits `27f3445`, `9bf731a`, `faf1ecf`, `0314e6e`, `c45966c`, `2d04973`；`docs/spec/prompt-design.md` §4.2-4.3；`src/storyloom/core/prompt_builder.py`。

### 冒险日志 Prompt 重设计——结构化架构对齐叙事 Prompt

**背景**：冒险日志 Prompt 是独立于叙事循环的单次 LLM 调用（结局时触发），优先级低于叙事 Prompt，但同样需要规范设计。旧版结构松散，缺少设计原则指导。

**决策**（spec `df20b6d` + impl `2020ba2`）：采用六段式架构——系统指令 → 格式说明 → 格式示例 → 要求说明 → 具体状态 → 尾部信息：

```
You are an adventure log author...

# Output Format — Markdown 三节（Chapter Recaps / Ending / Final State）
# Format Example — 英文 sci-fi 三章示例（含 Tess.Trust scoped variable）
# Requirements — 4 条
# Story Setting — Language / Premise / Characters / Locations
# Final Status — Outline（含 ↳ summary）+ Variables
尾部指令
```

**关键设计决策**：
- **示例先行**：格式示例在 Requirements 之前。英文 sci-fi 故事（The Scrap Heap / The Vega Corridor / The Dead Station）展示 `Tess.Trust: 85 / 100` 点号表示法
- **`_format_current_state()` 复用**：`## Variables` 节直接调用与叙事 Prompt 相同方法——number 带 `/ 100`、scoped 按 `[scope]` 分组——格式一致性确保 LLM 无歧义
- **`# Final Status`**：区别于叙事的 `# Current Status`——结局视角用 "final" 更准确
- **单一常量**：`ADVENTURE_LOG_PROMPT` 不拆 PREFIX/TEMPLATE——独立单消息调用无需分离
- **无 Prohibited 节**：输出格式简单（Markdown），失败模式不同于叙事 XML——不设独立禁止节以保持紧凑、生成更快

**API 变更**：`build_adventure_log_prompt()` 新增 `variables` 参数（供类型查找）。两个调用点（`game_loop.py`、`dev_cli/game_driver.py`）同步更新。

**依据**：commits `df20b6d`, `2020ba2`；`docs/spec/prompt-design.md` §5；`src/storyloom/core/prompt_builder.py`。

### 四个阶段 Prompt 全面审查与措辞修复

**背景**：冒险日志重设计完成后，对四个阶段 Prompt（共创追问、共创生成、叙事循环、冒险日志）做全面交叉审查。

**发现与修复**（commits `209a722`, `9150da2`, `18e3c41`）：

1. **叙事 Before You Write 措辞**（`209a722`）：
   - "Has the active node's goal been reached?" → "Can the active node's goal be reached?"
   - Before You Write 是创作前的无声规划——"can be" 准确反映规划思维，"has been" 回顾性视角不当

2. **共创生成 Before You Write 措辞**（`9150da2`）：
   - "the 1-3 variables that drive branches" → "the key variables that drive branches"
   - 代码与规范文档不一致。字段规范中变量上限可能 >3，规划阶段不应给更窄的数字

3. **共创生成 Before You Write 换行**（`18e3c41`）：
   - "Every route target must\n   hit a real node" → 合并为单行
   - 代码和规范文档均存在不必要的句中断行，一并修复

**审查结论**：四个阶段 Prompt 整体质量很高，结构一致、原则到位。

**依据**：commits `209a722`, `9150da2`, `18e3c41`；`docs/spec/prompt-design.md` §3.2, §4.2；`src/storyloom/core/co_create.py`, `prompt_builder.py`。

---

## 2026-07-28（周二）

> **概述**：10 次提交，两大核心功能落地——作用域变量（Scoped Variables）和叙事首轮 Prompt 前缀重设计，配套设计理论体系完善、共创 Prompt 无声规划模式、文档清理。版本号 1.1.0 → 1.1.1。315 测试全绿。

### 设计理论基础建设——三项范式框架 + 核心问题定义

**背景**：Storyloom 已有一套成熟的设计哲学（桥接、时序模型、双队列缓冲、本地数据优先），但这些理念散落在 spec 文档、工程日志、代码注释中——缺乏一个系统化的"为什么这样做"的理论陈述。需要一份不可撼动的设计基石文档，与 spec（"怎么做"）形成互补。

**决策**（commits `e75946e`, `70f968a`）：建立 `docs/theory/` 三个理论文件：

1. **`theory/README.md`**（07-27 晚，`e75946e`）：三项范式框架——
   - **范式一（批量生成）**：AI 一次性产出全部内容，交互与生成分离。自由度高、延迟为零，但内容预设
   - **范式二（完全实时）**：每次输入实时响应。自由度极高，但延迟直接暴露
   - **Storyloom（第三方向）**：以实时生成为基础，在用户消费期间完成生成（而非等待期间），通过结构化输出创造生成与展示的重叠窗口
   - 四个维度对比表（自由度/延迟/质量保证/状态）
   - 三个核心问题：① 内容质量保证（无人介入下的格式+逻辑把关）→ ② 消解生成延迟（让等待发生在体验期间，而非等待期间）→ ③ 自由度与延迟的矛盾（桥接以预期范围为前提，自由度与隐藏延迟方向相反）

2. **`theory/timing-model.md`**（07-28 早，`70f968a`）：延迟结构分析——
   - 指标重定义：TTFT（首字时间）vs 总生成时间——是两回事
   - 三因素模型：API 延迟 → Token 生成速率 → 内容消费速率
   - 三层流式模型（引擎→解析→展示）+ 双队列缓冲架构
   - 流式必然性论证：如果 LLM 生成比人阅读慢，唯一出路是让生成与展示重叠——流式解析是实现这一点的必要（但不充分）条件

3. **`theory/bridge-mechanism.md`**（07-28 早，`70f968a`）：桥接机制理论——
   - 核心思想：在玩家阅读当前内容时预获取下一轮内容
   - 三个可行性条件：结构化输出（有明确的"触发点"） + 可预测的输入空间（有限选项） + 生成与展示的重叠窗口
   - 设计约束：桥接位置不能太早（生成内容可能浪费）也不能太晚（窗口不够用）
   - 作为合成点：桥接机制是全部设计维度（Prompt 工程、流式解析、时序模型、状态管理）的交汇点

**更新规则**（`theory/README.md`）：theory 仅在重大理念转变时修改（与 spec 随实现频繁更新形成对比）。新增文件（如图像生成理论）可追加。

**依据**：commits `e75946e`, `70f968a`；`docs/theory/README.md`、`timing-model.md`、`bridge-mechanism.md`。

### 文档体系收尾——删除 course/，theory 引用贯通，obsolete 脚本清理

**背景**：理论文档到位后，三个清理动作：
1. `docs/course/`（课程评估报告 + 项目提案，共 1209 行）的理论性内容已提取到 `docs/theory/`，剩余课程特定内容无持续价值
2. `docs/README.md` 和 `CLAUDE.md` 的文档索引未包含 `theory/`
3. `scripts/rename_label_to_title.py`（label→title 批量重命名工具脚本，331 行）在重命名完成后属一次性工具

**决策**（commits `280ae6c`, `34abd78`, `6b96ae0`）：
- 删除 `docs/course/` 全部内容（`course-project-proposal.md` + `report.md`）
- `docs/README.md` 新增 `theory/` 到文档地图、阅读顺序、权威层级；`CLAUDE.md` 文档表新增 `theory/` 条目
- 删除 `scripts/rename_label_to_title.py`

**依据**：commits `280ae6c`, `34abd78`, `6b96ae0`。

### 共创 Prompt：Verification Checklist → Plan Silently（无声规划模式）

**背景**：共创生成 Prompt 的 "Verification Checklist"（8 项自检清单）与前面的 Field Specifications 和 Prohibited 内容高度重复——只是换了一种罗列方式。更根本的问题是：它以"输出后逐项对标"为逻辑，但 LLM 是自回归模型——token 产出后不可撤销，输出后对标已无意义。正确的方式是引导 LLM 在输出前做好无声规划。

**决策**（commit `330741c`）：删除完整的 Checklist 段，替换为 "Before You Write — Plan Silently" 指南：

```
1. The story — tier, premise, tone, language.
2. Who & where — protagonist, supporting cast, key locations.
3. What changes — the 1-3 variables that drive branches.
4. How it flows — the outline as a directed graph.
5. Self-check — verify compliance with the format and field specifications above.
```

5 步规划按因果依赖排序（故事→角色→变量→大纲→自检），引导 LLM 在生成 JSON 前先完成创意决策。同时修剪 Prohibited 段中与 Field Specs 重复的条目（markdown fences、root type、missing keys、protagonist count 等约束已在别处覆盖），移除过度 注标签（`(IMPORTANT)`），barrier statement 简化。

**关键理念转变**：从"输出后逐一核对"（verification mindset）到"写之前想清楚"（planning mindset）——对齐 LLM 的自回归生成本质。

**依据**：commit `330741c`；`src/storyloom/core/co_create.py`（+28/-36 行）；`docs/spec/prompt-design.md` §3.2。

### 作用域变量（Scoped Variables）——`Scope.Name` 点号表示法

**背景**：v2 数据模型引入 characters/locations/variables 后，变量系统的局限性暴露：所有变量是全局的（`state_vars` 为 `{name: value}` 扁平字典），角色专属变量（如"好感度"）无法跨角色共存——如果两个角色都有"信任度"，无法区分。且上限 3 个变量（`VARIABLE_CAP=3`）过于严格。类型数量限制（≤2 number、≤1 string）在无字符作用域场景下有意义（防止变量泛滥），但在有作用域后反而是不必要的约束。

**决策**（spec `1f8ebd8` + impl `ff78838`）：引入作用域（Scope）概念，使用 `Scope.Name` 点号表示法。

**核心变更**：

| 维度 | 旧 | 新 |
|------|-----|-----|
| `state_vars` 结构 | `{name: value}` 扁平字典 | `{scope: {name: value}}` 嵌套字典 |
| 变量引用 | `体力`（裸名称） | `耗子.信任度`（点号分隔）或 `体力`（GLOBAL） |
| `VARIABLE_CAP` | 3 | 6（全 scope 总量） |
| 类型上限 | ≤2 number, ≤1 string | 无类型数量限制 |
| `GLOBAL_SCOPE` | 无 | `"GLOBAL"`（默认 scope） |
| `SAVE_VERSION` | 2 | 3（breaking change） |

**引擎变更**（`game_loop.py`）：
- `GameState.__init__`：初始化时从 `scope` 字段（缺省=GLOBAL）分组存储 `_state_vars` 和 `_var_types`
- `GameState._split_var(var)`：新增静态方法——含 `.` 的变量名拆为 `(scope, name)`，裸名称返回 `(GLOBAL_SCOPE, name)`
- `GameState.apply_set()`：解析 scope → 在当前 scope 的字典中查找/操作变量。拒绝原因中显示原始变量引用（含 scope 前缀）便于调试
- `GameState._apply_number_op()` / `_apply_string_op()`：接受 `scope` 参数，操作 `_state_vars[scope][name]`
- `GameState.from_dict()` / `to_dict()`：嵌套序列化
- 条件求值（`block-spec.md`）：含 `.` 的变量名从对应 scope 取值；裸名称先查 `choice_dict` 再查 `state_vars["GLOBAL"]`

**共创验证器变更**（`co_create.py`）：
- `validate_variables()`：删除 numeric/string 类型上限检查，新增同 scope 内重复检测（跨 scope 同名合法）
- `validate_outline_cross_ref()`：scope 感知的变量引用验证
- `CO_CREATE_GENERATION_PROMPT`：变量数量约束从 "≤3 total, ≤2 number, ≤1 string" 改为 "≤$variable_cap total"，新增 scope 字段说明，格式示例含 `{"scope": "Mouse", "name": "Trust", ...}`

**Prompt 变更**（`prompt_builder.py`）：
- `_format_current_state()`：按 scope 分组——GLOBAL 变量无缩进无标题，角色 scope 显示 `[角色名]` 标题 + 2 空格缩进
- `_format_story_context()` / `build_adventure_log_prompt()`：`state_vars` 类型签名从 `dict[str, int | str]` 改为 `dict[str, dict[str, int | str]]`
- `ROUND1_PREFIX`：格式示例中 `<set var="trust"...` 改为 `<set var="Elena.trust"...`
- 状态展示格式：
  ```
  体力: 80 / 100
  所属势力: 自由佣兵
  [耗子]
    信任度: 10 / 100
  ```

**Session 适配**（`session.py`）：`_build_init_dict()` 构建嵌套 `state_vars`（`state_vars.setdefault(scope, {})[name] = initial`）。

**config.py**：`VARIABLE_CAP 3→6`，删除 `VARIABLE_NUMERIC_CAP`/`VARIABLE_STRING_CAP`，新增 `GLOBAL_SCOPE = "GLOBAL"`，`SAVE_VERSION 2→3`。

**存储层**：`save_manager.py` 无需修改——`SAVE_VERSION` 升级自动拒绝旧存档（用户决定）。`state_vars` 序列化格式自然跟随嵌套结构。

**测试**：315 passed，fixtures 和断言全面适配嵌套格式。关键新增：同 scope 重复检测、跨 scope 同名合法、`_split_var` 解析验证。

**设计考量**：
- `GLOBAL_SCOPE` 常量而非硬编码字符串——引擎内部统一引用，未来可改（如 `"global"` 或 `"_GLOBAL_"`）
- 裸变量名隐式归属 GLOBAL——向后兼容纯全局变量的旧存档（虽然 SAVE_VERSION bump 会拒绝它们，但迁移逻辑只需加 `scope: "GLOBAL"` 字段）
- 跨 scope 同名变量合法——不同角色的"好感度"独立，在共创验证器中通过

**依据**：commits `1f8ebd8`, `ff78838`；`docs/spec/data-model.md` §A.2；`docs/spec/block-spec.md` §5；`docs/spec/prompt-design.md` §3.2.5, §4.2-4.3。

### 叙事首轮 Prompt 前缀重设计——从"规则罗列"到"示例驱动 + 统一需求模板"

**背景**：`ROUND1_PREFIX`（~200 行 Python 字符串）是叙事引擎最重要的 Prompt——Round 1 作为永久锚定消息，其质量直接影响 LLM 在所有后续轮次的行为基线。但旧版存在两个结构性问题：

1. **伪代码示例无约束力**：旧版 "Structure" 示例全部是占位符（`narration text`、`option text`、`outcome narration`），只有结构骨架无叙事内容——LLM 看到的模板是骨架性的，无法传达"好的输出长什么样"
2. **规则与元素定义混杂**：Elements 描述、Core Rules、Quality Requirements 三个段落之间存在大量交叉引用和重复——同一约束（如 `<choice>` 的 `id` 引用规则、`<set>` 的 `var` 命名规则）在多处出现，修改时容易遗漏不一致
3. **禁止清单过于庞杂**：旧版 Prohibited 列出 9 项禁止（含对话引号、代词角色名等），其中大部分是元素规范的自然推论——既重复又削弱了核心禁止项的注意力权重
4. **缺少创作引导**：旧版纯粹是"格式规范 + 约束清单"——告知 LLM 不能做什么、必须包含什么，但未引导它如何将大纲中的故事目标转化为具体叙事

**决策**（spec `229facf` + impl `65031d3`）：全面重设计 `ROUND1_PREFIX`，对齐 §1.2 的设计原则（示例先行、正反双重覆盖、统一模板、无声规划）。

**新设计结构**：

```
# Output Format — 简化：仅行号 + XML-only 约束
# Examples — 两个完整故事示例（各 ~50 行）
# Requirements — 4 个元素 × 统一模板
# Prohibited — 3 项高频顽固错误
# Before You Write — 5 步无声规划
```

**两个完整示例**（替代旧版单骨架示例）：
- **Example 1**（Kael 酒馆线）：展示"多选择无 checkpoint"场景——纯粹的角色互动和氛围建立，不触发节点推进。元素覆盖：多角色对话、`<set>`、`<branch>` 交织、post-bridge 连贯叙事
- **Example 2**（Elena 古墓线）：展示"选择+checkpoint+双路线"场景——结局节点触发、scope 变量（`Silan.loyalty`）、`<route>` 条件路由、post-bridge 分化叙事

两个示例互补覆盖全部功能维度——LLM 看到的不再是骨架，而是完整的输出形态。

**统一需求模板**（每个元素规范化描述）：
```
## <element> — 标题
**Purpose**: 一句话定义
**Attributes**: (如适用) 属性表（Required/Description）
**Requirements**: 编号列表——具体规则
**Snippet**: (如适用) 代码片段
```

四个元素：`<seg>`、`<branch>`、`<choice>+<opt>`、`<set>`。新增元素按相同模板插入即可——模板化设计便于增量扩展。

**Prohibited 瘦身**：从 9 项缩减为 3 项高频顽固错误——
1. `<bridge/>` 数量不为 1
2. `<choice>`/`<set>`/`<checkpoint>` 在 bridge 之后（post-bridge 区域违规）
3. `<checkpoint>` `node` 或 `<route>` `target` 与大纲 node ID 不匹配

削减理由：其余 6 项（对话引号、代词角色名、`<set>` var 不存在、未到 checkpoint 节点提前触发、markdown fences、文本在 XML 外）或为元素规范的直接推论（对话格式已在 `<seg>` Requirements 中约束），或极少被触发——从 Prohibited 移除不会增加违规率，但可让保留的三项的注意力权重更集中。

**Before You Write（无声规划）**：借鉴共创 Prompt 的 Plan Silently 模式——5 步按因果依赖排序：
1. **节点大意**——本轮要达成的叙事目标
2. **场景与人物**——出场的角色和地点
3. **铺垫 → 交互**——构建到选择点的叙事推进
4. **分支后果**——每个选项的即时叙事后果
5. **Post-bridge 展开**——桥后的叙事发展

**block-spec 同步**：放宽两项约束——
- `at most one <choice>` → 0-N（可容纳无选择纯叙事轮次）
- `<branch>` can only contain `<seg>` 删除——允许更灵活的分支内容结构
- checkpoint summary 从 "1 sentence" 放宽为 "2-4 sentences"

**代码清理**（`prompt_builder.py`）：移除 4 个未使用的格式参数（`MIN_TAIL`、`REF_PRE`、`REF_SINGLE`、`REF_HALF`）及对应的 bridge 位置计算逻辑；`MIN_TAIL_LINES` 导入移除（常量保留于 config.py）。

**测试**：2 个断言更新（匹配新 Prompt 文本和示例内容）。315 tests green。

**依据**：commits `229facf`, `65031d3`；`docs/spec/prompt-design.md` §4.2；`docs/spec/block-spec.md`。

### 版本 1.1.1 + 清理

**背景**：累计变更——作用域变量（breaking SAVE_VERSION 2→3）+ 首轮 Prompt 重设计 + 共创无声规划模式 + 理论文档体系——达到 patch 版本级别。

**决策**（commit `2cc67b7`）：版本号 1.1.0 → 1.1.1。同步更新 `pyproject.toml` 和 `src/storyloom/__init__.py`。

**依据**：commit `2cc67b7`。

---

## 2026-07-27（周一）

> **概述**：12 次提交，完成共创数据模型 v2 的全面落地——JSON 输出格式、引擎适配、Web 层同步、多项缺陷修复。版本号 1.0.2 → 1.1.0。315 测试全绿。

### 共创 JSON 输出 + 数据模型 v2（Phase 2+3）——核心重构

**背景**：此前 Co-Create 的 `generate()` 使用自定义 `=== block ===` 分隔符 + INI 式变量行 + DSL 式 outline 路由语法。`CoCreateParser` 有 11 个解析方法（`split_blocks()`, `parse_story_config()`, `parse_variables()`, `parse_outline()`, `parse_routes()`...），每种格式有专属 parser——代码脆弱、错误信息不友好、LLM 格式偏离后重试无效。输出格式（`CoCreationResult` dataclass）与存档格式（dict）之间存在转换层。

07-26 的 spec 阶段已确定方案：LLM 输出 JSON → `json.loads()` 一行解析 → 输出格式 = 存档格式（零转换层）。

**决策**（commit `beeb0d3`）：全面重构共创管线——JSON 输出替换块分隔符格式。

**核心变更**：

1. **`CoCreateParser → CoCreateValidator`**：删除全部 11 个旧解析方法，新增 6 个 JSON 验证器：
   - `validate_json()` — JSON 解析 + 顶层键存在性检查
   - `validate_story_config()` — 4 字段（tier/title/language/premise）类型 + 约束验证
   - `validate_characters()` — 数组，每元素 4 字段（name/role/description/appearance）
   - `validate_locations()` — 数组，每元素 3 字段（id/name/description）
   - `validate_variables()` — 数组，每元素 3 字段（name/type/initial），类型白名单
   - `validate_outline_cross_ref()` — route target → node ID 引用完整性 + 变量名 → variables 列表交叉验证

2. **`CoCreationResult` 删除**：`generate()` 直接返回 dict（6 key：`story_config`/`characters`/`locations`/`variables`/`outline`/`outline_text`）——与存档格式完全一致，消除转换层。

3. **`CO_CREATE_GENERATION_PROMPT` 重写**：从 170 行块分隔符格式重写为 5 段 JSON 输出 Prompt（角色定义、完整 JSON 示例 + 屏障、逐块字段规范含正反双重覆盖、禁止模式含反例、自检清单）。完全对齐 `prompt-design.md` §3.2。

4. **存档格式 v2**：`SAVE_VERSION = 2`，顶层新增 `characters`/`locations`/`variables`，`story_config` 缩减为 4 字段（tier/title/language/premise）。

**级联变更**：
- `session.py`：`start_game(data: dict)` 替代旧的 `CoCreationResult`
- `save_manager.py`：`REQUIRED_FIELDS` 增加新顶层字段；`list_games()` `genre`→`premise`；`load()` 校验顶层 variables
- `game_driver.py`、`observer.py`、`web/sessions.py`、`web/server.py`：dict 访问模式

**测试**：315 passed（76 co_create + 239 others）。旧 parser 测试类替换为 6 个新 validator 测试类。全部存档 fixture 更新为 v2 格式。

**依据**：commit `beeb0d3`；`docs/spec/data-model.md` §1-3；`docs/spec/prompt-design.md` §3.2；`docs/api/co-create.md`。

### 叙事引擎适配 v2 数据模型（Phase 4-5）

**背景**：数据模型 v2 新增 `characters`/`locations`/`variables` 为顶层实体，`story_config` 从 11 字段缩减为 4 字段。引擎层所有依赖旧字段（`protagonist`/`genre`/`tone`/`conflict`）和旧变量注入路径（`story_config.get('variables')`）的代码必须同步更新。

**决策**（commit `36ea4f4`）：引擎层全面适配 v2。

**变更明细**：

| 模块 | 变更 |
|------|------|
| `GameState.__init__` | 接受 `variables: list[dict]` 直接注入（不再从 story_config 提取） |
| `GameState.from_dict` | 读取顶层 `variables` 字段 |
| `GameLoop.__init__` | 新增 `characters`/`locations`/`variables` 三个属性 |
| `GameLoop.to_save_dict` | 输出 `characters`/`locations`/`variables`；`story_config` 过滤为 canonical 4 字段 |
| `GameLoop.from_save_dict` | 读取 + 传递新顶层字段 |
| `GameLoop.stream_round` | `self.variables` 替代 `story_config.get('variables')` |
| `GameLoop.start_game` | 传递 `characters`/`locations`/`variables` 到 `build_round1` |
| `GameLoop.run_adventure_log` | 传递 `characters`/`locations` 到 `build_adventure_log_prompt` |
| `PromptBuilder.ROUND1_PREFIX` | 多字段 Story Context（genre/setting/protagonist/tone/conflict/characters）→ 单一 `{story_context}` 占位符 |
| `PromptBuilder._format_story_context` | **新增**静态方法——统一 Premise + Characters + Locations 格式，Round 1 和冒险日志共享（plan D15） |
| `PromptBuilder.build_round1` | 接受 `characters`/`locations`/`variables` 参数；删除旧字段提取逻辑 |
| `PromptBuilder.build_adventure_log_prompt` | 接受 `characters`/`locations` 参数；使用 `_format_story_context()` |

**设计考量**：

- **`_format_story_context()` 共享**（plan D15）：Round 1 和冒险日志都需展示世界设定——统一格式化方法避免字段罗列逻辑重复。
- **`ROUND1_PREFIX` 占位符化**（plan D9）：旧模板硬编码 genre/setting/protagonist 等字段名——`{story_context}` 单一占位符使模板与数据模型解耦，未来增减字段不触模板。
- **`story_config` 过滤**：存档仍保留 `story_config` 对象，但 `to_save_dict()` 仅输出 4 个 canonical 字段——多余的中间态字段不污染持久化层。

**测试**：更新全部 fixture（`SAMPLE_STORY_CONFIG` v2 格式，新增 `SAMPLE_CHARACTERS`/`SAMPLE_LOCATIONS`/`SAMPLE_VARIABLES`）和所有构造/方法调用匹配新签名。315 tests green。

**依据**：commit `36ea4f4`；`docs/spec/data-model.md` §1；plan D9、D15。

### Spec 文档全线同步 v2

**背景**：数据模型 v2 涉及 5 个核心文档的字段名/格式/常量变更。需在代码实现前后完成 spec 层对齐。

**决策**：4 个 commit 分步推进——先设计后实现：

1. **`3423377`** —— data-model.md、exec-flow.md、co-create.md 基础更新：
   - `data-model.md`：§1 GameState init（4-field story_config，top-level characters/locations/variables），§3 save format（v2），§A.2 常量表（`STORY_TITLE_*`, `zh-TW`, `SAVE_VERSION=2`）
   - `exec-flow.md`：§1.1 术语更新，§3.4 JSON 流程，§3.5 顶层变量初始化
   - `api/co-create.md`：`CoCreationResult → dict`，新字段表，验证规则更新

2. **`6efaff1`** —— data-model.md + exec-flow.md 细节打磨：§1 初始化代码块润色；§1–§4 删除代码内部引用，保持概念层面

3. **`74a65c2`** —— prompt-design.md 全文重写：
   - §3.2：JSON 字段规范（§3.2.2–3.2.6）+ 完整 `CO_CREATE_GENERATION_PROMPT` 文本
   - §4.2：`{background}/{protagonist}/{tone}/{conflict}/{characters}` → `{story_context}` 单一占位符
   - §4.4：删除 ~210 行完整中文示例（被 §4.2+§4.3 覆盖）
   - §5：冒险日志使用 `_format_story_context()` 格式；`{story_label}` → `{title}`

4. **`d3cb4bf`** —— 删除 prompt-design.md §6 迭代日志（重复于本工程日志），header 指向 engineering-journal.md

**依据**：commits `3423377`, `6efaff1`, `74a65c2`, `d3cb4bf`。

### 全局重命名：story-title `label` → `title`

**背景**：数据模型 v2 将故事名称字段从 `label` 改为 `title`——`label` 语义模糊（暗示"标签"，易与 CSS label、UI label 混淆），`title` 是小说/故事的行业标准术语。

**决策**（commit `27abaf8`）：全代码库批量重命名：

| 范围 | 变更 |
|------|------|
| 常量 | `STORY_LABEL_*` → `STORY_TITLE_*` |
| 复合名 | `label_hint`, `game_label`, `safe_label`, `story_label` → `title` 变体 |
| Dict key | `story_config['label']`, `metadata['label']` → `['title']` |
| JS | `config.label`, `g.label`, `GameState.storyConfig.label` → `.title` |
| `lang_meta` | `label_hint` key → `title_hint` |
| 字面量 | 错误/日志消息中 'Label' → 'Title' |
| 函数参数 | `save_manager`/`session` 中 `label` → `title` |

**保留项**：`VARIABLE_LABEL_CAP`（不同语义——变量名长度上限，非故事标题）。CSS class 和选择标签保留。

**辅助脚本**：新增 `scripts/rename_label_to_title.py` ——记录此次转换的工具脚本。

**依据**：commit `27abaf8`；314 tests green。

### Characters 字段合并：`traits` → `description`（5→4 字段）

**背景**：plan D10 决策——`traits`（"Calculating, morally grey"）独立字段破坏角色描述内聚性。玩家读到特性列表时缺乏叙事上下文，且写作实践中 traits 自然嵌入 description。

**决策**（commit `410ba9a`）：合并 `traits` 到 `description`，characters 从 5 字段（name/role/description/appearance/traits）缩减为 4 字段（name/role/description/appearance）。同步更新所有规范文档的 JSON 示例、字段表、验证规则。

**依据**：commit `410ba9a`；plan D10。

### 实现计划：共创数据模型重构

**背景**：v2 数据模型重构涉及 24 个文件、8 个阶段——spec 文档、引擎核心、解析器、存储层、Web UI、测试。需要系统化计划确保不遗漏。

**决策**（commit `133047b`）：新增 `docs/superpowers/plans/co-create-data-model-refactoring.md`——8 阶段 24 文件计划，16 项设计决策全部确认：

| 阶段 | 内容 |
|------|------|
| Phase 1 | Spec 文档更新（5 文件） |
| Phase 2 | 共创管线 JSON 化（parser→validator + prompt 重写） |
| Phase 3 | 存档格式 v2 + CoCreationResult 删除 |
| Phase 4 | 叙事引擎适配（GameState/GameLoop） |
| Phase 5 | PromptBuilder 适配 + `_format_story_context` |
| Phase 6 | Web API/JS 同步 |
| Phase 7 | 测试更新 |
| Phase 8 | 验证 + 清理 |

**依据**：commit `133047b`。

### Web JS 字段引用同步 v2

**背景**：引擎层数据模型 v2 后，Web 前端 JS 的字段引用仍指向旧 key（`config.setting`、`g.genre`）→ 游戏列表和预览页面显示 undefined。

**决策**（commit `3c02c51`）：
- `router.js` 游戏预览：`config.setting` → `config.premise`
- `router.js` 存档列表卡片：`g.genre` → `g.premise`

**依据**：commit `3c02c51`。

### 存档损坏不自动删除——用户决定

**背景**：`SaveManager.load()` 在版本不匹配/JSON 损坏/字段缺失时将文件标记为 corrupt 并调用 `_remove_corrupt()` 自动删除。静默数据销毁——用户看到 toast "存档损坏，请删除" 但文件已被删，无法手动恢复或检查原始内容。

**决策**（commit `c8f1ff4`）：删除 `load()` 中所有 `_remove_corrupt()` 调用。四种异常路径（版本不匹配、JSON 损坏、字段缺失、结构异常）统一抛 `ValueError` 并保留文件。UI 层 toast 通知用户，用户可重试或手动删除。

同步更新 `config.py` `SAVE_VERSION` 注释和 `session.py` docstring 反映新行为。

**依据**：commit `c8f1ff4`。

### Web UI：存档列表 hover 展开效果统一

**背景**：游戏列表（`#saves`）和 checkpoint 列表（`#saves/{game_id}`）的 hover 卡片展开效果此前用不同 CSS 实现——checkpoint 列表有展开动画，游戏列表没有。视觉风格不统一。

**决策**（commit `538c3a6`）：重命名 CSS modifier `sv-list--checkpoints` → `sv-list--expandable`，同时应用于两个视图。统一 hover 行为：meta 文本展开为多行、时间标签隐藏、卡片右移 + glow。

**依据**：commit `538c3a6`。

### Web UI：游戏列表卡片移除存档数显示

**背景**：游戏列表卡片 meta 区显示 "N saves"——截断时难看，展开时杂乱。存档数是实现细节，不应在主菜单层级展示。

**决策**（commit `ba30649`）：从卡片 meta 移除存档数。i18n 翻译保留在 `.po` 文件中（供未来可能的其他场景复用）。

**依据**：commit `ba30649`。

### 版本 1.1.0

**背景**：本轮交付了数据模型 v2（breaking change：存档格式 `SAVE_VERSION` 1→2）和多项 Web UI 修复——累积变更达到 minor 版本级别。

**决策**：版本号 1.0.2 → 1.1.0，同步更新 `pyproject.toml` 和 `src/storyloom/__init__.py`。

**依据**：commit `9cade00`。

### 打包修复：清理旧产物 + 版本专属 glob

**背景**：`scripts/build.sh` 未在构建前清理 `build/` 和 `dist/` 目录——旧版本的 wheel/sdist 残留在 `dist/` 中被一起复制到 release 目录。release 包体积膨胀且包含过期版本。

**决策**（commit `3bc4e22`）：
1. 新增 step [0/5]：构建前删除 `build/` 和 `dist/`
2. Release 目录只复制当前版本专属的 wheel 和 sdist（`storyloom_web-{VERSION}-*.whl` / `storyloom_web-{VERSION}.tar.gz`）

**依据**：commit `3bc4e22`。

### 设计理论奠基（07-27 晚间补录）

**背景**：Storyloom 的时序模型、桥接机制、双队列缓冲等核心设计理念散落在 spec 文档和代码注释中——缺乏系统化的"为什么"层面陈述。

**决策**（commit `e75946e`）：新增 `docs/theory/README.md`——三项范式框架（批量生成 vs 完全实时 vs Storyloom 探索方向）+ 三个核心问题（内容质量 → 消解延迟 → 自由度与延迟矛盾）+ 四个维度对比表。定义 theory 的定位（不可撼动的设计理念，仅在重大理念转变时修改）和与 spec 的关系（theory 描述"为什么"，spec 描述"怎么做"）。

此文件为 07-28 的 `timing-model.md` / `bridge-mechanism.md` 的理论扩展奠定基础。

**依据**：commit `e75946e`；`docs/theory/README.md`。

---

## 2026-07-26（周日）

> **概述**：共创数据模型 v2 设计阶段——spec 重设计、实现计划、代码基础准备。4 次提交，涵盖从概念到 spec 全流程。

### 共创数据模型重设计——JSON 输出，11→4 字段，独立角色/场景块

**背景**：`CoCreateParser` 的 `=== block ===` 分隔符解析有 11 个 micro-parser，每个有自己的错误格式。`story_config` 有 11 个字段（tier/label/language/genre/setting/protagonist/tone/conflict/synopsis/variables/characters）——混杂了故事元数据、叙事内容、游戏机制变量。`characters` 作为 `story_config` 的内嵌数组，缺少结构化字段（外观、特质）。没有 `locations` 概念——场景定义散落在 setting 和 goal 中。Outline 的 `routes` 字段使用 DSL 语法（`go if A==5` / `go if B>3` / `go`），parser 需要正则匹配箭头、解析条件表达式。

核心洞察：输出格式 = 存档格式——消除 `CoCreationResult → save dict` 的转换层。LLM 的 JSON 输出精确性远高于自定义 DSL——业界共识是 LLM 输出 JSON 的可靠性最高。

**决策**（commit `0bf5140`）：

| 维度 | 旧 | 新 |
|------|-----|-----|
| LLM 输出格式 | `=== block ===` 分隔 | JSON（`json.loads()` 一行解析） |
| story_config 字段 | 11 个混杂字段 | 4 个 canonical 字段（tier/title/language/premise） |
| 角色表示 | story_config 内嵌数组，3 字段 | top-level 数组，4 字段（name/role/description/appearance） |
| 场景表示 | 无——散落在 setting/goal | top-level `locations` 数组（id/name/description） |
| 变量表示 | `=== variables ===` 块，INI 行 | JSON `variables` 数组（name/type/initial） |
| Outline routes | DSL（`go if A==5`） | 结构化 JSON（`[{target, condition?}]`） |
| 存档版本 | `SAVE_VERSION = 1` | `SAVE_VERSION = 2` |
| Parser 代码 | 11 个解析方法 | `CoCreateValidator` 6 个验证方法 |

**spec 文档**（`docs/spec/co-create-data-model-v2.md`——在 spec 提交中内嵌）：完整字段定义、JSON 示例、验证规则、对比表。

**依据**：commit `0bf5140`。

### 标签重命名 + traits 合并——设计确认

**背景**：数据模型 v2 设计中两个字段级决策在 spec 后经过进一步讨论后细化：

1. **`label` → `title`**：`label` 在 Web UI 中与 HTML `<label>` 和 CSS label 产生命名冲突，且在小说领域 `title` 是行业标准术语。
2. **`traits` → `description` 合并**（plan D10）：`traits`（"Calculating, morally grey"）独立字段破坏角色描述内聚性——角色特质在叙事中自然从 description 中浮现，不应另起一个分离字段。

**决策**：
1. 全代码库 `label` → `title` 批量重命名（commit `27abaf8`，在次日执行）
2. Spec 中 characters 从 5 字段（含 traits）简化为 4 字段（commit `410ba9a`）

**依据**：commits `27abaf8`, `410ba9a`。

---

## 2026-07-25（周五）

### 课程文档目录重组

**背景**：课程评估报告 `docs/course/report.md` 及相关课程文档散落在 `docs/` 根目录——与工程规范文档（`spec/`）和工程日志混在一起，语义边界模糊。

**决策**（commit `692fc99`）：将课程相关文档移入 `docs/course/` 统一目录。课程材料与工程文档物理隔离。

**依据**：commit `692fc99`。

---

## 2026-07-21（周二）

> **概述**：10 次提交，集中在两大领域——共创 Prompt 重构（从"格式叮嘱"到"设计体系"）、打包/Web 缺陷修复。版本号 1.0.1 → 1.0.2。

### Co-Create 生成 Prompt 7 段式重构 —— 对齐叙事 Prompt 设计体系

**背景**：`CO_CREATE_GENERATION_PROMPT` 约 55 行，基于 `string.Template` 占位符替换——`$example_variables`、`$example_goal` 等由 `_LANG_META` 注入。存在三个结构性问题：(1) 设计理念与叙事 Prompt（`ROUND1_PREFIX` + `ROUND_TEMPLATE`）脱节——后者有成熟的"示例先行 + 正反双重覆盖 + 显式禁止 + 注意力标签"体系，前者仍是简单的"规则罗列 + 模板填充"；(2) 格式示例为中文（语言感知注入），但 LLM 最擅长从英文示例学习结构——中文内容示例可能被误读为"必须用中文写变量名"；(3) 缺少系统化的禁止清单和自检机制，LLM 犯错后只能通过解析失败→重试来修复。

**决策**：用 7 段式英文 Prompt 替代占位符模板，完全对齐叙事 Prompt 的 `prompt-design.md` §1.2 设计原则。

**7 段结构**：
| 段 | 作用 | 对应原则 |
|----|------|----------|
| 角色定义 | 明确任务边界——"基于对话生成设定，非写故事" | — |
| 完整格式示例 + 屏障 | 英文示例展示三块完整结构与引用关系；显式声明示例仅供格式参考 | 示例先行、示例-规则屏障 |
| 逐块字段规范 | 每个块的字段含义、约束、必填/可选，route target 引用规则 | 关键处不吝笔墨、具体优于抽象 |
| 禁止模式 | 逐条列出已知错误模式（缺字段、route 虚悬、超变量上限、markdown 围栏） | 显式禁止优于隐式模式、正反双重覆盖 |
| 自检清单 | 输出前逐项自查——引导 LLM 生成末尾做结构化验证 | 注意力标签 |

**语言策略**：格式示例使用英文（与叙事 Prompt 的 Kael 示例策略一致——LLM 学结构，不学内容），输出语言通过 `$language` 占位符控制。仅 `label_hint` 通过 `lang_meta/{lang}.json` 注入（非完整示例），避免语言注入扩散到结构学习层。

**Prompt 文本关键改进**：
- 所有 `story_config` 字段显式标注 `REQUIRED`，消除"可选/必填"歧义
- Route target 引用规则从"must match — cross-check"（验证心态）改为"Copy verbatim — references, not new names"（过程指引）
- 变量引用一致性：route conditions 只能引用 `=== variables ===` 中声明的变量
- 自检清单引导 LLM 在生成末尾逐项自查（字段完整性、引用一致性、节点数匹配、禁止模式）

**Spec 同步**（`6da1c74`）：`prompt-design.md` §3.2 合并 §3.2-3.4（原为三个独立子节）为统一 §3.2，7 段→5 段（交叉一致性约束内嵌于逐块规范 + 禁止清单中，不独立成段）。修正 `lang_meta` 注入范围描述（仅 `label_hint`，非完整示例）。

**依据**：commits `6eaff12`, `6da1c74`；`src/storyloom/core/co_create.py` `CO_CREATE_GENERATION_PROMPT`（~100 行→~170 行，占位符驱动→设计体系驱动）；`docs/spec/prompt-design.md` §3.2（合并后统一章节）。

### Outline 约束措辞强化 —— 三级收紧

**背景**：Co-Create 7 段式重构后，outline 块规范仍有两处可被 LLM 绕过的薄弱点：(1) `[node]` 字段无 REQUIRED 标注，与 `story_config` 块约束力度不一致；(2) route target 规则仅说"必须匹配"，未说明不匹配的后果——LLM 可能理解为"建议"而非"硬性要求"；(3) 最终节点的 `routes:` 空值规则未禁占位词——LLM 可能写 `routes: (ending)` 或 `routes: 无`。

**决策**（commit `cc419ea`）：
1. 所有四个 `[node]` 字段（`id`、`title`、`goal`、`routes`）显式标注 REQUIRED——与 `story_config` 块约束力度对齐
2. Route target 规则从中性"引用关系"改为后果导向："targets are node ids, not descriptions — mismatch = rejection"——明确告知 LLM 不匹配会导致整个生成被拒绝
3. 最终节点禁止扩展：从"no arrows, no '(ending)'"扩展为"no arrows, no annotations, no placeholder words"——堵住 `无`、`结束` 等占位词

**依据**：commit `cc419ea`；`src/storyloom/core/co_create.py` outline 块规范 4 行变更。

### Round N 选择缺失提醒 —— 引擎感知 + Prompt 反馈

**背景**：LLM 偶尔产出不含 `<choice>` 的轮次——纯叙事无交互，玩家只能被动阅读。此前引擎对此完全无感知——解析器不报告 choices 为空是异常还是有意为之，Prompt 也无相关反馈机制。

**决策**（commit `7697838`）：轻量级引擎感知 + Prompt 反馈，不改架构。

- **Phase 5 检测**：`parsed.choices` 为空 → 设置 `no_choices = True`，传入 `build_round_n()`
- **Prompt 注入**：`build_round_n()` 新增 `no_choices_last_round: bool = False` 参数（默认 False，向后兼容），为 True 时在 error feedback 区追加：*"Reminder: last round had no player choices. Include at least one `<choice>` element so the player can interact with the story."*
- **设计考量**：归入 error feedback 通道而非独立 Prompt 段——利用已有的错误反馈注意力权重，且无选择确实是"可改进的状态"而非"破坏性错误"

**依据**：commit `7697838`；`src/storyloom/core/game_loop.py` Phase 5（+1 行检测）、`src/storyloom/core/prompt_builder.py` `build_round_n()`（+7 行）；`tests/test_prompt_builder.py` 新增 2 个测试。

### Web 游戏模式状态泄漏修复

**背景**：用户在游戏中切换到 auto 模式 → 离开游戏 → 重新进入——此时模式按钮显示 manual 图标，但系统实际以 auto 节奏推进。根因：`_mode` 是模块级 IIFE 变量，`render()` 函数未重置该变量——离开时 Web 的 SPA 路由切换不销毁 JS 模块闭包。

**决策**（commit `35572b8`）：`render()` 入口显式重置 `_mode = 'manual'` + 调用 `_updateModeButton()` 同步按钮标题/图标。与 `exec-flow.md` §4.5 默认 manual 声明一致。

**依据**：commit `35572b8`；`src/storyloom/web/static/js/game.js` `render()`（+13 行）。

### 打包修复：PyInstaller 遗漏 lang_meta JSON + 平台名可读化

**背景**：两个打包相关问题：
1. i18n 重构（`b581a90`）将 `_LANG_META` 从内联 dict 外部化为 `lang_meta/{lang}.json`，`pyproject.toml` 正确声明了 package-data（wheel 正常），但 `build.sh` 的 PyInstaller 命令遗漏 `--add-data` 标志——打包后的 exe 找不到 JSON 文件，`_load_lang_meta()` 在 `lang == DEFAULT_LANGUAGE ('en')` 时抛出 `FileNotFoundError`
2. `build.sh` 的 zip 文件名直接使用 `uname -s` 输出——Windows（MINGW64_NT-10.0-26200）产生不可读的平台标识

**决策**：
1. `build.sh` PyInstaller 命令新增 `--add-data "src/storyloom/core/lang_meta:storyloom/core/lang_meta"`（commit `533184d`）——与已有的 `locale`、`static` 数据目录并列
2. `build.sh` 新增平台名映射——`MINGW*/MSYS*/CYGWIN*`→Windows、`Darwin`→macOS、`Linux`→Linux——用于 zip 文件名（commit `526150e`）

**依据**：commits `533184d`, `526150e`；`scripts/build.sh`；Fixes #25（follow-up）。

### 课程评估综合报告

**背景**：需提交课程项目答辩材料——涵盖背景、设计理念、实践过程、课程联系、工作量分解、构建过程、AI 协作心得。

**决策**（commit `2e6239e`）：新增 `docs/course/report.md`（1065 行），8 章结构：
1. 项目背景与动机
2. 9 大核心设计概念详解（Prompt 工程、bridge 机制、时序模型、流式解析、双队列缓冲、本地数据优先、错误处理、i18n、引擎-UI 分离）
3. 开发实践与迭代过程
4. 课程知识联系
5. 工作量分解
6. 构建与打包流程
7. AI 协作方法论与心得
8. 未来展望

含实验数据、Prompt 架构总览图、`<!-- future-update -->` 标记供后续维护。

**依据**：commit `2e6239e`；`docs/course/report.md`。

### 版本 1.0.2

**背景**：本轮修复了 PyInstaller 打包缺陷（lang_meta 遗漏）并完成了共创 Prompt 重构——累积变更足以形成新的 patch 版本。

**决策**：版本号 1.0.1 → 1.0.2，同步更新 `pyproject.toml` 和 `src/storyloom/__init__.py`。

**依据**：commit `a45739a`。

---

## 2026-07-19（周日）

### Continue 功能完整实现 —— `.last_played.json` 追踪 + 自动恢复 + 存档 API

**背景**：Web UI 主菜单的 Continue 按钮此前靠 `list_games()` 扫描 `saves/` 下所有目录的 `mtime` 来确定"最近玩过"的游戏——O(N) 扫描，且存在致命缺陷：`load_game()` 是只读操作（不产生新文件），加载存档后目录 mtime 不变 → Continue 无法识别刚加载的游戏为"最近玩过"。

**决策**：引入 `saves/.last_played.json` 单一追踪文件，实现 O(1) Continue。

1. **`SaveManager.write_last_played(game_id, filename)`**：每次 `save()` 和 `load_game()` 时写入追踪记录。文件格式 `{"game_id": "...", "filename": "...", "updated_at": "..."}`，原子写入（temp + `os.replace`）。
2. **`SaveManager.read_last_played()`**：读取追踪文件 → 校验 `game_id` 目录和 `filename` 存档文件是否存在 → 自动清理过期引用（目录/文件已删除 → 删除追踪文件 → 返回 None）。
3. **`GameSession.load_game()` 写入追踪**：加载成功后调用 `SaveManager.write_last_played()`——修复"加载的游戏不被识别为最近玩过"的核心 bug。
4. **CLI 适配**：`game_driver.py` 的 Continue 路径优先读 `.last_played.json`（O(1)），追踪文件不可用时回退到目录 mtime 扫描。
5. **Web API**：新增 `GET /api/saves/last-played` 单一端点替代原来的两次 API 调用（先 list games 再确定最近）。
6. **存档文件自动清理**：`delete_game()` / `delete()` 时检查并清理过期追踪引用。

**Continue 自动恢复流程**（commit `ec2c5c5`）：
- 前端 Continue 点击 → `GET /api/saves/last-played` → 获取 `game_id` + `filename`
- 后端 `GameSession.load_game(game_id, filename)` → 恢复 GameLoop → 静默预览模式
- 前端 `#game-preview` 页面展示存档信息，用户点击"开始冒险"→ `POST /api/game/{id}/start` → 进入游戏

**配套端点**（commits `8386e48`, `6c1a046`）：
- `POST /api/co-create/generate`：生成后立即调用 `GameSession.start_game()` 创建 `_init.json`，返回 `game_id`
- `POST /api/game/{game_id}/start`：调用 `gl.start_game()` 启动 Round 1 流式 Prompt
- `POST /api/saves/{game_id}/load/{filename}`：通过 `SaveManager` 读取存档数据供预览
- `6c1a046` 重构：前端存档读取统一走 `GameSession.read_save()` 而非直接调 `SaveManager`——保持 `GameSession` 作为 UI 层唯一入口

**无存档 Toast**（commits `033a46a`, `143b913`）：Continue 时若无存档（`read_last_played()` 返回 None），前端显示 toast 提示，i18n 双语（中/英），3 秒自动消失。Toast 增加 `transitionend` 兜底——`animationend` 在某些浏览器不触发时用 `transitionend` 做二次清理，并增加 `console.error` 日志辅助调试。

**依据**：commits `adf33fe`, `ec2c5c5`, `6c1a046`, `8386e48`, `033a46a`, `143b913`；`docs/spec/data-model.md` §3.1 目录结构。

### Web UI 全面搭建 —— 主菜单、共创聊天、过渡页面

**背景**：Web UI 此前仅为 comment-only skeleton（commit `6a2d97f`）。需在一天内搭建完整的端到端用户流程：主菜单 → 共创 → 过渡 → 游戏预览 → 游玩。

**决策**：单页应用（SPA）架构——`index.html` 单页面，hash router 驱动视图切换，FastAPI 后端提供 REST API + SSE 流式端点。

**架构**：
```
src/storyloom/web/
├── server.py              # FastAPI app + 全部 API 端点
├── sessions.py            # 内存 session 管理（game_id → GameLoop）
├── static/
│   ├── index.html         # SPA 壳
│   ├── css/main.css       # 暗色终端美学（CSS 变量体系）
│   └── js/
│       ├── state.js       # 全局状态 + i18n T 字典 + config 持久化
│       ├── router.js      # hash router + 视图渲染
│       ├── api.js         # API 调用封装
│       ├── co-create.js   # 共创聊天界面逻辑
│       ├── display.js     # 游戏画面渲染
│       ├── credits.js     # 制作人员数据
│       └── sse-client.js  # SSE 流式客户端
```

**主菜单**（commit `1a99f1c`，+1299 行）：
- 6 按钮（New Game / Continue / Load Save / Settings / Credits / Exit），CSS hover-grow 动画
- Settings 面板：语言切换、API 配置（base URL / key / model）——展示模式 + 铅笔编辑切换，API key 掩码显示
- `GET /api/config` 返回配置时**不**返回明文 API key（安全）；`POST /api/config` 校验语言白名单
- Credits 叠加层——从 `credits.js` 数据文件渲染
- 前端 i18n：`_()` 函数镜像 gettext 约定，`storyloom.po` 同步更新全部菜单/设置/credits 翻译
- 语言切换后重新获取 DOM overlay（修复切换后 settings 面板丢失 bug）
- 暗色终端美学：CSS 变量体系（`--bg`, `--fg`, `--accent` 等），统一视觉语言

**Menu 功能合并**（commits `2628e76`, `af67899`）：
- Continue 一键直达：直接加载最近存档并进入游戏预览
- Load Save 合并 load/delete 为统一界面——先选游戏再选存档
- Credits 独立屏幕

**共创聊天界面**（commits `f922feb` + `15ab2eb`，+1327/-244 行）：
- 聊天式 UI：用户输入 → 气泡显示 → LLM 回复流式展示
- Q&A 端点：`POST /api/co-create/send` → SSE 流式返回 LLM 回复
- 生成端点：`POST /api/co-create/generate` → 触发完整生成管线
- 重试端点：`POST /api/co-create/retry-generate` → 生成失败后重试
- 打字指示器动画（commit `d91910a`）：弹跳圆点（bouncing dots），纯 CSS 动画
- 多次 CSS 迭代微调（`f8ab943` → `2541f0c` revert → `d4b9b82` → `0dfa5f6` revert → `a70be94`）：typing indicator 加固和返回箭头居中对齐经两次尝试和 revert，最终用 `transform: translateY(-2px)` 微调

**过渡页面**（commits `77a5385` + `dac2e0c`）：
- **#game-init**（Start 后）：居中"正在生成设定…" + 弹跳圆点 → 自动调 generate → 跳转预览
- **#game-preview**（Generate 后）：展示故事 label + setting，返回按钮可中止回菜单，"开始冒险"按钮启动 Round 1
- 阶段状态清理（commits `9fc83c0`, `02d3dc3`）：移除冗余 CSS，`CoCreateView` 退出时 reset 阶段状态，菜单级 session 清理防止状态泄漏

**API 修复**（commit `88d1301`）：流式响应路径缺少空 choices 检查——某些 OpenAI 兼容代理返回 `choices: []` 时触发 `IndexError`。在 `stream_chat_iter()` 中增加 `if not choices: continue` guard，与 `_extract_content()` 已有逻辑对齐。

**依据**：commits `6a2d97f`, `1a99f1c`, `f922feb`, `15ab2eb`, `d91910a`, `f8ab943`, `2541f0c`, `d4b9b82`, `0dfa5f6`, `a70be94`, `77a5385`, `9fc83c0`, `dac2e0c`, `02d3dc3`, `88d1301`, `d19a323`；2646 行 Web UI 代码（14 文件），引擎核心 +120 行（5 文件）。

### 配置调整：STORY_LABEL_MAX_CHARS 15 → 30

**背景**：用户反馈中文故事标签经常超过 15 字符限制——中文字符信息密度高，15 字符仅约 7-8 个中文字，不足以表达有意义的故事名称。

**决策**：`STORY_LABEL_MAX_CHARS` 从 15 提升至 30。同步更新 `co_create.py` 中的 Prompt 约束和 `data-model.md` §A.2 常量表。

**依据**：commit `808f74a`。

### 其余 Prompt 修复（07-18 尾，补充记录）

**背景**：两项 Prompt 微调在 07-18 晚间完成，未写入当日日志。

1. **活跃节点措辞优化**（commit `371664b`）：原 Prompt 中 "Active Node" 行暗示"你需要在这一轮推进进度"——LLM 倾向于在每轮强行触发 checkpoint。改为中性表述 "Current chapter: {title}"，去除进度压力暗示。
2. **Goal 定位拓宽**（commit `1d1dffb`）：共创 Prompt 中 goal 约束原为聚焦单场景——改为覆盖章弧（chapter arc），goal 从"单场景任务描述"升级为"全章剧情概览"。

**依据**：commits `371664b`, `1d1dffb`；与 07-18 "Co-Create 大纲 goal 提示词优化"条目互补。

---

## 2026-07-20（周一）

> **概述**：Storyloom 历史上最密集的开发日——60+ 次提交，跨越 Web 游戏界面、打包发布、引擎线程安全、提示词系统、存档浏览器、UX 打磨六大领域。版本号从 0.1.0 跃升至 1.0.0，标志着首个可分发版本诞生。Web UI 从主菜单+共创的"半成品"进化为完整的端到端游戏体验。

### Web UI 叙事游戏界面 —— 核心玩法循环与 SSE 流式集成

**背景**：Web UI 此前仅有主菜单、共创聊天和过渡页面——缺少核心的"玩游戏"能力。需从零搭建完整的叙事游戏界面：流式接收引擎事件 → 按节奏逐段展示故事 → 渲染选择项 → 处理玩家交互 → 结局流程。架构上需对齐 CLI 的 `game_driver.py` 模式（事件队列 + 单消费者显示循环），同时适配 Web 端的异步特性。

**决策**：四层架构——服务端 daemon 线程运行 `GameLoop.stream_round()` → `queue.Queue` 缓冲 → async SSE generator 轮询出队 → 前端 `game.js` 事件队列 + 单消费者 `_displayTick()` 显示循环。

**服务端线程桥接**（`server.py` + `sessions.py`）：
- `store_game_stream()` 创建每游戏 ID 独立的 `queue.Queue` + `threading.Event` stop 信号
- daemon 线程重复调用 `gl.stream_round()`，迭代生成器，将每个事件 push 入队
- 遇 `options` 事件时阻塞在 `wait_for_choice()`（`threading.Event.wait(timeout=300)`）
- `POST /choice` 端点接收玩家选择 → `gen.send(key)` → 生成器恢复，产出 post-choice 事件
- async `event_generator()` 每 100ms 轮询队列，产出 SSE 格式消息；队列空时每 15s 发 `: keepalive` 注释防代理超时

**前端显示循环**（`game.js`，637 行）——完全对齐 CLI `game_driver.py` 的单消费者模式：
- SSE 事件处理器纯做"接收"——push 事件到 `_eventQueue` + 调 `_wakeDisplay()`
- 单消费者 `_displayTick()` 每次取一个事件显示，按节奏模式决定何时取下一个
- 状态机：队列有数据 → pop + 显示 + 进入节奏等待 → 队列空 → 检查 `_optionsPending`（展示选择）→ 检查 `_ending`（展示结局）→ 进入 150ms 轮询 + 500ms 防抖 loading 指示器
- 节奏模式：auto（`setTimeout` 按速度档位 2667/2000/1000/667ms）vs manual（`_waitForUserAdvance()` Promise，由 click/Space/Enter resolve）

**显示循环节奏演变**（5 次迭代修复）：
1. `593b9d5`：分离 mode 检查与 options-pending 检查——修复 manual 模式下选择后被 auto 逻辑覆盖的 bug
2. `a40bb4d`：移除 options-pending 时的 200ms 加速——选择始终在队列自然排空后出现
3. `9e0dbd4`：post-choice 内容从未显示——`_handleOptions()` 返回后未重启显示循环
4. `72f219c`：修复 auto→manual 切换时额外消耗一个 segment 的 bug
5. `3235c4d`：修复 auto 模式 burst、loading 闪烁、移除 manual 模式"按空格继续"提示——loading 指示器 500ms 防抖

**SSE 关键修复**（`cc80ad6`）：原 keepalive 路径使用 `asyncio.sleep(15)`——在 options 事件后队列排空，generator 进入 15s sleep，post-choice 事件延迟达 15s 才送达前端。改为 100ms 短轮询后事件在 100ms 内送达，loading 闪烁问题一并解决。

**选择面板**（`display.js` + `game.js`）：
- 扁平化引擎评估后的选择对象 → 构建按钮，禁用项显示条件原因（如"需理智值 >= 30，当前：20"）
- 居中绝对定位面板（`a3c11cd`）：max-width 420px、`scale(1.02)` hover 动画、速度设置面板、生成失败时返回按钮
- 渐变遮罩防文字穿透（`746ec6d`）、移除 CLI 遗留的 `[1] [2]` 编号前缀（`f90fec8`）
- 选择后追加绿色选择文本 → 清空面板 → `sendChoice()` 到服务端 → 重启显示循环（含节奏）

**创建验证**（`078c702`）：至少一条用户消息存在才允许点击 Start 进入生成——防止空白共创。

**依据**：commits `2b345f6`, `fba64a5`, `3235c4d`, `593b9d5`, `9e0dbd4`, `a40bb4d`, `079bab0`, `cc80ad6`, `a3c11cd`, `746ec6d`, `f90fec8`, `5fd12ae`；`src/storyloom/web/static/js/game.js` (637 行)、`display.js` (473 行)、`sse-client.js` (146 行)；`exec-flow.md` §4.5 完整实现。

### 游戏退出与线程安全 —— 6 次迭代消除全部竞态

**背景**：最初的游戏流实现没有任何停止机制——用户导航离开后 daemon 线程无限运行，持续消耗 API token。更复杂的是，daemon 线程可能在 3 个不同位置被阻塞：(1) `stream_round()` 内 `result_queue.get(timeout=180)` 等待 API 块；(2) `wait_for_choice()` 的 `Event.wait(timeout=300)`；(3) `stream_round()` 生成器 yield 点之间。

**决策**：三级解除阻塞机制 + 引用隔离 + 防御性清理——6 个 commit 逐步推进：

1. **`5cc1187`**——引入 `_game_stop_events` 字典（每 game ID 一个 `threading.Event`）：
   - `request_stop_game_stream()` 设置 stop event + 唤醒 `wait_for_choice()`
   - daemon 线程 `run_loop()` 在 3 个检查点读 stop 信号：`stream_round()` 前、每个事件 yield 后、`wait_for_choice()` 返回后
   - `pop_game_stream()` 增加队列身份检查——旧线程的 `finally` 不能移除新流的 queue

2. **`ca7abac`**——局部 stop-event 引用防覆盖竞态：
   - `store_game_stream()` 返回 `(queue, stop_event)` 元组
   - daemon 线程捕获局部 `stop_evt` 引用，直接读 `stop_evt.is_set()`，免疫全局字典覆盖

3. **`d5313ff`**（引擎层核心修复）——`GameLoop.cancel()` sentinel：
   - 问题：daemon 线程卡在 `stream_round()` 内部 `.get(timeout=180)` 时 stop 信号无法到达（只在生成器 yield 点检查）
   - 解决：`cancel()` 向 `_active_queue` 和 `_pending_queue` 同时注入 `__cancel__` sentinel——覆盖 `_launch_api()` 设置 pending queue 与 `stream_round()` 捕获它之间的窄窗口
   - `stream_round()` 在 `.get()` 后立即检查 sentinel → 返回而不 yield 错误事件
   - `request_stop_game_stream()` 三重并行：`gl.cancel()` + set stop event + wake `wait_for_choice()`

4. **`eea1582`**——渲染时清空 `_eventQueue` 和 `_optionsPending`：用户中途退出后立即继续 → 上次 session 残留事件仍在队列 → 显示循环直接消费 → loading 被跳过

5. **`22e071d`**——loading 退出时显式停止显示循环：loading 期间退出（SSE 尚未建立）→ EventSource CONNECTING → 浏览器不触发 `onerror` → SSEClient Promise 永不 resolve → `_stopDisplayLoop()` 永不运行。在 loading 退出路径显式调用 + `render()` 防御性调用

6. **`784e054`**——per-stream GameLoop 引用防 cancel 错目标：`request_stop_game_stream()` 通过全局 `_game_loops` 字典调 `gl.cancel()`——在 `game_stream` guard 中错误（`save_start` 已存储新 GameLoop）。新增 `_game_stream_loops` 字典，在流创建时捕获引用；guard 使用 `get_game_stream_loop()` cancel 旧 GameLoop → 轮询最多 5s 等旧线程 `finally` 执行完毕

**依据**：commits `5cc1187`, `ca7abac`, `d5313ff`, `eea1582`, `22e071d`, `784e054`；`src/storyloom/core/game_loop.py` `cancel()` 方法、`src/storyloom/web/sessions.py` 三级状态管理。

### 结局流程与冒险日志

**背景**：最初结局使用 modal 弹窗（"查看日志"/"退出"两个按钮）——中断叙事沉浸感。冒险日志在半途主动退出时也生成——但未完成的故事弧不应该有"完结"日志。结局 modal 的时机也有 bug：在 bridge_text 段还在队列中排队时就弹出。

**决策**：三个层面的重构：

1. **Inline 绿色结局选项**（`078c702`）——替换 modal：
   - 结局选择渲染为单个绿色文字按钮，inline 在选择面板中，与叙事选择保持一致的视觉风格
   - 文案："The story has ended. View adventure log." → 点击直达 `#adventure-log/{gameId}`
   - 同步加入 SSE `save` 事件监听 → checkpoint 自动存档时弹 "Saved" toast

2. **冒险日志页面**（`3898e0a`）——新增 `adventure-log.js`（160 行）：
   - `#adventure-log/{gameId}` 路由，轮询 `GET /api/game/{id}/adventure-log`（1s 间隔，最大 30 次 = 30s 超时）
   - Markdown 渲染（CDN `marked.js`），纯文本 fallback（`white-space: pre-wrap`）；统一游戏字体、max-width 680px、顶部渐变遮罩

3. **主动退出简化**（`976777d`）：
   - 半途退出不再生成冒险日志——日志语义是"完结故事弧的收尾"，中断游戏不满足
   - 存档保留，玩家可恢复游戏并在自然结局获取完整日志
   - `exec-flow.md` 流程图简化："确认退出 → 返回主菜单"（移除"确认日志 → 显示日志"）

4. **时机修复**（3 个 commit）：
   - `34bc011`：延迟结局展示到 bridge_text 队列排空——将结局检测移入显示循环的空队列分支
   - `857432a`：展示选择时隐藏 loading 指示器
   - `08f567c`：展示结局时隐藏 loading 指示器
   - `fc8d20f`：post-choice 第一个 segment 也遵守当前节奏模式

**依据**：commits `078c702`, `3898e0a`, `976777d`, `34bc011`, `857432a`, `08f567c`, `fc8d20f`；`src/storyloom/web/static/js/adventure-log.js`（新文件）。

### 存档浏览器

**背景**：Web UI 需要完整的存档管理能力——浏览游戏列表、查看存档点、加载/删除存档。

**决策**：两页面存档浏览器——`#saves`（游戏列表）+ `#saves/{game_id}`（存档点列表）。

1. **初始实现**（`3fba026` / `54b5354`）：
   - `#saves`：按最后游玩时间降序列出游戏文件夹，显示 label、genre、存档数、最后游玩日期
   - `#saves/{game_id}`：列出 checkpoint 存档（排除 `_init.json`），按 `saved_at` 降序；左键加载→游戏预览页；Restart 按钮加载 `_init.json` 全新开始
   - 删除：hover 触发垃圾桶图标 → 确认弹窗（Yes/No + 不可撤销警告）
   - 服务端：`GET /api/saves/games` 增加 `last_played_at` 富化与排序；新端点 `POST /api/saves/{game_id}/start/{filename}`
   - 11 条新 i18n 字符串

2. **架构违规修复**（`f1ab53b`）——修复 PR #16 审查中的三个问题：
   - **P1 #1**：`last_played_at` 富化从 `server.py`（直接访问私有 `_saves_root` + 原始 JSON I/O）移入 `SaveManager.list_games(enrich=True)` → `GameSession.list_games(enrich_last_played=True)`
   - **P1 #2**：`GameSession.load_game()` 拆分为公开方法 + 内部 `_load_from_data()`——消除冗余的双重读取+校验
   - **P2 #3**：`showContextMenu` → `showConfirmPopup`（函数是垃圾桶点击确认弹窗，不是右键菜单）

3. **卡片打磨**（4 次迭代）：
   - `81b40e5`：checkpoint 卡片显示截断的 checkpoint summary 而非 node ID；时间右对齐
   - `9d824c6`：移除游戏卡片 tier；长文本截断防碰撞
   - `8422b63`：hover 时展开截断文本
   - `3bb77dc` + `ff50850`：hover 时隐藏时间 + 限定作用域到 checkpoint 卡片

**依据**：commits `3fba026`, `54b5354`, `f1ab53b`, `81b40e5`, `9d824c6`, `8422b63`, `3bb77dc`, `ff50850`。

### UX 打磨迭代 —— 居中、字号、渐变、设计 Token

**背景**：游戏画面的阅读体验需要从"功能可用"打磨到"沉浸舒适"。一天内执行了 10+ 次快速 CSS/布局迭代。

**决策**：逐次微调，每次解决一个具体问题。关键改动：

| Commit | 改动 | 效果 |
|--------|------|------|
| `079bab0` | `.game-view` 高度 `100vh` → `calc(100vh - 4rem)` | 消除 body 级滚动条，修复三个 UX 问题 |
| `93ed665` | `text-align: center`；`_scrollToCenter()` 替代 `scrollToBottom()` | 内容居中；新段滚动到视口中央 |
| `8101850` | `padding-bottom: 50vh` | 视口可滚过最后一个元素 |
| `85d97e6` | max-width 800→960px；font-size 1.05→1.15rem；line-height 1.6→1.8；移除 pop 动效 | 更宽、更大、更舒适的阅读体验 |
| `8977524` | gap 1.8→1.2rem；顶部 `mask-image` 渐变遮罩 | 段落间距适中；顶部旧文字渐隐 |
| `5cf21be` | loading 居中；`.game-segment--active` `scale(1.06)` | 最新段微微放大 |
| `f3a8948` + `dd74299` | 新段立即放大，旧段平滑缩小 | 视觉焦点引导 |
| `b44060c` | 共创聊天宽度→960px；文字放大 | 与游戏画面一致 |
| `5fd12ae` | 提取 52 个 CSS 自定义属性 | 设计 token 体系——颜色/排版/间距/布局/圆角/过渡/阴影；统一 `--content-width: 960px`、font-size scale（`--font-xs`~`--font-4xl`）、spacing scale（`--space-xs`~`--space-3xl`） |
| `3537504` | 渐变阈值微调：story 顶部 8→10%、底部 60→72%、日志顶部 6→10% | 可读性优化 |

**依据**：commits 如上表；`src/storyloom/web/static/css/main.css` 52 个 CSS 设计 token。

### 提示词系统改进

**背景**：多项 Prompt 质量问题——LLM 倾向于在目标未达成时提前触发 checkpoint、选择与剧情分支过度耦合、Structure 模板过于复杂。

**决策**：四项独立改进：

1. **Checkpoint 门控规则**（`d086a85`）——双重覆盖（正面规则 + 负面禁止）：
   - 正面：Checkpoint 节增加 "If the goal has NOT been reached, omit `<checkpoint>` entirely. The node may take several rounds."
   - 负面：Prohibited 节增加 "`<checkpoint>` when the active node's goal has not been reached."
   - 同时应用于 Structure 模板和 Format Example 两个区域，遵循 `prompt-design.md` §1.2 双重覆盖原则

2. **Structure 模板简化**（`837a1eb`）：
   - 移除多分支 `<branch>` 块——改为纯 `<choice>` + 非分支 `<opt>` + 内联注释 "node still in progress -- no `<checkpoint>` yet"
   - Format Example 中插入轻量级 "drink" 选择——无 branch、无 set、无 checkpoint——示范"不是每个选择都需要剧情后果"
   - 统一去除所有 `<seg>` 文本末尾句号

3. **选择之间叙事间隙**（`86fc624`）：在 Structure 模板的微型分支块与主要交互选择之间插入 `...`（叙事停顿行）

4. **Choice-as-Play 引导**（`0fe3ff5`）：`ROUND_TEMPLATE` 增加 "Choices aren't just for branching -- place them freely as moments of play and interaction."——解耦选择与剧情分支，鼓励更轻量、更高频的玩家交互

**依据**：commits `d086a85`, `837a1eb`, `86fc624`, `0fe3ff5`；`docs/spec/prompt-design.md` §1.2。

### 共创管线修复

**背景**：三项独立问题——LLM 输出格式漂移导致解析失败、example_goal 叙事范围过窄、setting 字段语义不清。

**决策**：

1. **灵活块分隔符**（`930ecf4`）：
   - `CoCreateParser.split_blocks()` 的 `BLOCK_DELIMITER` 正则放宽——匹配 `===story_config===`（无空格）、`=== story config ===`（空格替代下划线）及任意混合
   - 块名归一化（空格→下划线），downstream key 不变；4 个新测试用例

2. **Setting 字段语义转变**（`6c74d37`）：
   - LLM 提示从 "era, location, key world facts" → "a story blurb that hooks the reader -- introduce the world, protagonist, and what's at stake"
   - 字段名不变（`setting` / `世界观`），只改变 Prompt 语义——LLM 写出吸引人的故事简介

3. **Example Goal 扩展**（`3b19415`）：中英文 `example_goal` 重写为多节拍弧线——相遇、调查、背叛、高潮抉择——替代原单场景设定

**依据**：commits `930ecf4`, `6c74d37`, `3b19415`；`tests/test_co_create.py` 新增 4 个测试。

### Web UI 打包 —— wheel + PyInstaller + 版本 1.0.0

**背景**：Storyloom 需要两种分发格式——面向开发者的 pip wheel、面向终端用户的独立可执行文件。此前无任何打包基础设施。

**决策**：设计先行——spec → plan → 实现的三步走自动化构建管线。

**设计文档**：
- `docs/superpowers/specs/2026-07-20-web-packaging-design.md`（138 行）——两种分发格式、发布目录布局、平台检测策略
- `docs/superpowers/plans/2026-07-20-web-packaging.md`（361 行）——详细实现计划

**构建脚本**（`scripts/build.sh`）——五步自动化：
1. 安装项目 + 构建工具（`pip install -e . build pyinstaller wheel`，`--break-system-packages` fallback）
2. 构建 pip 包（`python -m build --no-isolation`）→ `.whl` + `.tar.gz`
3. 构建独立可执行文件（`python -m PyInstaller --onefile`，`--add-data` 打包 locale/static，`--hidden-import` 覆盖 uvicorn 动态子模块）
4. 组装发布目录（binary + `locale/` + `.whl` + `.tar.gz` → `dist/storyloom-web-v{VERSION}/`）
5. 创建 zip 归档（`shutil.make_archive` → `dist/storyloom-web-v{VERSION}-{OS}.zip`）

**包配置变更**：
- `pyproject.toml`：web 依赖（fastapi, uvicorn）提升为顶层依赖；新增 `storyloom-web` 入口点；`[tool.setuptools.package-data]` 打包 static 文件
- `MANIFEST.in`：`graft src/storyloom/web/static`——确保 sdist 包含静态文件
- `src/storyloom/__init__.py`：新增 `__version__ = "1.0.0"`——从 0.1.0 跃升至 1.0.0

**PyInstaller 适配**（2 个文件的路径检测逻辑）：
- `i18n.py` `_get_locale_dir()`：`sys.frozen` → `sys.executable.parent / "locale"`；否则 → `Path(__file__).resolve().parents[3] / "locale"`；显式 `locale_dir` 优先
- `server.py` `_PROJECT_ROOT`：同模式；环境变量 `STORYLOOM_APP_DIR` 可覆盖

**Windows 特殊处理**（4 次迭代）：
| Commit | 问题 | 修复 |
|--------|------|------|
| `2ad86eb` | Windows 无 `python3` 命令 | 自动 fallback 到 `python` |
| `c90d882` | `wheel` 未安装（`build` 需要） | 添加到 pip install |
| `eeb8ecb` | PyInstaller 无法解析导入（依赖未安装） | `pip install -e .` 先于 PyInstaller |
| `e2b12d2` | `pyinstaller` 命令不在 PATH | `$PYTHON -m PyInstaller` |

**控制台可见性**（`742871b`）：最初添加了 `--noconsole` 标志隐藏 Windows 控制台——但无控制台则用户无法 Ctrl+C 关闭服务器，最终**回退**此修改。保留控制台可见。

**None stdout/stderr 处理**（`3197525` + `fef4984`）：无控制台时 `sys.stdout` 和 `sys.stderr` 为 `None` → uvicorn 日志格式化器在 `.isatty()` 上崩溃 → 重定向到 `storyloom.log` 文件（位于 executable 旁）

**浏览器自动打开**（`0c0a8a2`）：`main()` 中 daemon 线程等 1.5s 后 `webbrowser.open("http://127.0.0.1:8000")`

**API 配置延迟校验**（`3824034`）：
- `ApiClient` 不再在构造时校验——`api_key`/`base_url`/`model` 改为惰性属性（每次读 `UserConfig`）；`httpx.Client` 延迟到首次 API 调用创建；`_validate_config()` 在 `chat()`/`stream_chat()` 入口调用
- 服务器可在无 API key 时启动——只在用户尝试生成文本时才报错；运行时设置页修改配置无需重启

**依据**：commits `262ff6e`, `fd2b53f`, `d2f79d4`, `5799406`, `96bcf95`, `9598573`, `eb23725`, `ba3fc2e`, `7f98af0`, `2ad86eb`, `c90d882`, `eeb8ecb`, `e2b12d2`, `0c0a8a2`, `3197525`, `fef4984`, `742871b`, `3824034`；`scripts/build.sh`（104 行）；`docs/superpowers/specs/2026-07-20-web-packaging-design.md` + `plans/2026-07-20-web-packaging.md`。

### 图标 SVG 化与 i18n 修复

**背景**：Web UI 使用硬编码 Unicode 字符（`<-`、`^`、`✏`、`✓`）作为图标——在不同平台/字体下渲染不一致。i18n 方面，disabled 选项的 `(unavailable)` 标签缺乏有用信息。共创 Prompt 的多行 msgid 与 gettext 解析器存在兼容问题。

**决策**：

1. **Inline SVG 图标**（`ece433e` + `f067798`）：
   - 新增共享 `icons.js` 模块——`Icons.arrowLeft()`、`arrowUp()`、`pencil()`、`checkmark()`、`gear()` 五个 SVG 工厂函数
   - 替换 4 个 JS 文件中的 Unicode 字符
   - 统一风格：`const` 声明（匹配其他 JS 模块）、全部 fill-based（非 stroke）、gear 图标从 `game.js` 私有方法迁移到共享模块

2. **Disabled 选项显示条件原因**（`314d67c`）：
   - `_buildDisabledReason()` 解析引擎条件字符串 → 提取变量名 → 查找当前值 → 格式化 "需理智值 >= 30，当前：20"
   - 无变量值时 fallback 到 `"Requires {cond}"` 模板；新增 2 条 i18n 字符串

3. **缺失 `unavailable` msgid**（`d139af4`）：PR #22 改了 JS key 但未同步 `.po` 文件——补充 `"unavailable" → "不可用"` 条目

4. **共创 Prompt 中文翻译——已回退**（6 个 commit 的尝试→回退循环）：
   - `fa5ae6f`：添加共创 Prompt 中译到 `.po`
   - `d19bbfe`：构建脚本增加 `.po→.mo` 编译并更新译文
   - `e5cf481`：多行 msgid 压缩为单行（避免 gettext 换行歧义）
   - `de03441` → `6ca2220` → `61a542f`：三次全部回退
   - **最终状态**：`.po` 文件保持原样，`.mo` 编译步骤未加入构建脚本，翻译被放弃
   - **根因**：共创 Prompt 是多行长文本 msgid，gettext 的 `xgettext` 解析器对嵌入式换行敏感，单行/多行格式在 `.po`→`.mo` 编译时产生匹配不一致

**依据**：commits `ece433e`, `f067798`, `314d67c`, `d139af4`, `fa5ae6f`, `d19bbfe`, `e5cf481`, `de03441`, `6ca2220`, `61a542f`；`src/storyloom/web/static/js/icons.js`（新文件，78 行）。

### 规范与文档同步

**背景**：代码演进后规范文档滞后——常量值过时、元素数量不匹配、未实现功能残留、命名不一致。

**决策**：全量文档审计与同步（`ef04ead` + `26809d1` + `4d32fab`）：

1. **`ef04ead`**——规范批量同步：
   - `data-model.md` §A：`OUTLINE_NODE_RANGES` 更新为当前 `config.py` 值（short: 3-5→5-10, medium: 5-8→10-20, long: 8-15→20-30），加注"仅 Prompt 参考，非引擎强制"
   - `block-spec.md`：`<opt>` 数量 2-5→2-4（匹配 `ROUND1_PREFIX`）；移除未实现的 `classify_segment()` Python 代码示例
   - `prompt-design.md`：冒险日志模板重写——新增 Story Background（genre/setting/protagonist/tone/conflict/characters）+ Story Outline（每节点 `[completed]`/`[active]`/`[pending]` 状态 + 摘要）；Ending 指令收紧："Reference specific events from the summaries above -- do not fabricate"；zh-CN 示例同步更新

2. **`26809d1`**——修复 PR #20 审查中的三个 P2 命名/文档不一致：
   - `_showEndModal`/`_endModalShown` → `_showEndChoice`/`_endChoiceShown`（已不是 modal）
   - SSE handler 列表注释 + `stream_round()` docstring 增加 `save` 事件类型

3. **`4d32fab`**——`game_driver.py` 增加队列深度文档注释：
   - CLI 的 `event_queue` deque 任何时候只存 0-1 个事件（同步 drain）
   - 真正的缓冲在引擎层（daemon 线程 → `queue.Queue` → `stream_round`）
   - 确认 Web UI 正确实现了 `exec-flow.md` §4.5 全部 14 项 + §4.6 全部要求

**依据**：commits `ef04ead`, `26809d1`, `4d32fab`；`docs/spec/data-model.md` §A、`block-spec.md`、`prompt-design.md` §3.4、`exec-flow.md` §4.5-4.6。

---

## 2026-07-18（周六）

### Co-Create 大纲 goal 提示词优化 + 示例数据语言感知

**背景**：大纲各节点的 `goal` 字段偏短、不够详细，影响后续叙事生成的质量参照。根因有二：(1) Prompt 中 goal 的约束表述罗列要素（events, characters, stakes）而非传达功能定位和详细度要求；(2) `CO_CREATE_GENERATION_PROMPT` 的示例数据（变量名、分支条件、goal 占位符）硬编码中文，与语言感知设计不一致，且 goal 占位符为元指令而非具体示例，LLM 无样本可模仿。

**决策**：(1) goal 约束从 "Each node has a clear narrative goal which describes the specific events, characters, and stakes in 2-3 sentences." 改为 "Each node's goal provides a specific overview of the chapter's main content. 2-4 sentences, more is fine."——去掉要素罗列，聚焦于"章的主要内容的详细概览"，`more is fine` 给 LLM 写长的信号；(2) 示例数据从模板硬编码提取到 `_LANG_META` dict，新增 `example_variables`、`example_goal`、`example_branch_var` 三个 key，中英各一套（goal 示例 ~3 句，展示具体事件与张力）；(3) `_build_generation_prompt()` 增加 `_LANG_META.get(lang, _LANG_META[DEFAULT_LANGUAGE])` 兜底未知语言。模板中 `$example_*` 占位符均为单行文本，不引入换行——`parse_outline` 无须改动。

**依据**：`CO_CREATE_GENERATION_PROMPT`（`co_create.py`）；`_LANG_META`（`co_create.py` L406-448）；prompt-design.md §1.2 示例先行原则。

### 存档 bridge_text 移除 + checkpoint 存档 guard

**背景**：审计存档触发机制发现两个问题。其一，`to_save_dict()` 在 Phase 3（流式解析中）被调用，此时 `_last_bridge_text` 仍是上一轮 Phase 5 写入的值——存入的 bridge_text 比当前 checkpoint 滞后两轮。更深层的问题是：checkpoint 存档代表故事节点完成边界，不是 bridge 延续；加载存档后应"从 checkpoint 节点全新开始"，而非携带上一轮的 bridge_text 作为 "Continue from:" 注入首轮 Prompt。其二，`_handle_checkpoint` 中节点推进失败（target 为 None）时仍无条件执行 `_accumulate_checkpoint`，可能产生未推进状态却已存档的"僵尸存档"。

**决策**：(1) 从存档格式（`to_save_dict` / `from_save_dict` / `_build_init_dict`）中移除 `bridge_text` 字段——该字段属于游戏内跨轮循环，不属于持久化边界；(2) `build_round1()` 删除死参数 `checkpoint_history`（从未在函数体中引用）和 `bridge_text`，内部固定填入 `"(Story begins)"` 占位符；(3) `start_game()` 删除 bridge_section 构建死代码；(4) `_handle_checkpoint` 新增 `node_advanced` guard——仅当 checkpoint 成功推进节点后才触发 `_accumulate_checkpoint`；(5) `SAMPLE_XML` 测试 fixture 修复节点 ID（`ch2_meeting`→`ch2_confrontation`，`ch3_lead`→`ch3_ally`），新增 5 个 checkpoint 测试覆盖推进、存档、ending、未知节点拒绝等路径。

**依据**：`docs/spec/data-model.md` §3.1, §3.2, §3.5；`docs/spec/prompt-design.md` §4.3。

### ApiClient 从 urllib 迁移到 httpx——连接池解决代理 400

**背景**：WSL2 环境下 API 请求经 Windows 侧代理 `127.0.0.1:19828`。`urllib` 每次 `urlopen()` 新建 TCP 连接 + CONNECT 隧道，co-create 多轮 Q&A 和 daemon 线程流式连接累积后，代理隧道达到上限，拒绝新请求（HTTP 400）。错误信息不可读（代理返回 HTML，JSON 解析失败后 fallback 为 generic "Bad Request"），重试无效（完全相同的请求过同一拥塞代理）。另一方面，`deepseek-v4-pro` reasoning model 会在输出中产生 `\udcef` 等孤立代理字符（lone surrogates），`json.dumps()` 编码时抛出 `UnicodeEncodeError`，该异常不是 `ApiError` 子类，逃逸到 game_driver 层被当成致命错误而非触发重试。

**决策**：(1) 用 `httpx.Client` 替代 `urllib`——客户端实例持有连接池，复用 TCP 连接和 CONNECT 隧道，代理侧连接数稳定在 2-3 条，不再触及上限；(2) `_handle_http_error` 改为接收 `httpx.Response`，JSON 解析失败时展示原始响应体片段（最多 500 字符）；(3) `_extract_content` 处理 reasoning model 的 `content: null`；(4) `chat()` / `stream_chat_iter()` 增加可选 `max_tokens` 参数（默认 None，向后兼容）；(5) 新增 `except UnicodeError` 捕获，将 JSON 序列化错误转为 `ApiError` 进入正常 retry 流程。公共 API（`chat()`、`stream_chat_iter()`、`stream_chat()`、`ApiResult`、`ApiError`）签名不变，所有调用方零改动。

**依赖变更**：`pyproject.toml` 新增 `httpx>=0.28.0`——项目首个运行时依赖。

**依据**：`docs/spec/exec-flow.md` §4.3, §6.1；`data-model.md` §A.6。

### 大纲数据模型统一——status 与 summary 归于节点

### 大纲数据模型统一——status 与 summary 归于节点

**背景**：四个独立结构维护同一批大纲节点的不同侧面——`_outline_nodes`（纯结构）、`_completed_nodes`（状态列表）、`_checkpoint_history`（summary 列表，含 title/goal 副本）、`outline_text`（格式化快照，仅在构造时设置，永不更新）。这导致：(1) `outline_text` 在 checkpoint 推进后过时，状态标记不再准确；(2) `title`/`goal` 在 `_outline_nodes` 和 `_checkpoint_history` 中重复存储；(3) checkpoint summary 只在压缩消息和冒险日志中可见，不在每轮的 outline 段落中；(4) 读档后 ContextManager 的 `_compressed_summaries` 为空，LLM 看不到历史摘要。

**决策**：单一真相源——`_outline_nodes` 每个节点直接携带 `status`（pending/active/completed）和 `summary`，`outline_text` 改为 `@property` 实时派生。

- `_outline_nodes`: `[{id, title, goal, status, summary, routes}]` — 所有信息在节点上
- `outline_text` property: 从 `_outline_nodes` 实时生成，完成节点下追加 `↳ {summary}`
- `checkpoint_history` property: 从完成节点派生（向后兼容）
- `completed_nodes` property: 从 status 字段派生
- `_handle_checkpoint`: 直接修改节点的 status/summary，不再维护独立列表
- `_accumulate_checkpoint`: 直接写 `node["summary"] = cp_summary`
- 存档格式: outline 节点带 `status` + `summary`，删除 `progress.checkpoint_history`
- `from_save_dict`: 恢复 outline 节点（含 status/summary），兼容旧存档（`setdefault`）
- `start_round1`: `bridge_text` 通过参数传入 `build_round1()`，删除手动拼接
- `build_round1`: 去掉硬编码 `(This is the start of the whole story.)`，bridge_text 通过模板 `{bridge_text}` 槽位自然融入
- `build_adventure_log_prompt`: 删除 `checkpoint_history` 参数，summary 已在 `outline_text` 的 `↳` 行中

**依据**：`5782725`、`94657dd`、`341d4dd`；`docs/spec/data-model.md` §1-3、`exec-flow.md` §1.1, 5.2, 5.4、`prompt-design.md` §5.1。

### 冗余 checkpoint_summaries 清理

**背景**：`_checkpoint_summaries: list[str]` 与 `_checkpoint_history: list[dict]` 并存，前者是纯文本列表，后者是结构化记录（含 node/title/summary）。`checkpoint_history` 是 `checkpoint_summaries` 的严格超集——每个 summary 都带着 node/title 存在 history 中。代码中 `_checkpoint_summaries` 唯一的消费者是冒险日志——而冒险日志已经改用 `checkpoint_history`。

**决策**：删除 `_checkpoint_summaries`（初始化、写入、读取、追加），`checkpoint_history` 成为唯一的 checkpoint 数据承载结构。同时将 `goal` 字段加入 `checkpoint_history` 条目（在查 `title` 的同一个 outline 遍历中零成本获取）。

**依据**：`5782725`。

### 冒险日志 Prompt 重构

**背景**：`build_adventure_log_prompt` 接收了 `story_config` 但只用了 `label` 和 `language`——genre、setting、protagonist、tone、conflict、characters 全部丢弃。每章只有 title + 一句话 summary，LLM 在无知背景下被迫杜撰情节。

**决策**：注入完整 story_config 字段（Story Background 段）+ 完整 outline_text（Story Outline 段）。冒险日志从"给一句话扩写"变为"据背景和叙事摘要撰写"。同时删除未使用的 `checkpoint_summaries` 参数，改为传入 `outline_text`。

**依据**：`a8144ee`。

### Goal 和 checkpoint summary 示例扩充

**背景**：用户反馈三个痛点——存档继续时上下文冲突、LLM 生成不稳定、冒险日志杜撰。根因是叙事记忆链路太短：outline `goal` 只有一句话，checkpoint `summary` 只有一句话，且 `summary` 读档时未注入上下文。

**决策**（轻量先行）：不改架构，只改 Prompt 示例。
- `co_create.py`: `Each node has a clear narrative goal` → 加 `which describes the specific events, characters, and stakes in 2-3 sentences`
- `prompt_builder.py`: checkpoint summary 格式示例从 `"A stranger made contact at the inn."` 扩为 `"A mysterious stranger offered Kael a job at the inn. He accepted and set out for the old pass."`

LLM 通过模仿示例自然产出更丰富的内容，无需额外约束。

**依据**：`95acd26`；`prompt-design.md` §1.2 原则 #1（示例先行）。

**背景**：`ROUND1_TEMPLATE` 是一个整体文本，从角色定义一路写到 bridge_text。`build_round1()` 和 `build_round_n()` 是两个独立的构建路径——前者用模板填充，后者手拼字符串。两者产生的结构不一致（Round 1 叫 "Active Node"，Round N 叫 "Current node"；Round 1 有 `/100` 范围后缀，Round N 没有；Round 1 含行数约束，Round N 不含）。每轮都需要的状态上下文和量化约束分散在两条路径里，迭代时容易顾此失彼。

**决策**：将 Round 1 user 消息拆分为前缀块和回合块两部分：

- **首轮前缀**（`ROUND1_PREFIX`）：角色定义、XML 格式规范、Kael 示例、核心规则、故事背景。只发一次，永久锚定。
- **回合提示词**（`ROUND_TEMPLATE`）：大纲树、当前节点、状态快照、错误反馈、行数约束、bridge_text。每轮都发，首轮和后继轮共享。

Round 1 user = 前缀 + 回合块（bridge_text 为空，无错误反馈）+ 首轮尾句。
Round N user = 回合块（按实际填充）。

`build_round_n` 签名简化：去掉 `completed_nodes`（大纲状态标记已体现进度）和 `compressed_summaries`（ContextManager 的压缩消息对独立处理），新增 `outline_text` 和 `variables`（统一用 `_format_current_state` 带类型后缀）。状态变量在首轮和后继轮均采用 `变量名：值 / 100` 格式，消除此前 Round 1 有、Round N 无的差异。

**依据**：commit `68d4028`（spec）+ `90ba48d`（代码）；`docs/spec/prompt-design.md` §4.2–§4.4；268 测试全绿。

---

### 从持久化层移除 round_count 和 round

**背景**：读档后 ContextManager 完全重置（`_round_count = 0`），存档中记录的 `round_count` 与读档后的实际轮数完全断开——存档说第 15 轮，读档后下一轮被当作 Round 1。轮数仅在 ContextManager 内部用于滑动窗口压缩触发（`_maybe_compress()` 中 `total_rounds >= FIRST_COMPRESSION_AT`），不应该暴露给持久化层或 UI。

审计确认：
- `metadata.round_count` / `progress.round_count`：`from_save_dict()` 不读取
- `checkpoint_history[N].round`：零消费者（adventure log 用 `enumerate(cp, 1)` 自己编号）
- `list_saves()` 返回的 `round`：唯一消费者是 dev_cli 的保存列表展示
- streaming event 的 `done.round` / `ending.round`：UI 不应关注轮数实现细节

**决策**：从持久化层（save dict + checkpoint_history + list_saves）和流式事件（done/ending）中完全移除 `round_count` 和 `round`。保留 ContextManager 内部 `_round_count`（压缩逻辑需要）。

变更范围：
- `game_loop.py`：`to_save_dict()` 删 `round_count`；`_accumulate_checkpoint()` 删 `round`；3 个 yield event 删 `round`
- `session.py`：`_build_init_dict()` 删 `round_count`
- `save_manager.py`：`list_saves()` 删 `round` 字段
- `game_driver.py`：保存列表删除 round 展示
- `data-model.md`、`prompt-design.md`：同步删除 `round_count` 引用
- 现有存档 JSON 同步清理（`saves/` 在 `.gitignore` 中）

**依据**：commit `f8de931`（持久化层 + 文档）+ `dc98498`（dev_cli + 测试）；266 测试全绿。

---

## 2026-07-18（周六）

### 修复 Windows 文件名非法字符：存档目录 + Co-Create Prompt 格式歧义

**背景**：两起 Windows 端崩溃均与文件名/格式解析有关：

1. **存档目录创建失败**：`create_game()` 用 ISO 8601 `2026-07-17T17:10:23Z` 作为目录名一部分，其中 `:` 在 Windows/NTFS 为非法字符 → `OSError: [WinError 123]`。
2. **Co-Create 生成 parse 失败且重试无效**：`CO_CREATE_GENERATION_PROMPT` 中包含 `## Section 1: story_config` / `## Section 2: variables` / `## Section 3: outline` 标题行，并强调 "Use EXACTLY the format shown"。LLM 忠实输出这些标题行，但 parser 的 `split_blocks()` 只识别 `=== block ===` 分隔符，导致 `## Section 3: outline` 落入 variables block 文本 → `parse_variables()` 严格匹配失败。重试三次结果相同：`retry_generate()` 每次追加的 correction message 一字不差，LLM 在矛盾指令下（prompt 说标题是对的、error 说标题是错的）不会修正。

**决策**：

1. **存档目录名**：`game_id`（目录名）改用已有的 `_compact_ts()` 格式（`20260717T171023Z`，无冒号），与 checkpoint 文件名保持一致。`created_at` 返回值保持 ISO 8601 可读格式（`2026-07-17T17:10:23Z`）仅供 metadata JSON 存储。两类时间戳职责分离：目录名 = 机器友好，metadata = 人类可读。

2. **Co-Create Prompt 重构**：删除所有 `## Section N: name` 标题行——这是歧义根源。改为三段式结构：
   - **`# Rules`**：集中放置 variables 和 outline 的规则约束（内容不变）
   - **`# Output Format`**：新增格式指令区，明确 "exactly three blocks separated by `===` markers" + "no markdown headings, no commentary"
   - **模板区**：只保留 `=== block ===` 分隔符和内容占位符，与 parser 的 `BLOCK_DELIMITER` 精确对应
   
   设计参照 `prompt_builder.py` 中 `ROUND1_TEMPLATE` 的成熟模式：规则与模板分区独立。

3. **拒绝修改 parser**：用户明确要求只修提示词，不修改解析器。理由：parser 行为正确——它只认 `=== block ===` 是设计意图；问题是 prompt 给 LLM 发出了矛盾信号。

**依据**：commit `119332a`（存档目录）+ 本 commit（prompt 修复）；`co_create.py:455-538`（`CO_CREATE_GENERATION_PROMPT`）；`save_manager.py:234-239`（`create_game`）；`docs/spec/data-model.md:84-90`（目录结构规范）。

---

## 2026-07-17（周五）

### 选项条件评估收归引擎

**背景**：`<opt if="...">` 的条件评估此前由 UI 层负责——`options` 事件携带原始 `conditions` 字符串，UI 需自行实现与引擎一致的评估逻辑。这与 `<set>`、`<route>` 的条件评估（均由 `GameState.evaluate_condition()` 统一处理）不一致，且违反"本地数据为唯一真相源"原则。

**决策**：
1. 引擎在 yield `options` 事件前评估每个选项的 `if` 条件，结果写入 `enabled` 列表
2. 全部不可选时兜底为全部可选（防止游戏卡死）
3. CLI 适配：读 `enabled` 标注 `(locked)`，disabled 项本地拦截
4. spec `exec-flow.md` §4.6 同步更新

**依据**：memory `option-condition-engine-evaluation.md`；spec `exec-flow.md` §4.6；`game_loop.py` L718-738；`game_driver.py` L437-474。

---

### UserConfig 模块：集中用户配置管理 + 移除 .env 耦合

**背景**：项目缺少统一的用户配置层。语言硬编码在 `dev_main()` 中；API 凭证通过 `api_client._find_project_root()` 向上搜索 `.git` 目录定位 `.env` 文件——该模式在打包后不可用。存档路径、语言偏好等用户选择无持久化机制。

**决策**：

1. **新增 `UserConfig` 模块**：单类管理 `config.json`（JSON 格式），暴露 `language`/`api_key`/`api_base_url`/`api_model` 四个属性。支持 headless 模式（`app_dir=None`，纯内存）和 disk 模式（读写 `<app_dir>/config.json`）。原子写入（temp + `os.replace`），缺失字段自动回填，损坏 JSON 不删除文件。
2. **移除 `.env` 依赖**：`ApiClient` 构造器接受 `UserConfig`，不再内部搜索 `.env` 文件。优先级：`os.environ` > `UserConfig` > 默认值。删除 `_find_project_root()`、`_load_dotenv()`、`_load_env()`。
3. **i18n 运行时切换**：新增 `switch_language(language)`，提取 `_load_translator()` 供 `init_i18n` 和 `switch_language` 共用。`init_i18n` 新增 `locale_dir` 参数供打包场景传入自定义路径（默认 `__file__`-relative fallback 保持兼容）。
4. **依赖注入**：`GameSession.__init__` 的 `api_client` 变为可选参数，入口点负责 `UserConfig → ApiClient → GameSession` 全链路 wiring。
5. **应用根目录辅助函数**：`_get_app_dir()` 封装 `sys.frozen` 判断——打包后指向 exe 所在目录，开发时指向项目根。`config.json`、`locale/` 均基于 `app_dir` 解析。

**改动**：10 文件，+474/-267 行。新增 `user_config.py`、`config.example.json`、`test_user_config.py`、`test_i18n.py`。删除 `.env.example`。276 tests passed，零回归。

**依据**：commit `86c9345`..`f5d0917`（连续 9 commits）；spec `docs/superpowers/specs/2026-07-17-user-config-design.md`；plan `docs/superpowers/plans/2026-07-17-user-config-implementation.md`。

---

### 存档系统重构：按游戏分目录 + 追加式 checkpoint 存档

**背景**：当前存档系统每个游戏只有一个 `saves/{label}.json` 文件，每次 checkpoint 覆盖写入。玩家无法回到历史关键节点——存档仅适用于"继续最新进度"，不支持回溯或时间线浏览。需求：每个 checkpoint 独立存档、追加不覆盖、UI 两级选择（先选游戏再选存档）、修改最小化。

**决策**：

1. **Per-game 目录结构**：`saves/{label}_{created_at}/` 下存放所有存档。`_init.json`（`round_count=0`）为共创结束时创建的"元存档"——新游戏入口和 checkpoint 存档共享完全相同的格式（`to_save_dict()` 输出），`from_save_dict()` 统一加载。
2. **追加模式**：checkpoint 存档文件名为 `{cp_title}_{timestamp}.json`，时间戳保证不重名不覆盖。`SaveManager.save(cp_title=None)` 写 `_init.json`，`cp_title=str` 写 checkpoint 存档。
3. **`start_game()` 和 `load_game()` 收敛为单一路径**：`start_game(result)` 直接从 `CoCreationResult` 构建 `_init.json` 字典（零 GameLoop 依赖），写入后调用 `load_game()` 加载。新游戏 / 继续 / 回溯三条路径完全一致。
4. **修复 Round 1 prompt 状态值不一致**：`build_round1()` 原从 `story_config.variables[].initial` 读取变量值——读档时 LLM 看到初始值而非当前实际值。改为必传 `state_vars` 参数，始终显示 `game_state.state_vars` 实际值。删除旧 `_format_state_vars()` 方法。
5. **SaveManager API 重构**：实例方法操作单个游戏目录（`save`/`load`/`delete`/`list_saves`），跨游戏操作改为静态方法（`create_game`/`list_games`/`delete_game`/`list_saves_for_game`）。
6. **GameSession API 适配**：`start_game()` 返回 `(GameLoop, game_id)`；`load_game(game_id, filename)` 两级定位；新增 `list_games()`、`delete_game(game_id)`、`delete_save(game_id, filename)`。去除持久 SaveManager 实例。

**改动**：9 文件，+623/-252 行。核心引擎文件零改动：`co_create.py`、`context_manager.py`、`streaming_parser.py`、`api_client.py`、`config.py`、`i18n.py`。251 tests passed。

**依据**：commit `66fa07f`；plan `hidden-jumping-ripple.md`；`docs/spec/data-model.md §3.1-3.4`；`prompt_builder.py:220-222`（旧 `_format_state_vars` 逻辑）。

---

### 删除 `list` 变量类型

**背景**：存档中发现 LLM 为"事件标记"变量使用了 `list` 类型。审查发现虽然 `list` 类型在代码库中完整实现（初始化、`<set>` 操作 `+`/`-`、静默去重），但条件求值不支持 `包含`/`不含` 操作符——LLM 在路线条件中自然使用这些操作符时，引擎正则无法匹配，静默返回 `False`，导致路由永远走兜底逻辑。让 LLM 操作 list 类型带来的复杂度远大于其价值。

**决策**：彻底删除 `list` 变量类型，只保留 `number` 和 `string`。`VARIABLE_LABEL_CAP` 语义从 "string/list" 收紧为 "string"。

**改动**：删除 ~136 行（9 文件）——引擎核心 3 文件、规范文档 3 文件、测试 3 文件。新增 `test_rejects_unknown_variable_type`。

---

## 2026-07-16（周四）

### CLI 模式重构：游玩默认入口 + 两阶段录制

**背景**：CLI 默认进入观察者+instant 模式，对普通玩家不友好。观察者录制逻辑存在 prompt 双重写入（`write_prompt_at_send` 和 `record_round` 都写 `prompts.txt`），缺乏清晰的提交/接收两阶段契约。

**决策**：
1. 默认入口改为游玩模式（手动 pacing，Tab 切换），零参数。
2. 观察者通过 `--observer` 进入，默认手动 pacing（与游玩一致），`--instant` 禁用 pacing 和切换。
3. 录制改为两阶段：Phase 1 提交 prompt 时写 `prompts.txt` + 清空 `responses.txt`；Phase 2 完整接收后 `record_round` 只写 `responses.txt` + `checks.txt`。
4. 手动 argv 解析替换为 argparse。

**依据**：`src/storyloom/dev_cli/game_driver.py`、`src/storyloom/dev_cli/observer.py`、`src/storyloom/dev_cli/__init__.py`。

### 异常处理统一：移除自动重试，三阶段行为对齐

**背景**：引擎三个阶段的异常处理各自独立设计，行为不一致——共创阶段有自动重试（`MAX_RETRIES`），叙事阶段 yield error 事件 + 手动重试，冒险日志阶段无重试机制。用户期望所有严重异常由 UI 决策，引擎不做自动恢复。

**决策**：
1. 删除 `MAX_RETRIES` 全局常量——仅共创阶段使用，语义不统一。
2. 共创阶段：`send()` 和 `generate()` 移除自动重试循环，失败时抛 `CoCreateError(phase, message)`，保存 `_retry_state`；新增 `retry_send()` 和 `retry_generate()` 公开方法，与叙事阶段 `retry()` / `retry_adventure_log()` 模式一致。
3. 冒险日志阶段：`run_adventure_log()` 保存 prompt 到 `_adv_retry_prompt`；新增 `retry_adventure_log()` 方法。
4. UI 侧（`game_driver.py`）：三阶段均展示错误并询问重试。

**依据**：`src/storyloom/core/co_create.py`、`src/storyloom/core/game_loop.py`、`docs/spec/data-model.md` §B-5。

### Spec-vs-Code 审计 + 文档同步 —— 9 项修复

**背景**：距离上次审计（07-13）约三天。全面对照 4 份 spec + 全部核心源码 + 接口文档 + CLI 文档/代码，排查规范落实与文档一致性。

**决策**：

| # | 级别 | 文件 | 问题 | 处理 |
|---|------|------|------|------|
| 1 | P1 | `docs/api/co-create.md` | `send()` 返回值描述错误（dict vs str） | 重写全文（f7e24e1） |
| 2 | P1 | `docs/api/co-create.md` | 列出了引擎不做的关键词检测 | 同 1 |
| 3 | P1 | `docs/api/co-create.md` | 列出了不存在的 `generating` 阶段 | 同 1 |
| 4 | P1 | `docs/spec/exec-flow.md` | 超时处理流程与代码不一致（复杂截断 vs 严重错误+重试） | 更新规范对齐代码（44867cd） |
| 5 | P2 | `src/storyloom/core/save_manager.py` | `load()` 校验失败未删除损坏文件 | 新增 `_remove_corrupt()`（44867cd） |
| 6 | P1 | `docs/cli.md` | 全文描述已删除的旧 CLI（main.py, cli_utils.py, --quick 等） | 删除文件 + 清理索引（9de9aab） |
| 7 | P2 | `src/storyloom/dev_cli/game_driver.py` | auto 延迟 docstring 0.5s ≠ 代码 1.0s | 提取 `_AUTO_DELAY_SEC`，文档引用常量名（9de9aab, d2261fb） |
| 8 | P2 | `src/storyloom/dev_cli/game_driver.py` | `_drain_non_options` 未使用的 `mode` 参数 | 删除（9de9aab） |
| 9 | P2 | `src/storyloom/dev_cli/__init__.py` | docstring 只列 2 种用法，实际 7 种 | 补全（9de9aab） |

**误报**：`CoCreateParser.parse_story_config` 中 `characters` 空值校验——已有 `not result[f].strip()` 检查。

**依据**：commit 44867cd, f7e24e1, 9de9aab, d2261fb。227 测试全绿。

---

## 2026-07-13（周日）

### Spec-vs-Code 审计与精简 —— 16 项修复 + 4 项重叠消除

**背景**：距离上次审计（2026-07-11）约两天，项目继续演进（UiInterface 删除、Web 文件夹初始化、co_create prompt 清理）。重新全面对照 4 份 spec 文档与全部核心源码，发现 16 项不一致（8 P1 + 8 P2），以及 4 处文档间重叠。

**决策**：

**16 项修复**：

| # | 级别 | 文件 | 问题 | 处理 |
|---|------|------|------|------|
| 1 | P1 | CLAUDE.md | "StreamingXmlParser deleted" 断言错误（已于 07-11 恢复） | 改为 "restored" + 准确描述 |
| 2 | P1 | CLAUDE.md | `_launch_prefetch()` 方法名过时 | → `_launch_api()` |
| 3 | P2 | CLAUDE.md | 测试数 228 → 236 | 更新 |
| 4 | P1 | CLAUDE.local.md | 引用已删除的 `ui_interface.py` | 移除 |
| 5 | P1 | exec-flow.md | Phase 5 描述 SET/checkpoint 过时（应在 Phase 3） | 更新 |
| 6 | P2 | exec-flow.md | STORY_END 事件时机（Phase 5→Phase 3） | 从 Phase 5 移除 |
| 7 | P1 | exec-flow.md | `_launch_prefetch()` → `_launch_api()` | 更新 + 补充"所有轮次统一使用" |
| 8 | P1 | exec-flow.md | `prompt_builder.assemble()` 方法不存在 | → 实际调用链 |
| 9 | P1 | prompt-design.md | Round N 标签中文→英文（与代码对齐） | 更新示例 |
| 10 | P1 | prompt-design.md + exec-flow.md | 压缩消息/格式错误纠正中文→英文 | 同步两文档 |
| 11 | P2 | block-spec.md | "选项字母序号"→"选项数字键序号" | 修正 |
| 12 | P2 | exec-flow.md | `api_client.call()` → `api_client.chat()` | 修正 |
| 13 | P2 | data-model.md | 缺失 `SUPPORTED_LANGUAGES`、`DEFAULT_LANGUAGE` | 追加到 §A.2 |
| 14 | P2 | prompt-design.md | outline 状态图例行（代码中无） | 删除 |
| 15 | P2 | exec-flow.md | 引用废弃 `AUTO_ADVANCE_DELAY_MS` + M 键约束 | 删除，UI 自行管理 |
| — | P1 | exec-flow.md | `STORYLOOM_API_KEY` → `DEEPSEEK_API_KEY` | ~~跳过~~ → 2026-07-16 统一为 `LLM_API_KEY`（去品牌化） |

**4 项文档精简**：exec-flow.md 删除与 prompt-design.md 重叠的消息数组结构、Round N 内容表、压缩概念描述，净减 ~32 行。各文档职责更清晰：
- `exec-flow.md` — 执行管线（何时调用、如何流转）
- `prompt-design.md` — Prompt 内容结构
- `block-spec.md` — XML 元素语法与校验
- `data-model.md` — 数据结构与常量

**依据**：
- 227 tests pass
- 上次审计：[[2026-07-11-bridge-processing-audit]]

---

## 2026-07-11（周六）

### CoCreateFlow API 重构 —— Q&A 与生成分离，i18n 清理

**背景**：三个语言相关问题触发——
1. story label 几乎固定为英文（存档显示名与用户语言不匹配）
2. 共创阶段"是否开始"问句概率固定为英文
3. `co_create.py:437` 硬编码中文 `（或输入你自己的答案）`，未与配置语言联动

根因分析发现更深层问题：`_START_KEYWORDS` / `_QUIT_KEYWORDS` 在引擎侧硬编码解析用户意图，UI 与引擎职责混淆。

**决策**：

1. **i18n 清理**：`.po` 从 48 条精简至 3 条活跃条目，删除 45 条无用翻译，修正 msgid 换行符偏差导致翻译不生效的 bug。编写 `scripts/compile_mo.py`（stdlib 版 `.mo` 编译器）。

2. **语言感知 Prompt**：`CO_CREATE_SYSTEM_PROMPT` 转为 `string.Template`，`_LANG_META` 字典管理给 LLM 的英文指令，`_()` + `.po` 管理 LLM 输出给用户的文本模板（`$own_answer_hint`）。

3. **API 重构**：
   - `send()` → 返回 `str`（LLM 回复），纯转发，无关键词检测、无轮次上限。API 失败 3 次重试后 raise `RuntimeError`。
   - 新增 `generate()` 公共方法：注入格式规范 Prompt → API 调用 → 解析 + 校验 + 重试 → 返回 `CoCreationResult`。
   - 删除 `_START_KEYWORDS` / `_QUIT_KEYWORDS` / `_qa_round`。
   - Q&A 与生成 Prompt 拆分：`CO_CREATE_SYSTEM_PROMPT`（Q&A only）+ `CO_CREATE_GENERATION_PROMPT`（格式规范）。

4. **UI 层**：dev_cli 用 `/go` 触发 `generate()`，`/quit` 触发 `abort()`，其余输入全部直接转发 LLM。启动时显示命令提示。

5. **Prompt 语气优化**：维度从"必须聚焦"改为"作参考指南"；删除"禁止询问是否开始"等机械指令；主角维度补充 gender。

**净效果**：4 文件变更，+231/-360 行（净 -129）。227 tests pass。引擎与 UI 职责边界清晰化。

**依据**：
- commits: `9c60124`, `20426ab`, `c35769e`, `a8e04f1`
- [[co-create-api-refactor-2026-07-11]]
- [[co-create-i18n-hardcoded-assumptions]]

### Spec-vs-Code 审计 —— 6 项修复

**背景**：在 `stream_round()` 统一重构后，对全部 4 份 spec 文档与核心源代码进行逐条对照审计，确认代码是否忠实落实规范流程与设计。本次是重构后首次全面审计。

**发现与修复**：

| # | 级别 | 问题 | 处理 |
|---|------|------|------|
| 1 | P1 | `to_save_dict` 的 `round_count` 差一：存档在 Phase 3 触发但 `add_round` 在 Phase 5 递增 | `to_save_dict` 使用 `round_count + 1` |
| 2 | P1 | `from_save_dict` 重建 `outline_text` 丢失分支树（`├→`/`└→`） | 恢复分支连接行，兼容新旧保存格式 |
| 3 | P1 | `_handle_checkpoint` 设置的格式错误被 Phase 5 无条件覆盖 | Phase 5 合并解析器错误 + checkpoint 校验错误 |
| 4 | P2 | 冒险日志 `join()` 阻塞 generator，与普通轮间衔接的异步模式不对称 | 移除 `join()`，新增 `get_adventure_log()` 公共方法 |
| 5 | P2 | `_parse_outline_goals` 提取 `{title}：{goal}` 而非仅 goal | 规范 `prompt-design.md` §4.3 更新为含标题前缀 |
| 6 | P2 | `_accumulate_checkpoint` 残留 `cp_node == "end"` dead code | 删除旧设计分支 |
| 7 | P2 | `_handle_set_event` + `apply_set` 双重条件求值 | `apply_set` 区分"跳过"（`reason="skipped:..."`），删除 `_handle_set_event` 重复预检 |
| 8 | P2 | Q&A 15 轮上限与规范"不做轮数上限"矛盾 | 撤回——15 轮为安全熔断，非规范违规 |

**净效果**：引擎核心 -12 行（含 5 行 dead code），`GameLoop` 新增 1 个公共方法（`get_adventure_log`），`prompt-design.md` §4.3 更新 2 处，293 测试全绿。

**依据**：
- 4 份权威 spec：`exec-flow.md`、`block-spec.md`、`prompt-design.md`、`data-model.md`
- `stream_round()` 重构：commit `04845ce`

### 叙事循环统一重构 —— stream_round() 单入口

**背景**：07-11 前序审计（[[2026-07-11-bridge-processing-audit]]）和 streaming parser 集成后，代码与 spec 仍存在结构性偏离：

| 偏离 | 根因 |
|------|------|
| Round 1 不触发 pre-fetch | `start_round1_stream` 末尾无后台 API 调用 |
| 条件 set 跨轮延迟 | `continue_round_stream` 将条件 set 推迟到下一轮执行 |
| pre-fetch/live 双路径 | `_launch_prefetch` 同时做状态清算和 API 启动，live 路径双重调用 `_apply_deferred_step` |
| bridge_text 过期 | live 路径 `_launch_prefetch` 在 `_finalize_parsed_round` 之前调用，bridge_text 未更新 |

根因：代码未按照 `exec-flow.md` §4.1 的 6 阶段线性流程组织。每轮流程应是固定的、不可分割的。

**决策**：全面重构 `game_loop.py`——用 `stream_round()` 统一入口替代旧的双路径架构。

**架构**：
```
gl.start_game()          # 仅 Round 1：构建 Prompt + 启动后台 API
gen = gl.stream_round()  # 每轮统一入口
for event in gen:        # Phase 1-4: 流式解析
    if event["type"] == "options":
        gen.send(key)     # </choice> 暂停 → UI 输入 → 恢复
# Phase 5: </story> → add_round → build next prompt → launch API
```

**关键设计决策**：

1. **所有 API 调用走 daemon 线程 + queue.Queue**——取消 pre-fetch/live 分叉。每轮 Phase 5 启动后台 API，下一轮 `stream_round()` 消费 queue。Round 1 不例外。

2. **SET 解析时立即求值**——在 `stream_round()` 的 Phase 3 中，收到 `EventType.SET` 即构建 `SetOperation` + 条件求值 + `apply_set`。不再有"条件 set 延迟到下一轮"的概念。删除 `_apply_deferred_step`。

3. **CHECKPOINT 解析时立即处理**——在 `CHECKPOINT_END`（或自闭合 `<checkpoint/>`）时评估 routes、推进节点、accumulate checkpoint、触发 auto-save。删除 `_finalize_parsed_round` 中的 checkpoint 处理。

4. **Choice 暂停 via gen.send(key)**——`</choice>` 时 `yield options`，generator 暂停等 UI 调用 `gen.send(key)`。恢复后 `current_branch` 和 `choice_dict` 更新，后续 set 条件求值使用正确的 choice_dict。

5. **Phase 5 极简化**——`</story>` 后只做：`add_round` → `build_round_n` → `_launch_api`。数据处理（set/route/checkpoint）已在 Phase 3 完成。

6. **每轮数据独立**——`current_branch = "main"`、`choice_dict = {}` 每轮初始化，与 block-spec.md §3 "轮次结束时清空"一致。

**删除的旧代码**（-777 行）：
`start_round1_stream`、`continue_round_stream`、`start_round1`、`continue_round`、`_launch_prefetch`、`_apply_deferred_step`、`_finalize_parsed_round`、`_take_prefetch`、`_emit_options`、`_stream_parse_chunk`、`_prefetch_lock`、`_prefetch_data`、`_round1_started`

**新增代码**（+541 行）：
`stream_round()`、`start_game()`、`_launch_api()`、`_handle_set_event()`、`_handle_checkpoint()`

**StreamingXmlParser 变化**：
- `ParseEvent.choice_data` — `</choice>` 时携带累积的选项数据（id、branches、labels、conditions）
- `routes` 属性 — 暴露累积的 route 目标列表，供 checkpoint 处理时读取

**修复 A（结局判定）**：`_handle_checkpoint` 原以 LLM 输出是否包含 `<route>` 子元素判定结局。自闭合 checkpoint（中间单路径节点）无 `<route>` → 错误触发 `ending_flag`。修复：查大纲定义中该节点的 `routes` 是否为空。大纲中仅最终节点 `routes: []`。

**修复 B（set 条件求值）**：`_handle_set_event` 原依赖 `apply_set` 返回值区分"跳过"和"应用"。但两者返回相同的 `SetResult(accepted=True, reason=None)`，导致条件满足的 set 变更事件被抑制。修复：调用 `apply_set` 前先求值条件，不满足则直接跳过。

**净效果**：-236 行，293 测试全绿。`dev_cli/ui.py` 待后续适配新 API。

**依据**：
- `exec-flow.md` §4.1 — 6 阶段每轮统一
- `block-spec.md` §3 — 每轮数据独立，轮结束时清空
- `block-spec.md` §5 — set 在 bridge 前立即执行
- `data-model.md` §2 — routes 为空 → 结局节点（指大纲定义）
- commit `04845ce` — `refactor(engine): unify narrative loop into single stream_round() flow`
- commit `5488d79` — `fix(engine): use outline routes for ending detection, evaluate set conditions before apply`

### Spec-vs-Code 审计 —— 4 项快速修复

**背景**：对 4 份权威 spec 文档与全部核心源代码进行逐条对照审计（前序重构前）。

**修复**：

| # | 等级 | 问题 | 修复 |
|---|------|------|------|
| 3 | P1 | `apply_set` 对未知变量/非法操作 raise ValueError，应静默返回 | 4 处 `raise` → `return SetResult(accepted=False, reason=...)` |
| 4 | P1 | `_last_bridge_text` 使用未过滤的 `parsed.bridge_text`，含全部分支文本 | 改用 `sp.get_bridge_text(current_branch)` |
| 5 | P2 | Adventure Log Prompt 语言 spec-vs-code 不一致（spec 中文，代码英文） | Spec 更新：所有 Prompt 统一英文，输出语言由 story_config.language 决定 |
| 6 | P2 | StreamingXmlParser 未校验重复 bridge | 第二个 bridge 记入 `_format_errors`（与 post-bridge 违规同级） |

**依据**：commit `e5611da`

### 结局节点设计修订 —— routes 数量判定结局

**背景**：原设计用 `node="end"` 特殊值标识结局节点。问题：(1) 多结局故事中命名冲突，(2) LLM 需额外记住命名约定。

**决策**：移除 `node="end"` 特殊值。结局判定改为：**大纲定义中 routes 为空 = 结局节点**。`co_create.py:validate_outline` 已确保仅最终节点 routes 为空。

**影响文件**：`block-spec.md` §4、`data-model.md` §2、`exec-flow.md` §5.2、`prompt-design.md` §3.4、`co_create.py`（CO_CREATE_SYSTEM_PROMPT + parse_outline）

**依据**：spec 文档在上述 commit 中同步更新。

---

---

### Bridge 处理流程审计 —— 时序模型澄清与 Pipeline 缺口

**背景**：2026-07-11 的 StreamingXmlParser 恢复（commit `56cb7ee`）和全面集成后，仍有遗留问题：`_stream_parse_chunk()` 丢弃 `EventType.BRIDGE`，pre-fetch 触发时机和时序模型存在理解偏差。本 session 对 bridge 处理全流程进行系统性审计。

**时序模型澄清（关键认知修正）**：

三层独立流模型：
```
LLM 生成流（token 产出）
    ≥
程序解析流（StreamingXmlParser 逐行解析）
    ≥
UI 展示流（用户阅读 / 自动推进）
```

**`<bridge/>` 的正确定位**：
- 对 LLM：**结构约束**——标记交互区与叙事区硬分界
- 对程序：**模式切换**——`_post_bridge = True`，后续快速解析（无 UI 反馈）、错误捕获、bridge_text 存储
- Pre-fetch 的真正触发点是 **`</story>`（解析完成）**，不是 `<bridge/>`
- Bridge→`</story>` 区间解析极快（纯叙事、无 UI 阻塞），两者几乎同时

此澄清推翻了之前记忆文件中的部分结论——pre-fetch 不需要在 bridge 时刻立即触发，当前在解析完成处触发是正确设计。

**标准每轮流程**（引擎视角）：

```
1. TTFT 等待 — UI 展示上一轮 bridge_text（首轮无）
2. <story> 开始 — 解析生命周期入口
3. 流式解析 — 逐行处理，向 UI 发送 segment，必要时等待 UI 反馈（选项）
4. <bridge/> — 模式切换（非时序触发器）
5. </story> — 打包数据 → 存储 → 组装 Prompt → 后台 API 调用
6. 错误处理 — 严重（通知 UI、用户决策）/ 普通（程序内部处理、Prompt 反馈）
```

**修复内容**（commit `30a4a09`）：

| 修复 | 说明 |
|------|------|
| BRIDGE 事件产出 | `_stream_parse_chunk()` 新增 `{"type": "bridge"}` yield |
| 统一分支过滤 | 移除 `position == "pre"` 限制——post-bridge 命名 branch 同样按 `current_branch` 过滤 |
| 规范：三层时序 | `exec-flow.md` §4.3 增加时序模型 + 流间同步规则 |
| 规范：bridge 双重角色 | `exec-flow.md` §4.7 重写——分离"LLM 结构约束"和"程序模式切换" |
| 规范：UI 队列缓冲 | `exec-flow.md` §4.5 增加推荐 UI 消费模式 |

**剩余缺口**：

代码侧：
- `STORY_BEGIN` / `STORY_END` 事件被 `_stream_parse_chunk()` 丢弃——引擎无法感知解析生命周期边界（P1）
- 错误处理不一致：API 错误用 `yield {"type": "error"}`，解析失败用 `raise ParseError`——调用者需两条路径（P1）
- `continue_round_stream()` 与 `_stream_from_prefetch()` 共享 ~70 行重复逻辑——应抽取 `_process_round()`（P2）

规范侧：
- §4.1 8-step pipeline 混淆引擎/UI 职责（P1）
- 缺少显式 TTFT 等待阶段描述（P2）
- 缺少错误严重等级分类（P1）

**依据**：
- commit `30a4a09` — `fix(engine): surface BRIDGE events, unify branch filter across bridge boundary`
- [[2026-07-11-bridge-processing-audit]]（完整审计记录）
- [[2026-07-11-streaming-parser-timing-flaw]]（更新后状态）
- [[streaming-parser-integration-2026-07-11]]（更新后状态）

### 叙事循环统一 —— 审计缺口全面修复

**背景**：上一条审计发现 8 个缺口（4 代码 + 4 规范）。本 session 按照 6 阶段引擎视角标准流程，逐一修复。

**决策**：

**规范修复（3 项）**：
| 修复 | 说明 |
|------|------|
| §4.1 8-step → 6-phase | 替换混淆引擎/UI 职责的旧管道，明确职责边界 |
| §4.1.1 错误等级分类 | 正式定义两级错误：严重（通知 UI→用户决策）vs 普通（内部处理→Prompt 反馈） |
| TTFT 等待阶段 | 6 阶段第 1 步显式描述 |

**代码修复（5 项）**：
| 修复 | 说明 |
|------|------|
| STORY_BEGIN / STORY_END 事件 | `_stream_parse_chunk()` 不再丢弃——引擎可感知解析生命周期边界 |
| 提取 `_apply_deferred_step()` | Steps 2-3.6（延迟 set + 路由评估 + checkpoint 累积）在 `_launch_prefetch` 和 `continue_round_stream` 之间共享，消除重复 |
| 提取 `_finalize_parsed_round()` | Post-parse 逻辑（format_errors → add_round → unconditional sets → adventure log → options/ending/done yield → notify）从两处 ~70 行重复变为一处 |
| 删除 `_stream_from_prefetch` | 内联到 `continue_round_stream`——**单一续行入口**。Pre-fetch 降级为 API 响应来源的二选一（`queue.Queue` vs `api_client.stream_chat_iter`），不再有独立流程 |
| 错误路径统一 | `XmlParser` 的 `raise ParseError` 路径已从生产流消除（核心引擎零引用），所有错误统一走 `yield {"type": "error"}` |

**架构效果**：
```
continue_round_stream(choice_key)    ← 唯一续行入口
  ├─ [pre-fetch hit]  从 queue 取 chunks（来源 B）
  └─ [pre-fetch miss] 实时调用 API（来源 A）
  └─ _finalize_parsed_round()        ← 统一完成出口
```
净变化：-96 行（394 insertions, 490 deletions），8 个审计缺口全部关闭。

**依据**：
- commit `640a862` — `refactor(engine): unify narrative loop into single continuation flow`
- [[2026-07-11-bridge-processing-audit]]（缺口来源，状态更新为已关闭）

### Bridge pre-fetch 时机缺陷 —— 未在 `<bridge/>` 处即时触发

**背景**：2026-07-11 规范合规审查发现，`exec-flow.md` §4.3 明确要求：

> 当程序解析到 `<bridge/>` 时，立即通过 bridge pre-fetch 在后台线程发起下一轮 API 调用 — 同时继续展示 post-bridge 段落（bridge_text）。

但当前实现的实际时序为：

```
流式接收全部 token
  └─ _stream_parse_chunk 仅处理 SEGMENT 事件
     └─ BRIDGE 事件被 StreamingXmlParser 内部消费（设置 _post_bridge=True）
         ↓  —— GameLoop 完全不感知 bridge 时刻 ——
全部 token 接收完毕
  └─ sp.get_result()          # 完整解析
  └─ sp.get_bridge_text()     # 过滤 bridge_text
  └─ add_round(...)           # 存入 ContextManager
  └─ _launch_prefetch(...)    # 组装下一轮 Prompt
```

**核心问题**：`_stream_parse_chunk()`（`game_loop.py:1062`）只对 `EventType.SEGMENT` 做分支过滤和产出，`EventType.BRIDGE` 事件被丢弃。GameLoop 无法在 bridge 时刻触发 pre-fetch，必须等待全部 token 接收完毕。

**后果**：pre-fetch 竞争的不是"bridge_text 展示时长 vs TTFT"，而是"bridge_text 展示时长（10-20s）vs **完整生成时间 + 下一轮 TTFT**（35-80s）"。这违背了 bridge 机制的核心设计意图——利用 bridge_text 展示时间掩盖 API 延迟。

**待解决**：
1. `_stream_parse_chunk` 需要产出 `{"type": "bridge"}` 事件
2. `continue_round_stream` 在收到 bridge 事件时：已积累的 pre-bridge 数据（sets、checkpoint、routes）足以组装下一轮 Prompt；bridge_text 在流式接收中逐步附加
3. 预取线程在 bridge 时刻启动，与 post-bridge 展示并发执行

**依据**：
- `exec-flow.md` §4.3 — 明确要求 bridge 时刻即时触发 pre-fetch
- `exec-flow.md` §4.4 — "利用 NNN| 行号前缀使每行成为自包含的 XML 片段，逐行正则匹配产出事件"
- [[2026-07-11-streaming-parser-timing-flaw]] — 此前已分析过全量解析导致 pre-fetch 必然失败

### StreamingXmlParser 恢复与集成 —— 流式解析落地

**背景**：经过时序缺陷讨论（见下一条），确认 `StreamingXmlParser` 必须恢复。同时明确了三个架构认知：
1. 三条流（LLM 生成、程序解析、用户显示）是**时序顺序**关系而非速度关系——不可逆的先后依赖 + bridge 时刻的时间重叠
2. 双线处理（预处理建索引 + 实际处理做决策）在当前规模下无必要——分支过滤仅需 5 μs，O(1) 跳转无实际收益
3. 流式解析 ≠ 双线处理——前者解决"何时处理"，后者解决"几遍处理"。上一个 Agent 将二者混淆是删除 StreamingXmlParser 的关键原因

**决策**：
1. 从 git 历史恢复 `StreamingXmlParser`（commit `6697f47^`），修复 5 个 bug：
   - `m.lastindex` 脆弱逻辑 → 显式 group 索引
   - `_RE_SEG` 未捕获 n 属性 → 添加捕获组
   - Choice 合并逻辑错误 → `feed_line()` 中累积 `_pending_choices`
   - 自闭合 `<checkpoint/>` 不识别 → 新增 regex
   - SEGMENT 事件缺 `branch_name` → 从状态机设置
2. 移除双线预处理索引（`branch_ranges`、`_branch_start_line`）——单遍解析
3. 新增 `LineBuffer` 适配器：token chunks → 完整行
4. `_stream_from_prefetch()` 重写：`thread.join()` + 一次性 drain 替换为增量 `queue.get_nowait()` + `LineBuffer` → `StreamingXmlParser.feed_line()`。Segment 事件在行完成时即时产出
5. Pre-fetch 触发时机修复：`_launch_prefetch()` 从 `_emit_parsed()` 之后移至之前，`done_state` 在调用前捕获
6. 保留 `XmlParser.parse()` 用于非 pre-fetch 路径（Round 1、choice 轮次、ContextManager）
7. 45 个流式解析器测试 + 7 个一致性测试（vs XmlParser）

**依据**：
- commit `56cb7ee` — `feat(parser): restore StreamingXmlParser with streaming pre-fetch integration`
- [[2026-07-11-streaming-parser-restoration]]（完整变更记录）
- [[2026-07-11-streaming-parser-timing-flaw]]（动机分析）
- `docs/superpowers/specs/2026-07-05-narrative-flow-refactor-design.md` §2.2-2.5（设计依据）
- 303 passed, 24 skipped, 0 failed

### StreamingXmlParser 全面融入核心流程 —— 全量解析彻底平替

**背景**：上一条日志恢复了 `StreamingXmlParser` 但仅用于 pre-fetch 路径——Round 1 和 continue 慢路径仍使用 `XmlParser.parse()` 全量解析，且 `ContextManager._extract_bridge_from_xml()` 也依赖 `XmlParser`。

**决策**：
1. **三条路径统一流式化**：`start_round1_stream()` 和 `continue_round_stream()` 慢路径在 token 收集期间同步 `LineBuffer` + `StreamingXmlParser`，segment 事件随行完成即时产出
2. **提取 `_stream_parse_chunk()`**：消除三处 chunk→parser→event 重复逻辑
3. **`_emit_parsed()` → `_emit_options()`**：segment 在流式阶段已产出，`_emit_parsed` 简化为仅产出 options 事件
4. **`StreamingXmlParser` 增强**：
   - `_bridge_text_parts` → `_bridge_text_items: list[tuple[str, str|None]]` 追踪分支归属
   - 新增 `get_bridge_text(branch_name)` 方法支持分支过滤
5. **`ContextManager._extract_bridge_from_xml()`**：改用 `StreamingXmlParser.get_bridge_text()` 替代 `XmlParser.parse()` / `extract_bridge_text_for_branch()`
6. **Dataclass 归属迁移**：`ParsedOutput`、`Segment`、`SetOperation`、`RouteTarget`、`ParseError` 从 `xml_parser.py` 移至 `streaming_parser.py`（规范解析器拥有类型定义）。`xml_parser.py` 反向导入。所有生产代码消费者统一从 `storyloom.parser` 包级别导入
7. **测试数据修正**：`SAMPLE_XML` 的 `<opt key>` 从 `A`/`B` 改为 `1`/`2`（匹配规范）；`test_context_manager` 紧凑 XML 改为逐行格式（匹配真实 LLM 输出）

**架构效果**：
- 核心引擎（`game_loop.py`、`context_manager.py`）零依赖 `XmlParser` 类
- `xml_parser.py` 仅含 `XmlParser` 类（从 `streaming_parser` 导入类型），可安全删除
- 完整删除步骤记录在 [[xml-parser-removal-guide-2026-07-11]]

**依据**：
- `exec-flow.md` §4.3："所有轮次使用 `StreamingXmlParser` 逐行解析"
- `block-spec.md` §1："程序通过 `StreamingXmlParser` 逐行流式解析"
- commit `748f654` — `docs(spec): mandate StreamingXmlParser for all rounds, replace ElementTree full-parse`
- [[streaming-parser-integration-2026-07-11]]（完整变更记录）
- 303 passed, 24 skipped, 0 failed

### StreamingXmlParser 删除决定推翻 —— Bridge Pre-Fetch 时序缺陷

**背景**：2026-07-10 的架构分析（[[2026-07-10-adventure-log-and-parser-architecture]]）认为 `StreamingXmlParser` 的流式解析不必要，因为 `ElementTree` 全量解析仅需 234 μs。该模块被删除（commit `6697f47`）。2026-07-11 的深入讨论发现该分析存在根本性错误。

**核心发现**：Bridge pre-fetch 的时序约束不是"解析速度"，而是"**首段可展示内容的就绪时间**"。

**全量解析模型**（当前）：
- 下一轮内容可展示的前提：TTFT + **全部行**生成完毕 + XmlParser.parse()
- bridge_text 阅读时间（10-20s）需覆盖 TTFT + 完整生成时间（35-80s）
- **结论：不可能。** bridge_text 太短，pre-fetch 大概率无法在阅读期间完成
- 后果：用户在自动推进轮次之间经历 15-70 秒空白等待

**流式解析模型**（删除的 StreamingXmlParser）：
- 下一轮内容可展示的前提：TTFT + **第 1 行**生成完毕 + feed_line()
- bridge_text 阅读时间（10-20s）仅需覆盖 TTFT（10-30s）
- **结论：可行。** 在大多数场景下可实现无缝衔接

**之前分析为何错误**：
- 错误指标：已完成的 XML 字符串的解析耗时（234 μs）
- 正确指标：**从 pre-fetch 启动到首个可展示内容就绪的墙上时间**
- 差距不是 234 μs，而是**整个生成时间（25-50 秒）**

**附加发现**：`_launch_prefetch()` 在 `yield from self._emit_parsed()` 之后才调用。终端 UI 同步消费 segment 事件（含 `time.sleep`），导致 generator 阻塞——pre-fetch 在所有 segment 显示完毕后才能启动。bridge_text 实际提供了**零秒缓冲**。

**决策**：推翻 07-10 的删除决定。需要恢复 `StreamingXmlParser`（从 commit `7fe2278`）并正确集成到 pre-fetch 路径：
1. 移动 pre-fetch 触发点到 `_emit_parsed()` 之前
2. 后台线程中逐行 feed 到 StreamingXmlParser
3. ParseEvent 实时转发给 UI（segment 逐段展示，不等完整响应）
4. `XmlParser.parse()` 保留用于非 pre-fetch 路径（choice 轮次、Round 1）

**依据**：
- [[2026-07-11-streaming-parser-timing-flaw]]（完整时序分析）
- [[2026-07-10-adventure-log-and-parser-architecture]]（部分分析被推翻）
- `docs/superpowers/specs/2026-07-05-narrative-flow-refactor-design.md` §2.5-2.6（原始设计正确）
- exec-flow.md §4.3："bridge 机制的真正时限不是 LLM 总生成时间，而是后台 API 调用的 TTFT + 生成时间 vs. bridge_text 的展示时长"

### Adventure Log 时序修复

**背景**：`exec-flow.md` §5.2 要求冒险日志在 bridge 时刻发起，与 bridge_text 展示并发执行。实际代码中 `run_adventure_log()` 在所有 segment 展示完毕后同步调用——用户需额外等待 LLM 生成时间。

**决策**：
1. 提取 `_accumulate_checkpoint()` 辅助方法（消除 3 处重复的 checkpoint 处理逻辑）
2. Post-parse "end" 检测——Step 7 后立即检查 `parsed.checkpoint_node == "end"`
3. Adventure log 在 `_emit_parsed()` 前启动 daemon 线程，segment 展示期间并发执行
4. Early-return guard：`self._ending_handled` 标志防止结局后被重复调用

**依据**：
- commit `980ec2f` — `fix(engine): adventure log now runs concurrently with bridge_text display`
- [[2026-07-10-adventure-log-timing-fix]]
- exec-flow.md §5.2 并发设计描述

---

## 2026-07-10（周五）

### bridge pre-fetch 实现

**背景**：Bridge 机制要求程序在展示 post-bridge 缓冲文本期间发起下一轮 API 调用，以消除段边界停顿。exec-flow.md §4.3 描述了时序模型——程序解析到 `<bridge/>` 时立即提交下一轮 Prompt，同时继续展示 bridge_text。但此前实现侧一直是串行等待：展示完所有内容 → 等待玩家输入 → 组装 Prompt → API 调用 → 等待响应 → 开始下一轮。

**决策**：在 `GameLoop._launch_prefetch()` 中实现 daemon 线程 + `queue.Queue` 架构。

**触发条件**：仅对无选项（auto-advance）轮次触发。choice 轮次无法预计算下一轮的 messages 数组——bridge_text 的 branch 过滤依赖玩家选择，只有在玩家做出选择后才能确定 `current_branch`。

**流程**：
```
到达 <bridge/>
    │
    ├─ ① 检测：parsed.choices 非空？
    │   ├── 有 choice → 不预取（下一轮取决于玩家选择，messages 数组无法预计算）
    │   └── 无 choice → _launch_prefetch()
    │       ├── 捕获当前状态快照（done_state）
    │       ├── 组装下一轮 messages
    │       └── 启动 daemon 线程：api_client.stream_chat(messages) → queue.Queue
    │
    └─ ② 主线程：继续 emit bridge_text segments
        （用户阅读中；后台线程在 queue 中缓冲 chunks）
```

**已知局限**（07-10 已知，07-11 修复）：
- `_launch_prefetch()` 在 `yield from self._emit_parsed()` 之后调用——终端 UI 同步消费 segment 事件会阻塞 generator，导致 pre-fetch 在所有内容展示完后才启动。详见 07-11 日志"Pre-fetch 触发时机修复"
- 后台线程收集完整响应后才由主线程解析——无法实现流式展示。详见 07-11 日志"StreamingXmlParser 恢复"

**依据**：
- commit `663b9f2` — `feat(engine): implement bridge pre-fetch for auto-advance rounds`
- exec-flow.md §4.3 描述的时序模型
- [[2026-07-10-bridge-prefetch-work-log]]

### 规范合规审计与修复

**背景**：对代码实现与 4 份权威 spec 文档（exec-flow.md、block-spec.md、prompt-design.md、data-model.md）进行逐条对照审计。这是引擎完备化后首次系统性审计。

**决策**：发现并修复 1 P0 + 3 P1 + 4 P2 问题：

| 等级 | 问题 | 说明 | 修复 commit |
|------|------|------|-------------|
| P0 | unconditional set 双重应用 | 无条件的 `<set>` 在流式处理阶段应用一次，`_apply_sets()` 又应用一次 | `4715904` |
| P1 | emit_parsed 未传递 current_branch | 选项选择后的分支切换未反映在事件中 | `4715904` |
| P1 | AUTO_ADVANCE_DELAY_MS spec 引用错误 | 常量引用位置与 spec 不一致 | `4715904` |
| P1 | Round 1 parse 失败缺少 observer 通知 | `start_round1_stream` parse 失败路径缺少 `_notify()` 调用 | `951145c` |
| P2 | adventure log 时序 | 同步执行改为并发（见 07-11 详细日志） | `980ec2f` |
| P2 | save 文件缺少 label 字段 | spec 要求但未实现 | `642465f` |
| P2 | 配置文件与 data-model.md §A 不同步 | 常量值未反映最新 spec | `642465f` |
| P2 | streaming_parser.py 残留 | 已废弃的模块仍在仓库中 | `642465f`（后续 `6697f47` 彻底删除）|

**依据**：
- [[2026-07-10-spec-compliance-audit]]（完整审计报告）
- [[2026-07-10-spec-compliance-followup]]（修复记录）
- [[2026-07-10-adventure-log-timing-fix]]

### StreamingXmlParser 删除 **【07-11 推翻，见当日日志】**

**背景**：2026-07-05 的 narrative flow refactor 设计（`docs/superpowers/specs/2026-07-05-narrative-flow-refactor-design.md`）规划了 `StreamingXmlParser`——基于 `NNN| ` 行号前缀的逐行流式解析器，含状态机（`IN_STORY | IN_BRANCH | IN_CHECKPOINT | IN_CHOICE | POST_BRIDGE`）和预处理/实际处理双重线。该模块于 07-06 实现（commit `39c049d`）。

**07-10 的决策**：删除 `streaming_parser.py`。

**07-10 的理由**：
1. bridge pre-fetch 在后台线程完成完整 API 调用 + `ElementTree` 解析——流式解析的"边收边处理"优势被覆盖
2. 状态机 + 双重处理线（预处理建索引 / 实际处理做决策）的复杂度与 `ElementTree` 全量解析的 millisecond 级耗时不成比例
3. 两套解析器（XmlParser + StreamingXmlParser）需保持语义一致——维护负担 > 理论收益

**07-11 的推翻**：上述分析聚焦在错误的指标上（已完成的 XML 字符串解析耗时 234 μs）。正确指标是从 pre-fetch 启动到**首个可展示内容就绪**的墙上时间——全量解析需等待完整生成（25-50s），流式解析仅需等待首行生成。详见 07-11 日志"StreamingXmlParser 删除决定推翻"。

**教训**：**选择正确的度量指标是架构决策的前提。** 错误的指标（解析耗时）导向了错误的决策（删除流式解析器）。桥接机制的核心度量是"首段可展示时间"，而非"解析吞吐量"。

**依据**：
- [[2026-07-10-adventure-log-and-parser-architecture]]（部分分析被推翻）
- [[2026-07-11-streaming-parser-timing-flaw]]（修正分析）
- `src/storyloom/parser/streaming_parser.py` 已不存在（需从 `7fe2278` 恢复）

### CoCreateFlow.run() 删除

**背景**：`CoCreateFlow.run()` 是遗留的同步方法，内部直接调用 `Display` 进行终端 I/O（`d.output.write()`、`d.show_wait_message()`、`d.get_input()`）。随着 07-07 实现的状态机 API（`start()`/`send()`）和 07-10 的 `dev_cli`，该方法的使命终结。

**具体清理**：
- 删除 `run()` 方法（含内嵌的 `_step1_get_idea()`、`_step2_questioning()` 终端 I/O 调用）
- 删除所有对 `Display` 的直接/间接引用
- `GENERATE_ALL_PROMPT` 模板中的硬编码 UI 提示替换为引擎中立表述
- `_generate_all()` 重构为纯引擎逻辑（无 UI 副作用）

**影响**：commit `a6d941f` — `2 files changed, 268 insertions(+), 566 deletions(-)`（净 -298 行）。CoCreateFlow 现在完全 UI 无关——通过 `UiInterface` 协议和返回 dict 与任意 UI 层交互。

**依据**：
- commit `a6d941f` — `refactor: remove CoCreateFlow.run() and all UI coupling from core engine`
- CLAUDE.md §UI Territory 明确引擎不应依赖 UI 层文件
- [[2026-07-10-ui-logic-separation-audit]]

### Dev CLI 完整实现

**背景**：07-07 将 CLI 降级为测试工具后，`main.py` 成为尴尬的存在——它不再是"主界面"但却是唯一的 CLI 入口。需要一个最小化的 CLI 来：(1) 验证引擎端到端能力，(2) 提供开发者检查（记录原始 Prompt/响应/解析数据），(3) 可作为 Web UI 开发者的引擎行为参考。

**决策**：实现 `src/storyloom/dev_cli/` 包，独立于引擎核心（引擎零修改）。

**架构**：
```
dev_cli/
├── __init__.py      # dev_main() entry point
├── args.py          # 参数解析（--mode normal|dev, --story <file>, --no-save, --lang）
├── ui.py            # TerminalUi（实现 UiInterface）+ 游戏流程驱动 run_co_create()/run_game()
└── observer.py      # DevObserver → dev_output/{prompts,responses,checks}.txt
```

**关键设计决策**：
- **零引擎变更**：通过 `GameLoop._observers`（Python 约定私有属性）注册 DevObserver——引擎代码一行不改
- **追加模式输出**：3 个输出文件始终追加（`dev_output/prompts.txt`、`responses.txt`、`checks.txt`）——跨 session 累积
- **事件驱动消费**：`run_game()` 遍历 stream 事件（token→忽略、segment→print、options→菜单、state→记录、error→stderr、done→循环终止判断）
- **Ctrl+C 安全**：KeyboardInterrupt 在 `ask()` 中传播，在 `run_game()` 中捕获并提示存档

**实现迭代**（17 个 commits，`45ebd25` → `93c6020`）：
- 基础框架：args（`c580177`）、TerminalUi + driver（`6da20aa`）、DevObserver（`864aec2`）
- 体验修复：段间延迟 0.5s（`814e72f`）、流式实时输出（`8df3545`）、等待提示（`b8818b1`）
- 健壮性：错误处理（`e61d845`）、KeyboardInterrupt 传播（`f77f76d`）、事件字段守卫（`735dba1`）
- 完善：共创记录（`c250fd8`）、完整 messages 数组记录（`09f291a`）、速度配置/覆盖模式/暂停（`93c6020`）

**依据**：
- 设计 spec：`docs/superpowers/specs/2026-07-10-dev-cli-design.md`
- 实现计划：`docs/superpowers/plans/2026-07-10-dev-cli.md`

### 系统 Prompt 英文化

**背景**：部分 Prompt 残留中文硬编码，违反 prompt-design.md §1.1 确立的"英文 Prompt"原则（所有系统/叙事 Prompt 使用英文）。具体问题：(1) 冒险日志 Prompt 模板使用中文，(2) 共创 Prompt 中混入中文变量名假设，(3) 格式规范部分有中英混杂。

**决策**：全面清理：
1. 所有系统/叙事 Prompt 切换为英文——角色定义、输出格式、核心规则、质量要求
2. 冒险日志 Prompt 改为英文 + 引擎中立信号（用 `{story_label}`、`{chapter_title}` 占位符替代硬编码中文）
3. 代码注释中的中文替换为英文
4. i18n 层严格仅处理 UI 文本（CLI 输出、菜单、提示）——不触碰 Prompt

**依据**：
- commit `048ab53` — `refactor: purge Chinese from system prompts and format spec, enforce i18n layer separation`
- commit `77314b7` — `refactor: rewrite adventure log prompt in English, use neutral engine signals`
- prompt-design.md §1.1 英文 Prompt 原则

---

## 2026-07-07（周一）

### API 审计与界面集成设计

**背景**：引擎声称 UI 无关，但审计发现 Web UI 开发者需要重新实现大量业务逻辑才能接入——`CoCreateFlow` 的同步 `run()` 方法内嵌终端 I/O、`GameLoop` 的关键数据（checkpoint 历史、大纲节点）仅以私有属性存在、没有统一的会话生命周期管理。

**审计流程**：系统性地对照 "UI 需要做什么" vs. "引擎提供了什么"：

```
[Menu] → [Co-Create] → [Init GameState] → [Narrative Loop] → [Ending] → [Menu]

Phase              Engine Provides               UI Can Use Directly?
─────              ───────────────               ────────────────────
Menu               SaveManager.list_saves()      ✅
                   SaveManager.delete()          ✅
New Game           CoCreateFlow.run()            ❌ (synchronous, embedded UI)
                   GameState(story_config)       ✅
                   GameLoop(...)                 ⚠️ (7 constructor params)
Gameplay           start_round1_stream()         ✅
                   continue_round_stream(key)    ✅
                   get_available_options()       ✅
                   to_save_dict()                ✅
                   round_count, current_node     ✅
                   checkpoint_history            ❌ (private _attribute)
                   outline_nodes                 ❌ (private _attribute)
Ending             type: "ending" event          ✅ (built into stream)
                   adventure_log                 ✅ (in ending event)
Return to Menu     —                             ❌ (no transition mechanism)
```

**决策**：识别 5 个缺口并逐一解决：

| # | 缺口 | 严重度 | 解决方案 |
|---|------|--------|---------|
| 1 | UiInterface 过于极简（3 方法不够语义化） | 🔴 | 保持协议不变，通过状态机 API 返回 dict 弥补——UI 从返回值判断意图 |
| 2 | CoCreateFlow 不可被 Web UI 复用 | 🔴 | 实现 `start()`/`send()` 状态机 API——每个调用返回 `{phase, content}` dict，UI 自由决定如何展示 |
| 3 | 无顶层会话编排器 | 🔴 | 新增 `GameSession` 类——封装"新游戏/加载/保存"完整生命周期 |
| 4 | GameLoop 缺少公开访问器 | 🟡 | 新增 `checkpoint_history`（`list[dict]`）和 `outline_nodes`（`list[dict]`，含格式归一化）属性 |
| 5 | SaveManager 未与 GameLoop 统一 | 🟡 | `GameSession` 封装 `SaveManager`——UI 不需要手动连接二者 |

**关键发现——预存 bug**：`_outline_nodes` 存在两种不可互换的内部格式：
- 新鲜创建路径（`CoCreateParser.parse_outline()`）：`[{id, title, goal, routes: [{condition, target}]}]`
- 从 save 恢复路径：`[{node_id, title, goal, status, branches}]`

公开访问器 `outline_nodes` 需做格式归一化——**这是审计过程中发现的，而非预先知道的 bug。** commit message 中标注了此发现。

**状态机 API 设计**：
```python
flow = CoCreateFlow(api_client, ui=None)  # ui 参数可选——为 Web UI 设计
flow.start()                              # → {phase: "awaiting_idea"}
flow.send("a cyberpunk story")            # → {phase: "awaiting_answer", content: "..."}
flow.send("开始")                          # → {phase: "complete", result: CoCreationResult}
flow.abort()                              # 任意时刻中止
flow.phase                                # 当前阶段（只读）
flow.result                               # CoCreationResult | None（只读）
```

**依据**：
- 设计：`docs/superpowers/specs/2026-07-07-api-audit-and-interface-design.md`（v2 自我审查修正版）
- 计划：`docs/superpowers/plans/2026-07-07-api-interface-implementation.md`
- 实现 commits：
  - `03d992f` — `feat: add CoCreateFlow.start() method`
  - `e3a6750` — `feat: add CoCreateFlow.send() state machine method`
  - `0874cce` — `feat: add CoCreateFlow phase, result properties and abort() method`
  - `67a086e` — `feat: make CoCreateFlow ui parameter optional for state machine API`
  - `2ba92ea` — `feat: add GameSession lifecycle coordinator`
  - `7d08624` — `feat: add GameLoop.checkpoint_history public property`
  - `f8667df` — `feat: add GameLoop.outline_nodes public property with format normalization`

### CLI 降级与观察者统一

**背景**：`main.py` 中的 CLI 原本是"主界面"——直接从终端交互驱动游戏循环。但 Web 界面已成为主要 UI 层（并行分支活跃开发），且 `Display` 类混入了 `GameLoop`——引擎直接调用终端 I/O 方法，违反 UI-引擎解耦原则。

**决策**：
1. **CLI 降级**：`main.py` 从"主界面"变为"测试/维护工具"——保留 `--quick` 模式供开发者快速验证引擎行为
2. **Display 移除**：`GameLoop` 不再持有 `Display` 引用。所有内容输出改为 generator yield 事件流——`token`、`segment`、`options`、`state`、`error`、`done`
3. **观察者统一**：`cli_utils.py` 集成 observer 回调注册——供 `dev_cli` 和 `main.py` 共享

**事件流设计**（此设计为 07-10 Dev CLI 的基础）：

| type | payload | 说明 |
|------|---------|------|
| `token` | `{"text": str}` | LLM 逐 token（供 Web UI 流式渲染） |
| `segment` | `{"text": str, "n": int, "position": "pre"\|"post", "branch": str\|null}` | 叙事段完成 |
| `options` | `{"choices": [{"id": str, "branches": [str], "labels": [str], "conditions": {}}]}` | 选项面板 |
| `state` | `{"vars": dict, "changes": [{"var": str, "op": str, "val": str, "accepted": bool}]}` | 状态变更 |
| `error` | `{"message": str}` | 格式/API 错误 |
| `done` | `{"round": int, "node": str\|null, "state": dict}` | 轮次结束 |

**依据**：
- commit `2127350` — `refactor: demote CLI to test-only harness, unify observer system`
- commit `6697f47` — `refactor: remove dead code and mark deprecated files`
- [[2026-07-07-cli-observer-refactor]]

### 3 个 P0 引擎 Bug 修复

**背景**：代码审查发现条件变量解析逻辑存在优先级不一致——不同求值场景使用不同的解析顺序，导致同一条件在不同上下文中得出不同结果。

**Bug 1 — 条件变量解析优先级不一致**：
- 问题：`choice_dict > state_vars` 优先级在 options 置灰判断中遵循此顺序，但在 `set` 条件求值和 `route` 条件求值中使用相反顺序
- 根因：三处条件求值是独立实现的代码路径，没有共享的求值函数
- 修复：抽取共享的 `_evaluate_condition()` 方法，统一优先级为 `choice_dict > state_vars`（与 block-spec.md §3 一致）
- 影响：未修复时，`<set if="approach==1">` 在 choice_dict 已包含 `approach` 时可能错误地回退到 state_vars 查找

**Bug 2 — number 越界未 clamp**：
- 问题：`<set var="体力" op="-" val="100"/>` 结果可能为负数（如当前 30 → -70）
- 根因：`_apply_number_op()` 执行算术但没有边界检查
- 修复：所有 number 操作结果 clamp 到 [0, 100]（与 block-spec.md §5 一致）
- 影响：未修复时，LLM 可能在后续轮次中基于负数状态做出不合理叙事决策

**Bug 3 — route 兜底策略缺失**：
- 问题：checkpoint 的所有分支条件都不命中时，`target_node` 保持为 `None`——程序不知道该推进到哪个节点
- 根因：仅实现了"命中则设置 target"的逻辑，没有 else 分支
- 修复：取第一条 route 的 target 作为兜底（与 data-model.md §2 兜底策略一致——"取 LLM 列出的第一个分支"）
- 影响：未修复时，条件不命中会导致大纲推进卡死

**依据**：
- commit `6533e10` — `fix: condition priority, number clamp, route fallback — 3 core engine bugs`
- block-spec.md §3 条件变量解析优先级 + §5 状态变更校验
- data-model.md §2 兜底策略说明
- [[2026-07-07-audit-and-bugfix]]

### 规范文档 NNN| 格式同步

**背景**：代码于 07-05 迁移到 `NNN| ` 行号前缀格式（commit `ce5a776`），但规范文档（block-spec.md、prompt-design.md、data-model.md）仍使用旧的 `<seg n="N">` 属性编号描述——文档与代码不一致。

**修复范围（8 处）**：
1. block-spec.md §1 速查表：`<seg>` 的 `n` 属性描述改为"可选（兼容旧格式）"
2. block-spec.md §2：新增完整的行号规则节（`NNN| ` 前缀、零填充 3 位、全局连续）
3. block-spec.md §2.3：`XmlParser` 解析流程更新为剥离前缀 + 兼容 `n` 属性
4. prompt-design.md §4.2：Round 1 Prompt 模板中 `<seg N>` 替换为 `NNN| <seg>`
5. prompt-design.md §4.3：Round N 上下文描述更新
6. data-model.md §A.4：新增 `LINES_PER_ROUND_*` 行控制常量 + 架构说明
7. data-model.md §A.7：废弃 `SEGMENTS_PER_ROUND_*`、`BRIDGE_SEGMENT_RATIO`、`MIN_NARRATION_CHARS`
8. exec-flow.md §4.4：解析流程更新为行号剥离描述

**依据**：
- commit `f283d24` — `docs: sync spec format to NNN| line-number prefix, fix 8 issues`
- [[2026-07-07-doc-audit-and-format-sync]]

---

## 2026-07-16（周四）

### API 配置去品牌化：DEEPSEEK_* → LLM_*

**背景**：`api_client.py` 和 `.env.example` 中的环境变量名为 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`，将配置绑定到了特定提供方。但 `ApiClient` 使用的是 OpenAI 兼容的 `/v1/chat/completions` 接口，DeepSeek、OpenAI、Groq、Ollama、vLLM 等数十个提供方均支持此协议。变量名中的 "DEEPSEEK" 前缀：(1) 误导用户以为仅支持 DeepSeek；(2) 切换到其他兼容提供方时变量名与实际用途不一致。

**决策**：统一重命名为 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`——去品牌化、通用化。不做向后兼容 fallback（`.env` 文件修改变量名即可，无迁移成本）。

**变更范围**：
- `src/storyloom/io/api_client.py`：env var 读取 + 错误消息
- `.env.example`：模板变量名 + 添加多提供方说明注释
- `tests/prompt_lab/run_prompt_test.py`：env var 读取
- `docs/spec/data-model.md` §A.6：`DEEPSEEK_MODEL` → `LLM_MODEL`
- `docs/spec/exec-flow.md` §1：`STORYLOOM_API_KEY` → `LLM_API_KEY`

**依据**：用户决策——统一全局变量优于按提供方分变量；OpenAI-compatible API 的行业标准地位意味着单组变量覆盖所有提供方。

---

## 2026-07-06（周日）

### 后端完备化：存档、结局、解耦

**背景**：引擎核心缺失三个关键能力——(1) 存档系统仅存设计文档（exec-flow.md §2、data-model.md §3），(2) 结局检测和冒险日志未实现，(3) `CoCreateFlow` 直接 `import Display` 并调用终端 I/O 方法，Web UI 无法复用。这三个缺口阻塞了 Web 界面集成和端到端测试。

**设计方法**：以 4 份权威 spec 文档为标准（exec-flow.md、block-spec.md、data-model.md、prompt-design.md），代码适配文档——**spec 是权威，代码是派生。** 采用最小变更策略——只在现有模块上添加新方法/属性，不重构核心流程。

**实现（11 项任务）**：

**任务 1-2：UiInterface 协议 + CoCreateFlow 去耦合**
- 新建 `src/storyloom/core/ui_interface.py`：极简 3 方法协议——`write(text)`、`show_error(text)`、`ask(prompt) → str`
- `Display` 实现 `UiInterface`：`write()` 委托到 `self.output.write()`，`ask()` 委托到 `self.get_input()`
- `CoCreateFlow` 构造函数从 `display: Display` 改为 `ui: UiInterface`——所有 `self._display.output.write(...)` → `self._ui.write(...)`，共替换约 20 处
- 影响范围：仅 CoCreateFlow 和 Display 两个模块——不涉及 GameLoop

**任务 3-4：GameState/GameLoop 序列化**
- `GameState.to_dict()` → `{state_vars: dict}`（仅序列化变量状态）
- `GameState.from_dict(data, story_config)` → 用 story_config 提供的变量定义类型信息恢复 state_vars
- `GameLoop.to_save_dict()` → 组装完整的存档 dict（version、metadata、config、story_config、state_vars、outline、progress、bridge_text）
- `GameLoop.from_save_dict(data, api_client)` → 校验结构完整性 → 恢复 GameLoop 实例
- **关键设计**：`story_config.variables[].initial` 是**共创时的初始值**（非当前值），用于提供类型定义。实际状态来自 `state_vars`

**任务 5-6：存档系统（SaveManager）**
- 新建 `src/storyloom/core/save_manager.py`
- `save(save_data)`：序列化 → 写 `saves/{label}.tmp` → `os.replace(tmp, saves/{label}.json)`（原子写入，data-model.md §3.3）
- `load(label)`：JSON 解析 → 校验 version==1 → 校验关键字段（story_config 含 variables、state_vars、outline、progress）→ 校验 current_node 在 outline 中存在 → 返回 save_data dict
- `list_saves()`：扫描 `saves/*.json`，读取每个文件的 metadata（label、round_count、created_at、updated_at、current_node）
- `delete(label)`：删除 `saves/{label}.json`
- 加载校验失败 → `ValueError`（调用者删除损坏文件，提示用户返回主菜单）
- **前置依赖**：新增 `story_config.label` 字段——commit `926bc8e`。存档文件名从 label 派生（非法字符替换为 `_`，重名追加 `_2`/`_3`）

**任务 7-8：结局检测 + 冒险日志**
- `ending_flag`：GameLoop 新增属性（非 GameState——GameState 管理变量，ending_flag 是流程控制）
- 检测流程：`parsed.checkpoint_node == "end"` → `ending_flag = True` → 标记节点 completed → 存储 checkpoint 摘要/历史/快照 → 触发 auto-save → bridge 处组装冒险日志 Prompt → 独立 LLM 调用
- `build_adventure_log_prompt()`：注入 story_config + state_vars + checkpoint_summaries + checkpoint_history。Markdown 格式，500-1000 字，面向玩家回顾性口吻
- 冒险日志不走叙事循环解析管线——独立 `api_client.chat()` 调用（非流式）
- 新增流事件类型 `ending`：`{type: "ending", adventure_log: str, final_state: dict, summary: str|null}`

**任务 9-10：checkpoint 累积 + outline 结构化存储**
- 新增字段：`_checkpoint_summaries: list[str]`、`_checkpoint_history: list[dict]`、`_checkpoint_snapshots: dict[str, dict]`
- `_outline_nodes: list[dict]`：从 `CoCreateParser.parse_outline()` 获取结构化节点（替代仅存 `outline_text: str`）
- checkpoint snapshot 在 Phase 1 仅存储不读取——为 Phase 2 回档预留

**任务 11：Web 前端 MVP（并行分支）**
- FastAPI + SSE 流式渲染、共创支持、streaming parser 集成
- commit `3035496` — `feat: streaming web frontend with co-creation support`

**全部 commits**：`c18fb71`（SaveManager）、`acfd7c9`（UiInterface）、`4313b6e`（CoCreateFlow 解耦）、`6646a60`/`50a5057`（序列化）、`9f67ac6`（结局）、`06b49ba`（冒险日志）、`8e89d15`（checkpoint 累积）、`e139831`（outline 结构化）、`926bc8e`（label 字段）、`a9bd880`（存档时间戳/结局节点修复）、`65db872`（存档恢复 bridge_text 注入）

**依据**：
- 设计：`docs/superpowers/specs/2026-07-06-backend-completion-design.md`（经自我审查修订——v2 移除不必要的 UiInterface 扩展）
- 计划：`docs/superpowers/plans/2026-07-06-backend-completion.md`（11 任务，TDD）

### Narrative Flow 重构

**背景**：对 `xml_parser.py` 和 `game_loop.py` 的叙事流程进行系统性审视，发现 5 个问题。

**5 个问题及修复**：

1. **bridge_text 未按 current_branch 过滤**（P0）：
   - `XmlParser._extract_bridge_text()` 提取所有 `<branch>` 内的文本节点——未选中分支的文本泄露到下一轮上下文
   - 修复：`_extract_bridge_text(post_children, current_branch=None)`——bare `<seg>`（无分支 = 单路径）始终收集；`<branch name="X">` 仅在 `X == current_branch` 时收集
   - 统一逻辑：不再有"全量模式"和"分支模式"的区分——"默认就是一种分支"

2. **全量解析违背顺序处理原则**：
   - `ElementTree.fromstring()` 一次性解析完整 XML，然后批量处理所有元素
   - 设计文档（narrative-flow-refactor-design.md §2.1-2.2）规划了缓冲式读取——pre-bridge 交互区在 bridge 前处理，bridge 后内容作为缓冲
   - 修复：实现 `StreamingXmlParser`（见下条）（**该模块在 07-10 删除、07-11 恢复——见当日日志**）

3. **`run_full_test.py` 重写了全部生产逻辑**：
   - 手工状态管理、route 评估、choice_dict 构建——这些应该由 GameLoop 完成
   - 修复：全量重写为 GameLoop 驱动——脚本仅做配置 + observer 回调 + 选择策略

4. **无观察者机制**：
   - 测试/发布模式无法区分——每轮数据无法导出供调试
   - 修复：新增 `RoundRecord` dataclass + `observer: Callable[[RoundRecord], None] | None` 回调。每轮结束时调用 `_notify(record)`

5. **`format_error` 从未被赋值**（P0）：
   - `GameLoop._format_error` 声明了但没有任何代码设置它——XML 解析错误不会反馈给 LLM
   - 修复：流式解析异常时设置 `self._format_error`，`PromptBuilder.build_round_n()` 在下一轮注入纠正提示："上一轮输出存在格式问题——{format_error}。请严格遵循 XML 格式规范。"

**额外变更**：
- `ApiClient.stream_chat()` 返回类型从 `str` 改为 `ApiResult`（`{content, ttft, tokens}`）——记录首 token 时间和 token 用量
- 包结构拆分：`src/storyloom/` 扁平结构 → `core/` / `io/` / `parser/` 三个子包（commit `7fe2278`）

**依据**：
- 设计：`docs/superpowers/specs/2026-07-05-narrative-flow-refactor-design.md`
- commit `39c049d` — `refactor: narrative flow — branch-aware bridge_text, observer pattern, streaming parser`
- commit `7fe2278` — `refactor: split flat package into core/io/parser subpackages`

### 国际化迁移：Display.UI → gettext

**背景**：`Display.UI` dict 存储中英文 UI 文本（`{"zh-CN": "...", "en": "..."}`）。翻译者需要编辑 Python 字典——工作流不友好（无法使用标准翻译工具、无法增量更新、无法审查 diff）。

**决策**：迁移到 gettext `.po/.mo` 文件体系，使用标准 Python `gettext` 模块。

**迁移步骤**：
1. 新建 `src/storyloom/i18n.py`：封装 `gettext.translation()`，提供 `_()` 快捷函数
2. 创建 `locale/zh_CN/LC_MESSAGES/storyloom.po`：从 `Display.UI` dict 提取所有 UI 文本作为 msgid
3. 编译 → `locale/zh_CN/LC_MESSAGES/storyloom.mo`
4. `Display.t("key")` → `_("English text")`：所有 UI 文本调用替换
5. `main.py` 删除 `language` 参数传递——语言由 `LANG` 环境变量或系统 locale 决定
6. `co_create.py` 中的中文硬编码 → `_()` 调用
7. 移除 `Display.UI` dict 和 `Display.t()` 方法

**设计原则**：i18n 层严格仅处理 UI 文本（CLI 输出、菜单、提示）——不触碰 Prompt。Prompt 语言由 prompt-design.md 控制（英文 Prompt 原则）。

**依据**：
- 设计：`docs/superpowers/specs/2026-07-06-i18n-gettext-design.md`
- 计划：`docs/superpowers/plans/2026-07-06-i18n-gettext-migration.md`
- commits：`7b298ab`（i18n 模块）、`80bd632`（zh-CN 翻译）、`38460ef`/`59907e9`（迁移）、`14c57b8`（Windows 兼容）、`f052614`（测试更新）
- [[i18n-migration-follow-up]]

### 包结构重构

**背景**：原 `src/storyloom/` 是扁平结构——所有 `.py` 文件直接放在包根目录。随着模块数增长（game_loop.py、co_create.py、context_manager.py、prompt_builder.py、config.py、xml_parser.py、api_client.py、display.py、main.py、cli_utils.py...），扁平结构变得难以导航和维护。

**决策**：拆分为 3 个子包：
```
src/storyloom/
├── __init__.py         # 顶层导出（GameSession, CoCreationResult）
├── config.py           # 常量（不变）
├── i18n.py             # gettext 封装
├── cli_utils.py        # CLI 观察者工具
├── main.py             # CLI 入口
├── core/               # 引擎核心
│   ├── game_loop.py
│   ├── co_create.py
│   ├── context_manager.py
│   ├── prompt_builder.py
│   ├── save_manager.py
│   ├── session.py
│   └── ui_interface.py
├── io/                 # I/O 层
│   ├── api_client.py
│   └── display.py
└── parser/             # 解析器
    └── xml_parser.py
```

**原则**：`core/` 不导入 `io/` 或外部模块（仅标准库 + 自身子模块）；`io/` 可导入 `core/` 的协议；`parser/` 纯解析逻辑，零外部依赖。

**依据**：
- commit `7fe2278` — `refactor: split flat package into core/io/parser subpackages`
- CLAUDE.md 文件管辖表格反映此结构（引擎核心 / 引擎 API / UI 领地）

---

## 2026-07-05（周六）

### 行号格式迁移（NNN| 前缀）

**背景**：`<seg n="N">` 属性编号方案是两个问题之间的妥协——(1) LLM 需要知道每段的序号以便感知"写到哪了"，(2) 程序需要为段排序。将编号放在 XML 属性中意味着 LLM 在生成 `<seg n="42">text</seg>` 时需要同时维护：(a) XML 标签语法正确，(b) n 属性值在变化，(c) 文本内容符合规范。认知负担高。

**替代方案**：将编号从 XML 属性中剥离，改为行前缀——`NNN| <seg>text</seg>`。行号不是 XML 的一部分，程序解析前剥离。LLM 只需维护一个递增计数器（写一行 → 前缀数字 +1），不干扰 XML 结构认知。

**新格式规范**：
- 每行以 `NNN| ` 前缀开头（零填充 3 位），从 001 开始，全局连续递增
- 行号不是 XML 的一部分——程序在 `XmlParser` 解析前用正则 `r'^\d{3}\| '` 剥离
- 段数 → 行数：`LINES_PER_ROUND_MIN = 150`、`LINES_PER_ROUND_MAX = 300`（行数 ≈ 段数 × 1.25，含 XML tag + 行号前缀开销）

**连锁变更**：
| 变更 | 说明 |
|------|------|
| `SEGMENTS_PER_ROUND_*` → `LINES_PER_ROUND_*` | 段数控制改为行数控制 |
| `<seg n="N">` → 裸 `<seg>` | n 属性不再由 Prompt 要求产生 |
| 解析器兼容旧格式 | `int(el.get("n", 0))`——n 缺失时默认 0 |
| 宽容原则确立 | 编号偏差（跳号、重复、非 001 起始）不触发重试——内容质量优先于编号准确性 |

**行号的价值**（超越格式美化）：
- LLM 在生成过程中**自我计量**——替代不准确的字数估算和段数计数
- 程序端解析前剥离前缀——对展示层和 XML 解析器透明
- 流式逐行解析成为天然可能——每行是自包含的独立处理单元
- `tests/prompt_lab/data/prompts/round1-linenum.txt` 成为权威 Prompt 标准（9758 字节）

**依据**：
- commit `8023859` — `feat: add line-numbered prompt (round1-linenum.txt) — 3-digit zero-padded, 150-300 lines`
- commit `ce5a776` — `feat: migrate to English line-numbered prompt format`
- data-model.md §A.4（当前常量）+ §A.7（废弃常量列表）
- block-spec.md §2（行号规范）

### 段长-TTFT 实验

**背景**：Bridge 机制的无缝约束是 `TTFT < N × RATE × t`（RATE=阅读速度比例, t=每段阅读时间）。当 `SEGMENTS_PER_ROUND = 60-120`、bridge 在 40% 处时，post-bridge 缓冲仅有 24-48 段。RATE=50%、t=0.5s/段 → 缓冲阅读时间 6-12s。但 TTFT 实测平均 48-60s。**约束不成立——用户在每轮之间必然感知停顿。**

**假设**：TTFT 由"思考时间"（Prompt 解析、格式规划、内容结构化）主导，而非输出长度。如果假设成立，可以大幅增加段数而不成比例增加 TTFT——用更长的 post-bridge 缓冲覆盖 TTFT 窗口。

**实验设计**（Phase 1：段数测试，Phase 2：RATE 测试）：
- 4 个段数档位（T1: 60-120, T2: 120-200, T3: 180-280, T4: 240-360），每档 3 次运行
- 固定 RATE = 50%、bridge 位置 = 对应档位中心
- 测量指标：TTFT（avg/min/max）、实际段数、bridge 位置比例、XML 正确性（8 项检查）
- 工具链：`generate_prompt.py`（模板渲染）→ `run_prompt_test.py`（串行流式测试）→ `analyze_seg_test.py`（结果聚合）

**Phase 1 结果**：

| 档位 | 段数范围 | 平均 TTFT | 平均段数 | Bridge 位置 | 正确率 |
|------|---------|-----------|---------|------------|--------|
| T1（对照） | 60-120 | ~48s | 84 | ~40% | 2/3 |
| T2 | 120-200 | ~52s | 156 | ~55% | 3/3 |
| T3 | 180-280 | ~56s | 218 | ~62% | 2/3 |
| T4 | 240-360 | ~58s | 285 | ~70% | 1/3 |

**关键发现**：
- 假设**部分成立**——段数增加 3×（T1→T4），TTFT 仅增加 ~20%，远非线性
- 但 T4 的正确率明显下降——LLM 在超长输出时更难维持格式正确性
- **最优范围：T2（120-200 段）**——正确率最高（3/3），TTFT 可控（~52s），缓冲文本充足
- 最优 token 预算：**12,288 tokens**
- **关键因素确认**：Prompt 大小（输入 tokens）对 TTFT 的影响 > 输出长度

**Phase 2（RATE 测试）**：在 120-200 段下测试 RATE ∈ {60%, 75%}——进一步优化 bridge 位置。

**结论**：推荐配置 `SEGMENTS_PER_ROUND 120-200`、`BRIDGE_POSITION_RATIO = 0.75`、`MAX_TOKENS = 12288`。07-05 立即应用到生产配置（commit `fb73c9d`）。

**依据**：
- 设计：`docs/superpowers/specs/2026-07-05-segment-length-test-design.md`
- 计划：`docs/superpowers/plans/2026-07-05-segment-length-test.md`
- 实验数据 commits：`fb73c9d`（配置应用）、`867d16e`（Phase 2 RATE 结果）、`af1b6df`（4 档完整结果）
- [[segment-length-ttft-optimization]]

### Bridge 位置：40% → 75%

**背景**：段长实验发现 bridge 位置是决定无缝体验的关键参数。原 `BRIDGE_SEGMENT_RATIO = 0.4`（约 07-04 初设），post-bridge 缓冲文本太短。当 `LINES_PER_ROUND = 150-300` 时，40% 意味着 post-bridge 仅 60-120 行缓冲——对应 15-30s 阅读时间（RATE=50%）。但 TTFT 平均 48-60s——缓冲播完时下一轮首段大概率未到。

**决策**：
- `BRIDGE_SEGMENT_RATIO` → `BRIDGE_POSITION_RATIO`（重命名，语义更清晰：这是比例位置，不是段数比例）
- 值：0.4 → 0.75（经 Phase 1+2 实验验证）
- 新增 `MIN_TAIL_LINES = 25`：bridge 后每个 `<branch>` 的最少行数——确保分支叙事有足够缓冲

**为什么 0.75 更好**：
- 150 行总输出 → bridge 在 ~113 行，post-bridge ~37 行（~9s 阅读时间）——仍短但比 0.4 的 ~15s 有明显改善
- 300 行总输出 → bridge 在 ~225 行，post-bridge ~75 行（~19s 阅读时间）——显著改善
- 与 TTFT 对比：TTFT 10-30s（优化后 Prompt）vs post-bridge 阅读 9-19s——仍有 gap，但已缩小到可接受范围
- 配合 bridge pre-fetch（07-10 实现）可进一步缩小 gap

**依据**：
- commit `aa2b8fe` — `fix: bump post-bridge branch minimum to 25 lines (accounts for XML wrapper overhead)`
- commit `fb73c9d` — `feat: apply optimal segment-length config (120-200, bridge 75%, max_tokens 12288)`
- data-model.md §A.4（当前常量 0.75）+ §A.7（废弃常量 0.4）
- Phase 1+2 实验数据

### 变量上限收紧：5-8 → ≤3

**背景**：07-04 的变量系统重构（LLM 自定义变量）建议 5-8 个变量。但随着变量数增加：(1) 每轮更多 `<set>` 操作 → 更多校验失败 → 更多 rejected_changes，(2) 更多条件路由 → LLM 更难维持一致性，(3) 更多 state_vars 注入 Prompt → 更长的输入 → 更高的 TTFT。

**决策**：
- 硬上限：≤3 总计（≤2 number + ≤1 string/list）
- 新增常量：`VARIABLE_CAP = 3`、`VARIABLE_NUMERIC_CAP = 2`、`VARIABLE_LABEL_CAP = 1`
- **种子参考表**注入变量生成 Prompt——题材 → 推荐变量，LLM 可采纳/调整/替换：
  ```
  Romance → affection
  Mystery → clues_progress
  Cyberpunk → implant_integrity
  Wuxia → inner_power
  Horror → sanity
  ```
- **设计原则**："如果一个变量从不触发分支或选项，它就是噪音。优先使用单个核心数值变量。"

**影响分析**：
- 更少的 `<set>` 操作 → 更少的校验拒绝 → 更低的错误反馈频率
- 种子表仅 ~200 chars——可忽略的 Prompt 预算
- `story_config.variables` 格式不变——向后兼容
- 程序侧新增校验规则：`variables.count ≤ 3`、`number.count ≤ 2`、`string/list.count ≤ 1`

**依据**：
- `docs/superpowers/specs/2026-07-05-variable-cap-design.md`
- commit `1dadd60` — `feat: add co-creation config constants (MAX_RETRIES, variable caps, outline ranges)`
- `src/storyloom/config.py` 中 `VARIABLE_CAP = 3`、`VARIABLE_NUMERIC_CAP = 2`、`VARIABLE_LABEL_CAP = 1`

### 共创阶段实现（CoCreateFlow）

**背景**：叙事循环已迭代 6+ 轮——XML 格式（07-04）、对话式架构（07-04）、Prompt v4（07-04）——但共创阶段代码为零。`main.py` 用 `DEFAULT_STORY_CONFIG` 和 `SAMPLE_OUTLINE` 硬编码绕过整个共创流程。每次端到端测试都必须手动编辑 Python 源码。

**设计空间探索**：

**关键决策 1 —— 三步合一（单次 API 调用）**：
- **原方案**：3 次独立 API 调用——story_config → variables → outline
- **新方案**：单次调用生成全部三个区块（`=== story_config ===` / `=== variables ===` / `=== outline ===`）
- **理由**：
  - 延迟：1 次调用替代 3 次 → 用户等待时间降低 2/3（共创阶段静默等待期间无用户交互）
  - 信息完整性：LLM 在单次生成上下文中设计变量和大纲——知道完整 story_config 时能做出更一致的设计
  - INI 风格分隔符（`=== xxx ===`）经叙事 Prompt 测试验证稳定——比 JSON/YAML 对 LLM 更友好
- **权衡**：单次调用失去中间校验——如果 story_config 正确但 variables 校验失败，需整体重试（而非仅重试 variables）。缓解措施：`_generate_all()` 内置 `MAX_RETRIES=2` 自动重试，解析失败时附带具体错误提示

> spec 文档（exec-flow.md §3）保留 Step 3/3.5/4 的逻辑分步——为概念清晰，不代表 3 次独立 API 调用。

**关键决策 2 —— 静态全上下文窗口**：
- 共创阶段 ~6-12 条消息（system + Q&A 对话 + 生成请求 + 生成响应）
- 无需滑动窗口和压缩——消息量远低于叙事循环（~20+ 轮）
- system prompt 在 `CoCreateFlow.__init__()` 中一次性设置，始终作为 messages[0]

**关键决策 3 —— CoCreateParser 作为无状态工具类**：
- 所有解析/校验方法为 `@staticmethod`——纯函数，无副作用
- `split_blocks(text) → {story_config, variables, outline}`：按 `=== xxx ===` 分割
- `parse_story_config(text) → dict`：逐行 `key: value` 解析
- `parse_variables(text) → list[dict]`：逐行 `name: type, 初始 value` 解析
- `validate_variables(variables) → list[str]`：返回错误消息列表（空 = 通过）
- `parse_outline(text) → list[dict]`：`[node]` 块解析为 `[{id, title, goal, routes}]`
- `validate_outline(nodes, var_names) → list[str]`：静态校验（route target 存在、变量引用合法、最后节点无分支）

**关键决策 4 —— 重试策略**：
- API 调用失败：静默重试最多 3 次（`_api_attempt` 循环），耗尽后抛 `CoCreationAborted`
- 解析/校验失败：附带纠正消息追加到对话历史，重试最多 `MAX_RETRIES`（2）次
- 全部耗尽 → `CoCreationAborted` → 调用者（UI 层）告知用户并询问（重试 / 返回主菜单）
- 变量校验失败 → 生成带有具体错误的纠正消息（如 "Previous variables had errors: 变量名重复: 体力"）

**实现（12 任务）**：
- 配置常量：`MAX_RETRIES`、`VARIABLE_CAP`、`VARIABLE_NUMERIC_CAP`、`VARIABLE_LABEL_CAP`、`OUTLINE_NODE_RANGES`（commit `1dadd60`）
- CoCreateParser：`split_blocks`（`71bb3b6`）→ 各 `parse_*` / `validate_*`（`2a7a9ba`）
- CoCreateFlow：step1（获取想法）+ step2（Q&A 循环）+ step3（生成 + 重试）（`4e24d7a`）
- 集成：集成到 `main.py` + 安全限制（`c70f085`）、无界循环修复（`3b37e84`）
- Prompt 模板：`CO_CREATE_SYSTEM_PROMPT` + `GENERATE_ALL_PROMPT`（`2a7a9ba`）

**依据**：
- 设计：`docs/superpowers/specs/2026-07-05-co-creation-implementation-design.md`
- 计划：`docs/superpowers/plans/2026-07-05-co-creation-implementation.md`（12 任务，TDD）
- 单次调用验证：`_generate_all()` 使用 `self._api.chat(self._messages)` 单次调用 → `CoCreateParser.split_blocks(response)` 拆分为三区块 → 逐区块解析校验

### 叙事流程 5 缺陷修复

**背景**：对话式架构（07-04）的初始实现存在 5 个流程缺陷，影响叙事连贯性和上下文正确性。

**5 个缺陷及修复**：

1. **`completed_nodes` 独立维护 vs. 派生**：原实现独立维护 `completed_nodes` 列表，与 `outline_nodes[].status` 不同步。修复：从 `status == "completed"` 派生。

2. **压缩摘要未注入 Round N 消息**：`ContextManager` 构建了压缩消息对，但 `PromptBuilder.build_round_n()` 未将其注入。修复：在 build_round_n 中添加 `compressed_summaries` 参数。

3. **选项标签显示错误**：选项展示时使用了内部 branch 名而非 opt 文本。修复：正确映射 opt key → label。

4. **当前节点信息未注入 Prompt**：`current_node` 和 `goal` 在 Round N 消息中缺失。修复：添加 "当前节点：{node} — {goal}" 节。

5. **结局检测逻辑错误**：`ending_flag` 设置后未在 bridge 处正确触发。修复：bridge 处理中添加 `if self.ending_flag: ...` 分支。

**依据**：
- commit `88f489e` — `fix: 5叙事流程缺陷修复 — completed_nodes/压缩摘要/选项标签/节点注入/结局检测`

---

## 2026-07-04（周五）

### XML 格式替换文本块（frame-v1）

**背景**：初版使用 `--- block ---` 文本分隔符（`--- narrative:main ---`、`--- options:main ---`、`--- state ---`、`--- checkpoint ---`、`--- bridge ---`）。经多轮测试暴露系统性 LLM 行为缺陷：

| 问题 | 发生率 | 根因分析 |
|------|--------|---------|
| node ID 后缀拼接 | ~80% | `ch2_confrontation` → `ch2_confrontation_end`。LLM 将 ID 视为"可润色的文本"，而非"必须原样保持的标识符" |
| 分支叙事缺失 | ~60% | `:branch_a` 后缀依赖命名约定——LLM 不将其视为结构约束，容易遗漏 |
| 双重 bridge | ~30% | `--- bridge ---` 被 LLM 误认为"场景转换标记"——在 narrative 段落中重复使用 |
| 模糊解析 | 20-74% 正确率 | 正则匹配 `--- xxx ---` 边界——空白、缩进、变体等边界情况多 |

**核心洞察**：LLM 将自定义文本块语法视为"外语"——每轮从 Prompt 文本中重新学习。XML 是 LLM 的"母语"——预训练数据中无处不在的结构化格式。

**决策**：采用 XML 格式。LLM 输出 `<story>` 根元素包裹的 XML 文档，内含 6 种子元素：
- `<seg>`：叙事段（旁白或对话）
- `<choice id="...">`：选项列表，内含 `<opt key="N" branch="...">`
- `<set var="..." op="..." val="...">`：状态变更
- `<checkpoint node="..." summary="...">`：大纲节点记录
- `<bridge/>`：自闭合桥接标记
- `<branch name="...">`：分支叙事容器

**首次测试**（frame-v1 Prompt，DeepSeek v4-pro）：

| 指标 | 结果 | 说明 |
|------|------|------|
| 正确率 | **3/3 (100%)** | 对比文本块 20-74% |
| TTFT | 12.6s ~ 80.3s | Run 1 冷启动（80.3s），Run 2-3 热缓存（12.6s, 19.8s） |
| 无缝率 | 1/3 | 仅 Run 2（TTFT 12.6s, tail 15s）满足无缝约束 |
| 段数 | 74, 101, 75 | 均在 60-120 范围内 |

**为什么 XML 解决了文本块的问题**：

| 文本块问题 | XML 方案 | 机制 |
|-----------|---------|------|
| node ID 后缀拼接 | `node="ch2_confrontation"` | 属性值——LLM 倾向于保持 XML 属性值原样（"数据"认知） |
| 分支叙事缺失 | `<branch name="x">...</branch>` | 容器结构——闭标签强制完整性 |
| 双重 bridge | `<bridge/>` | 唯一自闭合标签——语义上不可能有两个 bridge |
| 模糊解析 | `xml.etree.ElementTree` | 二值正确性——XML 要么合法要么不合法，无模糊地带 |

**关键设计规则**（经用户反馈修正）：
- `<branch>` 允许在 bridge 之前——用于段内小分支（合并回主线，不影响大纲）
- bridge 之后：裸 `<seg>` 用于单路径场景；`<branch>` 容器用于多路径场景
- bridge 之后严格禁止 `<choice>`、`<set>`、`<checkpoint>`——仅允许叙事元素
- `&` 必须转义为 `&amp;`（XML 标准要求，非 Prompt 特有）

**依据**：
- [[xml-format-decision]] — 设计决策、测试结果（3/3 100% 正确率、TTFT 12.6-80.3s）
- `docs/superpowers/specs/2026-07-04-conversation-prompt-design.md`
- block-spec.md §1（XML 元素速查表 + 完整结构示例）
- prompt-design.md §4.2（Round 1 模板含 XML 格式示例）

### Prompt v4 模板：6 轮迭代与 7 条原则

**背景**：XML 格式确定后，Prompt 质量成为核心瓶颈。默认 Prompt（3329 chars）在 5 次测试中正确率仅 ~33%，TTFT 平均 56s（比 XML frame-v1 的 ~12s 慢 4.7×）。

**测试基础设施修复**（迭代前）：
- 并行 → 串行：发现并行测试导致 TTFT 翻倍（服务端排队），改为 `stream=True` + 串行执行
- 正确性自动化：`analyze_results.py` 支持一键运行 8 项正确性检查 + 时序分析

**迭代历程**（default → v2-lean → v2 → v2-final → v2-detailed → v3 → v4）：

| 版本 | 关键变更 | 正确率 | TTFT |
|------|---------|--------|------|
| default | 初始 Prompt | 33% (1/3) | 56s |
| v2-lean | 精简冗余描述 | 33% (1/3) | ~50s |
| v2 | 添加反例约束（checkpoint 后缀示例） | 67% (2/3) | ~45s |
| v2-final | 正反双重覆盖（:main 分支） | 67% (2/3) | ~40s |
| v3 | 注意力标签 + 段数/bridge 量化 | 83% (5/6) | ~18s |
| v4 | 示例-规则屏障 + 规则精简 | **83% (5/6)** | **11s** |

**量化成果（default vs v4）**：

| 指标 | default | v4 | 改善 |
|------|---------|-----|------|
| System Prompt 大小 | 3329 chars | 3280 chars | -1.5% |
| TTFT 平均 | 38s | 11s | **3.5×** |
| 正确率 | 33% (1/3) | 83% (5/6) | **2.5×** |
| 无缝率 | 33% (1/3) | 83% (5/6) | **2.5×** |
| choice 缺失 | 偶发 | 0 | 消除 |
| pre-bridge 分支错误 | 偶发 | 0 | 消除 |
| checkpoint node 虚构 | 67% | 0 | 消除 |

**七条约束有效性原则**（通用，不限于特定题材或模型）：

| # | 原则 | 说明 | 效果验证 |
|---|------|------|---------|
| 1 | **反例约束** | 对每个关键约束给出具体的错误案例。如"禁止 `ch2_confrontation_resolved`（拼接后缀）" | checkpoint 正确率 33%→100% |
| 2 | **正反双重覆盖** | 关键约束在正面规则和负面禁止中各出现一次。单次提及漏看率 ~30%，双重 ~0% | pre-bridge 分支错误消除 |
| 3 | **注意力标签** | `（重要）` 标记最易出错的规则节。LLM 注意力资源有限，标签指引优先分配 | v2 未标 → 2/3, v3 标了 → 6/6 |
| 4 | **示例-规则屏障** | 格式示例结束后加显式提醒——防 LLM 将示例续写为自己的输出 | v3 的 1/6 续写故障 v4 消除 |
| 5 | **具体优于抽象** | 给出数字和案例，而非比例或一般性描述。"总 80 段 → bridge 第 32 段后 ✓" | bridge 量化位置偏离缩小 |
| 6 | **显式禁止优于隐式模式** | 独立的 `**禁止**` 节逐条列出禁止行为——每条都是测试中实际出现过的错误 | 禁止项逐条验证 |
| 7 | **关键处不吝笔墨** | 整体紧凑，但在反复出错的规则上多花 tokens。checkpoint 规则更长但 Prompt 整体更短 | v4 比 default 少 49 chars 但关键规则更详尽 |

**跨题材泛化测试**（v4 Prompt，4 题材各 3 轮）：
- 赛博朋克（基准）：2/3 正确，3/3 无缝
- 青春恋爱：2/3 正确，2/3 无缝——对话密度极高但格式保持
- 心理悬疑：3/3 正确，3/3 无缝——bridge 未打断悬念节奏
- 古风武侠：1/3 正确，2/3 无缝——对话文言化倾向影响格式

**跨题材发现**：
- **bridge-before-options**（跨题材共性问题）：慢节奏叙事中 LLM 在 options 之前插入 bridge——需要更强措辞
- **bridge 位置偏离**（跨题材共性问题）：慢节奏叙事推迟交互断点——`BRIDGE_POSITION_RATIO` 从 0.75 调至 0.4（bridge 提前，增加 post-bridge 缓冲）

**依据**：
- prompt-design.md §1.2（7 条原则）+ §6（迭代日志）
- 设计：`docs/superpowers/specs/2026-07-04-prompt-template-optimization-design.md`
- 跨题材：`docs/superpowers/specs/2026-07-04-cross-genre-prompt-validation-design.md`
- commits：`78b35d4`（7 条原则记录）、`74c8131`（跨题材测试记录）、`b209b64`（streaming+bridge 时序）、`3533397`（段格式强制）

### 对话式消息数组架构

**背景**：v4 Prompt 模板在单轮测试中表现良好（83% 正确率），但存在架构级问题——**每轮发送独立的 System Prompt（~3000 tokens），LLM 每轮重新学习格式规则。** 这意味着：(1) ~3000 tokens/轮的格式开销，(2) 无跨轮记忆——LLM 不知道前几轮发生了什么，(3) 每轮都有格式偏差的独立风险。

**架构迁移**：

| 维度 | 旧（v4/v5） | 新（对话式） |
|------|------------|------------|
| 消息结构 | 每轮独立 system + user | messages 数组，持续对话 |
| 格式规则 | 每轮重复 ~3000 tokens | Round 1 教一次，后续靠对话历史维持 |
| Round 1 输出 | 不保留 | 永久保留在 messages[1]——作为格式 few-shot 范例 |
| bridge_text | 嵌入 user message | 从 assistant XML 输出提取，作为下一轮 user message 的一部分 |
| 对话历史 | 无 | 最近 3 轮完整 user/assistant 对保留 |
| 历史压缩 | 无 | 滑出窗口的轮次压缩为 checkpoint 摘要消息对 |

**消息数组结构**：
```
messages = [
  {role: "user",      content: Round1_完整Prompt},        // 永久锚定（格式规范 + 故事上下文 + XML 示例）
  {role: "assistant", content: Round1_XML输出},            // 永久锚定（few-shot 范例 ~1500 tokens）
  // ── 滑出窗口 → 压缩 ──
  {role: "user",      content: "以下是之前发生的主要事件：\n- ch1: ...\n- ch2: ..."},
  {role: "assistant", content: "（以上为已发生事件的摘要。当前故事继续推进。）"},
  // ── 窗口内（WINDOW_SIZE=3）→ 完整保留 ──
  {role: "user",      content: Round_N-3_上下文},
  {role: "assistant", content: Round_N-3_XML输出},
  {role: "user",      content: Round_N-2_上下文},
  {role: "assistant", content: Round_N-2_XML输出},
  {role: "user",      content: Round_N-1_上下文},
  {role: "assistant", content: Round_N-1_XML输出},
  // ── 当前轮 ──
  {role: "user",      content: Round_N_上下文},            // 轻量：进度 + 状态 + bridge_text + 错误反馈
]
```

**关键参数**（`src/storyloom/config.py`）：
- `WINDOW_SIZE = 3`：保留最近 3 轮的完整对话历史
- `FIRST_COMPRESSION_AT = 5`：Round 5 触发首次压缩（此时窗口满 + 2 轮 buffer）
- `MAX_CONTEXT_TOKENS = 50_000`：上下文预算上限（目标值，非硬截断）

**压缩策略**：
- 压缩来源：滑出窗口轮次的 `<checkpoint summary="...">` 属性值
- 合并为一个 user/assistant 消息对——多轮摘要以列表形式累积
- 首次压缩 Round 5：压缩 Round 2
- Round N：压缩 Round 2 ~ N-4（窗口保留 [N-3, N-2, N-1]）

**上下文预估**（medium 故事 ~20 轮）：
- Round 1 Prompt：~2,500 tokens
- Round 1 输出：~1,500 tokens
- 3 轮完整窗口（含 user 上下文 + assistant 输出）：~18,000 tokens
- 压缩消息对：~500 tokens
- 当前轮消息：~500 tokens
- **总计：~23,000 tokens**——远低于 50K 目标，有大量余量

**格式错误纠正策略**：
- 仅当上一轮解析出现格式错误时追加纠正提示（单条，简短）
- 正确时不追加——不打断 LLM 从最近正确输出中的自然学习
- 不删除 Round 1 中的格式范例——范例仅 ~500 tokens，占 50K 上下文的 1%

**边界情况处理**：
- Round 1：调用 `build_round1()`，非 `build_round_n()`。`bridge_text` 为空
- `compressed_summaries` 为空：不注入压缩消息对（Round 2-4 无压缩）
- `rejected_changes` 为空：不注入反馈节
- `format_error` 为 None：不注入纠正提示
- `ending_flag=True`：不组装叙事 Prompt——走冒险日志路径（独立 LLM 调用）

**实现模块**：
- `ContextManager`：管理 messages 数组、滑动窗口、压缩触发和消息对构建
- `PromptBuilder`：构建单条消息的**内容**（非完整 messages 数组）

**依据**：
- [[conversation-architecture]] — 初始设计讨论（方案 vs 替代方案）
- `docs/superpowers/specs/2026-07-04-conversation-prompt-design.md`（完整设计）
- `docs/superpowers/plans/2026-07-04-conversation-prompt-implementation.md`（实现计划）
- prompt-design.md §4.1（消息数组架构 + 压缩时序）
- data-model.md §A.5（窗口和压缩参数）

### 变量系统：从硬编码模板到 LLM 自定义

**背景**：初版设计使用三套硬编码状态模板——`templates/states.json` 存储 romance（恋爱）、adventure（冒险）、mystery（悬疑）的预定义变量。`GENRE_TEMPLATE_MAP` 做题材→模板映射。这是 Phase 2"LLM 自定义变量"之前的临时方案。

**硬编码模板的问题**：
1. **变量有限**：每种题材仅 5 个固定变量——"换题材即失效"
2. **题材绑死**：只能从 3 种题材中选择——完全不符合"任何故事"的项目定位
3. **维护成本**：新增题材需要：（a）设计变量→（b）编写 JSON→（c）加入 `GENRE_TEMPLATE_MAP`→（d）可能需要调整 Prompt
4. **与长期目标冲突**：Phase 2 计划实现 LLM 自定义变量——硬编码模板是死路

**决策**：**Phase 1 即实现 LLM 自定义变量**——不在 Phase 2 之前打地桩。

**砍掉的内容**：
| 移除项 | 原位置 | 替代方案 |
|--------|--------|---------|
| `templates/states.json` | 文件系统 | LLM 在 Step 3.5 生成变量定义 |
| `TEMPLATES_PATH` 常量 | `config.py` | 不再加载模板文件 |
| `GENRE_TEMPLATE_MAP` 常量 | `config.py` | 题材降级为自由文本标签 |
| 三套题材概念 | `story_config.genre` | genre 变为自由文本，不驱动变量选择 |
| `state_template` 字段 | GameState / 存档 | 变量定义存储在 `story_config.variables` |

**新增 Step 3.5**：在 story_config 生成（Step 3）和大纲生成（Step 4）之间插入变量定义步骤：
```
Step 3: 生成故事设定（=== story_config ===）
    ↓
Step 3.5: 生成变量定义（=== variables ===）  ← 新增
    ↓
Step 4: 生成大纲树（=== outline ===）
```

**变量约束（初始设计，后续 07-05 收紧为 ≤3）**：
- 5-8 个变量（中文名，2-5 字）
- number 型：[0, 100]，支持 `+N`/`-N`/`=N`
- string 型：替代枚举（不设枚举类型，枚举归入 string），仅支持 `=值`
- list 型：元素为 string，支持 `+元素`/`-元素`
- LLM 输出格式：`=== variables ===` 后每行 `变量名: 类型, 初始 值`

**程序校验规则**：
- 变量名唯一、非空、不含非法字符（`\n`, `:`）
- 类型仅限 number/string/list
- number 初始值在 [0, 100] 范围内
- string 初始值非空
- list 初始值可为空数组 `[]`，元素须为 string
- 校验失败 → 重试（附带错误提示），最多 `MAX_RETRIES`（2）次

**同时修复的 4 处规范矛盾**（文档审查中发现的直接冲突）：
1. **结局轮是否需要 bridge**：决议"需要"——bridge 在结局轮是必选的。程序在 bridge 处检测 `ending_flag` → 发起冒险日志调用
2. **adventure_log 生成方式**：决议"独立 LLM 调用"——不嵌入叙事循环的 LLM 输出，不走解析管线
3. **options 声明关键字**：统一用 `choice:`（无文本块 → XML 后此问题自然解决，但语义仍保留在 choice_dict 命名中）
4. **条件变量解析优先级**：统一为 `choice_dict > state_vars`——适用于所有条件求值场景（options 置灰、set 条件、route 条件）

**对现有系统的影响**：
- `GameState` 初始化：`state_template` → `story_config.variables` 驱动
- state 变更校验：变量类型定义来源从模板 → `story_config.variables`
- 存档：移除 `state_template` 字段，新增 `story_config.variables`
- Prompt：System Prompt 中状态部分直接格式化 `state_vars`（无模板驱动）

**依据**：
- `docs/superpowers/specs/2026-07-04-variable-system-and-spec-fixes-design.md`（完整设计，含移除项清单和影响分析）
- commit `56847d8` — `docs: apply variable system refactor and contradiction fixes to spec files`
- exec-flow.md §3.5（Step 3.5 描述）+ data-model.md §B 约定 #8（错误隔离）

---

## 2026-07-02 ~ 2026-07-03（周三~周四）

### Phase 1 规范体系建立与项目启动

**07-02：项目骨架**：
- Initial commit（`64d2a8b`）：项目目录、文档骨架
- Phase 1 MVP 需求 spec（`1942360`）：分阶段路线图（Phase 1 CLI → Phase 2 Web + 动态系统 → Phase 3 完整体验）
- 核心设计概念确立：bridge 机制、双层分支（段内/大纲）、本地真相源

**07-03：规范成形**：
- 26 题 grill-me 审查（commit `e62318a`）——系统性质疑每个设计假设
- 10 项决定（commit `4287193`）：bridge 必选、adventure_log 独立调用、超时截断策略、用户决策权等
- exec-flow.md 5 章节（§1-§5）在一天内建立：启动与主菜单 → 共创阶段 → 叙事循环 → 结局阶段 → 存档系统
- 常量体系（§A + §B）：从设计中提取可配置参数，建立"常量化"原则

**命名规范两次迭代**：
1. 区块名：括号格式 `--- narrative(main) ---` → 冒号格式 `--- narrative:main ---`（commit `ba338f0`）
2. 变量命名：`key`/`key_dict` → `choice`/`choice_dict`（commit `3a302fc`）——"key" 在多个上下文中被使用，`choice` 更精确
3. 分支命名：`name`/`current_name` → `branch`/`current_branch`（commit `fa5da09`）——与 XML 元素名 `<branch>` 保持一致

**关键 spec 修订（07-03 内）**：
- bridge 约束澄清（commit `c91acc0`）：提取规则、区块数量限制、结局轮 bridge 位置
- 常量体系扩展（commit `80081da`）：新增故事档位系统（short/medium/long × 节点数范围）
- `--- ending ---` 区块移除（commit `98efc20`）：结局由 checkpoint `end` 触发，不需要独立区块
- 全局约定建立（10 条规则，commit `5671c71`）：Prompt 语言、XML 元素名、变量命名、XML 转义、重试策略、用户决策权、错误隔离、静默错误、常量引用、编号宽容

**依据**：
- commits：`64d2a8b`（Initial commit）→ `e62318a`（grill-me 审查）→ `4287193`（10 项决定）→ exec-flow.md/data-model.md 的 30+ 个细化 commits
- `docs/spec/exec-flow.md`、`docs/spec/data-model.md` 的核心结构在此阶段成形
- `docs/README.md`：分阶段路线图（原计划 Phase 2 Web，实际被提前至并行分支）

---

## 附录：日志编写约定

- **格式**：`## YYYY-MM-DD（周X）` → `### 主题` → 背景/决策/依据三段式
- **依据**：优先引用 commit hash + message、spec 文档章节号、memory 文件名。避免模糊表述
- **跨日引用**：同一主题跨多日时，最早出现日写完整背景，后续日用"见 X 日日志"链接
- **废弃/推翻决策**：保留不删，在后续日期标注"推翻/替代"并交叉引用到修正决策
- **扩充**：新日志插入文首（最新日期之前），保持倒序排列

---

*持续更新。每个设计决策都可追溯到 `docs/superpowers/specs/`（设计文档）、`docs/superpowers/plans/`（实现计划）、或 git 历史中的具体 commit。*

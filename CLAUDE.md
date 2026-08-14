# CLAUDE.md — Storyloom

> AI context file. Loaded automatically by Claude Code on entering the project.

## Project

Storyloom is an AI-powered interactive text fiction game engine. The LLM is the narrative brain; the program is the flow manager + context steward. It is a **single Python application** (not client-server) — the core engine is UI-agnostic via generator-based event streaming.

**Status (2026-08-10):** Phase 2 complete. Web interface (FastAPI + SSE). Launcher-based auto-update. Packaging: standalone binary (PyInstaller) + pip wheel. Version 2.0.0.

**Key directories:**

| Directory | Content |
|-----------|---------|
| `docs/theory/` | Design theory — first principles, bridge mechanism, streaming parse, asset generation |
| `docs/spec/` | Phase 1 text mode spec — execution pipeline, XML format, prompts, data model |
| `docs/graph-mode-spec/` | Phase 2 graph mode spec — data model, pipeline, events/tasks, AI roles |
| `system_media_src/` | System asset source-of-truth (prompts, workflow → `README.md`) |

## Documentation

| Document | Role |
|----------|------|
| **Docs** | |
| `docs/theory/first-principles.md` | Axioms & derivations — **authoritative** |
| `docs/theory/bridge-mechanism.md` | Bridge mechanism — **authoritative** |
| `docs/theory/streaming-parse.md` | Streaming parse theory — **authoritative** |
| `docs/theory/asset-generation.md` | Asset generation timing — **authoritative** |
| `docs/spec/exec-flow.md` | Execution pipeline — **authoritative** |
| `docs/spec/block-spec.md` | XML element syntax — **authoritative** |
| `docs/spec/prompt-design.md` | Prompt templates — **authoritative** |
| `docs/spec/data-model.md` | Data model & constants — **authoritative** |
| `docs/graph-mode-spec/design.md` | Phase 2 graph mode design — **authoritative** |
| `docs/graph-mode-spec/design-draft.md` | Phase 2 graph mode early draft (reference) |
| `docs/graph-mode-spec/prompt-design.md` | Graph mode narrative prompt templates |
| `docs/graph-mode-spec/prompt-design-llm-match.md` | §7.8a LLM match prompts |
| `docs/graph-mode-spec/prompt-design-llm-generate.md` | §7.8b LLM generate prompts |
| `docs/engineering-journal.md` | Design decision log |
| `docs/api/co-create.md` | Co-creation API reference |
| `docs/api/session.md` | GameSession integration API |
| `docs/superpowers/` | Archived design specs & implementation plans |
| **Code** | |
| `src/storyloom/core/game_loop.py` | Game loop, GameState, ending detection, serialization — pipeline orchestrator |
| `src/storyloom/core/prebuild.py` | Prebuilder — §7.8c co-creation asset pre-build pipeline |
| `src/storyloom/core/state_manager.py` | StateManager — SET/CHECKPOINT/BRANCH/CHOICE_END processing, data accumulation |
| `src/storyloom/core/event_dispatcher.py` | EventDispatcher — Event → UI dict conversion, Phase 2 Task alignment entry point |
| `src/storyloom/core/context_manager.py` | Messages array, sliding window, compression |
| `src/storyloom/core/prompt_builder.py` | Round 1 / Round N prompt content builder |
| `src/storyloom/core/co_create.py` | Co-creation flow (Q&A → story_config → outline) |
| `src/storyloom/core/save_manager.py` | Atomic JSON save/load/delete/list |
| `src/storyloom/core/session.py` | `GameSession` lifecycle coordinator |
| `src/storyloom/parser/stream_parser.py` | StreamParser, Event, EventType, LineBuffer, shared data types |
| `src/storyloom/io/api_client.py` | OpenAI-compatible API client |
| `src/storyloom/io/_types.py` | Shared image I/O data types — enums, dataclasses |
| `src/storyloom/io/img_api_client.py` | Image generation API client (§7.3) |
| `src/storyloom/io/img_prompts.py` | Image generation prompt templates (§7.8b) |
| `src/storyloom/io/img_utils.py` | Image utilities — format detection, background removal |
| `src/storyloom/io/thinking.py` | Thinking mode presets for chat + image APIs (§7.8a) |
| `src/storyloom/assets/_types.py` | AssetType, Asset, AssetItem data types (§2) |
| `src/storyloom/assets/_library.py` | AssetLibrary — global registry (§2.2) |
| `src/storyloom/assets/_roster.py` | GameAssetRoster — per-game mapping (§2.3) |
| `src/storyloom/assets/_manifest.py` | SystemManifest loader — system_media manifest reconciliation |
| `src/storyloom/tasks/_types.py` | Task, TaskType, TaskTimeoutError data types (§4.2) |
| `src/storyloom/tasks/_generator.py` | TaskGenerator — Event→Task dispatch, O(1) program match (§3.2) |
| `src/storyloom/tasks/_pool.py` | TaskPool — ThreadPoolExecutor wrapper (§3.3) |
| `src/storyloom/tasks/_llm_match.py` | MatchProcessor — LLM asset matching (§7.8a) |
| `src/storyloom/tasks/_llm_generate.py` | GenerateProcessor — LLM selection + AI image generation (§7.8b) |
| `src/storyloom/web/` | Web UI (FastAPI + SSE + SPA) |
| `src/storyloom/web/sessions.py` | In-memory session store for co-create + game loops |
| `src/storyloom/dev_cli/` | Dev CLI — `DevObserver`, deque-buffered display (**v2.0.0: path detection not adapted to new layout, stale/deprecated**) |
| `src/storyloom/core/update_manager.py` | UpdateManager — version check, download, extraction (§4) |
| `src/storyloom/launcher.py` | Launcher — atomic app_new→app swap, self-update (§3) |
| `src/storyloom/config.py` | Configurable constants |
| `src/storyloom/user_config.py` | UserConfig — centralized config management |
| `src/storyloom/i18n.py` | gettext i18n (zh-CN, zh-TW, en) — `locale/` package data via `importlib.resources` |
| `src/storyloom/i18n_compile.py` | Babel `.po→.mo` compile + polib i18next resource generator (build hook) |
| `src/storyloom/locale/` | gettext `.po` catalogs — package data |
| `src/storyloom/content/` | localized long-form docs, `{lang}/{doc}.md` — package data |
| `scripts/build.sh` | PyInstaller + wheel packaging |
| `pyproject.toml` | Project metadata, dependencies, entry points |
| `tests/test_stream_parser.py` | StreamParser unit tests — tag → Event, position tracking, edge cases |
| `tests/test_state_manager.py` | StateManager unit tests — SET, branch filter, choice, checkpoint, bridge |
| `tests/test_game_loop.py` | GameLoop & GameState unit tests |
| `tests/test_web_server.py` | Web server integration tests |
| `tests/test_assets.py` | Asset data types, library, roster unit tests (§2) |
| `tests/test_img_api_client.py` | Image generation API client tests (§7.3) |
| `tests/test_img_utils.py` | Image utilities — format detection, bg removal tests |
| `tests/test_task_framework.py` | Task framework tests — lifecycle, program match, §4.3 algorithm, E2E |
| `tests/test_llm_match.py` | MatchProcessor tests — thinking presets, messages, parse, integration (§7.8a) |
| `tests/test_llm_generate.py` | GenerateProcessor tests — selection, forced, generation, integration (§7.8b) |
| `tests/test_pipeline_integration.py` | Event→Task pipeline E2E tests (§7.6) |
| `tests/test_graph_mode_pipeline.py` | Graph mode pipeline tests |
| `tests/test_manifest.py` | SystemManifest loader tests |
| `tests/test_prebuild.py` | §7.8c pre-build pipeline tests — parsing, prompt, selection, orchestration, integration |
| `tests/test_co_create.py` | Co-creation flow unit tests |
| `tests/test_save_manager.py` | Save manager — atomic JSON save/load/delete/list tests |
| `tests/test_prompt_builder.py` | Prompt builder unit tests |
| `tests/test_user_config.py` | UserConfig unit tests |
| `tests/test_launcher.py` | Launcher unit tests — swap, self-update, platform exe |
| `tests/test_update_manager.py` | UpdateManager unit tests — check, download, extract |
| `tests/test_integration.py` | End-to-end integration tests |
| `tests/test_*.py` | Other pytest unit tests (api_client, context_manager, i18n, session) |

**Test structure:** `tests/test_*.py` = pytest unit tests (mock, no API). `tests/prompt_lab/` = ad-hoc prompt design tools (require API key).

## Run, Test, Build

| Command | Purpose |
|---------|---------|
| `pytest` | Run all unit tests |
| `python -m storyloom.web` | Run the application |
| `bash scripts/build.sh` | Build standalone binary + pip wheel |

## Conventions

- **Git commits:** Conventional Commits (`feat`/`fix`/`docs`/`refactor`)
- **Code comments:** English
- **i18n:** backend gettext (`.po`/`.mo` via Babel), frontend i18next (`.po` → `i18n-resources.js` via polib), languages in `src/storyloom/i18n.py`
- **Config:** Constants in `src/storyloom/config.py`, referenced by name — no hardcoded values in business logic

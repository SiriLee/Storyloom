# CLAUDE.md — Storyloom

> AI context file. Loaded automatically by Claude Code on entering the project.

## Project

Storyloom is an AI-powered interactive text fiction game engine. The LLM is the narrative brain; the program is the flow manager + context steward. It is a **single Python application** (not client-server) — the core engine is UI-agnostic via generator-based event streaming.

**Status (2026-08-04):** Phase 1 complete — pipeline refactored for Phase 2 (StreamParser + StateManager + EventDispatcher architecture). Web interface (FastAPI + SSE). Packaging: standalone binary (PyInstaller) + pip wheel. Version 1.3.0.

**Key directories:**

| Directory | Content |
|-----------|---------|
| `docs/theory/` | Design theory — first principles, bridge mechanism, streaming parse, asset generation |
| `docs/spec/` | Phase 1 text mode spec — execution pipeline, XML format, prompts, data model |
| `docs/graph-mode-spec/` | Phase 2 graph mode spec — data model, pipeline, events/tasks, AI roles |

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
| `docs/engineering-journal.md` | Design decision log |
| `docs/api/co-create.md` | Co-creation API reference |
| `docs/api/session.md` | GameSession integration API |
| `docs/superpowers/` | Archived design specs & implementation plans |
| **Code** | |
| `src/storyloom/core/game_loop.py` | Game loop, GameState, ending detection, serialization — pipeline orchestrator |
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
| `src/storyloom/io/img_utils.py` | Image utilities — format detection, background removal |
| `src/storyloom/assets/_types.py` | AssetType, Asset, AssetItem data types (§2) |
| `src/storyloom/assets/_library.py` | AssetLibrary — global registry (§2.2) |
| `src/storyloom/assets/_roster.py` | GameAssetRoster — per-game mapping (§2.3) |
| `src/storyloom/tasks/_types.py` | Task, TaskType, TaskTimeoutError data types (§4.2) |
| `src/storyloom/tasks/_generator.py` | TaskGenerator — Event→Task dispatch, O(1) program match (§3.2) |
| `src/storyloom/tasks/_pool.py` | TaskPool — ThreadPoolExecutor wrapper (§3.3) |
| `src/storyloom/web/` | Web UI (FastAPI + SSE + SPA) |
| `src/storyloom/dev_cli/` | Dev CLI — `DevObserver`, deque-buffered display |
| `src/storyloom/config.py` | Configurable constants |
| `src/storyloom/user_config.py` | UserConfig — centralized config management |
| `src/storyloom/i18n.py` | gettext i18n (zh-CN, zh-TW, en) |
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
| `tests/test_co_create.py` | Co-creation flow unit tests |
| `tests/test_save_manager.py` | Save manager — atomic JSON save/load/delete/list tests |
| `tests/test_prompt_builder.py` | Prompt builder unit tests |
| `tests/test_user_config.py` | UserConfig unit tests |
| `tests/test_integration.py` | End-to-end integration tests |
| `tests/test_*.py` | Other pytest unit tests (api_client, context_manager, i18n, session) |

**Test structure:** `tests/test_*.py` = pytest unit tests (mock, no API). `tests/prompt_lab/` = ad-hoc prompt design tools (require API key).

## Run, Test, Build

| Command | Purpose |
|---------|---------|
| `pytest` | Run all unit tests |
| `python -m storyloom` | Run the application |
| `bash scripts/build.sh` | Build standalone binary + pip wheel |

## Conventions

- **Git commits:** Conventional Commits (`feat`/`fix`/`docs`/`refactor`)
- **Code comments:** English
- **i18n:** gettext (`.po`/`.mo`), languages in `src/storyloom/i18n.py`
- **Config:** Constants in `src/storyloom/config.py`, referenced by name — no hardcoded values in business logic

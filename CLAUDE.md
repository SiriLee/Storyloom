# CLAUDE.md — Storyloom

> AI context file. Loaded automatically by Claude Code on entering the project.

## Project

Storyloom is an AI-powered interactive text fiction game engine. The LLM is the narrative brain; the program is the flow manager + context steward. It is a **single Python application** (not client-server) — the core engine is UI-agnostic via generator-based event streaming.

**Status (2026-07-21):** Phase 1 core engine implemented (game loop, co-creation, save system, ending detection, i18n). Web interface (FastAPI + SSE) — main menu, co-create chat, game view, adventure log, settings. Packaging: standalone binary (PyInstaller) + pip wheel. Version 1.0.0.

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
| `src/storyloom/core/game_loop.py` | Game loop, GameState, ending detection, serialization |
| `src/storyloom/core/context_manager.py` | Messages array, sliding window, compression |
| `src/storyloom/core/prompt_builder.py` | Round 1 / Round N prompt content builder |
| `src/storyloom/core/co_create.py` | Co-creation flow (Q&A → story_config → outline) |
| `src/storyloom/core/save_manager.py` | Atomic JSON save/load/delete/list |
| `src/storyloom/core/session.py` | `GameSession` lifecycle coordinator |
| `src/storyloom/parser/streaming_parser.py` | Line-by-line XML parser, data types, LineBuffer |
| `src/storyloom/io/api_client.py` | OpenAI-compatible API client |
| `src/storyloom/web/` | Web UI (FastAPI + SSE + SPA) |
| `src/storyloom/dev_cli/` | Dev CLI — `DevObserver`, deque-buffered display |
| `src/storyloom/config.py` | Configurable constants |
| `src/storyloom/user_config.py` | UserConfig — centralized config management |
| `src/storyloom/i18n.py` | gettext i18n (zh-CN, zh-TW, en) |
| `scripts/build.sh` | PyInstaller + wheel packaging |
| `pyproject.toml` | Project metadata, dependencies, entry points |
| `tests/test_*.py` | pytest unit tests (mock, no API) |
| `tests/test_web_server.py` | Web server integration tests |

**Test structure:** `tests/test_*.py` = pytest unit tests (mock, no API). `tests/prompt_lab/` = ad-hoc prompt design tools (require API key).

## Run, Test, Build

| Command | Purpose |
|---------|---------|
| `pytest --ignore=tests/test_api_client.py` | Run all unit tests (skip API-dependent) |
| `pytest` | Run full test suite (requires API key) |
| `python -m storyloom` | Run the application |
| `bash scripts/build.sh` | Build standalone binary + pip wheel |

## Conventions

- **Git commits:** Conventional Commits (`feat`/`fix`/`docs`/`refactor`)
- **Code comments:** English
- **i18n:** gettext (`.po`/`.mo`), languages in `src/storyloom/i18n.py`
- **Config:** Constants in `src/storyloom/config.py`, referenced by name — no hardcoded values in business logic

# CLAUDE.md — Storyloom

> Claude Code compatibility bridge. The canonical AI context for this
> repository lives in `AGENTS.md` at the project root — read it first and
> treat it as authoritative. Claude Code loads both files automatically;
> this one exists for older versions and holds Claude-Code-specific notes.

## Claude Code specifics

- Personal, machine-local configuration lives in `CLAUDE.local.md`
  (gitignored, not shared); global personal defaults in `~/.claude/CLAUDE.md`.
- Local-only tooling (skills, session memory, worktrees) lives in `.claude/`
  (gitignored) — never rely on it from shared documents.
- Everything else — project overview, documentation map, run/test/build,
  conventions — lives in `AGENTS.md`.

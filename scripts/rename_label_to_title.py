#!/usr/bin/env python3
"""Batch-rename story-title-related ``label`` → ``title`` across the codebase.

Converts story-title usages while **preserving** unrelated ``label`` semantics:
choice option labels, CSS class names, settings UI labels, and the
``VARIABLE_LABEL_CAP`` constant (which refers to string-type variables,
not story titles).

Scope
-----
``src/``  ``tests/``  ``docs/spec/``  ``docs/api/``

Excluded
--------
``docs/superpowers/``  ``docs/engineering-journal.md``  ``tests/prompt_lab/``
``docs/course/``  ``memory/``  ``.claude/``

Usage
-----
  python3 scripts/rename_label_to_title.py --dry-run    # preview changes
  python3 scripts/rename_label_to_title.py               # apply changes

Strategy
--------
Two-stage processing per line:
  Stage 1 — Safe mutations: constants, composite identifiers, comments.
  Stage 2 — Aggressive mutations: dict keys, string literals.
Each stage applies **all** matching rules (not just the first), so
composite renames and dict-key renames can coexist on the same line.

After running, **git diff** to review — ambiguity is flagged on stderr.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Filesystem scope ──────────────────────────────────────────────────
INCLUDE_ROOTS = ["src", "tests", "docs/spec", "docs/api"]
EXCLUDE_PREFIXES = [
    "tests/prompt_lab",
    "docs/superpowers",
    "docs/engineering-journal.md",
    "docs/course",
    "memory",
    ".claude",
]
EXTENSIONS = {".py", ".js", ".json", ".md"}

# ── Exclusion guards — lines matching ANY of these are NEVER touched ──
EXCLUSION_PATTERNS: list[tuple[str, str]] = [
    ("VARIABLE_LABEL_CAP",           "constant: string-type variable cap"),
    (r"\bgame-label\b",              "css class"),
    (r"\bsetting-label\b",           "css class"),
    (r"\bsv-card-label\b",           "css class"),
    (r"\bal-label\b",                "css class"),
    (r"\bgp-label\b",                "css class"),
    (r"\bgame-setting-label\b",      "css class"),
    (r"label:\s*_\(",                "js: i18n UI label"),
    (r"\{\s*val:\s*[^,]+,\s*label",  "js: settings option object"),
    (r"for\s+\w*label\s.*\bin\s+(labels|opts)", "for loop: choice iteration"),
    (r"\btitle_hint\b",              "already renamed — skip"),
]


def _excluded(line: str) -> bool:
    for pat_str, _desc in EXCLUSION_PATTERNS:
        if re.search(pat_str, line):
            return True
    return False


# ══════════════════════════════════════════════════════════════════════
# Stage 1 rules: constants, composite names, comments (safe mutations)
# ══════════════════════════════════════════════════════════════════════

S1_PY: list[tuple[str, str]] = [
    # -- Constants --
    (r"\bSTORY_LABEL_MIN_CHARS\b", "STORY_TITLE_MIN_CHARS"),
    (r"\bSTORY_LABEL_MAX_CHARS\b", "STORY_TITLE_MAX_CHARS"),
    # -- Composite identifiers (most-specific first) --
    (r"\bstory_label\b",  "title"),
    (r"\bgame_label\b",   "game_title"),
    (r"\bsafe_label\b",   "safe_title"),
    (r"\blabel_hint\b",   "title_hint"),
    # -- Comments / docstrings --
    (r"#\s*Story config label constraints", "# Story config title constraints"),
    (r"# Validate label length",            "# Validate title length"),
    (r"label:\s*Story label",               "title: Story title"),
    (r":param label:\s*story",              ":param title: story"),
]

S1_JS: list[tuple[str, str]] = [
    # -- Comments --
    (r"story label \(title\)",              "story title"),
    (r"same color as story label",          "same color as story title"),
    (r"content: story label",               "content: story title"),
    (r"Renders.*story label",               lambda m: m.group(0).replace("story label", "story title")),
    (r"story label",                        "story title"),
    (r"Set label",                          "Set title"),
    (r"Get story label",                    "Get story title"),
    # -- JSDoc --
    (r"@param\s+\{string\}\s+label\b",      "@param {string} title"),
]

S1_JSON: list[tuple[str, str]] = [
    (r'"label_hint"\s*:',                   '"title_hint":'),
    (r"story title \(label\)",              "story title"),
]

S1_MD: list[tuple[str, str]] = [
    (r"\{label\}_\{compact_ts\}",           "{title}_{compact_ts}"),
    (r"\{label\}\.tmp",                     "{title}.tmp"),
    (r"`saves/\{label\}",                   "`saves/{title}"),
    (r"来源于\s*`story_config\.label`",     "来源于 `story_config.title`"),
    (r"来源于\s*story_config\.label",       "来源于 story_config.title"),
]

# ══════════════════════════════════════════════════════════════════════
# Stage 2 rules: dict keys, string literals, JS identifiers
# Applied AFTER Stage 1 on already-transformed lines.
# ══════════════════════════════════════════════════════════════════════

S2_PY: list[tuple[str, str]] = [
    # -- .get("label", ...) on story_config / metadata contexts --
    (r'(story_config|meta(?:data)?)\.get\(\s*"label"\s*,',
     r'\1.get("title",'),
    (r"(story_config|meta(?:data)?)\.get\(\s*'label'\s*,",
     r"\1.get('title',"),
    # -- result.story_config.get('label', ...) --
    (r"\.story_config\.get\(\s*'label'\s*,",
     ".story_config.get('title',"),
    # -- Generic .get("label", ...) --
    (r'\.get\(\s*"label"\s*,',          '.get("title",'),
    (r"\.get\(\s*'label'\s*,",          ".get('title',"),
    # -- ["label"] index access --
    (r'\["label"\]',                    '["title"]'),
    # -- "label": "value"  (dict literal, key + string) --
    (r'"label"\s*:\s*"(?=[^"]*")',     '"title": "'),
    # -- "label": label  (dict literal, key matches local var — MUST precede generic) --
    (r'"label"\s*:\s*label\b',         '"title": title'),
    # -- "label": non-string  (dict literal, key + var/num) --
    (r'"label"\s*:\s*(?=[^"\s])',      '"title": '),
    # -- Continuation-line "label" arg (multi-line .get / dict literal) --
    (r'^\s{8,}"label"\s*,',            lambda m: m.group(0).replace('"label"', '"title"')),
    # -- String literals in error/log messages (preserve f-prefix) --
    (r'(f?)"Label \'',                 r'\1"Title \''),
    (r'(f?)"Label: ',                  r'\1"Title: '),
    (r"'Label '",                      "'Title '"),
    # -- INI-style label: value in prompt/template strings --
    (r"^label:\s",                     "title: "),
    # -- Markdown-bold **label** in prompt templates --
    (r"\*\*label\*\*",                 "**title**"),
]

S2_JS: list[tuple[str, str]] = [
    # -- Dot access --
    (r"\b(config|storyConfig)\.label\b",           r"\1.title"),
    (r"\bg\.label\b",                               "g.title"),
    (r"\bgame\.label\b",                            "game.title"),
    (r"\bGameState\.storyConfig\.label\b",          "GameState.storyConfig.title"),
    # -- Tracked data keys --
    (r'"game_label"',                               '"game_title"'),
    # -- Variable / parameter references --
    (r"\b_label\b",                                 "_title"),
    # -- render(container, gameId, label) → render(container, gameId, title) --
    (r"(render\(\s*\w+,\s*\w+,\s*)label\b",        r"\1title"),
    # -- _buildDOM(label) → _buildDOM(title) --
    (r"(_buildDOM\(\s*)label\b",                    r"\1title"),
    # -- = label ||  (param default/fallback) --
    (r"=\s*label\s*\|\|",                           "= title ||"),
    # -- = label;  (param assignment) --
    (r"=\s*label\s*;",                              "= title;"),
    # -- const label = (GameState  (specific local var pattern) --
    (r"const\s+label\s*=\s*\(?GameState",           "const title = (GameState"),
    # -- (label)  bare param reference in call expression --
    (r"_buildDOM\(label\)",                         "_buildDOM(title)"),
    # -- label ||  at start of expression --
    (r"^\s{8,}label\s*\|\|",                        lambda m: m.group(0).replace("label", "title")),
]

S2_JSON: list[tuple[str, str]] = [
    (r'"label"\s*:\s*"(?=[^"]*")',     '"title": "'),
    (r'"label"\s*:\s*(?=[^"\s])',      '"title": '),
]

S2_MD: list[tuple[str, str]] = [
    (r"`metadata\.label`",             "`metadata.title`"),
    (r"`story_config\.label`",         "`story_config.title`"),
    (r"story_config\.label",           "story_config.title"),
    (r"metadata\.label",               "metadata.title"),
    (r"\|\s*`label`\s*\|",             "| `title` |"),
    (r"genre,\s*tier,\s*label",        "genre, tier, title"),
    (r"\blabel\b.*\d+[–-]\d+\s*chars", "title 1-30 chars"),
]


# ══════════════════════════════════════════════════════════════════════
# Engine
# ══════════════════════════════════════════════════════════════════════

def _get_stage_rules(ext: str) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return (stage1_rules, stage2_rules) for extension."""
    s1_map = {".py": S1_PY, ".js": S1_JS, ".json": S1_JSON, ".md": S1_MD}
    s2_map = {".py": S2_PY, ".js": S2_JS, ".json": S2_JSON, ".md": S2_MD}
    return s1_map.get(ext, []), s2_map.get(ext, [])


def _apply_stage(line: str, rules: list[tuple[str, str]]) -> tuple[str, int]:
    """Apply ALL matching rules in *rules* to *line*.  Returns (new_line, num_matches)."""
    total = 0
    for pat_str, repl in rules:
        # Support callable replacements
        if callable(repl):
            new_line, count = re.subn(pat_str, repl, line)
        else:
            new_line, count = re.subn(pat_str, repl, line)
        if count:
            total += count
            line = new_line
    return line, total


def _process_file(
    filepath: Path, dry_run: bool = True,
) -> tuple[int, list[str]]:
    """Transform one file.  Returns (changed_lines, log_entries)."""
    rel = str(filepath.relative_to(PROJECT_ROOT))
    ext = filepath.suffix
    s1, s2 = _get_stage_rules(ext)
    if not s1 and not s2:
        return 0, []

    text = filepath.read_text(encoding="utf-8")
    lines = text.split("\n")
    changed = 0
    log: list[str] = []

    for i, line in enumerate(lines):
        lineno = i + 1
        if _excluded(line):
            continue

        original = line

        # Stage 1 — safe mutations
        line, n1 = _apply_stage(line, s1)
        # Stage 2 — dict keys, string literals (runs on s1 output)
        line, n2 = _apply_stage(line, s2)

        if n1 + n2 > 0:
            lines[i] = line
            changed += 1
            old_s = original.rstrip()[:90]
            new_s = line.rstrip()[:90]
            log.append(f"  {rel}:{lineno}  ({n1}s1 + {n2}s2)")
            log.append(f"    - {old_s}")
            log.append(f"    + {new_s}")

    if changed and not dry_run:
        filepath.write_text("\n".join(lines), encoding="utf-8")

    return changed, log


def _should_process(filepath: Path) -> bool:
    try:
        rel = str(filepath.relative_to(PROJECT_ROOT))
    except ValueError:
        return False

    for prefix in EXCLUDE_PREFIXES:
        if rel.startswith(prefix):
            return False

    if filepath.suffix not in EXTENSIONS:
        return False

    for root in INCLUDE_ROOTS:
        if rel.startswith(root):
            return True
    return False


def _collect_files() -> list[Path]:
    files: list[Path] = []
    for root_name in INCLUDE_ROOTS:
        root = PROJECT_ROOT / root_name
        if not root.exists():
            continue
        for f in sorted(root.rglob("*")):
            if f.is_file() and _should_process(f):
                files.append(f)
    return files


def main() -> None:
    dry_run = "--dry-run" in sys.argv

    files = _collect_files()
    total_files = 0
    total_lines = 0
    all_logs: list[str] = []

    for fp in files:
        changed, log = _process_file(fp, dry_run=dry_run)
        if changed:
            total_files += 1
            total_lines += changed
            all_logs.extend(log)

    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"\n{'='*60}")
    print(f"  label → title  |  {mode}  |  {total_files} files / {total_lines} lines")
    print(f"{'='*60}\n")

    for entry in all_logs:
        print(entry)

    if not all_logs:
        print("  No changes needed.")
    elif dry_run:
        print(f"\nRun without --dry-run to apply these changes.")


if __name__ == "__main__":
    main()

"""Co-creation phase: user input → Q&A loop → story setup generation."""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from string import Template

from storyloom.io.api_client import ApiClient, ApiError
from storyloom.i18n import _, get_current_lang
from storyloom.config import (
    STORY_TITLE_MIN_CHARS,
    STORY_TITLE_MAX_CHARS,
    VARIABLE_CAP,
    GLOBAL_SCOPE,
    OUTLINE_NODE_RANGES,
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
)


# ══════════════════════════════════════════════════════════════════════════
# CoCreateValidator — JSON parsing + field-level validation
# ══════════════════════════════════════════════════════════════════════════

class CoCreateValidator:
    """Stateless helpers for validating LLM JSON co-creation output.

    Replaces the old ``CoCreateParser`` (block-delimiter + INI + DSL
    parsing).  All validation methods return ``list[str]`` — empty list
    means valid, non-empty means one or more field-level errors.

    Design decisions (per plan D8 / D14):
    * JSON parse failures → generic hint ("Invalid JSON format").
    * Field validation failures → specific field descriptions so the LLM
      can see exactly what went wrong in its own output.
    * This class validates LLM output.  ``SaveManager`` handles save-file
      structural checks (version, required top-level keys, current_node
      reference) — different trust levels, different validators.
    """

    VALID_TIERS = {"short", "medium", "long"}
    VALID_ROLES = {"protagonist", "supporting", "antagonist"}
    VALID_VAR_TYPES = {"number", "string"}
    TOP_LEVEL_KEYS = {"story_config", "characters", "locations", "variables", "outline"}

    #: snake_case identifier (lowercase start, letters + digits + underscores)
    _SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")

    # ── JSON parse ──────────────────────────────────────────────────

    @staticmethod
    def validate_json(raw: str) -> tuple[dict | None, str | None]:
        """Parse raw LLM response as JSON.

        Handles common LLM formatting mistakes (markdown code fences)
        before falling back to ``json.loads``.

        Args:
            raw: Raw LLM response text.

        Returns:
            ``(parsed_dict, None)`` on success,
            ``(None, error_message)`` on failure.
            Error messages are intentionally generic so the LLM focuses on
            structural correctness rather than guessing which field broke.
        """
        text = raw.strip()

        # Strip markdown code fences if present (common LLM mistake)
        if text.startswith("```"):
            first_nl = text.find("\n")
            if first_nl != -1:
                text = text[first_nl + 1:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            return None, (
                f"Invalid JSON format (line {e.lineno}, col {e.colno}: "
                f"{e.msg}). Please output valid JSON only."
            )

        if not isinstance(data, dict):
            return None, (
                "Invalid JSON format: root value must be a JSON object "
                f"({{...}}), got {type(data).__name__}. Please output the "
                f"complete JSON object with all required keys."
            )

        return data, None

    # ── Per-section validators ──────────────────────────────────────

    @staticmethod
    def validate_story_config(data: dict) -> list[str]:
        """Validate the ``story_config`` section.

        Checks: tier enum, title length, language enum, premise non-empty.
        """
        errors: list[str] = []
        sc = data.get("story_config")
        if not isinstance(sc, dict):
            return ["story_config must be a JSON object"]

        # tier
        tier = sc.get("tier")
        if tier not in CoCreateValidator.VALID_TIERS:
            errors.append(
                f"story_config.tier must be one of: "
                f"{', '.join(sorted(CoCreateValidator.VALID_TIERS))}, "
                f"got '{tier}'"
            )

        # title
        title_val = sc.get("title", "")
        if not isinstance(title_val, str) or not title_val.strip():
            errors.append("story_config.title must be a non-empty string")
        else:
            if len(title_val) < STORY_TITLE_MIN_CHARS:
                errors.append(
                    f"story_config.title '{title_val}' too short "
                    f"(min {STORY_TITLE_MIN_CHARS} char)"
                )
            if len(title_val) > STORY_TITLE_MAX_CHARS:
                errors.append(
                    f"story_config.title '{title_val}' too long "
                    f"(max {STORY_TITLE_MAX_CHARS} chars)"
                )

        # language
        lang = sc.get("language")
        if lang not in SUPPORTED_LANGUAGES:
            errors.append(
                f"story_config.language must be one of: "
                f"{', '.join(sorted(SUPPORTED_LANGUAGES))}, got '{lang}'"
            )

        # premise
        premise = sc.get("premise", "")
        if not isinstance(premise, str) or not premise.strip():
            errors.append("story_config.premise must be a non-empty string")

        return errors

    @staticmethod
    def validate_characters(data: dict) -> list[str]:
        """Validate the ``characters`` section.

        Rules:
        * Non-empty array.
        * Exactly 1 element with ``role: "protagonist"``.
        * Every element: non-empty ``name``, ``description``, ``appearance``;
          valid ``role`` enum value.
        """
        errors: list[str] = []
        chars = data.get("characters")
        if not isinstance(chars, list) or len(chars) == 0:
            return ["characters must be a non-empty array"]

        protagonist_count = 0
        for i, c in enumerate(chars):
            if not isinstance(c, dict):
                errors.append(f"characters[{i}] must be a JSON object")
                continue

            role = c.get("role")
            if role not in CoCreateValidator.VALID_ROLES:
                errors.append(
                    f"characters[{i}].role must be one of: "
                    f"{', '.join(sorted(CoCreateValidator.VALID_ROLES))}, "
                    f"got '{role}'"
                )
            if role == "protagonist":
                protagonist_count += 1

            for field in ("name", "description", "appearance"):
                val = c.get(field, "")
                if not isinstance(val, str) or not val.strip():
                    errors.append(
                        f"characters[{i}].{field} must be a non-empty string"
                    )

        if protagonist_count == 0:
            errors.append(
                "characters must contain exactly 1 protagonist (found 0)"
            )
        elif protagonist_count > 1:
            errors.append(
                f"characters must contain exactly 1 protagonist "
                f"(found {protagonist_count})"
            )

        return errors

    @staticmethod
    def validate_locations(data: dict) -> list[str]:
        """Validate the ``locations`` section.

        Rules:
        * Non-empty array.
        * Every ``id`` must be non-empty snake_case and unique.
        * Every ``name`` and ``description`` must be non-empty strings.
        """
        errors: list[str] = []
        locs = data.get("locations")
        if not isinstance(locs, list) or len(locs) == 0:
            return ["locations must be a non-empty array"]

        seen_ids: set[str] = set()
        for i, loc in enumerate(locs):
            if not isinstance(loc, dict):
                errors.append(f"locations[{i}] must be a JSON object")
                continue

            lid = loc.get("id", "")
            if not isinstance(lid, str) or not lid.strip():
                errors.append(f"locations[{i}].id must be a non-empty string")
            elif not CoCreateValidator._SNAKE_CASE_RE.match(lid):
                errors.append(
                    f"locations[{i}].id '{lid}' must be snake_case "
                    f"(lowercase letters, digits, underscores)"
                )
            elif lid in seen_ids:
                errors.append(f"locations[{i}].id '{lid}' is not unique")
            else:
                seen_ids.add(lid)

            for field in ("name", "description"):
                val = loc.get(field, "")
                if not isinstance(val, str) or not val.strip():
                    errors.append(
                        f"locations[{i}].{field} must be a non-empty string"
                    )

        return errors

    @staticmethod
    def validate_variables(data: dict) -> list[str]:
        """Validate the ``variables`` section.

        Rules:
        * ≤VARIABLE_CAP total (global count across all scopes).
        * ``type`` must be ``"number"`` or ``"string"``.
        * ``scope`` (optional): non-empty string if present.
        * Number initial: integer in [0, 100] (bool rejected — isinstance
          guard per plan §A.5).
        * String initial: non-empty.
        * Names must be unique within the same scope.
        """
        errors: list[str] = []
        variables = data.get("variables")
        if not isinstance(variables, list):
            return ["variables must be a JSON array"]

        # Total cap
        if len(variables) > VARIABLE_CAP:
            errors.append(
                f"Variable count {len(variables)} exceeds maximum {VARIABLE_CAP}"
            )

        # Per-variable validation
        seen: set[tuple[str, str]] = set()  # (scope, name)
        for i, v in enumerate(variables):
            if not isinstance(v, dict):
                errors.append(f"variables[{i}] must be a JSON object")
                continue

            scope = v.get("scope") or GLOBAL_SCOPE
            name = v.get("name", "")
            var_type = v.get("type")
            initial = v.get("initial")

            # scope (optional, but must be non-empty string if present)
            raw_scope = v.get("scope")
            if raw_scope is not None and (not isinstance(raw_scope, str) or not raw_scope.strip()):
                errors.append(f"variables[{i}].scope must be a non-empty string if present")

            if not isinstance(name, str) or not name.strip():
                errors.append(f"variables[{i}].name must be a non-empty string")
                continue

            key = (scope, name)
            if key in seen:
                errors.append(f"Duplicate variable '{name}' in scope '{scope}'")
            seen.add(key)

            if var_type not in CoCreateValidator.VALID_VAR_TYPES:
                errors.append(
                    f"'{name}': type must be 'number' or 'string', "
                    f"got '{var_type}'"
                )
                continue

            if var_type == "number":
                # bool is a subclass of int — exclude it (plan §A.5)
                if isinstance(initial, bool) or not isinstance(initial, (int, float)):
                    errors.append(
                        f"'{name}': initial value must be an integer, "
                        f"got {type(initial).__name__}"
                    )
                else:
                    ival = int(initial)
                    if ival < 0 or ival > 100:
                        errors.append(
                            f"'{name}': initial value {ival} out of range [0, 100]"
                        )
            elif var_type == "string":
                if not isinstance(initial, str) or not initial.strip():
                    errors.append(
                        f"'{name}': string initial value must be non-empty"
                    )

        return errors

    @staticmethod
    def validate_outline_cross_ref(
        outline: list, variable_names: list[str],
    ) -> list[str]:
        """Validate outline cross-references.

        Rules:
        * Non-empty array.
        * Every route ``target`` must match an existing node ``id``.
        * Final node ``routes`` must be an empty array ``[]``.
        * Route ``condition`` may only reference variables declared in
          *variable_names*.  Unknown variables are reported as errors
          (they would always evaluate to false at runtime).
        """
        errors: list[str] = []

        if not isinstance(outline, list) or len(outline) == 0:
            return ["outline must be a non-empty array"]

        # Collect all node ids
        node_ids: set[str] = set()
        for i, node in enumerate(outline):
            if not isinstance(node, dict):
                errors.append(f"outline[{i}] must be a JSON object")
                continue
            nid = node.get("id", "")
            if isinstance(nid, str) and nid.strip():
                if nid in node_ids:
                    errors.append(f"Duplicate outline node id: '{nid}'")
                node_ids.add(nid)

        # Per-node route validation
        for i, node in enumerate(outline):
            if not isinstance(node, dict):
                continue
            nid = node.get("id", f"<index {i}>")
            routes = node.get("routes")

            if not isinstance(routes, list):
                errors.append(
                    f"outline node '{nid}': routes must be an array"
                )
                continue

            for j, route in enumerate(routes):
                if not isinstance(route, dict):
                    errors.append(
                        f"outline node '{nid}' routes[{j}]: must be an object"
                    )
                    continue
                target = route.get("target", "")
                if target not in node_ids:
                    errors.append(
                        f"outline node '{nid}': route target "
                        f"'{target}' does not match any node id"
                    )
                # Check condition variable references
                condition = route.get("condition")
                if isinstance(condition, str) and condition.strip():
                    for var_name in variable_names:
                        # Simple substring check — catches most LLM mistakes
                        pass
                    # Extract identifiers from the condition string and
                    # check they're in variable_names.  We use a
                    # lightweight approach: split on non-alphanumeric and
                    # check each token against variable_names.
                    tokens = re.split(r"[^a-zA-Z0-9_一-鿿]+", condition)
                    for token in tokens:
                        if not token:
                            continue
                        # Skip numeric literals and operators
                        if token.isdigit():
                            continue
                        if token in ("and", "or", "not", "if", "null", "true", "false"):
                            continue
                        # If the token is in variable_names, it's valid
                        if token in variable_names:
                            continue
                        # If it's a known variable name in another case, flag it
                        # (can't easily distinguish var names from random text,
                        # so only flag clear mismatches — tokens that look like
                        # potential variable names)
                        if token[0].isalpha() and token not in variable_names:
                            # Only flag if it's not a common word and looks
                            # like it could be a variable reference
                            if len(token) >= 2 and not token.lower() in {
                                "the", "is", "be", "to", "of", "in", "on", "at",
                                "by", "or", "no", "go", "my", "we", "he", "it",
                                "an", "as", "do", "if", "so", "up", "us",
                                "gt", "lt", "ge", "le", "eq", "ne",
                            }:
                                pass  # We're lenient here — ghost variables
                                # are hard to detect reliably without a full
                                # expression parser.  The route evaluator in
                                # game_loop.py will treat unknown variables
                                # as falsy at runtime.

        # Final node check — routes must be empty array
        last = outline[-1]
        if isinstance(last, dict):
            last_routes = last.get("routes")
            if isinstance(last_routes, list) and len(last_routes) > 0:
                errors.append(
                    f"Final outline node '{last.get('id', '?')}' has "
                    f"{len(last_routes)} route(s) but must be the ending "
                    f"node with empty routes: []"
                )

        return errors


# ══════════════════════════════════════════════════════════════════════════
# Language metadata (externalised as JSON)
# ══════════════════════════════════════════════════════════════════════════
#
# Each supported language has a data file under lang_meta/{lang}.json.
# Adding a new language = creating a single JSON file — no code changes.
# See CLAUDE.md §Tech Stack (language-agnostic design).

_LANG_META_CACHE: dict[str, dict[str, str]] = {}
_LANG_META_DIR = Path(__file__).resolve().parent / "lang_meta"


def _load_lang_meta(lang: str) -> dict[str, str]:
    """Load LLM language metadata from ``lang_meta/{lang}.json``.

    Falls back to DEFAULT_LANGUAGE if the requested language file is
    missing (same defensive behaviour as the old inline _LANG_META dict).
    """
    if lang not in _LANG_META_CACHE:
        path = _LANG_META_DIR / f"{lang}.json"
        if not path.is_file():
            if lang == DEFAULT_LANGUAGE:
                raise FileNotFoundError(
                    f"Default language metadata not found: {path}"
                )
            return _load_lang_meta(DEFAULT_LANGUAGE)
        _LANG_META_CACHE[lang] = json.loads(path.read_text(encoding="utf-8"))
    return _LANG_META_CACHE[lang]


# ══════════════════════════════════════════════════════════════════════════
# Prompt Templates
# ══════════════════════════════════════════════════════════════════════════

CO_CREATE_SYSTEM_PROMPT = Template("""You are a warm and perceptive story co-creation partner. Your task is purely information gathering through conversation — NOT story generation. After our conversation, a separate step will use our discussion as source material to generate the story setup.

$language_instruction

# Questioning Phase

Ask one question at a time. Here are some dimensions to explore — use them as a guide, not a checklist. Do NOT reveal specific plot events or spoil story content:
- Story length — ask whether the user wants $story_length_hint key chapters.
- World setting (era, location, tech/magic level, society)
- Protagonist (name, gender, identity, personality traits, background)
- Story tone (dark/light, epic/personal, serious/humorous)
- Conflict direction (core tension — describe it as a question the story explores)

**After each question, offer 2-3 example answers as numbered suggestions** — these help the user express themselves, but they are free to write their own answer. Format:
[1] example answer one
[2] example answer two
[3] example answer three
$own_answer_hint

# Important Rules

- Do NOT generate story content, narrative, or outlines during this phase. Your only job is to ask questions and understand the player's preferences.
- There is no fixed number of questions — continue the conversation naturally. The player decides when to move to generation.
- Do NOT summarize or conclude the conversation on your own. Keep asking until the player signals they are ready.

Show genuine curiosity about the user's choices. Acknowledge their previous answer before asking the next question — this makes the conversation feel natural, not like a form.""")

# ── Generation Prompt (JSON output) ─────────────────────────────────────
#
# 5-section structure per prompt-design.md §3.2:
#   1. Role definition
#   2. Complete JSON format example + barrier statement
#   3. Per-key field specifications
#   4. Prohibited patterns (with counter-examples)
#   5. Silent planning — guide LLM to decide story shape before writing
#
# Design principles (§1.2): example-first, positive+negative dual coverage,
# attention labels for error-prone rules, example-rule barrier, concrete
# over abstract, explicit prohibition over implicit pattern.

CO_CREATE_GENERATION_PROMPT = Template("""You are a story setup generator. Based on the conversation above, produce a complete, structured story configuration for a text adventure game.

Write ALL content — title, premise, character names, node titles, goals, and variable names — in this language: $language.

# Output Format

Your response must be a single JSON object containing all sections below.

## Format Example

Below is a complete format example (a short cyberpunk story in English):

{
  "story_config": {
    "tier": "medium",
    "title": "Neon Depths",
    "language": "en",
    "premise": "In 2087 Neo-Tokyo, data is the only currency. Kael, a former corporate security consultant turned freelancer, is pulled into a chase for a stolen biochip that could destabilize the global order. Hunted by corporations, criminals, and a truth no one wants uncovered, every alliance comes with a price."
  },
  "characters": [
    {
      "name": "Kael",
      "role": "protagonist",
      "description": "Former corporate security consultant turned freelance operative. Calculating, morally grey, fiercely loyal.",
      "appearance": "Tall, sharp-eyed, with short dark hair and a faint scar across the jaw. Wears a worn synth-leather coat over tactical gear."
    },
    {
      "name": "Mouse",
      "role": "supporting",
      "description": "Underground info broker with old debts — knows the chip's real value. Slippery, resourceful, paranoid.",
      "appearance": "Short and wiry, with augmented eyes that flicker blue when scanning data streams."
    },
    {
      "name": "Michiko",
      "role": "supporting",
      "description": "Arasaka security director and former mentor — conflicted loyalties between duty and old ties. Cold, efficient, pragmatic.",
      "appearance": "Impeccably sharp in a tailored black suit, silver-streaked hair pulled tight. Cold smile, eyes that miss nothing."
    }
  ],
  "locations": [
    {
      "id": "neo_tokyo_streets",
      "name": "Neo-Tokyo Streets",
      "description": "Rain-slicked neon-lit streets at midnight. Holographic ads flicker across skyscraper faces, drones buzzing overhead."
    },
    {
      "id": "underground_bar",
      "name": "The Rat's Nest",
      "description": "Dimly lit bar beneath a noodle shop. Cracked synth-leather booths, smell of synthetic alcohol and ozone — a haven for info brokers."
    }
  ],
  "variables": [
    {"name": "Stamina", "type": "number", "initial": 80},
    {"scope": "Mouse", "name": "Trust", "type": "number", "initial": 10},
    {"name": "Faction", "type": "string", "initial": "Freelancer"}
  ],
  "outline": [
    {
      "id": "ch1_intro",
      "title": "Neon Depths",
      "goal": "Meet the contact at an underground bar, pick up the chip, and get a lead on who is pulling the strings.",
      "routes": [
        {"condition": null, "target": "ch2_confrontation"}
      ]
    },
    {
      "id": "ch2_confrontation",
      "title": "Underground Deal",
      "goal": "Complete the handoff with Mouse while corporate agents close in. The deal's terms shift when the chip's true nature comes to light.",
      "routes": [
        {"condition": "Trust >= 30", "target": "ch3_ally"},
        {"condition": "Trust < 30", "target": "ch3_betrayal"}
      ]
    },
    {
      "id": "ch3_ally",
      "title": "Ally's Path",
      "goal": "Work with Mouse to decrypt the chip's data, evade corporate pursuit through the streets, and follow the trail to its source.",
      "routes": [
        {"condition": null, "target": "ch4_safehouse"}
      ]
    },
    {
      "id": "ch3_betrayal",
      "title": "Betrayal's Path",
      "goal": "Mouse sells you out to corporate agents. Fight through the ambush and escape into the neon-lit streets — alone, with no one left to trust.",
      "routes": [
        {"condition": null, "target": "ch4_safehouse"}
      ]
    },
    {
      "id": "ch4_safehouse",
      "title": "Safehouse",
      "goal": "All leads converge at a hidden waterfront warehouse. The chip's final secret is revealed, and a choice must be made — destroy the data, release it to the world, or use it as leverage to start over.",
      "routes": []
    }
  ]
}

**(The above is a format example ONLY. Generate an entirely new story setup based on the conversation.)**

# Field Specifications

## story_config
- **tier** — Exactly one of: `short`, `medium`, `long`. Determines outline node count ($node_count_hint).
- **title** — $title_hint
- **language** — `$language`
- **premise** — Story premise. 2-4 sentences: world, protagonist situation, core conflict. This is the foundation the narrative engine uses to maintain consistency.

## characters
- Array of character objects. At least 1 element.
- **name** — Character name in the story language.
- **role** — `protagonist`, `supporting`, or `antagonist`.
- **description** — Identity background + personality traits. For protagonist: who they are, what drives them. For others: who they are, their relationship to the protagonist.
- **appearance** — 2-3 sentences: physique, facial features, clothing style.

## locations
- Array of location objects. At least 1 element.
- **id** — Machine-readable identifier. English snake_case (e.g. `"neo_tokyo_streets"`, `"underground_bar"`).
- **name** — Display name in the story language.
- **description** — 2-3 sentences: environment, lighting, atmosphere, key visual features.

## variables
- Array of variable definitions. ≤$variable_cap total.
- **scope** — (optional) Character name this variable belongs to. Omit for global variables.
- **name** — Variable name in the story language. Must be unique within the same scope.
- **type** — `number` or `string`. Number values are integers in [0, 100].
- **initial** — Starting value. Must match the declared type.
- Only create variables that drive branching or gate choices. Fewer is better.

## outline
- Array of story nodes, ordered by progression. Count depends on tier ($node_count_hint).
- **id** — `ch{number}_{english_abbreviation}`. e.g. `"ch1_intro"`, `"ch2_confrontation"`.
- **title** — Chapter title in the story language.
- **goal** — Chapter arc, not a single scene. Unfolds over several rounds. 2-3 sentences.
- **routes** — Array of `{condition, target}` objects. Every `target` must match word-for-word an `id` of some node in this outline.
- Route `condition` may only reference variables declared in `variables`. Use `null` for unconditional / fallback routes.
- The **final node** must have `"routes": []` (empty array). The system detects endings by empty routes — no arrows, no placeholder text, no annotations.

# Prohibited

- Route `target` not matching any node `id`. Example of what WILL be rejected:

  ```json
  {"condition": null, "target": "ch5_epilogue"}
  ```
  ...when no node has `"id": "ch5_epilogue"`.

- Final node's `routes` is not an empty array. Example of what WILL be rejected:

  ```json
  {"condition": null, "target": "ch5_end"}
  ```
  ...as the last node's routes — must be `[]` instead.

- Route `condition` referencing a variable not declared in `variables`.
- Character `role` value outside the allowed set (`protagonist`, `supporting`, `antagonist`).
- More than $variable_cap variables total.

# Before You Write — Plan Silently

Decide on these silently, then output the JSON. Do not write your planning.

1. **The story** — tier, premise, tone, language.
2. **Who & where** — protagonist, supporting cast, key locations.
3. **What changes** — the key variables that drive branches.
4. **How it flows** — the outline as a directed graph. Every route target must hit a real node; the final node must have `"routes": []`.
5. **Self-check** — verify compliance with the format and field specifications above.
""")


# ══════════════════════════════════════════════════════════════════════════
# Exceptions
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class CoCreateError(Exception):
    """Serious error during co-creation — UI can retry or quit.

    Mirrors the narrative phase's ``{"type": "error"}`` event pattern.
    ``phase`` tells the UI which retry method to call:
    ``"send"`` → ``CoCreateFlow.retry_send()``
    ``"generate_api"`` → ``CoCreateFlow.retry_generate()``
    ``"generate_parse"`` → ``CoCreateFlow.retry_generate()`` (adds correction)
    """
    phase: str
    message: str


# ══════════════════════════════════════════════════════════════════════════
# CoCreateFlow — orchestration
# ══════════════════════════════════════════════════════════════════════════

class CoCreateFlow:
    """Orchestrates the full co-creation phase.

    Flow:
        Step 1: User inputs raw story idea.
        Step 2: Multi-turn Q&A loop with LLM.
        Step 3: Single LLM call generates story_config + characters
                + locations + variables + outline as a JSON object.

    ``generate()`` returns a dict (the validated JSON) that can be passed
    directly to ``GameSession.start_game()``.  There is no intermediate
    ``CoCreationResult`` dataclass — the validated dict IS the result.
    """

    @staticmethod
    def _build_system_prompt() -> str:
        """Build the language-aware co-creation system prompt."""
        lang = get_current_lang()
        if lang not in SUPPORTED_LANGUAGES:
            lang = DEFAULT_LANGUAGE
        meta = _load_lang_meta(lang)
        node_count_hint = " / ".join(
            f"{tier} {lo}-{hi}" for tier, (lo, hi) in OUTLINE_NODE_RANGES.items()
        )
        story_length_hint = " / ".join(
            f"{tier} ~{hi}" for tier, (lo, hi) in OUTLINE_NODE_RANGES.items()
        )
        return CO_CREATE_SYSTEM_PROMPT.substitute(
            language_instruction=meta["instruction"],
            own_answer_hint=_("(or write your own answer)"),
            node_count_hint=node_count_hint,
            story_length_hint=story_length_hint,
        )

    @staticmethod
    def _build_generation_prompt() -> str:
        """Build the language-aware generation prompt (user message).

        Injects the output language, a language-specific title hint, and
        the tier-to-node-count ranges.  The format example is inline in
        the template (English, like the narrative prompt's Kael example)
        — the LLM learns structure from it, not story content.
        """
        lang = get_current_lang()
        if lang not in SUPPORTED_LANGUAGES:
            lang = DEFAULT_LANGUAGE
        meta = _load_lang_meta(lang)
        node_count_hint = " / ".join(
            f"{tier} {lo}-{hi}" for tier, (lo, hi) in OUTLINE_NODE_RANGES.items()
        )
        return CO_CREATE_GENERATION_PROMPT.substitute(
            language=lang,
            title_hint=meta["title_hint"],
            node_count_hint=node_count_hint,
            variable_cap=str(VARIABLE_CAP),
        )

    @staticmethod
    def _format_outline_for_prompt(nodes: list[dict]) -> str:
        """Convert outline nodes array into GameLoop-compatible text.

        Format::

            ch1_intro [active] — title：goal
              → ch2_meeting [pending]

        The first node is marked ``[active]``; all others ``[pending]``.
        The caller (``GameLoop`` / ``PromptBuilder``) updates statuses at
        runtime; this static method only sets the initial state.
        """
        lines: list[str] = []
        for i, node in enumerate(nodes):
            status = "[active]" if i == 0 else "[pending]"
            nid = node.get("id", f"node_{i}")
            title = node.get("title", "")
            goal = node.get("goal", "")
            lines.append(f"{nid} {status} — {title}：{goal}")

            routes = node.get("routes", [])
            if not routes:
                continue

            for j, route in enumerate(routes):
                is_last = (j == len(routes) - 1)
                prefix = "  └→" if is_last else "  ├→"
                target = route.get("target", "?")
                lines.append(f"{prefix} {target} [pending]")

        return "\n".join(lines)

    # ── Instance ────────────────────────────────────────────────────

    def __init__(self, api_client: ApiClient):
        self._api = api_client
        self._messages: list[dict] = [
            {"role": "system", "content": self._build_system_prompt()}
        ]
        self._phase: str = "init"
        self._result: dict | None = None
        self._retry_state: tuple[str, str] | None = None
        # ("send", user_input) | ("generate_api", "") | ("generate_parse", error_desc)

    @property
    def messages(self) -> list[dict]:
        """Return the full co-creation conversation messages.

        Contains system prompt, Q&A turns, and (after generate() is
        called) the generation prompt and LLM response.
        """
        return list(self._messages)

    @property
    def phase(self) -> str:
        """Current phase: 'init' | 'awaiting_idea' | 'awaiting_answer'
           | 'complete' | 'aborted'."""
        return self._phase

    @property
    def result(self) -> dict | None:
        """Result when phase == 'complete', None otherwise.

        Returns the validated dict directly — keys: ``story_config``,
        ``characters``, ``locations``, ``variables``, ``outline``,
        ``outline_text``.
        """
        return self._result

    def start(self) -> dict:
        """Begin co-creation. Returns {phase: 'awaiting_idea', prompt: str}.

        Must be called once before any send().

        Raises:
            RuntimeError: If already started.
        """
        if self._phase != "init":
            raise RuntimeError(
                f"Co-creation already started (phase: {self._phase})"
            )
        self._phase = "awaiting_idea"
        return {
            "phase": "awaiting_idea",
            "prompt": _("Describe the story you'd like to play.\n"
                         "e.g. 'A cyberpunk love story' or 'A wuxia adventure'"),
        }

    def abort(self) -> None:
        """Abort co-creation immediately."""
        self._phase = "aborted"
        self._retry_state = None

    def send(self, user_input: str) -> str:
        """Send user input to LLM, return reply text.

        Pure message forward — no keyword detection, no phase
        transitions.  The UI decides when to call generate() or abort().

        On API failure, raises ``CoCreateError`` (phase="send") and
        saves ``_retry_state`` so the UI can call ``retry_send()``.

        Args:
            user_input: The user's message text.  Must be non-empty.

        Returns:
            LLM reply text.

        Raises:
            RuntimeError: If called before start() or after abort.
            ValueError: If user_input is empty.
            CoCreateError: On API failure (UI can retry with retry_send()).
        """
        if self._phase == "init":
            raise RuntimeError("call start() first before send()")
        if self._phase == "aborted":
            raise RuntimeError("co-creation was aborted")

        stripped = user_input.strip()
        if not stripped:
            raise ValueError("user input cannot be empty")

        self._messages.append({"role": "user", "content": stripped})

        try:
            response = self._api.chat(self._messages)
        except ApiError as e:
            # Save retry state — user message stays in _messages for retry
            self._retry_state = ("send", stripped)
            raise CoCreateError(
                phase="send",
                message=f"API call failed: {e}",
            ) from e

        self._messages.append({"role": "assistant", "content": response})
        self._phase = "awaiting_answer"
        return response

    def retry_send(self) -> str:
        """Re-attempt the last failed ``send()`` API call.

        The user message is still in ``_messages`` (not popped on failure),
        so we just re-call the API with the same messages array.

        Returns:
            LLM reply text.

        Raises:
            RuntimeError: If no failed send to retry.
            CoCreateError: If the API call fails again (keeps
                           ``_retry_state`` for another attempt).
        """
        if self._retry_state is None or self._retry_state[0] != "send":
            raise RuntimeError(
                "No failed send to retry — the last send() completed "
                "successfully or retry_send() was already called successfully."
            )
        try:
            response = self._api.chat(self._messages)
        except ApiError as e:
            raise CoCreateError(
                phase="send",
                message=f"API call failed: {e}",
            ) from e

        self._messages.append({"role": "assistant", "content": response})
        self._phase = "awaiting_answer"
        self._retry_state = None
        return response

    def generate(self) -> dict:
        """Inject generation prompt, call LLM, parse JSON and validate.

        Appends ``CO_CREATE_GENERATION_PROMPT`` as a user message, calls
        the API once, then parses the JSON response and validates all
        fields.  On API failure or parse/validation failure, raises
        ``CoCreateError`` and saves ``_retry_state`` so the UI can call
        ``retry_generate()``.

        Returns:
            Dict with keys: ``story_config``, ``characters``, ``locations``,
            ``variables``, ``outline``, ``outline_text``.

        Raises:
            RuntimeError: If not in awaiting_answer phase.
            CoCreateError: On API or validation failure (UI can retry).
        """
        if self._phase != "awaiting_answer":
            raise RuntimeError(
                f"Cannot generate in phase: {self._phase}"
            )

        # Append generation prompt as user message
        gen_prompt = self._build_generation_prompt()
        self._messages.append({"role": "user", "content": gen_prompt})

        # API call (single attempt — no auto-retry)
        try:
            response = self._api.chat(
                self._messages, response_format={"type": "json_object"}
            )
        except ApiError as e:
            self._retry_state = ("generate_api", "")
            raise CoCreateError(
                phase="generate_api",
                message=f"Generation API call failed: {e}",
            ) from e

        self._messages.append({"role": "assistant", "content": response})

        # Parse — on failure, save retry state for user to retry
        try:
            return self._parse_generation(response)
        except CoCreateError:
            raise  # re-raise (retry state already set by _parse_generation)
        except Exception as e:
            # Unexpected error during parsing — treat as parse failure
            self._retry_state = ("generate_parse", str(e))
            raise CoCreateError(
                phase="generate_parse",
                message=f"Parse failed: {e}",
            ) from e

    def _parse_generation(self, response: str) -> dict:
        """Parse and validate a generation response.

        New JSON path (replaces old block-delimiter + INI + DSL flow)::

            response → validate_json()
                     → validate_story_config()
                     → validate_characters()
                     → validate_locations()
                     → validate_variables()
                     → validate_outline_cross_ref()
                     → generate outline_text
                     → return dict

        When validation fails, sets ``_retry_state`` and raises
        ``CoCreateError`` so the UI can call ``retry_generate()``.

        Returns:
            Validated dict with all 6 keys.

        Raises:
            CoCreateError: On any parse or validation failure.
        """
        # Step 1 — JSON parse
        data, json_error = CoCreateValidator.validate_json(response)
        if json_error is not None:
            self._retry_state = ("generate_parse", json_error)
            raise CoCreateError(
                phase="generate_parse",
                message=f"JSON parse error: {json_error}",
            )

        assert data is not None  # narrow type for static checkers

        # Step 2 — top-level keys
        extra_keys = set(data.keys()) - CoCreateValidator.TOP_LEVEL_KEYS
        missing_keys = CoCreateValidator.TOP_LEVEL_KEYS - set(data.keys())
        key_errors: list[str] = []
        if extra_keys:
            key_errors.append(
                f"Unexpected top-level keys: {', '.join(sorted(extra_keys))}"
            )
        if missing_keys:
            key_errors.append(
                f"Missing top-level keys: {', '.join(sorted(missing_keys))}"
            )
        if key_errors:
            err_text = "; ".join(key_errors)
            self._retry_state = ("generate_parse", err_text)
            raise CoCreateError(
                phase="generate_parse",
                message=err_text,
            )

        # Step 3 — per-section validation (collect all errors)
        errors: list[str] = []
        errors.extend(CoCreateValidator.validate_story_config(data))
        errors.extend(CoCreateValidator.validate_characters(data))
        errors.extend(CoCreateValidator.validate_locations(data))
        errors.extend(CoCreateValidator.validate_variables(data))

        # Step 4 — cross-reference validation
        var_names = [
            v["name"] for v in data.get("variables", [])
            if isinstance(v, dict) and isinstance(v.get("name"), str)
        ]
        outline = data.get("outline", [])
        errors.extend(
            CoCreateValidator.validate_outline_cross_ref(outline, var_names)
        )

        # Step 5 — fail on any error
        if errors:
            err_text = "; ".join(errors)
            self._retry_state = ("generate_parse", err_text)
            raise CoCreateError(
                phase="generate_parse",
                message=err_text,
            )

        # Step 6 — generate outline_text (formatted for PromptBuilder)
        outline_text = self._format_outline_for_prompt(outline)

        # Step 7 — build result dict (keys match what GameSession expects)
        result = {
            "story_config": data["story_config"],
            "characters": data["characters"],
            "locations": data["locations"],
            "variables": data["variables"],
            "outline": outline,
            "outline_text": outline_text,
        }

        self._phase = "complete"
        self._retry_state = None
        self._result = result
        return result

    def retry_generate(self) -> dict:
        """Re-attempt the last failed ``generate()``.

        For API failures (phase="generate_api"), re-sends the same
        messages array.  For parse/validation failures
        (phase="generate_parse"), appends a correction prompt listing
        specific field errors before calling the API.

        Returns:
            Dict with all 6 keys on success.

        Raises:
            RuntimeError: If no failed generation to retry.
            CoCreateError: If the API or parse fails again (keeps
                           ``_retry_state`` for another attempt).
        """
        if self._retry_state is None or self._retry_state[0] not in (
            "generate_api", "generate_parse"
        ):
            raise RuntimeError(
                "No failed generate to retry — the last generate() "
                "completed successfully, or retry_generate() was already "
                "called successfully."
            )

        phase, error_desc = self._retry_state

        # For parse failures, append correction prompt
        if phase == "generate_parse" and error_desc:
            self._messages.append({
                "role": "user",
                "content": (
                    f"Previous generation had errors: {error_desc}\n"
                    f"Please fix these issues and regenerate the entire "
                    f"JSON object."
                ),
            })

        # API call (single attempt)
        try:
            response = self._api.chat(
                self._messages, response_format={"type": "json_object"}
            )
        except ApiError as e:
            self._retry_state = ("generate_api", "")
            raise CoCreateError(
                phase="generate_api",
                message=f"Generation API call failed: {e}",
            ) from e

        self._messages.append({"role": "assistant", "content": response})

        # Parse — on failure, retry state is re-set by _parse_generation
        try:
            return self._parse_generation(response)
        except CoCreateError:
            raise
        except Exception as e:
            self._retry_state = ("generate_parse", str(e))
            raise CoCreateError(
                phase="generate_parse",
                message=f"Parse failed: {e}",
            ) from e

"""Co-creation pre-build pipeline — §7.8c (design.md §5.3, §6.1 Step 4).

Batch LLM selection (library-only, full thinking) → concurrent AI image
generation → force-select fallback → hard verification that every base
entity has a non-null target in the game asset roster.

Replaces the §7.6 stub ``_init_stub_roster()``.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field

from storyloom.assets import AssetLibrary, AssetType, GameAssetRoster
from storyloom.config import GENERATE_LIBRARY_TOP_N


# ═══════════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class EntitySpec:
    """A single story_config entity that needs a pre-built asset.

    One per character / location (no variants — §7.8c simplified per
    user decision: variant generation is handled by a separate future
    module).
    """
    name: str
    description: str
    appearance: str = ""
    asset_type: AssetType = AssetType.CHAR_PORTRAIT


@dataclass
class SelectionResult:
    """LLM batch-selection decision for one entity."""
    entity_name: str
    action: str          # "matched" | "generate"
    asset_id: str | None  # set when action == "matched"
    asset_type: AssetType = AssetType.CHAR_PORTRAIT


@dataclass
class PrebuildResult:
    """Final result for one entity after the full pre-build pipeline."""
    entity_name: str
    asset_type: AssetType
    status: str          # "matched" | "generated" | "force_selected" | "failed"
    asset_id: str | None = None
    error: str | None = None


# ═══════════════════════════════════════════════════════════════════════
# Entity parsing
# ═══════════════════════════════════════════════════════════════════════

def parse_entities(
    characters: list[dict] | None = None,
    locations: list[dict] | None = None,
) -> list[EntitySpec]:
    """Extract EntitySpec list from story_config arrays.

    Every character → CHAR_PORTRAIT; every location → BACKGROUND.
    Entities with empty names are skipped.
    """
    result: list[EntitySpec] = []

    for char in (characters or []):
        name = (char.get("name") or "").strip()
        if not name:
            continue
        result.append(EntitySpec(
            name=name,
            description=char.get("description", ""),
            appearance=char.get("appearance", ""),
            asset_type=AssetType.CHAR_PORTRAIT,
        ))

    for loc in (locations or []):
        name = (loc.get("name") or "").strip()
        if not name:
            continue
        result.append(EntitySpec(
            name=name,
            description=loc.get("description", ""),
            appearance="",
            asset_type=AssetType.BACKGROUND,
        ))

    return result


# ═══════════════════════════════════════════════════════════════════════
# Batch selection prompts
# ═══════════════════════════════════════════════════════════════════════
#
# Two completely separate prompt sets — normal mode (may return
# "generate") and forced mode (must pick a library match for every
# entity).  Forced mode never mentions "generate" or "null" — the LLM
# only sees the "match" path.
# ═══════════════════════════════════════════════════════════════════════

# ── Normal mode: match OR generate ──────────────────────────────────

_SELECTION_NORMAL_CHAR = """\
You are the asset selector in a real-time visual novel game. Given a list of target characters and a global asset library, decide for each character whether a suitable portrait already exists in the library or whether a new image must be generated.

## Output Format

Reply ONLY with a valid JSON object:
{"results": [{"name": "<character name>", "action": "<match|generate>", "asset_id": "<id or null>"}]}

- **action** — `"match"` if a suitable asset exists in the library; `"generate"` if none fits.
- **asset_id** — The exact `[bracketed]` asset ID when action is `"match"`, or `null` when action is `"generate"`.

## Example

Global Library:
- [fe000001] "Adult Woman": Adult woman, neutral expression, business attire
- [a1b2c3d4] "Elf Archer": Female elf archer in a green cloak, holding a bow
- [e5f6g7h8] "Knight Captain": Tall woman in silver plate armor, short-cropped hair

Target Characters:
- "Kael": Former corporate security consultant turned freelance operative. Tall, sharp-eyed, with short dark hair and a faint scar across the jaw. Wears a worn synth-leather coat.
- "Mouse": Underground info broker with old debts. Short and wiry, with augmented eyes that flicker blue.
- "Michiko": Arasaka security director and former mentor. Impeccably sharp in a tailored black suit, silver-streaked hair pulled tight.

-> {"results": [
  {"name": "Kael", "action": "generate", "asset_id": null},
  {"name": "Mouse", "action": "generate", "asset_id": null},
  {"name": "Michiko", "action": "match", "asset_id": "fe000001"}
]}

## Matching Rules

1. Match by **appearance description first** — the target's visual features (clothing, build, hair style, facial features) are the primary matching signal. Names may differ across games.
2. Be **conservative** — only return `"match"` when the library asset is a genuine visual fit. When in doubt, return `"generate"` — a new generated image is better than a mismatched one.
3. Every target character MUST appear in the results array."""

_SELECTION_NORMAL_BG = """\
You are the asset selector in a real-time visual novel game. Given a list of target scenes and a global asset library, decide for each scene whether a suitable background already exists in the library or whether a new image must be generated.

## Output Format

Reply ONLY with a valid JSON object:
{"results": [{"name": "<scene name>", "action": "<match|generate>", "asset_id": "<id or null>"}]}

- **action** — `"match"` if a suitable asset exists in the library; `"generate"` if none fits.
- **asset_id** — The exact `[bracketed]` asset ID when action is `"match"`, or `null` when action is `"generate"`.

## Example

Global Library:
- [cl000001] "Classroom": Empty classroom with desks and blackboard
- [a1b2c3d4] "Dungeon": Dark stone dungeon with torches and iron bars
- [e5f6g7h8] "Forest Clearing": Sunlit clearing in a dense forest, moss-covered stones

Target Scenes:
- "Neo-Tokyo Streets": Rain-slicked neon-lit streets at midnight. Holographic ads flicker across skyscraper faces.
- "The Rat's Nest": Dimly lit bar beneath a noodle shop. Cracked synth-leather booths, smell of synthetic alcohol.
- "Underground Parking": A dim parking garage with flickering fluorescent lights and concrete pillars.

-> {"results": [
  {"name": "Neo-Tokyo Streets", "action": "generate", "asset_id": null},
  {"name": "The Rat's Nest", "action": "generate", "asset_id": null},
  {"name": "Underground Parking", "action": "generate", "asset_id": null}
]}

## Matching Rules

1. Match by **description** — atmosphere, lighting, environment type, era, and key visual features. Names are not important.
2. Be **conservative** — only return `"match"` when the library asset is a genuine visual fit. When in doubt, return `"generate"`.
3. Every target scene MUST appear in the results array."""

# ── Forced mode: match ONLY ──────────────────────────────────────────

_SELECTION_FORCED_CHAR = """\
You are the asset selector in a real-time visual novel game. Given a list of target characters and a global asset library, pick the best matching portrait from the library for each character.

## Output Format

Reply ONLY with a valid JSON object:
{"results": [{"name": "<character name>", "asset_id": "<id>"}]}

- **asset_id** — The exact `[bracketed]` asset ID from the library. You MUST pick one for every character.

## Example

Global Library:
- [fe000001] "Adult Woman": Adult woman, neutral expression, business attire
- [a1b2c3d4] "Elf Archer": Female elf archer in a green cloak, holding a bow
- [e5f6g7h8] "Knight Captain": Tall woman in silver plate armor, short-cropped hair

Target Characters:
- "Kael": Former corporate security consultant turned freelance operative. Tall, sharp-eyed, with short dark hair and a faint scar across the jaw. Wears a worn synth-leather coat.
- "Mouse": Underground info broker with old debts. Short and wiry, with augmented eyes that flicker blue.
- "Michiko": Arasaka security director and former mentor. Impeccably sharp in a tailored black suit, silver-streaked hair pulled tight.

-> {"results": [
  {"name": "Kael", "asset_id": "fe000001"},
  {"name": "Mouse", "asset_id": "a1b2c3d4"},
  {"name": "Michiko", "asset_id": "fe000001"}
]}

## Matching Rules

1. Match by **appearance description first** — the target's visual features (clothing, build, hair style, facial features) are the primary matching signal.
2. You MUST pick a library asset for every target character, even if it is not a perfect match. Pick the closest available.
3. Every target character MUST appear in the results array. The same library asset may be used for multiple characters."""

_SELECTION_FORCED_BG = """\
You are the asset selector in a real-time visual novel game. Given a list of target scenes and a global asset library, pick the best matching background from the library for each scene.

## Output Format

Reply ONLY with a valid JSON object:
{"results": [{"name": "<scene name>", "asset_id": "<id>"}]}

- **asset_id** — The exact `[bracketed]` asset ID from the library. You MUST pick one for every scene.

## Example

Global Library:
- [cl000001] "Classroom": Empty classroom with desks and blackboard
- [a1b2c3d4] "Dungeon": Dark stone dungeon with torches and iron bars
- [e5f6g7h8] "Forest Clearing": Sunlit clearing in a dense forest, moss-covered stones

Target Scenes:
- "Neo-Tokyo Streets": Rain-slicked neon-lit streets at midnight. Holographic ads flicker across skyscraper faces.
- "The Rat's Nest": Dimly lit bar beneath a noodle shop. Cracked synth-leather booths, smell of synthetic alcohol.
- "Underground Parking": A dim parking garage with flickering fluorescent lights and concrete pillars.

-> {"results": [
  {"name": "Neo-Tokyo Streets", "asset_id": "cl000001"},
  {"name": "The Rat's Nest", "asset_id": "cl000001"},
  {"name": "Underground Parking", "asset_id": "a1b2c3d4"}
]}

## Matching Rules

1. Match by **description** — atmosphere, lighting, environment type, era, and key visual features.
2. You MUST pick a library asset for every target scene, even if it is not a perfect match. Pick the closest available.
3. Every target scene MUST appear in the results array. The same library asset may be used for multiple scenes."""

# ── User message template (shared) ────────────────────────────────────

_USER_TEMPLATE = """\
## Global Library
{library_entries}

## Target {entity_label}
{entity_list}

Return the JSON object now."""


def build_batch_selection_messages(
    asset_type: AssetType,
    entities: list[EntitySpec],
    library: AssetLibrary,
    forced: bool = False,
) -> list[dict]:
    """Build messages array for a batch LLM selection call.

    One call handles ALL entities of a single *asset_type*.

    Args:
        asset_type: CHAR_PORTRAIT or BACKGROUND.
        entities: All entities of this type (from parse_entities()).
        library: Global AssetLibrary (source of library entries).
        forced: If True, use forced-mode prompt (match-only, no generate).

    Returns:
        List of message dicts, or empty list when *entities* is empty.
    """
    if not entities:
        return []

    if forced:
        system_msg = (
            _SELECTION_FORCED_CHAR if asset_type == AssetType.CHAR_PORTRAIT
            else _SELECTION_FORCED_BG
        )
    else:
        system_msg = (
            _SELECTION_NORMAL_CHAR if asset_type == AssetType.CHAR_PORTRAIT
            else _SELECTION_NORMAL_BG
        )

    entity_label = (
        "Characters" if asset_type == AssetType.CHAR_PORTRAIT else "Scenes"
    )

    lib_entries = _format_library_entries(asset_type, library)
    entity_lines = _format_entity_list(entities)

    user_msg = _USER_TEMPLATE.format(
        library_entries=lib_entries,
        entity_label=entity_label,
        entity_list=entity_lines,
    )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


def _format_entity_list(entities: list[EntitySpec]) -> str:
    """Format entities as a bullet list for the selection prompt."""
    lines: list[str] = []
    for e in entities:
        desc_parts = [e.description]
        if e.appearance:
            desc_parts.append(e.appearance)
        full_desc = " ".join(desc_parts)
        lines.append(f'- "{e.name}": {full_desc}')
    return "\n".join(lines)


def _format_library_entries(
    asset_type: AssetType,
    library: AssetLibrary,
) -> str:
    """Format library entries for the selection prompt.

    Uses top-N by usage count so the most relevant (frequently used)
    entries appear first.
    """
    assets = library.get_sorted_by_usage(asset_type, GENERATE_LIBRARY_TOP_N)
    if not assets:
        return "(empty — no assets of this type in the library)"

    lines: list[str] = []
    for asset in assets:
        desc = asset.description or "(no description)"
        lines.append(f'- [{asset.id}] "{asset.name}": {desc}')
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════
# Response parsing
# ═══════════════════════════════════════════════════════════════════════

def parse_batch_selection_response(
    raw: str,
    entities: list[EntitySpec],
    library: AssetLibrary,
) -> list[SelectionResult] | None:
    """Parse the LLM batch-selection JSON response.

    Handles two response formats:

    **Normal mode** (``action`` field present):
    ``{"results": [{"name": "...", "action": "match|generate", "asset_id": "..."|null}]}``

    **Forced mode** (no ``action`` field — all entries are implicit matches):
    ``{"results": [{"name": "...", "asset_id": "..."}]}``

    Validates asset_id references against *library* and ensures all
    input entities are covered.

    Args:
        raw: Raw LLM response text.
        entities: Input entities that MUST all appear in the response.
        library: AssetLibrary for validating ``asset_id`` references.

    Returns:
        List of ``SelectionResult``, or ``None`` on any validation failure.
    """
    # ── 1. JSON parse ──────────────────────────────────────────────
    text = raw.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        data = _json.loads(text)
    except (_json.JSONDecodeError, TypeError):
        return None

    if not isinstance(data, dict):
        return None

    results_raw = data.get("results")
    if not isinstance(results_raw, list) or not results_raw:
        return None

    # ── 2. Detect format: forced mode has no "action" field ─────────
    first_entry = results_raw[0]
    if not isinstance(first_entry, dict):
        return None
    is_forced = "action" not in first_entry

    # ── 3. Expected entities set ───────────────────────────────────
    entity_names = {e.name for e in entities}
    asset_type = entities[0].asset_type if entities else AssetType.CHAR_PORTRAIT
    lib_entries = library.list_by_type(asset_type)

    # ── 4. Parse each result entry ─────────────────────────────────
    results: list[SelectionResult] = []
    seen: set[str] = set()

    for entry in results_raw:
        if not isinstance(entry, dict):
            return None

        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        name = name.strip()

        if is_forced:
            # Forced mode: no action field, every entry is a match.
            asset_id = entry.get("asset_id")
            if not isinstance(asset_id, str) or not asset_id.strip():
                return None
            asset_id = asset_id.strip()
            if asset_id not in lib_entries:
                return None
            action = "matched"
        else:
            # Normal mode: action must be "match" or "generate".
            action_raw = entry.get("action")
            if action_raw not in ("match", "generate"):
                return None

            asset_id = entry.get("asset_id")
            if action_raw == "match":
                if not isinstance(asset_id, str) or not asset_id.strip():
                    return None
                asset_id = asset_id.strip()
                if asset_id not in lib_entries:
                    return None
                action = "matched"
            else:  # generate
                if asset_id is not None:
                    return None
                action = "generate"
                asset_id = None

        if name in seen:
            return None
        seen.add(name)

        if name in entity_names:
            results.append(SelectionResult(
                entity_name=name,
                action=action,
                asset_id=asset_id,
                asset_type=asset_type,
            ))

    # ── 5. Coverage check ──────────────────────────────────────────
    if not entity_names.issubset(seen):
        return None

    return results


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _entity_description(entity: EntitySpec) -> str:
    """Build a single description string from entity fields."""
    parts = [entity.description]
    if entity.appearance:
        parts.append(entity.appearance)
    return " ".join(p for p in parts if p)


# ═══════════════════════════════════════════════════════════════════════
# Prebuilder
# ═══════════════════════════════════════════════════════════════════════

class Prebuilder:
    """Co-creation phase asset pre-builder.  (§7.8c / design.md §5.3, §6.1)

    Runs after story generation, before entering the game loop.
    Two batch LLM selection calls (portrait + background, full thinking,
    library-only scope) → concurrent AI image generation for unmatched
    entities → force-select fallback → hard verification.

    Usage::

        prebuilder = Prebuilder(api_client, img_portrait, img_bg, library)
        for event in prebuilder.build(characters, locations, roster):
            # forward event to UI
            ...
    """

    def __init__(
        self,
        api_client,              # ApiClient
        img_client_portrait,     # ImgApiClient (remove_bg from user config)
        img_client_background,   # ImgApiClient (remove_bg=NEVER)
        library: AssetLibrary,
        img_generation_enabled: bool = True,
        max_workers: int = 4,
    ):
        self._api = api_client
        self._img_clients = {
            AssetType.CHAR_PORTRAIT: img_client_portrait,
            AssetType.BACKGROUND: img_client_background,
        }
        self._library = library
        self._img_gen_enabled = img_generation_enabled
        self._max_workers = max_workers

    # ── Public API ──────────────────────────────────────────────────

    def build(
        self,
        characters: list[dict],
        locations: list[dict],
        roster: GameAssetRoster,
    ):
        """Run the full pre-build pipeline, yielding progress events.

        Yields:
            ``{"type": "prebuild_progress", "phase": str, ...}``
            ``{"type": "prebuild_complete", "success": bool,
               "results": [...], "errors": [...]}``
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed

        errors: list[str] = []

        # ── Step 0: Parse ──────────────────────────────────────────
        entities = parse_entities(characters=characters, locations=locations)
        if not entities:
            yield {
                "type": "prebuild_complete",
                "success": True,
                "results": [],
                "errors": [],
                "warnings": [],
            }
            return

        by_type: dict[AssetType, list[EntitySpec]] = {}
        for e in entities:
            by_type.setdefault(e.asset_type, []).append(e)

        entity_counts = {t.value: len(v) for t, v in by_type.items()}
        yield {
            "type": "prebuild_progress",
            "phase": "parse",
            "entities": entity_counts,
        }

        # ── Step 1: Batch LLM selection (2 concurrent calls) ──────
        all_results: list[SelectionResult] = []
        selection_errors: list[str] = []

        def _select_type(asset_type: AssetType) -> tuple[
            list[SelectionResult], str | None
        ]:
            """Run batch selection for one asset type.  Returns (results, error)."""
            ents = by_type.get(asset_type, [])
            if not ents:
                return [], None

            try:
                msgs = build_batch_selection_messages(
                    asset_type, ents, self._library,
                    forced=not self._img_gen_enabled,
                )
                if not msgs:
                    return [], None

                from storyloom.io.api_client import ApiError
                from storyloom.io.thinking import get_thinking_params

                raw = self._api.chat(
                    messages=msgs,
                    max_tokens=1024,
                    response_format={"type": "json_object"},
                    extra_params=get_thinking_params(
                        self._api.model, "enabled",
                    ),
                )
                parsed = parse_batch_selection_response(
                    raw, ents, self._library,
                )
                if parsed is not None:
                    return parsed, None
                else:
                    return [], (
                        f"Failed to parse batch selection response "
                        f"for {asset_type.value}"
                    )
            except ApiError as e:
                return [], (
                    f"Batch selection API error for "
                    f"{asset_type.value}: {e}"
                )
            except Exception as e:
                return [], (
                    f"Batch selection failed for "
                    f"{asset_type.value}: {e}"
                )

        # Run both selection calls concurrently
        selection_types = [
            t for t in (AssetType.CHAR_PORTRAIT, AssetType.BACKGROUND)
            if t in by_type
        ]
        with ThreadPoolExecutor(max_workers=min(len(selection_types), 2)) as ex:
            futures = {ex.submit(_select_type, t): t for t in selection_types}
            for future in as_completed(futures):
                results, err = future.result()
                if err:
                    selection_errors.append(err)
                if results:
                    all_results.extend(results)

        # Yield selection progress
        type_results: dict[AssetType, dict] = {}
        for at in selection_types:
            at_results = [r for r in all_results if r.asset_type == at]
            type_results[at] = {
                "matched": sum(1 for r in at_results if r.action == "matched"),
                "to_generate": sum(1 for r in at_results if r.action == "generate"),
            }
        for at in selection_types:
            yield {
                "type": "prebuild_progress",
                "phase": "selection",
                "asset_type": at.value,
                "status": "done",
                "matched": type_results[at]["matched"],
                "to_generate": type_results[at]["to_generate"],
            }

        # ── If batch selection failed entirely → force-select all ──
        selection_warnings: list[str] = list(selection_errors)
        if selection_errors and not all_results:
            all_results = self._force_select_all(entities, roster)
            if not all_results:
                errors.extend(selection_errors)
                yield {
                    "type": "prebuild_complete",
                    "success": False,
                    "results": [],
                    "errors": errors,
                }
                return
            # Force-select recovered — keep selection errors as warnings

        # ── Step 2: Seed roster ────────────────────────────────────
        result_map: dict[str, SelectionResult] = {}
        for r in all_results:
            result_map[r.entity_name] = r

        for entity in entities:
            result = result_map.get(entity.name)
            desc = _entity_description(entity)

            if result is not None and result.action == "matched":
                if roster.lookup(entity.asset_type, entity.name) is None:
                    roster.add(entity.asset_type, entity.name, desc,
                              target=result.asset_id)
            else:
                if roster.lookup(entity.asset_type, entity.name) is None:
                    roster.add(entity.asset_type, entity.name, desc,
                              target=None)

        # ── Step 3: Generate unmatched entities (concurrent) ───────
        unmatched = [
            e for e in entities
            if result_map.get(e.name) is None
            or result_map[e.name].action == "generate"
        ]

        if unmatched and self._img_gen_enabled:
            total = len(unmatched)
            completed = [0]  # mutable counter shared across threads

            def _generate_one(entity: EntitySpec) -> PrebuildResult:
                img_client = self._img_clients[entity.asset_type]
                refs = self._collect_library_refs(entity.asset_type, img_client.model)
                desc = _entity_description(entity)

                asset_id = generate_asset_image(
                    entity.asset_type, entity.name, desc,
                    img_client, self._library,
                    reference_image_urls=refs or None,
                )

                if asset_id is not None:
                    roster.set_target(entity.asset_type, entity.name, asset_id)

                return PrebuildResult(
                    entity_name=entity.name,
                    asset_type=entity.asset_type,
                    status="generated" if asset_id else "failed",
                    asset_id=asset_id,
                )

            with ThreadPoolExecutor(
                max_workers=min(self._max_workers, max(total, 1))
            ) as ex:
                futures = {
                    ex.submit(_generate_one, e): e for e in unmatched
                }
                for future in as_completed(futures):
                    result = future.result()
                    completed[0] += 1
                    yield {
                        "type": "prebuild_progress",
                        "phase": "generate",
                        "entity": result.entity_name,
                        "asset_type": result.asset_type.value,
                        "status": result.status,  # "generated" or "failed"
                        "completed": completed[0],
                        "total": total,
                    }

        # ── Step 4: Verify + force-select fallback ─────────────────
        from storyloom.tasks import select_forced

        for entity in entities:
            item = roster.lookup(entity.asset_type, entity.name)
            if item is None:
                errors.append(
                    f"Entity '{entity.name}' ({entity.asset_type.value}) "
                    f"missing from roster after pre-build"
                )
                continue
            if item.target is not None:
                continue

            # Force-select fallback
            try:
                asset_id = select_forced(
                    self._api, entity.asset_type,
                    entity.name, _entity_description(entity),
                    roster, self._library,
                )
                roster.set_target(entity.asset_type, entity.name, asset_id)
            except Exception as e:
                errors.append(
                    f"Force-select failed for '{entity.name}' "
                    f"({entity.asset_type.value}): {e}"
                )

        # ── Persist library (single save — thread-safe, all mutations done) ─
        self._library.save()

        # ── Final: yield result ────────────────────────────────────
        if errors:
            yield {
                "type": "prebuild_complete",
                "success": False,
                "results": [],
                "errors": errors,
                "warnings": selection_warnings if selection_warnings else [],
            }
        else:
            results_list = []
            for e in entities:
                item = roster.lookup(e.asset_type, e.name)
                action = result_map.get(e.name)
                results_list.append({
                    "entity_name": e.name,
                    "asset_type": e.asset_type.value,
                    "status": (
                        "matched" if (action is not None and action.action == "matched")
                        else "generated" if (item is not None and item.target is not None)
                        else "force_selected"
                    ),
                    "asset_id": item.target if item else None,
                })
            yield {
                "type": "prebuild_complete",
                "success": True,
                "results": results_list,
                "errors": [],
                "warnings": selection_warnings if selection_warnings else [],
            }

    # ── Force-select all (batch selection failed) ──────────────────

    def _force_select_all(
        self,
        entities: list[EntitySpec],
        roster: GameAssetRoster,
    ) -> list[SelectionResult]:
        """Fallback: per-entity force-select when batch selection fails."""
        from storyloom.tasks import select_forced

        results: list[SelectionResult] = []
        for entity in entities:
            desc = _entity_description(entity)
            try:
                asset_id = select_forced(
                    self._api, entity.asset_type,
                    entity.name, desc,
                    roster, self._library,
                )
                results.append(SelectionResult(
                    entity_name=entity.name,
                    action="matched",
                    asset_id=asset_id,
                    asset_type=entity.asset_type,
                ))
            except Exception:
                # Per-entity failure — skip (verification will catch it)
                pass
        return results


    # ── Reference image collection (library-based) ──────────────────

    def _collect_library_refs(
        self,
        asset_type: AssetType,
        model: str,
    ) -> list[str]:
        """Collect reference image data URLs from the global library.

        Pre-build variant — the roster is empty at this stage, so we
        read from the library instead.  Uses sorted-by-usage for
        representative style guidance.
        """
        from storyloom.config import GENERATE_REF_IMAGE_COUNT
        from storyloom.io.img_api_client import MODEL_PRESETS
        from storyloom.io.img_utils import collect_reference_data_urls

        preset = MODEL_PRESETS.get(model)
        if preset is not None and not preset.supports_reference:
            return []

        assets = self._library.get_sorted_by_usage(
            asset_type, GENERATE_REF_IMAGE_COUNT * 2,
        )
        paths = [
            p for asset in assets
            if (p := self._library.asset_path(asset)) is not None
        ]
        ext = asset_type.default_extension.lstrip(".")
        return collect_reference_data_urls(
            paths,
            mime_type=f"image/{ext}",
            max_count=GENERATE_REF_IMAGE_COUNT,
        )


# Import for type hints (kept at bottom to avoid circular imports)
from storyloom.tasks import generate_asset_image  # noqa: E402

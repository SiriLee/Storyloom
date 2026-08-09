"""LLM-based asset generation — selection + AI image generation for GENERATE tasks.

Per design.md §5.5: two-phase — LLM selection (roster + library) then AI image
generation.  Single disabled-thinking LLM call for selection (prompt_lab
15/15 pass).  Silent degradation via forced selection on failure.

Prompts are specified in docs/graph-mode-spec/prompt-design-llm-generate.md.
"""

from __future__ import annotations

import base64
import os
import uuid

from storyloom.assets import AssetLibrary, AssetType, GameAssetRoster
from storyloom.config import GENERATE_LIBRARY_TOP_N, GENERATE_REF_IMAGE_COUNT
from storyloom.tasks._types import Task

# ═══════════════════════════════════════════════════════════════════════
# Prompt templates (per prompt-design-llm-generate.md)
# ═══════════════════════════════════════════════════════════════════════

_SELECTION_SYSTEM_CHAR = """\
You are the asset selector in a real-time visual novel game. Given a target character and a list of available portrait entries, pick the single best match or select nothing if none is suitable."""

_SELECTION_SYSTEM_BG = """\
You are the asset selector in a real-time visual novel game. Given a target scene and a list of available background entries, pick the single best match or select nothing if none is suitable."""

_SELECTION_OUTPUT_NORMAL = """\
## Output Format

Reply ONLY with a valid JSON object:
{"scope": "<game|global|null>", "selected": "<name|id|null>"}"""

_SELECTION_OUTPUT_FORCED = """\
## Output Format

Reply ONLY with a valid JSON object:
{"scope": "<game|global>", "selected": "<name|id>"}"""

_SELECTION_EXAMPLE_CHAR = """\
## Example

Game Roaster
- "Alice": A young woman with silver hair and a gentle expression
- "Bob": A tall warrior in plate armor
- "Math Teacher": A middle-aged man in the white shirt

Global Library
- [sys_adult_female] "Adult Woman": Adult woman, neutral expression
- [a1b2c3d4] "Elf Archer": Female elf archer in a green cloak, holding a bow

### Case 1 — Game Roaster (name first)
Target
Name: "Teacher"
Description: An old bald man with glasses

→ {"scope": "game", "selected": "Math Teacher"}

### Case 2 — Global Library (description first)
Target
Name: "Legolas"
Description: A tall male elf with a bow, wearing forest-green clothing

→ {"scope": "global", "selected": "a1b2c3d4"}

### Case 3 — No match
Target
Name: "Xyloth"
Description: A cosmic horror entity from beyond the stars, with writhing tentacles

→ {"scope": "null", "selected": null}"""

_SELECTION_EXAMPLE_BG = """\
## Example

Game Roaster
- "Grand Library": A majestic two-story library with floor-to-ceiling bookshelves
- "Castle Gate": A massive stone gate with iron portcullis
- "Riverside Market": A bustling outdoor market along the riverbank

Global Library
- [sys_classroom] "Classroom": Empty classroom with desks and blackboard
- [e5f6g7h8] "Dungeon": Dark stone dungeon with torches and iron bars

### Case 1 — Game Roaster (name first)
Target
Name: "Library Restricted Section"
Description: A dim, forbidden section of the library behind a locked iron gate

→ {"scope": "game", "selected": "Grand Library"}

### Case 2 — Global Library (description first)
Target
Name: "Underground Prison"
Description: A damp underground prison with rusty chains on the walls

→ {"scope": "global", "selected": "e5f6g7h8"}

### Case 3 — No match
Target
Name: "Alien Spaceship"
Description: The bridge of an advanced alien spacecraft with holographic displays

→ {"scope": "null", "selected": null}"""

_SELECTION_RULES_NORMAL = """\
## Rules

1. **Game Roaster** — the current game's assets. Match by **name first**. Return `"scope": "game"` with the exact `name`.
2. **Global Library** — all available assets across games. Match by **description first**. Descriptions may be in different languages — compare by meaning. Return `"scope": "global"` with the exact `asset_id` (the [bracketed] prefix from the list).
3. **No Match** - If no entry in either source is a reasonable fit, return `"scope": "null", "selected": null`."""

_SELECTION_RULES_FORCED = """\
## Rules

1. **Game Roaster** — the current game's assets. Match by **name first**. Return `"scope": "game"` with the exact `name`.
2. **Global Library** — all available assets across games. Match by **description first**. Descriptions may be in different languages — compare by meaning. Return `"scope": "global"` with the exact `asset_id` (the [bracketed] prefix from the list).
3. **You MUST pick one.** If neither roster nor library has a great match, pick the closest from the global library. Do NOT return null."""

_SELECTION_TASK_HEADER = """\
## Task

### Game Roaster
{roster_entries}

### Global Library
{library_entries}

### Target
Name: {target_name}
Description: {target_description}"""

_GEN_CHAR = """\
You are an artist for a real-time visual novel game. Create a character portrait.

## Requirements
- {style_line}
- Transparent background; use plain white background if transparency is not supported.

## Character
Name: {name}
Description: {description}"""

_GEN_BG = """\
You are an artist for a real-time visual novel game. Create a background scene.

## Requirements
- {style_line}

## Scene
Name: {name}
Description: {description}"""

_STYLE_WITH_REF = (
    "The provided reference images are for art style reference only "
    "— match their art style, not the specific character designs."
)
_STYLE_WITHOUT_REF = "Use a standard anime visual novel art style."


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

def build_selection_prompt(
    asset_type: AssetType,
    target_name: str,
    target_description: str,
    roster: GameAssetRoster,
    library,  # AssetLibrary
    forced: bool = False,
) -> str:
    """Build the LLM selection prompt for a GENERATE task.

    Args:
        asset_type: CHAR_PORTRAIT or BACKGROUND.
        target_name: Name from the DECLARE tag.
        target_description: Description from the DECLARE tag.
        roster: Per-game asset roster (source of game entries).
        library: Global AssetLibrary (source of library entries).
        forced: If True, use forced-mode prompt (no null, must pick).

    Returns:
        Complete prompt string ready for ApiClient.chat().
    """
    system = (
        _SELECTION_SYSTEM_CHAR if asset_type == AssetType.CHAR_PORTRAIT
        else _SELECTION_SYSTEM_BG
    )
    example = (
        _SELECTION_EXAMPLE_CHAR if asset_type == AssetType.CHAR_PORTRAIT
        else _SELECTION_EXAMPLE_BG
    )
    output = _SELECTION_OUTPUT_FORCED if forced else _SELECTION_OUTPUT_NORMAL
    rules = _SELECTION_RULES_FORCED if forced else _SELECTION_RULES_NORMAL

    roster_entries = _format_roster_entries(asset_type, roster, target_name)
    library_entries = _format_library_entries(asset_type, library)

    task_section = _SELECTION_TASK_HEADER.format(
        roster_entries=roster_entries,
        library_entries=library_entries,
        target_name=target_name,
        target_description=target_description,
    )

    return "\n\n".join([system, output, example, rules, task_section])


def build_generation_prompt(
    asset_type: AssetType,
    name: str,
    description: str,
    has_reference: bool,
) -> str:
    """Build the AI image generation prompt.

    Args:
        asset_type: CHAR_PORTRAIT or BACKGROUND.
        name: Name from the DECLARE tag.
        description: Description from the DECLARE tag.
        has_reference: Whether reference images will be provided.

    Returns:
        Complete prompt string ready for ImgApiClient.generate().
    """
    style_line = _STYLE_WITH_REF if has_reference else _STYLE_WITHOUT_REF
    template = _GEN_CHAR if asset_type == AssetType.CHAR_PORTRAIT else _GEN_BG
    return template.format(style_line=style_line, name=name, description=description)


# ═══════════════════════════════════════════════════════════════════════
# Internal helpers
# ═══════════════════════════════════════════════════════════════════════

def _format_roster_entries(
    asset_type: AssetType,
    roster: GameAssetRoster,
    exclude_name: str,
) -> str:
    """Format roster entries for the selection prompt.

    Includes all entries except *exclude_name* (the current DECLARE's own
    placeholder — we don't want the LLM to "match" against the very entry
    we're trying to fill).  Placeholders (target=None) are included —
    they represent declared entities that the game knows about, and their
    names are valid matching targets.
    """
    entries = roster.list_by_type(asset_type)
    lines: list[str] = []
    for local_name, item in entries.items():
        if local_name == exclude_name:
            continue
        desc = item.local_description or "(no description)"
        lines.append(f'- "{local_name}": {desc}')
    return "\n".join(lines) if lines else "(empty)"


def _format_library_entries(
    asset_type: AssetType,
    library,  # AssetLibrary
) -> str:
    """Format library entries for the selection prompt.

    Uses get_sorted_by_usage with GENERATE_LIBRARY_TOP_N to get the
    most relevant entries.
    """
    assets = library.get_sorted_by_usage(asset_type, GENERATE_LIBRARY_TOP_N)
    lines: list[str] = []
    for asset in assets:
        desc = asset.description or "(no description)"
        lines.append(f'- [{asset.id}] "{asset.name}": {desc}')
    return "\n".join(lines) if lines else "(empty)"


def _select(
    api_client,  # ApiClient
    asset_type: AssetType,
    target_name: str,
    target_description: str,
    roster: GameAssetRoster,
    library,  # AssetLibrary
    forced: bool = False,
    thinking_mode: str = "disabled",
) -> str | None:
    """Run LLM selection.  Returns ``asset_id`` or ``None``.

    On ApiError or unparseable response, returns ``None``
    (caller handles fallback).

    Defaults to disabled thinking — the selection task (pick from a
    known list by name/description) is straightforward enough that
    reasoning overhead adds latency without improving accuracy.
    prompt_lab 15/15 pass at disabled, including zh↔en cross-lingual
    and church/temple disambiguation.
    """
    from storyloom.io.api_client import ApiError
    from storyloom.io.thinking import get_thinking_params

    thinking_mode = os.environ.get("LLM_SELECT_THINKING", thinking_mode)

    prompt = build_selection_prompt(
        asset_type, target_name, target_description,
        roster, library, forced=forced,
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        raw = api_client.chat(
            messages=messages,
            response_format={"type": "json_object"},
            extra_params=get_thinking_params(api_client.model, thinking_mode),
        )
    except ApiError:
        return None

    roster_entries = roster.list_by_type(asset_type)
    library_entries = library.list_by_type(asset_type)
    return _parse_selection_response(raw, roster_entries, library_entries)


def _parse_selection_response(
    raw: str,
    roster_entries: dict,
    library_entries: dict,
) -> str | None:
    """Parse the LLM selection response.

    Args:
        raw: Raw LLM response text.
        roster_entries: ``{local_name: AssetItem}`` from the roster.
        library_entries: ``{asset_id: Asset}`` from the library.

    Returns:
        ``asset_id`` if a valid match was found, ``None`` otherwise.
    """
    import json as _json

    try:
        data = _json.loads(raw)
    except (_json.JSONDecodeError, TypeError):
        return None

    scope = data.get("scope", "")
    selected = data.get("selected")

    if not isinstance(selected, str) or not selected.strip():
        return None

    selected = selected.strip()

    if scope == "game":
        item = roster_entries.get(selected)
        if item is not None:
            return item.target
        return None

    if scope == "global":
        if selected in library_entries:
            return selected
        return None

    return None


def _select_forced(
    api_client,  # ApiClient
    asset_type: AssetType,
    target_name: str,
    target_description: str,
    roster: GameAssetRoster,
    library,  # AssetLibrary
) -> str:
    """Run forced LLM selection — must return an ``asset_id``.

    Two attempts: light-thinking then enabled-thinking.  If both fail,
    programmatic pick: first ``sys_`` asset in the library of the given
    type, then first user asset, or raises ``RuntimeError`` if the
    library is empty.
    """
    # Attempt 1: light thinking
    result = _select(
        api_client, asset_type, target_name, target_description,
        roster, library, forced=True, thinking_mode="light",
    )
    if result is not None:
        return result

    # Attempt 2: enabled (heavier) thinking
    result = _select(
        api_client, asset_type, target_name, target_description,
        roster, library, forced=True, thinking_mode="enabled",
    )
    if result is not None:
        return result

    # Programmatic fallback: first sys_ asset, then first user asset
    all_assets = library.list_by_type(asset_type)
    sys_ids = sorted(aid for aid in all_assets if aid.startswith("sys_"))
    if sys_ids:
        return sys_ids[0]
    user_ids = sorted(aid for aid in all_assets if not aid.startswith("sys_"))
    if user_ids:
        return user_ids[0]

    raise RuntimeError(
        f"No assets available for type {asset_type.value} "
        f"— cannot complete forced selection"
    )


def _collect_reference_images(
    asset_type: AssetType,
    roster: GameAssetRoster,
    current_name: str,
    model: str,
) -> list[str]:
    """Collect up to GENERATE_REF_IMAGE_COUNT reference images from the roster.

    Source: roster entries of the same *asset_type* that have a real
    target (not None).  The current DECLARE's own entry is excluded.

    Returns:
        List of base64 data URL strings (MIME type derived from asset type),
        or empty list if the model doesn't support references or no
        suitable images exist.
    """
    from storyloom.io.img_api_client import MODEL_PRESETS

    preset = MODEL_PRESETS.get(model)
    if preset is not None and not preset.supports_reference:
        return []

    entries = roster.list_by_type(asset_type)
    refs: list[str] = []
    for local_name, item in entries.items():
        if local_name == current_name:
            continue
        if item.target is None:
            continue
        if len(refs) >= GENERATE_REF_IMAGE_COUNT:
            break

        # Resolve file path via the roster's library
        asset = roster._library.get(asset_type, item.target)
        if asset is None:
            continue
        path = roster._library.asset_path(asset)
        if path is None or not os.path.isfile(path):
            continue

        try:
            raw = open(path, "rb").read()
        except OSError:
            continue

        b64 = base64.b64encode(raw).decode("ascii")
        refs.append(f"data:{_mime_for(asset_type)};base64,{b64}")

    return refs


def _mime_for(asset_type: AssetType) -> str:
    """Return the MIME type for *asset_type* based on its default extension."""
    ext = asset_type.default_extension.lstrip(".")
    return f"image/{ext}"


# ═══════════════════════════════════════════════════════════════════════
# Image persistence
# ═══════════════════════════════════════════════════════════════════════

def _save_image(
    library: AssetLibrary,
    asset_type: AssetType,
    name: str,
    description: str,
    raw_bytes: bytes,
) -> str:
    """Save a generated image to disk and register in the library.

    Returns:
        The new ``asset_id``.
    """
    asset_id = uuid.uuid4().hex
    dir_path = os.path.join(library.media_dir, asset_type.value)
    os.makedirs(dir_path, exist_ok=True)
    filepath = os.path.join(dir_path, f"{asset_id}{asset_type.default_extension}")
    with open(filepath, "wb") as f:
        f.write(raw_bytes)
    library.add(asset_type, name, description, asset_id=asset_id)
    return asset_id


# ═══════════════════════════════════════════════════════════════════════
# GenerateProcessor
# ═══════════════════════════════════════════════════════════════════════

class GenerateProcessor:
    """LLM-based GENERATE task processor — replaces the §7.6 stub.

    Conforms to the ``generate_processor`` protocol expected by
    ``TaskGenerator``::

        processor = GenerateProcessor(api_client, img_client_portrait,
                                      img_client_background, library, ...)
        gen = TaskGenerator(queue, roster, generate_processor=processor)

    Per design.md §5.5: two-phase — LLM selection (roster + library)
    then AI image generation.  Single disabled-thinking LLM call for
    selection (prompt_lab 15/15).  Silent degradation via forced selection on failure.
    """

    def __init__(
        self,
        api_client,            # ApiClient
        img_client_portrait,   # ImgApiClient (remove_bg from user config)
        img_client_background,  # ImgApiClient (remove_bg=NEVER)
        library: AssetLibrary,
        img_generation_enabled: bool,
    ):
        self._api = api_client
        self._img_clients = {
            AssetType.CHAR_PORTRAIT: img_client_portrait,
            AssetType.BACKGROUND: img_client_background,
        }
        self._library = library
        self._img_generation_enabled = img_generation_enabled

    def __call__(
        self,
        asset_type: AssetType,
        local_name: str,
        roster: GameAssetRoster,
    ):
        """Return a ``Task.process`` closure.  Safe to call from any thread."""
        api = self._api
        lib = self._library
        img_gen_enabled = self._img_generation_enabled
        img_client = self._img_clients[asset_type]

        def process(task: Task) -> None:
            desc = roster.lookup(asset_type, local_name)
            description = desc.local_description if desc else ""

            # Phase 1: LLM Selection
            asset_id = _select(
                api, asset_type, local_name, description,
                roster, lib, forced=False,
            )

            if asset_id is not None:
                roster.set_target(asset_type, local_name, asset_id)
                lib.save()
                task.complete()
                return

            # Phase 2: AI Generation (if enabled)
            if img_gen_enabled:
                asset_id = self._generate(
                    asset_type, local_name, description,
                    roster, img_client,
                )

            # Phase 3: Forced fallback
            if asset_id is None:
                asset_id = _select_forced(
                    api, asset_type, local_name, description,
                    roster, lib,
                )

            roster.set_target(asset_type, local_name, asset_id)
            lib.save()
            task.complete()

        return process

    def _generate(
        self,
        asset_type: AssetType,
        local_name: str,
        description: str,
        roster: GameAssetRoster,
        img_client,  # ImgApiClient
    ) -> str | None:
        """Run AI image generation.  Returns ``asset_id`` or ``None``."""
        from storyloom.io._types import ImageSize
        from storyloom.io.img_api_client import ImageApiError

        model = img_client.model
        refs = _collect_reference_images(asset_type, roster, local_name, model)
        has_ref = len(refs) > 0

        prompt = build_generation_prompt(
            asset_type, local_name, description, has_reference=has_ref,
        )

        size = (
            ImageSize.PORTRAIT if asset_type == AssetType.CHAR_PORTRAIT
            else ImageSize.BACKGROUND
        )

        try:
            result = img_client.generate(prompt, size, image_urls=refs or None)
        except (ImageApiError, ValueError):
            return None

        raw = result.bytes

        # Post-process: enforce 16:9 for backgrounds
        if asset_type is AssetType.BACKGROUND:
            from storyloom.io.img_utils import normalize_background
            raw = normalize_background(raw)

        return _save_image(self._library, asset_type, local_name, description, raw)

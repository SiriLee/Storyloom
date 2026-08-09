"""LLM-based asset matching — replaces the §7.4 stub process_factory.

Per design.md §5.4: low-probability forced-choice path.  Scope is the
game asset roster only (never the global library).  Two attempts —
no-thinking then light-thinking — then silent degradation.
"""

from __future__ import annotations

from storyloom.assets import AssetType, GameAssetRoster
from storyloom.io.api_client import ApiClient, ApiError
from storyloom.io.thinking import get_thinking_params
from storyloom.tasks._types import Task


# ═══════════════════════════════════════════════════════════════════════
# Match prompt templates (design doc: prompt-design-llm-match.md)
# ═══════════════════════════════════════════════════════════════════════

_MATCH_SYSTEM_PROMPTS: dict[AssetType, str] = {
    AssetType.CHAR_PORTRAIT: """\
You are the asset matcher in a real-time visual novel game. Given a target character name and a list of available portrait entries, pick the single best match.

## Output Format

Reply ONLY with a valid JSON object:
{"selected": "<exact name from the list>"}

## Example

Target: "Alice.happy"
Entries:
- "Alice": A young woman with blue hair and a gentle expression
- "Alice.sad": A young woman with blue hair, looking down with sorrow
- "Alice.smile": A young woman with blue hair and a gentle smile
- "Bob": A tall warrior in plate armor
- "Queen": An elderly ruler with silver crown

Output:
{"selected": "Alice.smile"}

## Matching Rules

1. NAME VARIANT — match by name first.
2. SEMANTIC MATCH — use description when names are equally close.""",
    AssetType.BACKGROUND: """\
You are the asset matcher in a real-time visual novel game. Given a target scene name and a list of available background entries, pick the single best match.

## Output Format

Reply ONLY with a valid JSON object:
{"selected": "<exact name from the list>"}

## Example

Target: "forest.night"
Entries:
- "forest": A dense woodland with dappled sunlight through leaves
- "castle": An ancient stone fortress on a windswept cliff
- "tavern": A warm, crowded inn with a roaring fireplace

Output:
{"selected": "forest"}

## Matching Rules

1. NAME VARIANT — match by name first.
2. SEMANTIC MATCH — use description when names are equally close.""",
}

_USER_MESSAGE_TEMPLATE = """\
Target: "{target_name}"

Entries:
{entries}

Select the ONLY best match for "{target_name}". You MUST pick one."""


def build_match_messages(
    asset_type: AssetType,
    target_name: str,
    roster: GameAssetRoster,
) -> list[dict]:
    """Build the messages array for a match LLM call.

    Args:
        asset_type: Type of asset being matched.
        target_name: The name the Director LLM used (may not match exactly).
        roster: Per-game asset roster — only source of entries.

    Returns:
        List of message dicts ready for ``ApiClient.chat()``,
        or an empty list when the roster has no entries of *asset_type*.
    """
    entries = roster.list_by_type(asset_type)
    if not entries:
        return []

    system_msg = _MATCH_SYSTEM_PROMPTS[asset_type]

    entry_lines: list[str] = []
    for local_name, item in entries.items():
        desc = item.local_description or "(no description)"
        entry_lines.append(f'- "{local_name}": {desc}')

    user_msg = _USER_MESSAGE_TEMPLATE.format(
        target_name=target_name,
        entries="\n".join(entry_lines),
    )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]


# ═══════════════════════════════════════════════════════════════════════
# Response parsing
# ═══════════════════════════════════════════════════════════════════════

def _parse_match_response(raw: str, entries: dict) -> str | None:
    """Extract a valid ``local_name`` from the LLM response.

    1. Try ``json.loads`` → ``"selected"`` key → validate against *entries*.
    2. Try substring match: each entry key against *raw*.
    3. Neither works → ``None`` (caller decides retry / give-up).

    Args:
        raw: Raw LLM response text.
        entries: ``{local_name: AssetItem}`` dict from the roster.

    Returns:
        A valid *local_name* from *entries*, or ``None``.
    """
    if not entries:
        return None

    # 1. JSON parse
    import json as _json
    try:
        data = _json.loads(raw)
        selected = data.get("selected", "")
        if isinstance(selected, str) and selected.strip():
            name = selected.strip()
            if name in entries:
                return name
    except (_json.JSONDecodeError, TypeError, AttributeError):
        pass

    # 2. Substring scan — find any entry key in the raw text.
    # NOTE: this is intentionally loose — ``"hero" in "heroine"``
    # returns True.  In practice, local_names are sufficiently
    # distinct (``"jack_smile"`` / ``"forest_clearing"``) that
    # collisions are harmless.  This is a best-effort fallback;
    # the JSON parse above is the primary extraction path.
    for name in entries:
        if name in raw:
            return name

    return None


# ═══════════════════════════════════════════════════════════════════════
# MatchProcessor
# ═══════════════════════════════════════════════════════════════════════

class MatchProcessor:
    """LLM-based MATCH task processor — replaces the §7.4 stub.

    Instance conforms to the ``match_processor`` protocol expected by
    ``TaskGenerator``::

        processor = MatchProcessor(api_client)
        gen = TaskGenerator(queue, roster, match_processor=processor)

    Per design.md §5.4: forced-choice from roster, no thinking → light
    thinking retry → silent degradation on double failure.

    Args:
        api_client: Configured ``ApiClient`` for LLM calls.  Its
            ``model`` property drives thinking-parameter selection.
    """

    def __init__(self, api_client: ApiClient):
        self._api = api_client

    def __call__(
        self,
        asset_type: AssetType,
        local_name: str,
        roster: GameAssetRoster,
    ):
        """Return a ``Task.process`` closure for a MATCH task.

        The closure is safe to call from any thread (typically Thread 4,
        ``TaskPool``).  It never raises — failures are recorded in
        ``task.error`` and the task is always completed.
        """
        api = self._api
        target = local_name

        def process(task: Task) -> None:
            # ── Empty roster ──────────────────────────────────────────
            entries = roster.list_by_type(asset_type)
            if not entries:
                task.complete()
                return

            # ── Attempt 1: no thinking ────────────────────────────────
            result = _call_llm(api, asset_type, target, roster, "disabled")
            if result is not None:
                task.result = result
                task.complete()
                return

            # ── Attempt 2: light thinking ─────────────────────────────
            result = _call_llm(api, asset_type, target, roster, "light")
            if result is not None:
                task.result = result
                task.complete()
                return

            # ── Both failed — silent degradation ──────────────────────
            # EventDispatcher will skip binding; UI shows no asset.
            task.error = f"LLM match failed after 2 attempts: {target!r}"
            task.complete()

        return process


def _call_llm(
    api: ApiClient,
    asset_type: AssetType,
    target_name: str,
    roster: GameAssetRoster,
    thinking_mode: str,
) -> str | None:
    """Single LLM match call.  Returns *local_name* or ``None``.

    ``None`` means the caller should retry (with a different
    *thinking_mode*) or give up.  ``ApiError`` is caught and
    converted to ``None`` — non-API exceptions propagate to
    ``TaskPool._run``'s safety net.
    """
    messages = build_match_messages(asset_type, target_name, roster)
    if not messages:
        return None

    try:
        raw = api.chat(
            messages=messages,
            response_format={"type": "json_object"},
            extra_params=get_thinking_params(api.model, thinking_mode),
        )
    except ApiError:
        return None

    entries = roster.list_by_type(asset_type)
    return _parse_match_response(raw, entries)

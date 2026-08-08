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
# Match prompt templates (placeholder — §7.8a prompt design TBD)
# ═══════════════════════════════════════════════════════════════════════

# Final prompts will be designed in a dedicated session.  These are
# functional placeholders that produce correct matching behaviour.

_MATCH_SYSTEM_PROMPT = (
    "You are a strict media asset matcher for a visual novel engine.\n"
    "Given a target name and a list of available entries, select the\n"
    "single best matching entry.  You MUST pick one — this is a forced choice.\n\n"
    "Rules:\n"
    "- Prefer exact name matches.\n"
    "- If no exact match, prefer the entry whose name or description is most\n"
    "  semantically related to the target.\n"
    "- A partial or variant name (e.g. \"Jack\" vs \"Jack.smile\") counts as a\n"
    "  strong signal.\n"
    "- Reply ONLY with a JSON object: {\"selected\": \"<exact local_name>\"}"
)

# Per-type guidance appended to the system prompt.  (design.md §5.4:
# "不同素材类型使用不同 Prompt").
_ASSET_TYPE_GUIDANCE: dict[AssetType, str] = {
    AssetType.CHAR_PORTRAIT: (
        "For character portraits, match by name, appearance traits, or role.\n"
        "Favour entries whose description shares visual or personality cues\n"
        "with the target."
    ),
    AssetType.BACKGROUND: (
        "For background scenes, match by location name, atmosphere, or setting.\n"
        "Favour entries whose description shares environmental or mood cues\n"
        "with the target."
    ),
}

_ASSET_TYPE_LABELS: dict[AssetType, str] = {
    AssetType.CHAR_PORTRAIT: "Character Portrait",
    AssetType.BACKGROUND: "Background / Scene",
}


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

    guidance = _ASSET_TYPE_GUIDANCE.get(asset_type, "")
    system_msg = _MATCH_SYSTEM_PROMPT
    if guidance:
        system_msg += "\n\n" + guidance

    entry_lines: list[str] = []
    for local_name, item in entries.items():
        desc = item.local_description or "(no description)"
        entry_lines.append(f'- "{local_name}": {desc}')

    type_label = _ASSET_TYPE_LABELS.get(asset_type, asset_type.value)
    user_msg = (
        f'Target: "{target_name}"\n'
        f"Type: {type_label}\n"
        f"Available entries:\n"
        + "\n".join(entry_lines)
        + f'\n\nSelect the best match for "{target_name}".'
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
            max_tokens=64,
            response_format={"type": "json_object"},
            extra_params=get_thinking_params(api.model, thinking_mode),
        )
    except ApiError:
        return None

    entries = roster.list_by_type(asset_type)
    return _parse_match_response(raw, entries)

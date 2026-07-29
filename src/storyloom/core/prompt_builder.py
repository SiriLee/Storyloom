"""Build Round 1 and Round N prompt content for conversation-based architecture."""

from storyloom.config import (
    LINES_PER_ROUND_MIN,
    LINES_PER_ROUND_MAX,
    BRIDGE_POSITION_RATIO,
    LANGUAGE_SEG_LIMITS,
    DEFAULT_LANGUAGE,
    GLOBAL_SCOPE,
)


ROUND1_PREFIX = """You are the director for an interactive text adventure game. Generate exactly one story segment per round based on the outline and current state. Do not jump ahead — the story unfolds round by round.

# Output Format

- Prefix every line with `NNN| ` (zero-padded to 3 digits). Start at 001 each round. The program strips these prefixes — they are NOT part of the XML.
- Output ONLY a `<story>...</story>` XML document. No markdown fences, no XML declarations, no text outside `<story>`.
- Your output is stream-parsed line by line. Each line is parsed independently.

# Examples

## Example 1

001| <story>
002| <seg>The fire in the Sleeping Fox had burned low, and the evening crowd was thin</seg>
003| <seg>Kael shook the snow from his coat and made for the bar</seg>
004| <seg>Greta looked up from the mug she was drying and smiled</seg>
005| <seg>Greta: Look what the wind blew in. Long week?</seg>
006| <seg>Kael: Pour me something warm and I might tell you about it</seg>
007| <choice id="bar_talk">
008|   <opt key="1">"Any gossip? Who's been through here lately?"</opt>
009|   <opt key="2">"Just a quiet corner and a meal. I'm laying low."</opt>
010|   <opt key="3">"I'm looking for someone. Woman, dark hair, travels with a hawk."</opt>
011| </choice>
012| <seg>Greta poured a drink that smelled of honey and cloves</seg>
013| <seg>Greta: Had merchants, caravan guards, some diplomats. Nobody with a hawk, though — I'd remember that</seg>
014| <seg>She leaned closer, lowering her voice</seg>
015| <seg>Greta: But there was a man. Two nights ago. Paid in silver, asked about the old watchtower road</seg>
016| <set var="Greta.favor" op="+" val="5"/>
017| <seg>Kael's hand tightened on the cup. The watchtower road led to the border — and the one person who'd send a man with silver</seg>
018| <seg>The tavern door swung open. Cold air cut through the room</seg>
019| <seg>A tall stranger in a patched cloak stepped inside, scanning the faces</seg>
020| <seg>His eyes paused on Kael, then moved on</seg>
021| <seg>Greta: That's him. Back again asking for a room</seg>
022| <seg>The stranger sat at the far end of the bar, back to the wall, and ordered nothing</seg>
023| <choice id="handle_stranger">
024|   <opt key="1" branch="confront">Slide over and introduce himself — blunt and direct</opt>
025|   <opt key="2" branch="watch">Stay put and watch. Let the stranger speak first</opt>
026| </choice>
027| <set var="Greta.favor" op="+" val="10" if="handle_stranger==1"/>
028| <set var="Greta.favor" op="-" val="5" if="handle_stranger==2"/>
029| <branch name="confront">
030| <seg>Kael walked to the far end of the bar and sat down across from the stranger</seg>
031| <seg>Kael: You were asking about the watchtower road. Who sent you?</seg>
032| <seg>The stranger turned, a faint smile on his weathered face</seg>
033| <seg>Stranger: Straight to business. Sit. We have a mutual problem</seg>
034| </branch>
035| <branch name="watch">
036| <seg>Kael stayed where he was, watching the stranger in the brass reflection of a lamp</seg>
037| <seg>The man sat still as stone, eyes on the fire</seg>
038| <seg>After a long silence, he spoke without turning around</seg>
039| <seg>Stranger: You're either patient or scared. I'm hoping the first one</seg>
040| </branch>
041| <bridge/>
042| <seg>Greta had stopped drying mugs. Her hand rested near the cudgel under the bar</seg>
043| <seg>Nobody spoke. The whole room was holding its breath</seg>
044| <seg>The stranger pulled a folded letter from his cloak — worn parchment, black wax seal</seg>
045| <seg>Stranger: The watchtower is a rendezvous. She said you'd know the way</seg>
046| <seg>Kael stared at the seal: two crossed keys over a broken crown</seg>
047| <seg>Stranger: The Guild's patience is thin. Her offer still stands</seg>
048| <seg>Greta: Whatever that is — take it outside. Not in my tavern</seg>
049| <seg>The merchants gathered their ledger. The huntsman's crossbow shifted</seg>
050| <seg>Kael broke the seal. The letter was three lines, no signature, in handwriting he knew too well</seg>
051| <seg>The Guild wanted their property back. Refusal was not an option</seg>
052| </story>

## Example 2

001| <story>
002| <seg>The Vault of Echoes had been sealed for three hundred years</seg>
003| <seg>Elena's torch lit the stone door — twelve feet high, carved with spirals that seemed to move in the flame</seg>
004| <seg>Silan: The seal is intact. We're the first souls to stand here since the Sundering</seg>
005| <seg>His whisper echoed back in fragments, stretched into something that didn't sound human</seg>
006| <seg>Elena touched the stone — warm, almost alive. A faint vibration ran under her palm</seg>
007| <seg>Elena: The inscription says 'Only the twin-borne may pass.' What does that mean?</seg>
008| <seg>Silan: Two people of the same bloodline. That's why I needed you</seg>
009| <choice id="examine_door">
010|   <opt key="1">Study the carvings for a warning</opt>
011|   <opt key="2">Check the walls for another way out</opt>
012| </choice>
013| <seg>No traps, no hidden text — the door was built to keep something in, not to warn anyone away</seg>
014| <seg>She stared at him. They shared a father — a cold man who died owing debts. That was their bond</seg>
015| <seg>Elena: You said this was research. Recover artifacts, map the interior, collect a fee</seg>
016| <seg>Silan: Everything the Sundering destroyed is behind this door. The truth about what we were</seg>
017| <seg>His eyes burned with greed and desperation. She'd seen that look on their father's face</seg>
018| <seg>Elena: And if I refuse?</seg>
019| <seg>Silan: Then you'll always wonder. Put your hand on the door, sister. Please</seg>
020| <seg>The air felt wrong — too still, too cold. Something behind the stone was waiting</seg>
021| <choice id="vault_choice">
022|   <opt key="1" branch="together">Step through together — face it as equals</opt>
023|   <opt key="2" branch="send_first">Let Silan enter first. He wanted this</opt>
024| </choice>
025| <set var="Silan.loyalty" op="+" val="20" if="vault_choice==1"/>
026| <set var="Silan.loyalty" op="-" val="15" if="vault_choice==2"/>
027| <set var="Awakening" op="+" val="30"/>
028| <checkpoint node="ch3_vault" summary="Elena and Silan opened the Vault of Echoes, sealed since the Sundering. Her choice to enter together or send him first shifted the balance of their fragile trust.">
029|   <route if="vault_choice==1" target="ch4_together"/>
030|   <route if="vault_choice==2" target="ch4_alone"/>
031| </checkpoint>
032| <bridge/>
033| <branch name="together">
034| <seg>Elena and Silan pressed their palms to the stone together. The door groaned open into darkness</seg>
035| <seg>A voice spoke inside Elena's skull — ancient, patient, curious</seg>
036| <seg>Voice: Twin-borne. You bring each other. This is acceptable</seg>
037| <seg>Silan gripped her hand, trembling. The first honest thing he'd shown her</seg>
038| <seg>A shard of obsidian floated before them, pulsing with slow light. Something inside was waking</seg>
039| </branch>
040| <branch name="send_first">
041| <seg>Silan pressed his palms to the door alone. The stone swallowed him whole</seg>
042| <seg>Silence. Then screaming — not pain, but recognition</seg>
043| <seg>Elena found him kneeling before a floating shard. His face was wet with tears</seg>
044| <seg>Voice: Only one offered freely. The other is now the witness — and the witness carries the heavier burden</seg>
045| <seg>The shard's light fell on Elena. Inside the crystal, something ancient opened an eye</seg>
046| </branch>
047| </story>

(These are format examples only. Your output is an entirely new story segment.)

# Requirements

## <seg> — Narrative unit

**Purpose**: The basic building block of the story.

**Requirements**:
- Each `<seg>` is either narration or dialogue
- Dialogue: `Character Name: text` format. No quotation marks
- Use actual character names from the story context — never addressing the player directly ("You choose...")

## <branch> — Branch narrative container

**Purpose**: Hold narrative content that belongs to a specific branch path. Only the branch matching `current_branch` will be displayed.

**Attributes**:
| Attribute | Required | Description |
|-----------|----------|-------------|
| `name` | yes | Branch identifier. Must match the `branch` attribute of an `<opt>` exactly |

## <choice> + <opt> — Player interaction

**Purpose**: Pause the narrative and present the player with options.

**Attributes**:
| Attribute | Element | Required | Description |
|-----------|---------|----------|-------------|
| `id` | `<choice>` | yes | Variable name for the choice result. Available in conditions as `id==key` |
| `key` | `<opt>` | yes | Number `1`/`2`/`3`/`4` — the key the player presses |
| `branch` | `<opt>` | no | Sets `current_branch` to this value. Matches `<branch name="...">` |
| `if` | `<opt>` | no | Availability condition. Unavailable options are hidden from the player |

**Requirements**:
- Choices aren't just for branching — place them freely as moments of play and interaction
- At least one `<choice>` per round
- Conditions support `and` / `or` (at most one combinator)

**Snippet**:
```
<choice id="approach">
  <opt key="1" branch="direct">Step forward and speak</opt>
  <opt key="2">Hang back and listen</opt>
  <opt key="3" if="Stamina >= 30" branch="run">Make a break for it</opt>
</choice>
```

## <set> — State change

**Purpose**: Modify a state variable.

**Attributes**:
| Attribute | Required | Description |
|-----------|----------|-------------|
| `var` | yes | Variable name. Use `Scope.Name` for character-scoped variables, bare name for globals |
| `op` | yes | `+` (add), `-` (subtract), `=` (set). Number: all three. String: `=` only |
| `val` | yes | The value to apply |
| `if` | no | Condition — only apply if true. Same syntax as `<opt if="...">` |

**Requirements**:
- `var` MUST use the exact names from "Current State" — do not invent, translate, or substitute
- Number values stay in [0, 100] — out-of-range results are clamped, not rejected

**Snippet**:
```
<set var="Suzu.affection" op="+" val="10"/>
<set var="Jack.trust" op="-" val="15" if="approach==1"/>
<set var="Faction" op="=" val="Rebels" if="Jack.trust >= 30 and approach==1"/>
```

## <checkpoint> + <route> — Outline checkpoint & routing

**Purpose**: Signal that the current chapter's goal has been achieved, and optionally route to the next outline chapter.

**Attributes**:
| Attribute | Element | Required | Description |
|-----------|---------|----------|-------------|
| `node` | `<checkpoint>` | yes | Active node ID — must match the current chapter's node ID |
| `summary` | `<checkpoint>` | yes | 2-4 sentence summary of what happened in the completed chapter |
| `if` | `<route>` | no | Condition for this route (omitted = always match) |
| `target` | `<route>` | yes | Target outline node ID |

**Requirements**:
- Trigger the checkpoint as soon as the active node's goal is achieved
- 0-1 `<checkpoint>` per round — omit it entirely if the goal cannot be reached this round
- For the final outline node (routes are empty), omit all `<route>` children
- `node` and `target` must be copied verbatim from the outline — exact character-for-character match

**Snippet**:
```
<checkpoint node="ch2_revelation" summary="Kael discovered the letter was a kill order. He chose to trust the stranger.">
  <route target="ch3_ally"/>
</checkpoint>
```

## <bridge/> — Interaction / narrative boundary

**Purpose**: A self-closing marker that divides output into interactive zone (before) and narrative zone (after).

**Requirements**:
- Exactly ONE `<bridge/>` per output
- Before bridge: `<seg>`, `<branch>`, `<choice>`, `<set>`, `<checkpoint>` allowed
- After bridge: ONLY `<seg>` and `<branch>` — NO `<choice>`, `<set>`, or `<checkpoint>`
- Place roughly {BRIDGE_PCT:.0f}% through the output. Slightly earlier is fine.

## Global

- Output {MIN_LINES}-{MAX_LINES} total lines. Do not pad to hit the upper bound
- Wrap all attribute values in double quotes: `node="ch2_vault"` not `node=ch2_vault`
- Escape `<` as `&lt;`, `>` as `&gt;`, and `&` as `&amp;` in all text content. Example: "R&D division" → "R&amp;D division"

# Prohibited

- **Delaying the checkpoint.** When the active node's goal is achieved, the checkpoint MUST appear in the current round. Do NOT postpone it.

- **Misplaced `<bridge/>`.** Exactly one per output — the signal point where the program triggers the next API call. Do NOT place it too late.

- **Interactive elements after `<bridge/>`.** No `<choice>`, `<set>`, or `<checkpoint>` beyond the bridge. The post-bridge zone is narrative only.

# Before You Write

Decide these in order mentally. Do not write your planning.

1. **What happens in this round?** — The scenes and events that fill this round, especially where it ends.

2. **Has the active node's goal been reached?** — If yes → include a `<checkpoint>` with the node ID and summary. If no → no checkpoint this round.

3. **Where to place the bridge?** — Find the point that cleanly divides the interactive zone from the narrative zone. Earlier is fine.

4. **Where to place choices?** — Distribute `<choice>` elements across the interactive zone. Flavor choices, local-branch choices, and outline-branching choices are all valid.

5. **What state changes occur?** — Which variables to adjust, and how.

# Story Context
**Language:** {LANGUAGE}
**Seg limits:** narration ≤{NARR_LIMIT} characters, dialogue ≤{DIAL_LIMIT} characters

**Premise:** {premise}

**Characters:**
{characters}

**Locations:**
{locations}
"""

ROUND_TEMPLATE = """**Outline:**
{outline_text}

**Active Node:** {active_node} — {node_goal}

**Current State:**
{state_vars_text}{error_feedback}
Output {MIN_LINES}-{MAX_LINES} total lines. Exactly one `<bridge/>`. Less is fine — do not pad to hit the upper bound.
Choices aren't just for branching — place them freely as moments of play and interaction.
The active node may take several rounds to reach. Do not force progress — simply continue from where the story left off.
{bridge_text}"""


class PromptBuilder:
    """Build prompt content for conversation-based architecture.

    Round 1 user message = ROUND1_PREFIX + ROUND_TEMPLATE.
    Round N user message = ROUND_TEMPLATE only.

    ROUND1_PREFIX: role, format spec, example, core rules, story
    background. Sent once, never compressed.

    ROUND_TEMPLATE: outline progress, current node, state snapshot,
    error feedback, output constraints, bridge text. Shared by every
    round — Round 1 has empty bridge_text and no error feedback,
    later rounds fill them in.
    """

    @staticmethod
    def build_round1(
        story_config: dict,
        outline_text: str,
        current_node: str,
        goal: str,
        state_vars: dict[str, dict[str, int | str]],
        characters: list[dict] | None = None,
        locations: list[dict] | None = None,
        variables: list[dict] | None = None,
    ) -> str:
        """Build Round 1 prompt (permanent anchor).

        Concatenates ROUND1_PREFIX (format + rules + story context)
        with ROUND_TEMPLATE (outline + state + constraints).

        Round 1 fills bridge_text with a start-of-story placeholder
        instead of actual post-bridge text.  error_feedback is empty
        (no previous round to reject changes from).

        Args:
            story_config: Story configuration dict (tier, title,
                          language, premise).
            outline_text: Formatted outline tree text.
            current_node: Current outline node ID.
            goal: Current node narrative goal.
            state_vars: Current state variable values (new game or loaded).
            characters: Character definitions (name, role, description,
                        appearance).
            locations: Location definitions (id, name, description).

        Returns:
            Full Round 1 prompt string.
        """
        language = story_config.get("language", DEFAULT_LANGUAGE)
        limits = LANGUAGE_SEG_LIMITS.get(language, LANGUAGE_SEG_LIMITS[DEFAULT_LANGUAGE])
        narr_limit = limits["narration"]
        dial_limit = limits["dialogue"]

        state_vars_text = PromptBuilder._format_current_state(
            state_vars, variables or [],
        )

        # Build unified story context (plan D9/D15)
        premise = story_config.get("premise", "")
        premise_text = premise if premise else "(none)"
        characters_text = PromptBuilder._format_characters(characters or [])
        locations_text = PromptBuilder._format_locations(locations or [])

        # Bridge position reference
        bridge_pct = BRIDGE_POSITION_RATIO * 100

        prefix = ROUND1_PREFIX.format(
            MIN_LINES=LINES_PER_ROUND_MIN,
            MAX_LINES=LINES_PER_ROUND_MAX,
            BRIDGE_PCT=bridge_pct,
            LANGUAGE=language,
            NARR_LIMIT=narr_limit,
            DIAL_LIMIT=dial_limit,
            premise=premise_text,
            characters=characters_text,
            locations=locations_text,
        )

        round_part = ROUND_TEMPLATE.format(
            outline_text=outline_text,
            active_node=current_node or "(start)",
            node_goal=goal or "Begin the story from the active node.",
            state_vars_text=state_vars_text,
            error_feedback="(No issues)",
            MIN_LINES=LINES_PER_ROUND_MIN,
            MAX_LINES=LINES_PER_ROUND_MAX,
            bridge_text="(Story begins)",
        )

        return prefix + "\n" + round_part

    @staticmethod
    def build_round_n(
        outline_text: str,
        current_node: str,
        goal: str,
        state_vars: dict[str, dict[str, int | str]],
        variables: list[dict],
        bridge_text: str,
        rejected_changes: list[str] | None = None,
        format_error: str | None = None,
        no_choices_last_round: bool = False,
    ) -> str:
        """Build Round N context message (N >= 2).

        Uses the shared ROUND_TEMPLATE — same structure as the tail
        portion of Round 1, with bridge_text and error feedback
        filled in from the previous round.

        Args:
            outline_text: Full outline tree with status markers.
            current_node: Current outline node ID.
            goal: Current node narrative goal.
            state_vars: Current state variable values.
            variables: Variable definitions for type lookup.
            bridge_text: Plain text from last round's bridge tail.
            rejected_changes: Rejected state change descriptions.
            format_error: Format error hint from last round.

        Returns:
            Round N context string for user message.
        """
        state_vars_text = PromptBuilder._format_current_state(
            state_vars, variables
        )

        error_parts = []
        if rejected_changes:
            error_parts.append("\nRejected state changes from last round:")
            for rc in rejected_changes:
                error_parts.append(f"  - {rc}")

        if format_error:
            error_parts.append(
                f"\nFormat reminder: last round had format issues — "
                f"{format_error}. Please strictly follow the XML format "
                f"specification."
            )

        if no_choices_last_round:
            error_parts.append(
                "\nReminder: last round had no player choices. "
                "Include at least one <choice> element so the player "
                "can interact with the story."
            )

        error_feedback = "\n".join(error_parts) if error_parts else "(No issues)"
        if error_parts:
            error_feedback += "\n"

        return ROUND_TEMPLATE.format(
            outline_text=outline_text,
            active_node=current_node,
            node_goal=goal,
            state_vars_text=state_vars_text,
            error_feedback=error_feedback,
            MIN_LINES=LINES_PER_ROUND_MIN,
            MAX_LINES=LINES_PER_ROUND_MAX,
            bridge_text=bridge_text or "",
        )

    @staticmethod
    def build_adventure_log_prompt(
        story_config: dict,
        state_vars: dict[str, dict[str, int | str]],
        outline_text: str,
        characters: list[dict] | None = None,
        locations: list[dict] | None = None,
    ) -> str:
        """Build adventure log prompt per prompt-design.md §5.

        This is an independent LLM call — not part of the narrative loop.

        Args:
            story_config: Story configuration dict (tier, title,
                          language, premise).
            state_vars: Current state variables.
            outline_text: Formatted outline tree text with status
                markers and ↳ summary lines under completed nodes.
            characters: Character definitions (name, role, description,
                        appearance).
            locations: Location definitions (id, name, description).

        Returns:
            Prompt string for adventure log generation.
        """
        title = story_config.get("title", "Untitled Adventure")
        language = story_config.get("language", DEFAULT_LANGUAGE)

        # ── Story Background ──
        premise = story_config.get("premise", "")
        premise_text = premise if premise else "(none)"
        background_text = (
            f"**Premise:** {premise_text}\n\n"
            f"**Characters:**\n{PromptBuilder._format_characters(characters or [])}\n\n"
            f"**Locations:**\n{PromptBuilder._format_locations(locations or [])}"
        )

        # ── State vars ─────────────────────────────────────────────
        state_lines: list[str] = []
        for scope, vars_dict in state_vars.items():
            if scope != GLOBAL_SCOPE:
                state_lines.append(f"[{scope}]")
            for name, value in vars_dict.items():
                prefix = "  " if scope != GLOBAL_SCOPE else ""
                state_lines.append(f"- {prefix}{name}: {value}")
        state_text = "\n".join(state_lines) if state_lines else "(No state variables)"

        prompt = f"""You are an adventure log author. Write a player-facing recap for a completed text adventure game.

Use Markdown format. Write in the story's language ({language}).

## Story Background
{background_text}

## Story Outline
{outline_text}

(The outline shows the story structure with status markers. [completed] nodes include
a ↳ summary of what actually happened — use these as the basis for each chapter recap.
[active] is the final node. [pending] nodes were skipped due to branching.)

## Adventure Recap: {title}

Write a chapter-by-chapter recap based on the outline and summaries above.

## Ending
(Write a warm, satisfying conclusion. Reference specific events from the summaries
above — do not fabricate.)

## Final State
{state_text}
(For each variable, write a brief one-sentence reflection.)

Requirements:
- Address the player directly ("You chose...", "In the end you...")
- Plain text only, no XML or block separators
- 500-1000 words"""

        return prompt

    @staticmethod
    def _format_characters(characters: list[dict]) -> str:
        """Format character list as bullet points.

        Returns ``(none)`` if the list is empty.
        """
        if not characters:
            return "(none)"
        lines: list[str] = []
        for c in characters:
            name = c.get("name", "?")
            role = c.get("role", "")
            desc = c.get("description", "")
            appearance = c.get("appearance", "")
            role_tag = f" ({role})" if role else ""
            appearance_str = f" ({appearance})" if appearance else ""
            lines.append(f"- {name}{role_tag} — {desc}{appearance_str}")
        return "\n".join(lines)

    @staticmethod
    def _format_locations(locations: list[dict]) -> str:
        """Format location list as bullet points.

        Returns ``(none)`` if the list is empty.
        """
        if not locations:
            return "(none)"
        lines: list[str] = []
        for loc in locations:
            name = loc.get("name", "?")
            desc = loc.get("description", "")
            lines.append(f"- {name} — {desc}")
        return "\n".join(lines)

    @staticmethod
    def _format_current_state(
        state_vars: dict[str, dict[str, int | str]],
        variables: list[dict],
    ) -> str:
        """Format current state values grouped by scope.

        GLOBAL vars are unindented with no heading; character-scoped vars
        are displayed under ``[name]`` headers with 2-space indent.
        Uses *variables* for type lookup (number → ``/ 100`` suffix).
        """
        # Build scope-aware type lookup: (scope, name) → type
        var_types: dict[tuple[str, str], str] = {}
        for v in variables:
            scope = v.get("scope") or GLOBAL_SCOPE
            var_types[(scope, v["name"])] = v.get("type", "")

        lines: list[str] = []
        # GLOBAL first, then characters in insertion order
        scopes = list(state_vars.keys())
        if GLOBAL_SCOPE in scopes:
            scopes.remove(GLOBAL_SCOPE)
            scopes.insert(0, GLOBAL_SCOPE)

        for scope in scopes:
            vars_dict = state_vars.get(scope, {})
            if not vars_dict:
                continue
            if scope != GLOBAL_SCOPE:
                lines.append(f"[{scope}]")
            for name, value in vars_dict.items():
                prefix = "  " if scope != GLOBAL_SCOPE else ""
                if var_types.get((scope, name)) == "number":
                    lines.append(f"{prefix}{name}: {value} / 100")
                else:
                    lines.append(f"{prefix}{name}: {value}")
        return "\n".join(lines)

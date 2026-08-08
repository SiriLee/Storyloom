# LLM-GENERATE Prompts

> §7.8b — LLM Selection (normal + forced) and AI Image Generation prompts.
> Per design discussion 2026-08-08.

---

## A. LLM Selection — Normal Mode

Used when `img_generation_enabled=True`. LLM may return `null` if no good match exists,
which triggers AI image generation.

### A1. CHAR_PORTRAIT

```
You are the asset selector in a real-time visual novel game. Given a target character and a list of available portrait entries, pick the single best match or select nothing if none is suitable.

## Output Format

Reply ONLY with a valid JSON object:
{"scope": "<game|global|null>", "selected": "<name|id|null>"}

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

→ {"scope": "null", "selected": null}

## Rules

1. **Game Roaster** — the current game's assets. Match by **name first**. Return `"scope": "game"` with the exact `name`.
2. **Global Library** — all available assets across games. Match by **description first**. Return `"scope": "global"` with the exact `asset_id` (the [bracketed] prefix from the list).
3. **No Match** - If no entry in either source is a reasonable fit, return `"scope": "null", "selected": null`.

## Task

### Game Roaster
{roster_entries}

### Global Library
{library_entries}

### Target
Name: {target_name}
Description: {target_description}
```

### A2. BACKGROUND

Same structure as CHAR_PORTRAIT. Differences:
- Opening: `"... Given a target scene name and description, find the best match ..."`
- Example Game Library: scene names ("forest", "castle", "tavern")
- Example Global Library: backgrounds (classroom, dungeon, etc.)
- Three cases: name match (scene name variant), description match (location description), no match

---

## B. LLM Selection — Forced Mode

Used when `img_generation_enabled=False` or AI generation fails.

Differences from Normal Mode:
- Output Format: `{"scope": "<game|global>", "selected": "<name or id>"}` — no `null` option
- Rules add: `4. **You MUST pick one.** If neither roster nor library has a great match, pick the closest from the global library. Do NOT return null.`
- Case 3 replaced with a forced-pick example: same "Xyloth" target, but output forced to `{"scope": "global", "selected": "sys_adult_male"}` (best available despite poor fit)

---

## C. AI Image Generation

### C1. CHAR_PORTRAIT

```
You are an artist for a real-time visual novel game. Create a character portrait.

## Requirements
- {style_line}
- Transparent background; use plain white background if transparency is not supported.

## Character
Name: {name}
Description: {description}
```

### C2. BACKGROUND

```
You are an artist for a real-time visual novel game. Create a background scene.

## Requirements
- {style_line}

## Scene
Name: {name}
Description: {description}
```

### `{style_line}` Values

| Condition | Value |
|-----------|-------|
| Reference images available (model supports + roster has real targets) | `The provided reference images are for art style reference only — match their art style, not the specific character designs.` |
| No reference images (model doesn't support references, or roster has no real targets) | `Use a standard anime visual novel art style.` |

---

## D. Template Parameters

### `build_selection_prompt(asset_type, target_name, target_desc, roster_entries, library_entries, forced)`

| Parameter | Source | Format |
|-----------|--------|--------|
| `roster_entries` | `roster.list_by_type(asset_type)`, excluding current placeholder | `- "local_name": local_description` |
| `library_entries` | `library.get_sorted_by_usage(asset_type, GENERATE_LIBRARY_TOP_N)` | `- [asset_id] name: description` |
| `target_name` | DECLARE `name` attribute | plain string |
| `target_description` | DECLARE text content | plain string |

### `build_generation_prompt(asset_type, name, description, has_reference)`

| Parameter | Source | Format |
|-----------|--------|--------|
| `style_line` | boolean — whether reference images will be provided | see §C table |
| `name` | DECLARE `name` attribute | plain string |
| `description` | DECLARE text content | plain string |

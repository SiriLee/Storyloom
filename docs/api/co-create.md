# Co-Creation API

> **Audience:** UI developers integrating the co-creation phase.
> **Authoritative spec:** `docs/spec/exec-flow.md` §3

The co-creation phase is a guided Q&A flow between the player and the LLM.
It produces a dict containing story configuration, characters, locations,
variables, and outline — pass it to `GameSession.start_game()` to begin
the narrative.

## Entry Point

Use `GameSession` as the entry point:

```python
from storyloom.core import GameSession

session = GameSession()
flow = session.new_co_create()  # → CoCreateFlow
```

## State Machine API

`CoCreateFlow` exposes a simple state machine. The engine has no UI
dependency — each method call is self-contained, ideal for web UIs
where each step is a separate HTTP request.

### Phase Diagram

```
init  →  awaiting_idea  →  awaiting_answer  →  complete
                                    ↓
                                aborted
```

### Methods

#### `start() → dict`

Begin co-creation. Must be called once before any `send()`.

```python
event = flow.start()
# → {"phase": "awaiting_idea", "prompt": "Describe the story you'd like to play..."}
```

Raises `RuntimeError` if already started.

#### `send(user_input: str) → str`

Forward a user message to the LLM and return the reply text. **Pure
message forward — no keyword detection, no phase transitions.** The UI
decides when to call `generate()` or `abort()`.

```python
reply = flow.send("A cyberpunk story set in 2087 Tokyo")
# → "That sounds exciting! Tell me more about the protagonist..."
```

- On API failure, raises `CoCreateError` (phase="send") — UI can call
  `retry_send()` to re-attempt with the same messages array.
- Raises `RuntimeError` if called before `start()` or after `abort()`.
- Raises `ValueError` if `user_input` is empty or whitespace-only.
- After returning, `phase` transitions to `"awaiting_answer"`.

> **UI responsibility:** The UI layer detects when the user wants to
> start generation (e.g. a "Generate" button, `/go` command) or quit
> (e.g. a "Back" button, `/quit` command). The engine does **not**
> inspect message content for keywords. Per `exec-flow.md` §3.3.

#### `generate() → dict`

Inject the generation prompt, call the LLM, parse the JSON response,
and validate all fields.

```python
result = flow.generate()
# → {"story_config": {...}, "characters": [...], "locations": [...],
#    "variables": [...], "outline": [...], "outline_text": "..."}
```

- Must be in `"awaiting_answer"` phase; raises `RuntimeError` otherwise.
- On API failure, raises `CoCreateError` (phase="generate_api") — UI can
  call `retry_generate()` to re-attempt.
- On JSON parse failure, raises `CoCreateError` (phase="generate_parse")
  with a generic format hint.
- On field validation failure, raises `CoCreateError` (phase="generate_parse")
  with a description of which fields failed and why.
- On success, `phase` → `"complete"` and `result` is set.

#### `abort() → None`

Abort co-creation immediately. Sets `phase` to `"aborted"`.

```python
flow.abort()
```

#### `retry_send() → str`

Re-attempt the last failed `send()` API call. The user message is
preserved in the conversation array — no need to pass it again.

```python
try:
    reply = flow.send(user_input)
except CoCreateError as e:
    if e.phase == "send":
        reply = flow.retry_send()   # re-calls API with same messages
```

Raises `RuntimeError` if no failed send to retry.

#### `retry_generate() → dict`

Re-attempt the last failed `generate()`. For API failures, re-sends the
same messages. For parse/validation failures, appends a correction
prompt before calling the API.

```python
try:
    result = flow.generate()
except CoCreateError as e:
    if e.phase in ("generate_api", "generate_parse"):
        result = flow.retry_generate()   # re-calls API with correction
```

Raises `RuntimeError` if no failed generation to retry.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `phase` | `str` | Current phase: `"init"` \| `"awaiting_idea"` \| `"awaiting_answer"` \| `"complete"` \| `"aborted"` |
| `result` | `dict \| None` | Result when `phase == "complete"`, `None` otherwise |
| `messages` | `list[dict]` | Full conversation messages (system prompt, Q&A turns, generation prompt + response). For debug / prompt saving. |

### Error Handling

Errors during co-creation are propagated as `CoCreateError` exceptions. The `phase` field indicates which retry method to call:

| Method | Failure | Exception |
|--------|---------|-----------|
| `send()` | API failure | `CoCreateError` (phase="send") |
| `send()` | Wrong phase / empty input | `RuntimeError` / `ValueError` |
| `generate()` | API failure | `CoCreateError` (phase="generate_api") |
| `generate()` | Parse/validation failure | `CoCreateError` (phase="generate_parse") |
| `generate()` | Wrong phase | `RuntimeError` |

UI code should wrap these calls in try/except and present appropriate
messages to the user.

### Usage Example

```python
from storyloom.core import GameSession, CoCreateError

session = GameSession()
flow = session.new_co_create()

# Step 1 — collect story idea
event = flow.start()
print(event["prompt"])          # "Describe the story you'd like to play..."

# Step 2 — Q&A loop (UI-driven)
idea = get_user_input()         # e.g. "A cyberpunk love story"
try:
    reply = flow.send(idea)
    print(reply)                # LLM asks a follow-up question
except CoCreateError as e:
    if ask_retry():
        reply = flow.retry_send()
    else:
        return

# ... more Q&A turns as needed ...

# Step 3 — user triggers generation (UI decides when)
if user_wants_to_generate():
    try:
        result = flow.generate()
        gl, game_id = session.start_game(result)
        # game_id is used for subsequent save operations
    except CoCreateError as e:
        if ask_retry():
            result = flow.retry_generate()
        else:
            show_error("Generation failed. Returning to menu.")
```

## Output

`generate()` returns a dict with the following keys:

| Key | Type | Description |
|-----|------|-------------|
| `story_config` | `dict` | `tier`, `title`, `language`, `premise` |
| `characters` | `list[dict]` | Each: `name`, `role`, `description`, `appearance` |
| `locations` | `list[dict]` | Each: `id`, `name`, `description` |
| `variables` | `list[dict]` | Each: `name`, `type`, `initial` |
| `outline` | `list[dict]` | Each: `id`, `title`, `goal`, `routes` |
| `outline_text` | `str` | Formatted outline tree for prompt injection |

Pass the dict to ``GameSession.start_game()`` — it returns
``(GameLoop, game_id)``, handling ``GameState`` creation, ``GameLoop``
construction, and auto-save wiring.

## Validation

The engine validates all LLM output during generation:

- **JSON format:** must be valid JSON. Parse failures return a generic
  format hint to the LLM for retry.
- **story_config:** tier must be `short`/`medium`/`long`, title 1–30
  chars, language must be a supported code, premise non-empty.
- **characters:** non-empty array, exactly one `role: "protagonist"`,
  all required fields non-empty, role must be a valid enum value.
- **locations:** non-empty array, `id` must be snake_case, `name` and
  `description` non-empty.
- **variables:** ≤3 total, ≤2 number, ≤1 string. Number initial values
  in [0, 100]. Names must be unique. Type must be `"number"` or `"string"`.
- **outline:** non-empty array. Every route `target` must match an
  existing node `id`. Final node's `routes` must be empty. Route
  conditions may only reference declared variables.

Failures raise `CoCreateError` with a specific `phase` and error
description. The UI presents the error to the user, who can retry
(via `retry_generate()`) or return to the menu.

## Reference

| Resource | Content |
|----------|---------|
| `src/storyloom/core/co_create.py` | Implementation |
| `src/storyloom/core/session.py` | Entry point (`GameSession`) |
| `docs/spec/exec-flow.md` §3 | Authoritative flow spec |
| `docs/spec/prompt-design.md` §3 | Prompt templates, validation rules |
| `docs/spec/data-model.md` §A.2 | Configurable constants |
| `docs/api/session.md` | GameSession integration API — narrative loop, save/load |

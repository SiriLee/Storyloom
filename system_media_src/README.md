# System Media Assets — Workflow

`system_media_src/` is the **declarative source of truth** for all system
(built-in) media assets.  Each file defines `name`, `description`, and
`prompt` per asset.  The downstream `system_media/` directory and its
`_manifest.json` are **generated** from these sources — never hand-edited.

## Data flow

```
system_media_src/{type}.json        ← source of truth (you edit THIS)
        │
        ├── scripts/sysgen/generate_system_assets.py   → system_media/{type}/sys_*.png
        │
        └── scripts/sysgen/generate_manifest.py        → system_media/_manifest.json
                                           (name + description only;
                                            prompt is stripped)
```

## Adding a new system asset

1. **Edit `system_media_src/{type}.json`** — add an entry with `name`,
   `description`, and `prompt`.  Follow the existing style:
   - `name`: short human-readable label (1-5 words, title case)
   - `description`: one sentence describing key visual elements, used by
     the LLM matcher to disambiguate assets — be culturally and visually
     specific
   - `prompt`: image-generation prompt, always ending with
     *"Japanese anime visual novel style. Background art, wide establishing shot. … Atmospheric lighting, natural colors. Clean lineart, soft cel shading. No characters, no people, no text. High quality professional illustration."*

2. **Generate the image:**
   ```bash
   python scripts/sysgen/generate_system_assets.py --only sys_new_id --model <model>
   ```
   (Omit `--model` to use the default from config.json.)

3. **Regenerate the manifest:**
   ```bash
   python scripts/sysgen/generate_manifest.py --version <new-version>
   ```

## Modifying an existing asset (description only)

1. Edit the `description` (and `prompt` if desired) in
   `system_media_src/{type}.json`.
2. Run `python scripts/sysgen/generate_manifest.py --version <new-version>`.
3. If the prompt changed and you want a new image, run:
   ```bash
   python scripts/sysgen/generate_system_assets.py --only sys_id --force --model <model>
   ```

## Key scripts

| Script | Purpose |
|--------|---------|
| `scripts/sysgen/generate_system_assets.py` | Generate PNG images from prompts |
| `scripts/sysgen/generate_manifest.py` | Write `_manifest.json` from source metadata |
| `scripts/sysgen/_sysgen_utils.py` | Shared helpers (asset lookup, output paths) |
| `scripts/pack_system_media.sh` | Package `system_media/` into a distributable ZIP |

## File roles

| File | Role |
|------|------|
| `system_media_src/char_portrait.json` | Character portrait definitions (25 entries) |
| `system_media_src/background_img.json` | Background image definitions (26 entries) |
| `system_media/_manifest.json` | **Generated.**  Runtime manifest consumed by `AssetLibrary.import_system_assets()` |
| `system_media/VERSION` | **Generated.**  Semantic version — bump via `--version` on manifest regeneration |
| `system_media/{type}/sys_*.png` | **Generated.**  Rendered images |

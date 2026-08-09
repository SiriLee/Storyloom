"""Image generation prompt templates — shared by GenerateProcessor and Prebuilder.

Pure data module — no internal dependencies.  Prompts are text templates
consumed by ``ImgApiClient.generate()`` via ``generate_asset_image()``.

Per design.md §5.6: type-specific prompts with style guidance and optional
reference-image instructions.
"""

from __future__ import annotations

from storyloom.assets import AssetType

# ═══════════════════════════════════════════════════════════════════════
# Prompt templates
# ═══════════════════════════════════════════════════════════════════════

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
        Complete prompt string ready for ``ImgApiClient.generate()``.
    """
    style_line = _STYLE_WITH_REF if has_reference else _STYLE_WITHOUT_REF
    template = _GEN_CHAR if asset_type == AssetType.CHAR_PORTRAIT else _GEN_BG
    return template.format(style_line=style_line, name=name, description=description)

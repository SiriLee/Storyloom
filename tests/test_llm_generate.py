"""Tests for §7.8b LLM generate — prompt templates, reference collection,
LLM selection, forced selection, image save, full processor, and integration.

TDD order (matches plan):
  1. TestGeneratePrompts
  2. TestCollectReferenceImages
  3. TestLLMSelection
  4. TestForcedSelection
  5. TestImageSave
  6. TestGenerateProcessor
  7. TestGenerateProcessorIntegration
"""

import base64
import os
import threading
from collections import deque
from io import BytesIO

import pytest

from storyloom.assets import AssetItem, AssetLibrary, AssetType, GameAssetRoster
from storyloom.config import GENERATE_LIBRARY_TOP_N, GENERATE_REF_IMAGE_COUNT
from storyloom.io._types import ImageResult, RemoveBgPolicy
from storyloom.io.api_client import ApiError
from storyloom.tasks import Task, TaskPool, TaskType


# ═══════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════

@pytest.fixture
def library():
    """Fresh AssetLibrary in a temp directory."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        yield AssetLibrary(d)


@pytest.fixture
def roster(library):
    """Fresh GameAssetRoster."""
    return GameAssetRoster("test_generate", library)


@pytest.fixture
def roster_with_entries(roster, library):
    """Roster with CHAR_PORTRAIT entries (one placeholder)."""
    # Assets must exist in library before roster references them
    for aid, name in [("alice_id_01", "Alice"),
                      ("bob_id_02", "Bob")]:
        if library.get(AssetType.CHAR_PORTRAIT, aid) is None:
            library.add(AssetType.CHAR_PORTRAIT, name, "", asset_id=aid)
    roster.add(AssetType.CHAR_PORTRAIT, "Alice", "A young woman with silver hair",
               target="alice_id_01")
    roster.add(AssetType.CHAR_PORTRAIT, "Bob", "A tall warrior in plate armor",
               target="bob_id_02")
    # Placeholder entry (target=None) — should be excluded from prompt
    roster.add(AssetType.CHAR_PORTRAIT, "NewChar", "A mysterious stranger",
               target=None)
    return roster


@pytest.fixture
def library_with_entries(library):
    """AssetLibrary with CHAR_PORTRAIT entries."""
    library.add(AssetType.CHAR_PORTRAIT, "Adult Woman", "Adult woman, neutral expression",
                asset_id="lib_adult_female")
    library.add(AssetType.CHAR_PORTRAIT, "Elf Archer", "Female elf archer in a green cloak",
                asset_id="a1b2c3d4")
    library.add(AssetType.CHAR_PORTRAIT, "Adult Man", "Adult man, neutral expression",
                asset_id="lib_adult_male")
    return library


# ═══════════════════════════════════════════════════════════════════════
# FakeApiClient — controllable mock (same pattern as test_llm_match.py)
# ═══════════════════════════════════════════════════════════════════════

class FakeApiClient:
    """Mock ApiClient that records calls and returns configurable responses."""

    def __init__(self, responses=None, model="deepseek-v4-pro"):
        self.responses = list(responses) if responses else []
        self.calls: list[dict] = []
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def chat(self, messages, max_tokens=None, response_format=None,
             extra_params=None):
        self.calls.append({
            "messages": messages,
            "max_tokens": max_tokens,
            "response_format": response_format,
            "extra_params": extra_params,
        })
        if not self.responses:
            return '{"selected": "hero"}'
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


# ═══════════════════════════════════════════════════════════════════════
# 1. TestGeneratePrompts
# ═══════════════════════════════════════════════════════════════════════

class TestGeneratePrompts:
    """Prompt template rendering — selection and generation prompts."""

    # ── Selection prompt — normal mode ──────────────────────────────────

    def test_selection_normal_has_output_format_with_null(self, roster_with_entries,
                                                          library_with_entries):
        """Normal mode Output Format includes null option."""
        from storyloom.tasks._llm_generate import build_selection_prompt

        prompt = build_selection_prompt(
            AssetType.CHAR_PORTRAIT, "Alice.happy",
            "A young woman with silver hair, smiling brightly",
            roster_with_entries, library_with_entries, forced=False,
        )
        assert '"scope": "<game|global|null>"' in prompt
        assert '"selected": "<name|id|null>"' in prompt

    def test_selection_normal_rules_no_forced_clause(self, roster_with_entries,
                                                     library_with_entries):
        """Normal mode does NOT have the forced-pick rule."""
        from storyloom.tasks._llm_generate import build_selection_prompt

        prompt = build_selection_prompt(
            AssetType.CHAR_PORTRAIT, "Alice.happy",
            "A young woman with silver hair",
            roster_with_entries, library_with_entries, forced=False,
        )
        assert "You MUST pick one" not in prompt

    # ── Selection prompt — forced mode ──────────────────────────────────

    def test_selection_forced_no_null_in_output_format(self, roster_with_entries,
                                                       library_with_entries):
        """Forced mode Output Format does NOT include null."""
        from storyloom.tasks._llm_generate import build_selection_prompt

        prompt = build_selection_prompt(
            AssetType.CHAR_PORTRAIT, "Alice.happy",
            "A young woman with silver hair",
            roster_with_entries, library_with_entries, forced=True,
        )
        assert '"scope": "<game|global>"' in prompt
        assert '"selected": "<name|id>"' in prompt
        assert "null" not in prompt.split("Output Format")[1].split("##")[0]

    def test_selection_forced_has_must_pick_rule(self, roster_with_entries,
                                                  library_with_entries):
        """Forced mode adds the 'must pick one' rule."""
        from storyloom.tasks._llm_generate import build_selection_prompt

        prompt = build_selection_prompt(
            AssetType.CHAR_PORTRAIT, "Alice.happy",
            "A young woman with silver hair",
            roster_with_entries, library_with_entries, forced=True,
        )
        assert "You MUST pick one" in prompt

    # ── Selection prompt — entries formatting ───────────────────────────

    def test_roster_entries_format(self, roster_with_entries, library_with_entries):
        """Roster entries: '- "name": description', all entries included."""
        from storyloom.tasks._llm_generate import build_selection_prompt

        prompt = build_selection_prompt(
            AssetType.CHAR_PORTRAIT, "Alice.happy",
            "A young woman with silver hair",
            roster_with_entries, library_with_entries, forced=False,
        )
        assert '- "Alice": A young woman with silver hair' in prompt
        assert '- "Bob": A tall warrior in plate armor' in prompt
        # Placeholder entries (target=None) are included — they represent
        # entities the game knows about.  Only the current DECLARE's own
        # entry (exclude_name) is excluded.
        assert '"NewChar"' in prompt

    def test_library_entries_format(self, roster_with_entries, library_with_entries):
        """Library entries: '- [asset_id] "name": description'."""
        from storyloom.tasks._llm_generate import build_selection_prompt

        prompt = build_selection_prompt(
            AssetType.CHAR_PORTRAIT, "Alice.happy",
            "A young woman with silver hair",
            roster_with_entries, library_with_entries, forced=False,
        )
        assert '- [lib_adult_female] "Adult Woman": Adult woman, neutral expression' in prompt
        assert '- [a1b2c3d4] "Elf Archer": Female elf archer in a green cloak' in prompt

    def test_library_respects_top_n(self, roster_with_entries, library):
        """Library entries truncated to GENERATE_LIBRARY_TOP_N."""
        from storyloom.tasks._llm_generate import build_selection_prompt

        # Add more than TOP_N entries
        for i in range(GENERATE_LIBRARY_TOP_N + 5):
            aid = f"asset_{i:04d}"
            library.add(AssetType.CHAR_PORTRAIT, f"Char {i}", f"Description {i}",
                        asset_id=aid)

        prompt = build_selection_prompt(
            AssetType.CHAR_PORTRAIT, "test",
            "test description",
            roster_with_entries, library, forced=False,
        )

        # Count library entries in the Task section only (not Example)
        task_start = prompt.index("## Task")
        task_section = prompt[task_start:]
        lib_entry_count = task_section.count("\n- [")
        assert lib_entry_count <= GENERATE_LIBRARY_TOP_N

    def test_target_included(self, roster_with_entries, library_with_entries):
        """Target name and description appear in the prompt."""
        from storyloom.tasks._llm_generate import build_selection_prompt

        prompt = build_selection_prompt(
            AssetType.CHAR_PORTRAIT, "TestName",
            "Test description text",
            roster_with_entries, library_with_entries, forced=False,
        )
        assert "Name: TestName" in prompt
        assert "Description: Test description text" in prompt

    def test_char_intro_mentions_character(self, roster_with_entries, library_with_entries):
        """CHAR_PORTRAIT system prompt mentions 'character'."""
        from storyloom.tasks._llm_generate import build_selection_prompt

        prompt = build_selection_prompt(
            AssetType.CHAR_PORTRAIT, "test", "desc",
            roster_with_entries, library_with_entries, forced=False,
        )
        assert "target character" in prompt

    def test_background_intro_mentions_scene(self, roster, library_with_entries):
        """BACKGROUND system prompt mentions 'scene'."""
        from storyloom.tasks._llm_generate import build_selection_prompt

        # Create library asset first, then add roster entry
        library_with_entries.add(AssetType.BACKGROUND, "Forest", "A dark forest",
                                 asset_id="bg_forest_01")
        roster.add(AssetType.BACKGROUND, "forest", "A dark enchanted forest",
                   target="bg_forest_01")

        prompt = build_selection_prompt(
            AssetType.BACKGROUND, "Deep Woods", "An ancient forest with towering redwoods",
            roster, library_with_entries, forced=False,
        )
        assert "target scene" in prompt

    # ── Generation prompt ───────────────────────────────────────────────

    def test_gen_char_has_transparent_bg_requirement(self):
        """CHAR generation prompt includes transparent background requirement."""
        from storyloom.io.img_prompts import build_generation_prompt

        prompt = build_generation_prompt(
            AssetType.CHAR_PORTRAIT, "Alice",
            "A young woman with silver hair",
            has_reference=True,
        )
        assert "Transparent background" in prompt
        assert "plain white background" in prompt

    def test_gen_bg_no_transparent_requirement(self):
        """BACKGROUND generation prompt does NOT mention transparent bg."""
        from storyloom.io.img_prompts import build_generation_prompt

        prompt = build_generation_prompt(
            AssetType.BACKGROUND, "Forest",
            "A dark enchanted forest",
            has_reference=True,
        )
        assert "Transparent background" not in prompt
        assert "plain white background" not in prompt

    def test_gen_char_has_character_section(self):
        """CHAR generation prompt uses '## Character' heading."""
        from storyloom.io.img_prompts import build_generation_prompt

        prompt = build_generation_prompt(
            AssetType.CHAR_PORTRAIT, "Alice", "Desc", has_reference=True,
        )
        assert "## Character" in prompt
        assert "Name: Alice" in prompt
        assert "Description: Desc" in prompt

    def test_gen_bg_has_scene_section(self):
        """BACKGROUND generation prompt uses '## Scene' heading."""
        from storyloom.io.img_prompts import build_generation_prompt

        prompt = build_generation_prompt(
            AssetType.BACKGROUND, "Forest", "Desc", has_reference=True,
        )
        assert "## Scene" in prompt
        assert "Name: Forest" in prompt
        assert "Description: Desc" in prompt

    def test_style_line_with_reference(self):
        """has_reference=True → art style reference line."""
        from storyloom.io.img_prompts import build_generation_prompt

        prompt = build_generation_prompt(
            AssetType.CHAR_PORTRAIT, "Alice", "Desc", has_reference=True,
        )
        assert "art style reference only" in prompt
        assert "match their art style" in prompt

    def test_style_line_without_reference(self):
        """has_reference=False → standard anime style line."""
        from storyloom.io.img_prompts import build_generation_prompt

        prompt = build_generation_prompt(
            AssetType.CHAR_PORTRAIT, "Alice", "Desc", has_reference=False,
        )
        assert "standard anime visual novel art style" in prompt

    def test_gen_prompt_role_declaration(self):
        """Generation prompt opens with artist role declaration."""
        from storyloom.io.img_prompts import build_generation_prompt

        prompt = build_generation_prompt(
            AssetType.CHAR_PORTRAIT, "Alice", "Desc", has_reference=True,
        )
        assert prompt.startswith("You are an artist for a real-time visual novel game.")


# ═══════════════════════════════════════════════════════════════════════
# 2. TestCollectReferenceImages
# ═══════════════════════════════════════════════════════════════════════

def _make_png(width: int, height: int) -> bytes:
    """Create a minimal valid RGBA PNG with the given dimensions."""
    import struct
    import zlib

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw_rows = b"".join(
        b"\x00" + b"\xff\x00\x00\xff" * width for _ in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw_rows))
        + chunk(b"IEND", b"")
    )


class TestCollectReferenceImages:
    """_collect_reference_images — roster → base64 data URLs."""

    @pytest.fixture
    def media_library(self, tmp_path):
        """AssetLibrary with real image files on disk."""
        from storyloom.io.img_utils import normalize_background
        lib = AssetLibrary(str(tmp_path / "media"))
        # Create asset type directories
        for atype in AssetType:
            (tmp_path / "media" / atype.value).mkdir(parents=True, exist_ok=True)

        # Create test PNG files and add to library
        self._img_ids: dict[AssetType, list[str]] = {
            AssetType.CHAR_PORTRAIT: [],
            AssetType.BACKGROUND: [],
        }
        for atype in AssetType:
            for i in range(4):
                aid = f"ref_{atype.value}_{i}"
                path = tmp_path / "media" / atype.value / f"{aid}.png"
                path.write_bytes(_make_png(64, 64))
                lib.add(atype, f"Ref {i}", f"Description {i}", asset_id=aid)
                self._img_ids[atype].append(aid)
        return lib

    def test_three_images_returned(self, media_library):
        """Roster with 4 real targets → returns 3 base64 data URLs."""
        from storyloom.tasks._llm_generate import _collect_reference_images

        roster = GameAssetRoster("test_ref", media_library)
        for i in range(4):
            aid = self._img_ids[AssetType.CHAR_PORTRAIT][i]
            roster.add(AssetType.CHAR_PORTRAIT, f"Char{i}", f"Desc{i}", target=aid)

        refs = _collect_reference_images(
            AssetType.CHAR_PORTRAIT, roster, "OtherChar", "flux-2-pro",
        )
        assert len(refs) == GENERATE_REF_IMAGE_COUNT
        for ref in refs:
            assert ref.startswith("data:image/png;base64,")

    def test_fewer_than_three(self, media_library):
        """With GENERATE_REF_IMAGE_COUNT=0, returns empty list regardless
        of available targets.  (When count > 0, this test would verify
        that fewer targets than the limit returns all available.)"""
        from storyloom.tasks._llm_generate import _collect_reference_images

        roster = GameAssetRoster("test_ref", media_library)
        for i in range(2):
            aid = self._img_ids[AssetType.CHAR_PORTRAIT][i]
            roster.add(AssetType.CHAR_PORTRAIT, f"Char{i}", f"Desc{i}", target=aid)

        refs = _collect_reference_images(
            AssetType.CHAR_PORTRAIT, roster, "OtherChar", "flux-2-pro",
        )
        assert len(refs) == 0

    def test_empty_roster(self, media_library):
        """Empty roster → empty list."""
        from storyloom.tasks._llm_generate import _collect_reference_images

        roster = GameAssetRoster("test_ref", media_library)
        refs = _collect_reference_images(
            AssetType.CHAR_PORTRAIT, roster, "OtherChar", "flux-2-pro",
        )
        assert refs == []

    def test_placeholder_excluded(self, media_library):
        """Entries with target=None are skipped."""
        from storyloom.tasks._llm_generate import _collect_reference_images

        roster = GameAssetRoster("test_ref", media_library)
        # Only placeholders
        roster.add(AssetType.CHAR_PORTRAIT, "Char0", "Desc0", target=None)
        roster.add(AssetType.CHAR_PORTRAIT, "Char1", "Desc1", target=None)

        refs = _collect_reference_images(
            AssetType.CHAR_PORTRAIT, roster, "OtherChar", "flux-2-pro",
        )
        assert refs == []

    def test_current_entry_excluded(self, media_library):
        """With GENERATE_REF_IMAGE_COUNT=0, returns empty list.
        (When count > 0, the current DECLARE's own entry would be
        excluded while other entries are included.)"""
        from storyloom.tasks._llm_generate import _collect_reference_images

        roster = GameAssetRoster("test_ref", media_library)
        aid = self._img_ids[AssetType.CHAR_PORTRAIT][0]
        roster.add(AssetType.CHAR_PORTRAIT, "CurrentChar", "Current desc", target=aid)
        # Also add another entry
        aid2 = self._img_ids[AssetType.CHAR_PORTRAIT][1]
        roster.add(AssetType.CHAR_PORTRAIT, "OtherChar", "Other desc", target=aid2)

        refs = _collect_reference_images(
            AssetType.CHAR_PORTRAIT, roster, "CurrentChar", "flux-2-pro",
        )
        assert len(refs) == 0

    def test_model_no_reference_support(self, media_library):
        """Model with supports_reference=False → empty list, no file reads."""
        from storyloom.tasks._llm_generate import _collect_reference_images

        roster = GameAssetRoster("test_ref", media_library)
        for i in range(3):
            aid = self._img_ids[AssetType.CHAR_PORTRAIT][i]
            roster.add(AssetType.CHAR_PORTRAIT, f"Char{i}", f"Desc{i}", target=aid)

        refs = _collect_reference_images(
            AssetType.CHAR_PORTRAIT, roster, "OtherChar",
            "nano-banana",  # supports_reference=False
        )
        assert refs == []

    def test_file_missing_on_disk_skipped(self, media_library, tmp_path):
        """Asset in library but file missing → skipped gracefully."""
        from storyloom.tasks._llm_generate import _collect_reference_images

        roster = GameAssetRoster("test_ref", media_library)
        # Add a library asset but delete the file
        aid = "missing_file_01"
        path = tmp_path / "media" / AssetType.CHAR_PORTRAIT.value / f"{aid}.png"
        path.write_bytes(_make_png(64, 64))
        media_library.add(AssetType.CHAR_PORTRAIT, "Missing", "desc", asset_id=aid)
        roster.add(AssetType.CHAR_PORTRAIT, "MissingChar", "desc", target=aid)
        # Delete the file
        path.unlink()

        refs = _collect_reference_images(
            AssetType.CHAR_PORTRAIT, roster, "OtherChar", "flux-2-pro",
        )
        # Missing file skipped — no crash, empty result
        assert refs == []

    def test_different_asset_type_not_mixed(self, media_library):
        """CHAR_PORTRAIT collection does not include BACKGROUND entries."""
        from storyloom.tasks._llm_generate import _collect_reference_images

        roster = GameAssetRoster("test_ref", media_library)
        # Add CHAR entries
        for i in range(3):
            aid = self._img_ids[AssetType.CHAR_PORTRAIT][i]
            roster.add(AssetType.CHAR_PORTRAIT, f"Char{i}", f"Desc{i}", target=aid)
        # Add BG entries — should be ignored when collecting CHAR refs
        for i in range(3):
            aid = self._img_ids[AssetType.BACKGROUND][i]
            roster.add(AssetType.BACKGROUND, f"Bg{i}", f"Desc{i}", target=aid)

        refs = _collect_reference_images(
            AssetType.CHAR_PORTRAIT, roster, "OtherChar", "flux-2-pro",
        )
        assert len(refs) == GENERATE_REF_IMAGE_COUNT


# ═══════════════════════════════════════════════════════════════════════
# 3. TestLLMSelection
# ═══════════════════════════════════════════════════════════════════════

class TestLLMSelection:
    """_select — LLM selection call + response parsing."""

    @pytest.fixture
    def sel_roster(self, library):
        """Roster with one entry for selection tests."""
        library.add(AssetType.CHAR_PORTRAIT, "Hero", "", asset_id="hero_001")
        r = GameAssetRoster("test_sel", library)
        r.add(AssetType.CHAR_PORTRAIT, "hero", "A brave knight", target="hero_001")
        return r

    @pytest.fixture
    def sel_library(self, library):
        """Library with entries for selection tests."""
        library.add(AssetType.CHAR_PORTRAIT, "Adult Woman", "Adult woman, neutral",
                    asset_id="lib_female_01")
        library.add(AssetType.CHAR_PORTRAIT, "Elf Archer", "Female elf archer",
                    asset_id="lib_elf_01")
        return library

    def test_game_scope_returns_asset_id(self, sel_roster, sel_library):
        """scope='game' → resolve local_name to asset_id via roster."""
        from storyloom.tasks._llm_generate import _select

        api = FakeApiClient(responses=['{"scope": "game", "selected": "hero"}'])
        result = _select(api, AssetType.CHAR_PORTRAIT, "hero_knight",
                         "A brave knight in armor", sel_roster, sel_library,
                         forced=False)
        assert result == "hero_001"
        assert len(api.calls) == 1

    def test_global_scope_returns_asset_id(self, sel_roster, sel_library):
        """scope='global' → return the asset_id directly."""
        from storyloom.tasks._llm_generate import _select

        api = FakeApiClient(responses=['{"scope": "global", "selected": "lib_elf_01"}'])
        result = _select(api, AssetType.CHAR_PORTRAIT, "Legolas",
                         "A tall elf with a bow", sel_roster, sel_library,
                         forced=False)
        assert result == "lib_elf_01"

    def test_null_scope_returns_none(self, sel_roster, sel_library):
        """scope='null' → return None."""
        from storyloom.tasks._llm_generate import _select

        api = FakeApiClient(responses=['{"scope": "null", "selected": null}'])
        result = _select(api, AssetType.CHAR_PORTRAIT, "Xyloth",
                         "A cosmic horror", sel_roster, sel_library,
                         forced=False)
        assert result is None

    def test_api_error_returns_none(self, sel_roster, sel_library):
        """ApiError → return None (graceful degradation)."""
        from storyloom.tasks._llm_generate import _select

        api = FakeApiClient(responses=[ApiError("timeout")])
        result = _select(api, AssetType.CHAR_PORTRAIT, "hero",
                         "desc", sel_roster, sel_library, forced=False)
        assert result is None

    def test_invalid_json_returns_none(self, sel_roster, sel_library):
        """Non-JSON response → return None."""
        from storyloom.tasks._llm_generate import _select

        api = FakeApiClient(responses=["garbage text not json"])
        result = _select(api, AssetType.CHAR_PORTRAIT, "hero",
                         "desc", sel_roster, sel_library, forced=False)
        assert result is None

    def test_valid_json_wrong_selected_returns_none(self, sel_roster, sel_library):
        """Valid JSON but 'selected' not in entries → return None."""
        from storyloom.tasks._llm_generate import _select

        api = FakeApiClient(responses=['{"scope": "game", "selected": "nonexistent"}'])
        result = _select(api, AssetType.CHAR_PORTRAIT, "hero",
                         "desc", sel_roster, sel_library, forced=False)
        assert result is None

    def test_uses_disabled_thinking_by_default(self, sel_roster, sel_library):
        """LLM call uses disabled thinking by default (prompt_lab 15/15 pass)."""
        from storyloom.tasks._llm_generate import _select

        api = FakeApiClient(responses=['{"scope": "game", "selected": "hero"}'])
        _select(api, AssetType.CHAR_PORTRAIT, "hero", "desc",
                sel_roster, sel_library, forced=False)
        extra = api.calls[0]["extra_params"]
        assert extra == {"thinking": {"type": "disabled"}}  # DeepSeek disabled

    def test_uses_json_response_format(self, sel_roster, sel_library):
        """LLM call includes response_format={'type': 'json_object'}."""
        from storyloom.tasks._llm_generate import _select

        api = FakeApiClient(responses=['{"scope": "game", "selected": "hero"}'])
        _select(api, AssetType.CHAR_PORTRAIT, "hero", "desc",
                sel_roster, sel_library, forced=False)
        assert api.calls[0]["response_format"] == {"type": "json_object"}

    def test_roster_excludes_current_placeholder(self, sel_roster, sel_library):
        """Roster entries in prompt exclude the current DECLARE name."""
        from storyloom.tasks._llm_generate import _select

        sel_roster.add(AssetType.CHAR_PORTRAIT, "NewGuy", "A mysterious stranger",
                       target=None)

        api = FakeApiClient(responses=['{"scope": "game", "selected": "hero"}'])
        _select(api, AssetType.CHAR_PORTRAIT, "NewGuy", "desc",
                sel_roster, sel_library, forced=False)
        user_content = api.calls[0]["messages"][0]["content"]
        assert '"NewGuy"' not in user_content
        assert '"hero"' in user_content

    def test_forced_mode_uses_forced_prompt(self, sel_roster, sel_library):
        """_select(forced=True) uses forced-mode prompt (no null, must-pick rule)."""
        from storyloom.tasks._llm_generate import _select

        api = FakeApiClient(responses=['{"scope": "game", "selected": "hero"}'])
        _select(api, AssetType.CHAR_PORTRAIT, "hero", "desc",
                sel_roster, sel_library, forced=True)
        user_content = api.calls[0]["messages"][0]["content"]
        assert "null" not in user_content.split("Output Format")[1].split("##")[0]
        assert "You MUST pick one" in user_content


# ═══════════════════════════════════════════════════════════════════════
# 4. TestForcedSelection
# ═══════════════════════════════════════════════════════════════════════

class TestForcedSelection:
    """select_forced — must return an asset_id, with fallbacks."""

    @pytest.fixture
    def fs_roster(self, library):
        """Roster with entries for forced selection tests."""
        library.add(AssetType.CHAR_PORTRAIT, "Hero", "", asset_id="hero_001")
        r = GameAssetRoster("test_fs", library)
        r.add(AssetType.CHAR_PORTRAIT, "hero", "A brave knight", target="hero_001")
        return r

    @pytest.fixture
    def fs_library(self, library):
        """Library with a system asset and user assets."""
        # System asset (sys_ prefix) — for programmatic fallback
        library._add_system_asset(AssetType.CHAR_PORTRAIT, "sys_default",
                                  "Default Character", "A generic character")
        library.add(AssetType.CHAR_PORTRAIT, "Elf Archer", "Female elf archer",
                    asset_id="lib_elf_01")
        return library

    def test_forced_returns_asset_id(self, fs_roster, fs_library):
        """Successful forced selection returns asset_id."""
        from storyloom.tasks._llm_generate import select_forced

        api = FakeApiClient(responses=['{"scope": "game", "selected": "hero"}'])
        result = select_forced(api, AssetType.CHAR_PORTRAIT, "hero_knight",
                                "A brave knight", fs_roster, fs_library)
        assert result == "hero_001"

    def test_api_error_retries(self, fs_roster, fs_library):
        """First call raises ApiError → retry with enabled thinking → success."""
        from storyloom.tasks._llm_generate import select_forced

        api = FakeApiClient(responses=[
            ApiError("timeout"),
            '{"scope": "global", "selected": "lib_elf_01"}',
        ])
        result = select_forced(api, AssetType.CHAR_PORTRAIT, "elf",
                                "An elf", fs_roster, fs_library)
        assert result == "lib_elf_01"
        assert len(api.calls) == 2
        # First attempt: light thinking
        assert api.calls[0]["extra_params"]["thinking"]["type"] == "disabled"  # fast attempt
        # Retry: enabled (heavier) thinking
        assert api.calls[1]["extra_params"] == {}

    def test_both_attempts_fail_picks_system(self, fs_roster, fs_library):
        """Both LLM calls fail → programmatic pick from system catalog."""
        from storyloom.tasks._llm_generate import select_forced

        api = FakeApiClient(responses=[
            ApiError("network error"),
            ApiError("timeout"),
        ])
        result = select_forced(api, AssetType.CHAR_PORTRAIT, "hero",
                                "desc", fs_roster, fs_library)
        # Should pick sys_default (first sys_ asset)
        assert result == "sys_default"

    def test_empty_library_fallback(self, library):
        """Library with no assets → raises RuntimeError (defensive)."""
        from storyloom.tasks._llm_generate import select_forced

        api = FakeApiClient(responses=[
            ApiError("error"),
            ApiError("error"),
        ])
        # Fresh empty roster — no assets in library
        roster = GameAssetRoster("test_empty", library)
        import pytest as _pytest
        with _pytest.raises(RuntimeError, match="No assets available"):
            select_forced(api, AssetType.CHAR_PORTRAIT, "hero",
                           "desc", roster, library)


# ═══════════════════════════════════════════════════════════════════════
# 5. TestImageSave
# ═══════════════════════════════════════════════════════════════════════

class TestImageSave:
    """_save_image — file persistence + library registration."""

    def test_saves_png_to_media_dir(self, tmp_path):
        """Saves PNG bytes to media/{type}/{id}.png."""
        from storyloom.tasks._llm_generate import _save_image

        lib = AssetLibrary(str(tmp_path / "media"))
        raw = _make_png(64, 64)
        aid = _save_image(lib, AssetType.CHAR_PORTRAIT, "Test", "A test", raw)

        expected_path = tmp_path / "media" / "char_portrait" / f"{aid}.png"
        assert expected_path.is_file()
        assert expected_path.read_bytes() == raw

    def test_registers_in_library(self, tmp_path):
        """Asset is added to AssetLibrary with correct metadata."""
        from storyloom.tasks._llm_generate import _save_image

        lib = AssetLibrary(str(tmp_path / "media"))
        aid = _save_image(lib, AssetType.CHAR_PORTRAIT, "Hero", "A brave hero",
                          _make_png(64, 64))

        asset = lib.get(AssetType.CHAR_PORTRAIT, aid)
        assert asset is not None
        assert asset.name == "Hero"
        assert asset.description == "A brave hero"

    def test_creates_directory(self, tmp_path):
        """Creates media/{type}/ directory if missing."""
        from storyloom.tasks._llm_generate import _save_image

        lib = AssetLibrary(str(tmp_path / "media"))
        # Ensure directory doesn't exist yet
        import shutil
        media_dir = tmp_path / "media"
        if media_dir.exists():
            shutil.rmtree(media_dir)

        aid = _save_image(lib, AssetType.BACKGROUND, "Forest", "Dark forest",
                          _make_png(64, 36))
        expected = tmp_path / "media" / "background_img" / f"{aid}.png"
        assert expected.is_file()

    def test_background_saved_to_correct_dir(self, tmp_path):
        """BACKGROUND type saves to background_img/ directory."""
        from storyloom.tasks._llm_generate import _save_image

        lib = AssetLibrary(str(tmp_path / "media"))
        aid = _save_image(lib, AssetType.BACKGROUND, "Forest", "Dark forest",
                          _make_png(64, 36))
        assert os.path.join("background_img", f"{aid}.png") in str(
            tmp_path / "media" / "background_img" / f"{aid}.png"
        )


# ═══════════════════════════════════════════════════════════════════════
# FakeImgApiClient
# ═══════════════════════════════════════════════════════════════════════

class FakeImgApiClient:
    """Mock ImgApiClient for GenerateProcessor tests."""

    def __init__(self, responses=None, model="flux-2-pro",
                 remove_bg=RemoveBgPolicy.NEVER):
        self.responses = list(responses) if responses else []
        self.calls: list[dict] = []
        self._model = model
        self.remove_bg_policy = remove_bg

    @property
    def model(self) -> str:
        return self._model

    def generate(self, prompt, size, image_urls=None, remove_bg=None):
        self.calls.append({
            "prompt": prompt, "size": size, "image_urls": image_urls,
            "remove_bg": remove_bg,
        })
        if not self.responses:
            return ImageResult(
                bytes=_make_png(1024, 1024), format="png", has_alpha=True,
                width=1024, height=1024, url="", elapsed_ms=100,
            )
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


# ═══════════════════════════════════════════════════════════════════════
# 6. TestGenerateProcessor
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateProcessor:
    """GenerateProcessor — full two-phase flow with mock APIs."""

    @pytest.fixture
    def gp_library(self, tmp_path):
        """Library with assets for GenerateProcessor tests."""
        lib = AssetLibrary(str(tmp_path / "media"))
        (tmp_path / "media").mkdir(parents=True, exist_ok=True)
        for atype in AssetType:
            (tmp_path / "media" / atype.value).mkdir(parents=True, exist_ok=True)
            # Add a fallback asset of each type for forced selection
            lib._add_system_asset(atype, f"sys_fallback_{atype.value}",
                                  f"Fallback {atype.value}", "")
        return lib

    @pytest.fixture
    def gp_roster(self, gp_library):
        """Roster with entries for GenerateProcessor tests."""
        # Add library assets so roster entries have valid targets
        gp_library.add(AssetType.CHAR_PORTRAIT, "Hero", "", asset_id="hero_lib")
        r = GameAssetRoster("test_gp", gp_library)
        r.add(AssetType.CHAR_PORTRAIT, "hero", "A brave knight", target="hero_lib")
        return r

    def _make_gp(self, gp_library, api=None, img_portrait=None, img_bg=None,
                 enabled=True):
        """Create a GenerateProcessor with test dependencies."""
        from storyloom.tasks._llm_generate import GenerateProcessor

        if api is None:
            api = FakeApiClient()
        if img_portrait is None:
            img_portrait = FakeImgApiClient(remove_bg=RemoveBgPolicy.AUTO)
        if img_bg is None:
            img_bg = FakeImgApiClient(remove_bg=RemoveBgPolicy.NEVER)

        return GenerateProcessor(
            api_client=api,
            img_client_portrait=img_portrait,
            img_client_background=img_bg,
            library=gp_library,
            img_generation_enabled=enabled,
        )

    def test_selection_hit_game_scope(self, gp_library, gp_roster):
        """LLM selection hits game roster → set_target, no generation."""
        api = FakeApiClient(responses=['{"scope": "game", "selected": "hero"}'])
        proc = self._make_gp(gp_library, api=api)

        # TaskGenerator creates placeholder first, then calls processor
        gp_roster.add(AssetType.CHAR_PORTRAIT, "hero_knight", "A knight", target=None)

        task = Task(TaskType.GENERATE, 0, AssetType.CHAR_PORTRAIT)
        process = proc(AssetType.CHAR_PORTRAIT, "hero_knight", gp_roster)
        process(task)

        assert task.completed
        assert task.error is None
        item = gp_roster.lookup(AssetType.CHAR_PORTRAIT, "hero_knight")
        assert item is not None
        assert item.target == "hero_lib"

    def test_selection_null_triggers_generation(self, gp_library, gp_roster):
        """LLM returns null → AI generation runs → library.add + set_target."""
        api = FakeApiClient(responses=['{"scope": "null", "selected": null}'])
        img = FakeImgApiClient()
        proc = self._make_gp(gp_library, api=api, img_portrait=img)

        gp_roster.add(AssetType.CHAR_PORTRAIT, "NewHero", "A new hero", target=None)

        task = Task(TaskType.GENERATE, 0, AssetType.CHAR_PORTRAIT)
        process = proc(AssetType.CHAR_PORTRAIT, "NewHero",
                       gp_roster)
        process(task)

        assert task.completed
        assert task.error is None
        # One generation call
        assert len(img.calls) == 1
        # Roster entry target set
        item = gp_roster.lookup(AssetType.CHAR_PORTRAIT, "NewHero")
        assert item is not None
        assert item.target is not None

    def test_generation_failure_falls_back_to_forced(self, gp_library, gp_roster):
        """AI generation ImageApiError → forced selection → set_target."""
        from storyloom.io.img_api_client import ImageApiError

        api = FakeApiClient(responses=[
            '{"scope": "null", "selected": null}',   # selection: null
            '{"scope": "game", "selected": "hero"}',  # forced: hit
        ])
        img = FakeImgApiClient(responses=[ImageApiError("gen failed")])
        proc = self._make_gp(gp_library, api=api, img_portrait=img)

        gp_roster.add(AssetType.CHAR_PORTRAIT, "NewHero", "A hero", target=None)

        task = Task(TaskType.GENERATE, 0, AssetType.CHAR_PORTRAIT)
        process = proc(AssetType.CHAR_PORTRAIT, "NewHero",
                       gp_roster)
        process(task)

        assert task.completed
        # Forced selection set the target
        item = gp_roster.lookup(AssetType.CHAR_PORTRAIT, "NewHero")
        assert item is not None
        assert item.target == "hero_lib"

    def test_img_generation_disabled_uses_forced(self, gp_library, gp_roster):
        """img_generation_enabled=False → forced selection, no API generation."""
        api = FakeApiClient(responses=['{"scope": "game", "selected": "hero"}'])
        img = FakeImgApiClient()
        proc = self._make_gp(gp_library, api=api, img_portrait=img,
                             enabled=False)

        gp_roster.add(AssetType.CHAR_PORTRAIT, "NewHero", "A hero", target=None)

        task = Task(TaskType.GENERATE, 0, AssetType.CHAR_PORTRAIT)
        process = proc(AssetType.CHAR_PORTRAIT, "NewHero",
                       gp_roster)
        process(task)

        assert task.completed
        # No image generation was triggered
        assert len(img.calls) == 0
        item = gp_roster.lookup(AssetType.CHAR_PORTRAIT, "NewHero")
        assert item.target == "hero_lib"

    def test_background_no_bg_removal(self, gp_library, gp_roster):
        """BACKGROUND type calls generate with NEVER remove_bg and no bg removal."""
        api = FakeApiClient(responses=['{"scope": "null", "selected": null}'])
        img_bg = FakeImgApiClient(remove_bg=RemoveBgPolicy.NEVER)

        # Add BG entry to roster
        gp_library.add(AssetType.BACKGROUND, "Forest", "", asset_id="bg_forest")
        gp_roster.add(AssetType.BACKGROUND, "DeepWoods", "Ancient forest",
                      target="bg_forest")

        proc = self._make_gp(gp_library, api=api, img_bg=img_bg)

        task = Task(TaskType.GENERATE, 0, AssetType.BACKGROUND)
        process = proc(AssetType.BACKGROUND, "DeepWoods", gp_roster)
        process(task)

        assert task.completed
        # Should have used the bg client
        assert len(img_bg.calls) == 1

    def test_task_always_completed(self, gp_library, gp_roster):
        """Even on unexpected errors, task.completed is True via TaskPool."""
        api = FakeApiClient(responses=[RuntimeError("unexpected crash")])
        proc = self._make_gp(gp_library, api=api)

        gp_roster.add(AssetType.CHAR_PORTRAIT, "NewHero", "A hero", target=None)

        task = Task(TaskType.GENERATE, 0, AssetType.CHAR_PORTRAIT)
        process = proc(AssetType.CHAR_PORTRAIT, "NewHero", gp_roster)
        task.process = process

        with TaskPool(max_workers=1) as pool:
            pool.submit(task)
            task.wait(timeout=5.0)

        # TaskPool._run guarantees task.complete() in finally
        assert task.completed
        assert task.error is not None  # RuntimeError was recorded


# ═══════════════════════════════════════════════════════════════════════
# 7. TestGenerateProcessorIntegration
# ═══════════════════════════════════════════════════════════════════════

class TestGenerateProcessorIntegration:
    """GenerateProcessor via TaskPool — full async pipeline."""

    def test_full_generate_via_task_pool(self, tmp_path):
        """Task submitted to TaskPool → GenerateProcessor runs → target set."""
        from storyloom.tasks._llm_generate import GenerateProcessor

        lib = AssetLibrary(str(tmp_path / "media"))
        (tmp_path / "media").mkdir(parents=True, exist_ok=True)
        for atype in AssetType:
            (tmp_path / "media" / atype.value).mkdir(parents=True, exist_ok=True)
            lib._add_system_asset(atype, f"sys_{atype.value}",
                                  f"Fallback {atype.value}", "")

        roster = GameAssetRoster("test_int", lib)
        # Add a roster entry with placeholder (target=None) to simulate DECLARE
        roster.add(AssetType.CHAR_PORTRAIT, "NewChar", "A new character", target=None)

        api = FakeApiClient(responses=['{"scope": "null", "selected": null}'])
        img = FakeImgApiClient()
        proc = GenerateProcessor(
            api_client=api,
            img_client_portrait=img,
            img_client_background=img,
            library=lib,
            img_generation_enabled=True,
        )

        task = Task(TaskType.GENERATE, 0, AssetType.CHAR_PORTRAIT)
        process = proc(AssetType.CHAR_PORTRAIT, "NewChar", roster)
        task.process = process

        with TaskPool(max_workers=1) as pool:
            pool.submit(task)
            task.wait(timeout=5.0)

        assert task.completed
        assert task.error is None
        item = roster.lookup(AssetType.CHAR_PORTRAIT, "NewChar")
        assert item is not None
        assert item.target is not None
        # Generated asset should exist in the library
        assert (AssetType.CHAR_PORTRAIT, item.target) in lib

    def test_all_errors_fallback_to_system_asset(self, tmp_path):
        """All LLM/generation paths fail → programmatic fallback picks system asset."""
        from storyloom.tasks._llm_generate import GenerateProcessor
        from storyloom.io.img_api_client import ImageApiError

        lib = AssetLibrary(str(tmp_path / "media"))
        (tmp_path / "media").mkdir(parents=True, exist_ok=True)
        for atype in AssetType:
            (tmp_path / "media" / atype.value).mkdir(parents=True, exist_ok=True)
            lib._add_system_asset(atype, f"sys_{atype.value}",
                                  f"Fallback {atype.value}", "")

        roster = GameAssetRoster("test_int2", lib)
        roster.add(AssetType.CHAR_PORTRAIT, "NewChar", "A new character", target=None)

        api = FakeApiClient(responses=[
            '{"scope": "null", "selected": null}',
            ApiError("forced failed too"),
            ApiError("second try"),
        ])
        img = FakeImgApiClient(responses=[ImageApiError("gen failed")])
        proc = GenerateProcessor(
            api_client=api,
            img_client_portrait=img,
            img_client_background=img,
            library=lib,
            img_generation_enabled=True,
        )

        task = Task(TaskType.GENERATE, 0, AssetType.CHAR_PORTRAIT)
        process = proc(AssetType.CHAR_PORTRAIT, "NewChar", roster)
        task.process = process

        with TaskPool(max_workers=1) as pool:
            pool.submit(task)
            task.wait(timeout=5.0)

        assert task.completed
        item = roster.lookup(AssetType.CHAR_PORTRAIT, "NewChar")
        assert item.target is not None  # fallback worked
        # Must be a system asset (sys_ prefix)
        assert item.target.startswith("sys_")

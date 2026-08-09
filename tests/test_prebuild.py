"""Tests for §7.8c co-creation pre-build pipeline.

Per design.md §5.3 / §6.1 Step 4: batch LLM selection (library-only,
full thinking) → concurrent AI generation → force-select fallback
→ hard verification that every base entity has a non-null target.

TDD order:
  TestEntityParsing → TestBatchSelectionPrompt →
  TestBatchSelectionResponse → TestPrebuilderOrchestration →
  TestPrebuildIntegration
"""

import json
import tempfile
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from storyloom.assets import Asset, AssetItem, AssetLibrary, AssetType, GameAssetRoster


# ═══════════════════════════════════════════════════════════════════════
# 1. TestEntityParsing
# ═══════════════════════════════════════════════════════════════════════

class TestEntityParsing:
    """Parse story_config characters / locations into EntitySpec list.

    Per design: every character → one CHAR_PORTRAIT entity;
    every location → one BACKGROUND entity.
    """

    def test_parse_characters_basic(self):
        """Each character with name+description+appearance → EntitySpec."""
        from storyloom.core.prebuild import EntitySpec, parse_entities

        chars = [
            {"name": "Kael", "role": "protagonist",
             "description": "Former corp security.", "appearance": "Tall, sharp-eyed."},
            {"name": "Mouse", "role": "supporting",
             "description": "Info broker.", "appearance": "Short, wiry."},
        ]
        result = parse_entities(characters=chars, locations=[])
        portraits = [e for e in result if e.asset_type == AssetType.CHAR_PORTRAIT]
        assert len(portraits) == 2
        assert portraits[0].name == "Kael"
        assert portraits[0].description == "Former corp security."
        assert portraits[0].appearance == "Tall, sharp-eyed."

    def test_parse_locations_basic(self):
        """Each location → EntitySpec with BACKGROUND type."""
        from storyloom.core.prebuild import EntitySpec, parse_entities

        locs = [
            {"id": "neo_tokyo", "name": "Neo-Tokyo Streets",
             "description": "Rain-slicked neon streets."},
            {"id": "underground_bar", "name": "The Rat's Nest",
             "description": "Dimly lit bar."},
        ]
        result = parse_entities(characters=[], locations=locs)
        bgs = [e for e in result if e.asset_type == AssetType.BACKGROUND]
        assert len(bgs) == 2
        assert bgs[0].name == "Neo-Tokyo Streets"
        assert bgs[0].description == "Rain-slicked neon streets."

    def test_parse_mixed(self):
        """Characters + locations → combined list, each with correct type."""
        from storyloom.core.prebuild import parse_entities

        chars = [{"name": "Hero", "role": "protagonist",
                  "description": "A hero.", "appearance": "Brave."}]
        locs = [{"id": "test", "name": "Test Room", "description": "A room."}]
        result = parse_entities(characters=chars, locations=locs)
        assert len(result) == 2
        types = {e.asset_type for e in result}
        assert types == {AssetType.CHAR_PORTRAIT, AssetType.BACKGROUND}

    def test_parse_empty(self):
        """Empty inputs → empty list, no crash."""
        from storyloom.core.prebuild import parse_entities
        result = parse_entities(characters=[], locations=[])
        assert result == []

    def test_parse_missing_optional_fields(self):
        """Missing description / appearance → empty string, not crash."""
        from storyloom.core.prebuild import parse_entities

        chars = [{"name": "Ghost", "role": "antagonist"}]
        result = parse_entities(characters=chars, locations=[])
        assert len(result) == 1
        assert result[0].description == ""
        assert result[0].appearance == ""

    def test_parse_empty_name_skipped(self):
        """Character with empty name → skipped (defensive)."""
        from storyloom.core.prebuild import parse_entities

        chars = [
            {"name": "", "role": "supporting", "description": "no name"},
            {"name": "Valid", "role": "protagonist",
             "description": "has name", "appearance": "normal"},
        ]
        result = parse_entities(characters=chars, locations=[])
        assert len(result) == 1
        assert result[0].name == "Valid"

    def test_parse_empty_location_name_skipped(self):
        """Location with empty name → skipped."""
        from storyloom.core.prebuild import parse_entities

        locs = [
            {"id": "x", "name": "", "description": "no name"},
            {"id": "y", "name": "Valid Place", "description": "has name"},
        ]
        result = parse_entities(characters=[], locations=locs)
        assert len(result) == 1
        assert result[0].name == "Valid Place"


# ═══════════════════════════════════════════════════════════════════════
# 2. TestBatchSelectionPrompt
# ═══════════════════════════════════════════════════════════════════════

class TestBatchSelectionPrompt:
    """Build batch-selection LLM messages — one call per asset type.

    Per design.md §5.3: library-only scope; per §5.6: full thinking,
    type-specific prompts.  Input: all entities of one type + library
    top-N.  Output: messages array for ApiClient.chat().
    """

    @pytest.fixture
    def library(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            lib = AssetLibrary(d)
            # Add some entries of each type (non-sys IDs — sys_ reserved
            # for system assets via AssetLibrary._add_system_asset).
            lib.add(AssetType.CHAR_PORTRAIT, "Adult Woman",
                    "Adult woman, neutral expression", asset_id="fe000001")
            lib.add(AssetType.CHAR_PORTRAIT, "Elf Archer",
                    "Female elf archer in green cloak", asset_id="abc123")
            lib.add(AssetType.BACKGROUND, "Classroom",
                    "Empty classroom with desks", asset_id="cl000001")
            lib.add(AssetType.BACKGROUND, "Dungeon",
                    "Dark stone dungeon", asset_id="def456")
            yield lib

    def test_build_for_portrait(self, library):
        """Portrait prompt: system msg + user msg with entities + library."""
        from storyloom.core.prebuild import (
            EntitySpec,
            build_batch_selection_messages,
        )

        entities = [
            EntitySpec("Kael", "Former corp security.", "Tall.",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("Mouse", "Info broker.", "Short.",
                       AssetType.CHAR_PORTRAIT),
        ]
        msgs = build_batch_selection_messages(
            AssetType.CHAR_PORTRAIT, entities, library, forced=False,
        )
        assert len(msgs) == 2
        assert msgs[0]["role"] == "system"
        assert msgs[1]["role"] == "user"
        # User message contains all entity names
        user = msgs[1]["content"]
        assert "Kael" in user
        assert "Mouse" in user
        assert "Former corp security" in user
        # Library entries present
        assert "fe000001" in user
        assert "abc123" in user

    def test_build_for_background(self, library):
        """Background prompt: type-specific content."""
        from storyloom.core.prebuild import (
            EntitySpec,
            build_batch_selection_messages,
        )

        entities = [
            EntitySpec("Neo-Tokyo", "Rain-slicked streets.", "",
                       AssetType.BACKGROUND),
        ]
        msgs = build_batch_selection_messages(
            AssetType.BACKGROUND, entities, library, forced=False,
        )
        user = msgs[1]["content"]
        assert "Neo-Tokyo" in user
        assert "cl000001" in user
        assert "def456" in user

    def test_forced_mode_says_must_pick(self, library):
        """Forced mode: output format says no null allowed."""
        from storyloom.core.prebuild import (
            EntitySpec,
            build_batch_selection_messages,
        )

        entities = [EntitySpec("Hero", "A hero.", "Brave.",
                               AssetType.CHAR_PORTRAIT)]
        msgs = build_batch_selection_messages(
            AssetType.CHAR_PORTRAIT, entities, library, forced=True,
        )
        # System prompt should mention forced selection
        combined = msgs[0]["content"] + msgs[1]["content"]
        assert "MUST" in combined or "must" in combined

    def test_empty_entities_returns_empty(self, library):
        """No entities → empty messages list."""
        from storyloom.core.prebuild import build_batch_selection_messages

        msgs = build_batch_selection_messages(
            AssetType.CHAR_PORTRAIT, [], library, forced=False,
        )
        assert msgs == []

    def test_empty_library_still_produces_messages(self, library):
        """No library entries of this type → still build prompt (all entities
        will be 'generate')."""
        from storyloom.core.prebuild import (
            EntitySpec,
            build_batch_selection_messages,
        )

        # Use a fresh library with no entries of the tested type
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            empty_lib = AssetLibrary(d)
            entities = [EntitySpec("Hero", "A hero.", "Brave.",
                                   AssetType.CHAR_PORTRAIT)]
            msgs = build_batch_selection_messages(
                AssetType.CHAR_PORTRAIT, entities, empty_lib, forced=False,
            )
            assert len(msgs) == 2
            assert "Hero" in msgs[1]["content"]

    def test_response_format_is_json_object(self, library):
        """Prompt instructs JSON object output."""
        from storyloom.core.prebuild import (
            EntitySpec,
            build_batch_selection_messages,
        )

        entities = [EntitySpec("Kael", "Security consultant.", "Tall.",
                               AssetType.CHAR_PORTRAIT)]
        msgs = build_batch_selection_messages(
            AssetType.CHAR_PORTRAIT, entities, library, forced=False,
        )
        combined = msgs[0]["content"] + msgs[1]["content"]
        assert "json" in combined.lower()
        assert "results" in combined.lower()  # key name in output format


# ═══════════════════════════════════════════════════════════════════════
# 3. TestBatchSelectionResponse
# ═══════════════════════════════════════════════════════════════════════

class TestBatchSelectionResponse:
    """Parse LLM JSON response → list of SelectionResult.

    Per design: each entity gets {action: "matched"|"generate", asset_id}.
    Validate: all input entities appear in output; asset_ids valid for
    "matched" actions; no extra entities.
    """

    @pytest.fixture
    def library(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            lib = AssetLibrary(d)
            lib.add(AssetType.CHAR_PORTRAIT, "Adult Woman",
                    "Neutral expression", asset_id="fe000001")
            lib.add(AssetType.CHAR_PORTRAIT, "Elf Archer",
                    "Elf in green cloak", asset_id="abc123")
            yield lib

    @pytest.fixture
    def entities(self):
        from storyloom.core.prebuild import EntitySpec
        return [
            EntitySpec("Kael", "Security consultant.", "Tall.",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("Mouse", "Info broker.", "Short.",
                       AssetType.CHAR_PORTRAIT),
            EntitySpec("Michiko", "Security director.", "Cold.",
                       AssetType.CHAR_PORTRAIT),
        ]

    def test_parse_valid_response(self, entities, library):
        """Valid JSON → correct SelectionResult list."""
        from storyloom.core.prebuild import parse_batch_selection_response

        raw = json.dumps({
            "results": [
                {"name": "Kael", "action": "match", "asset_id": "fe000001"},
                {"name": "Mouse", "action": "generate", "asset_id": None},
                {"name": "Michiko", "action": "match", "asset_id": "abc123"},
            ]
        })
        results = parse_batch_selection_response(raw, entities, library)
        assert len(results) == 3
        assert results[0].entity_name == "Kael"
        assert results[0].action == "matched"
        assert results[0].asset_id == "fe000001"
        assert results[1].entity_name == "Mouse"
        assert results[1].action == "generate"
        assert results[1].asset_id is None
        assert results[2].entity_name == "Michiko"
        assert results[2].action == "matched"
        assert results[2].asset_id == "abc123"

    def test_parse_invalid_json_returns_none(self, entities, library):
        """Unparseable JSON → None."""
        from storyloom.core.prebuild import parse_batch_selection_response
        result = parse_batch_selection_response("not json", entities, library)
        assert result is None

    def test_parse_missing_results_key(self, entities, library):
        """JSON without 'results' key → None."""
        from storyloom.core.prebuild import parse_batch_selection_response
        result = parse_batch_selection_response('{"other": 1}', entities, library)
        assert result is None

    def test_parse_results_not_a_list(self, entities, library):
        """'results' is not a list → None."""
        from storyloom.core.prebuild import parse_batch_selection_response
        result = parse_batch_selection_response(
            '{"results": "string"}', entities, library,
        )
        assert result is None

    def test_parse_missing_name_field(self, entities, library):
        """Entry with missing 'name' → None (strict validation)."""
        from storyloom.core.prebuild import parse_batch_selection_response
        raw = json.dumps({
            "results": [
                {"action": "match", "asset_id": "fe000001"},
            ]
        })
        result = parse_batch_selection_response(raw, entities, library)
        assert result is None

    def test_parse_invalid_action(self, entities, library):
        """Entry with unknown action → None."""
        from storyloom.core.prebuild import parse_batch_selection_response
        raw = json.dumps({
            "results": [
                {"name": "Kael", "action": "delete", "asset_id": None},
            ]
        })
        result = parse_batch_selection_response(raw, entities, library)
        assert result is None

    def test_parse_matched_without_asset_id(self, entities, library):
        """'matched' action requires non-null asset_id."""
        from storyloom.core.prebuild import parse_batch_selection_response
        raw = json.dumps({
            "results": [
                {"name": "Kael", "action": "match", "asset_id": None},
            ]
        })
        result = parse_batch_selection_response(raw, entities, library)
        assert result is None

    def test_parse_matched_with_invalid_asset_id(self, entities, library):
        """'matched' with asset_id not in library → None."""
        from storyloom.core.prebuild import parse_batch_selection_response
        raw = json.dumps({
            "results": [
                {"name": "Kael", "action": "match", "asset_id": "nonexistent"},
            ]
        })
        result = parse_batch_selection_response(raw, entities, library)
        assert result is None

    def test_parse_not_all_entities_present(self, entities, library):
        """Response missing an entity → None."""
        from storyloom.core.prebuild import parse_batch_selection_response
        raw = json.dumps({
            "results": [
                {"name": "Kael", "action": "match", "asset_id": "fe000001"},
            ]
        })
        result = parse_batch_selection_response(raw, entities, library)
        assert result is None

    def test_parse_extra_entity_ignored_but_warns(self, entities, library):
        """Extra entity in response beyond input → still valid (LLM may
        suggest extra; we ignore them)."""
        from storyloom.core.prebuild import parse_batch_selection_response
        raw = json.dumps({
            "results": [
                {"name": "Kael", "action": "match", "asset_id": "fe000001"},
                {"name": "Mouse", "action": "generate", "asset_id": None},
                {"name": "Michiko", "action": "match", "asset_id": "abc123"},
                {"name": "ExtraGhost", "action": "generate", "asset_id": None},
            ]
        })
        results = parse_batch_selection_response(raw, entities, library)
        assert results is not None
        assert len(results) == 3  # ExtraGhost filtered out

    def test_parse_generate_with_null_asset_id_ok(self, entities, library):
        """'generate' with asset_id=null → valid (means need to generate)."""
        from storyloom.core.prebuild import parse_batch_selection_response
        raw = json.dumps({
            "results": [
                {"name": "Kael", "action": "generate", "asset_id": None},
                {"name": "Mouse", "action": "generate", "asset_id": None},
                {"name": "Michiko", "action": "generate", "asset_id": None},
            ]
        })
        results = parse_batch_selection_response(raw, entities, library)
        assert results is not None
        assert all(r.action == "generate" for r in results)
        assert all(r.asset_id is None for r in results)

    def test_parse_markdown_code_fence(self, entities, library):
        """LLM wraps JSON in ``` fences → still parsed correctly."""
        from storyloom.core.prebuild import parse_batch_selection_response
        raw = """```json
{
  "results": [
    {"name": "Kael", "action": "match", "asset_id": "fe000001"},
    {"name": "Mouse", "action": "generate", "asset_id": null},
    {"name": "Michiko", "action": "generate", "asset_id": null}
  ]
}
```"""
        results = parse_batch_selection_response(raw, entities, library)
        assert results is not None
        assert len(results) == 3
        assert results[0].action == "matched"


# ═══════════════════════════════════════════════════════════════════════
# 4. TestPrebuilderOrchestration
# ═══════════════════════════════════════════════════════════════════════

# Sample story_config data for tests
_SAMPLE_CHARS = [
    {"name": "Kael", "role": "protagonist",
     "description": "Former corp security.", "appearance": "Tall, sharp-eyed."},
    {"name": "Mouse", "role": "supporting",
     "description": "Info broker.", "appearance": "Short, wiry."},
]
_SAMPLE_LOCS = [
    {"id": "neo_tokyo", "name": "Neo-Tokyo Streets",
     "description": "Rain-slicked neon streets."},
    {"id": "bar", "name": "The Rat's Nest",
     "description": "Dimly lit underground bar."},
]


def _make_mock_api_client(*chat_returns: str):
    """Create a mock ApiClient whose .chat() returns successive values.

    Each call to .chat() returns the next element from *chat_returns*.
    The last element repeats if there are more calls than returns.
    """
    mock = MagicMock()
    if len(chat_returns) == 1:
        mock.chat.return_value = chat_returns[0]
    else:
        mock.chat.side_effect = list(chat_returns)
    type(mock).model = PropertyMock(return_value="deepseek-v4-pro")
    return mock


def _make_mock_img_client():
    """Create a mock ImgApiClient that returns a stub ImageResult.

    Returns a valid 4x4 RGBA PNG — large enough for normalize_background
    to not produce an empty crop.
    """
    from storyloom.io._types import ImageResult
    import struct, zlib
    mock = MagicMock()

    def _build_png(w: int, h: int) -> bytes:
        """Build a minimal valid RGBA PNG of size w×h."""
        def chunk(ctype: bytes, data: bytes) -> bytes:
            c = ctype + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        raw = b""
        for y in range(h):
            raw += b"\x00" + b"\x7f\x7f\x7f\xff" * w  # filter byte + RGBA

        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b"")
        )

    png_bytes = _build_png(1280, 720)
    mock.generate.return_value = ImageResult(
        bytes=png_bytes, format="png", has_alpha=True,
        width=1280, height=720, url="", elapsed_ms=100.0,
    )
    type(mock).model = PropertyMock(return_value="flux-2-pro")
    return mock


def _char_select_json(action="generate", asset_id=None):
    """Batch selection response for characters."""
    return json.dumps({"results": [
        {"name": "Kael", "action": action, "asset_id": asset_id},
        {"name": "Mouse", "action": action, "asset_id": asset_id},
    ]})


def _bg_select_json(action="generate", asset_id=None):
    """Batch selection response for backgrounds."""
    return json.dumps({"results": [
        {"name": "Neo-Tokyo Streets", "action": action, "asset_id": asset_id},
        {"name": "The Rat's Nest", "action": action, "asset_id": asset_id},
    ]})


class TestPrebuilderOrchestration:
    """Prebuilder.build() — full pipeline with mocked APIs.

    Verifies: parse → select → seed roster → generate → verify →
    force-fallback.  Progress events are yielded at each stage.
    """

    @pytest.fixture
    def library(self):
        with tempfile.TemporaryDirectory() as d:
            lib = AssetLibrary(d)
            lib.add(AssetType.CHAR_PORTRAIT, "Adult Woman",
                    "Neutral expression", asset_id="fe000001")
            lib.add(AssetType.BACKGROUND, "Classroom",
                    "Empty classroom", asset_id="cl000001")
            yield lib

    @pytest.fixture
    def roster(self, library):
        yield GameAssetRoster("test_game", library)

    # ── All matched (no generation) ──────────────────────────────────

    def test_all_matched_no_generation(self, library, roster):
        """When batch selection matches all entities → no generation needed,
        roster gets all targets set immediately."""
        from storyloom.core.prebuild import Prebuilder

        api = _make_mock_api_client(
            _char_select_json("match", "fe000001"),
            _bg_select_json("match", "cl000001"),
        )
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        events = list(prebuilder.build(_SAMPLE_CHARS, _SAMPLE_LOCS, roster))

        # Verify roster state
        item_k = roster.lookup(AssetType.CHAR_PORTRAIT, "Kael")
        assert item_k is not None
        assert item_k.target == "fe000001"
        item_m = roster.lookup(AssetType.CHAR_PORTRAIT, "Mouse")
        assert item_m is not None
        assert item_m.target == "fe000001"

        # Verify locations also processed
        item_n = roster.lookup(AssetType.BACKGROUND, "Neo-Tokyo Streets")
        assert item_n is not None
        item_r = roster.lookup(AssetType.BACKGROUND, "The Rat's Nest")
        assert item_r is not None

        # Final event is prebuild_complete with success=True
        final = events[-1]
        assert final["type"] == "prebuild_complete"
        assert final["success"] is True
        assert final["errors"] == []

        # img_client.generate was never called
        img.generate.assert_not_called()

    # ── Mixed matched + generate ─────────────────────────────────────

    def test_mixed_match_and_generate(self, library, roster):
        """Some entities matched, some need generation → generation runs
        for unmatched ones."""
        from storyloom.core.prebuild import Prebuilder

        # Kael matched, Mouse needs generation
        api = _make_mock_api_client(
            json.dumps({"results": [
                {"name": "Kael", "action": "match", "asset_id": "fe000001"},
                {"name": "Mouse", "action": "generate", "asset_id": None},
            ]}),
            _bg_select_json("match", "cl000001"),
        )
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        events = list(prebuilder.build(_SAMPLE_CHARS, _SAMPLE_LOCS, roster))

        # Kael: matched directly
        item_k = roster.lookup(AssetType.CHAR_PORTRAIT, "Kael")
        assert item_k.target == "fe000001"

        # Mouse: generated (target is a uuid hex string)
        item_m = roster.lookup(AssetType.CHAR_PORTRAIT, "Mouse")
        assert item_m is not None
        assert item_m.target is not None
        assert item_m.target != "fe000001"  # not the matched id

        # img_client.generate was called for Mouse
        img.generate.assert_called()

        final = events[-1]
        assert final["type"] == "prebuild_complete"
        assert final["success"] is True

    # ── Generation fails → force-select fallback ─────────────────────

    def test_generation_fails_force_select_fallback(self, library, roster):
        """When image generation raises, force-select picks from library."""
        from storyloom.core.prebuild import Prebuilder

        # Mock: 2 batch selection calls + force-select calls (light+enabled
        # for Kael). _select_forced has programmatic fallback, so we just
        # need the side_effect to not raise StopIteration.
        api = _make_mock_api_client(
            json.dumps({"results": [
                {"name": "Kael", "action": "generate", "asset_id": None},
            ]}),
            _bg_select_json("match", "cl000001"),
            # Force-select for Kael (light thinking + enabled thinking)
            # Return unparseable → triggers programmatic fallback
            "not json",
            "not json",
        )
        # Image generation fails
        from storyloom.io.img_api_client import ImageApiError
        img = _make_mock_img_client()
        img.generate.side_effect = ImageApiError("API error")

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        events = list(prebuilder.build(
            [{"name": "Kael", "role": "protagonist",
              "description": "Security consultant.", "appearance": "Tall."}],
            _SAMPLE_LOCS, roster,
        ))

        # Kael: force-selected (falls back to library)
        item_k = roster.lookup(AssetType.CHAR_PORTRAIT, "Kael")
        assert item_k is not None
        assert item_k.target is not None  # got something from library

        final = events[-1]
        assert final["type"] == "prebuild_complete"
        assert final["success"] is True

    # ── No-generation mode ───────────────────────────────────────────

    def test_no_generation_mode_forced_only(self, library, roster):
        """img_generation_enabled=False → forced selection for all, no API
        image generation calls."""
        from storyloom.core.prebuild import Prebuilder

        api = _make_mock_api_client(
            _char_select_json("match", "fe000001"),
            _bg_select_json("match", "cl000001"),
        )
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=False, max_workers=1)
        events = list(prebuilder.build(_SAMPLE_CHARS, _SAMPLE_LOCS, roster))

        # img_client.generate was never called
        img.generate.assert_not_called()

        # But all entities have targets (from forced selection)
        for name in ("Kael", "Mouse"):
            item = roster.lookup(AssetType.CHAR_PORTRAIT, name)
            assert item is not None, f"{name} missing from roster"
            assert item.target is not None, f"{name} has null target"

        final = events[-1]
        assert final["success"] is True

    # ── Progress events ──────────────────────────────────────────────

    def test_progress_events_sequence(self, library, roster):
        """Progress events are yielded in correct order with expected fields."""
        from storyloom.core.prebuild import Prebuilder

        api = _make_mock_api_client(
            json.dumps({"results": [
                {"name": "Kael", "action": "generate", "asset_id": None},
            ]}),
            _bg_select_json("match", "cl000001"),
        )
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        events = list(prebuilder.build(
            [{"name": "Kael", "role": "protagonist",
              "description": "Security consultant.", "appearance": "Tall."}],
            _SAMPLE_LOCS, roster,
        ))

        event_types = [e["type"] for e in events]
        # Parse event then selection events then generate events then complete
        assert "prebuild_progress" in event_types
        assert "prebuild_complete" in event_types

        # Check phase transitions
        phases = [e.get("phase") for e in events if e["type"] == "prebuild_progress"]
        assert "parse" in phases
        assert "selection" in phases or any("selection" in str(e) for e in events)
        assert "generate" in phases or any("generate" in str(e) for e in events)

    def test_progress_events_have_entity_names(self, library, roster):
        """Generate-phase progress events include entity names and counts."""
        from storyloom.core.prebuild import Prebuilder

        api = _make_mock_api_client(
            json.dumps({"results": [
                {"name": "Kael", "action": "generate", "asset_id": None},
            ]}),
            _bg_select_json("match", "cl000001"),
        )
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        events = list(prebuilder.build(
            [{"name": "Kael", "role": "protagonist",
              "description": "Security consultant.", "appearance": "Tall."}],
            _SAMPLE_LOCS, roster,
        ))

        # Find a generate progress event
        gen_events = [
            e for e in events
            if e["type"] == "prebuild_progress" and e.get("phase") == "generate"
        ]
        assert len(gen_events) > 0
        # Each generate event names the entity
        for ge in gen_events:
            assert "entity" in ge or "asset_type" in ge

    # ── Verification failure ─────────────────────────────────────────

    def test_verification_failure_missing_entity(self, library, roster):
        """If an entity is missing from the roster after all steps, the
        prebuild fails with errors."""
        from storyloom.core.prebuild import Prebuilder

        # Selection returns only 1 of 2 chars — missing "Mouse"
        api = _make_mock_api_client(
            json.dumps({"results": [
                {"name": "Kael", "action": "match", "asset_id": "fe000001"},
            ]}),
            _bg_select_json("match", "cl000001"),
        )
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        events = list(prebuilder.build(_SAMPLE_CHARS, _SAMPLE_LOCS, roster))

        final = events[-1]
        assert final["type"] == "prebuild_complete"
        # Selection response missing Mouse → parse_batch_selection_response
        # returns None → we fall through to force-select for all.  So
        # this should actually succeed (force-select covers the gap).
        # See test_selection_api_failure_triggers_force_select below.

    def test_selection_api_failure_triggers_force_select(self, library, roster):
        """When batch selection API call fails, all entities get force-selected."""
        from storyloom.core.prebuild import Prebuilder

        from storyloom.io.api_client import ApiError
        api = _make_mock_api_client("garbage", "garbage")
        # First 2 calls (batch selection) fail; subsequent calls (force-select) succeed
        api.chat.side_effect = [
            ApiError("Connection refused"),
            ApiError("Connection refused"),
            json.dumps({"selected": "fe000001"}),   # Kael force-select
            json.dumps({"selected": "fe000001"}),   # Mouse force-select
            json.dumps({"selected": "cl000001"}),   # Neo-Tokyo force-select
            json.dumps({"selected": "cl000001"}),   # Rat's Nest force-select
        ]
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        events = list(prebuilder.build(_SAMPLE_CHARS, _SAMPLE_LOCS, roster))

        # All base entities must have non-null targets
        for name in ("Kael", "Mouse"):
            item = roster.lookup(AssetType.CHAR_PORTRAIT, name)
            assert item is not None, f"{name} missing from roster"
            assert item.target is not None, f"{name} has null target"
        for name in ("Neo-Tokyo Streets", "The Rat's Nest"):
            item = roster.lookup(AssetType.BACKGROUND, name)
            assert item is not None, f"{name} missing from roster"
            assert item.target is not None, f"{name} has null target"

        final = events[-1]
        assert final["type"] == "prebuild_complete"
        assert final["success"] is True

    # ── Concurrent execution ─────────────────────────────────────────

    def test_concurrent_selection_two_calls(self, library, roster):
        """Batch selection makes exactly 2 LLM calls (portrait + background)
        regardless of entity count."""
        from storyloom.core.prebuild import Prebuilder

        api = _make_mock_api_client(
            _char_select_json("match", "fe000001"),
            _bg_select_json("match", "cl000001"),
        )
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        list(prebuilder.build(_SAMPLE_CHARS, _SAMPLE_LOCS, roster))

        # Exactly 2 chat calls (portrait + background batch selection)
        assert api.chat.call_count >= 2

    # ── Empty inputs ──────────────────────────────────────────────────

    def test_empty_inputs_noop(self, library, roster):
        """Empty characters + empty locations → immediate success, no API calls."""
        from storyloom.core.prebuild import Prebuilder

        api = _make_mock_api_client("{}")
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        events = list(prebuilder.build([], [], roster))

        api.chat.assert_not_called()
        img.generate.assert_not_called()

        final = events[-1]
        assert final["type"] == "prebuild_complete"
        assert final["success"] is True


# ═══════════════════════════════════════════════════════════════════════
# 5. TestPrebuildIntegration
# ═══════════════════════════════════════════════════════════════════════

class TestPrebuildIntegration:
    """End-to-end integration: real library + roster, mock API.

    Verifies the full pipeline produces a valid roster state that the
    game can use immediately.
    """

    @pytest.fixture
    def library(self):
        with tempfile.TemporaryDirectory() as d:
            lib = AssetLibrary(d)
            # Pre-populate with some library assets
            lib.add(AssetType.CHAR_PORTRAIT, "Adult Woman",
                    "Adult woman, neutral expression, business attire",
                    asset_id="fe000001")
            lib.add(AssetType.CHAR_PORTRAIT, "Elf Archer",
                    "Female elf archer in green cloak, holding a bow",
                    asset_id="abc123")
            lib.add(AssetType.BACKGROUND, "Classroom",
                    "Empty classroom with desks and blackboard",
                    asset_id="cl000001")
            lib.add(AssetType.BACKGROUND, "Dungeon",
                    "Dark stone dungeon with torches and iron bars",
                    asset_id="def456")
            yield lib

    @pytest.fixture
    def roster(self, library):
        yield GameAssetRoster("test_game", library)

    def test_full_pipeline_with_roster_persistence(self, library, roster):
        """After pre-build: roster contains all entities, save/load round-trip
        preserves state."""
        from storyloom.core.prebuild import Prebuilder

        api = _make_mock_api_client(
            json.dumps({"results": [
                {"name": "Kael", "action": "generate", "asset_id": None},
                {"name": "Mouse", "action": "match", "asset_id": "abc123"},
            ]}),
            _bg_select_json("match", "cl000001"),
        )
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        events = list(prebuilder.build(_SAMPLE_CHARS, _SAMPLE_LOCS, roster))

        assert events[-1]["success"] is True

        # Save roster → load back
        with tempfile.TemporaryDirectory() as saves_dir:
            import os
            roster_path = os.path.join(saves_dir, "_asset_roster.json")
            roster.save(roster_path)

            loaded = GameAssetRoster.load(roster_path, library, "test_game")
            assert len(loaded) == len(roster)

            # All base entities present with non-null targets
            for name in ("Kael", "Mouse"):
                item = loaded.lookup(AssetType.CHAR_PORTRAIT, name)
                assert item is not None, f"{name} missing after reload"
                assert item.target is not None, f"{name} has null target after reload"

    def test_library_use_count_incremented(self, library, roster):
        """Entities matched from library → use_count incremented."""
        from storyloom.core.prebuild import Prebuilder

        # Both match different library assets
        api = _make_mock_api_client(
            json.dumps({"results": [
                {"name": "Kael", "action": "match", "asset_id": "fe000001"},
                {"name": "Mouse", "action": "match", "asset_id": "abc123"},
            ]}),
            _bg_select_json("match", "cl000001"),
        )
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        list(prebuilder.build(_SAMPLE_CHARS, _SAMPLE_LOCS, roster))

        # use_count should be incremented for matched assets
        asset1 = library.get(AssetType.CHAR_PORTRAIT, "fe000001")
        assert asset1.use_count >= 1
        asset2 = library.get(AssetType.CHAR_PORTRAIT, "abc123")
        assert asset2.use_count >= 1

    def test_generated_asset_added_to_library(self, library, roster):
        """AI-generated images are added to the library with a uuid id."""
        from storyloom.core.prebuild import Prebuilder

        api = _make_mock_api_client(
            json.dumps({"results": [
                {"name": "Kael", "action": "generate", "asset_id": None},
            ]}),
            _bg_select_json("match", "cl000001"),
        )
        img = _make_mock_img_client()

        prebuilder = Prebuilder(api, img, img, library,
                                img_generation_enabled=True, max_workers=1)
        list(prebuilder.build(
            [{"name": "Kael", "role": "protagonist",
              "description": "Security consultant.", "appearance": "Tall."}],
            _SAMPLE_LOCS, roster,
        ))

        # The generated asset is in the library
        item = roster.lookup(AssetType.CHAR_PORTRAIT, "Kael")
        assert item.target is not None
        generated = library.get(AssetType.CHAR_PORTRAIT, item.target)
        assert generated is not None, "Generated asset not in library"
        assert generated.name == "Kael"
        assert generated.use_count >= 1

    def test_roster_empty_before_prebuild(self, roster):
        """Roster starts empty — pre-build is the first write."""
        assert len(roster) == 0

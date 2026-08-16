"""Tests for name folding (§7.6 asset matching) — fold_name, lookup_folded,
and TaskGenerator program-match integration for 繁简 / case / width variants.
"""

from collections import deque

import pytest

from storyloom.assets import AssetLibrary, AssetType, GameAssetRoster
from storyloom.assets._names import fold_name
from storyloom.parser.stream_parser import Event, EventType
from storyloom.tasks import TaskGenerator, TaskType


@pytest.fixture
def library():
    """Fresh AssetLibrary in a temp directory."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        yield AssetLibrary(d)


@pytest.fixture
def roster(library):
    """Fresh GameAssetRoster backed by *library*."""
    return GameAssetRoster("test_fold", library)


# ═══════════════════════════════════════════════════════════════════════
# 1. fold_name
# ═══════════════════════════════════════════════════════════════════════

class TestFoldName:
    def test_traditional_folds_to_simplified(self):
        """Traditional chars map to simplified (繁→简)."""
        assert fold_name("結") == "结"
        assert fold_name("蓮") == "莲"

    def test_simplified_is_stable(self):
        """Simplified chars are unchanged."""
        assert fold_name("结") == "结"
        assert fold_name("莲") == "莲"

    def test_bidirectional_equivalence(self):
        """繁 and 简 forms of the same name fold to the same canonical form."""
        assert fold_name("藤原結衣") == fold_name("藤原结衣") == "藤原结衣"
        assert fold_name("山田蓮") == fold_name("山田莲") == "山田莲"

    def test_nfkc_full_width(self):
        """Full-width Latin folds to half-width."""
        assert fold_name("Ａｌｉｃｅ") == fold_name("Alice")

    def test_casefold(self):
        """Case is folded (case-insensitive match)."""
        assert fold_name("Alice") == fold_name("alice") == "alice"

    def test_strip_whitespace(self):
        """Surrounding whitespace is stripped."""
        assert fold_name("  Alice  ") == fold_name("Alice")

    def test_empty_string(self):
        """Empty string folds to empty string."""
        assert fold_name("") == ""

    def test_unknown_chars_unchanged(self):
        """Characters absent from the table pass through unchanged."""
        assert fold_name("xyz123") == "xyz123"


# ═══════════════════════════════════════════════════════════════════════
# 2. GameAssetRoster.lookup_folded
# ═══════════════════════════════════════════════════════════════════════

class TestLookupFolded:
    def test_exact_hit(self, roster):
        """Exact match returns the item with its canonical local_name."""
        roster.add(AssetType.CHAR_PORTRAIT, "hero", "a knight")
        item = roster.lookup_folded(AssetType.CHAR_PORTRAIT, "hero")
        assert item is not None
        assert item.local_name == "hero"

    def test_folded_hit_traditional_query(self, roster):
        """Traditional query hits a simplified roster key."""
        roster.add(AssetType.CHAR_PORTRAIT, "藤原结衣", "少女")
        item = roster.lookup_folded(AssetType.CHAR_PORTRAIT, "藤原結衣")
        assert item is not None
        assert item.local_name == "藤原结衣"   # canonical key

    def test_folded_hit_simplified_query(self, roster):
        """Simplified query hits a traditional roster key (bidirectional)."""
        roster.add(AssetType.CHAR_PORTRAIT, "藤原結衣", "少女")
        item = roster.lookup_folded(AssetType.CHAR_PORTRAIT, "藤原结衣")
        assert item is not None
        assert item.local_name == "藤原結衣"

    def test_miss_returns_none(self, roster):
        """No equivalent entry → None."""
        roster.add(AssetType.CHAR_PORTRAIT, "hero", "a knight")
        assert roster.lookup_folded(AssetType.CHAR_PORTRAIT, "villain") is None

    def test_exact_takes_precedence(self, roster):
        """Exact key wins even if a folded variant also exists."""
        roster.add(AssetType.CHAR_PORTRAIT, "结", "simplified")
        roster.add(AssetType.CHAR_PORTRAIT, "結", "traditional")
        item = roster.lookup_folded(AssetType.CHAR_PORTRAIT, "結")
        assert item.local_name == "結"          # exact, not folded


# ═══════════════════════════════════════════════════════════════════════
# 3. TaskGenerator program-match integration
# ═══════════════════════════════════════════════════════════════════════

class TestTaskGeneratorFoldedMatch:
    def test_match_hits_without_llm(self, roster):
        """SEGMENT with traditional char → O(1) hit, no LLM processor."""
        roster.add(AssetType.CHAR_PORTRAIT, "藤原结衣", "少女")
        gen = TaskGenerator(deque(), roster)   # match_processor=None

        event = Event(EventType.SEGMENT, 5, {
            "text": "…",
            "position": "pre",
            "char": "藤原結衣",               # traditional — must hit
        })
        task = gen.enqueue(event)

        assert task.task_type == TaskType.MATCH
        assert task.completed is True
        assert task.result == "藤原结衣"       # canonical simplified key
        assert task.process is None            # no LLM fallback assigned

    def test_generate_dedups_folded(self, roster):
        """DECLARE with traditional name does not duplicate a simplified entry."""
        roster.add(AssetType.CHAR_PORTRAIT, "藤原结衣", "少女")
        gen = TaskGenerator(deque(), roster)

        event = Event(EventType.DECLARE, 3, {
            "kind": "CHAR",
            "name": "藤原結衣",               # traditional variant
            "desc": "重複声明",
        })
        task = gen.enqueue(event)

        assert task.completed is True
        entries = roster.list_by_type(AssetType.CHAR_PORTRAIT)
        assert len(entries) == 1               # no duplicate entry
        assert "藤原结衣" in entries

"""Name folding — canonical normalization for asset-name matching.

Folds a ``local_name`` to a canonical form so script variants
(simplified vs. traditional Chinese / Japanese kanji), full-width vs.
half-width forms, case, and surrounding whitespace do not break the
O(1) program match in the TaskGenerator (§7.6).

The 繁→简 (traditional→simplified) mapping is bundled as package data
(``assets/data/hanzi_t2s.json``), generated from OpenCC's
``TSCharacters.txt`` (Apache-2.0, https://github.com/BYVoid/OpenCC).
Folding BOTH sides to simplified yields bidirectional equivalence
without the 1:many ambiguity of the reverse (简→繁) direction — each
traditional character maps to exactly one simplified character.
"""

from __future__ import annotations

import importlib.resources
import json
import unicodedata
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _translation_table() -> dict:
    """Load the 繁→简 mapping once and build a ``str.translate`` table.

    Returns:
        A dict suitable for ``str.translate()``, mapping each traditional
        character to its simplified form.
    """
    path = Path(
        str(importlib.resources.files("storyloom") / "assets" / "data" / "hanzi_t2s.json")
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    return str.maketrans(data["traditional"], data["simplified"])


def fold_name(name: str) -> str:
    """Return the canonical folded form of *name*.

    Order matters: NFKC (full/half width) → strip → casefold → 繁→简.
    Both the roster key and the query name are folded before comparison,
    so the match is bidirectional across 繁/简.
    """
    table = _translation_table()
    return (
        unicodedata.normalize("NFKC", name)
        .strip()
        .casefold()
        .translate(table)
    )

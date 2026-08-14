"""Tests for the i18n build tool (Babel .po → .mo compile)."""

import gettext
from pathlib import Path

from storyloom.i18n_compile import compile_all


def _write_po(locale_dir: Path, lang: str) -> None:
    """Write a minimal .po catalog with a couple of representative entries."""
    po = (
        'msgid ""\n'
        'msgstr ""\n'
        '"Language: ' + lang + '\\n"\n'
        '\n'
        'msgid "(or write your own answer)"\n'
        'msgstr "（或输入你自己的答案）"\n'
        '\n'
        'msgid "Describe the story you\'d like to play.\\n'
        'e.g. \'A cyberpunk love story\' or \'A wuxia adventure\'"\n'
        'msgstr "请描述你想玩的故事。\\n例如：\'赛博朋克\'"\n'
    )
    d = locale_dir / lang / "LC_MESSAGES"
    d.mkdir(parents=True, exist_ok=True)
    (d / "storyloom.po").write_text(po, encoding="utf-8")


class TestCompileAll:
    def test_writes_mo_next_to_po(self, tmp_path):
        _write_po(tmp_path, "zh_CN")
        compiled = compile_all(str(tmp_path))
        assert len(compiled) == 1
        assert compiled[0].endswith("storyloom.mo")
        assert Path(compiled[0]).is_file()

    def test_compiled_mo_loads_and_translates(self, tmp_path):
        _write_po(tmp_path, "zh_CN")
        compile_all(str(tmp_path))
        trans = gettext.translation(
            "storyloom", str(tmp_path), languages=["zh_CN"], fallback=True
        )
        assert trans.gettext("(or write your own answer)") == "（或输入你自己的答案）"

"""Tests for the i18n build tools (Babel .mo compile + polib resource gen)."""

import gettext
import json
from pathlib import Path

from storyloom.i18n_compile import compile_all, generate_i18n_resources


def _write_po(locale_dir: Path, lang: str) -> None:
    """Write a minimal .po catalog with a couple of representative entries."""
    po = (
        'msgid ""\n'
        'msgstr ""\n'
        '"Language: ' + lang + '\\n"\n'
        '\n'
        'msgid "About"\n'
        'msgstr "关于"\n'
        '\n'
        'msgid "Requires {{cond}}"\n'
        'msgstr "需{{cond}}"\n'
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
        assert trans.gettext("About") == "关于"
        assert trans.gettext("Requires {{cond}}") == "需{{cond}}"


class TestGenerateI18nResources:
    def test_generates_i18next_bundle(self, tmp_path):
        _write_po(tmp_path, "zh_CN")
        out = tmp_path / "i18n-resources.js"
        generate_i18n_resources(str(tmp_path), str(out))

        text = out.read_text(encoding="utf-8")
        assert "window.STORYLOOM_I18N_RESOURCES" in text

        # Strip the JS assignment wrapper and parse the JSON payload.
        payload = text.split("=", 1)[1].rstrip(";\n")
        resources = json.loads(payload)

        assert set(resources) == {"en", "zh-CN"}
        assert resources["en"] == {"translation": {}}
        assert resources["zh-CN"]["translation"]["About"] == "关于"
        assert "Requires {{cond}}" in resources["zh-CN"]["translation"]

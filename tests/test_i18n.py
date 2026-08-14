"""Tests for i18n module."""
from storyloom.i18n import _, init_i18n, switch_language, get_current_lang


class TestI18NInit:
    def test_init_with_language(self):
        init_i18n("en")
        assert get_current_lang() == "en"

    def test_init_falls_back_for_unsupported_language(self):
        init_i18n("fr")
        assert get_current_lang() == "en"

    def test_init_uses_default_when_none(self):
        # Switch to a known state first, then back to None
        init_i18n("en")
        init_i18n(None)
        assert get_current_lang() == "en"

    def test_init_with_explicit_locale_dir(self):
        """Explicit locale_dir should not raise."""
        import importlib.resources
        locale_dir = str(importlib.resources.files("storyloom") / "locale")
        init_i18n("zh-CN", locale_dir=locale_dir)
        assert get_current_lang() == "zh-CN"


class TestI18NSwitch:
    def test_switch_to_supported_language(self):
        init_i18n("zh-CN")
        switch_language("en")
        assert get_current_lang() == "en"

    def test_switch_ignores_unsupported_language(self):
        init_i18n("zh-CN")
        switch_language("fr")
        assert get_current_lang() == "zh-CN"  # unchanged

    def test_switch_preserves_translator_cache(self):
        """After switching back and forth, translations still work."""
        init_i18n("zh-CN")
        switch_language("en")
        switch_language("zh-CN")
        assert get_current_lang() == "zh-CN"

    def test_switch_same_language_is_noop(self):
        init_i18n("zh-CN")
        switch_language("zh-CN")
        assert get_current_lang() == "zh-CN"


class TestI18NTranslate:
    def test_falls_back_to_msgid_for_missing_translation(self):
        init_i18n("en")
        result = _("nonexistent string xyz123")
        assert result == "nonexistent string xyz123"

    def test_translates_zh_cn_round_trip(self, tmp_path):
        """A real .po → .mo → gettext round-trip returns the translation."""
        import importlib.resources
        import shutil
        from storyloom.i18n_compile import compile_all

        pkg_locale = importlib.resources.files("storyloom") / "locale"
        tmp_locale = tmp_path / "locale"
        shutil.copytree(str(pkg_locale), str(tmp_locale))
        compile_all(str(tmp_locale))

        init_i18n("zh-CN", locale_dir=str(tmp_locale))
        assert _("(or write your own answer)") == "（或输入你自己的答案）"

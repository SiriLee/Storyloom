"""i18n build tools — compile gettext catalogs + generate i18next resources.

Replaces the former hand-rolled ``.po``→``.mo`` compiler with the standard
toolchain:

- ``compile_all`` uses Babel (``babel.messages``) to compile ``.po`` → ``.mo``
  (correct header/plural handling).
- ``generate_i18n_resources`` uses polib to read ``.po`` and emit the i18next
  resource bundle consumed by the frontend.

Both run at build time (``setup.py`` command hooks) or manually via
``python -m storyloom.i18n_compile``.  ``.mo`` files are build artifacts
(gitignored); ``i18n-resources.js`` is committed so the frontend works in a
fresh checkout without running a build.
"""

import json
from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po

import polib


def compile_all(locale_dir: str) -> list[str]:
    """Compile every ``.po`` under *locale_dir* to a ``.mo`` using Babel.

    Returns the list of ``.mo`` paths written.
    """
    compiled: list[str] = []
    for po_file in Path(locale_dir).rglob("*.po"):
        mo_file = po_file.with_suffix(".mo")
        with open(po_file, "rb") as fh:
            catalog = read_po(fh)
        with open(mo_file, "wb") as fh:
            write_mo(fh, catalog)
        compiled.append(str(mo_file))
    return compiled


def generate_i18n_resources(locale_dir: str, output_path: str) -> None:
    """Generate the i18next resource bundle from ``.po`` files.

    Reads every ``*.po`` under *locale_dir*, derives the BCP-47 language code
    from the directory name (``zh_CN`` → ``zh-CN``), and writes
    ``window.STORYLOOM_I18N_RESOURCES = {...}`` to *output_path*.

    The bundle uses i18next's resource shape
    ``{ "<lang>": { "translation": { msgid: msgstr, ... } } }``.  English is
    emitted as an empty identity map — i18next falls back to the key (the
    English ``msgid``) when no translation exists.
    """
    translations: dict[str, dict[str, str]] = {}

    for po_file in Path(locale_dir).rglob("*.po"):
        # locale/zh_CN/LC_MESSAGES/… → "zh-CN"
        lang_code = po_file.parent.parent.name.replace("_", "-")
        po = polib.pofile(str(po_file))
        lang_dict: dict[str, str] = {}
        for entry in po:
            if not entry.msgid:
                continue  # header entry
            lang_dict[entry.msgid] = entry.msgstr
        translations[lang_code] = lang_dict

    resources: dict[str, dict[str, dict[str, str]]] = {
        "en": {"translation": {}},
    }
    for lang in sorted(translations):
        resources[lang] = {"translation": translations[lang]}

    header = (
        "// Auto-generated from locale/*.po — DO NOT EDIT by hand.\n"
        "// Regenerate with: python -m storyloom.i18n_compile\n"
        "//\n"
        "// i18next resource bundle consumed by static/js/state.js.\n"
    )
    body = "window.STORYLOOM_I18N_RESOURCES = " + json.dumps(
        resources, ensure_ascii=False, indent=2, sort_keys=True
    ) + ";\n"

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + body, encoding="utf-8")


if __name__ == "__main__":
    _project = Path(__file__).resolve().parents[2]  # → repo root
    _locale = _project / "src" / "storyloom" / "locale"
    _web_js = _project / "src" / "storyloom" / "web" / "static" / "js"

    compiled = compile_all(str(_locale))
    print(f"[i18n] Compiled {len(compiled)} .mo file(s)")

    js_out = _web_js / "i18n-resources.js"
    generate_i18n_resources(str(_locale), str(js_out))
    print(f"[i18n] Generated {js_out}")

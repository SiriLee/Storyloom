"""i18n build tool — compile gettext ``.po`` catalogs to ``.mo`` via Babel.

Backend gettext translation.  Frontend translations are a separate source —
i18next JSON files under ``web/static/locales/`` — and are NOT derived from
these ``.po`` catalogs.

Runs at build time (``setup.py`` command hooks) or manually via
``python -m storyloom.i18n_compile``.  ``.mo`` files are build artifacts
(gitignored).
"""

from pathlib import Path

from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po


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


if __name__ == "__main__":
    _project = Path(__file__).resolve().parents[2]  # → repo root
    _locale = _project / "src" / "storyloom" / "locale"

    compiled = compile_all(str(_locale))
    print(f"[i18n] Compiled {len(compiled)} .mo file(s)")

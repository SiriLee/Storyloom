# locale — gettext translation catalogs

`locale/` holds the gettext `.po` UI-string catalogs, one per language under
`locale/{lang}/LC_MESSAGES/storyloom.po`.  Long-form documents (guide,
changelog, …) live in the sibling `src/storyloom/content/` tree — see below.

Both trees are **package data** (`[tool.setuptools.package-data]` in
`pyproject.toml`) and resolved at runtime via `importlib.resources` — so they
ship in the pip wheel and are bundled by PyInstaller, identically.

| Kind | Location | Format | Flow |
|------|----------|--------|------|
| UI strings | `src/storyloom/locale/{lang}/LC_MESSAGES/storyloom.po` | gettext `.po` | `.po` → `.mo` (Babel, server gettext) + `i18n-resources.js` (polib → i18next frontend), via `i18n_compile.py` |
| Long-form content | `src/storyloom/content/{lang}/{doc}.md` | Markdown | served at `GET /content/{lang}/{doc}` (`web/server.py`); loaded by `loadLocalizedContent(doc)` with fallback to `en` |

Language codes: `locale/` gettext directories use POSIX locale names
(`zh_CN`, `zh_TW`, `en`) as required by gettext; `content/` directories use
BCP-47 (`zh-CN`, `zh-TW`, `en`) to match the app/URL language codes directly.

`en` is the source language — it holds `content/` but no `LC_MESSAGES/`
(English strings are the `msgid` source in the `.po` files).

To add a long-form document: drop `content/{lang}/{doc}.md` for each
language and call `loadLocalizedContent("doc")` — no server change needed.

Why content isn't in `.po`: gettext `msgid`/`msgstr` targets short UI
strings; paragraph-level Markdown is *content*, so it lives as per-locale
files (the Docusaurus / Next.js pattern).

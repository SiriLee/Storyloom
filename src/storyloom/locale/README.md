# locale — backend gettext catalogs

`locale/` holds the **backend** gettext `.po` catalogs — a handful of strings
emitted by the Python engine (co-creation prompts), translated for zh-CN and
zh-TW.  Compiled to `.mo` at build time by `i18n_compile.py` (Babel) and
loaded via gettext.

**Frontend translations are a separate source** — i18next JSON files under
`src/storyloom/web/static/locales/{lang}.json` — not derived from these `.po`
catalogs.  This is the dual-source layout: backend gettext + frontend i18next.

| Kind | Location | Format | Flow |
|------|----------|--------|------|
| Backend strings | `src/storyloom/locale/{lang}/LC_MESSAGES/storyloom.po` | gettext `.po` | `.po` → `.mo` (Babel) → server gettext `_()` |
| Frontend strings | `src/storyloom/web/static/locales/{lang}.json` | i18next JSON | fetched by i18next http-backend at `GET /static/locales/{lang}.json` |
| Long-form content | `src/storyloom/content/{lang}/{doc}.md` | Markdown | served at `GET /content/{lang}/{doc}` (`web/server.py`); loaded by `loadLocalizedContent(doc)` with fallback to `en` |

Language codes: `locale/` gettext directories use POSIX locale names
(`zh_CN`, `zh_TW`, `en`) as required by gettext; `locales/` and `content/`
directories use BCP-47 (`zh-CN`, `zh-TW`, `en`) to match the app/URL codes.

`en` is the source language — no `en` `.po` (English strings are the `msgid`
source) and no `en` entries in the frontend JSON (i18next falls back to the
key).  To add a backend string: add the `_()` call in Python, then the
`msgid`/`msgstr` pair here.  To add a frontend string: add the `_()` call in
JS, then the key/value in `web/static/locales/{lang}.json`.

Why dual-source instead of one `.po` for everything: gettext `.po` targets
short backend strings; the frontend uses i18next natively, and a TMS
(Crowdin/Weblate) can export both formats from one project.

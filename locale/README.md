# locale — localized resources

`locale/` holds everything that changes per language.  Two kinds, sharing
one language-package layout `locale/{lang}/…`:

| Kind | Location | Format | Flow |
|------|----------|--------|------|
| UI strings | `{lang}/LC_MESSAGES/storyloom.po` | gettext `.po` | `.po` → `.mo` (server) + `i18n-dict.js` (frontend), via `i18n_compile.py` |
| Long-form content | `{lang}/content/{doc}.md` | Markdown | served at `GET /content/{lang}/{doc}` (`web/server.py`); loaded by `loadLocalizedContent(doc)` with fallback to `en` |

Language codes: directories use POSIX locale names (`zh_CN`, `zh_TW`, `en`);
the app and the `/content/` URL use BCP-47 (`zh-CN`, `zh-TW`, `en`).  The
server maps `-` → `_` on lookup, mirroring `i18n.py`.

`en` is the source language — it holds `content/` but no `LC_MESSAGES/`
(English strings are the `msgid` source in the `.po` files).

To add a long-form document: drop `{lang}/content/{doc}.md` for each
language and call `loadLocalizedContent("doc")` — no server change needed.

Why content isn't in `.po`: gettext `msgid`/`msgstr` targets short UI
strings; paragraph-level Markdown is *content*, so it lives as per-locale
files (the Docusaurus / Next.js pattern).

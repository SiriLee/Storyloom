/* ═══════════════════════════════════════════════════════════════════
   state.js — Front-end game state + i18n

   GameState singleton holds all client-side game state:
     gameId, roundCount, currentNode, endingFlag,
     outlineNodes, stateVars, displayMode, speedPreset, lang.

   _(msgid, opts) — i18n lookup via i18next.  Mirrors server-side gettext
              _() convention.  Keys are English source strings (msgid);
              translations come from JSON resources under
              web/static/locales/{lang}.json.

   i18next is the frontend translation runtime; resources are fetched per
   language via the http backend (vendor/i18nextHttpBackend.min.js).
   Frontend JSON and backend .po are independent (dual-source) — no
   dual-write.

   Authority:
     src/storyloom/i18n.py (backend gettext _() convention)
     src/storyloom/locale/zh_CN/LC_MESSAGES/storyloom.po (backend strings)
     src/storyloom/web/static/locales/{lang}.json (frontend strings)
   ═══════════════════════════════════════════════════════════════════ */

/* ── Shared constants ─────────────────────────────────────────────── */
/* Must match server-side values (src/storyloom/config.py).  */

/** Virtual path prefix for all asset images.  The server resolves this
 *  to the correct filesystem directory (media/ or system_media/).  */
const MEDIA_PATH = "/media";

/* ═══════════════════════════════════════════════════════════════════ */

const GameState = {
    gameId: null,
    gameMode: null,           // §7.7: "text" | "graph" — set from API response
    roundCount: 0,
    currentNode: null,
    endingFlag: false,
    outlineNodes: [],
    stateVars: {},
    displayMode: "auto",
    speedPreset: "normal",
    lang: localStorage.getItem("storyloom-lang") || "en",

    /** Story config from co-creation, set before game/new.
     *  Populated by _handleStart() in co-create.js after generate(). */
    storyConfig: null,

    /** Save file selected from checkpoint list.  When set, game-preview
     *  loads this file instead of ``_init.json``. */
    saveFile: null,

    /** Reset all per-game state.  Called on menu entry. */
    reset() {
        this.gameId = null;
        this.gameMode = null;  // §7.7
        this.roundCount = 0;
        this.currentNode = null;
        this.endingFlag = false;
        this.outlineNodes = [];
        this.stateVars = {};
        this.storyConfig = null;
        this.saveFile = null;
    },

    /** Set language and persist to localStorage.  Returns the
     *  i18next.changeLanguage promise so callers can await the resource
     *  load before re-rendering. */
    setLang(lang) {
        this.lang = lang;
        localStorage.setItem("storyloom-lang", lang);
        document.documentElement.lang = lang;
        return i18next.changeLanguage(lang);
    },
};

/* ── Theme State ──────────────────────────────────────────────────── */
/* Manages data-theme attribute on <html>.  Persisted to localStorage.
   Values: "system" (default), "dark", "light".
   The CSS variable system (theme-dark.css / theme-light.css) reacts
   to [data-theme] selectors, including @media prefers-color-scheme
   when data-theme="system".                                           */

const ThemeState = {
    _key: "storyloom-theme",

    /** Get the current stored preference ("system" | "dark" | "light"). */
    get current() {
        return document.documentElement.getAttribute("data-theme") || "system";
    },

    /** Get the effective resolved theme ("dark" or "light"). */
    get effective() {
        if (this.current === "system") {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
                ? "dark" : "light";
        }
        return this.current;
    },

    /** Initialize: read localStorage, apply data-theme, listen for OS changes. */
    init() {
        const saved = localStorage.getItem(this._key) || "system";
        document.documentElement.setAttribute("data-theme", saved);

        // Listen for OS theme changes — only matters in "system" mode.
        this._mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
        this._mediaQuery.addEventListener("change", () => {
            if (this.current === "system") {
                // Force CSS re-evaluation by re-applying the attribute.
                document.documentElement.setAttribute("data-theme", "system");
            }
        });
    },

    /** Set theme to a specific value. */
    set(value) {
        if (value !== "system" && value !== "dark" && value !== "light") return;
        document.documentElement.setAttribute("data-theme", value);
        localStorage.setItem(this._key, value);
    },

    /** Toggle: dark ↔ light.  System is only selectable via Appearance settings.
     *  If current is "system", resolves to the effective theme first. */
    toggle() {
        const next = this.effective === "dark" ? "light" : "dark";
        this.set(next);
        return next;
    },
};

/* ── Settings ────────────────────────────────────────────────────── */
/* Settings storage + persistence helpers.  The data-driven SETTINGS
   array was removed in the 2026-08-10 redesign — the settings UI is
   now rendered by router.js (_renderSettingsSection / factory
   functions).  The config keys and localStorage schema below remain
   authoritative and are unchanged.

   All setting values are persisted in localStorage under the key
   "storyloom-setting-<key>".  The "lang" setting is mirrored to
   GameState.lang for convenience.

   Authority: keys, defaults, and structure mirror
              src/storyloom/user_config.py UserConfig._DEFAULTS. */

const SETTINGS_STORE = "storyloom-setting-";

/* ── Language mode ──────────────────────────────────────────────────── */
/* Tracks whether the user chose "system" (follow browser language) or
   "manual" (explicit language selection).  Persisted in localStorage.
   When "system", the effective language is re-resolved from the browser
   on every page load.  The server always stores a concrete language code
   for i18n purposes — it never receives the sentinel "system" value.    */

const LANG_MODE_KEY = "storyloom-lang-mode";

function getLangMode() {
    return localStorage.getItem(LANG_MODE_KEY) || "system";
}

function setLangMode(mode) {
    localStorage.setItem(LANG_MODE_KEY, mode);
}

/** Resolve browser language to a supported language code.
 *  Strategy: direct match first (e.g. "zh-TW"), then primary-language
 *  prefix fallback (e.g. "zh" → "zh-CN"), finally "en" as ultimate
 *  default.  The returned value is always a member of the server-side
 *  SUPPORTED_LANGUAGES set. */
function resolveBrowserLang() {
    var raw = navigator.language || "en";
    // Direct match — covers zh-CN, zh-TW, en, en-US (normalized below)
    var supported = ["zh-CN", "zh-TW", "en"];
    if (supported.indexOf(raw) !== -1) return raw;
    // Prefix fallback (zh-* → zh-CN, en-* → en)
    var primary = raw.split("-")[0];
    var prefixMap = { "zh": "zh-CN", "en": "en" };
    if (prefixMap[primary]) return prefixMap[primary];
    // Ultimate default
    return "en";
}

/* ── Deprecated SETTINGS array (2026-08-10 redesign) ──────────────
 * Kept as reference for config key definitions.
 * Router now uses _renderSettingsSection / factory functions instead.
 *
 * Keys previously driven by this array:
 *   lang, game_mode, api_base_url, api_key, api_model,
 *   img_generation_enabled, img_api_base_url, img_api_key,
 *   img_api_model, portrait_remove_bg
 *
 * Types: select / text / password / toggle.  Placeholders mirrored
 * src/storyloom/user_config.py UserConfig._DEFAULTS.
 * ──────────────────────────────────────────────────────────────── */

/** Get the current value of a setting by key.
 *  Reads from localStorage first (instant); server is the
 *  authoritative source loaded via initConfig() at startup.
 *  For api_key / img_api_key: returns the real key if set, otherwise
 *  falls back to the server-provided masked display hint.            */
function getSetting(key) {
    if (key === "lang") return GameState.lang;
    const val = localStorage.getItem(SETTINGS_STORE + key);
    if (val) return val;
    if (key === "api_key" || key === "img_api_key") {
        return localStorage.getItem(SETTINGS_STORE + key + "_display") || "";
    }
    return "";
}

/** Apply a setting change — localStorage immediately, then
 *  persist to config.json via UserConfig.save() in background.
 *  Returns true if the change requires a UI re-render.         */
function applySetting(key, value) {
    localStorage.setItem(SETTINGS_STORE + key, value);
    /* Once the user has typed a real key, the masked display hint
       is no longer needed. */
    if ((key === "api_key" || key === "img_api_key") && value && !value.includes("****")) {
        localStorage.removeItem(SETTINGS_STORE + key + "_display");
    }
    if (key === "lang") GameState.setLang(value);
    saveConfig();
    return key === "lang";
}

/** Push current settings to server → UserConfig.save(). */
async function saveConfig() {
    const key = getSetting("api_key");
    const imgKey = getSetting("img_api_key");
    /* Language: when lang_mode is "system", resolve the effective language
       to send to the server (server never receives the sentinel "system"). */
    var langToSave = getSetting("lang");
    if (getLangMode() === "system") {
        langToSave = resolveBrowserLang();
    }
    const body = {
        language: langToSave,
        theme: ThemeState.current,
        accent_color: getSetting("accent_color") || "green",
        game_mode: getSetting("game_mode"),
        api_base_url: getSetting("api_base_url"),
        api_model: getSetting("api_model"),
        img_api_base_url: getSetting("img_api_base_url"),
        img_api_model: getSetting("img_api_model"),
        portrait_remove_bg: getSetting("portrait_remove_bg"),
        img_generation_enabled: getSetting("img_generation_enabled") !== "false",
        proxy_url: getSetting("proxy_url") || "",
    };
    /* Only send api_key if the user typed a real one — an empty or
       masked value means "keep the existing key on disk". */
    if (key && !key.includes("****")) body.api_key = key;
    if (imgKey && !imgKey.includes("****")) body.img_api_key = imgKey;

    try { await API.post("/api/config", body); } catch (err) {
        console.warn("saveConfig: server unreachable, values in localStorage only", err);
        if (typeof showToast !== "undefined") showToast(_("Failed to save settings"), 4000);
    }
}

/** Pull config from server (UserConfig properties) at startup.
 *  Populates localStorage + GameState.lang.  Call once on load. */
async function initConfig() {
    try {
        /* Check config version before loading — migration may be needed. */
        const status = await API.get("/api/config/version-status");
        if (status.needs_migration) {
            GameState.needsMigration = status;
            return;  // stop — renderMenu() will show migration UI
        }

        const data = await API.get("/api/config");
        /* Language: resolve based on lang_mode.  "system" → browser language;
           "manual" → server-stored language.  Default lang_mode is "system"
           so first-time users automatically get their browser language. */
        var langMode = getLangMode();
        var effectiveLang;
        if (langMode === "system") {
            effectiveLang = resolveBrowserLang();
        } else {
            effectiveLang = data.language || "en";
        }
        await GameState.setLang(effectiveLang);
        localStorage.setItem(SETTINGS_STORE + "lang", effectiveLang);
        /* If system mode, push the resolved language to the server so the
           stored config stays in sync (don't wait for explicit save). */
        if (langMode === "system" && effectiveLang !== data.language) {
            try {
                await API.post("/api/config", { language: effectiveLang });
            } catch (_) { /* non-critical — will sync on next saveConfig */ }
        }
        /* Server returns masked key for display hint only.
           Store it separately so the masked value never pollutes
           the editable api_key slot — saveConfig's guard relies on
           this separation. */
        if (data.api_key) {
            localStorage.setItem(SETTINGS_STORE + "api_key_display", data.api_key);
        }
        if (data.api_base_url) {
            localStorage.setItem(SETTINGS_STORE + "api_base_url", data.api_base_url);
        }
        if (data.api_model) {
            localStorage.setItem(SETTINGS_STORE + "api_model", data.api_model);
        }
        if (data.img_api_key) {
            localStorage.setItem(SETTINGS_STORE + "img_api_key_display", data.img_api_key);
        }
        if (data.img_api_base_url) {
            localStorage.setItem(SETTINGS_STORE + "img_api_base_url", data.img_api_base_url);
        }
        if (data.img_api_model) {
            localStorage.setItem(SETTINGS_STORE + "img_api_model", data.img_api_model);
        }
        if (data.portrait_remove_bg) {
            localStorage.setItem(SETTINGS_STORE + "portrait_remove_bg", data.portrait_remove_bg);
        }
        if (data.img_generation_enabled !== undefined) {
            localStorage.setItem(SETTINGS_STORE + "img_generation_enabled",
                data.img_generation_enabled ? "true" : "false");
        }
        if (data.proxy_url !== undefined) {
            localStorage.setItem(SETTINGS_STORE + "proxy_url", data.proxy_url);
        }
        if (data.game_mode) {
            localStorage.setItem(SETTINGS_STORE + "game_mode", data.game_mode);
        }
        if (data.theme) {
            ThemeState.set(data.theme);
        }
        if (data.accent_color) {
            localStorage.setItem(SETTINGS_STORE + "accent_color", data.accent_color);
            /* Apply accent CSS variables on page load — _applyAccentColor
               is exported by router.js (which loads before initConfig runs). */
            if (typeof window._applyAccentColor === "function") {
                window._applyAccentColor(data.accent_color);
            }
        }
    } catch (err) {
        console.warn("initConfig: server unreachable, using localStorage", err);
    }
    ThemeState.init();
}

// i18next — frontend translation runtime.  Translations live in
// /static/locales/{lang}.json (separate from the backend gettext .po
// catalogs) and are fetched via the http backend.
i18next.use(i18nextHttpBackend);

/** Load translation resources.  Await before the first render so no view
 *  paints in the untranslated (English-key) state. */
async function initI18n() {
    await i18next.init({
        lng: GameState.lang,
        fallbackLng: "en",
        backend: { loadPath: "/static/locales/{{lng}}.json" },
        // Interpolated values (condition text, state values) are inserted
        // via textContent, not innerHTML — disable default HTML escaping.
        interpolation: { escapeValue: false },
    });
}

/**
 * Look up a translated string.
 * Mirrors server-side gettext _() convention.
 *
 * @param {string} msgid — English source string (the i18next key)
 * @param {object} [opts] — interpolation variables (e.g. {cond: "x"})
 * @returns {string} translated string in the current language,
 *                   or msgid itself if no translation exists
 */
function _(msgid, opts) {
    return i18next.t(msgid, opts);
}

/**
 * Show a temporary toast notification that auto-dismisses.
 *
 * @param {string} message — already-translated string to display
 * @param {number} duration — ms before auto-dismiss (default 3000)
 */
function showToast(message, duration = 3000) {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        document.body.appendChild(container);
    }
    const toast = document.createElement("div");
    toast.className = "toast";
    toast.textContent = message;
    container.appendChild(toast);
    /* trigger reflow for enter animation */
    void toast.offsetWidth;
    toast.classList.add("toast--visible");
    setTimeout(() => {
        toast.classList.remove("toast--visible");
        const cleanup = () => {
            toast.remove();
            toast.removeEventListener("transitionend", cleanup);
        };
        toast.addEventListener("transitionend", cleanup);
        /* Fallback: force-remove after transition duration in case
           transitionend never fires (e.g. element removed from DOM). */
        setTimeout(cleanup, 500);
    }, duration);
}

/**
 * True when running inside a pywebview desktop window.
 * Used to switch download/export from browser Blob/anchor
 * patterns to the native save-dialog bridge (pywebview.api).
 */
function isPywebview() {
    return typeof window.pywebview !== "undefined"
        && typeof window.pywebview.api !== "undefined";
}

/**
 * Mark external (http/https) links inside *root* to open in a new tab.
 *
 * In pywebview a plain `<a href="https://…">` navigates the webview window
 * itself — stranding the user with no way back to the app.  Only links
 * carrying `target="_blank"` are routed to the system default browser
 * (pywebview's OPEN_EXTERNAL_LINKS_IN_BROWSER, on by default).  marked.js
 * does not add the attribute, so Markdown-rendered content (API guide,
 * adventure log) needs it applied after rendering.
 *
 * @param {Element} root — container whose descendant links to inspect
 */
function markExternalLinks(root) {
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("a[href]").forEach(function (a) {
        var href = a.getAttribute("href") || "";
        if (/^https?:\/\//i.test(href)) {
            a.setAttribute("target", "_blank");
            a.setAttribute("rel", "noopener");
        }
    });
}

/**
 * Fetch a localized long-form content document (Markdown) from the server.
 *
 * Documents live under locale/{lang}/content/{doc}.md and are served at
 * /content/{lang}/{doc}.  The active language is tried first, then English
 * as a fallback — so a missing translation never breaks the document.
 *
 * @param {string} doc — document name, e.g. "guide" (must be a slug)
 * @returns {Promise<string|null>} raw Markdown, or null if unavailable
 */
async function loadLocalizedContent(doc) {
    var lang = (typeof GameState !== "undefined" && GameState.lang)
        ? GameState.lang : "en";
    var candidates = lang === "en" ? ["en"] : [lang, "en"];
    for (var i = 0; i < candidates.length; i++) {
        try {
            var res = await fetch("/content/" + candidates[i] + "/" + doc);
            if (res.ok) return await res.text();
        } catch (e) {
            /* fetch failed — try the next candidate */
        }
    }
    return null;
}

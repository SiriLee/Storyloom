/* ═══════════════════════════════════════════════════════════════════
   state.js — Front-end game state + i18n

   GameState singleton holds all client-side game state:
     gameId, roundCount, currentNode, endingFlag,
     outlineNodes, stateVars, displayMode, speedPreset, lang.

   _(msgid) — i18n lookup.  Mirrors server-side gettext _() convention.
              Keys are English source strings (msgid); translations come
              from the dictionary matching GameState.lang.

   The ``T`` translation dictionary is auto-generated from .po files
   into i18n-dict.js (loaded before this script).  .po is now the
   single authoritative source — no more dual-write.

   Authority:
     src/storyloom/i18n.py (gettext _() convention)
     locale/zh_CN/LC_MESSAGES/storyloom.po (authoritative translations)
     src/storyloom/i18n_compile.py §generate_js_dict (build-time generation)
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

    /** Set language and persist to localStorage. */
    setLang(lang) {
        this.lang = lang;
        localStorage.setItem("storyloom-lang", lang);
        document.documentElement.lang = lang;
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
    const body = {
        language: getSetting("lang"),
        game_mode: getSetting("game_mode"),
        api_base_url: getSetting("api_base_url"),
        api_model: getSetting("api_model"),
        img_api_base_url: getSetting("img_api_base_url"),
        img_api_model: getSetting("img_api_model"),
        portrait_remove_bg: getSetting("portrait_remove_bg"),
        img_generation_enabled: getSetting("img_generation_enabled") !== "false",
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
        if (data.language) {
            GameState.setLang(data.language);
            localStorage.setItem(SETTINGS_STORE + "lang", data.language);
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
        if (data.game_mode) {
            localStorage.setItem(SETTINGS_STORE + "game_mode", data.game_mode);
        }
    } catch (err) {
        console.warn("initConfig: server unreachable, using localStorage", err);
    }
    ThemeState.init();
}

/**
 * Look up a translated string.
 * Mirrors server-side gettext _() convention.
 *
 * @param {string} msgid — English source string
 * @returns {string} translated string in the current language,
 *                   or msgid itself if no translation exists
 */
function _(msgid) {
    const dict = T[GameState.lang];
    if (dict && dict[msgid] !== undefined) return dict[msgid];
    return msgid;
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

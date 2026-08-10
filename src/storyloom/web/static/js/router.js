/* ═══════════════════════════════════════════════════════════════════
   router.js — Hash-based SPA router + view renderers

   Views:
     #menu            — main menu (new game / continue / load save / settings / credits / exit)
     #co-create       — co-creation Q&A view
     #game-preview    — story preview between co-create and game start
     #game/{id}       — game play view with SSE loop + paced display
     #saves           — save browse / load / delete
     #saves/{game_id} — checkpoint list for a game
     #settings        — full-page settings (API config, language)
     #adventure-log/{game_id} — post-ending adventure log

   Exports (on window):
     Router.navigate(hash)  — switch view
     Router.dispatch()      — re-render current route

   Authority:
     CLAUDE.local.md §3.2 (event flow consumption)
     exec-flow.md §4.1 (event types)
     web-reference hash routing pattern (structural reference only)
   ═══════════════════════════════════════════════════════════════════ */

(function () {
    const app = document.getElementById("app");

    /** Cleanup callback for the currently-active view.  Set by views
     *  that hold timers/polls (adventure-log) and invoked on every
     *  dispatch so navigating away (browser-back, hash change) releases
     *  them — not just the per-view back button. */
    let _currentViewCleanup = null;

    /** Tiny HTML escape — inline until display.js is implemented. */
    function esc(s) {
        const d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    /** Trash can icon (Feather-style SVG, 16×16). */
    const TRASH_ICON = `<svg width="16" height="16" viewBox="0 0 24 24" `
        + `fill="none" stroke="currentColor" stroke-width="2" `
        + `stroke-linecap="round" stroke-linejoin="round">`
        + `<polyline points="3 6 5 6 21 6"/>`
        + `<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>`
        + `<line x1="10" y1="11" x2="10" y2="17"/>`
        + `<line x1="14" y1="11" x2="14" y2="17"/>`
        + `</svg>`;

    // ── Route table ────────────────────────────────────────────────

    const routes = {
        "": renderMenu,
        "menu": renderMenu,
        "co-create": renderCoCreate,
        "game": renderGame,
        "game-preview": renderGamePreview,
        "saves": renderSaveList,
        "settings": renderSettings,
        "adventure-log": renderAdventureLog,
        "assets": renderAssetManager,
    };

    // ── Bootstrap ──────────────────────────────────────────────────

    async function init() {
        await initConfig();
        window.addEventListener("hashchange", dispatch);
        dispatch();
    }

    function dispatch() {
        /* Run the previous view's cleanup (e.g. adventure-log poll
           timer) before rendering the new route — covers browser-back
           and manual hash changes that bypass per-view buttons. */
        if (_currentViewCleanup) {
            _currentViewCleanup();
            _currentViewCleanup = null;
        }

        const hash = location.hash.replace("#", "") || "";
        const parts = hash.split("/");
        const view = parts[0];
        const gameId = parts[1] || null;

        /* #saves/{game_id} → checkpoint list; #saves → game list */
        if (view === "saves" && gameId) {
            renderCheckpointList(decodeURIComponent(gameId));
            return;
        }

        /* #game/{game_id} → narrative view */
        if (view === "game" && gameId) {
            renderGame(decodeURIComponent(gameId));
            return;
        }

        /* #adventure-log/{game_id} → post-ending adventure log */
        if (view === "adventure-log" && gameId) {
            renderAdventureLog(decodeURIComponent(gameId));
            return;
        }

        const render = routes[view] || routes[""];
        if (render) render();
    }

    function navigate(hash) {
        location.hash = hash;
    }

    window.Router = { navigate, dispatch };
    /* Export theme helpers at module load time so all views can use
       them on first render (previously these only ran when a theme
       toggle was clicked — first load of #co-create / #game / #assets /
       #adventure-log threw ReferenceError). */
    window._updateThemeButton = _updateThemeButton;
    window._updateAllThemeButtons = _updateAllThemeButtons;

    /* ═══════════════════════════════════════════════════════════════
       View: Main Menu (#menu / default)
       ──────────────────────────────────────────────────────────────
       Layout:
         centered "Storyloom" title
         6 buttons: New Game | Continue | Load Save | Settings | Credits | Exit
         hover → scale(1.08) grow (CSS-driven, no JS animation)

       Button behaviors:
         New Game  → navigate to #co-create
         Continue  → fetch /api/saves/games, show recent saves inline
         Load Save → navigate to #saves
         Settings  → navigate to #settings (full-page view)
         Credits   → open credits overlay
         Exit      → close window / navigate to goodbye
       ═══════════════════════════════════════════════════════════════ */

    function renderMenu() {
        // ── Config migration check (before normal menu) ────────────
        if (GameState.needsMigration) {
            _renderMigrationWarning();
            return;
        }

        // Best-effort stop any lingering game stream — catches
        // browser-back and manual hash changes that bypass the
        // per-view quit button.  Capture gameId before reset() clears it.
        const activeGameId = GameState.gameId;
        if (activeGameId && typeof API !== "undefined") {
            API.post(`/api/game/${encodeURIComponent(activeGameId)}/stop`).catch(() => {});
        }

        GameState.reset();
        // SSEClient may not be loaded yet — guard
        if (typeof SSEClient !== "undefined" && SSEClient.close) {
            SSEClient.close();
        }
        // Best-effort abort any lingering co-create session —
        // catches browser-back and manual hash changes that bypass
        // the per-view back buttons.
        API.post("/api/co-create/abort").catch(() => {});

        app.innerHTML = `
            <div class="menu-view">
                <h1 class="menu-title">${esc(_("Storyloom"))}</h1>
                <p class="menu-subtitle">${esc(_("AI Text Adventure"))}</p>

                <div class="menu-buttons">
                    <button class="menu-btn accent" id="btn-new-game">
                        ${esc(_("New Game"))}
                    </button>
                    <button class="menu-btn" id="btn-continue">
                        ${esc(_("Continue"))}
                    </button>
                    <button class="menu-btn" id="btn-load-save">
                        ${esc(_("Load Save"))}
                    </button>
                    <button class="menu-btn" id="btn-settings">
                        ${esc(_("Settings"))}
                    </button>
                    <button class="menu-btn" id="btn-assets">
                        ${esc(_("Asset Management"))}
                    </button>
                    <button class="menu-btn" id="btn-exit">
                        ${esc(_("Exit"))}
                    </button>
                </div>

                <!-- Continue panel: shown when "Continue" clicked, hidden initially -->
                <div id="continue-panel" class="continue-panel hidden"></div>

            </div>
        `;

        // ── Button 1: New Game ────────────────────────────────────

        document.getElementById("btn-new-game").addEventListener("click", () => {
            navigate("co-create");
        });

        // ── Button 2: Continue (auto-resume last played save) ─────────────
        // Reads .last_played.json (O(1)) — no selection UI.

        document.getElementById("btn-continue").addEventListener("click", async () => {
            const panel = document.getElementById("continue-panel");
            panel.classList.remove("hidden");
            panel.innerHTML = `<p class="text-muted">${esc(_("Loading..."))}</p>`;

            try {
                const lp = await API.get("/api/saves/last-played");
                if (!lp || !lp.game_id || !lp.save_file) {
                    showToast(_("No saves found"));
                    panel.classList.add("hidden");
                    return;
                }
                const res = await API.post(
                    `/api/saves/${encodeURIComponent(lp.game_id)}/start/${encodeURIComponent(lp.save_file)}`
                );
                GameState.gameId = res.game_id;
                GameState.gameMode = res.game_mode || "text";  // §7.7
                GameState.roundCount = res.round_count || 0;
                GameState.currentNode = res.current_node || null;
                GameState.storyConfig = res.story_config || {};
                panel.classList.add("hidden");
                navigate("game-preview");
            } catch (err) {
                console.error("Continue failed:", err);
                showToast(_("Something went wrong"));
                panel.classList.add("hidden");
            }
        });

        // ── Button 3: Load Save ───────────────────────────────────

        document.getElementById("btn-load-save").addEventListener("click", () => {
            navigate("saves");
        });

        // ── Button 4: Settings → full-page view ──

        document.getElementById("btn-settings").addEventListener("click", () => {
            navigate("settings");
        });

        // ── Button 5: Asset Management ─────────────────────────

        document.getElementById("btn-assets").addEventListener("click", () => {
            navigate("assets");
        });

        // ── Button 6: Exit ────────────────────────────────────────
        // Show a terminal goodbye screen immediately, then attempt
        // server shutdown.  In a packaged app the server kills the
        // process; in dev mode the user closes the tab manually.

        document.getElementById("btn-exit").addEventListener("click", async () => {
            // 1. Render terminal state — no interactive elements remain
            app.innerHTML = `
                <div class="menu-view">
                    <h1 class="menu-title">${esc(_("Storyloom"))}</h1>
                    <p style="font-size:1.3rem; color:var(--text-accent); margin-top:2rem">
                        ${esc(_("Goodbye"))}
                    </p>
                    <p class="text-muted" style="margin-top:0.5rem">
                        ${esc(_("You may close this tab."))}
                    </p>
                </div>
            `;

            // 2. Attempt graceful server shutdown (works in packaged app)
            try { await API.post("/api/exit"); } catch (_) { /* expected in dev */ }
        });
    }

    /* ── Shared Helpers ──────────────────────────────────────────── */

    /** Render config migration warning when config.json version is outdated.
     *  User must confirm reset or exit — normal menu is blocked. */
    function _renderMigrationWarning() {
        const ver = GameState.needsMigration;
        app.innerHTML = `
            <div class="menu-view">
                <h1 class="menu-title">${esc(_("Storyloom"))}</h1>

                <div class="migration-warning">
                    <div class="migration-icon">&#9888;</div>
                    <h2>${esc(_("Config Version Mismatch"))}</h2>
                    <p class="migration-text">${esc(_(
                        "Your configuration file is from an older version and needs to be reset. Please note down your API keys and other settings before continuing."
                    ))}</p>
                    <p class="text-muted" style="font-size:0.85rem">
                        ${esc(_("Current version:"))} ${esc(String(ver.current_version))}
                        &rarr; ${esc(_("Expected version:"))} ${esc(String(ver.expected_version))}
                    </p>
                    <div class="migration-actions">
                        <button class="menu-btn danger" id="btn-migrate-exit">
                            ${esc(_("Exit Application"))}
                        </button>
                        <button class="menu-btn accent" id="btn-migrate-confirm">
                            ${esc(_("Reset and Restart"))}
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.getElementById("btn-migrate-confirm").addEventListener("click", async () => {
            try {
                await API.post("/api/config/migrate");
            } catch (_) { /* server may already be shutting down */ }
            // Config has been reset — show goodbye and exit.
            app.innerHTML = `
                <div class="menu-view">
                    <h1 class="menu-title">${esc(_("Storyloom"))}</h1>
                    <p style="font-size:1.3rem; color:var(--text-accent); margin-top:2rem">
                        ${esc(_("Configuration reset. Please restart the application."))}
                    </p>
                    <p class="text-muted" style="margin-top:0.5rem">
                        ${esc(_("You may close this tab."))}
                    </p>
                </div>
            `;
            try { await API.post("/api/exit"); } catch (_) { /* expected */ }
        });

        document.getElementById("btn-migrate-exit").addEventListener("click", async () => {
            // Show goodbye, then attempt server shutdown
            app.innerHTML = `
                <div class="menu-view">
                    <h1 class="menu-title">${esc(_("Storyloom"))}</h1>
                    <p style="font-size:1.3rem; color:var(--text-accent); margin-top:2rem">
                        ${esc(_("Goodbye"))}
                    </p>
                    <p class="text-muted" style="margin-top:0.5rem">
                        ${esc(_("You may close this tab."))}
                    </p>
                </div>
            `;
            try { await API.post("/api/exit"); } catch (_) { /* expected in dev */ }
        });
    }

    /** Mask an API key for display: "sk-9a70****3000". */
    function maskKey(key) {
        if (!key || key.length < 8) return key ? "****" : "";
        return key.slice(0, 4) + "****" + key.slice(-4);
    }

    /* ═══════════════════════════════════════════════════════════════
       View: Co-Create (#co-create)
       ──────────────────────────────────────────────────────────────
       Full chat-style Q&A interface for co-creating the story setup.
       Delegates to CoCreateView.render() (co-create.js).

       Layout:
         top bar:  /quit (left)  |  "Co-Create" title (center)
         messages: scrollable chat bubbles (assistant / user / info / error)
         input bar:  textarea + ↑ send button + /go button
       ═══════════════════════════════════════════════════════════════ */

    function renderCoCreate() {
        CoCreateView.render(app);
    }

    /* ═══════════════════════════════════════════════════════════════
       View: Settings (#settings) — sidebar layout

       Layout:
         header:  ← Back button (left) + "Settings" title + theme toggle (right)
         body:    left sidebar (200px nav) + right content (cards)

       Sidebar sections: General, API, Image, Appearance,
                         — divider —
                         API Guide, Credits, Updates

       Authority:
         2026-08-10-frontend-redesign.md §3
       ═══════════════════════════════════════════════════════════════ */

    function renderSettings() {
        GameState.reset();
        if (typeof SSEClient !== "undefined" && SSEClient.close) {
            SSEClient.close();
        }

        /* Scroll-tracked settings sections + secondary sections after divider */
        var settingsSections = [
            { id: "general",    icon: "globe",   label: _("General") },
            { id: "api",        icon: "key",     label: _("API") },
            { id: "image",      icon: "image",   label: _("Image") },
            { id: "appearance", icon: "palette", label: _("Appearance") },
            { id: "updates",    icon: "refresh", label: _("Updates") },
        ];
        var secondarySections = [
            { id: "guide",      icon: "book",    label: _("API Guide") },
            { id: "credits",    icon: "heart",   label: _("Credits") },
        ];

        var currentSection = "general";

        /* ── Render shell ─────────────────────────────────────────── */
        app.innerHTML =
            '<div class="settings-view">'
            + '<div class="settings-header">'
            + '<button class="cc-back-btn" id="settings-back" '
            + 'title="' + esc(_("Back to Menu")) + '">' + Icons.arrowLeft() + '</button>'
            + '<span class="settings-title">' + esc(_("Settings")) + '</span>'
            + '<button class="theme-toggle-btn" id="settings-theme-btn" '
            + 'title="' + esc(_("Toggle Theme")) + '"></button>'
            + '</div>'
            + '<div class="settings-body">'
            + '<nav class="settings-nav" id="settings-nav"></nav>'
            + '<div class="settings-content" id="settings-content">'
            + '<div class="settings-content-inner" id="settings-inner"></div>'
            + '</div>'
            + '</div>'
            + '</div>';

        /* ── Render sidebar ──────────────────────────────────────── */
        var nav = document.getElementById("settings-nav");
        var allSections = settingsSections.concat([{ id: null, icon: null, label: null }], secondarySections);
        nav.innerHTML = allSections.map(function (s) {
            if (s.id === null) return '<div class="settings-nav-divider"></div>';
            var cls = (s.id === currentSection)
                ? "settings-nav-item active" : "settings-nav-item";
            return '<button class="' + cls + '" data-section="' + s.id + '">'
                + Icons[s.icon]() + '<span>' + esc(s.label) + '</span></button>';
        }).join("");

        /* ── Render initial section ───────────────────────────────── */
        _settingsScrollActive = true;
        _renderSettingsSection(currentSection);

        /* ── Sidebar navigation ──────────────────────────────────── */
        nav.querySelectorAll(".settings-nav-item").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var sid = this.dataset.section;
                if (sid === currentSection) return;
                currentSection = sid;
                _updateSidebarActive(nav, sid);
                _renderSettingsSection(sid);
                // Scroll to the target section heading
                var heading = document.getElementById("section-" + sid);
                if (heading) heading.scrollIntoView({ behavior: "smooth", block: "start" });
            });
        });

        /* ── Scroll tracking: highlight sidebar as user scrolls ──── */
        var trackedIds = settingsSections.map(function (s) { return s.id; });
        var contentEl = document.getElementById("settings-content");

        contentEl.addEventListener("scroll", function () {
            if (!_settingsScrollActive) return;
            var scrollTop = contentEl.scrollTop + 80;
            var active = trackedIds[0];
            for (var i = trackedIds.length - 1; i >= 0; i--) {
                var el = document.getElementById("section-" + trackedIds[i]);
                if (el && el.offsetTop <= scrollTop) {
                    active = trackedIds[i];
                    break;
                }
            }
            if (active !== currentSection) {
                currentSection = active;
                _updateSidebarActive(nav, active);
            }
        });

        /* ── Back button ──────────────────────────────────────────── */
        document.getElementById("settings-back").addEventListener("click", function () {
            navigate("menu");
        });

        /* ── Theme toggle ─────────────────────────────────────────── */
        _bindThemeToggle(document.getElementById("settings-theme-btn"));
    }

    /** Update sidebar active state. */
    function _updateSidebarActive(nav, activeId) {
        nav.querySelectorAll(".settings-nav-item").forEach(function (b) {
            b.classList.toggle("active", b.dataset.section === activeId);
        });
    }

    /** Render a section heading (icon + text, matches sidebar weight). */
    function _sectionHeading(iconFn, text, sectionId) {
        return '<div class="settings-section-heading" id="section-' + esc(sectionId) + '">'
            + iconFn() + '<span class="settings-section-heading-text">' + esc(text) + '</span></div>';
    }

    /* ═══════════════════════════════════════════════════════════════
       Settings Section Renderers
       ═══════════════════════════════════════════════════════════════ */

    /** Dispatch to the correct section renderer. */
    function _renderSettingsSection(id) {
        var container = document.getElementById("settings-inner");
        if (!container) return;

        // Disable scroll tracking for non-settings sections (guide, credits)
        // so the sidebar doesn't jump when those headings aren't in the DOM.
        var tracked = ["general", "api", "image", "appearance", "updates"];
        _settingsScrollActive = tracked.indexOf(id) !== -1;

        switch (id) {
            case "general":    _renderGeneralSection(container);    break;
            case "api":        _renderApiSection(container);        break;
            case "image":      _renderImageSection(container);      break;
            case "appearance": _renderAppearanceSection(container); break;
            case "updates":    _renderUpdatesSection(container);    break;
            case "guide":      _renderApiGuideSection(container);   break;
            case "credits":    _renderCreditsSection(container);    break;
        }
    }

    function _renderGeneralSection(container) {
        var lang = getSetting("lang") || GameState.lang || "zh-CN";
        var gameMode = getSetting("game_mode") || "text";

        container.innerHTML =
            _sectionHeading(Icons.globe, _("General"), "general")
            + '<div class="settings-card">'
            + '<div class="settings-card-title">' + Icons.language() + esc(_("Language")) + '</div>'
            + '<div class="lang-grid">'
            + _langBtn("system", _("System"), lang, false)
            + _langBtn("zh-CN", "中文", lang, false)
            + _langBtn("zh-TW", "繁體中文", lang, false)
            + _langBtn("en", "English", lang, false)
            + _langBtn("ja", "日本語", lang, true)
            + _langBtn("ko", "한국어", lang, true)
            + '</div>'
            + '</div>'
            + '<div class="settings-card">'
            + '<div class="settings-card-title">' + Icons.gamepad() + esc(_("Game Mode")) + '</div>'
            + _settingSegmented("game_mode", "", [
                { value: "text", label: _("Text") },
                { value: "graph", label: _("Graph") },
            ], gameMode)
            + '</div>';
        _bindSettingsInputs(container);
    }

    function _langBtn(value, label, current, disabled) {
        var cls = "lang-btn";
        if (disabled) cls += "";
        else if (value === current) cls += " active";
        var disAttr = disabled ? " disabled" : "";
        return '<button class="' + cls + '" data-lang="' + esc(value) + '"' + disAttr + '>'
            + esc(label) + '</button>';
    }

    function _renderApiSection(container) {
        container.innerHTML =
            _sectionHeading(Icons.key, _("API"), "api")
            + '<div class="settings-card">'
            + '<div class="settings-card-title">' + Icons.key() + esc(_("API Configuration")) + '</div>'
            + _settingText("api_base_url", _("API Base URL"), "https://api.deepseek.com")
            + _settingPassword("api_key", _("API Key"), "sk-...")
            + _settingText("api_model", _("Model"), "deepseek-v4-pro")
            + '</div>';
        _bindSettingsInputs(container);
    }

    function _renderImageSection(container) {
        var enabled = getSetting("img_generation_enabled") !== "false";
        var cutout = getSetting("portrait_remove_bg") || "auto";

        container.innerHTML =
            _sectionHeading(Icons.image, _("Image"), "image")
            + '<div class="settings-card">'
            + '<div class="settings-card-title">' + Icons.sparkle() + esc(_("Image Generation")) + '</div>'
            + _settingToggle("img_generation_enabled", _("Image Generation"))
            + '</div>';

        if (enabled) {
            container.innerHTML +=
                '<div class="settings-card" id="image-settings-group">'
                + '<div class="settings-card-title">' + Icons.image() + esc(_("Image API")) + '</div>'
                + _settingText("img_api_base_url", _("Image API URL"), "https://api.apiyi.com/v1")
                + _settingPassword("img_api_key", _("Image API Key"), "sk-...")
                + _settingText("img_api_model", _("Image Model"), "flux-2-pro")
                + '</div>'
                + '<div class="settings-card">'
                + '<div class="settings-card-title">' + Icons.scissors() + esc(_("Sprite Cutout")) + '</div>'
                + _settingSegmented("portrait_remove_bg", "", [
                    { value: "never", label: _("Never") },
                    { value: "auto", label: _("Auto") },
                    { value: "always", label: _("Always") },
                ], cutout)
                + '</div>';
        }

        _bindSettingsInputs(container);
    }

    function _renderAppearanceSection(container) {
        var theme = ThemeState.current;
        var accent = getSetting("accent_color") || "green";

        var accentColors = [
            { id: "green",    color: "#3fb950", label: _("Green") },
            { id: "emerald",  color: "#10b981", label: _("Emerald") },
            { id: "blue",     color: "#3b82f6", label: _("Blue") },
            { id: "amber",    color: "#f59e0b", label: _("Amber") },
            { id: "rose",     color: "#f43f5e", label: _("Rose") },
            { id: "violet",   color: "#8b5cf6", label: _("Violet") },
        ];

        container.innerHTML =
            _sectionHeading(Icons.palette, _("Appearance"), "appearance")
            + '<div class="settings-card">'
            + '<div class="settings-card-title">' + Icons.palette() + esc(_("Theme")) + '</div>'
            + _settingSegmented("theme", "", [
                { value: "system", label: _("System") },
                { value: "dark", label: _("Dark") },
                { value: "light", label: _("Light") },
            ], theme)
            + '</div>'
            + '<div class="settings-card">'
            + '<div class="settings-card-title">' + Icons.palette() + esc(_("Accent Color")) + '</div>'
            + '<div class="accent-grid">'
            + accentColors.map(function (a) {
                var cls = a.id === accent ? "accent-tile active" : "accent-tile";
                return '<button class="' + cls + '" data-accent="' + esc(a.id) + '">'
                    + '<span class="accent-tile-swatch" style="background:' + a.color + '"></span>'
                    + '<span class="accent-tile-label">' + esc(a.label) + '</span>'
                    + '</button>';
            }).join("")
            + '</div>'
            + '</div>';
        _bindSettingsInputs(container);
    }

    function _renderCreditsSection(container) {
        container.innerHTML =
            '<div class="settings-card">'
            + '<div class="settings-card-title">' + esc(_("Credits")) + '</div>'
            + '<div class="settings-credits-group">'
            + '<h3>' + esc(_("Developers")) + '</h3>'
            + '<p class="settings-credits-name">'
            + CREDITS.developers.map(function (p) {
                return '<a class="settings-credits-link" href="' + esc(p.url)
                    + '" target="_blank" rel="noopener">' + esc(p.name) + '</a>';
            }).join(" ")
            + '</p>'
            + '</div>'
            + '<div class="settings-credits-group">'
            + '<h3>' + esc(_("Contributors")) + '</h3>'
            + '<p class="settings-credits-name">'
            + CREDITS.contributors.map(function (p) {
                return '<a class="settings-credits-link" href="' + esc(p.url)
                    + '" target="_blank" rel="noopener">' + esc(p.name) + '</a>';
            }).join(" ")
            + '</p>'
            + '</div>'
            + '</div>';
    }

    function _renderUpdatesSection(container) {
        container.innerHTML =
            _sectionHeading(Icons.refresh, _("Updates"), "updates")
            + '<div class="settings-card">'
            + '<div class="settings-card-title">' + Icons.refresh() + esc(_("Updates")) + '</div>'
            + '<div class="settings-row">'
            + '<span class="settings-row-label">' + esc(_("Current Version")) + '</span>'
            + '<span class="settings-row-value" id="update-current-ver">...</span>'
            + '<button class="settings-row-edit" id="btn-check-update" '
            + 'style="width:auto;padding:0.35rem 0.9rem;border:1px solid var(--border-color);'
            + 'border-radius:var(--radius-sm);font-family:var(--font-sans);font-size:0.85rem">'
            + esc(_("Check for Updates")) + '</button>'
            + '</div>'
            + '</div>';

        /* Lazy-load current version */
        API.get("/api/update/check?force=false").then(function (result) {
            var el = document.getElementById("update-current-ver");
            if (el) el.textContent = result.app.current;
        }).catch(function () {
            var el = document.getElementById("update-current-ver");
            if (el) el.textContent = "?";
        });

        /* Bind update check button — direct API call.  Do NOT go through
           _bindUpdateCheck() (it would add ANOTHER click handler on every
           click, accumulating listeners).  Replicates the same flow inline. */
        var btn = document.getElementById("btn-check-update");
        if (btn) {
            btn.addEventListener("click", function () {
                btn.disabled = true;
                btn.textContent = "...";

                API.get("/api/update/check?force=true").then(function (result) {
                    btn.disabled = false;
                    btn.textContent = _("Check for Updates");
                    var el = document.getElementById("update-current-ver");
                    if (el) el.textContent = result.app.current;

                    if (!result.app.has_update && !result.system_media.has_update) {
                        showToast(_("Up to date"));
                        return;
                    }
                    _showUpdatePopup(result);
                }).catch(function (err) {
                    btn.disabled = false;
                    btn.textContent = _("Check for Updates");
                    showToast(_("Check failed") + ": " + err.message);
                });
            });
        }
    }

    function _renderApiGuideSection(container) {
        container.innerHTML =
            '<div class="settings-card">'
            + '<div class="settings-guide" id="guide-content">'
            + '<p class="settings-empty-card">' + esc(_("Loading...")) + '</p>'
            + '</div>'
            + '</div>';

        if (typeof marked !== "undefined" && typeof API_GUIDE_MD !== "undefined") {
            try {
                var html = marked.parse(API_GUIDE_MD);
                document.getElementById("guide-content").innerHTML = html;
            } catch (e) {
                document.getElementById("guide-content").innerHTML =
                    '<div class="settings-error-card">'
                    + '<div class="settings-error-icon">!</div>'
                    + '<p>' + esc(_("Failed to render API guide.")) + '</p>'
                    + '</div>';
            }
        } else {
            document.getElementById("guide-content").innerHTML =
                '<div class="settings-error-card">'
                + '<p>' + esc(_("API guide unavailable. Please check your installation.")) + '</p>'
                + '</div>';
        }
    }

    /* ═══════════════════════════════════════════════════════════════
       Settings Row Factories
       ═══════════════════════════════════════════════════════════════ */

    /** Render a select dropdown row. */
    function _settingSelect(key, label, options) {
        var current = getSetting(key);
        var opts = options.map(function (o) {
            var sel = o.value === current ? " selected" : "";
            return '<option value="' + esc(o.value) + '"' + sel + '>' + esc(o.label) + '</option>';
        }).join("");
        return '<div class="settings-row">'
            + '<span class="settings-row-label">' + esc(label) + '</span>'
            + '<select class="settings-row-select" data-key="' + esc(key) + '">' + opts + '</select>'
            + '</div>';
    }

    /** Render a text input row with read-only display + edit button. */
    function _settingText(key, label, placeholder) {
        var current = getSetting(key);
        var display = current || placeholder || "";
        var cls = current ? "settings-row-value" : "settings-row-value muted";
        return '<div class="settings-row" data-key="' + esc(key) + '">'
            + '<span class="settings-row-label">' + esc(label) + '</span>'
            + '<div class="settings-row-field">'
            + '<span class="' + cls + '">' + esc(display) + '</span>'
            + '<input type="text" class="settings-row-input hidden" '
            + 'value="' + esc(current) + '" placeholder="' + esc(placeholder || "") + '">'
            + '</div>'
            + '<button class="settings-row-edit" title="' + esc(_("Edit")) + '">'
            + Icons.pencil() + '</button>'
            + '</div>';
    }

    /** Render a password row (display masked, input type=password). */
    function _settingPassword(key, label, placeholder) {
        var current = getSetting(key);
        var display = current ? maskKey(current) : (placeholder || "");
        var cls = current ? "settings-row-value" : "settings-row-value muted";
        return '<div class="settings-row" data-key="' + esc(key) + '">'
            + '<span class="settings-row-label">' + esc(label) + '</span>'
            + '<div class="settings-row-field">'
            + '<span class="' + cls + '">' + esc(display) + '</span>'
            + '<input type="password" class="settings-row-input hidden" '
            + 'value="' + esc(current) + '" placeholder="' + esc(placeholder || "") + '">'
            + '</div>'
            + '<button class="settings-row-edit" title="' + esc(_("Edit")) + '">'
            + Icons.pencil() + '</button>'
            + '</div>';
    }

    /** Render a toggle switch row. */
    function _settingToggle(key, label) {
        var checked = getSetting(key) !== "false" ? " checked" : "";
        return '<div class="settings-row">'
            + '<span class="settings-row-label">' + esc(label) + '</span>'
            + '<label class="toggle-switch">'
            + '<input type="checkbox" data-key="' + esc(key) + '"' + checked + '>'
            + '<span class="toggle-slider"></span>'
            + '</label>'
            + '</div>';
    }

    /** Render a segmented control row (e.g. Theme: System | Dark | Light). */
    function _settingSegmented(key, label, options, currentVal) {
        var n = options.length;
        var segs = options.map(function (o) {
            var cls = o.value === currentVal ? "settings-seg-btn active" : "settings-seg-btn";
            return '<button class="' + cls + '" data-value="' + esc(o.value) + '">'
                + esc(o.label) + '</button>';
        }).join("");
        // Direct child of card — fills like .lang-grid
        return '<div class="settings-seg-group" data-key="' + esc(key) + '" '
            + 'style="grid-template-columns:repeat(' + n + ',1fr)">' + segs + '</div>';
    }

    /* ═══════════════════════════════════════════════════════════════
       Settings Event Binding
       ═══════════════════════════════════════════════════════════════ */

    /** Bind event listeners for all settings inputs in a container. */
    function _bindSettingsInputs(container) {
        if (!container) return;

        /* Select dropdowns */
        container.querySelectorAll(".settings-row-select").forEach(function (el) {
            el.addEventListener("change", function () {
                applySetting(this.dataset.key, this.value);
                if (this.dataset.key === "img_generation_enabled") {
                    _renderSettingsSection("image");
                }
                if (this.dataset.key === "lang") {
                    renderSettings();
                }
            });
        });

        /* Toggle switches */
        container.querySelectorAll(".toggle-switch input[type=checkbox]").forEach(function (el) {
            el.addEventListener("change", function () {
                var val = this.checked ? "true" : "false";
                applySetting(this.dataset.key, val);
                if (this.dataset.key === "img_generation_enabled") {
                    _renderSettingsSection("image");
                }
            });
        });

        /* Segmented controls */
        container.querySelectorAll(".settings-seg-group").forEach(function (group) {
            group.querySelectorAll(".settings-seg-btn").forEach(function (btn) {
                btn.addEventListener("click", function () {
                    var val = this.dataset.value;
                    group.querySelectorAll(".settings-seg-btn").forEach(function (b) {
                        b.classList.toggle("active", b.dataset.value === val);
                    });
                    if (group.dataset.key === "theme") {
                        ThemeState.set(val);
                        _updateAllThemeButtons();
                    } else if (group.dataset.key === "game_mode") {
                        applySetting("game_mode", val);
                    } else if (group.dataset.key === "portrait_remove_bg") {
                        applySetting("portrait_remove_bg", val);
                    }
                });
            });
        });

        /* Language button grid */
        container.querySelectorAll(".lang-btn:not([disabled])").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var val = this.dataset.lang;
                if (val === "system") {
                    // Resolve browser language
                    var navLang = (navigator.language || "en").split("-")[0];
                    var supported = { "zh": "zh-CN", "en": "en" };
                    val = supported[navLang] || "en";
                }
                container.querySelectorAll(".lang-btn").forEach(function (b) {
                    b.classList.toggle("active", b.dataset.lang === this.dataset.lang);
                }, this);
                applySetting("lang", val);
                GameState.setLang(val);
                renderSettings();
            });
        });

        /* Accent color tiles */
        container.querySelectorAll(".accent-tile").forEach(function (tile) {
            tile.addEventListener("click", function () {
                var val = this.dataset.accent;
                container.querySelectorAll(".accent-tile").forEach(function (t) {
                    t.classList.toggle("active", t.dataset.accent === val);
                });
                applySetting("accent_color", val);
                _applyAccentColor(val);
            });
        });

        /* Text / password edit buttons */
        container.querySelectorAll(".settings-row-edit").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var row = this.closest(".settings-row");
                if (!row) return;
                var key = row.dataset.key;
                var displayEl = row.querySelector(".settings-row-value");
                var inputEl = row.querySelector(".settings-row-input");
                if (!displayEl || !inputEl) return;

                if (!inputEl.classList.contains("hidden")) {
                    /* Save */
                    applySetting(key, inputEl.value);
                    var newVal = getSetting(key);
                    if (key === "api_key" || key === "img_api_key") {
                        displayEl.textContent = maskKey(newVal);
                    } else {
                        displayEl.textContent = newVal || "";
                        displayEl.classList.toggle("muted", !newVal);
                    }
                    inputEl.classList.add("hidden");
                    this.innerHTML = Icons.pencil();
                    /* Remove cancel button if present */
                    var cancelBtn = row.querySelector(".settings-row-cancel");
                    if (cancelBtn) cancelBtn.remove();
                } else {
                    /* Enter edit mode — input overlays value, no layout shift */
                    inputEl.value = getSetting(key);
                    inputEl.classList.remove("hidden");
                    this.innerHTML = Icons.checkmark();

                    /* Add cancel button */
                    var cancelBtn = document.createElement("button");
                    cancelBtn.className = "settings-row-cancel";
                    cancelBtn.innerHTML = Icons.x();
                    cancelBtn.title = _("Cancel");
                    cancelBtn.addEventListener("click", function () {
                        inputEl.classList.add("hidden");
                        btn.innerHTML = Icons.pencil();
                        cancelBtn.remove();
                    });
                    this.parentNode.insertBefore(cancelBtn, this);
                    inputEl.focus();
                }
            });
        });
    }

    /* ═══════════════════════════════════════════════════════════════
       Theme Toggle Button Helpers
       ═══════════════════════════════════════════════════════════════ */

    /** Bind a theme quick-toggle button. */
    function _bindThemeToggle(btn) {
        if (!btn) return;
        _updateThemeButton(btn);
        btn.addEventListener("click", function () {
            ThemeState.toggle();
            _updateAllThemeButtons();
        });
    }

    /** Update a single theme button icon to match current theme. */
    function _updateThemeButton(btn) {
        var cur = ThemeState.current;
        if (cur === "system") {
            btn.innerHTML = Icons.halfMoon();
            btn.title = _("Theme: System");
        } else if (ThemeState.effective === "dark") {
            btn.innerHTML = Icons.moon();
            btn.title = _("Theme: Dark");
        } else {
            btn.innerHTML = Icons.sun();
            btn.title = _("Theme: Light");
        }
    }

    /* ── Accent Color System ─────────────────────────────────────── */

    var ACCENT_PALETTE = {
        green:   { main: "#3fb950", hover: "#4cc964", light: "rgba(63,185,80,0.12)", lightDark: "rgba(63,185,80,0.15)" },
        emerald: { main: "#10b981", hover: "#34d399", light: "rgba(16,185,129,0.12)", lightDark: "rgba(16,185,129,0.15)" },
        blue:    { main: "#3b82f6", hover: "#60a5fa", light: "rgba(59,130,246,0.12)", lightDark: "rgba(59,130,246,0.15)" },
        amber:   { main: "#f59e0b", hover: "#fbbf24", light: "rgba(245,158,11,0.12)", lightDark: "rgba(245,158,11,0.15)" },
        rose:    { main: "#f43f5e", hover: "#fb7185", light: "rgba(244,63,94,0.12)", lightDark: "rgba(244,63,94,0.15)" },
        violet:  { main: "#8b5cf6", hover: "#a78bfa", light: "rgba(139,92,246,0.12)", lightDark: "rgba(139,92,246,0.15)" },
    };

    function _applyAccentColor(id) {
        var p = ACCENT_PALETTE[id] || ACCENT_PALETTE["green"];
        var root = document.documentElement;
        var isDark = ThemeState.effective === "dark";
        root.style.setProperty("--text-accent", p.main);
        root.style.setProperty("--accent-light", isDark ? p.lightDark : p.light);
        // Update shadow to match accent
        root.style.setProperty("--shadow-focus", "0 0 0 2px " + p.main + "59");
        root.style.setProperty("--shadow-glow", "0 0 8px " + p.main + "33");
        root.style.setProperty("--shadow-glow-lg", "0 0 12px " + p.main + "66");
    }

    /** Update ALL theme buttons on the page. */
    function _updateAllThemeButtons() {
        document.querySelectorAll(".theme-toggle-btn").forEach(function (btn) {
            _updateThemeButton(btn);
        });
        /* Update appearance segmented control if visible */
        var seg = document.querySelector('.settings-seg-group[data-key="theme"]');
        if (seg) {
            seg.querySelectorAll(".settings-seg-btn").forEach(function (b) {
                b.classList.toggle("active", b.dataset.value === ThemeState.current);
            });
        }
    }

    /** Bind the update check/apply flow on the settings page. */
    function _bindUpdateCheck() {
        var currentVer = document.getElementById("update-current-ver");
        if (!currentVer) return;

        // Lazy-load current version
        API.get("/api/update/check?force=false").then(function (result) {
            currentVer.textContent = result.app.current;
        }).catch(function () {
            currentVer.textContent = "?";
        });

        var btnCheck = document.getElementById("btn-check-update");
        if (!btnCheck) return;

        btnCheck.addEventListener("click", function () {
            btnCheck.disabled = true;
            btnCheck.textContent = "...";

            API.get("/api/update/check?force=true").then(function (result) {
                btnCheck.disabled = false;
                btnCheck.textContent = _("Check for Updates");
                // Update version display
                if (currentVer) currentVer.textContent = result.app.current;

                if (!result.app.has_update && !result.system_media.has_update) {
                    showToast(_("Up to date"));
                    return;
                }
                _showUpdatePopup(result);
            }).catch(function (err) {
                btnCheck.disabled = false;
                btnCheck.textContent = _("Check for Updates");
                showToast(_("Check failed") + ": " + err.message);
            });
        });
    }

    /** Show a centered modal for update download. */
    function _showUpdatePopup(result) {
        // Remove any existing popup
        var old = document.getElementById("update-popup-overlay");
        if (old) old.remove();

        var layers = [];
        var rows = "";
        if (result.app.has_update) {
            layers.push("app");
            rows += '<div class="update-popup-layer">'
                + '<strong>' + esc(_("App Core")) + '</strong> &nbsp; '
                + esc(result.app.current) + ' → ' + esc(result.app.latest)
                + '</div>';
        }
        if (result.system_media.has_update) {
            layers.push("system_media");
            rows += '<div class="update-popup-layer">'
                + '<strong>' + esc(_("System Media")) + '</strong> &nbsp; '
                + esc(result.system_media.current) + ' → '
                + esc(result.system_media.latest)
                + '</div>';
        }

        var overlay = document.createElement("div");
        overlay.id = "update-popup-overlay";
        overlay.innerHTML =
            '<div class="update-popup">'
            + '<h3 class="update-popup-title">' + esc(_("Update Available"))
            + '</h3>'
            + rows
            + '<div class="update-popup-actions">'
            + '<button class="menu-btn accent" id="btn-update-start">'
            + esc(_("Update")) + '</button>'
            + '<button class="menu-btn" id="btn-update-close">'
            + esc(_("Cancel")) + '</button>'
            + '</div>'
            + '<div id="update-popup-progress" class="hidden"></div>'
            + '</div>';
        document.body.appendChild(overlay);

        var remove = function () { overlay.remove(); };

        overlay.addEventListener("click", function (e) {
            if (e.target === overlay) remove();
        });
        document.getElementById("btn-update-close")
            .addEventListener("click", remove);

        document.getElementById("btn-update-start")
            .addEventListener("click", function () {
                var actions = overlay.querySelector(".update-popup-actions");
                if (actions) actions.classList.add("hidden");
                var prog = document.getElementById("update-popup-progress");
                if (prog) prog.classList.remove("hidden");

                _runUpdateDownload(layers, prog, remove);
            });
    }

    /** Stream the download progress into the popup. */
    function _runUpdateDownload(layers, container, onDone) {
        container.innerHTML =
            '<p class="text-muted">' + esc(_("Downloading...")) + '</p>'
            + '<div id="update-popup-bars"></div>';

        API.post("/api/update/apply", { layers: layers }).then(function (r) {
            SSEClient.open(r.stream_url, {
                progress: function (data) {
                    var bars = document.getElementById("update-popup-bars");
                    if (!bars) return;
                    var pct = data.total
                        ? Math.round(data.received * 100 / data.total) + "%"
                        : "?";
                    var html = "";
                    for (var i = 0; i < layers.length; i++) {
                        var l = layers[i];
                        if (l === data.layer && data.stage === "downloading") {
                            html += '<p>' + esc(l) + ': ' + pct + '</p>';
                        } else if (l === data.layer && data.stage === "extracting") {
                            html += '<p>' + esc(l) + ': '
                                + esc(_("Extracting...")) + '</p>';
                        } else {
                            html += '<p>' + esc(l) + ': ...</p>';
                        }
                    }
                    bars.innerHTML = html;
                },
                done: function () {
                    container.innerHTML =
                        '<p style="color:var(--color-success);text-align:center">'
                        + esc(_("Update ready")) + '</p>'
                        + '<p class="text-muted" style="text-align:center;'
                        + 'margin-top:0.5rem">'
                        + esc(_("Please restart via Storyloom.")) + '</p>'
                        + '<button class="menu-btn" id="btn-update-done-close"'
                        + ' style="margin-top:0.75rem;width:100%">'
                        + esc(_("Close")) + '</button>';
                    document.getElementById("btn-update-done-close")
                        .addEventListener("click", function () {
                            if (onDone) onDone();
                        });
                },
                error: function (data) {
                    container.innerHTML =
                        '<p style="color:var(--color-error);text-align:center">'
                        + esc(_("Update failed")) + ': '
                        + esc(data.error || "") + '</p>'
                        + '<button class="menu-btn" id="btn-update-retry"'
                        + ' style="margin-top:0.5rem;width:100%">'
                        + esc(_("Retry")) + '</button>';
                    document.getElementById("btn-update-retry")
                        .addEventListener("click", function () {
                            _runUpdateDownload(layers, container, onDone);
                        });
                }
            });
        }).catch(function (err) {
            container.innerHTML =
                '<p style="color:var(--color-error);text-align:center">'
                + esc(err.message) + '</p>';
        });
    }

    /* ═══════════════════════════════════════════════════════════════
       View: Game Preview (#game-preview)
       ──────────────────────────────────────────────────────────────
       Transition page between co-creation generate and game start.
       Reads story_config from the save file (GameState.saveFile or
       ``_init.json``) so the save is the canonical source of truth.

       Layout:
         header:  ← Back button (top-left)
         content: story title + setting text (centered)
                  + Begin Adventure button → Round 1 prompt
       ═══════════════════════════════════════════════════════════════ */

    function renderGamePreview() {
        const gameId = GameState.gameId;
        if (!gameId) {
            navigate("menu");
            return;
        }

        // Show loading state while fetching save data
        app.innerHTML = `
            <div class="gp-view">
                <div class="gp-header">
                    <button class="cc-back-btn" id="gp-back"
                            title="${esc(_("Back to Menu"))}">${Icons.arrowLeft()}</button>
                </div>
                <div class="gp-content">
                    <p class="text-muted">${esc(_("Loading..."))}</p>
                </div>
            </div>
        `;

        document.getElementById("gp-back").addEventListener("click", () => {
            GameState.reset();
            navigate("menu");
        });

        // Fetch story_config from the save file AND store game server-side.
        // Uses /start/ (not /load/) to ensure the GameLoop is in the session
        // before "Begin Adventure" → POST /api/game/{id}/start.
        const filename = GameState.saveFile || "_init.json";
        API.post(`/api/saves/${encodeURIComponent(gameId)}/start/${encodeURIComponent(filename)}`)
            .then(data => {
                GameState.gameMode = data.game_mode || "text";  // §7.7
                const config = data.story_config || {};
                _renderPreviewContent(config);
            })
            .catch(err => {
                // Fall back to in-memory story_config if save fetch fails
                const config = GameState.storyConfig;
                if (config) {
                    console.warn("Save fetch failed, using in-memory config:", err);
                    _renderPreviewContent(config);
                } else {
                    app.innerHTML = `
                        <div class="gp-view">
                            <div class="gp-content">
                                <p class="text-error">${esc(err.message)}</p>
                                <button class="menu-btn" style="margin-top:1.5rem" id="gp-back-err">
                                    ${esc(_("Back to Menu"))}
                                </button>
                            </div>
                        </div>
                    `;
                    document.getElementById("gp-back-err").addEventListener("click", () => {
                        GameState.reset();
                        navigate("menu");
                    });
                }
            });
    }

    /** Render the preview content with story title, setting, and
     *  Begin Adventure button that starts the game. */
    function _renderPreviewContent(config) {
        const gameId = GameState.gameId;
        app.innerHTML = `
            <div class="gp-view">
                <div class="gp-header">
                    <button class="cc-back-btn" id="gp-back"
                            title="${esc(_("Back to Menu"))}">${Icons.arrowLeft()}</button>
                    <button class="theme-toggle-btn" id="gp-theme-btn" title="${esc(_("Toggle Theme"))}"></button>
                </div>

                <div class="gp-content">
                    <h1 class="gp-label">${esc(config.title)}</h1>
                    <span class="gp-mode-badge" data-mode="${esc(GameState.gameMode || "text")}">${esc(_(GameState.gameMode === "graph" ? "Graph" : "Text"))}</span>
                    <p class="gp-setting">${esc(config.premise || "")}</p>

                    <button class="gp-start-btn" id="gp-start">
                        ${esc(_("Begin Adventure"))}
                    </button>
                </div>
            </div>
        `;

        document.getElementById("gp-back").addEventListener("click", () => {
            GameState.reset();
            navigate("menu");
        });

        document.getElementById("gp-start").addEventListener("click", () => {
            navigate(`game/${encodeURIComponent(gameId)}`);
        });

        var themeBtn = document.getElementById("gp-theme-btn");
        if (themeBtn) {
            _updateThemeButton(themeBtn);
            themeBtn.addEventListener("click", function () {
                ThemeState.toggle();
                _updateAllThemeButtons();
            });
        }
    }

    /* ═══════════════════════════════════════════════════════════════
       View: Game (#game/{id}) — PLACEHOLDER
       ═══════════════════════════════════════════════════════════════ */

    function renderGame(gameId) {
        if (!gameId) {
            navigate("menu");
            return;
        }

        GameState.gameId = gameId;
        const title = (GameState.storyConfig && GameState.storyConfig.title)
            || gameId;

        /* Close any existing SSE connection before rendering */
        if (typeof SSEClient !== "undefined" && SSEClient.close) {
            SSEClient.close();
        }

        /* Clear the app shell — GameView builds its own DOM */
        app.innerHTML = "";
        var gameMode = GameState.gameMode || "text";  // §7.7
        GameView.render(app, gameId, title, gameMode);
    }

    /* ═══════════════════════════════════════════════════════════════
       View: Save List (#saves) — PLACEHOLDER
       ═══════════════════════════════════════════════════════════════ */

    function renderSaveList() {
        GameState.reset();
        if (typeof SSEClient !== "undefined" && SSEClient.close) {
            SSEClient.close();
        }

        app.innerHTML = `
            <div class="sv-view">
                <div class="sv-header">
                    <button class="cc-back-btn" id="sv-back"
                            title="${esc(_("Back to Menu"))}">${Icons.arrowLeft()}</button>
                    <span class="sv-title">${esc(_("Load Save"))}</span>
                    <button class="theme-toggle-btn" id="sv-theme-btn" title="${esc(_("Toggle Theme"))}"></button>
                </div>
                <div class="sv-list sv-list--expandable" id="sv-game-list">
                    <p class="sv-card-empty">${esc(_("Loading..."))}</p>
                </div>
            </div>
        `;

        document.getElementById("sv-back").addEventListener("click", () => {
            navigate("menu");
        });

        var themeBtn = document.getElementById("sv-theme-btn");
        if (themeBtn) {
            _updateThemeButton(themeBtn);
            themeBtn.addEventListener("click", function () {
                ThemeState.toggle();
                _updateAllThemeButtons();
            });
        }

        API.get("/api/saves/games").then(games => {
            const list = document.getElementById("sv-game-list");
            if (!games.length) {
                list.innerHTML = `<p class="sv-card-empty">${esc(_("No saves found"))}</p>`;
                return;
            }
            list.innerHTML = games.map(g => `
                <div class="sv-card" data-game-id="${esc(g.game_id)}">
                    <div class="sv-card-main">
                        <span class="sv-card-label">${esc(g.title)}</span>
                        <span class="sv-mode-badge" data-mode="${esc(g.mode || "text")}">${esc(_(g.mode === "graph" ? "Graph" : "Text"))}</span>
                        <div class="sv-card-meta">
                            <span>${esc(g.premise || "?")}</span>
                        </div>
                    </div>
                    ${g.last_played_at ? `<span class="sv-card-time">${formatDate(g.last_played_at)}</span>` : ""}
                    <button class="sv-card-trash" title="${esc(_("Delete"))}">${TRASH_ICON}</button>
                </div>
            `).join("");

            list.querySelectorAll(".sv-card").forEach(card => {
                card.addEventListener("click", () => {
                    navigate(`saves/${encodeURIComponent(card.dataset.gameId)}`);
                });
                card.querySelector(".sv-card-trash").addEventListener("click", e => {
                    e.stopPropagation();
                    showConfirmPopup(e.clientX, e.clientY,
                        _("Delete this game?"),
                        () => {
                            API.del(`/api/saves/${encodeURIComponent(card.dataset.gameId)}`)
                                .then(() => {
                                    showToast(_("Game deleted."));
                                    card.remove();
                                    if (!list.querySelectorAll(".sv-card").length) {
                                        list.innerHTML = `<p class="sv-card-empty">${esc(_("No saves found"))}</p>`;
                                    }
                                })
                                .catch(err => showToast(err.message));
                        });
                });
            });
        }).catch(err => {
            document.getElementById("sv-game-list").innerHTML =
                `<p class="text-error">${esc(err.message)}</p>`;
        });
    }

    /* ═══════════════════════════════════════════════════════════════════
       View: Checkpoint List (#saves/{game_id}) — save file browser
       ──────────────────────────────────────────────────────────────
       Each card = one .json save file.  Sorted by saved_at descending.
       Left-click loads the save into the game session and navigates to
       #game-preview; right-click shows a delete confirmation popup.
       ═══════════════════════════════════════════════════════════════════ */

    function renderCheckpointList(gameId) {
        if (typeof SSEClient !== "undefined" && SSEClient.close) {
            SSEClient.close();
        }

        app.innerHTML = `
            <div class="sv-view">
                <div class="sv-header">
                    <button class="cc-back-btn" id="sv-back"
                            title="${esc(_("Back to Menu"))}">${Icons.arrowLeft()}</button>
                    <span class="sv-title" id="sv-cp-title">${esc(_("Loading..."))}</span>
                    <button class="theme-toggle-btn" id="cp-theme-btn" title="${esc(_("Toggle Theme"))}"></button>
                    <button class="sv-restart-btn" id="sv-restart">${esc(_("Restart"))}</button>
                </div>
                <div class="sv-list sv-list--expandable" id="sv-cp-list">
                    <p class="sv-card-empty">${esc(_("Loading..."))}</p>
                </div>
            </div>
        `;

        document.getElementById("sv-back").addEventListener("click", () => {
            navigate("saves");
        });

        document.getElementById("sv-restart").addEventListener("click", async () => {
            try {
                const data = await API.post(
                    `/api/saves/${encodeURIComponent(gameId)}/start/_init.json`
                );
                GameState.gameId = data.game_id;
                GameState.gameMode = data.game_mode || "text";  // §7.7
                GameState.roundCount = data.round_count || 0;
                GameState.currentNode = data.current_node || null;
                GameState.storyConfig = data.story_config || {};
                GameState.saveFile = "_init.json";
                navigate("game-preview");
            } catch (err) {
                showToast(err.message);
            }
        });

        var themeBtn = document.getElementById("cp-theme-btn");
        if (themeBtn) {
            _updateThemeButton(themeBtn);
            themeBtn.addEventListener("click", function () {
                ThemeState.toggle();
                _updateAllThemeButtons();
            });
        }

        /* Fetch saves + game metadata in parallel.
           Saves come back in directory order; re-sort by saved_at
           descending so the newest checkpoint is at the top. */
        Promise.all([
            API.get(`/api/saves/${encodeURIComponent(gameId)}`),
            API.get("/api/saves/games"),
        ]).then(([saves, games]) => {
            const game = games.find(g => g.game_id === gameId);
            document.getElementById("sv-cp-title").textContent =
                game ? game.title : gameId;

            saves.sort((a, b) => (b.saved_at || "").localeCompare(a.saved_at || ""));

            /* Exclude _init.json — it is the initial save, not a checkpoint. */
            const checkpoints = saves.filter(s =>
                s.filename !== "_init.json" && s.filename !== "_asset_roster.json"
            );

            const list = document.getElementById("sv-cp-list");
            if (!checkpoints.length) {
                list.innerHTML = `<p class="sv-card-empty">${esc(_("No saves in this game."))}</p>`;
                return;
            }

            list.innerHTML = checkpoints.map(s => {
                const label = s.checkpoint_title || s.filename;
                const summary = s.checkpoint_summary || "";
                return `
                    <div class="sv-card" data-filename="${esc(s.filename)}">
                        <div class="sv-card-main">
                            <span class="sv-card-label">${esc(label)}</span>
                            ${summary ? `<div class="sv-card-meta"><span>${esc(summary)}</span></div>` : ""}
                        </div>
                        ${s.saved_at ? `<span class="sv-card-time">${formatDate(s.saved_at)}</span>` : ""}
                        <button class="sv-card-trash" title="${esc(_("Delete"))}">${TRASH_ICON}</button>
                    </div>
                `;
            }).join("");

            list.querySelectorAll(".sv-card").forEach(card => {
                card.addEventListener("click", async () => {
                    const filename = card.dataset.filename;
                    try {
                        const data = await API.post(
                            `/api/saves/${encodeURIComponent(gameId)}/start/${encodeURIComponent(filename)}`
                        );
                        GameState.gameId = data.game_id;
                        GameState.gameMode = data.game_mode || "text";  // §7.7
                        GameState.roundCount = data.round_count || 0;
                        GameState.currentNode = data.current_node || null;
                        GameState.storyConfig = data.story_config || {};
                        GameState.saveFile = filename;
                        navigate("game-preview");
                    } catch (err) {
                        showToast(err.message);
                    }
                });
                card.querySelector(".sv-card-trash").addEventListener("click", e => {
                    e.stopPropagation();
                    showConfirmPopup(e.clientX, e.clientY,
                        _("Delete this save?"),
                        () => {
                            API.del(`/api/saves/${encodeURIComponent(gameId)}/${encodeURIComponent(card.dataset.filename)}`)
                                .then(() => {
                                    showToast(_("Save deleted."));
                                    card.remove();
                                    if (!list.querySelectorAll(".sv-card").length) {
                                        list.innerHTML = `<p class="sv-card-empty">${esc(_("No saves in this game."))}</p>`;
                                    }
                                })
                                .catch(err => showToast(err.message));
                        });
                });
            });
        }).catch(err => {
            document.getElementById("sv-cp-list").innerHTML =
                `<p class="text-error">${esc(err.message)}</p>`;
        });
    }

    /* ═══════════════════════════════════════════════════════════════════
       View: Adventure Log (#adventure-log/{game_id})
       ──────────────────────────────────────────────────────────────
       Post-ending scrollable text page showing the generated
       adventure log.  Delegates to AdventureLogView.render().

       Layout:
         header:  ← Back button (top-left) + story title + [Export] (disabled)
         content: scrollable log text (no border, white)
       ═══════════════════════════════════════════════════════════════ */

    function renderAdventureLog(gameId) {
        GameState.gameId = gameId;

        /* Get story title from GameState (set during game session).
           Falls back to gameId only when GameState has been reset —
           the label is present in normal flow (coming from game.js
           end modal, where GameState.storyConfig is still populated). */
        const title = (GameState.storyConfig && GameState.storyConfig.title)
            || gameId;

        app.innerHTML = "";
        /* Register cleanup so navigating away cancels any pending poll
           timer (not just the back button).  _cleanup is idempotent. */
        _currentViewCleanup = function () {
            if (typeof AdventureLogView !== "undefined" && AdventureLogView.cleanup) {
                AdventureLogView.cleanup();
            }
        };
        AdventureLogView.render(app, gameId, title);
    }

    /* ═══════════════════════════════════════════════════════════════════
       View: Asset Manager (#assets)
       ──────────────────────────────────────────────────────────────
       Left sidebar (type nav + "Auto Clean") + right card list.
       Cards show name, description, use_count.  Click → image viewer.
       Delegates to AssetManagerView.render() (assets.js).
       ═══════════════════════════════════════════════════════════════════ */

    function renderAssetManager() {
        AssetManagerView.render(app);
    }

    /* ── Confirm Popup (delete confirmation) ───────────────────────── */

    /** Show a positioned confirmation popup for delete actions.
     *  @param {number} x - clientX of the triggering click
     *  @param {number} y - clientY of the triggering click
     *  @param {string} message - main question text (already translated)
     *  @param {Function} onConfirm - called when user clicks "Yes"    */
    function showConfirmPopup(x, y, message, onConfirm) {
        const existing = document.querySelector(".ctx-menu");
        if (existing) existing.remove();

        const menu = document.createElement("div");
        menu.className = "ctx-menu";
        menu.innerHTML = `
            <p class="ctx-menu-text">${esc(message)}</p>
            <p class="ctx-menu-warn">${esc(_("This cannot be undone."))}</p>
            <div class="ctx-menu-actions">
                <button class="ctx-menu-btn" id="ctx-no">${esc(_("No"))}</button>
                <button class="ctx-menu-btn danger" id="ctx-yes">${esc(_("Yes"))}</button>
            </div>
        `;
        /* Keep within viewport bounds */
        menu.style.left = Math.min(x, window.innerWidth - 240) + "px";
        menu.style.top = Math.min(y, window.innerHeight - 140) + "px";
        document.body.appendChild(menu);

        const close = () => menu.remove();
        menu.querySelector("#ctx-no").addEventListener("click", close);
        menu.querySelector("#ctx-yes").addEventListener("click", () => {
            close();
            onConfirm();
        });
        /* Click outside to dismiss */
        setTimeout(() => {
            document.addEventListener("click", function handler(e) {
                if (!menu.contains(e.target)) {
                    close();
                    document.removeEventListener("click", handler);
                }
            });
        }, 0);
    }

    /** Format an ISO 8601 string for display (e.g. "2026-07-19 14:30"). */
    function formatDate(iso) {
        if (!iso) return "";
        const d = new Date(iso);
        if (isNaN(d.getTime())) return iso;
        const pad = n => String(n).padStart(2, "0");
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }

    // ── Kick off ──────────────────────────────────────────────────

    init();
})();

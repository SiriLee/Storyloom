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
       View: Settings (#settings) — full-page, same pattern as co-create
       ──────────────────────────────────────────────────────────────
       Layout:
         header:  ← Back button (top-left) + "Settings" title
         content: scrollable form area with all settings rows

       Data-driven: reads SETTINGS array from state.js — same data
       source as the old overlay panel.

       Authority:
         CLAUDE.local.md §3.2 (event flow consumption)
         Co-create view pattern (full-height routed view)
       ═══════════════════════════════════════════════════════════════ */

    function renderSettings() {
        GameState.reset();
        if (typeof SSEClient !== "undefined" && SSEClient.close) {
            SSEClient.close();
        }

        const X_SVG = '<svg viewBox="0 0 24 24" width="16" height="16" '
            + 'fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 '
            + '6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 '
            + '17.59 19 19 17.59 13.41 12 19 6.41z"/></svg>';

        const rows = SETTINGS.reduce((acc, def, i) => {
            const prevGroup = i > 0 ? SETTINGS[i - 1].group : undefined;
            const thisGroup = def.group;
            const current = getSetting(def.key);
            const label = esc(_(def.label));

            /* ── Group boundary: close previous group ── */
            if (prevGroup && prevGroup !== thisGroup) {
                acc.push("</div>");
            }

            /* ── Group boundary: open new group ── */
            if (thisGroup && thisGroup !== prevGroup) {
                const enabled = getSetting("img_generation_enabled") !== "false";
                const collapsed = enabled ? "" : " collapsed";
                acc.push(`<div class="setting-group${collapsed}" data-group="${thisGroup}">`);
            }

            /* ── Toggle (checkbox slider) ── */
            if (def.type === "toggle") {
                const checked = current !== "false" ? " checked" : "";
                acc.push(`
                    <div class="setting-row">
                        <span class="setting-label">${label}</span>
                        <label class="toggle-switch">
                            <input type="checkbox" id="setting-${def.key}"${checked}>
                            <span class="toggle-slider"></span>
                        </label>
                    </div>`);
                return acc;
            }

            /* ── Select dropdown ── */
            if (def.type === "select") {
                acc.push(`
                    <div class="setting-row">
                        <span class="setting-label">${label}</span>
                        <select id="setting-${def.key}">${def.options.map(opt =>
                            `<option value="${esc(opt.value)}" ${current === opt.value ? "selected" : ""}>${esc(_(opt.label))}</option>`
                        ).join("")}</select>
                    </div>`);
                return acc;
            }

            /* ── text / password: display + edit button (✎ → ✓ / ✕) ── */
            const isKeyField = def.key === "api_key" || def.key === "img_api_key";
            const displayVal = isKeyField
                ? maskKey(current)
                : (current || esc(def.placeholder || ""));
            const displayCls = (!current && def.key !== "api_key") ? "setting-val muted" : "setting-val";
            acc.push(`
                <div class="setting-row" id="row-${def.key}">
                    <span class="setting-label">${label}</span>
                    <span class="${displayCls}" id="display-${def.key}">${esc(displayVal)}</span>
                    <input type="${def.type === "password" ? "password" : "text"}"
                           id="input-${def.key}" value="${esc(current || "")}"
                           placeholder="${esc(def.placeholder || "")}"
                           class="setting-input hidden">
                    <button class="setting-edit-btn" id="edit-${def.key}"
                            title="${esc(_("Edit"))}">${Icons.pencil()}</button>
                </div>`);

            /* ── Close trailing group ── */
            if (i === SETTINGS.length - 1 && thisGroup) {
                acc.push("</div>");
            }

            return acc;
        }, []).join("");

        app.innerHTML = `
            <div class="settings-view">
                <div class="settings-header">
                    <button class="cc-back-btn" id="settings-back"
                            title="${esc(_("Back to Menu"))}">${Icons.arrowLeft()}</button>
                    <span class="settings-title">${esc(_("Settings"))}</span>
                </div>

                <div class="settings-content">
                    <div class="settings-form">
                        ${rows}
                    </div>
                    <!-- Updates — inline row matching other settings -->
                    <div class="settings-form" style="margin-top:2rem; padding-top:1.5rem; border-top:1px solid var(--border-color)">
                        <div class="setting-row" id="update-row">
                            <span class="setting-label">${esc(_("Current Version"))}</span>
                            <span class="setting-val" id="update-current-ver">...</span>
                            <button class="setting-edit-btn" id="btn-check-update"
                                    style="margin-left:auto">${esc(_("Check for Updates"))}</button>
                        </div>
                    </div>
                    <!-- Credits (moved from main menu) -->
                    <div class="settings-form" style="margin-top:2rem; padding-top:1.5rem; border-top:1px solid var(--border-color)">
                        <h3 style="font-family:var(--font-mono); color:var(--text-accent); margin-bottom:1rem; text-align:center">
                            ${esc(_("Credits"))}
                        </h3>
                        <div class="credits-section" style="text-align:center">
                            <h3>${esc(_("Developers"))}</h3>
                            <p class="credits-name">${CREDITS.developers.map(function(p) { return '<a class="credits-link" href="' + esc(p.url) + '" target="_blank" rel="noopener">' + esc(p.name) + '</a>'; }).join(" ")}</p>
                        </div>
                        <div class="credits-section" style="text-align:center">
                            <h3>${esc(_("Contributors"))}</h3>
                            <p class="credits-name">${CREDITS.contributors.map(function(p) { return '<a class="credits-link" href="' + esc(p.url) + '" target="_blank" rel="noopener">' + esc(p.name) + '</a>'; }).join(" ")}</p>
                        </div>
                    </div>
                </div>
            </div>
        `;

        /* ── Bind events ────────────────────────────────────────── */

        document.getElementById("settings-back").addEventListener("click", () => {
            navigate("menu");
        });

        SETTINGS.forEach(def => {
            /* ── Toggle: collapse / expand group ── */
            if (def.type === "toggle") {
                const el = document.getElementById(`setting-${def.key}`);
                if (!el) return;
                el.addEventListener("change", () => {
                    const value = el.checked ? "true" : "false";
                    /* Toggle group visibility */
                    const group = document.querySelector(
                        `.setting-group[data-group="${def.group || "image"}"]`
                    );
                    if (group) {
                        if (el.checked) {
                            group.classList.remove("collapsed");
                        } else {
                            group.classList.add("collapsed");
                        }
                    }
                    applySetting(def.key, value);
                });
                return;
            }

            if (def.type === "select") {
                const el = document.getElementById(`setting-${def.key}`);
                if (!el) return;
                el.addEventListener("change", async () => {
                    /* ── Background Removal: verify model is available ── */
                    if (def.key === "portrait_remove_bg" && el.value !== "never") {
                        try {
                            const status = await API.get("/api/config/bg-removal-status");
                            if (!status.available) {
                                /* Model not found — revert. */
                                el.value = getSetting("portrait_remove_bg") || "never";
                                return;
                            }
                        } catch (_) {
                            /* API unreachable — apply anyway (best-effort). */
                        }
                    }
                    const needsRerender = applySetting(def.key, el.value);
                    if (needsRerender) {
                        renderSettings();
                    }
                });
                return;
            }

            /* text / password: ✎ → ✓+✕ (lazy, same pattern as ✓) */
            const displayEl = document.getElementById(`display-${def.key}`);
            const inputEl   = document.getElementById(`input-${def.key}`);
            const editBtn   = document.getElementById(`edit-${def.key}`);
            if (!editBtn) return;

            let _preEditVal = "";
            let _xBtn = null;

            function _exitEdit() {
                inputEl.classList.add("hidden");
                displayEl.classList.remove("hidden");
                if (_xBtn) { _xBtn.remove(); _xBtn = null; }
                editBtn.innerHTML = Icons.pencil();
            }

            editBtn.addEventListener("click", () => {
                if (!inputEl.classList.contains("hidden")) {
                    /* Save */
                    applySetting(def.key, inputEl.value);
                    const newVal = getSetting(def.key);
                    if (def.key === "api_key" || def.key === "img_api_key") {
                        displayEl.textContent = maskKey(newVal);
                    } else {
                        displayEl.textContent = newVal || def.placeholder || "";
                        displayEl.classList.toggle("muted", !newVal);
                    }
                    _exitEdit();
                } else {
                    /* Enter edit — insert ✕ before ✓, same lazy pattern as ✓ */
                    _preEditVal = getSetting(def.key);
                    inputEl.value = _preEditVal;
                    inputEl.classList.remove("hidden");
                    displayEl.classList.add("hidden");
                    _xBtn = document.createElement("button");
                    _xBtn.className = "setting-edit-btn";
                    _xBtn.style.marginRight = "-0.8rem";
                    _xBtn.innerHTML = X_SVG;
                    _xBtn.title = _("Cancel");
                    _xBtn.addEventListener("click", () => {
                        inputEl.value = _preEditVal;
                        _exitEdit();
                    });
                    editBtn.parentNode.insertBefore(_xBtn, editBtn);
                    editBtn.innerHTML = Icons.checkmark();
                    inputEl.focus();
                }
            });
        });

        /* ── Update check button ─────────────────────────────────── */

        _bindUpdateCheck();
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
                </div>
                <div class="sv-list sv-list--expandable" id="sv-game-list">
                    <p class="sv-card-empty">${esc(_("Loading..."))}</p>
                </div>
            </div>
        `;

        document.getElementById("sv-back").addEventListener("click", () => {
            navigate("menu");
        });

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

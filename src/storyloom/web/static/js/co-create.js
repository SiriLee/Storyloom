/* ═══════════════════════════════════════════════════════════════════
   co-create.js — Co-Creation chat UI module

   Lifecycle:
     1. CoCreateView.render(container) — builds DOM, calls /start,
        shows the LLM's opening question.
     2. User chats with LLM — multi-turn Q&A.
     3. User clicks ← → abort → #menu.

   Phase gating:
     - Back button (←) and Start button only active during "chatting".
     - All other phases (loading, done) → buttons are silent.

   Error handling (mirrors dev_cli/game_driver.py run_co_create):
     - CoCreateError → show error + Retry button → call retry endpoint
     - RuntimeError / ValueError → fatal, show error with Back to Menu

   Authority:
     dev_cli/game_driver.py (co-creation driver — authoritative reference)
     src/storyloom/core/co_create.py (CoCreateFlow API)
     CLAUDE.local.md §3.2 (API consumption)
   ═══════════════════════════════════════════════════════════════════ */

const CoCreateView = (function () {
    /* ── Internal state ──────────────────────────────────────────── */
    let _container = null;
    let _phase = "loading";   // loading | chatting | done

    /* ── DOM helpers ─────────────────────────────────────────────── */

    /** Shortcut for _container.querySelector(sel).
     *  sel MUST be a valid CSS selector: "#id" for IDs, ".class" for classes. */
    function $(sel) { return _container.querySelector(sel); }

    function esc(s) {
        const d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    /* ── Public API ──────────────────────────────────────────────── */

    /** Render the co-creation chat view into *container*.
     *  Kicks off POST /api/co-create/start and shows the opening prompt. */
    async function render(container) {
        _container = container;
        _phase = "loading";

        var currentMode = getSetting("game_mode") || "text";
        var modeLabel = currentMode === "graph" ? _("Graph") : _("Text");

        _container.innerHTML = `
            <div class="co-create-view">
                <!-- Header: ← back | title | [spacer] | theme | mode | Start -->
                <div class="cc-header">
                    <button class="cc-back-btn" id="cc-back"
                            title="${esc(_("Back to Menu"))}" disabled>${Icons.arrowLeft()}</button>
                    <span class="cc-title">${esc(_("Co-Create"))}</span>
                    <span class="cc-spacer"></span>
                    <button class="theme-toggle-btn" id="cc-theme-btn" title="${esc(_("Toggle Theme"))}"></button>
                    <button class="cc-mode-btn" id="cc-mode-btn" title="${esc(_("Switch Mode"))}">${esc(modeLabel)}</button>
                    <button class="cc-start-btn" id="cc-start" disabled>${esc(_("Start"))}</button>
                </div>

                <!-- Chat panel -->
                <div class="cc-chat-panel">
                    <div class="cc-messages" id="cc-messages"></div>
                    <div class="cc-input-bar" id="cc-input-bar">
                        <div class="cc-input-wrap">
                            <textarea class="cc-input" id="cc-input"
                                      placeholder="${esc(_("Type your story idea..."))}"
                                      rows="1"></textarea>
                            <button class="cc-send-btn" id="cc-send"
                                    title="${esc(_("Send"))}" disabled>${Icons.arrowUp()}</button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        _bindEvents();

        // Call /start — get opening prompt
        _showTyping();
        try {
            const data = await API.post("/api/co-create/start");
            _hideTyping();
            _clearMessages();
            _addMessage("assistant", data.prompt);
            _phase = "chatting";
            _setInputEnabled(true);
            _updatePlaceholder();
            _focusInput();
        } catch (err) {
            _hideTyping();
            _clearMessages();
            _showFatalError(err.message);
        }
    }

    /* ── Event bindings ──────────────────────────────────────────── */

    function _bindEvents() {
        $("#cc-send").addEventListener("click", _handleSend);

        // Enter to send, Shift+Enter / Ctrl+Enter / Cmd+Enter for newline
        $("#cc-input").addEventListener("keydown", (e) => {
            if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey) {
                e.preventDefault();
                _handleSend();
            }
        });

        // Auto-resize textarea
        $("#cc-input").addEventListener("input", () => {
            _autoResize($("#cc-input"));
        });

        $("#cc-back").addEventListener("click", _handleBack);
        $("#cc-start").addEventListener("click", _handleStart);

        var themeBtn = document.getElementById("cc-theme-btn");
        if (themeBtn) {
            window._updateThemeButton(themeBtn);
            themeBtn.addEventListener("click", function () {
                ThemeState.toggle();
                saveConfig();
                window._updateAllThemeButtons();
            });
        }

        /* Mode toggle button */
        var modeBtn = document.getElementById("cc-mode-btn");
        if (modeBtn) {
            modeBtn.addEventListener("click", function () {
                var current = getSetting("game_mode") || "text";
                var next = current === "graph" ? "text" : "graph";
                applySetting("game_mode", next);
                modeBtn.textContent = next === "graph" ? _("Graph") : _("Text");
            });
        }
    }

    /* ── Back button — follows same gating as Start (via _setInputEnabled) ── */

    async function _handleBack() {
        if (_phase !== "chatting") return;

        // Immediate abort, no confirmation (matches dev_cli /quit)
        try { await API.post("/api/co-create/abort"); } catch (_) { /* ok */ }
        _phase = "done";
        Router.navigate("menu");
    }

    /* ── Start button — Phase 1: generate story setup ────────────── */

    /* ── Generate task list (§7.8c SSE) ─────────────────────────────── */
    /* Replaces the old sync POST + static transition.  Renders a task
       list that lights up as each JSON section is completed by the LLM. */

    /** Task list items — ordered to match ``_GENERATE_SECTION_ORDER``. */
    var _GEN_TASKS = [
        { key: "_thinking",    label: "Thinking",        icon: Icons.cpu },
        { key: "story_config", label: "Story Setting",   icon: Icons.book },
        { key: "characters",   label: "Characters",      icon: Icons.users },
        { key: "locations",    label: "Scenes",          icon: Icons.image },
        { key: "variables",    label: "Variables",       icon: Icons.gear },
        { key: "outline",      label: "Story Structure", icon: Icons.branch },
    ];

    /** Mark the "Thinking" task as active immediately on render. */
    function _startThinkingTask(tasks) {
        var t = tasks["_thinking"];
        if (t) t.className = 'gen-task active';
    }

    /** Render the task list view.  Returns {tasks, progressEl}. */
    function _renderGenerateView() {
        var itemsHtml = '';
        for (var i = 0; i < _GEN_TASKS.length; i++) {
            var t = _GEN_TASKS[i];
            var delay = (i * 0.06).toFixed(2);
            var iconSvg = t.icon ? t.icon() : '';
            itemsHtml +=
                '<div class="gen-task pending" data-gen-section="' + esc(t.key) + '"' +
                '     style="animation-delay:' + delay + 's">' +
                    '<span class="gen-task-icon">' + iconSvg + '</span>' +
                    '<span class="gen-task-dot"></span>' +
                    '<span class="gen-task-label">' + esc(_(t.label)) + '</span>' +
                    '<span class="gen-task-status">' + Icons.checkmark() + '</span>' +
                '</div>';
        }

        _container.innerHTML =
            '<div class="gen-view">' +
                '<div class="gen-header">' +
                    '<button class="cc-back-btn" id="gen-back-btn" disabled title="' + esc(_("Back to Menu")) + '">' + Icons.arrowLeft() + '</button>' +
                    '<span class="gen-title">' + esc(_("Creating Your Story")) + '</span>' +
                    '<span class="cc-spacer"></span>' +
                    '<button class="theme-toggle-btn" id="gen-theme-btn" title="' + esc(_("Toggle Theme")) + '"></button>' +
                '</div>' +
                '<div class="gen-tasks">' +
                    itemsHtml +
                '</div>' +
                '<div class="gen-progress" id="gen-progress">' +
                    '<span>' + esc(_("Thinking")) + '</span>' +
                    '<span class="cc-dots"><span>.</span><span>.</span><span>.</span></span>' +
                '</div>' +
            '</div>';

        var tasks = {};
        var allTasks = _container.querySelectorAll('.gen-task');
        allTasks.forEach(function (el) {
            tasks[el.getAttribute('data-gen-section')] = el;
        });
        // Thinking task starts active immediately (TTFT is the longest phase)
        _startThinkingTask(tasks);

        // Theme toggle button
        var genThemeBtn = document.getElementById("gen-theme-btn");
        if (genThemeBtn) {
            window._updateThemeButton(genThemeBtn);
            genThemeBtn.addEventListener("click", function () {
                ThemeState.toggle();
                saveConfig();
                window._updateAllThemeButtons();
            });
        }

        return { tasks: tasks, progressEl: document.getElementById('gen-progress') };
    }

    function _updateGenProgress(el, text, showDots) {
        if (showDots === undefined) showDots = true;
        el.innerHTML =
            '<span>' + esc(text) + '</span>' +
            (showDots ? '<span class="cc-dots"><span>.</span><span>.</span><span>.</span></span>' : '');
    }

    /** Handle one SSE event — light up tasks as they arrive.
     *  When a section arrives: preceding items get checkmarks,
     *  the current item lights up (active), later items stay pending.
     *  The "_thinking" task completes when the first real section arrives. */
    function _handleGenEvent(data, tasks, progressEl) {
        if (data.type === 'section_complete') {
            var task = tasks[data.section];
            if (!task) return;

            // First real section → thinking is done
            var thinkingTask = tasks["_thinking"];
            if (thinkingTask && thinkingTask.classList.contains('active')) {
                thinkingTask.className = 'gen-task complete';
            }

            var found = false;
            for (var i = 0; i < _GEN_TASKS.length; i++) {
                var t = tasks[_GEN_TASKS[i].key];
                if (!t) continue;
                if (_GEN_TASKS[i].key === data.section) {
                    // Current section: accent color (being generated)
                    t.className = 'gen-task active';
                    found = true;
                } else if (!found) {
                    // Preceding sections: green checkmark (done)
                    t.className = 'gen-task complete';
                }
                // Later sections stay pending (no change)
            }

            var label = '';
            for (var j = 0; j < _GEN_TASKS.length; j++) {
                if (_GEN_TASKS[j].key === data.section) {
                    label = _(_GEN_TASKS[j].label);
                    break;
                }
            }
            _updateGenProgress(progressEl, _("Building") + ' ' + (label || data.section));
        } else if (data.type === 'generate_done') {
            // All sections done — mark everything complete
            for (var i = 0; i < _GEN_TASKS.length; i++) {
                var t = tasks[_GEN_TASKS[i].key];
                if (t) t.className = 'gen-task complete';
            }
            _updateGenProgress(progressEl, _("Done"), false);
        }
    }

    /** Connect to the SSE stream and drive the task list. */
    async function _connectGenerateStream(tasks, progressEl) {
        var url = '/api/co-create/generate/stream';

        var response;
        try { response = await fetch(url); } catch (err) { return { event: null, error: String(err) }; }

        if (!response.ok) {
            var detail = '';
            try { var ed = await response.json(); detail = ed.detail || ''; } catch (_) {}
            return { event: null, error: detail || ('HTTP ' + response.status) };
        }

        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buf = '';
        var doneEvent = null;

        try {
            while (true) {
                var chunk = await reader.read();
                if (chunk.done) break;
                buf += decoder.decode(chunk.value, { stream: true });
                var parts = buf.split('\n\n');
                buf = parts.pop() || '';
                parts.forEach(function (frame) {
                    if (!frame.trim()) return;
                    var etype = '';
                    var lines = frame.split('\n');
                    lines.forEach(function (line) {
                        if (line.startsWith('event: ')) etype = line.slice(7).trim();
                        else if (line.startsWith('data: ')) {
                            try {
                                var d = JSON.parse(line.slice(6));
                                _handleGenEvent(d, tasks, progressEl);
                                if (etype === 'generate_done' || d.type === 'generate_done') doneEvent = d;
                            } catch (_) {}
                        }
                    });
                });
            }
        } finally { try { reader.cancel(); } catch (_) {} }

        return { event: doneEvent, error: null };
    }

    function _renderGenError(message, retryHandler) {
        _container.innerHTML =
            '<div class="gen-view">' +
                '<div class="cc-transition-text" style="font-size:1.4rem; color:var(--text-error); margin-bottom:1.5rem;">' +
                    esc(message) +
                '</div>' +
                '<div style="display:flex; gap:0.8rem; justify-content:center;">' +
                    '<button class="menu-btn" id="gen-retry">' + esc(_("Retry")) + '</button>' +
                    '<button class="menu-btn" id="gen-back">' + esc(_("Back to Menu")) + '</button>' +
                '</div>' +
            '</div>';
        document.getElementById('gen-retry').addEventListener('click', retryHandler);
        document.getElementById('gen-back').addEventListener('click', function () { Router.navigate('menu'); });
    }

    /* ── Prebuild phase (§7.8c SSE) ────────────────────────────────── */
    /* Replaces the old sync POST + static transition screen.  Renders a
       card grid from story_config, then streams per-entity status updates
       via SSE until prebuild_complete. */

    /** Render the prebuild card grid from entity arrays.
     *  Returns { cards: {name → DOM element}, progressEl } so the SSE
     *  handler can update individual cards in O(1). */
    function _renderPrebuildView(characters, locations) {
        characters = characters || [];
        locations = locations || [];

        var charCardsHtml = '';
        characters.forEach(function (ch, i) {
            charCardsHtml += _buildCardHtml(ch.name, 'char_portrait', i);
        });

        var bgCardsHtml = '';
        locations.forEach(function (loc, i) {
            bgCardsHtml += _buildCardHtml(loc.name, 'background', i);
        });

        _container.innerHTML =
            '<div class="pb-view">' +
                '<div class="pb-header">' +
                    '<button class="cc-back-btn" id="pb-back-btn" disabled title="' + esc(_("Back to Menu")) + '">' + Icons.arrowLeft() + '</button>' +
                    '<span class="pb-title">' + esc(_("Building Your World")) + '</span>' +
                    '<span class="cc-spacer"></span>' +
                    '<button class="theme-toggle-btn" id="pb-theme-btn" title="' + esc(_("Toggle Theme")) + '"></button>' +
                '</div>' +
                '<div class="pb-grid">' +
                    '<div>' +
                        '<div class="pb-column-label">' + esc(_("Characters")) + '</div>' +
                        '<div id="pb-char-cards">' + charCardsHtml + '</div>' +
                    '</div>' +
                    '<div>' +
                        '<div class="pb-column-label">' + esc(_("Scenes")) + '</div>' +
                        '<div id="pb-bg-cards">' + bgCardsHtml + '</div>' +
                    '</div>' +
                '</div>' +
                '<div class="pb-progress" id="pb-progress">' +
                    esc(_("Connecting...")) +
                '</div>' +
            '</div>';

        /* Build card lookup map — each card is already in the DOM,
           we just grab references by entity name. */
        var cards = {};
        var allCards = _container.querySelectorAll('.pb-card');
        allCards.forEach(function (el) {
            cards[el.getAttribute('data-entity')] = el;
        });

        var progressEl = document.getElementById('pb-progress');

        // Theme toggle button
        var pbThemeBtn = document.getElementById("pb-theme-btn");
        if (pbThemeBtn) {
            window._updateThemeButton(pbThemeBtn);
            pbThemeBtn.addEventListener("click", function () {
                ThemeState.toggle();
                saveConfig();
                window._updateAllThemeButtons();
            });
        }

        return { cards: cards, progressEl: progressEl };
    }

    /** Build inner HTML for one entity card.
     *  Uses single-quote delimiters for data-entity to avoid breakage
     *  if the entity name contains double-quote characters. */
    function _buildCardHtml(name, assetType, index) {
        var escName = esc(name);
        var delay = (index * 0.04).toFixed(2);
        return (
            "<div class='pb-card waiting' data-entity='" + escName + "'" +
            "     data-asset-type='" + assetType + "'" +
            "     style='animation-delay:" + delay + "s'>" +
                "<div class='pb-card-name'>" + escName + "</div>" +
                "<div class='pb-card-status'>" +
                    "<span class='pb-status-dot'></span>" +
                    "<span class='pb-status-text'></span>" +
                "</div>" +
            "</div>"
        );
    }

    /** Set a card's visual state + status text. */
    function _setCardState(card, state, text) {
        card.className = 'pb-card ' + state;
        var textEl = card.querySelector('.pb-status-text');
        if (textEl) textEl.textContent = text;
    }

    /** Update the bottom progress line. */
    function _updatePrebuildProgress(el, text, showDots) {
        if (showDots === undefined) showDots = true;
        /* Strip trailing dots from static text — animated cc-dots provide the ellipsis. */
        if (showDots) {
            text = text.replace(/\.{2,}$/, '');
        }
        el.innerHTML =
            '<span>' + esc(text) + '</span>' +
            (showDots ? '<span class="cc-dots"><span>.</span><span>.</span><span>.</span></span>' : '');
    }

    /** Handle one SSE event — dispatch by phase. */
    function _handlePrebuildEvent(data, cards, progressEl) {
        var phase = data.phase || '';

        if (phase === 'parse') {
            /* All entities parsed — cards transition from "waiting" to "selecting". */
            Object.values(cards).forEach(function (c) {
                _setCardState(c, 'selecting', _("matching..."));
            });
            _updatePrebuildProgress(progressEl, _("Matching entities to library assets..."));
            return;
        }

        if (phase === 'selection') {
            /* Aggregate counts only — per-entity results arrive in "seeded". */
            var atLabel = data.asset_type === 'char_portrait' ? _("Characters") : _("Scenes");
            _updatePrebuildProgress(progressEl,
                atLabel + ': ' + data.matched + ' ' + _("matched") + ', ' +
                data.to_generate + ' ' + _("to generate"));
            return;
        }

        if (phase === 'seeded') {
            /* Per-entity selection results — flip all cards to final pre-generation state. */
            var entities = data.entities || [];
            var toGenerate = 0;
            entities.forEach(function (e) {
                var card = cards[e.name];
                if (!card) return;
                if (e.action === 'matched') {
                    _setCardState(card, 'matched', e.asset_id || _("matched"));
                } else {
                    _setCardState(card, 'generating', _("generating..."));
                    toGenerate++;
                }
            });
            if (toGenerate > 0) {
                _updatePrebuildProgress(progressEl,
                    _("Generating") + ' ' + toGenerate + ' ' + _("images..."));
            } else {
                _updatePrebuildProgress(progressEl,
                    _("All assets ready"), false);
            }
            return;
        }

        if (phase === 'generate') {
            /* Single entity generation completed. */
            var card = cards[data.entity];
            if (!card) return;
            if (data.status === 'generated') {
                _setCardState(card, 'generated', _("generated"));
            } else {
                _setCardState(card, 'failed', _("failed"));
            }
            _updatePrebuildProgress(progressEl,
                _("Generating images...") + ' ' + data.completed + '/' + data.total + ' ' + _("complete"));
            return;
        }

        if (phase === 'fallback') {
            /* Force-select fallback result for a failed generation. */
            var card = cards[data.entity];
            if (!card) return;
            if (data.status === 'force_selected') {
                _setCardState(card, 'matched', data.asset_id || _("fallback selected"));
            } else {
                _setCardState(card, 'failed', _("fallback failed"));
            }
            return;
        }
    }

    /** Connect to the prebuild SSE stream and drive the card UI.
     *  Returns ``{event, error}`` — *event* is the ``prebuild_complete``
     *  data on success; *error* is a string on connection / HTTP failure. */
    async function _connectPrebuildStream(gameId, cards, progressEl) {
        var url = '/api/co-create/prebuild/' + encodeURIComponent(gameId) + '/stream';
        var completeEvent = null;

        var response;
        try {
            response = await fetch(url);
        } catch (err) {
            return { event: null, error: String(err) };
        }

        if (!response.ok) {
            var detail = '';
            try {
                var errData = await response.json();
                detail = errData.detail || '';
            } catch (_) { /* body may not be JSON */ }
            return { event: null, error: detail || ('HTTP ' + response.status) };
        }

        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';

        try {
            while (true) {
                var chunk = await reader.read();
                if (chunk.done) break;

                buffer += decoder.decode(chunk.value, { stream: true });

                /* Parse SSE frames: split on double-newline.
                   Incomplete final chunk stays in buffer. */
                var parts = buffer.split('\n\n');
                buffer = parts.pop() || '';

                parts.forEach(function (frame) {
                    if (!frame.trim()) return;
                    var eventType = '';
                    var lines = frame.split('\n');
                    lines.forEach(function (line) {
                        if (line.startsWith('event: ')) {
                            eventType = line.slice(7).trim();
                        } else if (line.startsWith('data: ')) {
                            try {
                                var data = JSON.parse(line.slice(6));
                                _handlePrebuildEvent(data, cards, progressEl);
                                if (eventType === 'prebuild_complete' || data.type === 'prebuild_complete') {
                                    completeEvent = data;
                                }
                            } catch (_) { /* malformed JSON — skip */ }
                        }
                    });
                });
            }
        } finally {
            try { reader.cancel(); } catch (_) { /* ok */ }
        }

        return { event: completeEvent, error: null };
    }

    /** Render a prebuild error with Retry + Back to Menu buttons.
     *  (Lightweight inline version — no cards, just error message.) */
    function _renderPrebuildError(errors, retryHandler) {
        var msg = Array.isArray(errors) ? errors.join('; ') : String(errors);
        _container.innerHTML =
            '<div class="pb-view">' +
                '<div class="cc-transition-text" style="font-size:1.4rem; color:var(--text-error); margin-bottom:1.5rem;">' +
                    esc(msg) +
                '</div>' +
                '<div style="display:flex; gap:0.8rem; justify-content:center;">' +
                    '<button class="menu-btn" id="pb-retry">' + esc(_("Retry")) + '</button>' +
                    '<button class="menu-btn" id="pb-back">' + esc(_("Back to Menu")) + '</button>' +
                '</div>' +
            '</div>';
        document.getElementById('pb-retry').addEventListener('click', function () {
            retryHandler();
        });
        document.getElementById('pb-back').addEventListener('click', function () {
            Router.navigate('menu');
        });
    }

    async function _handleStart() {
        if (_phase !== "chatting") return;

        /* Require at least one user message before starting generation. */
        const userMsgs = $("#cc-messages").querySelectorAll(".cc-message.user");
        if (userMsgs.length === 0) {
            showToast(_("Please send a message first."));
            return;
        }

        _phase = "generating";
        _setInputEnabled(false);

        try {
            // ── Phase 1: Story generation (streaming SSE) ──────────
            var genState = _renderGenerateView();
            var genResult = await _connectGenerateStream(
                genState.tasks, genState.progressEl
            );

            if (genResult.error) {
                _renderGenError(genResult.error, _retryGenerate);
                return;
            }

            var doneEvent = genResult.event;
            if (!doneEvent || !doneEvent.game_id) {
                _renderGenError(_("Something went wrong"), _retryGenerate);
                return;
            }

            GameState.gameId = doneEvent.game_id;
            GameState.gameMode = doneEvent.game_mode || "text";  // §7.7
            GameState.storyConfig = doneEvent.story_config;

            // ── Phase 2: Material pre-build (§7.8c SSE) ──────────
            if (doneEvent.game_mode === "graph") {
                var characters = doneEvent.characters || [];
                var locations = doneEvent.locations || [];
                var hasEntities = characters.length > 0 || locations.length > 0;

                if (hasEntities) {
                    var pbState = _renderPrebuildView(characters, locations);
                    var pbResult = await _connectPrebuildStream(
                        doneEvent.game_id, pbState.cards, pbState.progressEl
                    );

                    if (pbResult.error) {
                        _renderPrebuildError(pbResult.error, _retryGenerate);
                        return;
                    }

                    var completeEvent = pbResult.event;
                    if (!completeEvent || !completeEvent.success) {
                        var errors = (completeEvent && completeEvent.errors) || [_("Prebuild failed")];
                        _renderPrebuildError(errors, _retryGenerate);
                        return;
                    }

                    /* Brief pause so the user can see all cards as "done". */
                    await new Promise(function (r) { setTimeout(r, 800); });
                }
            }

            /* Brief pause so the user can see all gen cards complete. */
            await new Promise(function (r) { setTimeout(r, 600); });

            // ── Navigate ────────────────────────────────────────────
            _phase = "done";
            Router.navigate("game-preview");
        } catch (err) {
            _renderGenError(err.message, _retryGenerate);
        }
    }

    /** Retry generation after a CoCreateError.  Uses the sync retry
     *  endpoint (faster for single retries — LLM already has context). */
    async function _retryGenerate() {
        _phase = "generating";

        try {
            // ── Phase 1: Retry story generation ────────────────────
            var genState = _renderGenerateView();
            _updateGenProgress(genState.progressEl, _("Retry") + '...');

            const genData = await API.post("/api/co-create/retry-generate");
            GameState.gameId = genData.game_id;
            GameState.gameMode = genData.game_mode || "text";  // §7.7
            GameState.storyConfig = genData.story_config;

            // ── Phase 2: Material pre-build (§7.8c SSE) ──────────
            if (genData.game_mode === "graph") {
                var characters = genData.characters || [];
                var locations = genData.locations || [];
                var hasEntities = characters.length > 0 || locations.length > 0;

                if (hasEntities) {
                    var pbState = _renderPrebuildView(characters, locations);
                    var pbResult = await _connectPrebuildStream(
                        genData.game_id, pbState.cards, pbState.progressEl
                    );

                    if (pbResult.error) {
                        _renderPrebuildError(pbResult.error, _retryGenerate);
                        return;
                    }

                    var completeEvent = pbResult.event;
                    if (!completeEvent || !completeEvent.success) {
                        var errors = (completeEvent && completeEvent.errors) || [_("Prebuild failed")];
                        _renderPrebuildError(errors, _retryGenerate);
                        return;
                    }

                    /* Brief pause so the user can see all cards as "done". */
                    await new Promise(function (r) { setTimeout(r, 800); });
                }
            }

            // ── Navigate ────────────────────────────────────────────
            _phase = "done";
            Router.navigate("game-preview");
        } catch (err) {
            if (err.status === 502) {
                _renderGenError(err.message, _retryGenerate);
            } else {
                _renderGenError(err.message, function () {
                    Router.navigate('menu');
                });
            }
        }
    }

    /* ── Transition phase rendering ────────────────────────────────── */

    /** Render the centered transition screen with animated dots.
     *  Reuses the existing cc-dots / cc-bounce animation design. */
    function _renderTransition(msg) {
        var text = msg || _("Generating settings");
        _container.innerHTML = `
            <div class="cc-transition">
                <div class="cc-transition-text">
                    <span>${esc(text)}</span>
                    <span class="cc-dots">
                        <span>.</span><span>.</span><span>.</span>
                    </span>
                </div>
            </div>
        `;
    }

    /** Transition screen with error + Retry + Back to Menu buttons. */
    function _renderTransitionError(message, retryHandler) {
        _container.innerHTML = `
            <div class="cc-transition">
                <div class="cc-transition-text" style="font-size:1.4rem; color:var(--text-error); margin-bottom:1.5rem;">
                    ${esc(message)}
                </div>
                <div style="display:flex; gap:0.8rem; justify-content:center;">
                    <button class="menu-btn" id="cc-transition-retry">${esc(_("Retry"))}</button>
                    <button class="menu-btn" id="cc-transition-back">${esc(_("Back to Menu"))}</button>
                </div>
            </div>
        `;
        document.getElementById("cc-transition-retry").addEventListener("click", () => {
            retryHandler();
        });
        document.getElementById("cc-transition-back").addEventListener("click", () => {
            Router.navigate("menu");
        });
    }

    /** Transition screen with fatal error + Back to Menu button. */
    function _renderTransitionFatal(message) {
        _phase = "done";
        _container.innerHTML = `
            <div class="cc-transition">
                <div class="cc-transition-text" style="font-size:1.4rem; color:var(--text-error); margin-bottom:1.5rem;">
                    ${esc(message)}
                </div>
                <button class="menu-btn" id="cc-transition-back">${esc(_("Back to Menu"))}</button>
            </div>
        `;
        document.getElementById("cc-transition-back").addEventListener("click", () => {
            Router.navigate("menu");
        });
    }

    /* ── Send message ─────────────────────────────────────────────── */

    async function _handleSend() {
        if (_phase !== "chatting") return;

        const input = $("#cc-input");
        const text = input.value.trim();
        if (!text) return;

        // ── Normal message → send to LLM ──────────────────────────
        _addMessage("user", text);
        input.value = "";
        _autoResize(input);
        _setInputEnabled(false);
        _showTyping();

        try {
            const data = await API.post("/api/co-create/send", { text });
            _hideTyping();
            _addMessage("assistant", data.reply);
            _setInputEnabled(true);
            _updatePlaceholder();
            _focusInput();
        } catch (err) {
            _hideTyping();
            // 502 = CoCreateError → retriable (mirrors dev_cli)
            if (err.status === 502) {
                _addErrorWithRetry(err.message, _retrySend);
            } else {
                _showFatalError(err.message);
            }
            _setInputEnabled(true);
            _focusInput();
        }
    }

    /** Self-contained retry — calls retry-send directly, no input dependency. */
    async function _retrySend() {
        _setInputEnabled(false);
        _showTyping();
        try {
            const data = await API.post("/api/co-create/retry-send");
            _hideTyping();
            _addMessage("assistant", data.reply);
            _setInputEnabled(true);
            _focusInput();
        } catch (err) {
            _hideTyping();
            if (err.status === 502) {
                _addErrorWithRetry(err.message, _retrySend);
            } else {
                _showFatalError(err.message);
            }
            _setInputEnabled(true);
            _focusInput();
        }
    }

    /* ── Message rendering ───────────────────────────────────────── */

    function _addMessage(role, text) {
        const msgs = $("#cc-messages");
        if (!msgs) return;
        const div = document.createElement("div");
        div.className = `cc-message ${role}`;
        div.textContent = text;
        msgs.appendChild(div);
        _scrollToBottom();
    }

    /** Show typing indicator with animated bouncing dots. */
    function _showTyping() {
        const msgs = $("#cc-messages");
        if (!msgs) return;
        const el = document.createElement("div");
        el.className = "cc-typing";
        el.id = "cc-typing-indicator";
        el.innerHTML = `<span>${esc(_("Thinking"))}</span><span class="cc-dots"><span>.</span><span>.</span><span>.</span></span>`;
        msgs.appendChild(el);
        _scrollToBottom();
    }

    function _hideTyping() {
        const el = $("#cc-typing-indicator");
        if (el) el.remove();
    }

    function _clearMessages() {
        const msgs = $("#cc-messages");
        if (msgs) msgs.innerHTML = "";
    }

    /** Error message + Retry button — text and button stacked vertically. */
    function _addErrorWithRetry(message, retryHandler) {
        const msgs = $("#cc-messages");
        if (!msgs) return;
        const div = document.createElement("div");
        div.className = "cc-message error";

        const msgEl = document.createElement("div");
        msgEl.textContent = message;
        div.appendChild(msgEl);

        const btn = document.createElement("button");
        btn.className = "menu-btn";
        btn.style.display = "block";
        btn.style.margin = "0.7rem auto 0";
        btn.textContent = _("Retry");
        btn.addEventListener("click", () => {
            div.remove();
            retryHandler();
        });
        div.appendChild(btn);
        msgs.appendChild(div);
        _scrollToBottom();
    }

    /** Fatal error — show message with Back to Menu button below. */
    function _showFatalError(message) {
        _phase = "done";
        _setInputEnabled(false);
        const msgs = $("#cc-messages");
        if (!msgs) return;
        const div = document.createElement("div");
        div.className = "cc-message error";

        const msgEl = document.createElement("div");
        msgEl.textContent = message;
        div.appendChild(msgEl);

        const btn = document.createElement("button");
        btn.className = "menu-btn";
        btn.style.display = "block";
        btn.style.margin = "0.7rem auto 0";
        btn.textContent = _("Back to Menu");
        btn.addEventListener("click", () => {
            Router.navigate("menu");
        });
        div.appendChild(btn);
        msgs.appendChild(div);
        _scrollToBottom();
    }

    /* ── Input helpers ────────────────────────────────────────────── */

    function _setInputEnabled(enabled) {
        const input = $("#cc-input");
        const sendBtn = $("#cc-send");
        const backBtn = $("#cc-back");
        const startBtn = $("#cc-start");
        if (input) input.disabled = !enabled;
        if (sendBtn) sendBtn.disabled = !enabled;
        if (backBtn) backBtn.disabled = !enabled;
        if (startBtn) startBtn.disabled = !enabled;
    }

    function _focusInput() {
        const input = $("#cc-input");
        if (input && !input.disabled) {
            input.focus();
        }
    }

    function _autoResize(textarea) {
        if (!textarea) return;
        textarea.style.height = "auto";
        textarea.style.height = Math.min(textarea.scrollHeight, 128) + "px";
    }

    function _updatePlaceholder() {
        const input = $("#cc-input");
        if (!input) return;
        const msgs = $("#cc-messages");
        const userCount = msgs
            ? msgs.querySelectorAll(".cc-message.user").length
            : 0;
        input.placeholder = userCount === 0
            ? _("Type your story idea...")
            : _("Type your answer...");
    }

    function _scrollToBottom() {
        const msgs = $("#cc-messages");
        if (msgs) {
            requestAnimationFrame(() => {
                msgs.scrollTop = msgs.scrollHeight;
            });
        }
    }

    /* ── Export ──────────────────────────────────────────────────── */
    return { render };
})();

/* ═══════════════════════════════════════════════════════════════════
   graph-renderer.js — Visual Novel rendering module (§7.7)

   Manages VN layers: background, sprites, dialog with typewriter,
   choices overlay, backlog, settings, immersive mode.

   Exports (GraphRenderer namespace):
     init(container)                — build VN DOM
     destroy()                      — clean up
     setBackground(url)             — fade-in background
     setSprite(url)                 — set character sprite
     clearSprite()                  — remove sprite
     showSegment(text, char)        — typewriter text + name tag
     showChoices(choices, cb)       — render choice buttons, cb(key)
     clearChoices()                 — remove choice overlay
     showBacklog()                  — open backlog overlay
     hideBacklog()                  — close backlog
     showSettings()                 — open settings overlay
     hideSettings()                 — close settings
     setAutoMode(on)                — toggle auto-advance
     setImmersive(on)               — toggle immersive mode
     showEndChoice(onViewLog)       — post-ending "view log" button
     setTitle(title)                — set topbar title
     onAdvance(callback)            — set callback for manual advance

   Tunable constants (§4): SPEEDS, AUTO_CHAR_MS, FONT_SIZES — no hardcoded
   magic numbers.  All UI strings via _() (i18n).

   Authority:
     design.md §4-5 (constants, API)
     temp/vn-prototype.html (reference implementation)
     display.js / game.js (IIFE module pattern)
   ═══════════════════════════════════════════════════════════════════ */

const GraphRenderer = (function () {
    /* ── Tunable constants (§4) ─────────────────────────────────── */
    const SPEEDS       = { slow: 25, normal: 15, fast: 8 };         // ms / char (typewriter)
    const AUTO_CHAR_MS = { short: 30, normal: 50, long: 70 };       // ms / char (auto-delay)
    const FONT_SIZES   = { small: "1.15rem", medium: "1.35rem", large: "1.55rem" };
    const AUTO_BASE_MS = 500;  // minimum auto-delay (ms)

    /* ── Internal state ─────────────────────────────────────────── */
    let _container = null;
    let _mode = "manual";        // "manual" | "auto"
    let _immersive = false;
    let _typing = false;
    let _typeTimer = null;
    let _autoTimer = null;
    let _charDelay = SPEEDS.normal;
    let _autoCharMs = AUTO_CHAR_MS.normal;
    let _currentText = "";       // for auto-delay calculation
    let _history = [];           // {name, text}[]
    let _advanceCallback = null;  // called when user advances past text
    let _modeChangeCallback = null;  // called when auto/manual mode changes

    /* ── DOM helpers ────────────────────────────────────────────── */
    function $(sel) { return _container ? _container.querySelector(sel) : null; }

    /** Build a /media/ URL for an asset.  Uses the AssetType value as the
     *  subdirectory name (e.g. "char_portrait", "background_img").  */
    function assetUrl(assetType, assetId) {
        return "/" + DEFAULT_MEDIA_DIR + "/" + assetType + "/" + assetId + ".png";
    }

    /** Available via state.js initConfig → read from config.  Must match
     *  server-side DEFAULT_MEDIA_DIR (src/storyloom/config.py).  */
    var DEFAULT_MEDIA_DIR = "media";

    /* ═══════════════════════════════════════════════════════════════
       Public API
       ═══════════════════════════════════════════════════════════════ */

    function init(container) {
        _container = container;
        _currentText = "";  // reset stale text from previous session
        _buildDOM();
        _bindEvents();
    }

    function destroy() {
        _stopTimers();
        if (_keydownHandler) {
            document.removeEventListener("keydown", _keydownHandler);
            _keydownHandler = null;
        }
        if (_container) {
            _container.innerHTML = "";
            _container = null;
        }
        _history = [];
        _advanceCallback = null;
        _modeChangeCallback = null;
    }

    /* ── DOM construction ───────────────────────────────────────── */

    function _buildDOM() {
        _container.innerHTML = `
            <div class="vn-scene" id="vnScene">
                <div class="vn-bg" id="vnBg"><img src="" alt=""></div>
                <div class="vn-sprites" id="vnSprites"></div>
                <div class="vn-topbar" id="vnTopbar">
                    <button class="vn-btn" id="vnBtnExit" title="${_("Quit")}">
                        <svg viewBox="0 0 24 24"><polyline points="15,4 7,12 15,20"/></svg>
                    </button>
                    <span class="vn-topbar-title" id="vnTitle"></span>
                    <button class="vn-btn" id="vnBtnAuto" title="${_("Switch to Auto")}">
                        <svg viewBox="0 0 24 24" id="vnSvgAuto"><polygon points="6,4 20,12 6,20"/></svg>
                    </button>
                    <button class="vn-btn" id="vnBtnBacklog" title="${_("Backlog")}">
                        <svg viewBox="0 0 24 24"><line x1="8" y1="6" x2="20" y2="6"/><line x1="8" y1="10" x2="20" y2="10"/><line x1="8" y1="14" x2="20" y2="14"/><line x1="4" y1="6" x2="4" y2="14"/></svg>
                    </button>
                    <button class="vn-btn" id="vnBtnImmersive" title="${_("Immersive Mode")}">
                        <svg viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
                    </button>
                    <button class="vn-btn" id="vnBtnSettings" title="${_("Settings")}">
                        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
                    </button>
                </div>
                <div class="vn-dialog" id="vnDialog">
                    <div class="vn-dialog-inner">
                        <div class="vn-name-tag" id="vnNameTag" style="display:none"></div>
                        <div class="vn-text" id="vnText"></div>
                    </div>
                </div>
                <div class="vn-ctc" id="vnCtc">▼</div>
                <div class="vn-backlog-overlay" id="vnBacklog" style="display:none">
                    <div class="vn-backlog-header">
                        <span class="vn-backlog-title">${_("Backlog")}</span>
                        <button class="vn-btn" id="vnBacklogClose">
                            <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                    </div>
                    <div class="vn-backlog-list" id="vnBacklogList"></div>
                </div>
                <div class="vn-settings-overlay" id="vnSettings" style="display:none">
                    <div class="vn-settings-panel">
                        <h3>${_("Settings")}</h3>
                        <div class="vn-setting-row">
                            <span class="vn-setting-label">${_("Display Speed")}</span>
                            <div class="vn-setting-options" id="vnSettingAuto">
                                <button class="vn-setting-opt" data-val="${AUTO_CHAR_MS.long}">${_("Slow")}</button>
                                <button class="vn-setting-opt active" data-val="${AUTO_CHAR_MS.normal}">${_("Medium")}</button>
                                <button class="vn-setting-opt" data-val="${AUTO_CHAR_MS.short}">${_("Fast")}</button>
                            </div>
                        </div>
                        <div class="vn-setting-row">
                            <span class="vn-setting-label">${_("Font Size")}</span>
                            <div class="vn-setting-options" id="vnSettingFont">
                                <button class="vn-setting-opt" data-val="${FONT_SIZES.small}">${_("Small")}</button>
                                <button class="vn-setting-opt active" data-val="${FONT_SIZES.medium}">${_("Medium")}</button>
                                <button class="vn-setting-opt" data-val="${FONT_SIZES.large}">${_("Large")}</button>
                            </div>
                        </div>
                        <button class="vn-settings-close" id="vnSettingsClose">${_("Close")}</button>
                    </div>
                </div>
                <div class="vn-choices-overlay" id="vnChoices" style="display:none">
                    <div class="vn-choices-box" id="vnChoicesBox"></div>
                </div>
            </div>
        `;
    }

    /* ── Event binding ──────────────────────────────────────────── */

    let _keydownHandler = null;

    function _bindEvents() {
        /* Click on scene → advance (manual mode) */
        $("#vnScene").addEventListener("click", function (e) {
            if (e.target.closest(".vn-choices-overlay")) return;
            if (e.target.closest(".vn-backlog-overlay")) return;
            if (e.target.closest(".vn-settings-overlay")) return;
            if (e.target.closest("button")) return;
            if (_immersive) { setImmersive(false); return; }
            if (_mode === "manual") _advance();
        });

        /* Keyboard */
        _keydownHandler = _onKeyDown;
        document.addEventListener("keydown", _keydownHandler);

        /* Topbar buttons */
        $("#vnBtnAuto").addEventListener("click", function () { setAutoMode(_mode !== "auto"); });
        $("#vnBtnBacklog").addEventListener("click", function () { showBacklog(); });
        $("#vnBtnImmersive").addEventListener("click", function () { setImmersive(!_immersive); });
        $("#vnBtnSettings").addEventListener("click", function () { showSettings(); });
        $("#vnBacklogClose").addEventListener("click", function () { hideBacklog(); });
        $("#vnSettingsClose").addEventListener("click", function () { hideSettings(); });

        /* Settings handlers — O(1) delegated click */
        _bindSettingClicks("vnSettingAuto", function (val) { _autoCharMs = parseInt(val); });
        _bindSettingClicks("vnSettingFont", function (val) {
            document.documentElement.style.setProperty("--vn-font-size", val);
        });
    }

    /** Generic O(1) delegated click for a settings option group. */
    function _bindSettingClicks(id, onChange) {
        var el = $("#" + id);
        if (!el) return;
        el.addEventListener("click", function (e) {
            var btn = e.target.closest(".vn-setting-opt");
            if (!btn) return;
            var opts = el.querySelectorAll(".vn-setting-opt");
            for (var i = 0; i < opts.length; i++) opts[i].classList.remove("active");
            btn.classList.add("active");
            onChange(btn.dataset.val);
        });
    }

    /* ═══════════════════════════════════════════════════════════════
       Background / Sprite layers
       ═══════════════════════════════════════════════════════════════ */

    function setBackground(url) {
        var container = $("#vnBg");
        if (!container) return;
        var oldImg = container.querySelector("img");
        if (oldImg && oldImg.src === url) return;  // no change
        // Crossfade: insert new img behind, fade old out, remove old
        var newImg = document.createElement("img");
        newImg.src = url;
        newImg.style.opacity = "0";
        newImg.style.position = "absolute";
        newImg.style.inset = "0";
        newImg.style.width = "100%";
        newImg.style.height = "100%";
        newImg.style.objectFit = "cover";
        newImg.style.transition = "opacity 0.6s ease";
        container.appendChild(newImg);
        // Force layout then fade in
        void newImg.offsetWidth;
        newImg.style.opacity = "1";
        if (oldImg) {
            oldImg.style.opacity = "0";
            setTimeout(function () { if (oldImg.parentNode) oldImg.remove(); }, 700);
        }
    }

    function setSprite(url) {
        var container = $("#vnSprites");
        if (!container) return;
        var img = container.querySelector("img");
        if (!img) {
            img = document.createElement("img");
            img.className = "vn-sprite";
            container.appendChild(img);
        }
        img.src = url;
    }

    function clearSprite() {
        var container = $("#vnSprites");
        if (container) container.innerHTML = "";
    }

    /* ── Loading indicator ──────────────────────────────────────── */

    function showLoading() {
        var el = $("#vnText");
        if (!el || el.textContent) return;
        el.innerHTML = '<svg width="60" height="12" viewBox="0 0 60 12" style="display:block;margin:0 auto">'
            + '<circle cx="6" cy="6" r="4" fill="var(--text-secondary)" opacity="0.3">'
            + '<animate attributeName="opacity" values="0.3;1;0.3" dur="1.2s" begin="0s" repeatCount="indefinite"/></circle>'
            + '<circle cx="22" cy="6" r="4" fill="var(--text-secondary)" opacity="0.3">'
            + '<animate attributeName="opacity" values="0.3;1;0.3" dur="1.2s" begin="0.2s" repeatCount="indefinite"/></circle>'
            + '<circle cx="38" cy="6" r="4" fill="var(--text-secondary)" opacity="0.3">'
            + '<animate attributeName="opacity" values="0.3;1;0.3" dur="1.2s" begin="0.4s" repeatCount="indefinite"/></circle>'
            + '<circle cx="54" cy="6" r="4" fill="var(--text-secondary)" opacity="0.3">'
            + '<animate attributeName="opacity" values="0.3;1;0.3" dur="1.2s" begin="0.6s" repeatCount="indefinite"/></circle>'
            + '</svg>';
    }

    function hideLoading() {
        var el = $("#vnText");
        if (el && el.querySelector("svg")) el.textContent = "";
    }

    /* ═══════════════════════════════════════════════════════════════
       Typewriter
       ═══════════════════════════════════════════════════════════════ */

    function showSegment(text, charName) {
        _currentText = text;  // §7.7: store for auto-delay calculation
        /* Name tag */
        var nameTag = $("#vnNameTag");
        if (nameTag) {
            if (charName) {
                nameTag.textContent = charName;
                nameTag.style.display = "inline-block";
            } else {
                nameTag.style.display = "none";
            }
        }
        /* Add to history */
        _history.push({ name: charName || null, text: text });
        /* Start typewriter */
        _startTyping(text);
    }

    function _startTyping(text) {
        _stopTimers();
        _typing = true;
        var el = $("#vnText");
        if (!el) return;
        el.textContent = "";
        var ctc = $("#vnCtc");
        if (ctc) ctc.classList.remove("visible");
        var i = 0;
        function tick() {
            if (i < text.length) {
                el.textContent += text[i];
                i++;
                _typeTimer = setTimeout(tick, _charDelay);
            } else {
                _typing = false;
                if (ctc) ctc.classList.add("visible");
                if (_mode === "auto") {
                    var delay = AUTO_BASE_MS + _currentText.length * _autoCharMs;
                    _autoTimer = setTimeout(function () { _advance(); }, delay);
                }
            }
        }
        _typeTimer = setTimeout(tick, _charDelay);
    }

    /** First click: show full text instantly.  Returns true if skipped. */
    function _skipTypewriter() {
        if (!_typing) return false;
        clearTimeout(_typeTimer);
        _typing = false;
        var ctc = $("#vnCtc");
        if (ctc) ctc.classList.add("visible");
        return true;
    }

    function _advance() {
        if (_typing) {
            _skipTypewriter();
            return;
        }
        clearTimeout(_autoTimer);
        if (_advanceCallback) _advanceCallback();
    }

    function _stopTimers() {
        if (_typeTimer) { clearTimeout(_typeTimer); _typeTimer = null; }
        if (_autoTimer) { clearTimeout(_autoTimer); _autoTimer = null; }
    }

    function onAdvance(callback) {
        _advanceCallback = callback;
    }

    function onModeChange(callback) {
        _modeChangeCallback = callback;
    }

    /* ═══════════════════════════════════════════════════════════════
       Choices
       ═══════════════════════════════════════════════════════════════ */

    var _choiceCallback = null;

    function showChoices(choices, callback) {
        _choiceCallback = callback;
        var box = $("#vnChoicesBox");
        var overlay = $("#vnChoices");
        if (!box || !overlay) return;

        var flat = Display.flattenChoices(choices);
        var html = "";
        for (var i = 0; i < flat.length; i++) {
            var c = flat[i];
            var reasonHtml = (!c.enabled && c.reason)
                ? '<span class="vn-choice-reason">(' + c.reason + ')</span>' : "";
            html += '<button class="vn-choice-btn" data-key="' + c.key + '"'
                 + (c.enabled ? "" : " disabled") + '>'
                 + c.label + reasonHtml + '</button>';
        }
        box.innerHTML = html;

        var btns = box.querySelectorAll(".vn-choice-btn:not(:disabled)");
        for (var j = 0; j < btns.length; j++) {
            btns[j].addEventListener("click", function () {
                overlay.style.display = "none";
                if (_choiceCallback) _choiceCallback(this.dataset.key);
            });
        }

        overlay.style.display = "flex";
    }

    function clearChoices() {
        var overlay = $("#vnChoices");
        if (overlay) overlay.style.display = "none";
        _choiceCallback = null;
    }

    /* ═══════════════════════════════════════════════════════════════
       Backlog
       ═══════════════════════════════════════════════════════════════ */

    function showBacklog() {
        var overlay = $("#vnBacklog");
        var list = $("#vnBacklogList");
        if (!overlay || !list) return;
        setAutoMode(false);  // always switch to manual
        var html = "";
        for (var i = 0; i < _history.length; i++) {
            var h = _history[i];
            html += '<div class="vn-backlog-entry">'
                 + (h.name ? '<div class="vn-backlog-name">' + h.name + '</div>' : "")
                 + '<div class="vn-backlog-text">' + h.text + '</div></div>';
        }
        list.innerHTML = html;
        list.scrollTop = list.scrollHeight;  // show newest entries first
        overlay.style.display = "flex";
    }

    function hideBacklog() {
        var overlay = $("#vnBacklog");
        if (overlay) overlay.style.display = "none";
    }

    /* ═══════════════════════════════════════════════════════════════
       Settings
       ═══════════════════════════════════════════════════════════════ */

    function showSettings() {
        var overlay = $("#vnSettings");
        if (!overlay) return;
        setAutoMode(false);  // always switch to manual
        overlay.style.display = "flex";
    }

    function hideSettings() {
        var overlay = $("#vnSettings");
        if (overlay) overlay.style.display = "none";
    }

    /* ═══════════════════════════════════════════════════════════════
       Modes
       ═══════════════════════════════════════════════════════════════ */

    function setAutoMode(on) {
        _mode = on ? "auto" : "manual";
        var btn = $("#vnBtnAuto");
        var svg = $("#vnSvgAuto");
        if (btn) {
            btn.classList.toggle("active", on);
            btn.title = on ? _("Switch to Manual") : _("Switch to Auto");
        }
        if (svg) {
            svg.innerHTML = on
                ? '<rect x="7" y="5" width="3" height="14" rx="0.5"/><rect x="14" y="5" width="3" height="14" rx="0.5"/>'
                : '<polygon points="6,4 20,12 6,20"/>';
        }
        /* Cancel stale auto-advance timer but leave typewriter intact —
           toggling mode while text is appearing should not kill the
           typewriter mid-stream.  The new mode takes effect after the
           current typewriter finishes naturally. */
        if (_autoTimer) { clearTimeout(_autoTimer); _autoTimer = null; }
        if (_modeChangeCallback) _modeChangeCallback(on);
        /* Only auto-start the timer when text is already on screen
           (typewriter completed).  If _currentText is empty the user
           switched to auto before the first segment — let the typewriter
           completion set the first autoTimer naturally. */
        if (on && !_typing && _currentText) {
            _autoTimer = setTimeout(function () { _advance(); }, AUTO_BASE_MS);
        }
    }

    function setImmersive(on) {
        if (on) setAutoMode(false);  // entering immersive → manual
        _immersive = on;
        var topbar = $("#vnTopbar");
        var dialog = $("#vnDialog");
        var ctc = $("#vnCtc");
        var btn = $("#vnBtnImmersive");
        if (topbar) topbar.classList.toggle("hidden", on);
        if (dialog) { dialog.style.opacity = on ? "0" : "1"; dialog.style.transition = "opacity 0.5s"; }
        if (ctc) ctc.style.display = on ? "none" : "block";
        if (btn) btn.classList.toggle("active", on);
    }

    /* ── Keyboard handler ───────────────────────────────────────── */

    function _onKeyDown(e) {
        if (e.key === " " || e.key === "Enter") {
            e.preventDefault();
            /* Don't advance when an overlay is open */
            var bl = $("#vnBacklog");
            var st = $("#vnSettings");
            if ((bl && bl.style.display === "flex") ||
                (st && st.style.display === "flex")) return;
            if (_immersive) { setImmersive(false); return; }
            if (_mode === "manual") _advance();
        }
        if (e.key === "Escape") {
            hideSettings();
            hideBacklog();
        }
        if (e.key === "a" && !e.ctrlKey && !e.metaKey) setAutoMode(_mode !== "auto");
        if (e.key === "i" && !e.ctrlKey && !e.metaKey) setImmersive(!_immersive);
        if (e.key === "b" && !e.ctrlKey && !e.metaKey) {
            var bl = $("#vnBacklog");
            if (bl && bl.style.display === "flex") hideBacklog(); else showBacklog();
        }
    }

    /* ═══════════════════════════════════════════════════════════════
       End-of-game
       ═══════════════════════════════════════════════════════════════ */

    function showEndChoice(onViewLog) {
        var box = $("#vnChoicesBox");
        var overlay = $("#vnChoices");
        if (!box || !overlay) return;
        box.innerHTML = '<button class="vn-choice-btn vn-ending-choice" id="vnEndChoice">'
            + _("The story has ended. View adventure log.") + '</button>';
        document.getElementById("vnEndChoice").addEventListener("click", function () {
            overlay.style.display = "none";
            if (onViewLog) onViewLog();
        });
        overlay.style.display = "flex";
    }

    /* ── Title ───────────────────────────────────────────────────── */

    function setTitle(title) {
        var el = $("#vnTitle");
        if (el) el.textContent = title;
    }

    /* ── Export ──────────────────────────────────────────────────── */
    return {
        init: init,
        destroy: destroy,
        setBackground: setBackground,
        setSprite: setSprite,
        clearSprite: clearSprite,
        showLoading: showLoading,
        hideLoading: hideLoading,
        assetUrl: assetUrl,
        showSegment: showSegment,
        showChoices: showChoices,
        clearChoices: clearChoices,
        showEndChoice: showEndChoice,
        showBacklog: showBacklog,
        hideBacklog: hideBacklog,
        showSettings: showSettings,
        hideSettings: hideSettings,
        setAutoMode: setAutoMode,
        setImmersive: setImmersive,
        onAdvance: onAdvance,
        onModeChange: onModeChange,
        setTitle: setTitle,
    };
})();

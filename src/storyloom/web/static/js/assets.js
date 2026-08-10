/* ═══════════════════════════════════════════════════════════════════
   assets.js — Asset Management view (#assets)

   Layout: left sidebar (type nav + "Auto Clean" button) + right
   card list.  Cards show name, description, use_count.  Click card
   → image viewer overlay.  Hover → trash icon (greyed if in use).

   Exports (on window):
     AssetManagerView.render(app)  — render the full asset manager view

   Authority:
     design.md §2.2 (AssetLibrary), §9 (storage)
     router.js renderSaveList pattern (card list UI)
   ═══════════════════════════════════════════════════════════════════ */

const AssetManagerView = (function () {
    "use strict";

    /** Tiny HTML escape (same algorithm as router.js esc()). */
    function esc(s) {
        var d = document.createElement("div");
        d.textContent = s;
        return d.innerHTML;
    }

    // ── SVG icons ─────────────────────────────────────────────────

    const X_ICON = '<svg viewBox="0 0 24 24" width="22" height="22" '
        + 'fill="none" stroke="currentColor" stroke-width="2" '
        + 'stroke-linecap="round">'
        + '<path d="M6 6 L18 18 M18 6 L6 18"/>'
        + '</svg>';

    const TRASH_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" '
        + 'fill="none" stroke="currentColor" stroke-width="2" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<polyline points="3 6 5 6 21 6"/>'
        + '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
        + '<line x1="10" y1="11" x2="10" y2="17"/>'
        + '<line x1="14" y1="11" x2="14" y2="17"/>'
        + '</svg>';

    // ── Type labels (msgid) ───────────────────────────────────────

    const TYPE_LABELS = {
        "char_portrait": "Character Portrait",
        "background_img": "Background Image",
    };

    // ── State ─────────────────────────────────────────────────────

    let _assets = null;       // cached API response: { type_value: { id: Asset_dict } }
    let _activeType = null;   // currently selected AssetType value string

    /* ── Main render ─────────────────────────────────────────────── */

    function render(app) {
        GameState.reset();
        if (typeof SSEClient !== "undefined" && SSEClient.close) {
            SSEClient.close();
        }

        app.innerHTML = `
            <div class="am-view">
                <div class="am-header">
                    <button class="cc-back-btn" id="am-back"
                            title="${esc(_("Back to Menu"))}">${Icons.arrowLeft()}</button>
                    <span class="am-title">${esc(_("Asset Management"))}</span>
                    <button class="theme-toggle-btn" id="am-theme-btn" title="${esc(_("Toggle Theme"))}"></button>
                </div>
                <div class="am-body">
                    <div class="am-sidebar" id="am-sidebar">
                        <p class="am-loading">${esc(_("Loading..."))}</p>
                    </div>
                    <div class="am-content">
                        <div class="am-toolbar" id="am-toolbar"></div>
                        <div class="am-list" id="am-list">
                            <!-- cards rendered here -->
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.getElementById("am-back").addEventListener("click", function () {
            Router.navigate("menu");
        });

        var themeBtn = document.getElementById("am-theme-btn");
        if (themeBtn) {
            window._updateThemeButton(themeBtn);
            themeBtn.addEventListener("click", function () {
                ThemeState.toggle();
                saveConfig();
                window._updateAllThemeButtons();
            });
        }

        API.get("/api/assets").then(function (data) {
            _assets = data.types || {};
            var typeKeys = Object.keys(_assets);
            if (!typeKeys.length) {
                document.getElementById("am-sidebar").innerHTML = "";
                document.getElementById("am-list").innerHTML =
                    '<p class="am-empty">' + esc(_("No assets found")) + '</p>';
                return;
            }
            if (!_activeType || !_assets[_activeType]) {
                _activeType = typeKeys[0];
            }
            _renderSidebar(typeKeys);
            _renderToolbar();
            _renderCards();
        }).catch(function (err) {
            document.getElementById("am-sidebar").innerHTML = "";
            document.getElementById("am-toolbar").innerHTML = "";
            document.getElementById("am-list").innerHTML =
                '<p class="text-error">' + esc(err.message) + '</p>';
        });
    }

    /* ── Sidebar ─────────────────────────────────────────────────── */

    function _renderSidebar(typeKeys) {
        var sidebarEl = document.getElementById("am-sidebar");
        sidebarEl.innerHTML =
            '<nav class="am-nav">' +
                typeKeys.map(function (k) {
                    return '<button class="am-nav-item' + (k === _activeType ? " active" : "") + '"'
                        + ' data-type="' + esc(k) + '">' + esc(_(TYPE_LABELS[k] || k)) + '</button>';
                }).join("") +
            '</nav>';

        sidebarEl.querySelectorAll(".am-nav-item").forEach(function (btn) {
            btn.addEventListener("click", function () {
                _activeType = btn.dataset.type;
                _renderSidebar(typeKeys);
                _renderToolbar();
                _renderCards();
            });
        });
    }

    /* ── Toolbar (right panel, above cards) ─────────────────────── */

    function _renderToolbar() {
        var toolbarEl = document.getElementById("am-toolbar");
        toolbarEl.innerHTML =
            '<span class="am-toolbar-label">' + esc(_(TYPE_LABELS[_activeType] || _activeType)) + '</span>' +
            '<button class="am-clean-btn" id="am-clean"'
                + ' title="' + esc(_("Clean Unused")) + '">' + esc(_("Clean Unused")) + '</button>';

        document.getElementById("am-clean").addEventListener("click", async function () {
            try {
                var res = await API.post(
                    "/api/assets/clean?type=" + encodeURIComponent(_activeType) +
                    "&keep_count=" + encodeURIComponent("50")
                );
                showToast(_("Cleanup complete."));
                var data = await API.get("/api/assets");
                _assets = data.types || {};
                _renderCards();
            } catch (err) {
                showToast(err.message);
            }
        });
    }

    /* ── Card list — gallery grid ────────────────────────────────── */

    function _renderCards() {
        var listEl = document.getElementById("am-list");
        var items = _assets[_activeType] || {};
        var ids = Object.keys(items);

        if (!ids.length) {
            listEl.innerHTML = '<p class="am-empty">' + esc(_("No assets found")) + '</p>';
            return;
        }

        var imgUrl = MEDIA_PATH + "/" + _activeType + "/";

        listEl.innerHTML = ids.map(function (id) {
            var a = items[id];
            var name = a.name || id;
            var desc = a.description || "";
            var uc = a.use_count || 0;
            var trashCls = uc > 0 ? "am-card-trash disabled" : "am-card-trash";
            return '<div class="am-card" data-id="' + esc(id) + '" data-name="' + esc(name) + '">'
                + '<img class="am-card-img" src="' + imgUrl + encodeURIComponent(id) + '"'
                    + ' alt="' + esc(name) + '" loading="lazy">'
                + '<div class="am-card-overlay">'
                    + '<span class="am-card-label" title="' + esc(name) + '">' + esc(name) + '</span>'
                    + (desc ? '<span class="am-card-desc" title="' + esc(desc) + '">' + esc(desc) + '</span>' : "")
                    + '<span class="am-card-usage">' + esc(_("In Use")) + ': ' + uc + '</span>'
                + '</div>'
                + '<button class="' + trashCls + '"'
                    + ' title="' + esc(_("Delete")) + '" data-id="' + esc(id) + '"'
                    + (uc > 0 ? ' data-uc="1"' : "") + '>' + Icons.trash() + '</button>'
            + '</div>';
        }).join("");

        // Card click → viewer (ignore clicks on trash button)
        listEl.querySelectorAll(".am-card").forEach(function (card) {
            card.addEventListener("click", function (e) {
                if (e.target.closest(".am-card-trash")) return;
                _openViewer(card.dataset.id, card.dataset.name, _activeType);
            });
        });

        // Trash click
        listEl.querySelectorAll(".am-card-trash").forEach(function (btn) {
            btn.addEventListener("click", function (e) {
                e.stopPropagation();
                var id = btn.dataset.id;
                if (btn.dataset.uc) {
                    showToast(_("Asset in use, cannot delete"));
                    return;
                }
                _confirmDelete(e.clientX, e.clientY, id);
            });
        });
    }

    /* ── Delete confirmation ──────────────────────────────────────── */

    function _confirmDelete(x, y, assetId) {
        var existing = document.querySelector(".ctx-menu");
        if (existing) existing.remove();

        var menu = document.createElement("div");
        menu.className = "ctx-menu";
        menu.innerHTML =
            '<p class="ctx-menu-text">' + esc(_("Delete this asset?")) + '</p>'
            + '<p class="ctx-menu-warn">' + esc(_("This cannot be undone.")) + '</p>'
            + '<div class="ctx-menu-actions">'
                + '<button class="ctx-menu-btn" id="ctx-no">' + esc(_("No")) + '</button>'
                + '<button class="ctx-menu-btn danger" id="ctx-yes">' + esc(_("Yes")) + '</button>'
            + '</div>';
        menu.style.left = Math.min(x, window.innerWidth - 240) + "px";
        menu.style.top = Math.min(y, window.innerHeight - 140) + "px";
        document.body.appendChild(menu);

        var close = function () { menu.remove(); };
        menu.querySelector("#ctx-no").addEventListener("click", close);
        menu.querySelector("#ctx-yes").addEventListener("click", async function () {
            close();
            try {
                await API.del(
                    "/api/assets/" + encodeURIComponent(_activeType) +
                    "/" + encodeURIComponent(assetId)
                );
                showToast(_("Asset deleted."));
                delete _assets[_activeType][assetId];
                _renderCards();
            } catch (err) {
                showToast(err.message);
            }
        });
        setTimeout(function () {
            document.addEventListener("click", function handler(e) {
                if (!menu.contains(e.target)) {
                    close();
                    document.removeEventListener("click", handler);
                }
            });
        }, 0);
    }

    /* ── Image viewer overlay ─────────────────────────────────────── */

    function _openViewer(assetId, name, assetType) {
        var url = MEDIA_PATH + "/" + assetType + "/" + assetId;

        var overlay = document.createElement("div");
        overlay.className = "am-viewer-overlay";
        overlay.id = "am-viewer-overlay";
        overlay.innerHTML =
            '<div class="am-viewer-toolbar">'
                + '<a class="am-viewer-btn" href="' + url + '" download'
                    + ' title="' + esc(_("Download")) + '">' + Icons.download() + '</a>'
                + '<button class="am-viewer-btn" id="am-viewer-close"'
                    + ' title="' + esc(_("Close")) + '">' + X_ICON + '</button>'
            + '</div>'
            + '<div class="am-viewer-content">'
                + '<img src="' + url + '" alt="' + esc(name) + '" class="am-viewer-img">'
            + '</div>';

        document.body.appendChild(overlay);

        var closeViewer = function () { overlay.remove(); };
        document.getElementById("am-viewer-close").addEventListener("click", closeViewer);
        overlay.addEventListener("click", function (e) {
            if (e.target === overlay) closeViewer();
        });
        document.addEventListener("keydown", function onEsc(e) {
            if (e.key === "Escape") {
                closeViewer();
                document.removeEventListener("keydown", onEsc);
            }
        });
    }

    /* ── Export ──────────────────────────────────────────────────── */
    return { render: render };
})();

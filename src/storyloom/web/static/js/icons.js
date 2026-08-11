/* ═══════════════════════════════════════════════════════════════════
   icons.js — Shared SVG icons (Feather-style: 24×24, 1.5px stroke)

   All icons follow Feather design principles: viewBox="0 0 24 24",
   fill="none", stroke="currentColor", stroke-width="2",
   stroke-linecap="round", stroke-linejoin="round".

   Exports (on window): Icons.{name}() → HTML string

   Authority: 2026-08-10-frontend-redesign.md §5.3
   ═══════════════════════════════════════════════════════════════════ */

(function () {
    "use strict";

    var I = {};

    /* ── Navigation ──────────────────────────────────────────────── */

    I.arrowLeft = function () {
        return '<svg viewBox="0 0 24 24" width="20" height="20" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M19 12H5m0 0l6-6m-6 6l6 6"/></svg>';
    };

    I.arrowUp = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M12 19V5m0 0l-6 6m6-6l6 6"/></svg>';
    };

    /* ── Actions ─────────────────────────────────────────────────── */

    I.pencil = function () {
        return '<svg viewBox="0 0 24 24" width="16" height="16" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>';
    };

    I.checkmark = function () {
        return '<svg viewBox="0 0 24 24" width="16" height="16" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M20 6L9 17l-5-5"/></svg>';
    };

    I.x = function () {
        return '<svg viewBox="0 0 24 24" width="16" height="16" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M18 6L6 18M6 6l12 12"/></svg>';
    };

    I.gear = function () {
        return '<svg viewBox="0 0 24 24" width="20" height="20" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<circle cx="12" cy="12" r="3"/>'
            + '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';
    };

    I.trash = function () {
        return '<svg viewBox="0 0 24 24" width="16" height="16" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<polyline points="3 6 5 6 21 6"/>'
            + '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
            + '<line x1="10" y1="11" x2="10" y2="17"/>'
            + '<line x1="14" y1="11" x2="14" y2="17"/></svg>';
    };

    /* ── Theme ───────────────────────────────────────────────────── */

    I.sun = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<circle cx="12" cy="12" r="5"/>'
            + '<path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>';
    };

    I.moon = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';
    };

    I.halfMoon = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<circle cx="12" cy="12" r="10"/>'
            + '<path d="M12 2a10 10 0 0 1 0 20V2z"/></svg>';
    };

    /* ── Settings Sidebar ────────────────────────────────────────── */

    I.globe = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<circle cx="12" cy="12" r="10"/>'
            + '<path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>';
    };

    I.key = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>';
    };

    I.image = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>'
            + '<circle cx="8.5" cy="8.5" r="1.5"/>'
            + '<path d="M21 15l-5-5L5 21"/></svg>';
    };

    I.palette = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<circle cx="12" cy="12" r="10"/>'
            + '<path d="M12 2a10 10 0 0 1 0 20c-1.5 0-2.5-1-2.5-2.5 0-.6.2-1.1.5-1.5.3-.4.5-.9.5-1.5 0-1-1-1.5-2-1.5-3 0-5.5-2-5.5-5A7.5 7.5 0 0 1 12 2z"/>'
            + '<circle cx="8.5" cy="9" r="1.5" fill="currentColor" stroke="none"/>'
            + '<circle cx="15.5" cy="8" r="1.5" fill="currentColor" stroke="none"/>'
            + '<circle cx="8.5" cy="15" r="1.5" fill="currentColor" stroke="none"/>'
            + '<circle cx="15.5" cy="14" r="1.5" fill="currentColor" stroke="none"/></svg>';
    };

    I.book = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
            + '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>';
    };

    I.heart = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>';
    };

    I.info = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<circle cx="12" cy="12" r="10"/>'
            + '<line x1="12" y1="16" x2="12" y2="12"/>'
            + '<line x1="12" y1="8" x2="12.01" y2="8"/></svg>';
    };

    I.users = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>'
            + '<circle cx="9" cy="7" r="4"/>'
            + '<path d="M23 21v-2a4 4 0 0 0-3-3.87"/>'
            + '<path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>';
    };

    I.refresh = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M23 4v6h-6M1 20v-6h6"/>'
            + '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>';
    };

    /* ── Card-specific (not reused from section headings) ───────── */

    I.language = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20z"/>'
            + '<path d="M2 12h20"/>'
            + '<path d="M12 2a13.5 13.5 0 0 1 3.5 9 13.5 13.5 0 0 1-3.5 9 13.5 13.5 0 0 1-3.5-9A13.5 13.5 0 0 1 12 2z"/></svg>';
    };

    I.gamepad = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<line x1="6" y1="11" x2="10" y2="11"/>'
            + '<line x1="8" y1="9" x2="8" y2="13"/>'
            + '<line x1="15" y1="12" x2="15.01" y2="12"/>'
            + '<line x1="18" y1="10" x2="18.01" y2="10"/>'
            + '<path d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5z"/></svg>';
    };

    I.sparkle = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M12 3l1.5 5.5L19 10l-5.5 1.5L12 17l-1.5-5.5L5 10l5.5-1.5z"/>'
            + '<path d="M18 14l.7 2.8L21 17l-2.3.7L18 20l-.7-2.3L15 17l2.3-.7z"/></svg>';
    };

    I.scissors = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<circle cx="6" cy="6" r="3"/>'
            + '<circle cx="6" cy="18" r="3"/>'
            + '<line x1="20" y1="4" x2="8.12" y2="15.88"/>'
            + '<line x1="8.12" y1="8.12" x2="20" y2="20"/></svg>';
    };

    I.server = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<rect x="2" y="2" width="20" height="8" rx="2" ry="2"/>'
            + '<rect x="2" y="14" width="20" height="8" rx="2" ry="2"/>'
            + '<line x1="6" y1="6" x2="6.01" y2="6"/>'
            + '<line x1="6" y1="18" x2="6.01" y2="18"/></svg>';
    };

    I.monitor = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<rect x="2" y="3" width="20" height="14" rx="2" ry="2"/>'
            + '<line x1="8" y1="21" x2="16" y2="21"/>'
            + '<line x1="12" y1="17" x2="12" y2="21"/></svg>';
    };

    I.download = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>'
            + '<polyline points="7 10 12 15 17 10"/>'
            + '<line x1="12" y1="15" x2="12" y2="3"/></svg>';
    };

    /* ── Media Controls ──────────────────────────────────────────── */

    I.play = function () {
        return '<svg viewBox="0 0 24 24" width="16" height="16" '
            + 'fill="currentColor" stroke="none">'
            + '<path d="M8 5v14l11-7z"/></svg>';
    };

    I.pause = function () {
        return '<svg viewBox="0 0 24 24" width="16" height="16" '
            + 'fill="currentColor" stroke="none">'
            + '<rect x="6" y="4" width="4" height="16"/>'
            + '<rect x="14" y="4" width="4" height="16"/></svg>';
    };

    /* ── Misc ────────────────────────────────────────────────────── */

    I.cpu = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<rect x="4" y="4" width="16" height="16" rx="2" ry="2"/>'
            + '<rect x="9" y="9" width="6" height="6"/>'
            + '<line x1="9" y1="1" x2="9" y2="4"/>'
            + '<line x1="15" y1="1" x2="15" y2="4"/>'
            + '<line x1="9" y1="20" x2="9" y2="23"/>'
            + '<line x1="15" y1="20" x2="15" y2="23"/>'
            + '<line x1="20" y1="9" x2="23" y2="9"/>'
            + '<line x1="20" y1="14" x2="23" y2="14"/>'
            + '<line x1="1" y1="9" x2="4" y2="9"/>'
            + '<line x1="1" y1="14" x2="4" y2="14"/></svg>';
    };

    I.branch = function () {
        return '<svg viewBox="0 0 24 24" width="18" height="18" '
            + 'fill="none" stroke="currentColor" stroke-width="2" '
            + 'stroke-linecap="round" stroke-linejoin="round">'
            + '<line x1="6" y1="3" x2="6" y2="15"/>'
            + '<circle cx="18" cy="6" r="3"/>'
            + '<circle cx="6" cy="18" r="3"/>'
            + '<path d="M18 9a9 9 0 0 1-9 9"/></svg>';
    };

    /* ── Exports ─────────────────────────────────────────────────── */

    window.Icons = I;
})();

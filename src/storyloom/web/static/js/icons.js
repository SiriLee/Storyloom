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

    /* ── Brand ────────────────────────────────────────────────────── */

    /* Program logo (assets/branding/logo.svg). Single-path mark using
       fill="currentColor" so it inherits the CSS accent color via
       color: var(--text-accent). */
    I.logo = function () {
        return '<svg viewBox="0 0 250 250" role="img" aria-label="Storyloom">'
            + '<path d="M 115.8 88.3 L 112.4 87.7 L 109.9 84.7 L 108.4 81.2 L 106.7 77.9 L 105.0 74.5 L 103.4 71.2 L 101.7 67.8 L 99.3 64.7 L 96.0 62.8 L 92.1 62.5 L 88.1 62.5 L 84.0 62.5 L 80.0 62.5 L 75.9 62.5 L 71.8 62.5 L 67.9 62.1 L 64.4 61.0 L 61.0 59.2 L 58.1 56.6 L 55.9 53.4 L 54.4 50.0 L 53.6 46.3 L 53.5 42.3 L 53.5 38.3 L 53.5 34.1 L 53.4 30.1 L 53.5 26.1 L 54.1 22.3 L 55.3 18.7 L 57.2 15.4 L 59.9 12.6 L 63.2 10.6 L 66.7 9.2 L 70.4 8.5 L 74.5 8.4 L 78.6 8.5 L 82.6 8.5 L 86.7 8.5 L 90.7 8.5 L 94.8 8.5 L 98.8 8.5 L 102.9 8.5 L 106.9 8.5 L 111.0 8.5 L 115.0 8.5 L 119.1 8.5 L 123.1 8.5 L 127.2 8.5 L 131.2 8.5 L 135.3 8.5 L 139.3 8.5 L 143.4 8.5 L 147.5 8.5 L 151.5 8.5 L 155.5 8.5 L 159.5 8.7 L 163.3 9.4 L 166.7 11.0 L 169.8 13.3 L 172.3 16.2 L 174.1 19.6 L 175.1 23.3 L 175.5 27.1 L 175.5 31.1 L 175.5 35.2 L 175.6 39.3 L 175.5 43.3 L 175.1 47.2 L 174.2 50.9 L 172.6 54.3 L 170.2 57.4 L 167.1 59.7 L 163.7 61.4 L 160.1 62.3 L 156.2 62.6 L 152.0 62.5 L 148.0 62.5 L 144.0 62.6 L 139.9 62.5 L 135.8 62.4 L 132.0 63.2 L 129.0 65.5 L 126.8 68.6 L 125.2 72.1 L 123.6 75.4 L 121.8 78.7 L 119.9 82.0 L 118.1 85.4 L 115.8 88.3 Z M 115.2 74.7 L 116.8 72.2 L 118.1 69.3 L 119.5 66.4 L 121.1 63.6 L 123.1 61.1 L 125.3 59.0 L 127.9 57.1 L 130.8 55.9 L 134.1 55.5 L 137.5 55.5 L 140.9 55.5 L 144.3 55.5 L 147.8 55.5 L 151.2 55.5 L 154.6 55.6 L 157.9 55.4 L 161.1 54.6 L 164.0 53.2 L 166.1 51.0 L 167.2 48.1 L 167.6 44.7 L 167.6 41.2 L 167.5 37.8 L 167.4 34.5 L 167.5 31.0 L 167.6 27.6 L 167.5 24.2 L 166.7 21.1 L 164.8 18.5 L 162.1 16.9 L 159.1 16.0 L 155.9 15.6 L 152.5 15.5 L 149.1 15.5 L 145.6 15.5 L 142.2 15.5 L 138.8 15.5 L 135.4 15.5 L 132.0 15.5 L 128.5 15.5 L 125.1 15.5 L 121.7 15.5 L 118.3 15.5 L 114.9 15.5 L 111.5 15.5 L 108.0 15.5 L 104.6 15.5 L 101.2 15.5 L 97.8 15.5 L 94.4 15.5 L 91.0 15.5 L 87.5 15.5 L 84.1 15.4 L 80.7 15.4 L 77.3 15.5 L 73.9 15.6 L 70.5 15.7 L 67.4 16.3 L 64.7 18.1 L 62.5 20.4 L 61.2 23.3 L 60.6 26.5 L 60.5 29.9 L 60.5 33.3 L 60.5 36.7 L 60.5 40.1 L 60.5 43.5 L 61.0 46.7 L 62.1 49.8 L 63.9 52.3 L 66.5 54.1 L 69.7 54.9 L 72.9 55.3 L 76.2 55.5 L 79.6 55.6 L 83.1 55.5 L 86.5 55.5 L 90.0 55.4 L 93.4 55.5 L 96.7 55.7 L 99.8 56.4 L 102.5 58.2 L 105.0 60.4 L 107.2 62.9 L 109.0 65.6 L 110.5 68.4 L 111.9 71.2 L 113.3 74.3 L 115.2 74.7 Z M 129.8 35.4 L 129.6 36.7 L 128.9 37.9 L 127.9 38.8 L 126.7 39.3 L 125.3 39.4 L 124.0 39.1 L 122.9 38.4 L 122.1 37.3 L 121.6 36.0 L 121.6 34.7 L 122.1 33.4 L 122.9 32.3 L 124.0 31.6 L 125.3 31.3 L 126.7 31.4 L 127.9 31.9 L 128.9 32.8 L 129.6 34.0 L 129.8 35.4 Z M 85.2 35.6 L 85.0 37.0 L 84.3 38.2 L 83.3 39.1 L 82.1 39.6 L 80.7 39.7 L 79.4 39.4 L 78.3 38.7 L 77.4 37.6 L 77.0 36.3 L 77.0 35.0 L 77.4 33.7 L 78.3 32.6 L 79.4 31.9 L 80.7 31.5 L 82.1 31.6 L 83.3 32.2 L 84.3 33.1 L 85.0 34.3 L 85.2 35.6 Z M 107.1 36.0 L 106.9 37.3 L 106.3 38.5 L 105.3 39.4 L 104.1 39.9 L 102.7 40.0 L 101.4 39.7 L 100.3 39.0 L 99.5 37.9 L 99.0 36.6 L 99.0 35.3 L 99.5 34.0 L 100.3 33.0 L 101.4 32.2 L 102.7 31.9 L 104.1 32.0 L 105.3 32.5 L 106.3 33.5 L 106.9 34.6 L 107.1 36.0 Z M 152.2 36.0 L 151.9 37.3 L 151.3 38.5 L 150.3 39.4 L 149.0 40.0 L 147.7 40.1 L 146.3 39.8 L 145.2 39.0 L 144.3 37.9 L 143.9 36.6 L 143.9 35.3 L 144.3 34.0 L 145.2 32.9 L 146.3 32.1 L 147.7 31.8 L 149.0 31.9 L 150.3 32.5 L 151.3 33.4 L 151.9 34.6 L 152.2 36.0 Z M 101.7 248.9 L 95.7 242.1 L 88.9 236.1 L 81.4 231.8 L 73.4 228.6 L 65.1 226.5 L 56.3 225.1 L 47.4 224.4 L 38.0 224.5 L 29.0 225.0 L 20.0 225.8 L 11.6 225.2 L 8.2 217.2 L 5.3 209.2 L 2.8 201.0 L 4.9 192.8 L 7.6 184.7 L 10.3 176.5 L 13.0 168.3 L 15.4 160.1 L 18.2 151.9 L 20.9 143.8 L 23.6 135.7 L 26.1 127.4 L 28.7 119.2 L 31.5 111.1 L 34.2 102.9 L 36.8 94.7 L 43.5 89.9 L 51.8 87.6 L 60.6 86.5 L 69.9 86.4 L 78.8 87.2 L 87.1 89.8 L 94.8 93.6 L 102.1 98.2 L 109.1 103.6 L 116.0 107.6 L 122.6 101.1 L 129.8 96.2 L 137.3 91.7 L 145.3 88.7 L 153.8 86.8 L 162.9 86.4 L 172.1 86.7 L 180.7 88.5 L 188.9 91.0 L 195.9 90.8 L 202.8 84.8 L 209.7 79.0 L 216.6 73.4 L 223.6 67.9 L 230.8 62.8 L 238.0 58.0 L 244.5 59.4 L 244.3 68.8 L 243.5 77.7 L 242.5 86.6 L 241.2 95.3 L 237.5 103.1 L 231.6 109.8 L 224.7 115.5 L 217.8 121.3 L 211.1 127.4 L 205.2 134.0 L 207.6 142.0 L 210.1 150.2 L 212.6 158.4 L 215.4 166.6 L 218.1 174.7 L 220.8 182.9 L 223.2 191.1 L 226.0 199.3 L 224.4 207.4 L 221.5 215.5 L 218.5 223.7 L 210.9 226.2 L 201.9 225.3 L 193.0 224.6 L 183.7 224.4 L 174.6 224.9 L 165.8 226.0 L 157.2 227.8 L 149.2 230.8 L 141.7 235.0 L 134.7 240.6 L 128.6 247.4 L 120.3 252.0 L 110.1 252.6 L 101.7 248.9 Z M 160.5 168.0 L 165.2 166.4 L 169.2 164.2 L 172.1 160.2 L 174.9 156.1 L 177.9 152.2 L 180.8 148.2 L 184.2 144.4 L 187.6 140.6 L 190.8 136.8 L 194.3 133.0 L 198.1 129.4 L 201.8 126.0 L 205.6 122.6 L 209.4 119.2 L 213.2 115.8 L 217.0 112.5 L 220.8 109.3 L 224.6 105.9 L 228.3 102.2 L 231.9 98.5 L 234.0 94.2 L 235.1 89.5 L 235.5 84.4 L 235.8 79.3 L 236.6 74.6 L 236.4 69.2 L 233.7 69.3 L 229.6 72.4 L 225.8 75.5 L 221.8 78.5 L 217.9 81.6 L 214.1 84.9 L 210.2 88.1 L 206.4 91.3 L 202.5 94.6 L 198.7 97.9 L 195.0 101.5 L 191.3 105.0 L 187.3 108.0 L 183.7 111.8 L 180.0 115.5 L 176.3 119.1 L 172.9 122.9 L 169.6 126.7 L 166.2 130.5 L 162.9 134.3 L 160.1 138.3 L 157.2 142.3 L 154.6 146.5 L 152.9 150.7 L 152.3 156.1 L 153.2 160.9 L 155.8 160.3 L 158.3 155.9 L 160.9 151.8 L 163.6 147.8 L 166.5 143.7 L 169.5 139.8 L 172.5 135.9 L 175.8 132.0 L 178.9 128.1 L 182.2 124.3 L 185.8 120.6 L 189.5 117.0 L 193.2 113.3 L 196.9 109.7 L 200.6 106.3 L 204.6 103.1 L 208.4 100.0 L 212.5 97.7 L 215.9 101.1 L 213.8 104.9 L 209.8 108.2 L 206.1 111.5 L 202.3 114.9 L 198.4 118.1 L 194.7 121.7 L 191.1 125.5 L 187.7 129.2 L 184.4 133.0 L 181.2 136.9 L 177.9 140.7 L 174.9 144.7 L 172.0 148.7 L 169.2 152.7 L 166.3 156.7 L 163.8 160.8 L 161.2 165.1 L 160.5 168.0 Z M 109.8 213.7 L 110.8 211.3 L 110.8 206.8 L 110.5 201.6 L 110.3 196.7 L 110.3 192.3 L 110.5 188.1 L 110.6 183.8 L 110.6 179.4 L 110.6 174.9 L 110.5 170.4 L 110.5 165.8 L 110.5 161.3 L 110.4 156.8 L 110.5 152.3 L 110.5 147.9 L 110.5 143.5 L 110.5 139.0 L 110.5 134.6 L 110.4 130.1 L 110.4 125.6 L 110.7 121.0 L 110.4 116.7 L 108.4 113.0 L 105.3 109.9 L 102.0 107.0 L 98.6 104.3 L 95.2 101.9 L 91.7 99.7 L 88.0 97.8 L 84.1 96.3 L 80.1 95.0 L 75.9 94.1 L 71.7 93.6 L 67.4 93.4 L 63.0 93.5 L 58.7 93.9 L 54.3 94.4 L 49.9 95.0 L 46.0 96.2 L 43.6 99.2 L 41.9 102.9 L 40.4 106.8 L 39.1 110.7 L 37.9 114.6 L 36.7 118.6 L 35.5 122.6 L 34.3 126.5 L 33.0 130.5 L 31.7 134.4 L 30.4 138.4 L 29.0 142.3 L 27.7 146.3 L 26.4 150.2 L 25.1 154.1 L 23.8 158.1 L 22.6 162.0 L 21.4 165.9 L 20.3 169.8 L 19.0 173.8 L 17.7 177.7 L 16.3 181.8 L 14.7 185.8 L 13.2 189.8 L 12.5 193.4 L 13.4 196.0 L 17.0 196.4 L 21.3 195.9 L 25.8 195.4 L 30.2 195.0 L 34.6 194.7 L 39.0 194.5 L 43.4 194.5 L 47.8 194.6 L 52.2 194.8 L 56.5 195.1 L 60.8 195.6 L 65.0 196.2 L 69.2 196.9 L 73.3 197.8 L 77.4 198.8 L 81.4 199.9 L 85.3 201.2 L 89.1 202.7 L 92.9 204.4 L 96.6 206.4 L 100.2 208.5 L 103.8 211.0 L 107.2 213.2 L 109.8 213.7 Z M 119.6 214.4 L 124.1 211.6 L 129.1 208.0 L 134.0 205.5 L 139.2 203.1 L 144.5 200.9 L 150.0 199.2 L 155.6 197.9 L 161.3 196.8 L 167.1 195.9 L 173.0 195.1 L 179.0 194.7 L 185.0 194.5 L 191.1 194.6 L 197.2 194.9 L 203.1 195.3 L 209.1 196.0 L 215.0 196.4 L 216.8 193.3 L 214.6 187.4 L 212.8 182.0 L 211.1 176.7 L 209.3 171.3 L 207.4 165.8 L 205.7 160.4 L 204.0 155.0 L 202.3 149.5 L 200.6 143.9 L 198.3 140.5 L 193.9 144.5 L 189.9 149.0 L 186.0 153.7 L 182.4 158.2 L 179.0 163.0 L 175.8 168.0 L 171.7 171.5 L 166.4 173.4 L 160.6 175.2 L 155.5 177.7 L 152.0 181.5 L 149.3 187.0 L 145.5 191.4 L 141.8 188.7 L 142.6 183.4 L 146.1 178.2 L 147.2 172.7 L 146.6 167.0 L 145.7 161.1 L 145.4 155.1 L 146.0 149.2 L 147.8 143.7 L 150.7 138.7 L 154.2 134.0 L 157.9 129.4 L 161.6 124.8 L 165.4 120.2 L 169.6 115.7 L 174.0 111.4 L 178.5 107.2 L 182.8 102.7 L 185.2 98.0 L 179.9 95.6 L 174.3 94.4 L 168.5 93.7 L 162.3 93.4 L 156.2 93.6 L 150.4 94.5 L 144.9 96.2 L 139.7 98.4 L 134.8 101.3 L 130.0 104.6 L 125.3 108.4 L 121.2 112.7 L 118.6 117.8 L 118.3 123.8 L 118.6 130.1 L 118.6 136.3 L 118.5 142.4 L 118.5 148.6 L 118.5 154.7 L 118.5 160.9 L 118.5 167.1 L 118.5 173.2 L 118.5 179.4 L 118.5 185.6 L 118.5 191.8 L 118.5 197.9 L 118.6 204.0 L 118.3 210.6 L 119.6 214.4 Z M 122.3 242.5 L 126.5 239.4 L 130.1 235.4 L 134.0 231.7 L 138.2 228.8 L 142.7 226.4 L 147.2 224.3 L 151.8 222.4 L 156.5 220.9 L 161.4 219.6 L 166.4 218.7 L 171.5 218.0 L 176.8 217.5 L 182.1 217.3 L 187.5 217.3 L 192.9 217.5 L 198.3 217.7 L 203.5 218.1 L 208.8 218.4 L 213.2 217.0 L 214.7 212.2 L 216.9 207.2 L 215.7 204.1 L 211.1 203.2 L 205.8 202.7 L 200.3 202.5 L 195.0 202.3 L 189.8 202.0 L 184.7 201.9 L 179.5 202.0 L 174.2 202.3 L 169.0 202.9 L 163.8 203.6 L 158.8 204.5 L 154.0 205.6 L 149.1 207.0 L 144.4 208.6 L 139.7 210.6 L 135.3 212.8 L 131.0 215.4 L 126.9 218.4 L 122.9 221.7 L 118.7 225.3 L 114.4 227.5 L 110.2 225.1 L 106.1 221.5 L 102.0 218.2 L 97.8 215.3 L 93.4 212.8 L 89.0 210.6 L 84.4 208.7 L 79.7 207.0 L 74.9 205.6 L 69.9 204.5 L 64.9 203.6 L 59.7 202.9 L 54.5 202.4 L 49.3 202.1 L 44.1 201.9 L 38.9 201.8 L 33.7 202.2 L 28.5 202.6 L 23.0 202.8 L 17.7 203.0 L 13.0 204.1 L 12.1 207.4 L 13.9 212.7 L 15.9 217.0 L 20.5 218.5 L 25.7 218.3 L 30.9 217.7 L 36.3 217.4 L 41.7 217.2 L 47.2 217.3 L 52.5 217.6 L 57.7 218.0 L 62.8 218.7 L 67.8 219.6 L 72.7 220.8 L 77.5 222.3 L 82.1 224.1 L 86.6 226.4 L 90.9 229.0 L 95.1 232.1 L 98.9 235.7 L 102.7 239.5 L 106.9 242.5 L 111.9 243.7 L 117.3 243.7 L 122.3 242.5 Z" fill="currentColor" fill-rule="evenodd"/></svg>';
    };

    /* ── Exports ─────────────────────────────────────────────────── */

    window.Icons = I;
})();

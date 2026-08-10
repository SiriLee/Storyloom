# Frontend Redesign — Dark/Light Theme + Settings Refactor

**Date:** 2026-08-10  
**Status:** Approved  
**Scope:** Theme system, settings page, API docs integration, icon refresh

## 1. Design Decisions

| Decision | Choice |
|----------|--------|
| Layout | Left sidebar + right content cards |
| Visual style | Modern minimal — clean, generous whitespace, large border-radius |
| Color accent | Green (`#3fb950` dark, `#228b22` light) |
| API docs | Integrated into Settings sidebar as "API Guide" nav item |
| Theme toggle | Appearance panel (System/Dark/Light) + global quick-toggle icon in all topbars |

## 2. Theme System

### 2.1 CSS Variable Architecture

Three-layer variable system:

```
:root           — theme-agnostic: fonts, spacing, border-radius, shadows, transitions
[data-theme="dark"]  — dark color tokens
[data-theme="light"] — light color tokens
@media (prefers-color-scheme: dark) — applied ONLY when data-theme="system"
```

The `<html>` element carries `data-theme` attribute: `"system"` | `"dark"` | `"light"`.

### 2.2 Color Palette

#### Dark Theme (`[data-theme="dark"]`)

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#0d1117` | Page background |
| `--bg-secondary` | `#161b22` | Card / panel / sidebar background |
| `--bg-tertiary` | `#21262d` | Hover states, selected nav items |
| `--text-primary` | `#e6edf3` | Body text |
| `--text-secondary` | `#8b949e` | Labels, muted text |
| `--text-accent` | `#3fb950` | Active nav, buttons, headings, links |
| `--text-warning` | `#d29922` | Warning / generating state |
| `--text-error` | `#f85149` | Errors, destructive actions |
| `--border-color` | `#21262d` | Borders, dividers |
| `--button-bg` | `#21262d` | Button background |
| `--button-hover` | `#30363d` | Button hover |
| `--overlay-bg` | `rgba(0, 0, 0, 0.6)` | Modal overlay |

#### Light Theme (`[data-theme="light"]`)

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-primary` | `#ffffff` | Page background |
| `--bg-secondary` | `#f6f8fa` | Card / panel / sidebar background |
| `--bg-tertiary` | `#eaeef2` | Hover states, selected nav items |
| `--text-primary` | `#1a1a2e` | Body text |
| `--text-secondary` | `#656d76` | Labels, muted text |
| `--text-accent` | `#228b22` | Active nav, buttons, headings, links |
| `--text-warning` | `#9a6700` | Warning / generating state |
| `--text-error` | `#cf222e` | Errors, destructive actions |
| `--border-color` | `#d0d7de` | Borders, dividers |
| `--button-bg` | `#f6f8fa` | Button background |
| `--button-hover` | `#eaeef2` | Button hover |
| `--overlay-bg` | `rgba(0, 0, 0, 0.4)` | Modal overlay |

### 2.3 Theme-Agnostic Tokens (in `:root`)

These do NOT change between themes:

- Typography: `--font-mono`, `--font-serif`, `--font-sans`, `--font-xs`…`--font-4xl`
- Spacing: `--space-xs`…`--space-3xl`
- Layout: `--content-width`, `--choices-width`, `--icon-btn-size`
- Border radius: `--radius-sm`…`--radius-round`
- Transitions: `--trans-fast`, `--trans-normal`, `--trans-slow`
- Shadows: `--shadow-glow`, `--shadow-modal`, `--shadow-toast`, `--shadow-focus`

### 2.4 Theme Persistence

1. On load: read `localStorage["storyloom-theme"]` → apply `data-theme`
2. Default: `"system"` (follows `prefers-color-scheme`)
3. On change: update `data-theme` + save to localStorage
4. OS change listener: `matchMedia('(prefers-color-scheme: dark)').addEventListener('change', ...)` — only effective when theme is `"system"`

## 3. Settings Page Redesign

### 3.1 Layout

```
┌──────────────────────────────────────────────────┐
│ ← Back to Menu          Settings                 │
├──────────┬───────────────────────────────────────┤
│ SETTINGS │                                       │
│          │  ┌─────────────────────────────────┐  │
│ ● General│  │  Section Title                  │  │
│   API    │  │                                 │  │
│   Image  │  │  ┌─────────────────────────────┐│  │
│   Appear.│  │  │ Setting Row                 ││  │
│          │  │  │ Setting Row                 ││  │
│ ──────── │  │  │ Setting Row                 ││  │
│ API Guide│  │  └─────────────────────────────┘│  │
│ Credits  │  │                                 │  │
│ Updates  │  └─────────────────────────────────┘  │
│          │                                       │
└──────────┴───────────────────────────────────────┘
```

- **Sidebar**: fixed 200px width, vertical nav with icon + label per item
- **Content**: flex 1, scrollable, each section rendered as a bordered card
- **Active section**: highlighted with green accent background + green text
- **Divider**: between main settings groups and secondary items (API Guide, Credits, Updates)

### 3.2 Sidebar Navigation Structure

| Section | Icon | Content |
|---------|------|---------|
| General | globe | Language, Game Mode |
| API | key | API Base URL, API Key, Model |
| Image | image | Image Generation toggle, Image API URL, Image API Key, Image Model, Sprite Cutout |
| Appearance | palette | Theme, Font Size (if narrative view needs it) |
| — | (divider) | — |
| API Guide | book | Full API setup documentation (marked.js rendered) |
| Credits | heart | Developer/contributor credits |
| Updates | refresh | Version check, update download |

### 3.3 Settings Row Types

Each row inside a section card:

```
Label                        Value / Control
─────────────────────────────────────────────
```

- **text/password**: label left, value right, ✎ edit button → inline input with ✓/✕
- **select**: label left, `<select>` right
- **toggle**: label left, iOS-style toggle switch right
- **segmented**: label left, segmented button group right (for Theme)

### 3.4 Behavior

- Click sidebar item → scroll/switch right panel (no page reload)
- Settings auto-save on change (already implemented via `applySetting()`)
- Group collapse/expand retained from current implementation (Image Generation off → hide image group)
- Back button top-left → `#menu`

## 4. API Documentation Integration

### 4.1 Current State

`help.html` is a standalone HTML page served at `GET /help`. It has its own hardcoded dark theme CSS, separate from the SPA.

### 4.2 Target State

- `help.html` content converted to a JS string module (Markdown source)
- Rendered via `marked.js` (already loaded in the SPA) inside the settings right panel
- Accessible via Settings sidebar → "API Guide"
- Inherits the active theme (dark/light) from the SPA
- `/help` route removed from server.py

### 4.3 Content Structure

The API guide covers:
1. Overview — two API services
2. Text API (LLM) — quality requirements, model recommendations, providers
3. Image API — model families, recommendations, providers
4. API aggregation platforms — comparison table
5. Background removal — U²-Net modes
6. Troubleshooting — common errors and fixes
7. Official links & references

## 5. Global Theme Toggle Icon

### 5.1 Placement

In every view's topbar, right side:
- **Game view**: next to mode toggle and settings gear
- **Co-create view**: in the header bar
- **Settings view**: in the header bar
- **Save browser / Adventure log / Asset manager**: in the header bar

### 5.2 Icon Design

- Dark theme active → show ☀️ (sun) icon → click to switch to light
- Light theme active → show 🌙 (moon) icon → click to switch to dark
- System theme active → show ◐ (half-moon) icon
- Click behavior: System → Dark → Light → System (cycle)

### 5.3 SVG Icons

All icons re-designed as simple geometric SVGs (no emoji). Feather-style: 24×24 viewBox, 1.5px stroke, round caps/joins.

## 6. Narrative View Theme Adaptation

No layout changes. Color variables auto-adapt:

- `.game-story` background → `--bg-primary`
- `.game-segment` text → `--text-primary`
- `.game-choice-btn` → `--bg-secondary` + `--border-color`
- `.game-choice-btn:hover` → `--button-hover` + `--text-accent` border
- `.game-choices` gradient → uses `--bg-primary`
- `.game-label` → `--text-accent`
- Topbar → `--bg-primary`
- Modal → `--bg-secondary` + `--overlay-bg`

## 7. Implementation Strategy

### 7.1 Branch

New branch: `refactor/frontend-redesign`

### 7.2 CSS Refactoring (main.css → split)

| File | Purpose |
|------|---------|
| `static/css/variables.css` | `:root` theme-agnostic tokens |
| `static/css/theme-dark.css` | `[data-theme="dark"]` color tokens |
| `static/css/theme-light.css` | `[data-theme="light"]` color tokens |
| `static/css/main.css` | All component styles (uses variables) |
| `static/css/graph.css` | VN styles (uses variables, no layout changes) |

`index.html` loads: `variables.css` → `theme-dark.css` → `theme-light.css` → `main.css` → `graph.css`

### 7.3 JS Changes

| File | Change |
|------|--------|
| `state.js` | Add `ThemeState` object: `current`, `init()`, `set()`, `cycle()` |
| `router.js` | Rewrite `renderSettings()` with sidebar layout; add API guide renderer |
| `icons.js` | Add sun/moon/half-moon SVG icons; refresh existing icons |
| `display.js` | Add theme toggle button to game topbar |
| `game.js` | Wire theme toggle button in topbar |
| `co-create.js` | Add theme toggle to cc-header |
| NEW `api-guide.js` | API doc Markdown content as JS string |
| `index.html` | Add new CSS files, add api-guide.js |

### 7.4 Server Changes

| Change | Purpose |
|--------|---------|
| Remove `GET /help` route | API docs now in SPA |

### 7.5 Test Strategy

- Manual visual verification: dark mode, light mode, system mode
- Verify all views render correctly in both themes
- Verify settings save/load across theme changes
- Verify API guide content matches current help.html
- `pytest` to confirm no backend regressions

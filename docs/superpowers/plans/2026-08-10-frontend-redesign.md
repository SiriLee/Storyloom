# Frontend Redesign — Dark/Light Theme + Settings Refactor Implementation Plan

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为 Storyloom Web 前端添加深色/浅色主题系统，重构 Settings 页面为侧边栏+内容布局，将 API 指南文档整合进 SPA。

**架构：** CSS 变量三层体系（`:root` 非主题 → `[data-theme="dark"]` → `[data-theme="light"]`），`data-theme` 属性控制主题。Settings 页左右分栏：200px 固定侧边栏 + flex 内容区。API 文档转 JS Markdown 字符串，通过 marked.js 渲染在 Settings 面板中。

**技术栈：** Vanilla JS (ES6), CSS Custom Properties, FastAPI static files, marked.js

---

## 文件结构

| 文件 | 操作 | 职责 |
|------|------|------|
| `static/css/variables.css` | **新建** | `:root` 非主题变量（字体、间距、圆角、阴影、过渡） |
| `static/css/theme-dark.css` | **新建** | `[data-theme="dark"]` 深色配色变量 |
| `static/css/theme-light.css` | **新建** | `[data-theme="light"]` 浅色配色变量 |
| `static/css/main.css` | **修改** | 移除 `:root` 颜色变量定义，保留组件样式（颜色引用改为变量） |
| `static/css/graph.css` | **修改** | 变量引用适配，VU 颜色适配浅色主题 |
| `static/js/state.js` | **修改** | 新增 `ThemeState` 对象和全局 `showToast` 主题适配 |
| `static/js/icons.js` | **修改** | 新增 sun/moon/half-moon/globe/key/image/palette/book/heart/refresh SVG 图标 |
| `static/js/router.js` | **修改** | 重写 `renderSettings()` → 侧边栏布局；新增 API Guide 渲染逻辑 |
| `static/js/api-guide.js` | **新建** | API 文档 Markdown 内容（从 help.html 提取） |
| `static/js/game.js` | **修改** | 游戏顶栏新增主题切换按钮 |
| `static/js/co-create.js` | **修改** | Co-create 顶栏新增主题切换按钮 |
| `static/js/display.js` | **修改** | 通用顶栏主题按钮工厂函数 |
| `static/js/adventure-log.js` | **修改** | 冒险日志顶栏新增主题切换按钮 |
| `static/js/assets.js` | **修改** | 资产管理顶栏新增主题切换按钮 |
| `static/index.html` | **修改** | 加载新 CSS 文件 + api-guide.js |
| `static/help.html` | **删除** | 内容迁移至 api-guide.js |
| `web/server.py` | **修改** | 删除 `GET /help` 路由 |

---

### 任务 1：CSS 变量拆分 — 创建三层主题体系

**文件：**
- 创建：`src/storyloom/web/static/css/variables.css`
- 创建：`src/storyloom/web/static/css/theme-dark.css`
- 创建：`src/storyloom/web/static/css/theme-light.css`
- 修改：`src/storyloom/web/static/index.html:7-8`

- [ ] **步骤 1：创建 `variables.css` — 非主题变量**

从当前 `main.css` 的 `:root` 块中提取所有非颜色变量，放入新文件：

```css
/* ═══════════════════════════════════════════════════════════════════
   variables.css — Theme-agnostic design tokens
   Colors live in theme-dark.css / theme-light.css.
   ═══════════════════════════════════════════════════════════════════ */

:root {
    /* ── Typography ──────────────────────────────────────────────── */
    --font-mono: "Consolas", "Courier New", monospace;
    --font-serif: "Georgia", "Noto Serif SC", serif;
    --font-sans: "Segoe UI", "PingFang SC", sans-serif;
    --font-xs: 0.8rem;
    --font-sm: 0.85rem;
    --font-base: 0.95rem;
    --font-md: 1.05rem;
    --font-lg: 1.15rem;
    --font-xl: 1.3rem;
    --font-2xl: 1.8rem;
    --font-3xl: 2.2rem;
    --font-4xl: 3.2rem;

    /* ── Spacing ─────────────────────────────────────────────────── */
    --space-xs: 0.25rem;
    --space-sm: 0.5rem;
    --space-md: 0.75rem;
    --space-lg: 1rem;
    --space-xl: 1.5rem;
    --space-2xl: 2rem;
    --space-3xl: 3rem;

    /* ── Layout ──────────────────────────────────────────────────── */
    --content-width: 960px;
    --choices-width: 420px;
    --icon-btn-size: 2.2rem;

    /* ── Border Radius ───────────────────────────────────────────── */
    --radius-sm: 4px;
    --radius-md: 6px;
    --radius-lg: 8px;
    --radius-xl: 12px;
    --radius-round: 24px;

    /* ── Transitions ─────────────────────────────────────────────── */
    --trans-fast: 0.15s ease;
    --trans-normal: 0.2s ease;
    --trans-slow: 0.3s ease;

    /* ── Shadows (theme-agnostic — use rgba with variable alpha) ─── */
    --shadow-glow: 0 0 8px rgba(63, 185, 80, 0.2);
    --shadow-glow-sm: 0 0 10px rgba(63, 185, 80, 0.15);
    --shadow-glow-lg: 0 0 12px rgba(63, 185, 80, 0.4);
    --shadow-glow-xl: 0 0 18px rgba(63, 185, 80, 0.4);
    --shadow-modal: 0 8px 32px rgba(0, 0, 0, 0.4);
    --shadow-toast: 0 4px 16px rgba(0, 0, 0, 0.3);
    --shadow-focus: 0 0 0 2px rgba(63, 185, 80, 0.35);

    /* ── Overlays ────────────────────────────────────────────────── */
    --overlay-bg-dark: rgba(0, 0, 0, 0.6);
    --overlay-bg-light: rgba(0, 0, 0, 0.4);

    interpolate-size: allow-keywords;
}

/* ── Theme-dependent overlay ────────────────────────────────────── */

[data-theme="dark"] { --overlay-bg: var(--overlay-bg-dark); }
[data-theme="light"] { --overlay-bg: var(--overlay-bg-light); }

/* System default: follow prefers-color-scheme */
@media (prefers-color-scheme: dark) {
    [data-theme="system"] { --overlay-bg: var(--overlay-bg-dark); }
}
@media (prefers-color-scheme: light) {
    [data-theme="system"] { --overlay-bg: var(--overlay-bg-light); }
}
```

- [ ] **步骤 2：创建 `theme-dark.css` — 深色配色**

```css
/* ═══════════════════════════════════════════════════════════════════
   theme-dark.css — Dark theme color tokens
   Active when [data-theme="dark"] or system-prefers-dark with "system".
   ═══════════════════════════════════════════════════════════════════ */

[data-theme="dark"] {
    --bg-primary: #0d1117;
    --bg-secondary: #161b22;
    --bg-tertiary: #21262d;
    --text-primary: #e6edf3;
    --text-secondary: #8b949e;
    --text-accent: #3fb950;
    --text-warning: #d29922;
    --text-error: #f85149;
    --border-color: #21262d;
    --button-bg: #21262d;
    --button-hover: #30363d;
    --bg-panel: rgba(22, 27, 34, 0.92);
}

/* System dark — maps to same token values */
@media (prefers-color-scheme: dark) {
    [data-theme="system"] {
        --bg-primary: #0d1117;
        --bg-secondary: #161b22;
        --bg-tertiary: #21262d;
        --text-primary: #e6edf3;
        --text-secondary: #8b949e;
        --text-accent: #3fb950;
        --text-warning: #d29922;
        --text-error: #f85149;
        --border-color: #21262d;
        --button-bg: #21262d;
        --button-hover: #30363d;
        --bg-panel: rgba(22, 27, 34, 0.92);
    }
}
```

- [ ] **步骤 3：创建 `theme-light.css` — 浅色配色**

```css
/* ═══════════════════════════════════════════════════════════════════
   theme-light.css — Light theme color tokens
   Active when [data-theme="light"] or system-prefers-light with "system".
   ═══════════════════════════════════════════════════════════════════ */

[data-theme="light"] {
    --bg-primary: #ffffff;
    --bg-secondary: #f6f8fa;
    --bg-tertiary: #eaeef2;
    --text-primary: #1a1a2e;
    --text-secondary: #656d76;
    --text-accent: #228b22;
    --text-warning: #9a6700;
    --text-error: #cf222e;
    --border-color: #d0d7de;
    --button-bg: #f6f8fa;
    --button-hover: #eaeef2;
    --bg-panel: rgba(255, 255, 255, 0.95);
}

@media (prefers-color-scheme: light) {
    [data-theme="system"] {
        --bg-primary: #ffffff;
        --bg-secondary: #f6f8fa;
        --bg-tertiary: #eaeef2;
        --text-primary: #1a1a2e;
        --text-secondary: #656d76;
        --text-accent: #228b22;
        --text-warning: #9a6700;
        --text-error: #cf222e;
        --border-color: #d0d7de;
        --button-bg: #f6f8fa;
        --button-hover: #eaeef2;
        --bg-panel: rgba(255, 255, 255, 0.95);
    }
}
```

- [ ] **步骤 4：修改 `index.html` — 加载新 CSS 文件**

将：
```html
<link rel="stylesheet" href="/static/css/main.css">
<link rel="stylesheet" href="/static/css/graph.css">
```

替换为：
```html
<link rel="stylesheet" href="/static/css/variables.css">
<link rel="stylesheet" href="/static/css/theme-dark.css">
<link rel="stylesheet" href="/static/css/theme-light.css">
<link rel="stylesheet" href="/static/css/main.css">
<link rel="stylesheet" href="/static/css/graph.css">
```

- [ ] **步骤 5：Commit**

```bash
git add src/storyloom/web/static/css/variables.css \
        src/storyloom/web/static/css/theme-dark.css \
        src/storyloom/web/static/css/theme-light.css \
        src/storyloom/web/static/index.html
git commit -m "feat: add CSS theme system — variables, dark, light layers"
```

---

### 任务 2：main.css 颜色变量迁移

**文件：**
- 修改：`src/storyloom/web/static/css/main.css:1-2694`

- [ ] **步骤 1：移除 `:root` 块中的颜色变量定义**

删除 `main.css` 第 26-97 行的 `:root` 块中所有颜色相关变量（`--bg-primary` 到 `--overlay-bg-light`），保留非颜色变量。同时删除文件头注释中的旧颜色值（第 3-19 行），更新为指向新主题文件的引用。

具体操作：将 `main.css` 第 1-97 行替换为：

```css
/* ═══════════════════════════════════════════════════════════════════
   Storyloom Web — Main Stylesheet

   Color tokens: see variables.css (agnostic), theme-dark.css, theme-light.css.
   All component styles reference CSS variables — no hardcoded colors.

   Authority: CLAUDE.md §Tech Stack, prototype reference.
   ═══════════════════════════════════════════════════════════════════ */

/* Theme-agnostic tokens + color variables loaded via variables.css + theme-*.css */

/* ── Reset & Base ───────────────────────────────────────────────── */
```

删除 `:root { ... }` 块（第 26-97 行全部移除）。

- [ ] **步骤 2：更新阴影变量引用**

`main.css` 中 `--shadow-glow` 等阴影变量使用了旧的颜色值 `rgba(78, 204, 163, ...)`。在 `variables.css` 中已用新的绿色 `rgba(63, 185, 80, ...)` 替代。无需额外修改。

- [ ] **步骤 3：更新 `.game-choices` 渐变引用**

找到 `.game-choices` 的 `background: linear-gradient(...)` 声明（约第 2074 行），确认它使用 `--bg-primary` 变量。当前代码已使用变量，无需修改。

- [ ] **步骤 4：更新 graph.css 的 `:root` 重复声明**

`graph.css:16-32` 有独立的 `:root` 块重新声明了颜色变量。需要移除这些颜色变量声明，只保留 VN 特有的 `--vn-*` 变量。

将 `graph.css` 第 16-32 行的 `:root` 块替换为：

```css
:root {
  /* Tunable VN constants — adjusted by in-game settings panel */
  --vn-font-size: 1.35rem;
  --vn-choice-gap: 1.4rem;
  --vn-dialog-height: 14rem;
  /* Static VN constants */
  --vn-sprite-max-h: 70vh;
  --vn-sprite-max-w: 45vw;
  --vn-text-max-width: 760px;
}
```

- [ ] **步骤 5：Commit**

```bash
git add src/storyloom/web/static/css/main.css \
        src/storyloom/web/static/css/graph.css
git commit -m "refactor: migrate CSS color values to theme variable system"
```

---

### 任务 3：ThemeState — JS 主题管理

**文件：**
- 修改：`src/storyloom/web/static/js/state.js`（在 `GameState` 对象之后，`SETTINGS_STORE` 之前添加）

- [ ] **步骤 1：在 `GameState` 对象后添加 `ThemeState` 对象**

在 `state.js` 第 70 行（`GameState` 对象结束 `};` 之后）插入：

```js
/* ── Theme State ──────────────────────────────────────────────────── */
/* Manages data-theme attribute on <html>.  Persisted to localStorage.
   Values: "system" (default), "dark", "light".
   The CSS variable system (theme-dark.css / theme-light.css) reacts
   to [data-theme] selectors, including @media prefers-color-scheme
   when data-theme="system".                                           */

const ThemeState = {
    _key: "storyloom-theme",
    _current: null,
    _mediaQuery: null,

    /** Get the current effective theme (resolved: "dark" or "light"). */
    get effective() {
        const attr = document.documentElement.getAttribute("data-theme") || "system";
        if (attr === "system") {
            return window.matchMedia("(prefers-color-scheme: dark)").matches
                ? "dark" : "light";
        }
        return attr;
    },

    /** Get the stored preference ("system" | "dark" | "light"). */
    get current() {
        return document.documentElement.getAttribute("data-theme") || "system";
    },

    /** Initialize: read localStorage, apply data-theme, listen for OS changes. */
    init() {
        const saved = localStorage.getItem(this._key) || "system";
        this._apply(saved);

        // Listen for OS theme changes — only matters when in "system" mode.
        this._mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
        this._mediaQuery.addEventListener("change", () => {
            if (this.current === "system") {
                // Force a style recalc by re-applying (triggers CSS re-eval).
                document.documentElement.setAttribute("data-theme", "system");
            }
        });
    },

    /** Set theme to a specific value. */
    set(value) {
        this._apply(value);
        localStorage.setItem(this._key, value);
    },

    /** Cycle: system → dark → light → system */
    cycle() {
        const order = ["system", "dark", "light"];
        const idx = order.indexOf(this.current);
        const next = order[(idx + 1) % order.length];
        this.set(next);
        return next;
    },

    /** Apply data-theme attribute to <html>. */
    _apply(value) {
        document.documentElement.setAttribute("data-theme", value);
        this._current = value;
    },
};
```

- [ ] **步骤 2：在 `initConfig()` 末尾调用 `ThemeState.init()`**

在 `initConfig()` 函数末尾（第 278 行 `}` 之前），添加：

```js
        ThemeState.init();
```

- [ ] **步骤 3：Commit**

```bash
git add src/storyloom/web/static/js/state.js
git commit -m "feat: add ThemeState — JS theme management with system/dark/light"
```

---

### 任务 4：图标系统刷新

**文件：**
- 修改：`src/storyloom/web/static/js/icons.js`

- [ ] **步骤 1：重写 `icons.js` — 新增所有图标**

将 `icons.js` 全部替换为：

```js
/* ═══════════════════════════════════════════════════════════════════
   icons.js — Shared SVG icons (Feather-style: 24×24, 1.5px stroke)

   All icons follow Feather design: viewBox="0 0 24 24", fill="none",
   stroke="currentColor", stroke-width="1.5", round caps/joins.

   Exports (on window): Icons.{name}() → HTML string
   ═══════════════════════════════════════════════════════════════════ */

(function () {
    const I = {};

    /* ── Navigation ──────────────────────────────────────────────── */

    I.arrowLeft = () =>
        '<svg viewBox="0 0 24 24" width="20" height="20" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M19 12H5m0 0l6-6m-6 6l6 6"/></svg>';

    I.arrowUp = () =>
        '<svg viewBox="0 0 24 24" width="20" height="20" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M12 19V5m0 0l-6 6m6-6l6 6"/></svg>';

    /* ── Actions ─────────────────────────────────────────────────── */

    I.pencil = () =>
        '<svg viewBox="0 0 24 24" width="16" height="16" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/></svg>';

    I.checkmark = () =>
        '<svg viewBox="0 0 24 24" width="16" height="16" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M20 6L9 17l-5-5"/></svg>';

    I.gear = () =>
        '<svg viewBox="0 0 24 24" width="20" height="20" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<circle cx="12" cy="12" r="3"/>'
        + '<path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>';

    /* ── Theme ───────────────────────────────────────────────────── */

    I.sun = () =>
        '<svg viewBox="0 0 24 24" width="18" height="18" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<circle cx="12" cy="12" r="5"/>'
        + '<path d="M12 1v2m0 18v2M4.22 4.22l1.42 1.42m12.72 12.72l1.42 1.42M1 12h2m18 0h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>';

    I.moon = () =>
        '<svg viewBox="0 0 24 24" width="18" height="18" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>';

    I.halfMoon = () =>
        '<svg viewBox="0 0 24 24" width="18" height="18" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<circle cx="12" cy="12" r="10"/>'
        + '<path d="M12 2a10 10 0 0 1 0 20V2z"/></svg>';

    /* ── Settings Sidebar ────────────────────────────────────────── */

    I.globe = () =>
        '<svg viewBox="0 0 24 24" width="18" height="18" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<circle cx="12" cy="12" r="10"/>'
        + '<path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>';

    I.key = () =>
        '<svg viewBox="0 0 24 24" width="18" height="18" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>';

    I.image = () =>
        '<svg viewBox="0 0 24 24" width="18" height="18" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>'
        + '<circle cx="8.5" cy="8.5" r="1.5"/>'
        + '<path d="M21 15l-5-5L5 21"/></svg>';

    I.palette = () =>
        '<svg viewBox="0 0 24 24" width="18" height="18" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<circle cx="12" cy="12" r="10"/>'
        + '<path d="M12 2a10 10 0 0 1 0 20c-1.5 0-2.5-1-2.5-2.5 0-.6.2-1.1.5-1.5.3-.4.5-.9.5-1.5 0-1-1-1.5-2-1.5-3 0-5.5-2-5.5-5A7.5 7.5 0 0 1 12 2z"/>'
        + '<circle cx="8.5" cy="9" r="1.5" fill="currentColor" stroke="none"/>'
        + '<circle cx="15.5" cy="8" r="1.5" fill="currentColor" stroke="none"/>'
        + '<circle cx="8.5" cy="15" r="1.5" fill="currentColor" stroke="none"/>'
        + '<circle cx="15.5" cy="14" r="1.5" fill="currentColor" stroke="none"/></svg>';

    I.book = () =>
        '<svg viewBox="0 0 24 24" width="18" height="18" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>'
        + '<path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>';

    I.heart = () =>
        '<svg viewBox="0 0 24 24" width="18" height="18" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/></svg>';

    I.refresh = () =>
        '<svg viewBox="0 0 24 24" width="18" height="18" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M23 4v6h-6M1 20v-6h6"/>'
        + '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg>';

    I.play = () =>
        '<svg viewBox="0 0 24 24" width="16" height="16" '
        + 'fill="currentColor" stroke="none">'
        + '<path d="M8 5v14l11-7z"/></svg>';

    I.pause = () =>
        '<svg viewBox="0 0 24 24" width="16" height="16" '
        + 'fill="currentColor" stroke="none">'
        + '<rect x="6" y="4" width="4" height="16"/>'
        + '<rect x="14" y="4" width="4" height="16"/></svg>';

    I.x = () =>
        '<svg viewBox="0 0 24 24" width="16" height="16" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<path d="M18 6L6 18M6 6l12 12"/></svg>';

    I.trash = () =>
        '<svg viewBox="0 0 24 24" width="16" height="16" '
        + 'fill="none" stroke="currentColor" stroke-width="1.5" '
        + 'stroke-linecap="round" stroke-linejoin="round">'
        + '<polyline points="3 6 5 6 21 6"/>'
        + '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>'
        + '<line x1="10" y1="11" x2="10" y2="17"/>'
        + '<line x1="14" y1="11" x2="14" y2="17"/></svg>';

    window.Icons = I;
})();
```

- [ ] **步骤 2：Commit**

```bash
git add src/storyloom/web/static/js/icons.js
git commit -m "feat: refresh icon system — Feather-style SVGs, add theme + sidebar icons"
```

---

### 任务 5：Settings 页 — 侧边栏布局重写

**文件：**
- 修改：`src/storyloom/web/static/js/router.js:359-582`（`renderSettings` 函数）

- [ ] **步骤 1：重写 `renderSettings()` 函数**

将 `router.js` 中第 359-582 行的 `renderSettings` 函数全部替换为侧边栏布局版本。关键变更：

```js
function renderSettings() {
    GameState.reset();
    if (typeof SSEClient !== "undefined" && SSEClient.close) {
        SSEClient.close();
    }

    // ── Sidebar section definitions ───────────────────────────────
    var sections = [
        { id: "general",  icon: "globe",   label: _("General") },
        { id: "api",      icon: "key",     label: _("API") },
        { id: "image",    icon: "image",   label: _("Image") },
        { id: "appearance", icon: "palette", label: _("Appearance") },
        { id: null,       icon: null,      label: null },  // divider
        { id: "guide",    icon: "book",    label: _("API Guide") },
        { id: "credits",  icon: "heart",   label: _("Credits") },
        { id: "updates",  icon: "refresh", label: _("Updates") },
    ];

    var currentSection = "general";

    // ── Render shell ──────────────────────────────────────────────
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
        + '<div class="settings-content" id="settings-content"></div>'
        + '</div>'
        + '</div>';

    // ── Render sidebar ────────────────────────────────────────────
    var nav = document.getElementById("settings-nav");
    nav.innerHTML = sections.map(function (s) {
        if (s.id === null) return '<div class="settings-nav-divider"></div>';
        var cls = (s.id === currentSection) ? "settings-nav-item active" : "settings-nav-item";
        return '<button class="' + cls + '" data-section="' + s.id + '">'
            + Icons[s.icon]() + '<span>' + esc(s.label) + '</span></button>';
    }).join("");

    // ── Render initial content ────────────────────────────────────
    _renderSettingsSection(currentSection);

    // ── Sidebar click → switch section ────────────────────────────
    nav.querySelectorAll(".settings-nav-item").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var sid = this.dataset.section;
            if (sid === currentSection) return;
            currentSection = sid;
            nav.querySelectorAll(".settings-nav-item").forEach(function (b) {
                b.classList.toggle("active", b.dataset.section === sid);
            });
            _renderSettingsSection(sid);
        });
    });

    // ── Back button ────────────────────────────────────────────────
    document.getElementById("settings-back").addEventListener("click", function () {
        navigate("menu");
    });

    // ── Theme toggle ───────────────────────────────────────────────
    _bindThemeToggle(document.getElementById("settings-theme-btn"));
}
```

- [ ] **步骤 2：添加 `_renderSettingsSection()` 函数**

在 `renderSettings()` 之后添加各 section 的渲染函数。每个 section 渲染为一张卡片：

```js
/** Render a settings section into #settings-content. */
function _renderSettingsSection(id) {
    var container = document.getElementById("settings-content");
    if (!container) return;

    switch (id) {
        case "general":   _renderGeneralSection(container);   break;
        case "api":       _renderApiSection(container);       break;
        case "image":     _renderImageSection(container);     break;
        case "appearance": _renderAppearanceSection(container); break;
        case "guide":     _renderApiGuideSection(container);  break;
        case "credits":   _renderCreditsSection(container);   break;
        case "updates":   _renderUpdatesSection(container);   break;
    }
}
```

每个 section 渲染函数的结构：

```js
function _renderGeneralSection(container) {
    container.innerHTML =
        '<div class="settings-card">'
        + '<div class="settings-card-title">' + esc(_("General")) + '</div>'
        + _settingSelect("lang", _("Language"), [
            { value: "zh-CN", label: "中文" },
            { value: "zh-TW", label: "繁體中文" },
            { value: "en", label: "English" },
        ])
        + _settingSelect("game_mode", _("Game Mode"), [
            { value: "text", label: _("Text") },
            { value: "graph", label: _("Graph") },
        ])
        + '</div>';
    _bindSettingsInputs(container);
}

function _renderApiSection(container) {
    container.innerHTML =
        '<div class="settings-card">'
        + '<div class="settings-card-title">' + esc(_("API Configuration")) + '</div>'
        + _settingText("api_base_url", _("API Base URL"), "https://api.deepseek.com")
        + _settingPassword("api_key", _("API Key"), "sk-...")
        + _settingText("api_model", _("Model"), "deepseek-v4-pro")
        + '</div>';
    _bindSettingsInputs(container);
}

function _renderImageSection(container) {
    var enabled = getSetting("img_generation_enabled") !== "false";
    container.innerHTML =
        '<div class="settings-card">'
        + '<div class="settings-card-title">' + esc(_("Image Generation")) + '</div>'
        + _settingToggle("img_generation_enabled", _("Image Generation"))
        + '</div>'
        + (enabled
            ? '<div class="settings-card" id="image-settings-group">'
              + _settingText("img_api_base_url", _("Image API URL"), "https://api.apiyi.com/v1")
              + _settingPassword("img_api_key", _("Image API Key"), "sk-...")
              + _settingText("img_api_model", _("Image Model"), "flux-2-pro")
              + _settingSelect("portrait_remove_bg", _("Sprite Cutout"), [
                  { value: "never", label: _("Never") },
                  { value: "auto", label: _("Auto") },
                  { value: "always", label: _("Always") },
              ])
              + '</div>'
            : "");
    _bindSettingsInputs(container);
}

function _renderAppearanceSection(container) {
    container.innerHTML =
        '<div class="settings-card">'
        + '<div class="settings-card-title">' + esc(_("Appearance")) + '</div>'
        + _settingSegmented("theme", _("Theme"), [
            { value: "system", label: _("System") },
            { value: "dark", label: _("Dark") },
            { value: "light", label: _("Light") },
        ], ThemeState.current)
        + '</div>';
    _bindSettingsInputs(container);
}
```

- [ ] **步骤 3：添加设置行工厂函数**

```js
/* ── Settings Row Factories ──────────────────────────────────────── */

/** Render a select dropdown row. */
function _settingSelect(key, label, options) {
    var current = getSetting(key);
    var opts = options.map(function (o) {
        var sel = (o.value === current) ? " selected" : "";
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
        + '<span class="' + cls + '">' + esc(display) + '</span>'
        + '<button class="settings-row-edit" title="' + esc(_("Edit")) + '">' + Icons.pencil() + '</button>'
        + '<input type="text" class="settings-row-input hidden" value="' + esc(current) + '" placeholder="' + esc(placeholder || "") + '">'
        + '</div>';
}

/** Render a password row (same as text but type=password for input). */
function _settingPassword(key, label, placeholder) {
    var current = getSetting(key);
    var display = current ? maskKey(current) : (placeholder || "");
    var cls = current ? "settings-row-value" : "settings-row-value muted";
    return '<div class="settings-row" data-key="' + esc(key) + '">'
        + '<span class="settings-row-label">' + esc(label) + '</span>'
        + '<span class="' + cls + '">' + esc(display) + '</span>'
        + '<button class="settings-row-edit" title="' + esc(_("Edit")) + '">' + Icons.pencil() + '</button>'
        + '<input type="password" class="settings-row-input hidden" value="' + esc(current) + '" placeholder="' + esc(placeholder || "") + '">'
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

/** Render a segmented control row (for theme selection). */
function _settingSegmented(key, label, options, currentVal) {
    var segs = options.map(function (o) {
        var cls = (o.value === currentVal) ? "settings-seg-btn active" : "settings-seg-btn";
        return '<button class="' + cls + '" data-value="' + esc(o.value) + '">'
            + esc(o.label) + '</button>';
    }).join("");
    return '<div class="settings-row">'
        + '<span class="settings-row-label">' + esc(label) + '</span>'
        + '<div class="settings-seg-group" data-key="' + esc(key) + '">' + segs + '</div>'
        + '</div>';
}
```

- [ ] **步骤 4：添加设置事件绑定函数**

```js
/** Bind event listeners for all settings inputs in a container. */
function _bindSettingsInputs(container) {
    if (!container) return;

    /* Select dropdowns */
    container.querySelectorAll(".settings-row-select").forEach(function (el) {
        el.addEventListener("change", function () {
            applySetting(this.dataset.key, this.value);
            // Re-render image section if generation toggle changed
            if (this.dataset.key === "img_generation_enabled" || this.dataset.key === "portrait_remove_bg") {
                _renderSettingsSection("image");
            }
            if (this.dataset.key === "lang") {
                renderSettings(); // full re-render for language change
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
                // Update active state
                group.querySelectorAll(".settings-seg-btn").forEach(function (b) {
                    b.classList.toggle("active", b.dataset.value === val);
                });
                // Theme: use ThemeState.set()
                if (group.dataset.key === "theme") {
                    ThemeState.set(val);
                    _updateAllThemeButtons();
                }
            });
        });
    });

    /* Text/password edit buttons */
    container.querySelectorAll(".settings-row-edit").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var row = this.closest(".settings-row");
            var key = row.dataset.key;
            var displayEl = row.querySelector(".settings-row-value");
            var inputEl = row.querySelector(".settings-row-input");

            if (!inputEl.classList.contains("hidden")) {
                // Save
                applySetting(key, inputEl.value);
                var newVal = getSetting(key);
                if (key === "api_key" || key === "img_api_key") {
                    displayEl.textContent = maskKey(newVal);
                } else {
                    displayEl.textContent = newVal || "";
                    displayEl.classList.toggle("muted", !newVal);
                }
                inputEl.classList.add("hidden");
                displayEl.classList.remove("hidden");
                this.innerHTML = Icons.pencil();
                this.classList.remove("editing");
                // Remove cancel button
                var cancelBtn = row.querySelector(".settings-row-cancel");
                if (cancelBtn) cancelBtn.remove();
            } else {
                // Enter edit mode
                inputEl.value = getSetting(key);
                inputEl.classList.remove("hidden");
                displayEl.classList.add("hidden");
                this.innerHTML = Icons.checkmark();
                this.classList.add("editing");

                // Add cancel button
                var cancelBtn = document.createElement("button");
                cancelBtn.className = "settings-row-cancel";
                cancelBtn.innerHTML = Icons.x();
                cancelBtn.title = _("Cancel");
                cancelBtn.addEventListener("click", function () {
                    inputEl.classList.add("hidden");
                    displayEl.classList.remove("hidden");
                    btn.innerHTML = Icons.pencil();
                    btn.classList.remove("editing");
                    cancelBtn.remove();
                });
                row.insertBefore(cancelBtn, this.nextSibling);
                inputEl.focus();
            }
        });
    });
}
```

- [ ] **步骤 5：添加主题切换按钮绑定函数**

```js
/** Bind a theme quick-toggle button.  Updates icon on click. */
function _bindThemeToggle(btn) {
    if (!btn) return;
    _updateThemeButton(btn);
    btn.addEventListener("click", function () {
        ThemeState.cycle();
        _updateAllThemeButtons();
    });
}

/** Update a single theme button icon to match current theme. */
function _updateThemeButton(btn) {
    var t = ThemeState.effective;  // resolved: "dark" or "light"
    var cur = ThemeState.current;  // "system" | "dark" | "light"
    if (cur === "system") {
        btn.innerHTML = Icons.halfMoon();
        btn.title = _("Theme: System");
    } else if (t === "dark") {
        btn.innerHTML = Icons.moon();
        btn.title = _("Theme: Dark");
    } else {
        btn.innerHTML = Icons.sun();
        btn.title = _("Theme: Light");
    }
}

/** Update ALL theme buttons on the page. */
function _updateAllThemeButtons() {
    document.querySelectorAll(".theme-toggle-btn").forEach(function (btn) {
        _updateThemeButton(btn);
    });
    // Also update appearance segmented control if visible
    var seg = document.querySelector('.settings-seg-group[data-key="theme"]');
    if (seg) {
        seg.querySelectorAll(".settings-seg-btn").forEach(function (b) {
            b.classList.toggle("active", b.dataset.value === ThemeState.current);
        });
    }
}
```

- [ ] **步骤 6：Commit**

```bash
git add src/storyloom/web/static/js/router.js
git commit -m "feat: rewrite settings page with sidebar layout + theme toggle"
```

---

### 任务 6：Settings 侧边栏 CSS

**文件：**
- 修改：`src/storyloom/web/static/css/main.css`（追加新样式）

- [ ] **步骤 1：在 main.css 末尾追加 Settings 侧边栏布局样式**

```css
/* ═══════════════════════════════════════════════════════════════════
   Settings View — Sidebar Layout (Phase 2 redesign)
   ═══════════════════════════════════════════════════════════════════ */

/* ── View container ──────────────────────────────────────────────── */

.settings-view {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 4rem);
    max-width: var(--content-width);
    margin: 0 auto;
    animation: fadeIn var(--trans-slow);
}

/* ── Header ──────────────────────────────────────────────────────── */

.settings-header {
    display: flex;
    align-items: center;
    padding: var(--space-md) var(--space-xs);
    flex-shrink: 0;
    gap: 0.6rem;
}

.settings-title {
    font-family: var(--font-mono);
    font-size: var(--font-md);
    color: var(--text-accent);
    font-weight: normal;
    flex: 1;
}

/* ── Body: sidebar + content ─────────────────────────────────────── */

.settings-body {
    display: flex;
    flex: 1;
    min-height: 0;
}

/* ── Sidebar Navigation ──────────────────────────────────────────── */

.settings-nav {
    display: flex;
    flex-direction: column;
    width: 200px;
    flex-shrink: 0;
    border-right: 1px solid var(--border-color);
    padding: var(--space-sm) 0;
    overflow-y: auto;
    scrollbar-width: none;
    -ms-overflow-style: none;
}

.settings-nav::-webkit-scrollbar { display: none; }

.settings-nav-item {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.6rem 1rem;
    margin: 0.1rem 0.5rem;
    border: none;
    border-radius: var(--radius-md);
    background: transparent;
    color: var(--text-secondary);
    font-family: var(--font-sans);
    font-size: 0.9rem;
    text-align: left;
    cursor: pointer;
    transition: background var(--trans-normal), color var(--trans-normal);
}

.settings-nav-item:hover {
    color: var(--text-primary);
    background: var(--bg-tertiary);
}

.settings-nav-item.active {
    color: var(--text-accent);
    background: var(--bg-tertiary);
    font-weight: 500;
}

.settings-nav-item svg {
    flex-shrink: 0;
}

.settings-nav-divider {
    height: 1px;
    background: var(--border-color);
    margin: 0.5rem 1rem;
}

/* ── Content Area ────────────────────────────────────────────────── */

.settings-content {
    flex: 1;
    overflow-y: auto;
    padding: var(--space-lg) var(--space-xl) var(--space-2xl);
    scrollbar-width: none;
    -ms-overflow-style: none;
}

.settings-content::-webkit-scrollbar { display: none; }

/* ── Settings Card ───────────────────────────────────────────────── */

.settings-card {
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-lg);
    padding: 1.4rem;
    margin-bottom: 1rem;
}

.settings-card-title {
    font-size: 0.75rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 1rem;
    font-family: var(--font-sans);
}

/* ── Settings Row ────────────────────────────────────────────────── */

.settings-row {
    display: flex;
    align-items: center;
    padding: 0.6rem 0;
    border-bottom: 1px solid var(--border-color);
    gap: 0.8rem;
}

.settings-row:last-child {
    border-bottom: none;
}

.settings-row-label {
    color: var(--text-secondary);
    font-size: 0.9rem;
    flex-shrink: 0;
    min-width: 130px;
}

.settings-row-value {
    flex: 1;
    font-family: var(--font-mono);
    font-size: 0.87rem;
    color: var(--text-primary);
    text-align: right;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.settings-row-value.muted {
    color: var(--text-secondary);
    font-style: italic;
}

.settings-row-input {
    flex: 1;
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--text-accent);
    border-radius: var(--radius-sm);
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.87rem;
    outline: none;
    max-width: 380px;
}

.settings-row-select {
    padding: 0.4rem 0.6rem;
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    background: var(--bg-primary);
    color: var(--text-primary);
    font-family: var(--font-mono);
    font-size: 0.87rem;
    text-align: center;
    text-align-last: center;
    min-width: 100px;
    cursor: pointer;
}

.settings-row-select:focus {
    outline: none;
    border-color: var(--text-accent);
    box-shadow: var(--shadow-focus);
}

/* ── Edit / Cancel Buttons ───────────────────────────────────────── */

.settings-row-edit {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    flex-shrink: 0;
    transition: color var(--trans-normal), background var(--trans-normal);
}

.settings-row-edit:hover {
    color: var(--text-accent);
    background: var(--bg-tertiary);
}

.settings-row-edit.editing {
    color: var(--text-accent);
}

.settings-row-cancel {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    padding: 0;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-error);
    cursor: pointer;
    flex-shrink: 0;
    transition: color var(--trans-normal), background var(--trans-normal);
}

.settings-row-cancel:hover {
    background: rgba(248, 81, 73, 0.1);
}

/* ── Segmented Control ───────────────────────────────────────────── */

.settings-seg-group {
    display: flex;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-md);
    overflow: hidden;
}

.settings-seg-btn {
    padding: 0.4rem 0.9rem;
    border: none;
    background: transparent;
    color: var(--text-secondary);
    font-family: var(--font-sans);
    font-size: 0.84rem;
    cursor: pointer;
    transition: background var(--trans-normal), color var(--trans-normal);
    border-right: 1px solid var(--border-color);
}

.settings-seg-btn:last-child { border-right: none; }

.settings-seg-btn:hover { color: var(--text-primary); }

.settings-seg-btn.active {
    background: var(--text-accent);
    color: var(--bg-primary);
}

/* ── Theme Toggle Button (global) ────────────────────────────────── */

.theme-toggle-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: var(--icon-btn-size);
    height: var(--icon-btn-size);
    padding: 0;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    flex-shrink: 0;
    transition: color var(--trans-normal), background var(--trans-normal);
}

.theme-toggle-btn:hover {
    color: var(--text-primary);
    background: var(--bg-tertiary);
}

/* ── Credits ─────────────────────────────────────────────────────── */

.settings-credits-group {
    text-align: center;
    padding: 0.5rem 0;
}

.settings-credits-group h3 {
    font-family: var(--font-mono);
    font-size: 0.82rem;
    color: var(--text-secondary);
    margin: 0.8rem 0 0.3rem;
    font-weight: normal;
}

.settings-credits-name {
    font-size: 0.95rem;
    color: var(--text-primary);
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 1rem;
}

.settings-credits-link {
    color: var(--text-accent);
    text-decoration: none;
    transition: color var(--trans-normal);
}

.settings-credits-link:hover {
    text-decoration: underline;
}

/* ── API Guide Section ───────────────────────────────────────────── */

.settings-guide {
    font-size: 0.9rem;
    line-height: 1.7;
    color: var(--text-primary);
}

.settings-guide h2 {
    font-size: 1.2rem;
    color: var(--text-accent);
    margin: 1.5rem 0 0.8rem;
    padding-bottom: 0.3rem;
    border-bottom: 1px solid var(--border-color);
    font-family: var(--font-sans);
    font-weight: 500;
}

.settings-guide h3 {
    font-size: 1rem;
    color: var(--text-primary);
    margin: 1.2rem 0 0.5rem;
    font-family: var(--font-sans);
    font-weight: 500;
}

.settings-guide p {
    color: var(--text-secondary);
    margin: 0.5rem 0;
}

.settings-guide a {
    color: var(--text-accent);
    text-decoration: none;
}

.settings-guide a:hover { text-decoration: underline; }

.settings-guide ul, .settings-guide ol {
    color: var(--text-secondary);
    padding-left: 1.5rem;
    margin: 0.4rem 0;
}

.settings-guide li { margin: 0.2rem 0; }

.settings-guide code {
    font-family: var(--font-mono);
    background: var(--bg-primary);
    padding: 0.1rem 0.35rem;
    border-radius: 3px;
    font-size: 0.88em;
    color: var(--text-accent);
}

.settings-guide pre {
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: var(--radius-sm);
    padding: 0.8rem 1rem;
    overflow-x: auto;
    font-size: 0.85rem;
    line-height: 1.5;
    margin: 0.6rem 0;
}

.settings-guide pre code {
    background: none;
    padding: 0;
    color: var(--text-primary);
}

.settings-guide table {
    width: 100%;
    border-collapse: collapse;
    margin: 0.8rem 0;
    font-size: 0.85rem;
}

.settings-guide th, .settings-guide td {
    padding: 0.5rem 0.7rem;
    text-align: left;
    border-bottom: 1px solid var(--border-color);
}

.settings-guide th {
    color: var(--text-primary);
    font-weight: 600;
    white-space: nowrap;
}

.settings-guide td { color: var(--text-secondary); }

.settings-guide .guide-callout {
    border-left: 3px solid var(--text-accent);
    background: var(--bg-primary);
    padding: 0.6rem 0.9rem;
    margin: 0.8rem 0;
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    font-size: 0.87rem;
    color: var(--text-secondary);
}

.settings-guide .guide-callout.warn {
    border-left-color: var(--text-warning);
}

.settings-guide .guide-callout.good {
    border-left-color: var(--text-accent);
}

.settings-guide .guide-badge {
    display: inline-block;
    padding: 0.1em 0.5em;
    border-radius: 3px;
    font-size: 0.8rem;
    font-weight: 600;
}

.settings-guide .guide-badge.best { background: rgba(63,185,80,0.15); color: var(--text-accent); }
.settings-guide .guide-badge.good { background: rgba(100,149,237,0.15); color: #6495ed; }
.settings-guide .guide-badge.usable { background: rgba(210,153,34,0.15); color: var(--text-warning); }
```

- [ ] **步骤 2：Commit**

```bash
git add src/storyloom/web/static/css/main.css
git commit -m "feat: add settings sidebar layout CSS — nav, cards, segmented control, guide styles"
```

---

### 任务 7：API 指南 JS 模块 + 渲染

**文件：**
- 创建：`src/storyloom/web/static/js/api-guide.js`
- 修改：`src/storyloom/web/static/js/router.js`（追加 `_renderApiGuideSection` 等函数）
- 修改：`src/storyloom/web/static/index.html`（加载 api-guide.js）

- [ ] **步骤 1：创建 `api-guide.js` — 从 help.html 提取 Markdown 内容**

`api-guide.js` 的内容是将 `help.html` 的核心文档内容（§1-§7）转为 Markdown 字符串，去除 HTML 结构和内联样式。保留所有实际信息内容（表格、链接、说明文字）。

```js
/* ═══════════════════════════════════════════════════════════════════
   api-guide.js — API Setup Guide content (Markdown)

   Content migrated from help.html.  Rendered via marked.js in the
   Settings → API Guide section.  Both dark and light themes supported
   through CSS variable inheritance.

   Exports (on window): API_GUIDE_MD — Markdown string
   ═══════════════════════════════════════════════════════════════════ */

var API_GUIDE_MD = [
"# API Setup Guide",
"",
"How to configure text generation and image generation for Storyloom.",
"",
"## 1. Overview",
"",
"Storyloom interacts with two kinds of API, but **only one is required**:",
"",
"### Text API (LLM) — required",
"",
"Generates the narrative — story prose, dialogue, choices, and game state. The **core engine** of the game. Without a working text API, the game cannot run at all.",
"",
"- **Interface:** OpenAI-compatible `/v1/chat/completions`",
"- **Settings fields:** `API Base URL` · `API Key` · `Model`",
"",
"### Image API — optional",
"",
"Generates character portraits and scene backgrounds for visual novel / graph mode. **Entirely optional.** If left unconfigured or disabled, the game uses its **built-in system media library**.",
"",
"> 💡 **Key fallback:** If `Image API Key` is left empty, Storyloom automatically falls back to your text `API Key`.",
"",
/* ... (complete Markdown for all 7 sections from help.html) ... */
].join("\n");
```

（完整 Markdown 内容从 `help.html` 提取 —— 省略号处的实际内容是 help.html 的全部文档文本，转为 Markdown 格式。表格保留 Markdown table 语法。）

- [ ] **步骤 2：添加 `_renderApiGuideSection()` 函数到 router.js**

在 `router.js` 中追加（在 `_renderAppearanceSection` 之后）：

```js
function _renderApiGuideSection(container) {
    container.innerHTML =
        '<div class="settings-card">'
        + '<div class="settings-guide" id="guide-content">'
        + '<p class="text-muted">' + esc(_("Loading...")) + '</p>'
        + '</div>'
        + '</div>';

    // Render with marked.js (loaded globally from CDN)
    if (typeof marked !== "undefined" && typeof API_GUIDE_MD !== "undefined") {
        var html = marked.parse(API_GUIDE_MD);
        // Wrap callouts (blockquotes that start with emoji)
        html = html.replace(/<blockquote>\s*<p>(💡|⚠️|🎭|📌)/g,
            '<blockquote class="guide-callout good"><p>$1');
        html = html.replace(/<blockquote>\s*<p>/g,
            '<blockquote class="guide-callout"><p>');
        // Badge spans
        html = html.replace(/<span class="badge badge-good">/g,
            '<span class="guide-badge best">');
        html = html.replace(/<span class="badge badge-info">/g,
            '<span class="guide-badge good">');
        html = html.replace(/<span class="badge badge-warn">/g,
            '<span class="guide-badge usable">');
        document.getElementById("guide-content").innerHTML = html;
    } else {
        document.getElementById("guide-content").innerHTML =
            '<p class="text-muted">' + esc(_("API guide unavailable.")) + '</p>';
    }
}
```

- [ ] **步骤 3：添加 `_renderCreditsSection()` 和 `_renderUpdatesSection()`**

```js
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
        '<div class="settings-card">'
        + '<div class="settings-card-title">' + esc(_("Updates")) + '</div>'
        + '<div class="settings-row">'
        + '<span class="settings-row-label">' + esc(_("Current Version")) + '</span>'
        + '<span class="settings-row-value" id="update-current-ver">...</span>'
        + '<button class="settings-row-edit" id="btn-check-update" '
        + 'style="width:auto;padding:0.35rem 0.8rem;border:1px solid var(--border-color);'
        + 'border-radius:var(--radius-sm);font-family:var(--font-sans);font-size:0.84rem">'
        + esc(_("Check for Updates")) + '</button>'
        + '</div>'
        + '</div>';

    // Lazy-load current version
    API.get("/api/update/check?force=false").then(function (result) {
        var el = document.getElementById("update-current-ver");
        if (el) el.textContent = result.app.current;
    }).catch(function () {
        var el = document.getElementById("update-current-ver");
        if (el) el.textContent = "?";
    });

    // Bind update check button (reuse existing _bindUpdateCheck logic)
    var btn = document.getElementById("btn-check-update");
    if (btn) {
        btn.addEventListener("click", function () {
            // Delegate to existing update popup logic
            _bindUpdateCheck();
            document.getElementById("btn-check-update").click();
        });
    }
}
```

- [ ] **步骤 4：修改 `index.html` 加载 api-guide.js**

在 `index.html` 的 `<script>` 加载顺序中，`api-guide.js` 需要在 `marked.js` CDN 之前或之后都可以（只是定义字符串变量）。放在 `credits.js` 之后：

```html
<script src="/static/js/credits.js"></script>
<script src="/static/js/api-guide.js"></script>
```

- [ ] **步骤 5：Commit**

```bash
git add src/storyloom/web/static/js/api-guide.js \
        src/storyloom/web/static/js/router.js \
        src/storyloom/web/static/index.html
git commit -m "feat: integrate API guide into settings sidebar via Markdown module"
```

---

### 任务 8：全局主题切换按钮 — 所有视图顶栏

**文件：**
- 修改：`src/storyloom/web/static/js/display.js`（导出 `_bindThemeToggle` 辅助函数引用）
- 修改：`src/storyloom/web/static/js/game.js`（游戏顶栏加主题按钮）
- 修改：`src/storyloom/web/static/js/co-create.js`（Co-create 顶栏加主题按钮）
- 修改：`src/storyloom/web/static/js/adventure-log.js`（Adventure log 顶栏加主题按钮）
- 修改：`src/storyloom/web/static/js/assets.js`（Asset manager 顶栏加主题按钮）
- 修改：`src/storyloom/web/static/js/router.js`（Save list / Game preview 顶栏加主题按钮）

- [ ] **步骤 1：在每个视图的 topbar 添加主题切换按钮**

**game.js** — 在 `.game-topright` 容器中添加：

```js
// 在 render() 函数中，game-topright 的 HTML 中添加：
'<button class="theme-toggle-btn" id="game-theme-btn" '
+ 'title="' + esc(_("Toggle Theme")) + '"></button>'
```

渲染后绑定：
```js
// 在 render() 末尾的事件绑定区域添加：
var themeBtn = document.getElementById("game-theme-btn");
if (themeBtn) {
    _updateThemeButton(themeBtn);
    themeBtn.addEventListener("click", function () {
        ThemeState.cycle();
        _updateAllThemeButtons();
    });
}
```

**co-create.js** — 在 `.cc-header` 中添加主题按钮（在 `cc-start-btn` 之前）：

```js
// 在 render() 函数的 header HTML 中添加（cc-start-btn 前面）：
'<button class="theme-toggle-btn" id="cc-theme-btn" '
+ 'title="' + esc(_("Toggle Theme")) + '"></button>'
```

渲染后绑定 `_bindThemeToggle(document.getElementById("cc-theme-btn"))`。

**adventure-log.js** — 在 `.al-header` 中添加：

```js
// 在 render() 函数的 header HTML 中，al-label 之后添加：
'<button class="theme-toggle-btn" id="al-theme-btn" '
+ 'title="' + esc(_("Toggle Theme")) + '"></button>'
```

渲染后绑定。

**assets.js** — 在 `.am-header` 中添加：

```js
// 在 render() 函数的 am-header HTML 中，am-title 之后添加：
'<button class="theme-toggle-btn" id="am-theme-btn" '
+ 'title="' + esc(_("Toggle Theme")) + '"></button>'
```

渲染后绑定。

**router.js** — 在 `renderGamePreview()` 和 `renderSaveList()` 的 header 中添加主题按钮。

- [ ] **步骤 2：确保 `_updateThemeButton` 和 `_updateAllThemeButtons` 全局可访问**

在 `router.js` 中将这两个函数挂到 `window`：

```js
window._updateThemeButton = _updateThemeButton;
window._updateAllThemeButtons = _updateAllThemeButtons;
```

- [ ] **步骤 3：Commit**

```bash
git add src/storyloom/web/static/js/game.js \
        src/storyloom/web/static/js/co-create.js \
        src/storyloom/web/static/js/adventure-log.js \
        src/storyloom/web/static/js/assets.js \
        src/storyloom/web/static/js/router.js
git commit -m "feat: add global theme toggle button to all view topbars"
```

---

### 任务 9：清理 — 删除 help.html + /help 路由

**文件：**
- 删除：`src/storyloom/web/static/help.html`
- 修改：`src/storyloom/web/server.py:168-171`

- [ ] **步骤 1：删除 `/help` 路由**

删除 `server.py` 第 168-171 行：

```python
@app.get("/help")
async def help_page():
    """Serve the API setup guide."""
    return FileResponse(str(_STATIC / "help.html"))
```

- [ ] **步骤 2：删除 help.html 文件**

```bash
git rm src/storyloom/web/static/help.html
```

- [ ] **步骤 3：运行 pytest 确认无后端回归**

```bash
pytest
```

- [ ] **步骤 4：Commit**

```bash
git add src/storyloom/web/server.py
git commit -m "refactor: remove standalone /help route — API docs now in SPA settings"
```

---

### 任务 10：最终验证 + 微调

- [ ] **步骤 1：运行全量测试**

```bash
pytest
```
预期：全部通过

- [ ] **步骤 2：启动应用进行视觉检查**

```bash
python -m storyloom.web
```

检查清单：
- [ ] 默认跟随系统主题（`data-theme="system"`）
- [ ] 浏览器 DevTools 切换 `prefers-color-scheme` → 主题跟随切换
- [ ] Settings 页侧边栏布局正常，7 个分组均可点击切换
- [ ] API Guide 内容完整渲染（marked.js）
- [ ] Appearance → Theme 分段控件切换正常
- [ ] 全局主题按钮图标随主题变化（sun/moon/half-moon）
- [ ] 游戏叙事视图颜色正确适配双主题
- [ ] Co-create 聊天视图颜色正确
- [ ] Save browser / Adventure log / Asset manager 颜色正确
- [ ] 设置修改保存后在 localStorage 持久化
- [ ] `localStorage["storyloom-theme"]` 正确保存/读取

- [ ] **步骤 3：提交最终修复（如有）**

```bash
git add -A
git commit -m "fix: visual tweaks from theme verification pass"
```

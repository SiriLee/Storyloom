# Auto-Update Design

> 2026-08-10 | Status: draft

## 1. Overview

Users (primarily exe users) can check for and apply updates from within the
application without visiting GitHub manually.  User data (saves, config,
generated media) is never touched.  System media and app core are independent
update targets.

**Core principle:** The app downloads new versions; the user decides when to
restart.  A platform-native launcher script (~10 lines) picks the latest
version on each start.

## 2. Directory Layout

### 2.1 Current (v1.3.0) — flat, everything in one directory

```
storyloom-web-v1.3.0/
├── storyloom-web            ← PyInstaller single-file exe
├── locale/
├── config.example.json
├── storyloom-1.3.0-*.whl
├── storyloom-1.3.0.tar.gz
├── config.json              ← user data (created at runtime)
├── saves/                   ← user data
└── media/                   ← user data
```

### 2.2 Target — shared user data + versioned app dirs

```
storyloom/                        ← user-facing root (one-time setup)
├── storyloom-launcher.sh         ← Linux/macOS entry point
├── storyloom-launcher.bat        ← Windows entry point
├── app/                          ← versioned application directories
│   ├── v1.3.0/
│   │   ├── storyloom-web
│   │   ├── locale/
│   │   └── config.example.json
│   └── v1.4.0/
│       ├── storyloom-web
│       ├── locale/
│       └── config.example.json
├── saves/                        ← user data (shared across all versions)
├── media/                        ← user data (shared across all versions)
├── config.json                   ← user data (shared across all versions)
└── system_media/                 ← independent update target
    ├── VERSION
    ├── _manifest.json
    ├── char_portrait/
    └── background_img/
```

**Key changes from current layout:**
- User data (`saves/`, `media/`, `config.json`) lifted to shared root.
- App code lives in versioned `app/v{X}.{Y}.{Z}/` directories — read-only
  after extraction.
- `system_media/` lives at root, updated independently.
- `models/u2netp.onnx` stays inside the exe (via `--add-data`), follows
  app version — no independent model updates.

### 2.3 Migration from flat to layered

On first launch of v1.4.0+ (the first version shipping with launcher), the
app:
1. Detects old flat layout — `config.json` exists next to the exe.
2. Creates the new layout structure alongside.
3. Moves `saves/`, `media/`, `config.json` to shared root.
4. Moves old `system_media/` if present.
5. Writes the launcher scripts.
6. Shows a one-time message: "Restart via storyloom-launcher from now on."

### 2.4 WHL users

No layout change.  `pip install --upgrade storyloom` works normally.
User data lives wherever the user runs the app from — the launcher concept
is irrelevant for pip users.  The UpdateManager can still check for new
pip versions and suggest `pip install --upgrade storyloom`.

## 3. Launcher

### 3.1 Design

Each launch:
1. List `app/v*/` directories.
2. Sort by semver.
3. `exec` the `storyloom-web` binary in the latest directory.

The launcher is **stateless and side-effect-free** — it does not download,
check for updates, or write anything.  It only chooses and launches the
latest installed version.

The launcher itself **does not auto-update**.  Its logic ("find latest →
exec") is stable.  In the unlikely event it must change, the main app can
overwrite it since the launcher is not running while the app is running.

### 3.2 Script: Linux / macOS

`storyloom-launcher.sh`:
```bash
#!/bin/bash
# Storyloom Launcher — find latest version and exec it.
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
LATEST=$(ls -d "$DIR/app/"v*/ 2>/dev/null | sort -V | tail -1)
if [ -z "$LATEST" ]; then
    echo "No Storyloom installation found in $DIR/app/" >&2
    exit 1
fi
exec "$LATEST/storyloom-web" "$@"
```

### 3.3 Script: Windows

`storyloom-launcher.bat`:
```batch
@echo off
setlocal enabledelayedexpansion
set "DIR=%~dp0"
set "LATEST="
for /f "tokens=*" %%d in ('dir /b /ad /on "%DIR%app\v*" 2^>nul') do set "LATEST=%%d"
if "%LATEST%"=="" (
    echo No Storyloom installation found in %DIR%app\ >&2
    exit /b 1
)
start "" "%DIR%app\%LATEST%\storyloom-web.exe" %*
```

### 3.4 Permissions

- Linux/macOS: `chmod +x storyloom-launcher.sh`
- Windows: `.bat` is natively executable
- Desktop shortcuts / start menu entries point to the launcher, not the exe

## 4. UpdateManager Module

New module: `src/storyloom/core/update_manager.py`

### 4.1 Responsibilities

- Query GitHub Releases API for latest app version.
- Query for latest system_media version (separate release asset or tag).
- Compare against installed versions.
- Download and extract release zips with progress reporting.
- Never touch user data.

### 4.2 Version sources

| Layer | Local version source | Remote version source |
|-------|---------------------|----------------------|
| App Core | `storyloom.__version__` | GitHub latest release `tag_name` (strip `v` prefix) |
| System Media | `system_media/VERSION` file | GitHub release asset filename pattern `system_media-v{ver}.zip` |

### 4.3 GitHub API integration

```
GET https://api.github.com/repos/SiriLee/Storyloom/releases/latest
Authorization: none (public repo)
```

Parse response:
- `tag_name` → latest app version (e.g. `"v1.4.0"`)
- `assets[].name` → find `storyloom-web-v{ver}-{platform}.zip` and
  `system_media-v{ver}.zip`
- `assets[].browser_download_url` → direct download URL
- `body` → release notes (markdown, for UI display)

Platform detection for asset matching:
```python
import sys
if sys.platform == "win32":
    _PLATFORM = "Windows"
elif sys.platform == "darwin":
    _PLATFORM = "macOS"
else:
    _PLATFORM = "Linux"
```

### 4.4 Download with progress

```python
def download_with_progress(url: str, dest: str, progress_callback) -> None:
    """Stream download with per-chunk progress reporting.
    
    progress_callback(received_bytes: int, total_bytes: int | None)
    """
```

The callback pushes progress events into the SSE queue so the frontend
can render a progress bar.

### 4.5 Extraction

For app core:
1. Download `storyloom-v{ver}-{platform}.zip` to a temp directory.
2. Extract.  The zip contains launcher scripts at root and `app/v{ver}/`
   as a subdirectory.
3. Move `app/v{ver}/` from temp to `<APP_ROOT>/app/v{ver}/`.
4. Copy launcher scripts from temp to `<APP_ROOT>/`, overwriting existing
   ones (handles launcher script updates).
5. Verify the exe exists at `<APP_ROOT>/app/v{ver}/storyloom-web`.

For system_media:
1. Download `system_media-v{ver}.zip` to temp.
2. Extract to `<APP_ROOT>/system_media/`, overwriting existing files.
3. Verify `system_media/VERSION` updated.

### 4.6 Key data types

```python
@dataclass
class VersionInfo:
    current: str       # "1.3.0"
    latest: str        # "1.4.0" (empty if no update)
    has_update: bool
    release_notes: str

@dataclass  
class UpdateCheckResult:
    app: VersionInfo
    system_media: VersionInfo

@dataclass
class UpdateProgress:
    layer: str         # "app" | "system_media"
    stage: str         # "downloading" | "extracting" | "done" | "error"
    received: int
    total: int | None
    error: str | None
```

## 5. API Endpoints

All endpoints under the web server.

### 5.1 `GET /api/update/check`

Returns `UpdateCheckResult`.

Side effect: makes one HTTP request to GitHub Releases API.

Caching: results cached for 15 minutes to avoid rate-limiting on repeated
clicks.  `?force=true` bypasses cache.

### 5.2 `POST /api/update/apply`

Request body:
```json
{
  "layers": ["app", "system_media"]
}
```

Returns immediately with an SSE stream URL.

### 5.3 `GET /api/update/stream`

SSE stream. Events:

```
event: progress
data: {"layer":"app","stage":"downloading","received":5242880,"total":23123456}

event: progress
data: {"layer":"app","stage":"extracting"}

event: progress
data: {"layer":"system_media","stage":"downloading","received":1048576,"total":5242880}

event: done
data: {"layers":{"app":"1.4.0","system_media":"1.2.0"}}

event: error
data: {"layer":"app","error":"Download failed: connection reset"}
```

The stream ends on `done` or `error`.

## 6. Frontend UI

### 6.1 Location

Settings page, new section: "Updates"

### 6.2 States

**Idle (before check):**
```
┌──────────────────────────────────┐
│  更新                             │
│  当前版本: 1.3.0                  │
│              [检查更新]            │
└──────────────────────────────────┘
```

**Checking:**
```
┌──────────────────────────────────┐
│  更新                             │
│  正在检查... ⏳                    │
└──────────────────────────────────┘
```

**No updates:**
```
┌──────────────────────────────────┐
│  更新                             │
│  ✅ 已是最新版本 (1.3.0)          │
│              [检查更新]            │
└──────────────────────────────────┘
```

**Updates available:**
```
┌──────────────────────────────────┐
│  更新                             │
│                                   │
│  App Core     1.3.0 → 1.4.0      │
│  ┌─────────────────────────────┐ │
│  │ Release notes (markdown)    │ │
│  └─────────────────────────────┘ │
│                                   │
│  System Media 1.1.0 → 1.2.0      │
│                                   │
│              [更新选中的项目]       │
└──────────────────────────────────┘
```

**Downloading:**
```
┌──────────────────────────────────┐
│  正在下载...                       │
│                                   │
│  App Core     ████████░░ 78%     │
│  System Media ⏳ 等待中            │
│                                   │
│              (后台继续)            │
└──────────────────────────────────┘
```

**Done — ready to restart:**
```
┌──────────────────────────────────┐
│  ✅ 更新已就绪                     │
│                                   │
│  App Core v1.4.0 已安装            │
│  System Media v1.2.0 已更新        │
│                                   │
│  请关闭应用后重新启动。              │
│  双击 storyloom-launcher 即可。    │
└──────────────────────────────────┘
```

### 6.3 User flow

1. Navigate to Settings → Updates.
2. Click "检查更新".
3. Review what's available.
4. Click "更新选中的项目".
5. Watch progress.
6. Close the application.
7. Double-click `storyloom-launcher` (or desktop shortcut).
8. New version starts automatically.

## 7. Build Script Changes

`scripts/build.sh` changes:

1. Release zip structure — launcher scripts at root, app in versioned subdir:
   ```
   storyloom-v1.4.0-Linux.zip          ← renamed: {name}-v{ver}-{platform}.zip
   ├── storyloom-launcher.sh            ← NEW — at root, user clicks this
   ├── storyloom-launcher.bat           ← NEW — at root, user clicks this
   └── app/
       └── v1.4.0/
           ├── storyloom-web            ← PyInstaller single-file exe
           ├── locale/
           ├── config.example.json
           ├── storyloom-1.4.0-*.whl
           └── storyloom-1.4.0.tar.gz
   ```

   First-time installation: download zip → extract anywhere → double-click launcher.

   Update: download zip → extract `app/v{new}/` into existing `app/` → copy
   launcher scripts to root (overwrite with newer version).

2. `system_media/` is **no longer bundled inside the exe** via
   `--add-data`.  Instead, it's distributed as a separate release asset
   (`system_media-v{ver}.zip`) and extracted to the shared root at
   first launch or update time.  `serve_media` gracefully returns 404
   for missing system_media — the frontend already handles missing assets.

3. `_APP_DIR` (shared root) detection: the app is at `app/v{X}.{Y}.{Z}/storyloom-web`.
   Shared root = two levels up from `sys.executable`:
   ```python
   if getattr(sys, 'frozen', False):
       _APP_DIR = Path(sys.executable).parent.parent.parent
   ```
   `STORYLOOM_APP_DIR` env var overrides auto-detection (for WHL users and
   custom setups).

### 7.1 First-launch bootstrap

On first launch:
1. App detects `system_media/` is missing at the shared root.
2. Downloads `system_media-v{latest}.zip` from GitHub.
3. Extracts to `system_media/`.
4. Writes `system_media/VERSION`.

If download fails (offline), the app runs without system media —
frontend shows placeholder images for sys_ assets.  First subsequent
online check will prompt to download.

## 8. WHL Users

### 8.1 Version check

`GET /api/update/check` also checks PyPI:
```
GET https://pypi.org/pypi/storyloom/json
```

Parse `info.version` → latest pip version.

### 8.2 Update path

For WHL users, the "update" action shows:
```
pip install --upgrade storyloom
```

The user runs this manually.  The app cannot (and should not) call pip
programmatically — it risks dependency conflicts, permission issues, and
broken environments.

### 8.3 Launcher

WHL users don't use the launcher scripts.  They run `storyloom-web`
directly (console_scripts entry point).  User data (saves, config,
media) lives in the current working directory or `STORYLOOM_APP_DIR`.

## 9. Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| GitHub API rate-limited (60 req/hr unauthenticated) | Cache results 15 min; show "try again later" message with retry time |
| Download interrupted | Delete partial file; allow retry |
| Disk full during extraction | Delete partial extraction; show error with space requirement |
| New version requires higher min_app_version for system_media | Check `_manifest.json` min_app_version before applying; warn if incompatible |
| User runs exe directly, not via launcher | App still works; "check for updates" still works; restart prompt says "use launcher next time" |
| Old version dirs accumulate (v1.2.0, v1.3.0, v1.4.0...) | Settings UI shows installed versions with "delete" button; app never auto-deletes |
| Launcher script deleted accidentally | App can re-generate launcher scripts on next launch |
| First install — no existing layout | Release zip contains launcher + `app/v{ver}/`; user extracts once; on first run, app bootstraps `saves/`, `media/`, `config.json` |
| Corrupt download | Verify zip integrity before extraction; if corrupt, delete and retry |
| User data migration on first upgrade from flat layout | One-time migration on startup: move saves/, media/, config.json to shared root; show confirmation message |

## 10. Non-Goals (YAGNI)

- **Auto-check on startup** — manual trigger only.
- **Auto-restart after update** — user restarts manually.
- **Delta/差分更新** — PyInstaller single-file exe can't be delta-patched.
- **Background download** — download happens after user clicks "update".
- **Model independent updates** — ONNX models follow app version.
- **Rollback automation** — user manually launches old version from
  `app/v{old}/` if needed.  Old directories are never deleted automatically.
- **Update channels** (beta/stable) — single release channel for now.
- **Signed/verified binaries** — no code signing infrastructure.

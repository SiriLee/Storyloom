# Auto-Update Design

> 2026-08-10 | Status: draft

## 1. Overview

Users (primarily exe users) can check for and apply updates from within the
application without visiting GitHub manually.  User data (saves, config,
generated media) is never touched.  System media and app core are independent
update targets.

**Core principle:** The app downloads new versions; the user restarts to apply.
A PyInstaller-compiled launcher executable (`Storyloom.exe`) handles the
atomic swap on next launch.

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

### 2.2 Target — shared user data + single active version

```
storyloom/                        ← user-facing root (one-time setup)
├── Storyloom / Storyloom.exe     ← Launcher — PyInstaller single-file exe
├── app/                          ← current active version (only one)
│   ├── storyloom-web
│   ├── locale/
│   └── config.example.json
├── app_new/                      ← staging dir for next version (only during update)
├── saves/                        ← user data (shared)
├── media/                        ← user data (shared)
├── config.json                   ← user data (shared)
└── system_media/                 ← independent update target
    ├── VERSION
    ├── _manifest.json
    ├── char_portrait/
    └── background_img/
```

**Key changes from current layout:**
- User data (`saves/`, `media/`, `config.json`) lifted to shared root.
- `app/` holds one version at a time.  No multi-version accumulation.
- `app_new/` exists only during an update — Launcher deletes `app_old/`
  and renames `app_new/` → `app/` on next start.
- `system_media/` lives at root, updated independently.
- `models/u2netp.onnx` stays inside the main exe (via `--add-data`),
  follows app version — no independent model updates.
- `Storyloom`/`Storyloom.exe` is the user-facing entry point.

### 2.3 Migration from flat to layered

On first launch of v1.4.0+ (the first version shipping with the launcher),
the app:
1. Detects old flat layout — `config.json` exists next to the main exe.
2. Creates the new layout structure alongside.
3. Moves `saves/`, `media/`, `config.json` to shared root.
4. Moves old `system_media/` if present.
5. Copies the Launcher exe to shared root.
6. Shows a one-time message: "Restart via Storyloom from now on."

### 2.4 WHL users

No layout change.  `pip install --upgrade storyloom` works normally.
User data lives wherever the user runs the app from — the Launcher concept
is irrelevant for pip users.  The UpdateManager can still check for new
pip versions and suggest `pip install --upgrade storyloom`.

## 3. Launcher

### 3.1 Design

The Launcher is a standalone PyInstaller-compiled executable with zero
dependencies.  Size: ~8 MB (Python interpreter overhead).  Platform-specific
naming: `Storyloom` (Linux/macOS), `Storyloom.exe` (Windows).

Each launch:
1. Check for `app_new/` — a pending update.
2. If found: atomic swap.  `app/` → `app_old/`, `app_new/` → `app/`,
   delete `app_old/`.
3. If `launcher.new` exists — self-update (§3.2).
4. `exec` the main exe at `app/storyloom-web`.

The Launcher is **stateless** — it does not download, check for updates,
or write anything except during the atomic swap at startup.

### 3.2 Launcher self-update

The Launcher itself almost never needs updating — its only contract with
the main app is three stable conventions:

```
Directory names:  app/   app_new/
Executable name:  storyloom-web / storyloom-web.exe
```

When the Launcher must be updated (rare), the main app handles it safely —
the Launcher is **not running** while the main app is running:

```
Update zip optionally contains:
├── launcher.new              ← new Launcher binary (if Launcher itself changed)
└── app_new/                  ← new app version

Main app extracts:
  1. app_new/ → <root>/app_new/          (always)
  2. launcher.new → <root>/launcher.new   (only if present in zip)

User restarts → current Launcher starts:
  1. Detect launcher.new exists
  2. Self-replace:
     - Linux/macOS: os.rename("launcher.new", "Storyloom") then exec the new one
     - Windows: cannot rename running exe → write a one-shot .bat:
       ```
       @timeout /t 1 >nul
       @move /Y launcher.new Storyloom.exe
       @start Storyloom.exe
       ```
       spawn this .bat detached, then exit.  .bat waits 1s for old
       Launcher to terminate, swaps, and re-launches the new Launcher.
  3. New Launcher continues: finds app_new/ → swap → exec main app
```

This two-level dance is only needed when the Launcher itself changes.
99%+ of updates won't include a new Launcher.

### 3.3 Launcher source

```python
"""
Storyloom Launcher — apply pending updates and launch the main application.
"""
import os
import shutil
import subprocess
import sys


def _platform_exe(name: str) -> str:
    return name + (".exe" if sys.platform == "win32" else "")


LAUNCHER_NAME = _platform_exe("Storyloom")
MAIN_EXE = _platform_exe("storyloom-web")

DIR = os.path.dirname(os.path.abspath(sys.executable))
APP = os.path.join(DIR, "app")
APP_NEW = os.path.join(DIR, "app_new")
APP_OLD = os.path.join(DIR, "app_old")
LAUNCHER_NEW = os.path.join(DIR, "launcher.new")


def _apply_app_update():
    """Atomic swap: app_new → app."""
    if not os.path.isdir(APP_NEW):
        return
    shutil.rmtree(APP_OLD, ignore_errors=True)
    if os.path.isdir(APP):
        os.rename(APP, APP_OLD)
    os.rename(APP_NEW, APP)
    shutil.rmtree(APP_OLD, ignore_errors=True)


def _apply_launcher_update():
    """Self-replace the Launcher binary."""
    if not os.path.isfile(LAUNCHER_NEW):
        return

    if sys.platform == "win32":
        # Cannot rename running exe on Windows — spawn a one-shot cmd.
        bat = os.path.join(DIR, "_launcher_swap.bat")
        with open(bat, "w") as f:
            f.write(
                "@echo off\n"
                "timeout /t 1 /nobreak >nul\n"
                f'move /Y "{LAUNCHER_NEW}" "{LAUNCHER_NAME}"\n'
                f'start "" "{os.path.join(DIR, LAUNCHER_NAME)}"\n'
            )
        subprocess.Popen(
            bat, shell=True,
            creationflags=0x00000008,  # DETACHED_PROCESS
            close_fds=True,
        )
        sys.exit(0)
    else:
        # Unix: rename works across inode — running process unaffected.
        launcher_path = os.path.join(DIR, LAUNCHER_NAME)
        os.rename(LAUNCHER_NEW, launcher_path)
        os.chmod(launcher_path, 0o755)
        os.execv(launcher_path, [launcher_path] + sys.argv[1:])


def main():
    _apply_launcher_update()
    _apply_app_update()

    target = os.path.join(APP, MAIN_EXE)
    if not os.path.isfile(target):
        print(f"Error: {target} not found", file=sys.stderr)
        sys.exit(1)

    os.execv(target, [target] + sys.argv[1:])


if __name__ == "__main__":
    main()
```

## 4. UpdateManager Module

New module: `src/storyloom/core/update_manager.py`

### 4.1 Responsibilities

- Read a small per-layer manifest file from the GitHub release *download*
  CDN — never the rate-limited REST API (`api.github.com`).
- Compare against installed versions.
- Download and extract release zips with progress reporting.
- Never touch user data.

### 4.2 Version sources

Each layer declares its current version in a manifest asset served from the
release CDN (`releases/download/…`, which 302s to
`release-assets.githubusercontent.com` — not rate-limited).

| Layer | Local version source | Remote manifest (CDN) | Download asset (deterministic) |
|-------|---------------------|-----------------------|-------------------------------|
| App Core | `storyloom.__version__` | `releases/latest/download/update.json` → `version` | `storyloom-app-v{ver}-{platform}.zip` |
| System Media | `system_media/VERSION` file | `releases/download/system-media/_manifest.json` → `version` | `system_media-v{ver}.zip` |
| Launcher | `launcher.version` file (exe dist only) | `releases/download/launcher/VERSION` (plain text) | `storyloom-launcher-v{ver}-{platform}.zip` |

### 4.3 Manifest format

```
GET https://github.com/SiriLee/Storyloom/releases/latest/download/update.json
```

The app manifest (`update.json`) carries:

```json
{
  "version": "1.4.0",
  "notes": "markdown release notes"
}
```

The system_media manifest is the existing `_manifest.json` (already carries
`version` + `min_app_version`).  The launcher manifest is a plain-text
`VERSION` file.

Download URLs are deterministic — derived from the manifest version and the
fixed asset naming convention, so no API call is needed to discover them.
The launcher layer is skipped entirely when no launcher is installed (empty
`launcher.version`).

Platform detection for asset naming:
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
2. Extract.  The zip contains:
   ```
   ├── launcher.new              ← new Launcher (optional — only if Launcher
   │                                itself changed; 99%+ of updates omit this)
   └── app_new/                  ← new app version
       ├── storyloom-web
       ├── locale/
       └── config.example.json
   ```
3. Move `app_new/` to `<APP_ROOT>/app_new/`.  If `app_new/` already
   exists (previous update never applied), delete it first.
4. If `launcher.new` is present in the zip, copy it to
   `<APP_ROOT>/launcher.new`.
5. Verify `<APP_ROOT>/app_new/storyloom-web` exists.

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

Side effect: makes three manifest requests over the release download CDN
(no API rate limit).

Caching: results cached for 15 minutes.  `?force=true` bypasses cache.

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
│  请关闭应用后重新启动 Storyloom。    │
└──────────────────────────────────┘
```

### 6.3 User flow

1. Navigate to Settings → Updates.
2. Click "检查更新".
3. Review what's available.
4. Click "更新选中的项目".
5. Watch progress.
6. Close the application.
7. Double-click `Storyloom` (or desktop shortcut).
8. Launcher applies swap — new version starts.

## 7. Build Script Changes

`scripts/build.sh` changes:

### 7.1 Build the Launcher exe

A second PyInstaller invocation compiles the Launcher from the minimal
source in §3.3:

```bash
$PYTHON -m PyInstaller --onefile \
    --name "$LAUNCHER_NAME" \
    --clean \
    src/storyloom/launcher.py
```

No `--add-data` — the Launcher has zero bundled data.  Exe size ~8 MB.

### 7.2 Release zip structure

```
storyloom-v1.4.0-Linux.zip         ← {name}-v{ver}-{platform}.zip
├── launcher.new                    ← Launcher exe (named .new so extraction
│                                     doesn't overwrite running Launcher)
└── app_new/                        ← new app version (named _new for same reason)
    ├── storyloom-web               ← PyInstaller single-file exe
    ├── locale/
    ├── config.example.json
    ├── storyloom-1.4.0-*.whl
    └── storyloom-1.4.0.tar.gz
```

**First-time installation:**
1. Download `storyloom-v1.4.0-Linux.zip`.
2. Extract to desired location.
3. Rename `launcher.new` → `Storyloom`.
4. Rename `app_new/` → `app/`.
5. Double-click `Storyloom`.

`--regenerate-launcher` recovers a deleted Launcher binary by downloading
it from the launcher release asset (see §4.2) — it does not rebuild from
source.

**Update:**
1. App downloads zip and extracts to temp.
2. Moves `app_new/` to `<root>/app_new/`.
3. If `launcher.new` present, copies to `<root>/launcher.new`.
4. User restarts → Launcher applies both.

### 7.3 Separate system_media asset

`system_media/` is **no longer bundled inside the exe** via `--add-data`.
Instead, it's distributed as a separate release asset
(`system_media-v{ver}.zip`) and extracted to the shared root at first
launch or update time.  `serve_media` returns 404 for missing system_media
assets — the frontend already handles missing assets.

### 7.4 `_APP_DIR` detection

```python
if getattr(sys, 'frozen', False):
    # Running as PyInstaller exe:
    #   sys.executable = <root>/app/storyloom-web
    #   _APP_DIR       = <root>
    _APP_DIR = Path(sys.executable).parent.parent
else:
    # Dev mode — repo root
    _APP_DIR = Path(__file__).resolve().parents[3]
```

`STORYLOOM_APP_DIR` env var overrides auto-detection (for WHL users and
custom setups).

### 7.5 First-launch bootstrap

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

WHL users don't use the Launcher.  They run `storyloom-web` directly
(console_scripts entry point).  User data (saves, config, media) lives
in the current working directory or `STORYLOOM_APP_DIR`.

## 9. Edge Cases & Error Handling

| Scenario | Handling |
|----------|----------|
| Manifest request fails (network/offline) | Cache results 15 min; per-layer `error` category shown in UI |
| Download interrupted | Delete partial file; allow retry |
| Disk full during extraction | Delete partial extraction; show error with space requirement |
| New version requires higher min_app_version for system_media | Check `_manifest.json` min_app_version before applying; warn if incompatible |
| User runs main exe directly, not via Launcher | App still works; "check for updates" still works; restart prompt says "use Storyloom Launcher next time" |
| `app_new/` exists but is incomplete | Launcher checks for `app_new/storyloom-web` existence; if missing, reports error and skips swap; user can still run old version |
| Launcher deleted accidentally | App includes `--regenerate-launcher` CLI flag; user runs `storyloom-web --regenerate-launcher` to restore it |
| First install — no existing layout | Release zip contains `launcher.new` + `app_new/`; user extracts, renames, double-clicks Launcher; on first run, app bootstraps `saves/`, `media/`, `config.json`, downloads `system_media/` |
| Corrupt download | Verify zip integrity before extraction; if corrupt, delete and retry |
| User data migration on first upgrade from flat layout | One-time migration on startup: move saves/, media/, config.json to shared root; show confirmation message |
| `launcher.new` self-update fails mid-way on Windows | `.bat` script handles retry on next run; if hopelessly broken, user runs `storyloom-web --regenerate-launcher` |

## 10. Non-Goals (YAGNI)

- **Auto-check on startup** — manual trigger only.
- **Auto-restart after update** — user restarts manually.
- **Delta/差分更新** — PyInstaller single-file exe can't be delta-patched.
- **Background download** — download happens after user clicks "update".
- **Model independent updates** — ONNX models follow app version.
- **Update channels** (beta/stable) — single release channel for now.
- **Signed/verified binaries** — no code signing infrastructure.

#!/bin/bash
# Build Storyloom Web UI — wheel + PyInstaller portable distribution
# Run on the target platform (Linux → ELF, Windows → .exe, macOS → Mach-O)
set -e

PYTHON="${PYTHON:-python3}"
# Fallback to 'python' on Windows / if 'python3' not found
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON="python"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Extract version from __init__.py without importing (avoids dependency deadlock).
VERSION=$($PYTHON -c "import re; print(re.search(r'__version__\s*=\s*\"(.+?)\"', open('src/storyloom/__init__.py', encoding='utf-8').read()).group(1))")
# Launcher has its own independent version (bumped only when launcher.py changes).
LAUNCHER_VER=$(head -1 launcher.version 2>/dev/null | tr -d '[:space:]' || true)
if [ -z "$LAUNCHER_VER" ]; then
    echo "ERROR: launcher.version missing or empty" >&2
    exit 1
fi
PYI_FLAGS=""
BIN_NAME="storyloom-web"
LAUNCHER_NAME="Storyloom"
ICON="assets/icons/icon.ico"
OUTPUT_DIR="dist/storyloom-v${VERSION}"

# ── Platform detection (once) ────────────────────────────────────────
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)  BIN_NAME="storyloom-web.exe"
                            LAUNCHER_NAME="Storyloom.exe"
                            ADD_SEP=";"
                            PLATFORM="Windows" ;;
    Darwin)                 ADD_SEP=":"
                            PLATFORM="macOS" ;;
    Linux)                  ADD_SEP=":"
                            PLATFORM="Linux" ;;
    *)                      ADD_SEP=":"
                            PLATFORM="$(uname -s)" ;;
esac

echo "=== Storyloom Web UI Build v${VERSION} ==="

# 0. Clean previous build artifacts (dist + PyInstaller build cache only).
echo "--- Cleaning previous builds ---"
rm -rf build/ dist/*.whl dist/*.tar.gz dist/storyloom-v* dist/storyloom-web* dist/Storyloom-v*

# 0b. Ensure background-removal model is available (u2netp.onnx, ~4.4 MB).
#     Bundled via --add-data into the main exe.  Downloaded once and cached.
#     Build aborts if the model cannot be obtained — a release binary must
#     include every feature it advertises.
MODEL_DIR="src/storyloom/models"
MODEL_FILE="$MODEL_DIR/u2netp.onnx"
MODEL_URL="https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"
if [ ! -f "$MODEL_FILE" ]; then
    echo "--- Downloading u2netp.onnx (background removal model) ---"
    $PYTHON -c "
import urllib.request, os
url = '${MODEL_URL}'
dest = '${MODEL_FILE}'
os.makedirs(os.path.dirname(dest), exist_ok=True)
urllib.request.urlretrieve(url, dest)
print(f'  Downloaded {os.path.getsize(dest)} bytes')
" || {
        echo "ERROR: Failed to download u2netp.onnx." >&2
        echo "  Manual download: ${MODEL_URL}" >&2
        echo "  Place at: ${MODEL_FILE}" >&2
        exit 1
    }
fi

# 1. Install project + build tools (PyInstaller needs deps to discover imports)
echo "--- Installing project + build tools ---"
$PYTHON -m pip install -q -e ".[bg,desktop]" build pyinstaller wheel 2>/dev/null || \
    $PYTHON -m pip install -q --break-system-packages -e ".[bg,desktop]" build pyinstaller wheel

# 2. pip packages (wheel + sdist)
#    i18n (.mo + frontend JS dict) compiled automatically by setup.py build hook
echo "--- Building pip packages ---"
$PYTHON -m build --no-isolation

# System media — pack via pack_system_media.sh for filtered, consistent output
# (skips runtime thumbnails, validates manifest vs. source).
# Pre-built zip takes priority; falls back to packing from local system_media/.
SM_VERSION=$(head -1 system_media/VERSION 2>/dev/null | tr -d '[:space:]' || true)
SM_ZIP="system_media-v${SM_VERSION}.zip"

if [ -n "$SM_VERSION" ] && [ -f "$SM_ZIP" ]; then
    echo "--- System media: using $SM_ZIP ---"
elif [ -f "system_media/_manifest.json" ]; then
    echo "--- System media: packing from local system_media/ ---"
    bash scripts/pack_system_media.sh --skip-check
    SM_ZIP="system_media-v${SM_VERSION}.zip"
else
    echo "--- System media: not found (run scripts/pack_system_media.sh first) ---"
fi

# 3. PyInstaller single-file executable
echo "--- Building standalone executable ---"
$PYTHON -m PyInstaller --onefile $PYI_FLAGS \
    --name "$BIN_NAME" \
    --icon "$ICON" \
    --add-data "locale${ADD_SEP}locale" \
    --add-data "src/storyloom/web/static${ADD_SEP}storyloom/web/static" \
    --add-data "src/storyloom/core/lang_meta${ADD_SEP}storyloom/core/lang_meta" \
    --add-data "src/storyloom/models${ADD_SEP}storyloom/models" \
    --hidden-import uvicorn.loops.auto \
    --hidden-import uvicorn.protocols.http.auto \
    --hidden-import onnxruntime \
    --hidden-import numpy \
    --hidden-import webview \
    src/storyloom/web/__main__.py

# 3b. Build Launcher — minimal PyInstaller exe (no --add-data)
echo "--- Building Launcher ---"
$PYTHON -m PyInstaller --onefile $PYI_FLAGS \
    --name "$LAUNCHER_NAME" \
    --icon "$ICON" \
    --clean \
    src/storyloom/launcher.py

# 3c. Package Launcher as a separate update asset — downloaded only when
#     launcher.version bumps (independent of the app version).
echo "--- Packaging launcher asset ---"
mkdir -p build/launcher_asset
cp "dist/$LAUNCHER_NAME" build/launcher_asset/
cp launcher.version build/launcher_asset/
$PYTHON -c "import shutil; shutil.make_archive('dist/Storyloom-v${LAUNCHER_VER}-${PLATFORM}', 'zip', 'build/launcher_asset')"

# 4. Assemble release directory — ready-to-run structure for first install
#    app/ holds versioned files replaced on update: binary + locale.
#    Shared root holds user data: config, saves, media, system_media.
echo "--- Assembling release directory ---"
mkdir -p "$OUTPUT_DIR/app"
cp "dist/$BIN_NAME" "$OUTPUT_DIR/app/"
cp "dist/$LAUNCHER_NAME" "$OUTPUT_DIR/$LAUNCHER_NAME"
cp launcher.version "$OUTPUT_DIR/"
cp -r locale "$OUTPUT_DIR/app/"
cp config.example.json "$OUTPUT_DIR/app/"
# wheel + sdist stay in dist/ as separate PyPI-channel assets — never inside
# the binary payload (binary users don't need them; they bloat every update).

# System media — extract from filtered zip into release directory.
# Uses the same zip produced by pack_system_media.sh (skips thumbnails).
if [ -f "$SM_ZIP" ]; then
    echo "--- System media: extracting $SM_ZIP into release ---"
    $PYTHON -c "import zipfile, os; \
os.makedirs('${OUTPUT_DIR}/system_media', exist_ok=True); \
zipfile.ZipFile('${SM_ZIP}').extractall('${OUTPUT_DIR}/system_media')"
else
    echo "WARNING: no system_media zip — release will lack built-in media"
fi

# 5. Create release zips — full (with system_media) + app-only (for updates).
# 5a. Full zip — for first-time users.  Includes system_media/.
echo "--- Creating full release archive ---"
FULL_ZIP="storyloom-v${VERSION}-${PLATFORM}"
$PYTHON -c "import shutil; shutil.make_archive('dist/$FULL_ZIP', 'zip', 'dist/storyloom-v${VERSION}')"

# 5b. App-only zip — for in-app updates.  Contains only app/ (the binary
#     payload).  Excludes the launcher (separate asset), wheel/sdist (PyPI
#     channel), and system_media/ (separate layer).
echo "--- Creating app-only release archive ---"
APP_ZIP="storyloom-app-v${VERSION}-${PLATFORM}"
$PYTHON -c "
import os, zipfile
root = 'dist/storyloom-v${VERSION}'
app_dir = os.path.join(root, 'app')
with zipfile.ZipFile('dist/$APP_ZIP.zip', 'w', zipfile.ZIP_DEFLATED) as zf:
    for dirpath, dirnames, filenames in os.walk(app_dir):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            arc = os.path.relpath(full, root)  # 'app/...'
            zf.write(full, arc)
            print(f'  + {arc}')
print(f'Wrote dist/$APP_ZIP.zip  ({os.path.getsize(\"dist/$APP_ZIP.zip\") / 1024 / 1024:.0f} MiB)')
"

echo ""
echo "=== Done ==="
echo "Release dir:  $OUTPUT_DIR"
echo "Full zip:     dist/${FULL_ZIP}.zip"
echo "App zip:      dist/${APP_ZIP}.zip"
echo "Launcher:     dist/Storyloom-v${LAUNCHER_VER}-${PLATFORM}.zip"
ls -lh "$OUTPUT_DIR/"

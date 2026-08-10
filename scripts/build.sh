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

VERSION=$($PYTHON -c "from storyloom import __version__; print(__version__)")
PYI_FLAGS=""
BIN_NAME="storyloom-web"
LAUNCHER_NAME="Storyloom"
OUTPUT_DIR="dist/storyloom-v${VERSION}"

# Platform-specific binary extension
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)  BIN_NAME="storyloom-web.exe"
                            LAUNCHER_NAME="Storyloom.exe" ;;
    Darwin)                ;;  # macOS: no extension
    Linux)                 ;;  # Linux: no extension
esac

echo "=== Storyloom Web UI Build v${VERSION} ==="

# 0. Clean previous build artifacts (dist + PyInstaller build cache only).
echo "--- Cleaning previous builds ---"
rm -rf build/ dist/*.whl dist/*.tar.gz dist/storyloom-web*

# 0b. Ensure background-removal model is available (u2netp.onnx, ~4.4 MB).
#     Bundled via --add-data into the main exe.  Downloaded once and cached.
MODEL_DIR="src/storyloom/models"
MODEL_FILE="$MODEL_DIR/u2netp.onnx"
MODEL_URL="https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2netp.onnx"
if [ ! -f "$MODEL_FILE" ]; then
    echo "--- Downloading u2netp.onnx (background removal model) ---"
    $PYTHON -c "
import urllib.request, os, sys
url = '${MODEL_URL}'
dest = '${MODEL_FILE}'
os.makedirs(os.path.dirname(dest), exist_ok=True)
try:
    urllib.request.urlretrieve(url, dest)
    print(f'  Downloaded {os.path.getsize(dest)} bytes')
except Exception as e:
    print(f'  WARNING: Download failed: {e}', file=sys.stderr)
    print('  Background removal will be unavailable.', file=sys.stderr)
    print(f'  Manual download: {url}', file=sys.stderr)
    print(f'  Place at: {dest}', file=sys.stderr)
"
fi

# 1. Install project + build tools (PyInstaller needs deps to discover imports)
echo "--- Installing project + build tools ---"
$PYTHON -m pip install -q -e ".[bg]" build pyinstaller wheel 2>/dev/null || \
    $PYTHON -m pip install -q --break-system-packages -e ".[bg]" build pyinstaller wheel

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

# PyInstaller --add-data separator: ':' on Linux/macOS, ';' on Windows.
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) ADD_SEP=";" ;;
    *)                     ADD_SEP=":" ;;
esac

# 3. PyInstaller single-file executable
echo "--- Building standalone executable ---"
$PYTHON -m PyInstaller --onefile $PYI_FLAGS \
    --name "$BIN_NAME" \
    --add-data "locale${ADD_SEP}locale" \
    --add-data "src/storyloom/web/static${ADD_SEP}storyloom/web/static" \
    --add-data "src/storyloom/core/lang_meta${ADD_SEP}storyloom/core/lang_meta" \
    --add-data "src/storyloom/models${ADD_SEP}storyloom/models" \
    --hidden-import uvicorn.loops.auto \
    --hidden-import uvicorn.protocols.http.auto \
    --hidden-import onnxruntime \
    --hidden-import numpy \
    src/storyloom/web/__main__.py

# 3b. Build Launcher — minimal PyInstaller exe (no --add-data)
echo "--- Building Launcher ---"
$PYTHON -m PyInstaller --onefile $PYI_FLAGS \
    --name "$LAUNCHER_NAME" \
    --clean \
    src/storyloom/launcher.py

# 4. Assemble release directory — ready-to-run structure for first install
#    app/ holds versioned files replaced on update: binary, locale, pip pkgs.
#    Shared root holds user data: config, saves, media, system_media.
echo "--- Assembling release directory ---"
mkdir -p "$OUTPUT_DIR/app"
cp "dist/$BIN_NAME" "$OUTPUT_DIR/app/"
cp "dist/$LAUNCHER_NAME" "$OUTPUT_DIR/$LAUNCHER_NAME"
cp -r locale "$OUTPUT_DIR/app/"
cp config.example.json "$OUTPUT_DIR/app/"
cp "dist/storyloom-${VERSION}-"*.whl "dist/storyloom-${VERSION}.tar.gz" "$OUTPUT_DIR/app/"

# System media — extract from filtered zip into release directory.
# Uses the same zip produced by pack_system_media.sh (skips thumbnails).
if [ -f "$SM_ZIP" ]; then
    echo "--- System media: extracting $SM_ZIP into release ---"
    $PYTHON -c "import zipfile; zipfile.ZipFile('${SM_ZIP}').extractall('${OUTPUT_DIR}')"
else
    echo "WARNING: no system_media zip — release will lack built-in media"
fi

# 5. Create zip for GitHub Release upload
echo "--- Creating release archive ---"
# Map platform to friendly name for release assets
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) PLATFORM="Windows" ;;
    Darwin)                PLATFORM="macOS" ;;
    Linux)                 PLATFORM="Linux" ;;
    *)                     PLATFORM="$(uname -s)" ;;
esac
ZIP_NAME="storyloom-v${VERSION}-${PLATFORM}"
ZIP_DIR="storyloom-v${VERSION}"
# root_dir=dist/$ZIP_DIR — no base_dir, so zip contents are at root
$PYTHON -c "import shutil; shutil.make_archive('dist/$ZIP_NAME', 'zip', 'dist/$ZIP_DIR')"

echo ""
echo "=== Done ==="
echo "Release dir:  $OUTPUT_DIR"
echo "GitHub asset: dist/${ZIP_NAME}.zip"
ls -lh "$OUTPUT_DIR/"

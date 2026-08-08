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
OUTPUT_DIR="dist/storyloom-web-v${VERSION}"

# Platform-specific binary extension
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)  BIN_NAME="storyloom-web.exe" ;;
    Darwin)                ;;  # macOS: no extension
    Linux)                 ;;  # Linux: no extension
esac

echo "=== Storyloom Web UI Build v${VERSION} ==="

# 0. Clean previous build artifacts
echo "--- Cleaning previous builds ---"
rm -rf build/ dist/*.whl dist/*.tar.gz dist/storyloom-web*
rm -f src/storyloom/models/*.onnx

# 1. Install project + build tools (PyInstaller needs deps to discover imports)
echo "--- Installing project + build tools ---"
$PYTHON -m pip install -q -e ".[bg]" build pyinstaller wheel 2>/dev/null || \
    $PYTHON -m pip install -q --break-system-packages -e ".[bg]" build pyinstaller wheel

# 2. pip packages (wheel + sdist)
#    i18n (.mo + frontend JS dict) compiled automatically by setup.py build hook
echo "--- Building pip packages ---"
$PYTHON -m build --no-isolation

# System media: use local copy or download from GitHub Release.
SM_VERSION="1.0.0"
SM_ZIP="system_media-v${SM_VERSION}.zip"
SM_URL="https://github.com/SiriLee/Storyloom/releases/download/v${VERSION}/${SM_ZIP}"

# Portable check: manifest exists AND both directories contain at least one PNG.
_has_media() {
    [ -f "system_media/_manifest.json" ] || return 1
    [ -f "system_media/VERSION" ] || return 1
    [ -n "$(find system_media/char_portrait -name '*.png' -print -quit 2>/dev/null)" ] || return 1
    [ -n "$(find system_media/background_img -name '*.png' -print -quit 2>/dev/null)" ] || return 1
}

if _has_media; then
    echo "--- System media: using local copy ---"
else
    echo "--- System media: downloading v${SM_VERSION} ---"
    # Local zip (from scripts/pack_system_media.sh) takes priority over download.
    if [ -f "$SM_ZIP" ]; then
        echo "  Using local $SM_ZIP"
    else
        $PYTHON -c "
import urllib.request, sys
try:
    urllib.request.urlretrieve('${SM_URL}', '${SM_ZIP}')
    print('  Downloaded ${SM_ZIP}')
except Exception as e:
    print(f'  WARNING: Download failed: {e}', file=sys.stderr)
    print('  Generate locally: python scripts/generate_system_assets.py', file=sys.stderr)
    sys.exit(1)
" || true  # continue build even if download fails
    fi
    if [ -f "$SM_ZIP" ]; then
        mkdir -p system_media
        $PYTHON -c "import zipfile; zipfile.ZipFile('${SM_ZIP}').extractall('system_media')"
        echo "  Extracted to system_media/"
    fi
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
    --add-data "system_media${ADD_SEP}system_media" \
    --hidden-import uvicorn.loops.auto \
    --hidden-import uvicorn.protocols.http.auto \
    --hidden-import onnxruntime \
    --hidden-import numpy \
    src/storyloom/web/__main__.py

# 4. Assemble release directory
echo "--- Assembling release directory ---"
mkdir -p "$OUTPUT_DIR"
cp "dist/$BIN_NAME" "$OUTPUT_DIR/"
cp -r locale "$OUTPUT_DIR/"
cp config.example.json "$OUTPUT_DIR/"
cp "dist/storyloom-${VERSION}-"*.whl "dist/storyloom-${VERSION}.tar.gz" "$OUTPUT_DIR/"

# 5. Create zip for GitHub Release upload
echo "--- Creating release archive ---"
# Map platform to friendly name for release assets
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) PLATFORM="Windows" ;;
    Darwin)                PLATFORM="macOS" ;;
    Linux)                 PLATFORM="Linux" ;;
    *)                     PLATFORM="$(uname -s)" ;;
esac
ZIP_NAME="storyloom-web-v${VERSION}-${PLATFORM}"
$PYTHON -c "import shutil; shutil.make_archive('dist/$ZIP_NAME', 'zip', 'dist', 'storyloom-web-v${VERSION}')"

echo ""
echo "=== Done ==="
echo "Release dir:  $OUTPUT_DIR"
echo "GitHub asset: dist/${ZIP_NAME}.zip"
ls -lh "$OUTPUT_DIR/"

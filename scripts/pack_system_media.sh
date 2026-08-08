#!/bin/bash
# Pack the system media source directory into a distributable zip.
#
# Reads from:  system_media_src/
# Outputs to:  system_media-v{version}.zip
#
# Usage:
#   bash scripts/pack_system_media.sh
#
# Prerequisites:
#   - system_media_src/VERSION exists with a semver string (e.g. "1.0.0")
#   - system_media_src/_manifest.json exists with matching version
#   - system_media_src/char_portrait/*.png and background_img/*.png
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SRC_DIR="$PROJECT_ROOT/system_media_src"

if [ ! -d "$SRC_DIR" ]; then
    echo "ERROR: system_media_src/ not found."
    echo "Create it with:"
    echo "  mkdir -p system_media_src/{char_portrait,background_img}"
    echo "  echo '1.0.0' > system_media_src/VERSION"
    echo "  # ... write _manifest.json and place .png files ..."
    exit 1
fi

if [ ! -f "$SRC_DIR/VERSION" ]; then
    echo "ERROR: system_media_src/VERSION not found."
    exit 1
fi

VERSION=$(cat "$SRC_DIR/VERSION" | tr -d '[:space:]')
if [ -z "$VERSION" ]; then
    echo "ERROR: system_media_src/VERSION is empty."
    exit 1
fi

if [ ! -f "$SRC_DIR/_manifest.json" ]; then
    echo "ERROR: system_media_src/_manifest.json not found."
    exit 1
fi

OUTPUT="$PROJECT_ROOT/system_media-v${VERSION}.zip"

echo "=== Packing system_media v${VERSION} ==="
echo "Source: $SRC_DIR"
echo "Output: $OUTPUT"

# -j: flatten paths — zip root contains VERSION, _manifest.json,
#     char_portrait/*.png, background_img/*.png
(cd "$SRC_DIR" && zip -r "$OUTPUT" . -x ".DS_Store" "*.gitkeep")

echo ""
echo "Done: $OUTPUT"
echo ""
echo "Next steps:"
echo "  1. Verify: unzip -l $OUTPUT"
echo "  2. Upload: gh release create system-assets-v${VERSION} \\"
echo "       --title 'System Media v${VERSION}' \\"
echo "       --notes 'System asset pack.' \\"
echo "       $OUTPUT"

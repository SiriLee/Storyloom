#!/bin/bash
# Download & extract the system media package from GitHub Releases.
#
# Usage:
#   bash scripts/setup_system_media.sh           # latest version
#   bash scripts/setup_system_media.sh v1.0.0    # specific version
#
# When no package is available yet, creates a minimal skeleton
# so the application can start without errors.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SYSTEM_DIR="$PROJECT_ROOT/system_media"
VERSION="${1:-latest}"

echo "=== Storyloom — System Media Setup ==="

# ── TODO: download from GitHub Releases when first package is published ──
# REPO="your-org/storyloom"
# if [ "$VERSION" = "latest" ]; then
#     gh release download --repo "$REPO" --pattern "system_media-*.zip" --dir "$PROJECT_ROOT"
# else
#     gh release download "$VERSION" --repo "$REPO" --pattern "system_media-$VERSION.zip" --dir "$PROJECT_ROOT"
# fi
# unzip -o "$PROJECT_ROOT/system_media-$VERSION.zip" -d "$PROJECT_ROOT"
# rm "$PROJECT_ROOT/system_media-$VERSION.zip"
# echo "System media $VERSION installed to system_media/"
# exit 0

# ── Skeleton fallback (no published package yet) ──
echo "No system media package published yet — creating empty skeleton."
mkdir -p "$SYSTEM_DIR/char_portrait" "$SYSTEM_DIR/background_img"

echo "0.0.0" > "$SYSTEM_DIR/VERSION"

cat > "$SYSTEM_DIR/_manifest.json" << 'EOF'
{
  "version": "0.0.0",
  "min_app_version": "1.3.0",
  "assets": {}
}
EOF

echo "system_media/ skeleton created (version 0.0.0)"
echo "Run this script again when a system media package is available."

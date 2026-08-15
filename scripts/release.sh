#!/usr/bin/env bash
# Release helper — publish the per-layer update manifests to GitHub Releases.
#
# The update checker reads these manifests from the release *download* CDN
# (never api.github.com).
#
# Run AFTER creating the GitHub releases (`gh release create vX.Y.Z`, and the
# persistent `system-media` / `launcher` tags).  Idempotent — `--clobber`
# overwrites a previously uploaded manifest for the same tag.
#
# Usage:
#   bash scripts/release.sh VERSION [NOTES_FILE]
#
#   VERSION      e.g. "2.3.0" (the app release tag is "v2.3.0")
#   NOTES_FILE   optional path to a markdown file with release notes
set -euo pipefail

REPO="SiriLee/Storyloom"
VERSION="${1:?usage: scripts/release.sh VERSION [NOTES_FILE]}"
NOTES_FILE="${2:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

mkdir -p "$ROOT/dist"

# ── 1. App manifest: update.json ─────────────────────────────────────
python3 - "$VERSION" "$NOTES_FILE" > "$ROOT/dist/update.json" <<'PY'
import json
import sys

version, notes_file = sys.argv[1], sys.argv[2]
notes = ""
if notes_file:
    with open(notes_file, "r", encoding="utf-8") as f:
        notes = f.read().strip()
print(json.dumps({"version": version, "notes": notes}, ensure_ascii=False, indent=2))
PY

gh release upload "v$VERSION" "$ROOT/dist/update.json" \
    --repo "$REPO" --clobber

# ── 2. system_media manifest: _manifest.json ─────────────────────────
if [ -f "$ROOT/system_media/_manifest.json" ]; then
    gh release upload "system-media" "$ROOT/system_media/_manifest.json" \
        --repo "$REPO" --clobber
else
    echo "WARNING: system_media/_manifest.json not found — skipping" >&2
fi

# ── 3. launcher manifest: VERSION (plain text) ───────────────────────
if [ -f "$ROOT/launcher.version" ]; then
    cp "$ROOT/launcher.version" "$ROOT/dist/VERSION"
    gh release upload "launcher" "$ROOT/dist/VERSION" \
        --repo "$REPO" --clobber
else
    echo "WARNING: launcher.version not found — skipping" >&2
fi

echo "Update manifests published for v$VERSION"

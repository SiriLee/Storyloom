#!/usr/bin/env bash
# Pack system_media/ into a distributable zip for GitHub Release.
#
# Reads from:  system_media/ (generated assets + _manifest.json)
# Outputs:     system_media-v{version}.zip
#
# Usage:
#   bash scripts/pack_system_media.sh
#   bash scripts/pack_system_media.sh --skip-check   (emergency bypass)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MEDIA_DIR="$PROJECT_ROOT/system_media"
SRC_DIR="$PROJECT_ROOT/system_media_src"
MANIFEST="$MEDIA_DIR/_manifest.json"
VERSION_FILE="$MEDIA_DIR/VERSION"

SKIP_CHECK=false
if [[ "${1:-}" == "--skip-check" ]]; then
    SKIP_CHECK=true
fi

# ── Prerequisites ───────────────────────────────────────────────────
if [[ ! -f "$MANIFEST" ]]; then
    echo "ERROR: _manifest.json not found." >&2
    echo "  Run:  python scripts/generate_manifest.py" >&2; exit 1
fi
if [[ ! -f "$VERSION_FILE" ]]; then
    echo "ERROR: VERSION not found." >&2; exit 1
fi

VER=$(head -1 "$VERSION_FILE" | tr -d '[:space:]')
if [[ -z "$VER" ]]; then
    echo "ERROR: VERSION is empty." >&2; exit 1
fi

echo "=== Packing system_media v${VER} ==="
echo "Source: $MEDIA_DIR"
echo

# ── Consistency check ───────────────────────────────────────────────
if ! $SKIP_CHECK; then
    echo "--- Consistency check ---"
    python3 - "$MEDIA_DIR" "$SRC_DIR" << 'PYEOF'
import json, os, sys

media = sys.argv[1]
src_d = sys.argv[2]

manifest = json.load(open(os.path.join(media, "_manifest.json")))
ok = True

for atype_key, src_fname in [
    ("char_portrait", "char_portrait.json"),
    ("background_img", "background_img.json"),
]:
    src = json.load(open(os.path.join(src_d, src_fname)))
    m_ids = set(manifest["assets"][atype_key])
    s_ids = set(src)
    subdir = os.path.join(media, atype_key)
    # Disk has thumbnails (_thumb, _thumb_560) alongside base PNGs —
    # strip suffixes so only base IDs are compared against the manifest.
    # Use os.path.splitext to handle both .png and .webp extensions.
    _all = {os.path.splitext(f)[0] for f in os.listdir(subdir)} if os.path.isdir(subdir) else set()
    _base = {r.replace("_thumb_560", "").replace("_thumb", "") for r in _all}
    _unknown = {e for e in (_all - m_ids)
                if not e.endswith("_thumb")
                and not e.endswith("_thumb_560")}

    print(f"  {atype_key}: manifest={len(m_ids)}"
          f"  source={len(s_ids)}  files={len(_all)}")

    if m_ids != s_ids:
        print(f"  ERROR: manifest != source", file=sys.stderr)
        if m_ids - s_ids:
            print(f"    In manifest but not source: {sorted(m_ids - s_ids)}",
                  file=sys.stderr)
        if s_ids - m_ids:
            print(f"    In source but not manifest: {sorted(s_ids - m_ids)}",
                  file=sys.stderr)
        ok = False
    missing = m_ids - _base
    if missing:
        print(f"  ERROR: missing on disk — {sorted(missing)}", file=sys.stderr)
        ok = False
    if _unknown:
        print(f"  WARNING: unexpected files on disk — {sorted(_unknown)}",
              file=sys.stderr)
    for aid in m_ids & s_ids:
        if manifest["assets"][atype_key][aid]["name"] != src[aid]["name"]:
            print(f"  ERROR: {aid} name mismatch", file=sys.stderr)
            ok = False

if not ok:
    print("\nERROR: Consistency check failed.", file=sys.stderr)
    print("  Re-run: python scripts/generate_manifest.py", file=sys.stderr)
    print("  Bypass: bash scripts/pack_system_media.sh --skip-check", file=sys.stderr)
    sys.exit(1)
print("  All consistent.")
PYEOF
    echo
else
    echo "--- Consistency check SKIPPED ---"
    echo
fi

# ── Build zip (pure Python — no system 'zip' dependency) ────────────
ARCHIVE_NAME="system_media-v${VER}.zip"
ARCHIVE_PATH="$PROJECT_ROOT/$ARCHIVE_NAME"

python3 - "$MEDIA_DIR" "$ARCHIVE_PATH" << 'PYEOF'
import sys, os
from zipfile import ZipFile, ZIP_DEFLATED

media = sys.argv[1]
archive = sys.argv[2]

with ZipFile(archive, "w", ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(media):
        for fn in files:
            # Skip runtime-generated thumbnails — the app generates
            # these on first request and caches them to disk.
            # See server.py serve_media() line 130-132.
            base, ext = os.path.splitext(fn)
            if base.endswith("_thumb") or base.endswith("_thumb_560"):
                continue
            full = os.path.join(root, fn)
            arcname = os.path.relpath(full, media)
            zf.write(full, arcname)
            print(f"  + {arcname}")

print()
print(f"Wrote {archive}  ({os.path.getsize(archive) / 1024 / 1024:.0f} MiB)")
PYEOF

echo
echo "Done."
echo "  $ARCHIVE_PATH"
echo
echo "Upload:"
echo "  gh release create v{app_version} --title 'v{app_version} — System Assets' $ARCHIVE_NAME"
echo "  # or for existing release:"
echo "  gh release upload v{app_version} $ARCHIVE_NAME"

"""UpdateManager — version checking, download, and extraction for auto-updates.

Spec: docs/superpowers/specs/2026-08-10-auto-update-design.md §4
"""
import json
import os
import re
import shutil
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from urllib.request import Request, urlopen


# ── Config ────────────────────────────────────────────────────────

GITHUB_API_RELEASES = (
    "https://api.github.com/repos/SiriLee/Storyloom/releases/latest"
)
CACHE_SECONDS = 900  # 15 minutes

# Per spec §4.3
if sys.platform == "win32":
    _PLATFORM = "Windows"
elif sys.platform == "darwin":
    _PLATFORM = "macOS"
else:
    _PLATFORM = "Linux"

# ── Cache ─────────────────────────────────────────────────────────

_cache: dict = {"ts": 0, "data": None}


# ── Data types ────────────────────────────────────────────────────


@dataclass
class VersionInfo:
    """Version information for one update layer."""

    current: str  # "1.3.0"
    latest: str   # "1.4.0" (empty if no update or offline)
    release_notes: str = ""
    asset_url: str = ""  # direct download URL for the release asset
    has_update: bool = field(default=False, init=False)

    def __post_init__(self):
        if self.latest and self.asset_url:
            self.has_update = _version_gt(self.latest, self.current)


@dataclass
class UpdateCheckResult:
    """Result of checking all update layers."""

    app: VersionInfo
    system_media: VersionInfo


@dataclass
class UpdateProgress:
    """Progress event for a single-layer update operation."""

    layer: str   # "app" | "system_media"
    stage: str   # "downloading" | "extracting" | "done" | "error"
    received: int = 0
    total: int | None = None
    error: str | None = None


# ── Semver helpers ────────────────────────────────────────────────


def _version_gt(a: str, b: str) -> bool:
    """Compare two semver strings.  Returns True if *a* > *b*."""

    def parse(v: str) -> tuple:
        v = v.lstrip("v")
        parts = v.split("-")[0].split(".")
        return tuple(int(p) for p in parts if p.isdigit())

    try:
        return parse(a) > parse(b)
    except (ValueError, IndexError):
        return False


# ── GitHub API helpers ────────────────────────────────────────────


def _http_get_json(url: str) -> dict:
    """GET JSON from a URL.  Raises on HTTP errors or connection failure."""
    req = Request(url, headers={"Accept": "application/vnd.github+json"})
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _parse_version_from_tag(tag: str) -> str:
    """'v1.4.0' → '1.4.0'"""
    return tag.lstrip("v")


def _parse_version_from_asset_name(name: str, prefix: str) -> str | None:
    """Extract version from asset filename.

    E.g. 'system_media-v1.2.0.zip', prefix='system_media-v' → '1.2.0'
    """
    pattern = re.escape(prefix) + r"(\d+\.\d+\.\d+)"
    m = re.search(pattern, name)
    return m.group(1) if m else None


def _find_asset_url(
    assets: list, pattern: str, platform_specific: bool = True
) -> tuple[str | None, str | None]:
    """Find an asset by name pattern.  Returns (url, version) or (None, None).

    If *platform_specific*, matches ``{pattern}*{_PLATFORM}*`` first.
    Falls back to matching ``{pattern}*`` without platform.
    """
    # First pass: with platform (for platform-specific assets)
    if platform_specific:
        for a in assets:
            name = a.get("name", "")
            if pattern in name and _PLATFORM in name:
                ver = _parse_version_from_asset_name(name, pattern)
                return a.get("browser_download_url"), ver
        return None, None  # never fall through to wrong platform
    # Platform-agnostic pass
    for a in assets:
        name = a.get("name", "")
        if pattern in name:
            ver = _parse_version_from_asset_name(name, pattern)
            return a.get("browser_download_url"), ver
    return None, None


# ── Download ──────────────────────────────────────────────────────


def _download_file(url: str, dest: str, progress_callback=None) -> None:
    """Stream download with optional per-chunk progress reporting.

    *progress_callback* receives (received_bytes: int, total_bytes: int | None).
    """
    req = Request(url, headers={"Accept": "application/octet-stream"})
    with urlopen(req, timeout=120) as resp:
        total = resp.headers.get("Content-Length")
        total = int(total) if total else None
        received = 0
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                received += len(chunk)
                if progress_callback:
                    progress_callback(received, total)


# ── Public API ────────────────────────────────────────────────────


def check_for_updates(
    app_version: str,
    system_media_version: str,
    *,
    force: bool = False,
) -> UpdateCheckResult:
    """Check GitHub Releases for available updates.

    Args:
        app_version: Current app version (``storyloom.__version__``).
        system_media_version: Current system_media version (from ``VERSION`` file).
        force: Bypass cache.

    Returns:
        ``UpdateCheckResult`` with version info for each layer.
        On network errors, both layers return empty ``latest`` strings.
    """
    global _cache

    now = time.time()
    if not force and _cache["data"] is not None and (now - _cache["ts"]) < CACHE_SECONDS:
        return _cache["data"]

    try:
        release = _http_get_json(GITHUB_API_RELEASES)
    except Exception:
        result = UpdateCheckResult(
            app=VersionInfo(current=app_version, latest=""),
            system_media=VersionInfo(current=system_media_version, latest=""),
        )
        _cache = {"ts": now, "data": result}
        return result

    assets = release.get("assets", [])
    release_notes = release.get("body", "")

    remote_tag = release.get("tag_name", "")
    remote_app_ver = _parse_version_from_tag(remote_tag)

    app_url, _ = _find_asset_url(
        assets, "storyloom-v", platform_specific=True
    )
    sm_url, remote_sm_ver = _find_asset_url(
        assets, "system_media-v", platform_specific=False
    )

    result = UpdateCheckResult(
        app=VersionInfo(
            current=app_version,
            latest=remote_app_ver,
            release_notes=release_notes,
            asset_url=app_url or "",
        ),
        system_media=VersionInfo(
            current=system_media_version,
            latest=remote_sm_ver or "",
            asset_url=sm_url or "",
        ),
    )

    _cache = {"ts": now, "data": result}
    return result


def download_and_extract(
    layer: str,
    url: str,
    target_root: str,
    progress_callback=None,
) -> None:
    """Download a release zip and extract it to *target_root*.

    Args:
        layer: ``"app"`` or ``"system_media"`` — determines extraction strategy.
        url: Download URL.
        target_root: Root directory for extraction.
        progress_callback: ``callable(UpdateProgress)`` for progress events.

    For ``layer="app"``: zip contains ``app_new/`` (and optionally
    ``launcher.new``).  Extracts to ``<target_root>/app_new/``, deleting
    any stale ``app_new/`` first.

    For ``layer="system_media"``: zip contents extracted directly into
    *target_root*, overwriting existing files.
    """
    tmp_dir = tempfile.mkdtemp(prefix="storyloom_update_")
    zip_path = os.path.join(tmp_dir, "update.zip")

    def _emit(stage: str, received: int = 0, total: int | None = None):
        if progress_callback:
            progress_callback(
                UpdateProgress(
                    layer=layer,
                    stage=stage,
                    received=received,
                    total=total,
                )
            )

    try:
        _emit("downloading")

        def _dl_cb(received: int, total: int | None):
            _emit("downloading", received=received, total=total)

        _download_file(url, zip_path, progress_callback=_dl_cb)

        _emit("extracting")

        if layer == "app":
            app_new = os.path.join(target_root, "app_new")
            if os.path.isdir(app_new):
                shutil.rmtree(app_new)

            extract_tmp = os.path.join(tmp_dir, "extract")
            os.makedirs(extract_tmp, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_tmp)

            src = os.path.join(extract_tmp, "app_new")
            if os.path.isdir(src):
                shutil.move(src, app_new)
            else:
                raise ValueError(
                    "Update zip does not contain app_new/ directory"
                )

            launcher_new = os.path.join(extract_tmp, "launcher.new")
            if os.path.isfile(launcher_new):
                shutil.copy2(
                    launcher_new, os.path.join(target_root, "launcher.new")
                )

            if not os.path.isfile(
                os.path.join(app_new, "storyloom-web")
            ) and not os.path.isfile(
                os.path.join(app_new, "storyloom-web.exe")
            ):
                raise ValueError(
                    "Extracted app_new/ missing storyloom-web executable"
                )

        else:  # system_media
            os.makedirs(target_root, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    # Guard against zip-slip path traversal
                    member_path = os.path.normpath(
                        os.path.join(target_root, member.filename)
                    )
                    if not member_path.startswith(
                        os.path.normpath(target_root) + os.sep
                    ) and member_path != os.path.normpath(target_root):
                        raise ValueError(
                            f"Rejected path outside target: {member.filename}"
                        )
                    zf.extract(member, target_root)

            version_file = os.path.join(target_root, "VERSION")
            if not os.path.isfile(version_file):
                raise ValueError(
                    "Extracted system_media missing VERSION file"
                )

        _emit("done")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

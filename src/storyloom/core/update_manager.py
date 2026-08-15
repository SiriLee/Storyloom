"""UpdateManager — version checking, download, and extraction for auto-updates.
"""
import json
import os
import shutil
import socket
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener

from storyloom.config import (
    GITHUB_DOWNLOAD_BASE,
    GITHUB_RELEASES_URL,
    LAUNCHER_MANIFEST_FILENAME,
    LAUNCHER_TAG,
    SYSTEM_MEDIA_MANIFEST_FILENAME,
    SYSTEM_MEDIA_TAG,
    UPDATE_MANIFEST_FILENAME,
)


# ── Config ────────────────────────────────────────────────────────

# Per-layer manifest URLs, served by the release *download* CDN (not the
# rate-limited REST API).  Underlying constants live in config.py.
_APP_MANIFEST_URL = (
    f"{GITHUB_RELEASES_URL}/latest/download/{UPDATE_MANIFEST_FILENAME}"
)
_SYSTEM_MEDIA_MANIFEST_URL = (
    f"{GITHUB_DOWNLOAD_BASE}/{SYSTEM_MEDIA_TAG}/{SYSTEM_MEDIA_MANIFEST_FILENAME}"
)
_LAUNCHER_MANIFEST_URL = (
    f"{GITHUB_DOWNLOAD_BASE}/{LAUNCHER_TAG}/{LAUNCHER_MANIFEST_FILENAME}"
)
CACHE_SECONDS = 900  # 15 minutes

# Per spec §4.3
if sys.platform == "win32":
    _PLATFORM = "Windows"
elif sys.platform == "darwin":
    _PLATFORM = "macOS"
else:
    _PLATFORM = "Linux"

# ── Proxy ─────────────────────────────────────────────────────────

_proxy_url: str = ""


def set_update_proxy_url(url: str) -> None:
    """Set the proxy URL for update-related HTTP requests.

    Call once at startup with ``UserConfig.proxy_url`` and again whenever
    the user changes the proxy setting.  Pass ``""`` to clear.
    """
    global _proxy_url
    _proxy_url = url.strip() if url else ""


def _get_opener():
    """Return a urllib opener, with proxy if configured."""
    if _proxy_url:
        return build_opener(ProxyHandler({
            "https": _proxy_url,
            "http": _proxy_url,
        }))
    return build_opener()


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
    # Error category when the version check failed ("" = ok):
    # rate_limit | timeout | network | http | not_found | parse | unknown.
    error: str = ""
    has_update: bool = field(default=False, init=False)

    def __post_init__(self):
        if self.latest and self.asset_url:
            self.has_update = _version_gt(self.latest, self.current)


@dataclass
class UpdateCheckResult:
    """Result of checking all update layers."""

    app: VersionInfo
    system_media: VersionInfo
    launcher: VersionInfo


@dataclass
class UpdateProgress:
    """Progress event for a single-layer update operation."""

    layer: str   # "app" | "launcher" | "system_media"
    stage: str   # "downloading" | "extracting" | "done" | "error"
    received: int = 0
    total: int | None = None
    error: str | None = None


# ── Semver helpers ────────────────────────────────────────────────


def _version_tuple(v: str) -> tuple:
    """Parse a semver string into a comparable tuple.

    Strips an optional ``v`` prefix and any pre-release suffix
    (``1.2.3-rc1`` → ``(1, 2, 3)``).  Returns an empty tuple for
    unparseable input.
    """
    v = v.lstrip("v")
    parts = v.split("-")[0].split(".")
    return tuple(int(p) for p in parts if p.isdigit())


def _version_gt(a: str, b: str) -> bool:
    """Compare two semver strings.  Returns True if *a* > *b*."""
    return _version_tuple(a) > _version_tuple(b)


# ── HTTP helpers ──────────────────────────────────────────────────


def _http_get_json(url: str) -> dict:
    """GET JSON from a URL.  Raises on HTTP errors or connection failure."""
    req = Request(url, headers={"Accept": "application/json"})
    with _get_opener().open(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get_text(url: str) -> str:
    """GET a plain-text body (e.g. the launcher ``VERSION`` asset)."""
    req = Request(url, headers={"Accept": "text/plain"})
    with _get_opener().open(req, timeout=15) as resp:
        return resp.read().decode("utf-8").strip()


def _classify_error(exc: Exception) -> str:
    """Map an HTTP/network exception to a short error category.

    Categories: ``rate_limit``, ``timeout``, ``network``, ``http``,
    ``not_found``, ``parse``, ``unknown``.
    """
    if isinstance(exc, HTTPError):
        if exc.code == 404:
            return "not_found"
        if exc.code in (403, 429):  # e.g. an upstream proxy or CDN throttle
            return "rate_limit"
        return "http"
    if isinstance(exc, TimeoutError):  # socket.timeout is an alias
        return "timeout"
    if isinstance(exc, URLError):
        if isinstance(exc.reason, TimeoutError):
            return "timeout"
        return "network"
    if isinstance(exc, ValueError):  # includes json.JSONDecodeError
        return "parse"
    return "unknown"


def _download_url(layer: str, version: str) -> str:
    """Deterministic asset URL for a layer, derived from tag + version.

    Asset names are fixed by ``scripts/build.sh`` — no need to query the
    REST API to discover them.  ``releases/download/…`` 302s to the CDN.
    """
    if layer == "app":
        return (
            f"{GITHUB_DOWNLOAD_BASE}/v{version}/"
            f"storyloom-app-v{version}-{_PLATFORM}.zip"
        )
    if layer == "system_media":
        return f"{GITHUB_DOWNLOAD_BASE}/{SYSTEM_MEDIA_TAG}/system_media-v{version}.zip"
    if layer == "launcher":
        return (
            f"{GITHUB_DOWNLOAD_BASE}/{LAUNCHER_TAG}/"
            f"storyloom-launcher-v{version}-{_PLATFORM}.zip"
        )
    raise ValueError(f"Unknown layer: {layer!r}")


# ── Download ──────────────────────────────────────────────────────


def _download_file(url: str, dest: str, progress_callback=None) -> None:
    """Stream download with optional per-chunk progress reporting.

    *progress_callback* receives (received_bytes: int, total_bytes: int | None).
    """
    req = Request(url, headers={"Accept": "application/octet-stream"})
    with _get_opener().open(req, timeout=120) as resp:
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


def _check_app_update(app_version: str) -> VersionInfo:
    """Read the app ``update.json`` manifest from the ``latest`` release.

    Returns a ``VersionInfo`` with ``latest=""`` on any error (offline,
    manifest missing, etc.) so one layer's failure never blocks the other.
    The error category is recorded in ``VersionInfo.error``.
    """
    try:
        manifest = _http_get_json(_APP_MANIFEST_URL)
    except Exception as exc:
        return VersionInfo(
            current=app_version, latest="", error=_classify_error(exc)
        )

    remote_ver = str(manifest.get("version", "")).lstrip("v")
    release_notes = manifest.get("notes", "") or manifest.get("body", "")

    return VersionInfo(
        current=app_version,
        latest=remote_ver,
        release_notes=release_notes,
        asset_url=_download_url("app", remote_ver) if remote_ver else "",
    )


def _check_system_media_update(system_media_version: str) -> VersionInfo:
    """Read the ``_manifest.json`` asset from the ``system-media`` tag.

    The manifest already carries ``version`` (and ``min_app_version``),
    so it doubles as the remote version source — no separate version
    asset needed.  A 404 (manifest not yet uploaded as a standalone
    asset) is treated as "no update" rather than an error.
    """
    try:
        manifest = _http_get_json(_SYSTEM_MEDIA_MANIFEST_URL)
    except Exception as exc:
        err = _classify_error(exc)
        if err == "not_found":
            return VersionInfo(current=system_media_version, latest="")
        return VersionInfo(
            current=system_media_version, latest="", error=err
        )

    remote_ver = str(manifest.get("version", "")).lstrip("v")

    return VersionInfo(
        current=system_media_version,
        latest=remote_ver,
        asset_url=_download_url("system_media", remote_ver) if remote_ver else "",
    )


def _check_launcher_update(launcher_version: str) -> VersionInfo:
    """Read the ``VERSION`` asset from the ``launcher`` tag.

    The launcher is versioned independently of the app and is only bumped
    when ``launcher.py`` itself changes.

    When no launcher is installed (wheel users, or a missing
    ``launcher.version`` file), the layer is not applicable — return an
    empty ``VersionInfo`` so the UI never shows a spurious update.
    """
    if not launcher_version:
        return VersionInfo(current="", latest="")

    try:
        remote_ver = _http_get_text(_LAUNCHER_MANIFEST_URL).lstrip("v")
    except Exception as exc:
        err = _classify_error(exc)
        if err == "not_found":
            return VersionInfo(current=launcher_version, latest="")
        return VersionInfo(
            current=launcher_version, latest="", error=err
        )

    return VersionInfo(
        current=launcher_version,
        latest=remote_ver,
        asset_url=_download_url("launcher", remote_ver) if remote_ver else "",
    )


def check_for_updates(
    app_version: str,
    system_media_version: str,
    launcher_version: str,
    *,
    force: bool = False,
) -> UpdateCheckResult:
    """Check for available updates across the three update layers.

    Each layer reads a small manifest file served by the GitHub release
    *download* CDN — never the rate-limited REST API:
      - app: ``releases/latest/download/update.json``
      - system_media: ``releases/download/system-media/_manifest.json``
      - launcher: ``releases/download/launcher/VERSION``

    Each layer fails independently — a network error on one never
    prevents the other from reporting results.

    Args:
        app_version: Current app version (``storyloom.__version__``).
        system_media_version: Current system_media version (from ``VERSION`` file).
        launcher_version: Current launcher version (from ``launcher.version`` file).
        force: Bypass cache.

    Returns:
        ``UpdateCheckResult`` with version info for each layer.
    """
    global _cache

    now = time.time()
    if not force and _cache["data"] is not None and (now - _cache["ts"]) < CACHE_SECONDS:
        return _cache["data"]

    result = UpdateCheckResult(
        app=_check_app_update(app_version),
        system_media=_check_system_media_update(system_media_version),
        launcher=_check_launcher_update(launcher_version),
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
        layer: ``"app"``, ``"launcher"``, or ``"system_media"`` — determines
            the extraction strategy.
        url: Download URL.
        target_root: Root directory for extraction.
        progress_callback: ``callable(UpdateProgress)`` for progress events.

    For ``layer="app"``: zip contains ``app/``.  Extracts to
    ``<target_root>/app_new/``, deleting any stale ``app_new/`` first.

    For ``layer="launcher"``: zip contains the launcher binary
    (``Storyloom``/``Storyloom.exe``) and ``launcher.version``.  Stages
    them as ``<target_root>/launcher.new`` and ``launcher.version`` for
    the launcher's self-replace on next start.

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

            # The release zip ships with "app/" (ready-to-run).
            # For an in-place update we rename it to "app_new/"
            # so the launcher can atomically swap it in.
            src = os.path.join(extract_tmp, "app")
            if os.path.isdir(src):
                shutil.move(src, app_new)
            else:
                raise ValueError(
                    "Update zip does not contain app/ directory"
                )

            if not os.path.isfile(
                os.path.join(app_new, "storyloom-web")
            ) and not os.path.isfile(
                os.path.join(app_new, "storyloom-web.exe")
            ):
                raise ValueError(
                    "Extracted app_new/ missing storyloom-web executable"
                )

        elif layer == "launcher":
            os.makedirs(target_root, exist_ok=True)
            extract_tmp = os.path.join(tmp_dir, "extract")
            os.makedirs(extract_tmp, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_tmp)

            # Stage the launcher binary + version file for the launcher's
            # self-replace on next start (see launcher.py).
            staged = False
            for candidate in ("Storyloom", "Storyloom.exe"):
                p = os.path.join(extract_tmp, candidate)
                if os.path.isfile(p):
                    shutil.copy2(
                        p, os.path.join(target_root, "launcher.new")
                    )
                    staged = True
                    break
            if not staged:
                raise ValueError("Launcher zip missing Storyloom binary")

            version_src = os.path.join(extract_tmp, "launcher.version")
            if os.path.isfile(version_src):
                shutil.copy2(
                    version_src,
                    os.path.join(target_root, "launcher.version"),
                )

        elif layer == "system_media":
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

        else:
            raise ValueError(f"Unknown layer: {layer!r}")

        _emit("done")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def regenerate_launcher(target_dir: str) -> bool:
    """Download and extract just the Launcher binary from the launcher asset.

    Used by ``--regenerate-launcher`` to recover a deleted ``Storyloom`` /
    ``Storyloom.exe`` without downloading the full app update.

    Args:
        target_dir: Directory to place the launcher binary (typically
                    the app root — parent of ``app/``).

    Returns:
        ``True`` if the launcher was restored successfully.
    """
    launcher_name = "Storyloom.exe" if sys.platform == "win32" else "Storyloom"
    tmp_dir = tempfile.mkdtemp(prefix="storyloom_launcher_")
    zip_path = os.path.join(tmp_dir, "release.zip")

    try:
        # Get the download URL for the latest platform-specific launcher asset.
        info = _check_launcher_update("0.0.0")  # dummy version — we need the URL
        if not info.asset_url:
            print(
                "Error: could not find download URL for launcher asset",
                file=sys.stderr,
            )
            return False

        print(f"Downloading launcher from {info.asset_url} ...")
        _download_file(info.asset_url, zip_path)

        extract_tmp = os.path.join(tmp_dir, "extract")
        os.makedirs(extract_tmp, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_tmp)

        # The launcher asset zip ships "Storyloom" / "Storyloom.exe" at root.
        src = os.path.join(extract_tmp, launcher_name)
        if not os.path.isfile(src):
            print(
                f"Error: {launcher_name} not found in launcher asset",
                file=sys.stderr,
            )
            return False

        dest = os.path.join(target_dir, launcher_name)
        shutil.copy2(src, dest)
        if sys.platform != "win32":
            os.chmod(dest, 0o755)

        # Restore the version file too so future update checks compare
        # against the correct local version.
        version_src = os.path.join(extract_tmp, "launcher.version")
        if os.path.isfile(version_src):
            shutil.copy2(
                version_src, os.path.join(target_dir, "launcher.version")
            )

        print(f"Launcher restored: {dest}")
        return True

    except Exception as exc:
        print(f"Error: failed to restore launcher: {exc}", file=sys.stderr)
        return False

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

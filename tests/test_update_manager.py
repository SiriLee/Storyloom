"""Tests for UpdateManager — data types, version check, download, extraction."""
import os
import socket
import sys
import tempfile
import zipfile
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import pytest

from storyloom.core.update_manager import (
    CACHE_SECONDS,
    UpdateCheckResult,
    UpdateProgress,
    VersionInfo,
    _download_url,
    _version_gt,
    check_for_updates,
    download_and_extract,
    regenerate_launcher,
)


# ── Data model tests ──────────────────────────────────────────────


def test_version_info_no_update():
    v = VersionInfo(current="1.3.0", latest="1.3.0")
    assert v.has_update is False


def test_version_info_has_update():
    v = VersionInfo(current="1.3.0", latest="1.4.0",
                    asset_url="https://example.com/a.zip")
    assert v.has_update is True


def test_version_info_has_update_no_asset_url():
    """No downloadable asset → has_update stays False even if version newer."""
    v = VersionInfo(current="1.3.0", latest="1.4.0")
    assert v.has_update is False


def test_version_info_current_newer():
    v = VersionInfo(current="1.5.0-dev", latest="1.4.0")
    assert v.has_update is False


def test_version_info_empty_latest():
    v = VersionInfo(current="1.3.0", latest="")
    assert v.has_update is False


def test_version_gt_basic():
    assert _version_gt("1.4.0", "1.3.0") is True
    assert _version_gt("1.3.0", "1.4.0") is False
    assert _version_gt("1.3.0", "1.3.0") is False


def test_version_gt_with_v_prefix():
    assert _version_gt("v1.4.0", "v1.3.0") is True


def test_version_gt_prerelease():
    assert _version_gt("1.4.0", "1.5.0-dev") is False
    assert _version_gt("2.0.0", "1.99.99") is True


def test_version_gt_invalid():
    assert _version_gt("abc", "1.0.0") is False


# ── Error classification ──────────────────────────────────────────


def test_classify_http_errors():
    from storyloom.core.update_manager import _classify_error
    assert _classify_error(HTTPError("u", 403, "Forbidden", None, None)) == "rate_limit"
    assert _classify_error(HTTPError("u", 429, "Too Many", None, None)) == "rate_limit"
    assert _classify_error(HTTPError("u", 404, "Not Found", None, None)) == "not_found"
    assert _classify_error(HTTPError("u", 500, "Internal", None, None)) == "http"


def test_classify_timeout():
    from storyloom.core.update_manager import _classify_error
    assert _classify_error(TimeoutError()) == "timeout"
    assert _classify_error(URLError(socket.timeout())) == "timeout"


def test_classify_network_and_parse():
    from storyloom.core.update_manager import _classify_error
    assert _classify_error(URLError("connection refused")) == "network"
    assert _classify_error(ValueError("bad json")) == "parse"
    assert _classify_error(RuntimeError("boom")) == "unknown"


# ── Deterministic download URL ────────────────────────────────────


def test_download_url_app():
    url = _download_url("app", "1.4.0")
    plat = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    assert url == (
        "https://github.com/SiriLee/Storyloom/releases/download/"
        f"v1.4.0/storyloom-app-v1.4.0-{plat}.zip"
    )


def test_download_url_system_media():
    url = _download_url("system_media", "1.2.0")
    assert url == (
        "https://github.com/SiriLee/Storyloom/releases/download/"
        "system-media/system_media-v1.2.0.zip"
    )


def test_download_url_launcher():
    url = _download_url("launcher", "1.1.0")
    plat = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    assert url == (
        "https://github.com/SiriLee/Storyloom/releases/download/"
        f"launcher/storyloom-launcher-v1.1.0-{plat}.zip"
    )


def test_download_url_unknown_layer():
    with pytest.raises(ValueError):
        _download_url("nope", "1.0.0")


# ── Version check (manifest model) ────────────────────────────────


def _app_manifest(version="1.4.0", notes="## notes"):
    """Mock the app ``update.json`` manifest."""
    return {"version": version, "notes": notes}


def _sm_manifest(version="1.2.0"):
    """Mock the system_media ``_manifest.json`` manifest."""
    return {"version": version, "min_app_version": "1.3.0"}


def _route_json(mock_json, *, app, sm):
    """Route ``_http_get_json`` by URL substring: app vs system_media."""
    def dispatch(url):
        if "system-media" in url:
            return sm
        return app
    mock_json.side_effect = dispatch


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_error_category_propagates(mock_text, mock_json):
    """App layer failure records its category; sm/launcher remain ok."""
    mock_text.return_value = "1.0.0"

    def _dispatch(url):
        if "system-media" in url:
            return _sm_manifest()
        raise URLError("connection refused")

    mock_json.side_effect = _dispatch
    result = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=True)
    assert result.app.error == "network"
    assert result.app.has_update is False
    assert result.system_media.error == ""
    assert result.launcher.error == ""


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_404_manifest_is_not_error(mock_text, mock_json):
    """Missing sm/launcher manifest → no update, no error; app ok."""
    mock_text.side_effect = HTTPError("u", 404, "Not Found", None, None)

    def _dispatch(url):
        if "system-media" in url:
            raise HTTPError(url, 404, "Not Found", None, None)
        return _app_manifest(version="1.3.0")

    mock_json.side_effect = _dispatch
    result = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=True)
    assert result.system_media.error == ""
    assert result.system_media.latest == ""
    assert result.system_media.has_update is False
    assert result.launcher.error == ""
    assert result.launcher.has_update is False


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_no_update(mock_text, mock_json):
    _route_json(mock_json, app=_app_manifest("1.3.0"), sm=_sm_manifest("1.1.0"))
    mock_text.return_value = "1.0.0"
    result = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=True)
    assert result.app.has_update is False
    assert result.system_media.has_update is False
    assert result.launcher.has_update is False


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_app_update(mock_text, mock_json):
    _route_json(mock_json, app=_app_manifest("1.4.0"), sm=_sm_manifest("1.1.0"))
    mock_text.return_value = "1.0.0"
    result = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=True)
    assert result.app.has_update is True
    assert result.app.latest == "1.4.0"
    assert result.app.asset_url == _download_url("app", "1.4.0")
    assert result.app.release_notes == "## notes"


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_system_media_update(mock_text, mock_json):
    _route_json(mock_json, app=_app_manifest("1.3.0"), sm=_sm_manifest("1.2.0"))
    mock_text.return_value = "1.0.0"
    result = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=True)
    assert result.system_media.has_update is True
    assert result.system_media.latest == "1.2.0"
    assert result.system_media.asset_url == _download_url("system_media", "1.2.0")


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_no_system_media_asset(mock_text, mock_json):
    """sm manifest without a version → no update (mirrors empty asset list)."""
    _route_json(mock_json, app=_app_manifest("1.3.0"), sm={})
    mock_text.return_value = "1.0.0"
    result = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=True)
    assert result.system_media.has_update is False
    assert result.system_media.latest == ""


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_launcher_update(mock_text, mock_json):
    _route_json(mock_json, app=_app_manifest("1.4.0"), sm=_sm_manifest("1.1.0"))
    mock_text.return_value = "1.1.0"
    result = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=True)
    assert result.launcher.has_update is True
    assert result.launcher.latest == "1.1.0"
    assert result.launcher.asset_url == _download_url("launcher", "1.1.0")


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_launcher_no_update(mock_text, mock_json):
    _route_json(mock_json, app=_app_manifest("1.4.0"), sm=_sm_manifest("1.1.0"))
    mock_text.return_value = "1.0.0"
    result = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=True)
    assert result.launcher.has_update is False
    assert result.launcher.latest == "1.0.0"


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_launcher_empty_skipped(mock_text, mock_json):
    """No launcher installed (empty version) → layer skipped, no HTTP call."""
    _route_json(mock_json, app=_app_manifest("1.4.0"), sm=_sm_manifest("1.1.0"))
    result = check_for_updates("1.3.0", "1.1.0", "", force=True)
    assert result.launcher.has_update is False
    assert result.launcher.latest == ""
    assert result.launcher.error == ""
    mock_text.assert_not_called()


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_api_error_returns_empty(mock_text, mock_json):
    """Every layer fails independently — thrown errors yield empty layers."""
    mock_json.side_effect = RuntimeError("boom")
    mock_text.side_effect = RuntimeError("boom")
    result = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=True)
    assert result.app.has_update is False
    assert result.app.latest == ""
    assert result.system_media.has_update is False
    assert result.system_media.latest == ""
    assert result.launcher.has_update is False
    assert result.launcher.latest == ""


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_cache(mock_text, mock_json):
    _route_json(mock_json, app=_app_manifest("1.4.0"), sm=_sm_manifest("1.2.0"))
    mock_text.return_value = "1.0.0"
    # force=True → 2 JSON + 1 text HTTP calls
    r1 = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=True)
    assert mock_json.call_count == 2
    assert mock_text.call_count == 1
    # force=False → cached, no additional calls
    r2 = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=False)
    assert mock_json.call_count == 2
    assert mock_text.call_count == 1
    assert r2.app.latest == r1.app.latest
    # force=True → bypass cache, more calls
    r3 = check_for_updates("1.3.0", "1.1.0", "1.0.0", force=True)
    assert mock_json.call_count == 4
    assert mock_text.call_count == 2


@patch("storyloom.core.update_manager._http_get_json")
@patch("storyloom.core.update_manager._http_get_text")
def test_check_prerelease_no_downgrade(mock_text, mock_json):
    _route_json(mock_json, app=_app_manifest("1.4.0"), sm=_sm_manifest("1.2.0"))
    mock_text.return_value = "1.0.0"
    result = check_for_updates("1.5.0-dev", "1.1.0", "1.0.0", force=True)
    assert result.app.has_update is False


# ── Download & extract tests ──────────────────────────────────────


def _create_test_zip(dir_path: str, files: dict) -> str:
    zip_path = os.path.join(dir_path, "test.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return zip_path


def test_download_extract_app(tmp_path):
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    zip_path = _create_test_zip(str(zip_dir), {
        "app/storyloom-web": b"fake-exe",
        "app/config.example.json": b'{"version": 2}',
    })
    target = tmp_path / "target"

    events = []

    def cb(p: UpdateProgress):
        events.append(p)

    def fake_download(url, dest, progress_callback=None):
        import shutil
        shutil.copy2(zip_path, dest)
        if progress_callback:
            progress_callback(os.path.getsize(zip_path), os.path.getsize(zip_path))

    with patch("storyloom.core.update_manager._download_file", fake_download):
        download_and_extract("app", "https://example.com/app.zip", str(target), cb)

    assert os.path.isfile(str(target / "app_new" / "storyloom-web"))
    # locale/ is now baked into the --onefile binary, not a separate app/ dir.
    assert os.path.isfile(str(target / "app_new" / "config.example.json"))
    stages = [e.stage for e in events]
    assert "downloading" in stages
    assert "extracting" in stages
    assert "done" in stages


def test_download_extract_launcher(tmp_path):
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    _create_test_zip(str(zip_dir), {
        "Storyloom": b"fake-launcher",
        "launcher.version": b"1.1.0",
    })
    target = tmp_path / "target"

    def fake_download(url, dest, progress_callback=None):
        import shutil
        zip_path_src = os.path.join(str(zip_dir), "test.zip")
        shutil.copy2(zip_path_src, dest)
        if progress_callback:
            progress_callback(100, 100)

    with patch("storyloom.core.update_manager._download_file", fake_download):
        download_and_extract("launcher", "https://example.com/launcher.zip", str(target))

    assert os.path.isfile(str(target / "launcher.new"))
    assert (target / "launcher.version").read_text() == "1.1.0"


def test_download_extract_system_media(tmp_path):
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    _create_test_zip(str(zip_dir), {
        "char_portrait/sys_young_male.png": b"fake-png",
        "VERSION": b"1.2.0",
        "_manifest.json": b'{"version":"1.2.0","min_app_version":"1.3.0"}',
    })
    target = tmp_path / "target"
    target.mkdir()
    (target / "VERSION").write_text("1.1.0")

    def fake_download(url, dest, progress_callback=None):
        import shutil
        zip_path_src = os.path.join(str(zip_dir), "test.zip")
        shutil.copy2(zip_path_src, dest)
        if progress_callback:
            progress_callback(100, 100)

    with patch("storyloom.core.update_manager._download_file", fake_download):
        download_and_extract("system_media", "https://example.com/sm.zip", str(target))

    assert (target / "VERSION").read_text() == "1.2.0"
    assert os.path.isfile(str(target / "char_portrait" / "sys_young_male.png"))


def test_download_extract_invalid_zip(tmp_path):
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    bad_zip = zip_dir / "bad.zip"
    bad_zip.write_text("not a zip file")

    def fake_download(url, dest, progress_callback=None):
        import shutil
        shutil.copy2(str(bad_zip), dest)

    with patch("storyloom.core.update_manager._download_file", fake_download):
        with pytest.raises(Exception):
            download_and_extract(
                "app", "https://example.com/bad.zip", str(tmp_path / "target")
            )


def test_download_extract_cleans_stale_app_new(tmp_path):
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    _create_test_zip(str(zip_dir), {"app/storyloom-web": b"new-exe"})
    target = tmp_path / "target"
    stale = target / "app_new"
    stale.mkdir(parents=True)
    (stale / "stale-file.txt").write_text("old")

    def fake_download(url, dest, progress_callback=None):
        import shutil
        zip_path_src = os.path.join(str(zip_dir), "test.zip")
        shutil.copy2(zip_path_src, dest)
        if progress_callback:
            progress_callback(100, 100)

    with patch("storyloom.core.update_manager._download_file", fake_download):
        download_and_extract("app", "https://example.com/app.zip", str(target))

    assert not os.path.exists(str(stale / "stale-file.txt"))
    assert os.path.isfile(str(target / "app_new" / "storyloom-web"))


# ── regenerate_launcher tests ──────────────────────────────────────


def test_regenerate_launcher_success(tmp_path):
    """Happy path: launcher asset zip contains launcher + version file."""
    from storyloom.launcher import _platform_exe

    launcher_name = _platform_exe("Storyloom")

    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    _create_test_zip(str(zip_dir), {
        launcher_name: b"fake-launcher",
        "launcher.version": b"1.1.0",
    })

    def fake_check(launcher_version):
        return VersionInfo(
            current=launcher_version,
            latest="1.1.0",
            asset_url="https://example.com/launcher.zip",
        )

    def fake_download(url, dest, progress_callback=None):
        import shutil
        shutil.copy2(os.path.join(str(zip_dir), "test.zip"), dest)

    with patch("storyloom.core.update_manager._check_launcher_update", fake_check):
        with patch("storyloom.core.update_manager._download_file", fake_download):
            ok = regenerate_launcher(str(tmp_path))

    assert ok is True
    assert os.path.isfile(str(tmp_path / launcher_name))
    assert (tmp_path / "launcher.version").read_text() == "1.1.0"


def test_regenerate_launcher_no_asset_url(tmp_path):
    """Returns False when the release has no downloadable asset (offline)."""

    def fake_check(launcher_version):
        return VersionInfo(current="2.0.0", latest="2.0.0", asset_url="")

    with patch("storyloom.core.update_manager._check_launcher_update", fake_check):
        ok = regenerate_launcher(str(tmp_path))

    assert ok is False


def test_regenerate_launcher_missing_launcher_in_zip(tmp_path):
    """Returns False when zip doesn't contain the launcher binary."""
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    _create_test_zip(str(zip_dir), {
        "launcher.version": b"1.1.0",
        # No Storyloom at root
    })

    def fake_check(launcher_version):
        return VersionInfo(
            current=launcher_version,
            latest="1.1.0",
            asset_url="https://example.com/launcher.zip",
        )

    def fake_download(url, dest, progress_callback=None):
        import shutil
        shutil.copy2(os.path.join(str(zip_dir), "test.zip"), dest)

    with patch("storyloom.core.update_manager._check_launcher_update", fake_check):
        with patch("storyloom.core.update_manager._download_file", fake_download):
            ok = regenerate_launcher(str(tmp_path))

    assert ok is False


def test_regenerate_launcher_windows_exe(tmp_path, monkeypatch):
    """On Windows, looks for Storyloom.exe instead of Storyloom."""
    monkeypatch.setattr(sys, "platform", "win32")
    launcher_name = "Storyloom.exe"

    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    _create_test_zip(str(zip_dir), {
        "Storyloom.exe": b"fake-launcher",
        "launcher.version": b"1.1.0",
    })

    def fake_check(launcher_version):
        return VersionInfo(
            current=launcher_version,
            latest="1.1.0",
            asset_url="https://example.com/launcher.zip",
        )

    def fake_download(url, dest, progress_callback=None):
        import shutil
        shutil.copy2(os.path.join(str(zip_dir), "test.zip"), dest)

    with patch("storyloom.core.update_manager._check_launcher_update", fake_check):
        with patch("storyloom.core.update_manager._download_file", fake_download):
            ok = regenerate_launcher(str(tmp_path))

    assert ok is True
    assert os.path.isfile(str(tmp_path / launcher_name))

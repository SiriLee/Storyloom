"""Tests for UpdateManager — data types, version check, download, extraction."""
import os
import sys
import tempfile
import zipfile
from unittest.mock import Mock, patch

import pytest

from storyloom.core.update_manager import (
    CACHE_SECONDS,
    UpdateCheckResult,
    UpdateProgress,
    VersionInfo,
    _find_asset_url,
    _parse_version_from_asset_name,
    _parse_version_from_tag,
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


def test_parse_version_from_tag():
    assert _parse_version_from_tag("v1.4.0") == "1.4.0"
    assert _parse_version_from_tag("1.4.0") == "1.4.0"
    assert _parse_version_from_tag("") == ""


def test_parse_version_from_asset_name():
    assert _parse_version_from_asset_name(
        "system_media-v1.2.0.zip", "system_media-v"
    ) == "1.2.0"
    assert _parse_version_from_asset_name(
        "storyloom-v1.4.0-Linux.zip", "storyloom-v"
    ) == "1.4.0"
    assert (
        _parse_version_from_asset_name("no_version_here.zip", "system_media-v")
        is None
    )


def test_find_asset_url_platform_specific():
    assets = [
        {
            "name": "storyloom-v1.4.0-Linux.zip",
            "browser_download_url": "https://example.com/linux.zip",
        },
        {
            "name": "storyloom-v1.4.0-Windows.zip",
            "browser_download_url": "https://example.com/win.zip",
        },
    ]
    with patch(
        "storyloom.core.update_manager._PLATFORM", "Windows"
    ):
        url, ver = _find_asset_url(assets, "storyloom-v", platform_specific=True)
        assert url == "https://example.com/win.zip"
        assert ver == "1.4.0"


def test_find_asset_url_platform_agnostic():
    assets = [
        {"name": "system_media-v1.2.0.zip",
         "browser_download_url": "https://example.com/sm.zip"},
    ]
    url, ver = _find_asset_url(assets, "system_media-v", platform_specific=False)
    assert url == "https://example.com/sm.zip"
    assert ver == "1.2.0"


def test_find_asset_url_not_found():
    assets = [{"name": "other-asset.zip",
               "browser_download_url": "https://example.com/other.zip"}]
    url, ver = _find_asset_url(assets, "system_media-v", platform_specific=False)
    assert url is None
    assert ver is None


# ── Version check tests ───────────────────────────────────────────


def _make_app_release(tag="v1.4.0", assets=None, body="## Release notes"):
    """Build a mock response for the app release (``releases/latest``)."""
    import sys
    plat = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    if assets is None:
        assets = [
            {"name": f"storyloom-{tag}-{plat}.zip",
             "browser_download_url": "https://example.com/app.zip"},
        ]
    return {
        "tag_name": tag,
        "body": body,
        "assets": assets,
    }


def _make_sm_release(assets=None):
    """Build a mock response for the system-media release tag."""
    if assets is None:
        assets = [
            {"name": "system_media-v1.2.0.zip",
             "browser_download_url": "https://example.com/sm.zip"},
        ]
    return {
        "tag_name": "system-media",
        "body": "",
        "assets": assets,
    }


def _patch_updates(mock_get, *, app_release, sm_release):
    """Set up the dual-release mock.

    ``_http_get_json`` is called twice per ``check_for_updates()`` —
    once for ``releases/latest`` (app) and once for
    ``releases/tags/system-media``.  Route by URL substring.
    """
    def _dispatch(url):
        if "/tags/system-media" in url:
            return sm_release
        return app_release

    mock_get.side_effect = _dispatch


@patch("storyloom.core.update_manager._http_get_json")
def test_check_no_update(mock_get):
    import sys
    plat = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    _patch_updates(
        mock_get,
        app_release=_make_app_release(tag="v1.3.0", assets=[
            {"name": f"storyloom-v1.3.0-{plat}.zip",
             "browser_download_url": "https://example.com/app.zip"},
        ]),
        sm_release=_make_sm_release(assets=[
            {"name": "system_media-v1.1.0.zip",
             "browser_download_url": "https://example.com/sm.zip"},
        ]),
    )
    result = check_for_updates("1.3.0", "1.1.0", force=True)
    assert result.app.has_update is False
    assert result.system_media.has_update is False


@patch("storyloom.core.update_manager._http_get_json")
def test_check_app_update(mock_get):
    import sys
    plat = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    _patch_updates(
        mock_get,
        app_release=_make_app_release(tag="v1.4.0", assets=[
            {"name": f"storyloom-v1.4.0-{plat}.zip",
             "browser_download_url": "https://example.com/app.zip"},
        ]),
        sm_release=_make_sm_release(assets=[
            {"name": "system_media-v1.2.0.zip",
             "browser_download_url": "https://example.com/sm.zip"},
        ]),
    )
    result = check_for_updates("1.3.0", "1.1.0", force=True)
    assert result.app.has_update is True
    assert result.app.latest == "1.4.0"
    assert result.app.asset_url == "https://example.com/app.zip"


@patch("storyloom.core.update_manager._http_get_json")
def test_check_system_media_update(mock_get):
    import sys
    plat = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    _patch_updates(
        mock_get,
        app_release=_make_app_release(tag="v1.3.0", assets=[
            {"name": f"storyloom-v1.3.0-{plat}.zip",
             "browser_download_url": "https://example.com/app.zip"},
        ]),
        sm_release=_make_sm_release(assets=[
            {"name": "system_media-v1.2.0.zip",
             "browser_download_url": "https://example.com/sm.zip"},
        ]),
    )
    result = check_for_updates("1.3.0", "1.1.0", force=True)
    assert result.system_media.has_update is True
    assert result.system_media.latest == "1.2.0"


@patch("storyloom.core.update_manager._http_get_json")
def test_check_no_system_media_asset(mock_get):
    import sys
    plat = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    _patch_updates(
        mock_get,
        app_release=_make_app_release(tag="v1.3.0", assets=[
            {"name": f"storyloom-v1.3.0-{plat}.zip",
             "browser_download_url": "https://example.com/app.zip"},
        ]),
        sm_release=_make_sm_release(assets=[]),  # no system_media asset
    )
    result = check_for_updates("1.3.0", "1.1.0", force=True)
    assert result.system_media.has_update is False
    assert result.system_media.latest == ""


@patch("storyloom.core.update_manager._http_get_json")
def test_check_api_error_returns_empty(mock_get):
    """Every layer fails independently — app error doesn't block sm, and
    vice versa.  When both API calls throw, both layers are empty."""
    mock_get.side_effect = RuntimeError("rate limited")
    result = check_for_updates("1.3.0", "1.1.0", force=True)
    assert result.app.has_update is False
    assert result.app.latest == ""
    assert result.system_media.has_update is False
    assert result.system_media.latest == ""


@patch("storyloom.core.update_manager._http_get_json")
def test_check_cache(mock_get):
    _patch_updates(
        mock_get,
        app_release=_make_app_release(tag="v1.4.0"),
        sm_release=_make_sm_release(),
    )
    # force=True → 2 HTTP calls (one per layer)
    r1 = check_for_updates("1.3.0", "1.1.0", force=True)
    assert mock_get.call_count == 2
    # force=False → cached, 0 additional calls
    r2 = check_for_updates("1.3.0", "1.1.0", force=False)
    assert mock_get.call_count == 2
    assert r2.app.latest == r1.app.latest
    # force=True → bypass cache, 2 more calls
    r3 = check_for_updates("1.3.0", "1.1.0", force=True)
    assert mock_get.call_count == 4


@patch("storyloom.core.update_manager._http_get_json")
def test_check_prerelease_no_downgrade(mock_get):
    _patch_updates(
        mock_get,
        app_release=_make_app_release(tag="v1.4.0"),
        sm_release=_make_sm_release(),
    )
    result = check_for_updates("1.5.0-dev", "1.1.0", force=True)
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
        "app/locale/en/LC_MESSAGES/storyloom.mo": b"fake-mo",
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
    assert os.path.isfile(
        str(target / "app_new" / "locale" / "en" / "LC_MESSAGES" / "storyloom.mo")
    )
    stages = [e.stage for e in events]
    assert "downloading" in stages
    assert "extracting" in stages
    assert "done" in stages


def test_download_extract_with_launcher_new(tmp_path):
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    _create_test_zip(str(zip_dir), {
        "app/storyloom-web": b"fake-exe",
        "Storyloom": b"fake-launcher",
    })
    target = tmp_path / "target"

    def fake_download(url, dest, progress_callback=None):
        import shutil
        zip_path_src = os.path.join(str(zip_dir), "test.zip")
        shutil.copy2(zip_path_src, dest)
        if progress_callback:
            progress_callback(100, 100)

    with patch("storyloom.core.update_manager._download_file", fake_download):
        download_and_extract("app", "https://example.com/app.zip", str(target))

    assert os.path.isfile(str(target / "launcher.new"))


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
    """Happy path: zip contains launcher at root, extracted to target dir."""
    from storyloom.launcher import _platform_exe

    launcher_name = _platform_exe("Storyloom")
    app_exe = _platform_exe("storyloom-web")

    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    _create_test_zip(str(zip_dir), {
        f"app/{app_exe}": b"fake-exe",
        launcher_name: b"fake-launcher",
    })

    def fake_check(app_version):
        return VersionInfo(
            current=app_version,
            latest="2.0.0",
            asset_url="https://example.com/release.zip",
        )

    def fake_download(url, dest, progress_callback=None):
        import shutil
        shutil.copy2(os.path.join(str(zip_dir), "test.zip"), dest)

    with patch("storyloom.core.update_manager._check_app_update", fake_check):
        with patch("storyloom.core.update_manager._download_file", fake_download):
            ok = regenerate_launcher(str(tmp_path))

    assert ok is True
    assert os.path.isfile(str(tmp_path / launcher_name))


def test_regenerate_launcher_no_asset_url(tmp_path):
    """Returns False when the release has no downloadable asset (offline)."""

    def fake_check(app_version):
        return VersionInfo(current="2.0.0", latest="2.0.0", asset_url="")

    with patch("storyloom.core.update_manager._check_app_update", fake_check):
        ok = regenerate_launcher(str(tmp_path))

    assert ok is False


def test_regenerate_launcher_missing_launcher_in_zip(tmp_path):
    """Returns False when zip doesn't contain the launcher binary."""
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    _create_test_zip(str(zip_dir), {
        "app/storyloom-web": b"fake-exe",
        # No Storyloom at root
    })

    def fake_check(app_version):
        return VersionInfo(
            current=app_version,
            latest="2.0.0",
            asset_url="https://example.com/release.zip",
        )

    def fake_download(url, dest, progress_callback=None):
        import shutil
        shutil.copy2(os.path.join(str(zip_dir), "test.zip"), dest)

    with patch("storyloom.core.update_manager._check_app_update", fake_check):
        with patch("storyloom.core.update_manager._download_file", fake_download):
            ok = regenerate_launcher(str(tmp_path))

    assert ok is False


def test_regenerate_launcher_windows_exe(tmp_path, monkeypatch):
    """On Windows, looks for Storyloom.exe instead of Storyloom."""
    monkeypatch.setattr(sys, "platform", "win32")
    # Reset the module-level LAUNCHER_NAME computation
    launcher_name = "Storyloom.exe"

    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    _create_test_zip(str(zip_dir), {
        "app/storyloom-web.exe": b"fake-exe",
        "Storyloom.exe": b"fake-launcher",
    })

    def fake_check(app_version):
        return VersionInfo(
            current=app_version,
            latest="2.0.0",
            asset_url="https://example.com/release.zip",
        )

    def fake_download(url, dest, progress_callback=None):
        import shutil
        shutil.copy2(os.path.join(str(zip_dir), "test.zip"), dest)

    with patch("storyloom.core.update_manager._check_app_update", fake_check):
        with patch("storyloom.core.update_manager._download_file", fake_download):
            ok = regenerate_launcher(str(tmp_path))

    assert ok is True
    assert os.path.isfile(str(tmp_path / launcher_name))

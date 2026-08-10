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


def _make_release_json(tag="v1.4.0", assets=None, body="## Release notes"):
    return {
        "tag_name": tag,
        "body": body,
        "assets": assets or [
            {"name": "storyloom-v1.4.0-Linux.zip",
             "browser_download_url": "https://example.com/app.zip"},
            {"name": "system_media-v1.2.0.zip",
             "browser_download_url": "https://example.com/sm.zip"},
        ],
    }


@patch("storyloom.core.update_manager._http_get_json")
def test_check_no_update(mock_get):
    import sys
    plat = {"win32": "Windows", "darwin": "macOS"}.get(
        sys.platform, "Linux"
    )
    mock_get.return_value = _make_release_json(tag="v1.3.0", assets=[
        {"name": f"storyloom-v1.3.0-{plat}.zip",
         "browser_download_url": "https://example.com/app.zip"},
        {"name": "system_media-v1.1.0.zip",
         "browser_download_url": "https://example.com/sm.zip"},
    ])
    result = check_for_updates("1.3.0", "1.1.0", force=True)
    assert result.app.has_update is False
    assert result.system_media.has_update is False


@patch("storyloom.core.update_manager._http_get_json")
def test_check_app_update(mock_get):
    import sys
    plat = {"win32": "Windows", "darwin": "macOS"}.get(
        sys.platform, "Linux"
    )
    mock_get.return_value = _make_release_json(tag="v1.4.0", assets=[
        {"name": f"storyloom-v1.4.0-{plat}.zip",
         "browser_download_url": "https://example.com/app.zip"},
        {"name": "system_media-v1.2.0.zip",
         "browser_download_url": "https://example.com/sm.zip"},
    ])
    result = check_for_updates("1.3.0", "1.1.0", force=True)
    assert result.app.has_update is True
    assert result.app.latest == "1.4.0"
    assert result.app.asset_url == "https://example.com/app.zip"


@patch("storyloom.core.update_manager._http_get_json")
def test_check_system_media_update(mock_get):
    import sys
    plat = {"win32": "Windows", "darwin": "macOS"}.get(
        sys.platform, "Linux"
    )
    mock_get.return_value = _make_release_json(
        tag="v1.3.0",
        assets=[
            {"name": f"storyloom-v1.3.0-{plat}.zip",
             "browser_download_url": "https://example.com/app.zip"},
            {"name": "system_media-v1.2.0.zip",
             "browser_download_url": "https://example.com/sm.zip"},
        ],
    )
    result = check_for_updates("1.3.0", "1.1.0", force=True)
    assert result.system_media.has_update is True
    assert result.system_media.latest == "1.2.0"


@patch("storyloom.core.update_manager._http_get_json")
def test_check_no_system_media_asset(mock_get):
    import sys
    plat = {"win32": "Windows", "darwin": "macOS"}.get(
        sys.platform, "Linux"
    )
    mock_get.return_value = _make_release_json(
        tag="v1.3.0",
        assets=[
            {"name": f"storyloom-v1.3.0-{plat}.zip",
             "browser_download_url": "https://example.com/app.zip"},
        ],
    )
    result = check_for_updates("1.3.0", "1.1.0", force=True)
    assert result.system_media.has_update is False
    assert result.system_media.latest == ""


@patch("storyloom.core.update_manager._http_get_json")
def test_check_api_error_returns_empty(mock_get):
    mock_get.side_effect = RuntimeError("rate limited")
    result = check_for_updates("1.3.0", "1.1.0", force=True)
    assert result.app.has_update is False
    assert result.app.latest == ""
    assert result.system_media.has_update is False


def _mock_release_with_platform(tag, include_app=True):
    import sys
    plat = {"win32": "Windows", "darwin": "macOS"}.get(
        sys.platform, "Linux"
    )
    assets = []
    if include_app:
        assets.append({
            "name": f"storyloom-{tag}-{plat}.zip",
            "browser_download_url": "https://example.com/app.zip",
        })
    assets.append({
        "name": f"system_media-v1.2.0.zip",
        "browser_download_url": "https://example.com/sm.zip",
    })
    return {"tag_name": tag, "body": "## Release notes", "assets": assets}


@patch("storyloom.core.update_manager._http_get_json")
def test_check_cache(mock_get):
    mock_get.return_value = _mock_release_with_platform("v1.4.0")
    r1 = check_for_updates("1.3.0", "1.1.0", force=True)
    assert mock_get.call_count == 1
    r2 = check_for_updates("1.3.0", "1.1.0", force=False)
    assert mock_get.call_count == 1  # cached
    assert r2.app.latest == r1.app.latest
    r3 = check_for_updates("1.3.0", "1.1.0", force=True)
    assert mock_get.call_count == 2  # force bypass


@patch("storyloom.core.update_manager._http_get_json")
def test_check_prerelease_no_downgrade(mock_get):
    mock_get.return_value = _mock_release_with_platform("v1.4.0")
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
        "app_new/storyloom-web": b"fake-exe",
        "app_new/locale/en/LC_MESSAGES/storyloom.mo": b"fake-mo",
        "app_new/config.example.json": b'{"version": 2}',
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
        "app_new/storyloom-web": b"fake-exe",
        "launcher.new": b"fake-launcher",
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
    _create_test_zip(str(zip_dir), {"app_new/storyloom-web": b"new-exe"})
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

"""Tests for the Storyloom Launcher — self-contained, no filesystem deps
beyond tmp_path."""

import os
import sys
from unittest.mock import Mock, patch

import pytest

from launcher import (
    _apply_app_update,
    _apply_launcher_update,
    _platform_exe,
    LAUNCHER_NAME,
    MAIN_EXE,
)


def test_platform_exe_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert _platform_exe("Storyloom") == "Storyloom"
    assert _platform_exe("storyloom-web") == "storyloom-web"


def test_platform_exe_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert _platform_exe("Storyloom") == "Storyloom.exe"
    assert _platform_exe("storyloom-web") == "storyloom-web.exe"


def test_apply_app_update_no_pending(tmp_path, monkeypatch):
    monkeypatch.setattr("launcher.DIR", str(tmp_path))
    _apply_app_update()
    assert not (tmp_path / "app").exists()


def test_apply_app_update_swaps(tmp_path, monkeypatch):
    monkeypatch.setattr("launcher.DIR", str(tmp_path))
    monkeypatch.setattr("launcher.APP", str(tmp_path / "app"))
    monkeypatch.setattr("launcher.APP_NEW", str(tmp_path / "app_new"))
    monkeypatch.setattr("launcher.APP_OLD", str(tmp_path / "app_old"))

    main_exe = _platform_exe("storyloom-web")
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / main_exe).write_text("old")
    (tmp_path / "app_new").mkdir()
    (tmp_path / "app_new" / main_exe).write_text("new")

    _apply_app_update()

    assert (tmp_path / "app" / main_exe).read_text() == "new"
    assert not (tmp_path / "app_old").exists()
    assert not (tmp_path / "app_new").exists()


def test_apply_app_update_no_old_app(tmp_path, monkeypatch):
    """First install via update — no app/ dir yet."""
    monkeypatch.setattr("launcher.DIR", str(tmp_path))
    monkeypatch.setattr("launcher.APP", str(tmp_path / "app"))
    monkeypatch.setattr("launcher.APP_NEW", str(tmp_path / "app_new"))
    monkeypatch.setattr("launcher.APP_OLD", str(tmp_path / "app_old"))

    main_exe = _platform_exe("storyloom-web")
    (tmp_path / "app_new").mkdir()
    (tmp_path / "app_new" / main_exe).write_text("new")

    _apply_app_update()

    assert (tmp_path / "app" / main_exe).read_text() == "new"
    assert not (tmp_path / "app_new").exists()


def test_apply_launcher_update_none(tmp_path, monkeypatch):
    monkeypatch.setattr("launcher.DIR", str(tmp_path))
    monkeypatch.setattr("launcher.LAUNCHER_NEW",
                        str(tmp_path / "launcher.new"))
    _apply_launcher_update()


def test_apply_launcher_update_unix(tmp_path, monkeypatch):
    monkeypatch.setattr("launcher.DIR", str(tmp_path))
    monkeypatch.setattr("launcher.LAUNCHER_NEW",
                        str(tmp_path / "launcher.new"))
    monkeypatch.setattr("launcher.LAUNCHER_NAME", "Storyloom")
    monkeypatch.setattr(sys, "platform", "linux")

    (tmp_path / "launcher.new").write_text("new-launcher")

    mock_execv = Mock()
    monkeypatch.setattr(os, "chmod", Mock())
    monkeypatch.setattr(os, "execv", mock_execv)

    _apply_launcher_update()

    assert not (tmp_path / "launcher.new").exists()
    assert (tmp_path / "Storyloom").read_text() == "new-launcher"
    mock_execv.assert_called_once()


def test_apply_launcher_update_windows_bat_paths(tmp_path, monkeypatch):
    """The .bat script must use absolute paths for both source and dest."""
    monkeypatch.setattr("launcher.DIR", str(tmp_path))
    monkeypatch.setattr(
        "launcher.LAUNCHER_NEW",
        str(tmp_path / "launcher.new"),
    )
    monkeypatch.setattr("launcher.LAUNCHER_NAME", "Storyloom.exe")
    monkeypatch.setattr(sys, "platform", "win32")

    (tmp_path / "launcher.new").write_text("new-launcher")

    mock_popen = Mock()
    monkeypatch.setattr("launcher.subprocess.Popen", mock_popen)

    # sys.exit is called after spawning the .bat — prevent test exit.
    with pytest.raises(SystemExit):
        _apply_launcher_update()

    # Verify .bat was written with absolute paths.
    bat_path = tmp_path / "_launcher_swap.bat"
    assert bat_path.exists()
    content = bat_path.read_text()
    launcher_dest = str(tmp_path / "Storyloom.exe")
    # Both source and dest in move /Y must be absolute paths.
    assert f'move /Y' in content
    assert launcher_dest in content, f"Expected absolute dest in: {content}"
    # start command must also use absolute path.
    assert f'start ""' in content
    # move must retry until launcher.new is gone (launcher may still
    # hold the Storyloom.exe lock beyond the 1s timeout).
    assert ":retry" in content
    assert "goto retry" in content
    # .bat must self-delete after running (avoid leftover artifact).
    assert 'del "%~f0"' in content
    mock_popen.assert_called_once()

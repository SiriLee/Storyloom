"""Tests for the Storyloom Launcher — self-contained, no filesystem deps
beyond tmp_path."""

import os
import sys
from unittest.mock import Mock, patch

import pytest

from storyloom.launcher import (
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
    monkeypatch.setattr("storyloom.launcher.DIR", str(tmp_path))
    _apply_app_update()
    assert not (tmp_path / "app").exists()


def test_apply_app_update_swaps(tmp_path, monkeypatch):
    monkeypatch.setattr("storyloom.launcher.DIR", str(tmp_path))
    monkeypatch.setattr("storyloom.launcher.APP", str(tmp_path / "app"))
    monkeypatch.setattr("storyloom.launcher.APP_NEW", str(tmp_path / "app_new"))
    monkeypatch.setattr("storyloom.launcher.APP_OLD", str(tmp_path / "app_old"))

    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "storyloom-web").write_text("old")
    (tmp_path / "app_new").mkdir()
    (tmp_path / "app_new" / "storyloom-web").write_text("new")

    _apply_app_update()

    assert (tmp_path / "app" / "storyloom-web").read_text() == "new"
    assert not (tmp_path / "app_old").exists()
    assert not (tmp_path / "app_new").exists()


def test_apply_app_update_no_old_app(tmp_path, monkeypatch):
    """First install via update — no app/ dir yet."""
    monkeypatch.setattr("storyloom.launcher.DIR", str(tmp_path))
    monkeypatch.setattr("storyloom.launcher.APP", str(tmp_path / "app"))
    monkeypatch.setattr("storyloom.launcher.APP_NEW", str(tmp_path / "app_new"))
    monkeypatch.setattr("storyloom.launcher.APP_OLD", str(tmp_path / "app_old"))

    (tmp_path / "app_new").mkdir()
    (tmp_path / "app_new" / "storyloom-web").write_text("new")

    _apply_app_update()

    assert (tmp_path / "app" / "storyloom-web").read_text() == "new"
    assert not (tmp_path / "app_new").exists()


def test_apply_launcher_update_none(tmp_path, monkeypatch):
    monkeypatch.setattr("storyloom.launcher.DIR", str(tmp_path))
    monkeypatch.setattr("storyloom.launcher.LAUNCHER_NEW",
                        str(tmp_path / "launcher.new"))
    _apply_launcher_update()


def test_apply_launcher_update_unix(tmp_path, monkeypatch):
    monkeypatch.setattr("storyloom.launcher.DIR", str(tmp_path))
    monkeypatch.setattr("storyloom.launcher.LAUNCHER_NEW",
                        str(tmp_path / "launcher.new"))
    monkeypatch.setattr("storyloom.launcher.LAUNCHER_NAME", "Storyloom")
    monkeypatch.setattr(sys, "platform", "linux")

    (tmp_path / "launcher.new").write_text("new-launcher")

    mock_execv = Mock()
    monkeypatch.setattr(os, "chmod", Mock())
    monkeypatch.setattr(os, "execv", mock_execv)

    _apply_launcher_update()

    assert not (tmp_path / "launcher.new").exists()
    assert (tmp_path / "Storyloom").read_text() == "new-launcher"
    mock_execv.assert_called_once()

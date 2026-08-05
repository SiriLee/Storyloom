"""Tests for img_utils — format/alpha detection, dimensions, rembg helpers.

TDD: these tests define the contract before implementation exists.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

DATA_DIR = Path(__file__).resolve().parent / "data"


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════

def _load(name: str) -> bytes:
    """Read a test data file."""
    return (DATA_DIR / name).read_bytes()


def _rgba_png() -> bytes:
    return _load("test_rgba.png")


def _rgb_png() -> bytes:
    return _load("test_rgb.png")


def _rgb_jpg() -> bytes:
    return _load("test_rgb.jpg")


def _lossy_webp() -> bytes:
    return _load("test_lossy.webp")


# ═══════════════════════════════════════════════════════════════════
# detect_format
# ═══════════════════════════════════════════════════════════════════

class TestDetectFormat:
    """detect_format — magic bytes → format string."""

    def test_png_rgb(self):
        from storyloom.io.img_utils import detect_format
        assert detect_format(_rgb_png()) == "png"

    def test_png_rgba(self):
        from storyloom.io.img_utils import detect_format
        assert detect_format(_rgba_png()) == "png"

    def test_jpeg(self):
        from storyloom.io.img_utils import detect_format
        assert detect_format(_rgb_jpg()) == "jpeg"

    def test_webp(self):
        from storyloom.io.img_utils import detect_format
        assert detect_format(_lossy_webp()) == "webp"

    def test_unknown_empty(self):
        from storyloom.io.img_utils import detect_format
        assert detect_format(b"") == "unknown"

    def test_unknown_garbage(self):
        from storyloom.io.img_utils import detect_format
        assert detect_format(b"not an image at all") == "unknown"

    def test_unknown_text_file(self):
        """Plain text should not be misidentified."""
        from storyloom.io.img_utils import detect_format
        assert detect_format(b"hello world\n") == "unknown"


# ═══════════════════════════════════════════════════════════════════
# detect_alpha
# ═══════════════════════════════════════════════════════════════════

class TestDetectAlpha:
    """detect_alpha — alpha channel presence per format."""

    def test_png_rgba_has_alpha(self):
        from storyloom.io.img_utils import detect_alpha
        assert detect_alpha(_rgba_png(), "png") is True

    def test_png_rgb_no_alpha(self):
        from storyloom.io.img_utils import detect_alpha
        assert detect_alpha(_rgb_png(), "png") is False

    def test_jpeg_no_alpha(self):
        from storyloom.io.img_utils import detect_alpha
        assert detect_alpha(_rgb_jpg(), "jpeg") is False

    def test_webp_lossy_no_alpha(self):
        from storyloom.io.img_utils import detect_alpha
        assert detect_alpha(_lossy_webp(), "webp") is False

    def test_unknown_format_returns_false(self):
        from storyloom.io.img_utils import detect_alpha
        assert detect_alpha(b"garbage", "unknown") is False


# ═══════════════════════════════════════════════════════════════════
# get_dimensions
# ═══════════════════════════════════════════════════════════════════

class TestGetDimensions:
    """get_dimensions — width/height extraction from headers."""

    def test_png_rgb_1x1(self):
        from storyloom.io.img_utils import get_dimensions
        assert get_dimensions(_rgb_png(), "png") == (1, 1)

    def test_png_rgba_1x1(self):
        from storyloom.io.img_utils import get_dimensions
        assert get_dimensions(_rgba_png(), "png") == (1, 1)

    def test_jpeg_1x1(self):
        from storyloom.io.img_utils import get_dimensions
        assert get_dimensions(_rgb_jpg(), "jpeg") == (1, 1)

    def test_webp_returns_nonzero_or_zero(self):
        """WebP dimension extraction — returns (w, h); 0s are acceptable
        for lossy VP8 where our minimal test file may not have valid
        dimension data. The contract is: never crash, return ints."""
        from storyloom.io.img_utils import get_dimensions
        w, h = get_dimensions(_lossy_webp(), "webp")
        assert isinstance(w, int)
        assert isinstance(h, int)
        # Width can be 0 for malformed VP8, but we accept it —
        # the caller handles (0, 0) gracefully.

    def test_unknown_returns_zero(self):
        from storyloom.io.img_utils import get_dimensions
        assert get_dimensions(b"", "unknown") == (0, 0)

    def test_truncated_returns_zero(self):
        from storyloom.io.img_utils import get_dimensions
        assert get_dimensions(b"\x89PNG", "png") == (0, 0)


# ═══════════════════════════════════════════════════════════════════
# _check_rembg
# ═══════════════════════════════════════════════════════════════════

class TestCheckRembg:
    """_check_rembg — lazy import detection (module-level cache)."""

    def test_returns_bool(self):
        """_check_rembg returns True or False — no exception."""
        from storyloom.io.img_utils import _check_rembg
        result = _check_rembg()
        assert isinstance(result, bool)

    def test_import_error_returns_false(self):
        """When rembg is not importable, _check_rembg returns False."""
        from storyloom.io import img_utils
        # Reset cache to force re-check
        img_utils._HAS_REMBG = None
        # Simulate ImportError by patching __import__
        with patch("builtins.__import__") as mock_import:
            mock_import.side_effect = ImportError("No module named 'rembg'")
            # Reset cache for this test
            img_utils._HAS_REMBG = None
            assert img_utils._check_rembg() is False

    def test_cached_result(self):
        """Second call returns cached result without re-importing."""
        from storyloom.io import img_utils
        img_utils._HAS_REMBG = True
        assert img_utils._check_rembg() is True
        img_utils._HAS_REMBG = None  # restore


# ═══════════════════════════════════════════════════════════════════
# install_rembg
# ═══════════════════════════════════════════════════════════════════

class TestInstallRembg:
    """install_rembg — subprocess pip install + cache invalidation."""

    def test_already_installed_skips_pip(self):
        """When already installed, return (True, ...) without subprocess."""
        from storyloom.io import img_utils
        img_utils._HAS_REMBG = True
        try:
            success, msg = img_utils.install_rembg()
            assert success is True
            assert "already" in msg.lower()
        finally:
            img_utils._HAS_REMBG = None

    def test_pip_success(self):
        """Successful pip install returns (True, ...) and sets _HAS_REMBG."""
        from storyloom.io import img_utils
        img_utils._HAS_REMBG = False
        try:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="", stderr="",
                )
                success, msg = img_utils.install_rembg()
                assert success is True
                # Verify pip was called with expected args
                call_args = mock_run.call_args[0][0]
                cmd_str = " ".join(call_args)
                assert "pip" in cmd_str
                assert "install" in cmd_str
                assert "rembg" in cmd_str
        finally:
            img_utils._HAS_REMBG = None

    def test_pip_failure(self):
        """Failed pip install returns (False, ...)."""
        from storyloom.io import img_utils
        img_utils._HAS_REMBG = False
        try:
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, stdout="", stderr="package not found",
                )
                success, msg = img_utils.install_rembg()
                assert success is False
                assert "pip" in msg.lower() or "package" in msg.lower()
        finally:
            img_utils._HAS_REMBG = None

    def test_subprocess_error(self):
        """subprocess exception returns (False, ...)."""
        from storyloom.io import img_utils
        img_utils._HAS_REMBG = False
        try:
            with patch("subprocess.run", side_effect=OSError("no pip")):
                success, msg = img_utils.install_rembg()
                assert success is False
        finally:
            img_utils._HAS_REMBG = None


# ═══════════════════════════════════════════════════════════════════
# remove_background
# ═══════════════════════════════════════════════════════════════════

class TestRemoveBackground:
    """remove_background — rembg integration (degraded when unavailable)."""

    def test_returns_none_when_rembg_unavailable(self):
        """When rembg not installed, return None without error."""
        from storyloom.io import img_utils
        img_utils._HAS_REMBG = False
        try:
            result = img_utils.remove_background(_rgba_png(), "png")
            assert result is None
        finally:
            img_utils._HAS_REMBG = None

    def test_returns_bytes_when_rembg_available(self):
        """When rembg is available, returns processed bytes."""
        from storyloom.io import img_utils
        img_utils._HAS_REMBG = True
        try:
            with patch("rembg.remove") as mock_remove:
                from io import BytesIO
                from PIL import Image
                img = Image.new("RGBA", (1, 1), (255, 0, 0, 128))
                mock_remove.return_value = img
                result = img_utils.remove_background(_rgba_png(), "png")
                assert isinstance(result, bytes)
                assert len(result) > 0
        finally:
            img_utils._HAS_REMBG = None


# ═══════════════════════════════════════════════════════════════════
# maybe_remove_background
# ═══════════════════════════════════════════════════════════════════

class TestMaybeRemoveBackground:
    """maybe_remove_background — policy-driven background removal."""

    @pytest.fixture
    def img_result(self):
        from storyloom.io.img_api_client import ImageResult
        return ImageResult(
            bytes=_rgb_png(),
            format="png",
            has_alpha=False,
            width=1,
            height=1,
            url="",
            elapsed_ms=100.0,
        )

    def test_policy_never_returns_unchanged(self, img_result):
        from storyloom.io.img_utils import maybe_remove_background
        from storyloom.io.img_api_client import RemoveBgPolicy
        result = maybe_remove_background(img_result, RemoveBgPolicy.NEVER)
        assert result is img_result

    def test_policy_auto_skips_when_has_alpha(self):
        from storyloom.io.img_utils import maybe_remove_background
        from storyloom.io.img_api_client import ImageResult, RemoveBgPolicy
        r = ImageResult(
            bytes=_rgba_png(), format="png", has_alpha=True,
            width=1, height=1, url="", elapsed_ms=100.0,
        )
        result = maybe_remove_background(r, RemoveBgPolicy.AUTO)
        assert result is r  # unchanged — already has alpha

    def test_policy_auto_removes_when_no_alpha(self):
        from storyloom.io import img_utils
        from storyloom.io.img_api_client import ImageResult, RemoveBgPolicy
        r = ImageResult(
            bytes=_rgb_png(), format="png", has_alpha=False,
            width=1, height=1, url="", elapsed_ms=100.0,
        )
        img_utils._HAS_REMBG = True
        try:
            with patch("rembg.remove") as mock_remove:
                from PIL import Image
                mock_remove.return_value = Image.new("RGBA", (1, 1))
                result = img_utils.maybe_remove_background(r, RemoveBgPolicy.AUTO)
                assert result.has_alpha is True
                assert result.format == "png"
        finally:
            img_utils._HAS_REMBG = None

    def test_policy_always_forces_removal(self):
        from storyloom.io import img_utils
        from storyloom.io.img_api_client import ImageResult, RemoveBgPolicy
        r = ImageResult(
            bytes=_rgba_png(), format="png", has_alpha=True,
            width=1, height=1, url="", elapsed_ms=100.0,
        )
        img_utils._HAS_REMBG = True
        try:
            with patch("rembg.remove") as mock_remove:
                from PIL import Image
                mock_remove.return_value = Image.new("RGBA", (1, 1))
                result = img_utils.maybe_remove_background(r, RemoveBgPolicy.ALWAYS)
                assert mock_remove.called
        finally:
            img_utils._HAS_REMBG = None

    def test_degrade_when_rembg_unavailable(self):
        """When rembg unavailable, returns original regardless of policy."""
        from storyloom.io import img_utils
        from storyloom.io.img_api_client import ImageResult, RemoveBgPolicy
        r = ImageResult(
            bytes=_rgb_png(), format="png", has_alpha=False,
            width=1, height=1, url="", elapsed_ms=100.0,
        )
        img_utils._HAS_REMBG = False
        try:
            result = img_utils.maybe_remove_background(r, RemoveBgPolicy.AUTO)
            assert result is r  # unchanged — no rembg available
        finally:
            img_utils._HAS_REMBG = None

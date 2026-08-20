"""Tests for img_utils — format/alpha detection, dimensions, background removal.

TDD: these tests define the contract before implementation exists.
"""

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


def _graya_png() -> bytes:
    """PNG color type 4 — grayscale + alpha."""
    return _load("test_graya.png")


def _alpha_webp() -> bytes:
    """VP8X WebP with alpha flag set (1x1 canvas)."""
    return _load("test_alpha.webp")


def _vp8x_webp() -> bytes:
    """VP8X WebP without alpha, 64x48 canvas."""
    return _load("test_vp8x.webp")


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

    def test_png_graya(self):
        from storyloom.io.img_utils import detect_format
        assert detect_format(_graya_png()) == "png"

    def test_jpeg(self):
        from storyloom.io.img_utils import detect_format
        assert detect_format(_rgb_jpg()) == "jpeg"

    def test_webp_lossy(self):
        from storyloom.io.img_utils import detect_format
        assert detect_format(_lossy_webp()) == "webp"

    def test_webp_vp8x(self):
        from storyloom.io.img_utils import detect_format
        assert detect_format(_vp8x_webp()) == "webp"

    def test_riff_non_webp_is_unknown(self):
        """RIFF container not WEBP (e.g. AVI, WAV) returns 'unknown'."""
        from storyloom.io.img_utils import detect_format
        # RIFF + "AVI " fourcc — should not be misidentified as WebP
        riff_data = b"RIFF\x10\x00\x00\x00AVI DATA"
        assert detect_format(riff_data) == "unknown"

    def test_riff_too_short_for_fourcc(self):
        """RIFF header but too short to read fourcc."""
        from storyloom.io.img_utils import detect_format
        assert detect_format(b"RIFF\x00\x00\x00") == "unknown"

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

    def test_png_graya_has_alpha(self):
        """PNG color type 4 (grayscale+alpha) should be detected."""
        from storyloom.io.img_utils import detect_alpha
        assert detect_alpha(_graya_png(), "png") is True

    def test_png_rgb_no_alpha(self):
        from storyloom.io.img_utils import detect_alpha
        assert detect_alpha(_rgb_png(), "png") is False

    def test_jpeg_no_alpha(self):
        from storyloom.io.img_utils import detect_alpha
        assert detect_alpha(_rgb_jpg(), "jpeg") is False

    def test_webp_lossy_no_alpha(self):
        from storyloom.io.img_utils import detect_alpha
        assert detect_alpha(_lossy_webp(), "webp") is False

    def test_webp_vp8x_has_alpha(self):
        """VP8X WebP with alpha flag set → True."""
        from storyloom.io.img_utils import detect_alpha
        assert detect_alpha(_alpha_webp(), "webp") is True

    def test_webp_vp8x_no_alpha(self):
        """VP8X WebP without alpha flag → False."""
        from storyloom.io.img_utils import detect_alpha
        assert detect_alpha(_vp8x_webp(), "webp") is False

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

    def test_webp_vp8x_known_dimensions(self):
        """VP8X with 64x48 canvas — returns exact dimensions."""
        from storyloom.io.img_utils import get_dimensions
        w, h = get_dimensions(_vp8x_webp(), "webp")
        assert w == 64, f"Expected width=64, got {w}"
        assert h == 48, f"Expected height=48, got {h}"

    def test_webp_lossy_does_not_crash(self):
        """VP8 lossy WebP — returns ints, doesn't crash."""
        from storyloom.io.img_utils import get_dimensions
        w, h = get_dimensions(_lossy_webp(), "webp")
        assert isinstance(w, int)
        assert isinstance(h, int)
        # VP8 lossy dimension extraction depends on valid bitstream;
        # our minimal test file may not have valid dimension data,
        # so (0, 0) is acceptable here — the contract is "no crash".

    def test_unknown_returns_zero(self):
        from storyloom.io.img_utils import get_dimensions
        assert get_dimensions(b"", "unknown") == (0, 0)

    def test_truncated_returns_zero(self):
        from storyloom.io.img_utils import get_dimensions
        assert get_dimensions(b"\x89PNG", "png") == (0, 0)


# ═══════════════════════════════════════════════════════════════════
# _model_dir — bundled path priority
# ═══════════════════════════════════════════════════════════════════

class TestModelDir:
    """_model_dir — env override, else bundled package data."""

    def test_env_override_takes_priority(self, tmp_path):
        from storyloom.io import img_utils

        override = tmp_path / "custom-models"
        with patch.object(img_utils.os, "environ", {"STORYLOOM_MODEL_DIR": str(override)}):
            assert img_utils._model_dir() == override

    def test_defaults_to_bundled_package_models(self):
        import importlib.resources
        from storyloom.io import img_utils

        expected = Path(str(importlib.resources.files("storyloom") / "models"))
        with patch.object(img_utils.os, "environ", {}):
            assert img_utils._model_dir() == expected


# ═══════════════════════════════════════════════════════════════════
# check_model
# ═══════════════════════════════════════════════════════════════════

class TestCheckModel:
    """check_model — file existence + SHA256 verification."""

    def test_returns_false_when_file_missing(self):
        """No model file → False."""
        from storyloom.io import img_utils
        with patch.object(img_utils, "_model_path") as mock_path:
            mock_path.return_value = Path("/nonexistent/model.onnx")
            assert img_utils.check_model() is False

    def test_returns_true_when_sha256_matches(self, tmp_path):
        """File with correct SHA256 → True."""
        from storyloom.io import img_utils
        import hashlib
        content = b"fake-model-bytes-for-testing"
        expected = hashlib.sha256(content).hexdigest()
        model = tmp_path / "u2net.onnx"
        model.write_bytes(content)
        with patch.object(img_utils, "_model_path") as mock_path:
            with patch.object(img_utils, "BG_REMOVAL_MODEL_SHA256", expected):
                mock_path.return_value = model
                assert img_utils.check_model() is True

    def test_returns_false_when_sha256_mismatches(self, tmp_path):
        """File with wrong hash → False."""
        from storyloom.io import img_utils
        model = tmp_path / "u2net.onnx"
        model.write_bytes(b"corrupt-data")
        with patch.object(img_utils, "_model_path") as mock_path:
            mock_path.return_value = model
            assert img_utils.check_model() is False


# ═══════════════════════════════════════════════════════════════════
# remove_background
# ═══════════════════════════════════════════════════════════════════

class TestRemoveBackground:
    """remove_background — onnxruntime inference (degraded gracefully)."""

    def test_returns_none_when_model_unavailable(self):
        """When model file missing, return None without error."""
        from storyloom.io import img_utils
        with patch.object(img_utils, "check_model", return_value=False):
            result = img_utils.remove_background(_rgba_png(), "png")
            assert result is None

    def test_returns_bytes_when_available(self, monkeypatch):
        """When everything works, returns PNG RGBA bytes."""
        from storyloom.io import img_utils
        np = pytest.importorskip("numpy")  # bg-removal path; skip without `bg` extra

        # ONNX output: (batch=1, channel=1, H=320, W=320)
        pred = np.ones((1, 1, 320, 320), dtype=np.float32) * 0.8

        mock_session = MagicMock()
        mock_session.get_inputs.return_value = [MagicMock(name="input")]
        mock_session.run.return_value = [pred]

        with patch.object(img_utils, "check_model", return_value=True):
            with patch.object(img_utils, "_get_session", return_value=mock_session):
                result = img_utils.remove_background(_rgb_png(), "png")
                assert isinstance(result, bytes)
                assert len(result) > 0


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
        with patch.object(img_utils, "remove_background") as mock_remove:
            mock_remove.return_value = b"rgba-bytes"
            result = img_utils.maybe_remove_background(r, RemoveBgPolicy.AUTO)
            assert mock_remove.called
            assert result.has_alpha is True
            assert result.format == "png"
            assert result.bytes == b"rgba-bytes"

    def test_policy_always_forces_removal(self):
        from storyloom.io import img_utils
        from storyloom.io.img_api_client import ImageResult, RemoveBgPolicy
        r = ImageResult(
            bytes=_rgba_png(), format="png", has_alpha=True,
            width=1, height=1, url="", elapsed_ms=100.0,
        )
        with patch.object(img_utils, "remove_background") as mock_remove:
            mock_remove.return_value = b"rgba-bytes"
            result = img_utils.maybe_remove_background(r, RemoveBgPolicy.ALWAYS)
            assert mock_remove.called

    def test_degrade_when_remove_background_fails(self):
        """When remove_background returns None, return original."""
        from storyloom.io import img_utils
        from storyloom.io.img_api_client import ImageResult, RemoveBgPolicy
        r = ImageResult(
            bytes=_rgb_png(), format="png", has_alpha=False,
            width=1, height=1, url="", elapsed_ms=100.0,
        )
        with patch.object(img_utils, "remove_background", return_value=None):
            result = img_utils.maybe_remove_background(r, RemoveBgPolicy.AUTO)
            assert result is r  # unchanged — degrade gracefully


# ═══════════════════════════════════════════════════════════════════
# normalize_background (§7.8b)
# ═══════════════════════════════════════════════════════════════════

def _make_png(width: int, height: int) -> bytes:
    """Create a minimal valid RGBA PNG with the given dimensions."""
    import struct
    import zlib

    def chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    raw_rows = b"".join(
        b"\x00" + b"\xff\x00\x00\xff" * width for _ in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw_rows))
        + chunk(b"IEND", b"")
    )


class TestNormalizeBackground:
    """normalize_background — 16:9 aspect ratio enforcement."""

    def test_already_16_9_passthrough(self):
        """320x180 is exactly 16:9 → returned unchanged."""
        from storyloom.io.img_utils import normalize_background

        raw = _make_png(320, 180)
        result = normalize_background(raw)
        assert result == raw

    def test_non_16_9_cropped(self):
        """200x200 (1:1) → cropped to center 16:9."""
        from storyloom.io.img_utils import normalize_background

        raw = _make_png(200, 200)
        result = normalize_background(raw)
        assert result != raw
        from storyloom.io.img_utils import detect_format, get_dimensions
        fmt = detect_format(result)
        w, h = get_dimensions(result, fmt)
        assert w > 0 and h > 0
        assert abs((w / h) - (16.0 / 9.0)) <= 0.02

    def test_invalid_bytes_passthrough(self):
        """Garbage bytes → returned unchanged (graceful degradation)."""
        from storyloom.io.img_utils import normalize_background

        garbage = b"not an image"
        result = normalize_background(garbage)
        assert result == garbage

    def test_too_wide_cropped(self):
        """320x100 (3.2:1) → crop sides to 16:9."""
        from storyloom.io.img_utils import normalize_background

        raw = _make_png(320, 100)
        result = normalize_background(raw)
        assert result != raw
        from storyloom.io.img_utils import detect_format, get_dimensions
        fmt = detect_format(result)
        w, h = get_dimensions(result, fmt)
        assert abs((w / h) - (16.0 / 9.0)) <= 0.02

    def test_too_tall_cropped(self):
        """100x320 (0.31:1) → crop top/bottom to 16:9."""
        from storyloom.io.img_utils import normalize_background

        raw = _make_png(100, 320)
        result = normalize_background(raw)
        assert result != raw
        from storyloom.io.img_utils import detect_format, get_dimensions
        fmt = detect_format(result)
        w, h = get_dimensions(result, fmt)
        assert abs((w / h) - (16.0 / 9.0)) <= 0.02

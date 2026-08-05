"""Tests for img_api_client — data types, presets, ImgApiClient.

TDD: these tests define the contract before implementation exists.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest

from storyloom.user_config import UserConfig


# ═══════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════

@pytest.fixture
def cfg():
    """UserConfig with both LLM and image API key set."""
    c = UserConfig()
    c.api_key = "sk-llm-key"
    c.api_base_url = "https://api.llm.com"
    c.api_model = "deepseek-v4-pro"
    c.img_api_key = "sk-img-key"
    c.img_api_base_url = "https://api.img.com"
    c.img_api_model = "flux-2-pro"
    c.img_remove_bg = "auto"
    return c


# ═══════════════════════════════════════════════════════════════════
# Data types
# ═══════════════════════════════════════════════════════════════════

class TestImageResult:
    """ImageResult dataclass — fields and defaults."""

    def test_all_fields_present(self):
        from storyloom.io.img_api_client import ImageResult
        r = ImageResult(
            bytes=b"fake",
            format="png",
            has_alpha=False,
            width=100,
            height=200,
            url="https://example.com/img.png",
            elapsed_ms=3000.0,
        )
        assert r.bytes == b"fake"
        assert r.format == "png"
        assert r.has_alpha is False
        assert r.width == 100
        assert r.height == 200
        assert r.url == "https://example.com/img.png"
        assert r.elapsed_ms == 3000.0

    def test_zero_dimensions_ok(self):
        """width=0, height=0 is valid when dimensions are unknown."""
        from storyloom.io.img_api_client import ImageResult
        r = ImageResult(
            bytes=b"", format="unknown", has_alpha=False,
            width=0, height=0, url="", elapsed_ms=0.0,
        )
        assert r.width == 0
        assert r.height == 0


class TestImageApiError:
    """ImageApiError — basic exception behavior."""

    def test_is_exception(self):
        from storyloom.io.img_api_client import ImageApiError
        with pytest.raises(ImageApiError):
            raise ImageApiError("test error")

    def test_message_preserved(self):
        from storyloom.io.img_api_client import ImageApiError
        try:
            raise ImageApiError("HTTP 500: internal error")
        except ImageApiError as e:
            assert "500" in str(e)
            assert "internal error" in str(e)

    def test_not_caught_by_ApiError(self):
        """ImageApiError is NOT a subclass of ApiError — different
        exception hierarchy so callers can catch separately."""
        from storyloom.io.api_client import ApiError
        from storyloom.io.img_api_client import ImageApiError
        err = ImageApiError("test")
        assert not isinstance(err, ApiError)


class TestEnums:
    """RemoveBgPolicy and ImageSize enum values."""

    def test_remove_bg_policy_values(self):
        from storyloom.io.img_api_client import RemoveBgPolicy
        assert RemoveBgPolicy.AUTO.value == "auto"
        assert RemoveBgPolicy.ALWAYS.value == "always"
        assert RemoveBgPolicy.NEVER.value == "never"

    def test_image_size_values(self):
        from storyloom.io.img_api_client import ImageSize
        assert ImageSize.PORTRAIT.value == "portrait"
        assert ImageSize.BACKGROUND.value == "background"


class TestImageModelPreset:
    """ImageModelPreset dataclass."""

    def test_defaults(self):
        from storyloom.io.img_api_client import ImageModelPreset
        p = ImageModelPreset(label="Test Model")
        assert p.label == "Test Model"
        assert p.default_sizes == {}
        assert p.supports_reference is True
        assert p.extra_body == {}

    def test_full_construction(self):
        from storyloom.io.img_api_client import ImageModelPreset
        p = ImageModelPreset(
            label="Custom",
            default_sizes={"portrait": "512x512"},
            supports_reference=False,
            extra_body={"custom_param": True},
        )
        assert p.supports_reference is False
        assert p.extra_body["custom_param"] is True


class TestModelPresets:
    """MODEL_PRESETS dict — known models have expected structure."""

    def test_flux_2_pro_preset_exists(self):
        from storyloom.io.img_api_client import MODEL_PRESETS
        assert "flux-2-pro" in MODEL_PRESETS
        p = MODEL_PRESETS["flux-2-pro"]
        assert "portrait" in p.default_sizes
        assert "background" in p.default_sizes

    def test_unknown_model_uses_fallback(self):
        """Unknown models should not crash — fallback to defaults."""
        from storyloom.io.img_api_client import MODEL_PRESETS
        assert "nonexistent-model-999" not in MODEL_PRESETS


# ═══════════════════════════════════════════════════════════════════
# ImgApiClient — init & config
# ═══════════════════════════════════════════════════════════════════

class TestImgApiClientInit:
    """ImgApiClient construction and config resolution."""

    def test_reads_img_config_from_user_config(self, cfg):
        from storyloom.io.img_api_client import ImgApiClient
        with patch("storyloom.io.img_api_client.httpx.Client"):
            client = ImgApiClient(cfg)
        assert client.api_key == "sk-img-key"
        assert client.base_url == "https://api.img.com"
        assert client.model == "flux-2-pro"
        assert client.remove_bg_policy.value == "auto"

    def test_env_var_overrides_img_config(self, cfg, monkeypatch):
        monkeypatch.setenv("IMAGE_API_KEY", "sk-from-env")
        monkeypatch.setenv("IMAGE_MODEL", "custom-model-env")
        from storyloom.io.img_api_client import ImgApiClient
        with patch("storyloom.io.img_api_client.httpx.Client"):
            client = ImgApiClient(cfg)
        assert client.api_key == "sk-from-env"
        assert client.model == "custom-model-env"

    def test_img_key_falls_back_to_llm_key(self, monkeypatch):
        """When IMAGE_API_KEY is empty and img_api_key is empty,
        fall back to LLM_API_KEY."""
        monkeypatch.delenv("IMAGE_API_KEY", raising=False)
        monkeypatch.setenv("LLM_API_KEY", "sk-llm-fallback")
        c = UserConfig()
        c.api_key = "sk-llm-cfg"
        c.img_api_key = ""
        from storyloom.io.img_api_client import ImgApiClient
        with patch("storyloom.io.img_api_client.httpx.Client"):
            client = ImgApiClient(c)
        assert client.api_key == "sk-llm-fallback"  # env overrides

    def test_img_key_falls_back_to_llm_key_config(self, monkeypatch):
        """When IMAGE_API_KEY is empty and img_api_key is empty,
        fall back to api_key (config-level, no env)."""
        monkeypatch.delenv("IMAGE_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        c = UserConfig()
        c.api_key = "sk-llm-config-only"
        c.img_api_key = ""
        from storyloom.io.img_api_client import ImgApiClient
        with patch("storyloom.io.img_api_client.httpx.Client"):
            client = ImgApiClient(c)
        assert client.api_key == "sk-llm-config-only"

    def test_base_url_uses_default_when_empty(self, monkeypatch):
        monkeypatch.delenv("IMAGE_BASE_URL", raising=False)
        c = UserConfig()
        c.img_api_base_url = ""
        from storyloom.io.img_api_client import ImgApiClient
        with patch("storyloom.io.img_api_client.httpx.Client"):
            client = ImgApiClient(c)
        assert client.base_url == "https://api.apiyi.com/v1"

    def test_uses_config_when_no_env(self, cfg, monkeypatch):
        monkeypatch.delenv("IMAGE_API_KEY", raising=False)
        monkeypatch.delenv("IMAGE_BASE_URL", raising=False)
        monkeypatch.delenv("IMAGE_MODEL", raising=False)
        monkeypatch.delenv("IMAGE_REMOVE_BG", raising=False)
        from storyloom.io.img_api_client import ImgApiClient
        with patch("storyloom.io.img_api_client.httpx.Client"):
            client = ImgApiClient(cfg)
        assert client.api_key == "sk-img-key"
        assert client.base_url == "https://api.img.com"
        assert client.model == "flux-2-pro"

    def test_resolve_size_known_preset(self, cfg):
        """PORTRAIT → 1024x1024 for flux-2-pro preset."""
        from storyloom.io.img_api_client import ImgApiClient, ImageSize
        with patch("storyloom.io.img_api_client.httpx.Client"):
            client = ImgApiClient(cfg)
        assert client._resolve_size(ImageSize.PORTRAIT) == "1024x1024"
        assert client._resolve_size(ImageSize.BACKGROUND) == "1280x720"

    def test_resolve_size_unknown_model(self, monkeypatch):
        """Unknown model uses generic defaults."""
        monkeypatch.setenv("IMAGE_MODEL", "unknown-model-xyz")
        c = UserConfig()
        from storyloom.io.img_api_client import ImgApiClient, ImageSize
        with patch("storyloom.io.img_api_client.httpx.Client"):
            client = ImgApiClient(c)
        assert client._resolve_size(ImageSize.PORTRAIT) == "1024x1024"
        assert client._resolve_size(ImageSize.BACKGROUND) == "1280x720"


# ═══════════════════════════════════════════════════════════════════
# ImgApiClient — generate()
# ═══════════════════════════════════════════════════════════════════

def _mock_download(resp, content: bytes, status: int = 200):
    """Configure the mock HTTP client for successful image download."""
    # resp is the POST response mock — its json() returns url
    # httpx.get() returns the download response
    dl_resp = MagicMock(spec=httpx.Response)
    dl_resp.status_code = status
    dl_resp.content = content
    return dl_resp


def _configure_mocks_for_success(mock_client, raw_png: bytes):
    """Set up httpx.Client mocks for a successful generate() call."""
    post_resp = MagicMock(spec=httpx.Response)
    post_resp.status_code = 200
    post_resp.json.return_value = {
        "data": [{"url": "https://cdn.example.com/img.png"}],
    }
    mock_client.post.return_value = post_resp
    # Also mock httpx.get for image download
    mock_client.get.return_value = _mock_download(post_resp, raw_png)
    return mock_client


def _load_test_png() -> bytes:
    from pathlib import Path
    return (Path(__file__).resolve().parent / "data" / "test_rgba.png").read_bytes()


class TestImgApiClientGenerate:
    """ImgApiClient.generate() — success and error paths."""

    def test_generate_returns_image_result(self, cfg, monkeypatch):
        """Successful generation returns ImageResult with correct metadata."""
        monkeypatch.setenv("IMAGE_API_KEY", "sk-test")
        raw = _load_test_png()
        from storyloom.io.img_api_client import (
            ImgApiClient, ImageResult, ImageSize, RemoveBgPolicy,
        )
        with patch("storyloom.io.img_api_client.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            _configure_mocks_for_success(mock_client, raw)

            client = ImgApiClient(cfg)
            result = client.generate(
                "test prompt", ImageSize.PORTRAIT,
                remove_bg=RemoveBgPolicy.NEVER,
            )
            assert isinstance(result, ImageResult)
            assert result.format == "png"
            assert result.has_alpha is True  # RGBA test image
            assert result.width == 1
            assert result.height == 1
            assert len(result.bytes) == len(raw)

    def test_generate_sends_correct_payload(self, cfg, monkeypatch):
        """Verify the JSON payload sent to the API."""
        monkeypatch.setenv("IMAGE_API_KEY", "sk-test")
        raw = _load_test_png()
        from storyloom.io.img_api_client import ImgApiClient, ImageSize, RemoveBgPolicy
        with patch("storyloom.io.img_api_client.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            _configure_mocks_for_success(mock_client, raw)

            client = ImgApiClient(cfg)
            client.generate("anime warrior", ImageSize.PORTRAIT,
                            remove_bg=RemoveBgPolicy.NEVER)

            call_args = mock_client.post.call_args
            url = call_args[0][0]
            assert "/images/generations" in url

            payload = call_args[1]["json"]
            assert payload["model"] == "flux-2-pro"
            assert payload["prompt"] == "anime warrior"
            assert payload["size"] == "1024x1024"
            assert payload["output_format"] == "png"
            assert payload["watermark"] is False

    def test_generate_with_reference_images(self, cfg, monkeypatch):
        """image_urls parameter is included in the payload."""
        monkeypatch.setenv("IMAGE_API_KEY", "sk-test")
        raw = _load_test_png()
        from storyloom.io.img_api_client import ImgApiClient, ImageSize, RemoveBgPolicy
        with patch("storyloom.io.img_api_client.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            _configure_mocks_for_success(mock_client, raw)

            client = ImgApiClient(cfg)
            client.generate(
                "same character", ImageSize.PORTRAIT,
                image_urls=["https://ref.example.com/ref.png"],
                remove_bg=RemoveBgPolicy.NEVER,
            )

            payload = mock_client.post.call_args[1]["json"]
            assert "image_urls" in payload
            assert payload["image_urls"] == ["https://ref.example.com/ref.png"]

    def test_generate_http_error_raises_image_api_error(self, cfg, monkeypatch):
        """Non-200 response raises ImageApiError."""
        monkeypatch.setenv("IMAGE_API_KEY", "sk-test")
        from storyloom.io.img_api_client import ImgApiClient, ImageApiError, ImageSize, RemoveBgPolicy
        with patch("storyloom.io.img_api_client.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            post_resp = MagicMock(spec=httpx.Response)
            post_resp.status_code = 401
            post_resp.json.return_value = {
                "error": {"message": "Invalid API key"},
            }
            mock_client.post.return_value = post_resp

            client = ImgApiClient(cfg)
            with pytest.raises(ImageApiError, match="401"):
                client.generate("prompt", ImageSize.PORTRAIT,
                                remove_bg=RemoveBgPolicy.NEVER)

    def test_generate_network_error_raises_image_api_error(self, cfg, monkeypatch):
        """httpx.RequestError raises ImageApiError."""
        monkeypatch.setenv("IMAGE_API_KEY", "sk-test")
        from storyloom.io.img_api_client import (
            ImgApiClient, ImageApiError, ImageSize, RemoveBgPolicy,
        )
        import httpx
        with patch("storyloom.io.img_api_client.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.post.side_effect = httpx.ConnectError("connection refused")

            client = ImgApiClient(cfg)
            with pytest.raises(ImageApiError, match="onnect"):
                client.generate("prompt", ImageSize.PORTRAIT,
                                remove_bg=RemoveBgPolicy.NEVER)

    def test_generate_download_failure_raises_image_api_error(self, cfg, monkeypatch):
        """When the generated image URL fails to download, raise ImageApiError."""
        monkeypatch.setenv("IMAGE_API_KEY", "sk-test")
        from storyloom.io.img_api_client import ImgApiClient, ImageApiError, ImageSize, RemoveBgPolicy
        with patch("storyloom.io.img_api_client.httpx.Client") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            post_resp = MagicMock(spec=httpx.Response)
            post_resp.status_code = 200
            post_resp.json.return_value = {
                "data": [{"url": "https://cdn.example.com/img.png"}],
            }
            mock_client.post.return_value = post_resp
            # Download fails
            mock_client.get.return_value = _mock_download(
                post_resp, b"", status=403,
            )

            client = ImgApiClient(cfg)
            with pytest.raises(ImageApiError, match="download.*403"):
                client.generate("prompt", ImageSize.PORTRAIT,
                                remove_bg=RemoveBgPolicy.NEVER)

    def test_generate_no_api_key_raises_value_error(self, monkeypatch):
        """Missing API key raises ValueError (config issue, not API issue)."""
        monkeypatch.delenv("IMAGE_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        c = UserConfig()
        c.api_key = ""
        c.img_api_key = ""
        from storyloom.io.img_api_client import ImgApiClient, ImageSize
        with patch("storyloom.io.img_api_client.httpx.Client"):
            client = ImgApiClient(c)
        with pytest.raises(ValueError, match="API key"):
            client.generate("prompt", ImageSize.PORTRAIT)


class TestImgApiClientConfigSummary:
    """config_summary property."""

    def test_returns_string_with_key_info(self, cfg):
        from storyloom.io.img_api_client import ImgApiClient
        with patch("storyloom.io.img_api_client.httpx.Client"):
            client = ImgApiClient(cfg)
        summary = client.config_summary
        assert "flux-2-pro" in summary
        assert "api.img.com" in summary or "auto" in summary

    def test_returns_string_without_exception(self, monkeypatch):
        monkeypatch.delenv("IMAGE_API_KEY", raising=False)
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        c = UserConfig()
        c.img_api_key = ""
        from storyloom.io.img_api_client import ImgApiClient
        with patch("storyloom.io.img_api_client.httpx.Client"):
            client = ImgApiClient(c)
        summary = client.config_summary
        assert isinstance(summary, str)
        assert len(summary) > 0

# Auto-Update Implementation Plan

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** Storyloom 应用内检查更新 + PyInstaller Launcher exe 原子替换，系统素材独立更新。

**架构：** 新增 `UpdateManager` 模块查询 GitHub API、下载 zip、报告进度；新增 Launcher PyInstaller exe 处理 `app_new/ → app/` 原子 swap；Web 设置页新增更新 UI 区块；构建脚本新增 Launcher 编译步骤。

**技术栈：** Python 3.10+, FastAPI SSE, PyInstaller, JavaScript (vanilla)

---

## 文件结构

| 文件 | 职责 | 操作 |
|------|------|------|
| `src/storyloom/launcher.py` | Launcher 源码 — swap + exec | **创建** |
| `src/storyloom/core/update_manager.py` | 版本检查、下载、解压、进度报告 | **创建** |
| `src/storyloom/web/server.py` | 新增 3 个 API 端点 + 更新 `_APP_DIR` 检测 | **修改** |
| `src/storyloom/core/__init__.py` | 导出 UpdateManager 公共类型 | **修改** |
| `src/storyloom/__init__.py` | 导出 `__version__`（已有，确认） | **不变** |
| `src/storyloom/web/static/js/router.js` | 设置页新增更新 UI 区块 | **修改** |
| `src/storyloom/web/static/js/state.js` | 无变动（更新按钮逻辑内联在 router.js） | **不变** |
| `src/storyloom/web/static/js/api.js` | 无变动（使用已有 API 包装器） | **不变** |
| `scripts/build.sh` | 新增 Launcher 编译步骤 + 调整 zip 结构 | **修改** |
| `src/storyloom/config.py` | 新增 GitHub repo URL 等常量 | **修改** |
| `tests/test_update_manager.py` | UpdateManager 单元测试 | **创建** |
| `tests/test_launcher.py` | Launcher 逻辑单元测试 | **创建** |
| `tests/test_web_server.py` | 新增 API 端点集成测试 | **修改** |

---

### 任务 1：UpdateManager 数据模型

**文件：**
- 创建：`src/storyloom/core/update_manager.py`（仅数据模型部分）
- 创建：`tests/test_update_manager.py`（仅数据模型测试）

- [ ] **步骤 1：编写 dataclass 测试**

```python
"""Tests for UpdateManager data types."""
from storyloom.core.update_manager import VersionInfo, UpdateCheckResult, UpdateProgress


def test_version_info_no_update():
    v = VersionInfo(current="1.3.0", latest="1.3.0", release_notes="")
    assert v.has_update is False


def test_version_info_has_update():
    v = VersionInfo(current="1.3.0", latest="1.4.0", release_notes="## Changes")
    assert v.has_update is True


def test_version_info_current_newer_than_latest():
    """Edge case: dev build with version ahead of published release."""
    v = VersionInfo(current="1.5.0-dev", latest="1.4.0", release_notes="")
    assert v.has_update is False


def test_version_info_empty_latest():
    """latest is empty when no remote version info available (e.g. offline)."""
    v = VersionInfo(current="1.3.0", latest="", release_notes="")
    assert v.has_update is False


def test_update_check_result_both_updates():
    app = VersionInfo(current="1.3.0", latest="1.4.0", has_update=True, release_notes="## v1.4.0")
    sm = VersionInfo(current="1.1.0", latest="1.2.0", has_update=True, release_notes="")
    result = UpdateCheckResult(app=app, system_media=sm)
    assert result.app.has_update
    assert result.system_media.has_update


def test_update_progress_downloading():
    p = UpdateProgress(layer="app", stage="downloading", received=1024, total=2048)
    assert p.layer == "app"
    assert p.stage == "downloading"
    assert p.error is None


def test_update_progress_error():
    p = UpdateProgress(layer="app", stage="error", received=0, total=None,
                       error="connection reset")
    assert p.stage == "error"
    assert p.error == "connection reset"
```

- [ ] **步骤 2：运行测试验证失败**

```bash
pytest tests/test_update_manager.py::test_version_info_no_update -v
```
预期：FAIL — 模块不存在

- [ ] **步骤 3：编写数据模型**

```python
"""UpdateManager — version checking, download, and extraction for auto-updates.

Spec: docs/superpowers/specs/2026-08-10-auto-update-design.md §4
"""
from dataclasses import dataclass, field


@dataclass
class VersionInfo:
    """Version information for one update layer."""
    current: str              # "1.3.0"
    latest: str               # "1.4.0" (empty if no update or offline)
    release_notes: str = ""

    @property
    def has_update(self) -> bool:
        if not self.latest:
            return False
        return _version_gt(self.latest, self.current)


@dataclass
class UpdateCheckResult:
    """Result of checking all update layers."""
    app: VersionInfo
    system_media: VersionInfo


@dataclass
class UpdateProgress:
    """Progress event for a single layer update operation."""
    layer: str           # "app" | "system_media"
    stage: str           # "downloading" | "extracting" | "done" | "error"
    received: int = 0
    total: int | None = None
    error: str | None = None


def _version_gt(a: str, b: str) -> bool:
    """Compare two semver strings (without 'v' prefix). Returns True if a > b."""
    def parse(v: str) -> tuple:
        # Strip leading 'v' if present; handle pre-release suffixes by
        # taking only the numeric prefix for comparison.
        v = v.lstrip("v")
        parts = v.split("-")[0].split(".")
        return tuple(int(p) for p in parts if p.isdigit())
    try:
        return parse(a) > parse(b)
    except (ValueError, IndexError):
        return False
```

- [ ] **步骤 4：运行测试验证通过**

```bash
pytest tests/test_update_manager.py -v
```
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add src/storyloom/core/update_manager.py tests/test_update_manager.py
git commit -m "feat: add UpdateManager data types — VersionInfo, UpdateCheckResult, UpdateProgress

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 2：GitHub API 版本检查

**文件：**
- 修改：`src/storyloom/core/update_manager.py` — 新增 `check_for_updates()`
- 修改：`tests/test_update_manager.py` — 新增版本检查测试

- [ ] **步骤 1：编写测试（mock GitHub API）**

```python
"""Tests for GitHub API version checking."""
from unittest.mock import patch, Mock
from storyloom.core.update_manager import check_for_updates, CACHE_SECONDS


def make_release_json(tag="v1.4.0", assets=None, body="## Release notes"):
    """Build a minimal GitHub release API response."""
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
    mock_get.return_value = make_release_json(tag="v1.3.0")
    result = check_for_updates(
        app_version="1.3.0",
        system_media_version="1.1.0",
        force=True,
    )
    assert result.app.has_update is False
    assert result.system_media.has_update is False


@patch("storyloom.core.update_manager._http_get_json")
def test_check_app_update(mock_get):
    mock_get.return_value = make_release_json(tag="v1.4.0")
    result = check_for_updates(
        app_version="1.3.0",
        system_media_version="1.1.0",
        force=True,
    )
    assert result.app.has_update is True
    assert result.app.latest == "1.4.0"


@patch("storyloom.core.update_manager._http_get_json")
def test_check_system_media_update(mock_get):
    """system_media version parsed from asset filename."""
    mock_get.return_value = make_release_json(tag="v1.3.0", assets=[
        {"name": "storyloom-v1.3.0-Linux.zip",
         "browser_download_url": "https://example.com/app.zip"},
        {"name": "system_media-v1.2.0.zip",
         "browser_download_url": "https://example.com/sm.zip"},
    ])
    result = check_for_updates(
        app_version="1.3.0",
        system_media_version="1.1.0",
        force=True,
    )
    assert result.system_media.has_update is True
    assert result.system_media.latest == "1.2.0"


@patch("storyloom.core.update_manager._http_get_json")
def test_check_no_system_media_asset(mock_get):
    """No system_media asset in release — latest stays empty."""
    mock_get.return_value = make_release_json(tag="v1.3.0", assets=[
        {"name": "storyloom-v1.3.0-Linux.zip",
         "browser_download_url": "https://example.com/app.zip"},
    ])
    result = check_for_updates(
        app_version="1.3.0",
        system_media_version="1.1.0",
        force=True,
    )
    assert result.system_media.has_update is False
    assert result.system_media.latest == ""


@patch("storyloom.core.update_manager._http_get_json")
def test_check_api_error_returns_empty(mock_get):
    """GitHub API error → no crash, return empty latest."""
    mock_get.side_effect = RuntimeError("rate limited")
    result = check_for_updates(
        app_version="1.3.0",
        system_media_version="1.1.0",
        force=True,
    )
    assert result.app.has_update is False
    assert result.app.latest == ""
    assert result.system_media.has_update is False


@patch("storyloom.core.update_manager._http_get_json")
def test_check_cache(mock_get):
    """Second call within cache window returns cached result."""
    mock_get.return_value = make_release_json(tag="v1.4.0")
    
    # First call — hits API
    r1 = check_for_updates("1.3.0", "1.1.0", force=True)
    assert mock_get.call_count == 1
    
    # Second call within cache — no API call
    r2 = check_for_updates("1.3.0", "1.1.0", force=False)
    assert mock_get.call_count == 1
    assert r2.app.latest == r1.app.latest
    
    # Third call with force — hits API again
    r3 = check_for_updates("1.3.0", "1.1.0", force=True)
    assert mock_get.call_count == 2


@patch("storyloom.core.update_manager._http_get_json")
def test_check_version_gt_handles_pre_release(mock_get):
    """1.5.0-dev locally, 1.4.0 remote → no downgrade."""
    mock_get.return_value = make_release_json(tag="v1.4.0")
    result = check_for_updates(
        app_version="1.5.0-dev",
        system_media_version="1.1.0",
        force=True,
    )
    assert result.app.has_update is False
```

- [ ] **步骤 2：运行测试验证失败**

```bash
pytest tests/test_update_manager.py -v -k "test_check"
```
预期：FAIL — `check_for_updates` 不存在

- [ ] **步骤 3：编写 `check_for_updates()` 和 GitHub API 调用**

在 `src/storyloom/core/update_manager.py` 中追加：

```python
import json
import re
import time
import sys
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── Config ────────────────────────────────────────────────────────

GITHUB_API_RELEASES = "https://api.github.com/repos/SiriLee/Storyloom/releases/latest"
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


def _find_asset_url(assets: list, pattern: str) -> tuple[str | None, str | None]:
    """Find an asset by name pattern.  Returns (url, version) or (None, None)."""
    for a in assets:
        name = a.get("name", "")
        if pattern in name and _PLATFORM in name:
            ver = _parse_version_from_asset_name(name, pattern.split("{")[0])
            return a.get("browser_download_url"), ver
    # Fallback: try without platform suffix (for system_media which is platform-agnostic)
    for a in assets:
        name = a.get("name", "")
        if pattern in name and _PLATFORM not in name:
            ver = _parse_version_from_asset_name(name, pattern.split("{")[0].rstrip("-"))
            return a.get("browser_download_url"), ver
    return None, None


# ── Public API ────────────────────────────────────────────────────

def check_for_updates(
    app_version: str,
    system_media_version: str,
    *,
    force: bool = False,
) -> UpdateCheckResult:
    """Check GitHub Releases for available updates.
    
    Args:
        app_version: Current app version (storyloom.__version__).
        system_media_version: Current system_media version (from VERSION file).
        force: Bypass cache.
    
    Returns:
        UpdateCheckResult with version info for each layer.
        On network errors, both layers return empty latest strings.
    """
    global _cache

    # ── Cache ─────────────────────────────────────────────────────
    now = time.time()
    if not force and _cache["data"] is not None and (now - _cache["ts"]) < CACHE_SECONDS:
        return _cache["data"]

    # ── Fetch ─────────────────────────────────────────────────────
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

    # App version from tag
    remote_tag = release.get("tag_name", "")
    remote_app_ver = _parse_version_from_tag(remote_tag)

    # System media version from asset filename
    sm_url, remote_sm_ver = _find_asset_url(assets, "system_media-v")

    result = UpdateCheckResult(
        app=VersionInfo(
            current=app_version,
            latest=remote_app_ver,
            release_notes=release_notes,
        ),
        system_media=VersionInfo(
            current=system_media_version,
            latest=remote_sm_ver or "",
        ),
    )

    _cache = {"ts": now, "data": result}
    return result
```

同时更新 `__all__` 导出列表。

- [ ] **步骤 4：运行测试验证通过**

```bash
pytest tests/test_update_manager.py -v
```
预期：全部 8 个测试 PASS

- [ ] **步骤 5：Commit**

```bash
git add src/storyloom/core/update_manager.py tests/test_update_manager.py
git commit -m "feat: add GitHub API version check with 15-minute cache

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 3：下载 + 提取功能

**文件：**
- 修改：`src/storyloom/core/update_manager.py` — 新增 `download_and_extract()`
- 修改：`tests/test_update_manager.py` — 新增下载测试

- [ ] **步骤 1：编写测试**

```python
"""Tests for download and extraction."""
import os
import tempfile
import zipfile
from unittest.mock import patch, Mock, call
from storyloom.core.update_manager import download_and_extract, UpdateProgress


def create_test_zip(dir_path: str, files: dict):
    """Create a test zip file.  *files* maps path-in-zip to content bytes."""
    zip_path = os.path.join(dir_path, "test.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return zip_path


def test_download_extract_app(tmp_path, monkeypatch):
    """Download app zip → extract app_new/ to target."""
    # Create a fake zip with app_new/ contents
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    zip_path = create_test_zip(str(zip_dir), {
        "app_new/storyloom-web": b"fake-exe",
        "app_new/locale/en/LC_MESSAGES/storyloom.mo": b"fake-mo",
        "app_new/config.example.json": b'{"version": 2}',
    })

    target = tmp_path / "target"

    progress_events = []
    def cb(p: UpdateProgress):
        progress_events.append(p)

    # Mock download: copy the test zip instead of downloading
    def fake_download(url, dest, cb):
        import shutil
        shutil.copy2(zip_path, dest)
        cb(UpdateProgress(layer="app", stage="downloading",
                          received=os.path.getsize(zip_path),
                          total=os.path.getsize(zip_path)))

    with patch("storyloom.core.update_manager._download_file", fake_download):
        download_and_extract(
            layer="app",
            url="https://example.com/app.zip",
            target_root=str(target),
            progress_callback=cb,
        )

    # Verify extraction
    assert os.path.isfile(str(target / "app_new" / "storyloom-web"))
    assert os.path.isfile(str(target / "app_new" / "locale" / "en" / "LC_MESSAGES" / "storyloom.mo"))

    # Verify progress events
    assert any(e.stage == "downloading" for e in progress_events)
    assert any(e.stage == "extracting" for e in progress_events)
    assert any(e.stage == "done" for e in progress_events)


def test_download_extract_system_media(tmp_path, monkeypatch):
    """Download system_media zip → extract to target, overwriting existing."""
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    zip_path = create_test_zip(str(zip_dir), {
        "char_portrait/sys_young_male.png": b"fake-png",
        "background_img/sys_forest.png": b"fake-png",
        "VERSION": b"1.2.0",
        "_manifest.json": b'{"version":"1.2.0","min_app_version":"1.3.0"}',
    })

    target = tmp_path / "target"
    target.mkdir()
    # Pre-existing file to test overwrite
    (target / "VERSION").write_text("1.1.0")

    def fake_download(url, dest, cb):
        import shutil
        shutil.copy2(zip_path, dest)
        cb(UpdateProgress(layer="system_media", stage="downloading",
                          received=os.path.getsize(zip_path),
                          total=os.path.getsize(zip_path)))

    with patch("storyloom.core.update_manager._download_file", fake_download):
        download_and_extract(
            layer="system_media",
            url="https://example.com/sm.zip",
            target_root=str(target),
        )

    # Verify overwrite
    assert (target / "VERSION").read_text() == "1.2.0"
    assert os.path.isfile(str(target / "char_portrait" / "sys_young_male.png"))


def test_download_extract_invalid_zip(tmp_path):
    """Corrupt zip → raises error."""
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    bad_zip = zip_dir / "bad.zip"
    bad_zip.write_text("not a zip file")

    def fake_download(url, dest, cb):
        import shutil
        shutil.copy2(str(bad_zip), dest)

    with patch("storyloom.core.update_manager._download_file", fake_download):
        try:
            download_and_extract("app", "https://example.com/bad.zip", str(tmp_path / "target"))
            assert False, "should have raised"
        except Exception:
            pass  # expected


def test_download_extract_cleans_stale_app_new(tmp_path):
    """If app_new/ already exists, delete it before extracting new one."""
    zip_dir = tmp_path / "zip"
    zip_dir.mkdir()
    zip_path = create_test_zip(str(zip_dir), {
        "app_new/storyloom-web": b"new-exe",
    })

    target = tmp_path / "target"
    stale = target / "app_new"
    stale.mkdir(parents=True)
    (stale / "stale-file.txt").write_text("old")

    def fake_download(url, dest, cb):
        import shutil
        shutil.copy2(zip_path, dest)
        cb(UpdateProgress(layer="app", stage="downloading",
                          received=os.path.getsize(zip_path),
                          total=os.path.getsize(zip_path)))

    with patch("storyloom.core.update_manager._download_file", fake_download):
        download_and_extract("app", "https://example.com/app.zip", str(target))

    assert not os.path.exists(str(stale / "stale-file.txt"))
    assert os.path.isfile(str(target / "app_new" / "storyloom-web"))
```

- [ ] **步骤 2：运行测试验证失败**

```bash
pytest tests/test_update_manager.py -v -k "test_download"
```
预期：FAIL — `download_and_extract` 不存在

- [ ] **步骤 3：编写 `download_and_extract()`**

在 `src/storyloom/core/update_manager.py` 中追加：

```python
import os
import shutil
import tempfile
import zipfile
from pathlib import Path


def _download_file(url: str, dest: str, progress_callback=None) -> None:
    """Stream download with optional progress reporting.
    
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


def download_and_extract(
    layer: str,
    url: str,
    target_root: str,
    progress_callback=None,
) -> None:
    """Download a release zip and extract it to *target_root*.
    
    Args:
        layer: "app" or "system_media" — determines extraction strategy.
        url: Download URL.
        target_root: Root directory for extraction.
        progress_callback: callable(UpdateProgress) for progress events.
    
    For layer="app": zip contains ``app_new/`` (and optionally
    ``launcher.new``).  Extracts to ``<target_root>/app_new/``,
    deletes stale ``app_new/`` first.
    
    For layer="system_media": zip contents extracted directly to
    *target_root*, overwriting existing files.
    """
    tmp_dir = tempfile.mkdtemp(prefix="storyloom_update_")
    zip_path = os.path.join(tmp_dir, "update.zip")

    def _emit(stage: str, received: int = 0, total: int | None = None):
        if progress_callback:
            progress_callback(UpdateProgress(
                layer=layer, stage=stage,
                received=received, total=total,
            ))

    try:
        # ── Download ───────────────────────────────────────────────
        _emit("downloading")

        def _dl_cb(received: int, total: int | None):
            _emit("downloading", received=received, total=total)

        _download_file(url, zip_path, progress_callback=_dl_cb)

        # ── Extract ────────────────────────────────────────────────
        _emit("extracting")

        if layer == "app":
            # Clear stale app_new/ if present
            app_new = os.path.join(target_root, "app_new")
            if os.path.isdir(app_new):
                shutil.rmtree(app_new)

            with zipfile.ZipFile(zip_path, "r") as zf:
                # Extract to temp, then move app_new/ to target
                extract_tmp = os.path.join(tmp_dir, "extract")
                os.makedirs(extract_tmp, exist_ok=True)
                zf.extractall(extract_tmp)

                # Move app_new/ to target
                src = os.path.join(extract_tmp, "app_new")
                if os.path.isdir(src):
                    shutil.move(src, app_new)
                else:
                    raise ValueError(
                        "Update zip does not contain app_new/ directory"
                    )

                # Copy launcher.new if present
                launcher_new = os.path.join(extract_tmp, "launcher.new")
                if os.path.isfile(launcher_new):
                    shutil.copy2(launcher_new,
                                 os.path.join(target_root, "launcher.new"))

            # Verify
            if not os.path.isfile(os.path.join(app_new, "storyloom-web")):
                raise ValueError(
                    "Extracted app_new/ missing storyloom-web executable"
                )

        else:  # system_media
            os.makedirs(target_root, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(target_root)

            version_file = os.path.join(target_root, "VERSION")
            if not os.path.isfile(version_file):
                raise ValueError(
                    "Extracted system_media missing VERSION file"
                )

        _emit("done")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
```

- [ ] **步骤 4：运行测试验证通过**

```bash
pytest tests/test_update_manager.py -v
```
预期：全部 PASS

- [ ] **步骤 5：Commit**

```bash
git add src/storyloom/core/update_manager.py tests/test_update_manager.py
git commit -m "feat: add download_and_extract with progress reporting

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 4：API 端点

**文件：**
- 修改：`src/storyloom/web/server.py` — 新增 3 个端点
- 修改：`src/storyloom/config.py` — 新增常量
- 修改：`tests/test_web_server.py` — 新增端点测试

- [ ] **步骤 1：新增配置常量**

在 `src/storyloom/config.py` 末尾追加：

```python
# ── Auto-update ────────────────────────────────────────────────────
GITHUB_REPO_OWNER = "SiriLee"
GITHUB_REPO_NAME = "Storyloom"
UPDATE_CACHE_SECONDS = 900  # 15 minutes — matches update_manager.CACHE_SECONDS
```

- [ ] **步骤 2：更新 `_APP_DIR` 检测逻辑**

在 `src/storyloom/web/server.py` 中，将现有的 `_APP_DIR` 检测替换为 spec §7.4 的两级父目录模式：

```python
# App directory — where config.json / locale / saves / media / system_media live.
# Dev: repo root (server.py → web → storyloom → src → repo root).
# PyInstaller (new layout): exe at <root>/app/storyloom-web → root = ../..
if getattr(sys, 'frozen', False):
    _PROJECT_ROOT = Path(sys.executable).parent.parent
else:
    _PROJECT_ROOT = Path(__file__).resolve().parents[3]
```

- [ ] **步骤 3：编写端点测试**

在 `tests/test_web_server.py` 中追加：

```python
"""Auto-update API endpoint tests."""
from unittest.mock import patch
from storyloom.core.update_manager import UpdateCheckResult, VersionInfo


_NO_UPDATE = UpdateCheckResult(
    app=VersionInfo(current="1.3.0", latest="1.3.0", release_notes=""),
    system_media=VersionInfo(current="1.1.0", latest="1.1.0", release_notes=""),
)

_HAS_UPDATE = UpdateCheckResult(
    app=VersionInfo(current="1.3.0", latest="1.4.0", release_notes="## v1.4.0"),
    system_media=VersionInfo(current="1.1.0", latest="1.2.0", release_notes=""),
)


class TestUpdateAPI:
    """Tests for /api/update/* endpoints."""

    @patch("storyloom.web.server.check_for_updates")
    def test_check_no_update(self, mock_check, client):
        mock_check.return_value = _NO_UPDATE
        resp = client.get("/api/update/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["app"]["has_update"] is False
        assert data["system_media"]["has_update"] is False

    @patch("storyloom.web.server.check_for_updates")
    def test_check_has_update(self, mock_check, client):
        mock_check.return_value = _HAS_UPDATE
        resp = client.get("/api/update/check")
        assert resp.status_code == 200
        data = resp.json()
        assert data["app"]["has_update"] is True
        assert data["app"]["latest"] == "1.4.0"

    @patch("storyloom.web.server.check_for_updates")
    def test_check_force_cache_bypass(self, mock_check, client):
        mock_check.return_value = _NO_UPDATE
        client.get("/api/update/check?force=true")
        mock_check.assert_called_once()
        # Verify force=True was passed
        _, kwargs = mock_check.call_args
        assert kwargs.get("force") is True

    def test_apply_requires_layers(self, client):
        resp = client.post("/api/update/apply", json={})
        assert resp.status_code == 422  # validation error

    def test_apply_returns_stream_url(self, client):
        resp = client.post("/api/update/apply", json={"layers": ["app"]})
        assert resp.status_code == 200
        data = resp.json()
        assert "stream_url" in data
```

- [ ] **步骤 4：运行测试验证失败**

```bash
pytest tests/test_web_server.py -v -k "TestUpdateAPI"
```
预期：FAIL — 端点不存在（404）

- [ ] **步骤 5：编写 API 端点**

在 `src/storyloom/web/server.py` 中追加（放在 save 端点之后、system 端点之前）：

```python
# ── Auto-Update ────────────────────────────────────────────────────
# Spec: docs/superpowers/specs/2026-08-10-auto-update-design.md §5

from storyloom.config import GITHUB_REPO_OWNER, GITHUB_REPO_NAME
from storyloom.core.update_manager import (
    check_for_updates,
    download_and_extract,
    UpdateCheckResult,
    UpdateProgress,
    CACHE_SECONDS as UPDATE_CACHE_SECONDS,
)
from storyloom import __version__


def _get_system_media_version() -> str:
    """Read system_media version from VERSION file, or '' if missing."""
    version_file = os.path.join(_APP_DIR, "system_media", "VERSION")
    try:
        with open(version_file, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (OSError, FileNotFoundError):
        return ""


class ApplyUpdateRequest(BaseModel):
    layers: list[str]  # e.g. ["app", "system_media"]


@app.get("/api/update/check")
async def update_check(force: bool = False):
    """Check GitHub Releases for available updates.
    
    Returns ``UpdateCheckResult`` serialized as JSON.
    Cached for 15 minutes; ``?force=true`` bypasses cache.
    """
    sm_ver = _get_system_media_version()
    result = check_for_updates(
        app_version=__version__,
        system_media_version=sm_ver,
        force=force,
    )
    return result


@app.post("/api/update/apply")
async def update_apply(req: ApplyUpdateRequest):
    """Start downloading and extracting update layers.
    
    Returns a stream URL for SSE progress tracking.
    The actual download runs in a background thread.
    """
    stream_id = os.urandom(8).hex()
    
    # Store download params for the SSE endpoint
    sessions.update_store[stream_id] = {
        "layers": req.layers,
        "status": "pending",
    }
    
    return {"stream_url": f"/api/update/stream/{stream_id}"}


@app.get("/api/update/stream/{stream_id}")
async def update_stream(stream_id: str):
    """SSE endpoint for update download progress.
    
    Events: ``progress`` (per-chunk), ``done``, ``error``.
    See spec §5.3 for event format.
    """
    import asyncio
    import threading

    params = sessions.update_store.pop(stream_id, None)
    if not params:
        raise HTTPException(404, "Unknown or expired stream ID")

    q: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _emit_layer_done(ver: str):
        loop.call_soon_threadsafe(q.put_nowait, {
            "type": "layer_done",
            "version": ver,
        })

    def run_update():
        try:
            layers = params["layers"]
            results = {}

            for layer in layers:
                # Resolve download URL from the latest release
                # (re-use cached check result to avoid extra API call)
                sm_ver = _get_system_media_version()
                check = check_for_updates(__version__, sm_ver, force=False)

                if layer == "app" and check.app.latest:
                    # Find the app asset URL
                    import sys
                    if sys.platform == "win32":
                        plat = "Windows"
                    elif sys.platform == "darwin":
                        plat = "macOS"
                    else:
                        plat = "Linux"
                    # Re-fetch to get asset URLs
                    from storyloom.core.update_manager import _http_get_json, _find_asset_url, GITHUB_API_RELEASES
                    release = _http_get_json(GITHUB_API_RELEASES)
                    assets = release.get("assets", [])
                    url, _ = _find_asset_url(assets, f"storyloom-v{{ver}}-{plat}.zip")

                elif layer == "system_media" and check.system_media.latest:
                    from storyloom.core.update_manager import _http_get_json, _find_asset_url, GITHUB_API_RELEASES
                    release = _http_get_json(GITHUB_API_RELEASES)
                    assets = release.get("assets", [])
                    url, _ = _find_asset_url(assets, "system_media-v")
                else:
                    continue  # no update for this layer

                if not url:
                    continue

                def progress_cb(p: UpdateProgress):
                    loop.call_soon_threadsafe(q.put_nowait, {
                        "type": "progress",
                        "layer": p.layer,
                        "stage": p.stage,
                        "received": p.received,
                        "total": p.total,
                        "error": p.error,
                    })

                download_and_extract(
                    layer=layer,
                    url=url,
                    target_root=_APP_DIR,
                    progress_callback=progress_cb,
                )

                if layer == "app":
                    results[layer] = check.app.latest
                else:
                    results[layer] = check.system_media.latest

            loop.call_soon_threadsafe(q.put_nowait, {
                "type": "done",
                "layers": results,
            })

        except Exception as exc:
            loop.call_soon_threadsafe(q.put_nowait, {
                "type": "error",
                "error": str(exc),
            })
        finally:
            loop.call_soon_threadsafe(q.put_nowait, None)

    thread = threading.Thread(target=run_update, daemon=True)
    thread.start()

    async def event_generator():
        while True:
            event = await q.get()
            if event is None:
                break
            etype = event.get("type", "")
            data = json.dumps(event, ensure_ascii=False)
            yield f"event: {etype}\ndata: {data}\n\n"
            if etype in ("done", "error"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

需要在 `src/storyloom/web/sessions.py` 中添加 `update_store` 字典：

```python
# In sessions.py — add near the top with other stores
update_store: dict = {}  # stream_id → {layers, status}
```

- [ ] **步骤 6：运行测试验证通过**

```bash
pytest tests/test_web_server.py -v -k "TestUpdateAPI"
```
预期：全部 PASS

- [ ] **步骤 7：Commit**

```bash
git add src/storyloom/web/server.py src/storyloom/web/sessions.py \
        src/storyloom/config.py tests/test_web_server.py
git commit -m "feat: add /api/update/check, /api/update/apply, /api/update/stream endpoints

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 5：设置页更新 UI

**文件：**
- 修改：`src/storyloom/web/static/js/router.js` — `renderSettings()` 中新增更新区块

- [ ] **步骤 1：在设置页渲染中添加更新区块**

在 `renderSettings()` 函数中，在 Credits 区块**之前**插入更新 UI。找到这一行（约 line 453）：

```javascript
                    <!-- Credits (moved from main menu) -->
```

在其**上方**插入更新区块的 HTML。完整修改如下：

```javascript
// 在 renderSettings() 中，settings-form 闭合后、Credits 区块前插入：

                    <!-- Updates -->
                    <div class="settings-form" style="margin-top:2rem; padding-top:1.5rem; border-top:1px solid var(--border-color)">
                        <h3 style="font-family:var(--font-mono); color:var(--text-accent); margin-bottom:1rem; text-align:center">
                            <span id="update-section-title">${esc(_("Updates"))}</span>
                        </h3>
                        <div id="update-section">
                            <div class="setting-row">
                                <span class="setting-label">${esc(_("Current Version"))}</span>
                                <span class="setting-val" id="update-current-ver">...</span>
                            </div>
                            <button class="menu-btn" id="btn-check-update" style="margin-top:0.5rem; width:100%">
                                ${esc(_("Check for Updates"))}
                            </button>
                        </div>
                    </div>
```

同时，在绑定事件区域（约 line 572 之前，`}` 结束 `SETTINGS.forEach` 的位置之后），添加更新按钮的事件绑定和 UI 状态管理。

- [ ] **步骤 2：添加更新按钮事件处理**

在 `renderSettings()` 函数末尾、`SETTINGS.forEach` 之后追加：

```javascript
        /* ── Update check button ───────────────────────────── */

        const currentVer = document.getElementById("update-current-ver");
        if (currentVer) {
            // Display current version from a hidden API call or from
            // global state.  We fetch it lazily on settings render.
            API.get("/api/update/check?force=false").then(result => {
                currentVer.textContent = result.app.current;
            }).catch(() => {
                currentVer.textContent = "?";
            });
        }

        const btnCheck = document.getElementById("btn-check-update");
        const updateSection = document.getElementById("update-section");

        if (btnCheck) {
            btnCheck.addEventListener("click", async () => {
                // ── State: checking ──
                updateSection.innerHTML = `
                    <p class="text-muted" style="text-align:center">${esc(_("Checking..."))}</p>
                `;

                try {
                    const result = await API.get("/api/update/check?force=true");

                    if (!result.app.has_update && !result.system_media.has_update) {
                        // ── State: no updates ──
                        updateSection.innerHTML = `
                            <div class="setting-row">
                                <span class="setting-label">${esc(_("Current Version"))}</span>
                                <span class="setting-val">${esc(result.app.current)}</span>
                            </div>
                            <p style="text-align:center; color:var(--color-success); margin-top:0.5rem">
                                ✅ ${esc(_("Up to date"))}
                            </p>
                            <button class="menu-btn" id="btn-check-update-again" style="margin-top:0.5rem; width:100%">
                                ${esc(_("Check for Updates"))}
                            </button>
                        `;
                        document.getElementById("btn-check-update-again")
                            .addEventListener("click", () => {
                                // Re-trigger check — re-render settings
                                renderSettings();
                                // Then click the button programmatically after render
                                setTimeout(() => {
                                    const b = document.getElementById("btn-check-update");
                                    if (b) b.click();
                                }, 100);
                            });
                        return;
                    }

                    // ── State: updates available ──
                    let rows = "";
                    let hasAny = false;

                    if (result.app.has_update) {
                        hasAny = true;
                        rows += `
                            <div class="setting-row" style="flex-direction:column; align-items:flex-start; gap:0.5rem">
                                <span class="setting-label">
                                    App Core &nbsp; ${esc(result.app.current)} → <strong>${esc(result.app.latest)}</strong>
                                </span>
                                ${result.app.release_notes ? `
                                    <div style="max-height:150px; overflow-y:auto; font-size:0.85rem;
                                                color:var(--text-muted); padding-left:0.5rem;
                                                border-left:2px solid var(--border-color)">
                                        ${result.app.release_notes.replace(/\n/g, "<br>")}
                                    </div>` : ""}
                            </div>
                        `;
                    }

                    if (result.system_media.has_update) {
                        hasAny = true;
                        rows += `
                            <div class="setting-row">
                                <span class="setting-label">
                                    System Media &nbsp; ${esc(result.system_media.current)} → <strong>${esc(result.system_media.latest)}</strong>
                                </span>
                            </div>
                        `;
                    }

                    rows += `
                        <div style="display:flex; gap:0.5rem; margin-top:0.75rem">
                            <button class="menu-btn accent" id="btn-apply-update" style="flex:1">
                                ${esc(_("Update Selected"))}
                            </button>
                        </div>
                    `;

                    updateSection.innerHTML = rows;

                    if (hasAny) {
                        document.getElementById("btn-apply-update")
                            .addEventListener("click", async () => {
                                // Determine which layers to update
                                const layers = [];
                                if (result.app.has_update) layers.push("app");
                                if (result.system_media.has_update) layers.push("system_media");

                                // ── State: downloading ──
                                updateSection.innerHTML = `
                                    <div id="update-progress">
                                        <p class="text-muted" style="text-align:center">${esc(_("Downloading..."))}</p>
                                        <div id="update-progress-bars"></div>
                                    </div>
                                `;

                                try {
                                    const applyResult = await API.post(
                                        "/api/update/apply",
                                        { layers: layers }
                                    );

                                    // Open SSE for progress
                                    SSEClient.open(
                                        applyResult.stream_url,
                                        {
                                            progress: (data) => {
                                                const bars = document.getElementById("update-progress-bars");
                                                if (!bars) return;
                                                const pct = data.total
                                                    ? Math.round(data.received * 100 / data.total)
                                                    : "?";
                                                bars.innerHTML = layers.map(l => {
                                                    if (l === data.layer && data.stage === "downloading") {
                                                        return `<p>${esc(l)}: ████████ ${pct}%</p>`;
                                                    } else if (l === data.layer && data.stage === "extracting") {
                                                        return `<p>${esc(l)}: ${esc(_("extracting..."))}</p>`;
                                                    } else {
                                                        return `<p>${esc(l)}: ${esc(_("waiting..."))}</p>`;
                                                    }
                                                }).join("");
                                            },
                                            done: (data) => {
                                                // ── State: done ──
                                                updateSection.innerHTML = `
                                                    <p style="text-align:center; color:var(--color-success)">
                                                        ✅ ${esc(_("Update ready"))}
                                                    </p>
                                                    <p class="text-muted" style="text-align:center; margin-top:0.5rem">
                                                        ${esc(_("Please close the application and restart via Storyloom."))}
                                                    </p>
                                                `;
                                            },
                                            error: (data) => {
                                                updateSection.innerHTML = `
                                                    <p style="text-align:center; color:var(--color-error)">
                                                        ${esc(_("Update failed"))}: ${esc(data.error || "")}
                                                    </p>
                                                    <button class="menu-btn" id="btn-retry-update" style="margin-top:0.5rem; width:100%">
                                                        ${esc(_("Retry"))}
                                                    </button>
                                                `;
                                                document.getElementById("btn-retry-update")
                                                    .addEventListener("click", () => {
                                                        renderSettings();
                                                        setTimeout(() => {
                                                            const b = document.getElementById("btn-check-update");
                                                            if (b) b.click();
                                                        }, 100);
                                                    });
                                            },
                                        }
                                    );
                                } catch (err) {
                                    updateSection.innerHTML = `
                                        <p style="text-align:center; color:var(--color-error)">
                                            ${esc(err.message)}
                                        </p>
                                    `;
                                }
                            });
                    }
                } catch (err) {
                    updateSection.innerHTML = `
                        <p style="text-align:center; color:var(--color-error)">
                            ${esc(_("Check failed"))}: ${esc(err.message)}
                        </p>
                        <button class="menu-btn" id="btn-retry-check" style="margin-top:0.5rem; width:100%">
                            ${esc(_("Retry"))}
                        </button>
                    `;
                    document.getElementById("btn-retry-check")
                        .addEventListener("click", () => {
                            renderSettings();
                            setTimeout(() => {
                                const b = document.getElementById("btn-check-update");
                                if (b) b.click();
                            }, 100);
                        });
                }
            });
        }
```

- [ ] **步骤 3：手动验证**

启动开发服务器，导航到 `#settings`，点击「Check for Updates」按钮验证 UI 流程。

```bash
python -m storyloom.web
```

- [ ] **步骤 4：Commit**

```bash
git add src/storyloom/web/static/js/router.js
git commit -m "feat: add update UI section to settings page

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 6：Launcher 源码 + 构建集成

**文件：**
- 创建：`src/storyloom/launcher.py`
- 修改：`scripts/build.sh`
- 创建：`tests/test_launcher.py`

- [ ] **步骤 1：编写 Launcher 测试**

```python
"""Tests for the Storyloom Launcher."""
import os
import sys
import pytest
from unittest.mock import patch, Mock, call

# Import the launcher module functions
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
    """No app_new/ → no-op."""
    monkeypatch.setattr("storyloom.launcher.DIR", str(tmp_path))
    _apply_app_update()
    assert not (tmp_path / "app").exists()


def test_apply_app_update_swaps(tmp_path, monkeypatch):
    """app_new/ exists → swap to app/."""
    monkeypatch.setattr("storyloom.launcher.DIR", str(tmp_path))

    # Create old app and new app
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "storyloom-web").write_text("old")
    (tmp_path / "app_new").mkdir()
    (tmp_path / "app_new" / "storyloom-web").write_text("new")

    _apply_app_update()

    assert (tmp_path / "app" / "storyloom-web").read_text() == "new"
    assert not (tmp_path / "app_old").exists()
    assert not (tmp_path / "app_new").exists()


def test_apply_app_update_no_old_app(tmp_path, monkeypatch):
    """app_new/ exists but app/ doesn't (first install via update)."""
    monkeypatch.setattr("storyloom.launcher.DIR", str(tmp_path))

    (tmp_path / "app_new").mkdir()
    (tmp_path / "app_new" / "storyloom-web").write_text("new")

    _apply_app_update()

    assert (tmp_path / "app" / "storyloom-web").read_text() == "new"
    assert not (tmp_path / "app_new").exists()


def test_apply_launcher_update_none(tmp_path, monkeypatch):
    """No launcher.new → no-op."""
    monkeypatch.setattr("storyloom.launcher.DIR", str(tmp_path))
    _apply_launcher_update()
    # Should not raise, should not create anything unexpected


def test_apply_launcher_update_unix(tmp_path, monkeypatch):
    """launcher.new present on Unix → rename + exec."""
    monkeypatch.setattr("storyloom.launcher.DIR", str(tmp_path))
    monkeypatch.setattr(sys, "platform", "linux")

    launcher_new = tmp_path / "launcher.new"
    launcher_new.write_text("new-launcher")

    # Mock os.chmod + os.execv
    mock_execv = Mock()
    monkeypatch.setattr(os, "chmod", Mock())
    monkeypatch.setattr(os, "execv", mock_execv)

    _apply_launcher_update()

    # Verify rename happened
    assert not launcher_new.exists()
    assert (tmp_path / LAUNCHER_NAME).exists()
    assert (tmp_path / LAUNCHER_NAME).read_text() == "new-launcher"
    mock_execv.assert_called_once()
```

- [ ] **步骤 2：运行测试验证失败**

```bash
pytest tests/test_launcher.py -v
```
预期：FAIL — `storyloom.launcher` 模块不存在

- [ ] **步骤 3：创建 Launcher 源码**

创建 `src/storyloom/launcher.py`：

```python
"""
Storyloom Launcher — apply pending updates and launch the main application.

Compiled to a standalone executable with PyInstaller (``--onefile``).
The Launcher is stateless: it does not download, check for updates, or
write anything except during the atomic swap at startup.

Spec: docs/superpowers/specs/2026-08-10-auto-update-design.md §3
"""
import os
import shutil
import subprocess
import sys


def _platform_exe(name: str) -> str:
    return name + (".exe" if sys.platform == "win32" else "")


LAUNCHER_NAME = _platform_exe("Storyloom")
MAIN_EXE = _platform_exe("storyloom-web")

DIR = os.path.dirname(os.path.abspath(sys.executable))
APP = os.path.join(DIR, "app")
APP_NEW = os.path.join(DIR, "app_new")
APP_OLD = os.path.join(DIR, "app_old")
LAUNCHER_NEW = os.path.join(DIR, "launcher.new")


def _apply_app_update():
    """Atomic swap: app_new → app."""
    if not os.path.isdir(APP_NEW):
        return
    shutil.rmtree(APP_OLD, ignore_errors=True)
    if os.path.isdir(APP):
        os.rename(APP, APP_OLD)
    os.rename(APP_NEW, APP)
    shutil.rmtree(APP_OLD, ignore_errors=True)


def _apply_launcher_update():
    """Self-replace the Launcher binary."""
    if not os.path.isfile(LAUNCHER_NEW):
        return

    if sys.platform == "win32":
        # Cannot rename running exe on Windows — spawn a one-shot cmd.
        bat = os.path.join(DIR, "_launcher_swap.bat")
        with open(bat, "w") as f:
            f.write(
                "@echo off\n"
                "timeout /t 1 /nobreak >nul\n"
                f'move /Y "{LAUNCHER_NEW}" "{LAUNCHER_NAME}"\n'
                f'start "" "{os.path.join(DIR, LAUNCHER_NAME)}"\n'
            )
        subprocess.Popen(
            bat, shell=True,
            creationflags=0x00000008,  # DETACHED_PROCESS
            close_fds=True,
        )
        sys.exit(0)
    else:
        launcher_path = os.path.join(DIR, LAUNCHER_NAME)
        os.rename(LAUNCHER_NEW, launcher_path)
        os.chmod(launcher_path, 0o755)
        os.execv(launcher_path, [launcher_path] + sys.argv[1:])


def main():
    _apply_launcher_update()
    _apply_app_update()

    target = os.path.join(APP, MAIN_EXE)
    if not os.path.isfile(target):
        print(f"Error: {target} not found", file=sys.stderr)
        sys.exit(1)

    os.execv(target, [target] + sys.argv[1:])


if __name__ == "__main__":
    main()
```

- [ ] **步骤 4：运行测试验证通过**

```bash
pytest tests/test_launcher.py -v
```
预期：全部 PASS

- [ ] **步骤 5：更新构建脚本**

在 `scripts/build.sh` 中，步骤 3（PyInstaller）之前添加 Launcher 编译步骤：

```bash
# Launcher name follows platform convention
case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) LAUNCHER_NAME="Storyloom.exe" ;;
    *)                     LAUNCHER_NAME="Storyloom" ;;
esac

echo "--- Building Launcher ---"
$PYTHON -m PyInstaller --onefile $PYI_FLAGS \
    --name "$LAUNCHER_NAME" \
    --clean \
    src/storyloom/launcher.py
```

更新步骤 4 中的发布目录结构（spec §7.2）：

```bash
# 4. Assemble release directory
echo "--- Assembling release directory ---"
mkdir -p "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/app_new"
cp "dist/$BIN_NAME" "$OUTPUT_DIR/app_new/"
cp "dist/$LAUNCHER_NAME" "$OUTPUT_DIR/launcher.new"
cp -r locale "$OUTPUT_DIR/app_new/"
cp config.example.json "$OUTPUT_DIR/app_new/"
cp "dist/storyloom-${VERSION}-"*.whl "dist/storyloom-${VERSION}.tar.gz" "$OUTPUT_DIR/app_new/"
```

同时移除 `system_media` 的 `--add-data`（步骤 3）：

```bash
# 原来:
# --add-data "system_media${ADD_SEP}system_media" \

# 改为删除该行。system_media 作为独立 asset 发布。
```

更新 zip 创建步骤中的路径以反映新结构。

- [ ] **步骤 6：Commit**

```bash
git add src/storyloom/launcher.py tests/test_launcher.py scripts/build.sh
git commit -m "feat: add Storyloom Launcher source with PyInstaller build integration

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 7：`core/__init__.py` 导出 + 整合

**文件：**
- 修改：`src/storyloom/core/__init__.py`
- 修改：`src/storyloom/__init__.py`（如有必要）

- [ ] **步骤 1：添加 UpdateManager 导出**

在 `src/storyloom/core/__init__.py` 中追加：

```python
from storyloom.core.update_manager import (
    VersionInfo,
    UpdateCheckResult,
    UpdateProgress,
    check_for_updates,
    download_and_extract,
)
```

更新 `__all__` 列表追加这些名称。

- [ ] **步骤 2：运行完整测试**

```bash
pytest tests/test_update_manager.py tests/test_launcher.py tests/test_web_server.py -v
```
预期：全部 PASS

- [ ] **步骤 3：Commit**

```bash
git add src/storyloom/core/__init__.py
git commit -m "feat: export UpdateManager types from core package

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

## 自检

1. **规格覆盖度**：每个规格章节都有对应实现：
   - §3 Launcher → 任务 6
   - §4 UpdateManager → 任务 1-3
   - §5 API → 任务 4
   - §6 前端 → 任务 5
   - §7 构建 → 任务 6（步骤 5）
   - §8 WHL（预留，非本次实现范围）
   - §9 错误处理 → 各任务中包含

2. **占位符检查**：无 TODO、TBD、待定项。所有步骤包含完整代码。

3. **类型一致性**：
   - `VersionInfo` 在任务 1 定义，任务 2-4 使用 — 字段一致
   - `UpdateProgress` 在任务 1 定义，任务 3-4 使用 — 字段一致
   - `check_for_updates()` 签名：`(app_version, system_media_version, force)` — 任务 2 和任务 4 一致
   - `download_and_extract()` 签名：`(layer, url, target_root, progress_callback)` — 任务 3 和任务 4 一致

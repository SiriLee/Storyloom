"""Build hook — compile .po → .mo + download ONNX model during ``pip install``.

Users never need ``msgfmt`` or any manual step.  Everything happens
automatically inside the build phase.
"""

from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py
from setuptools.command.develop import develop as _develop
from setuptools.command.editable_wheel import editable_wheel as _editable_wheel


def _compile_mo_files() -> None:
    """Compile all .po files under the project ``locale/`` directory
    and generate the frontend JS translation dictionary."""
    project_root = Path(__file__).resolve().parent
    src = project_root / "src"

    # Load i18n_compile directly (avoids storyloom.__init__ → httpx import
    # chain, which fails in isolated build environments like editable_wheel).
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "storyloom.i18n_compile",
        str(src / "storyloom" / "i18n_compile.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    compile_all = mod.compile_all
    generate_js_dict = mod.generate_js_dict

    locale_dir = project_root / "locale"
    if locale_dir.is_dir():
        compiled = compile_all(str(locale_dir))
        if compiled:
            print(f"[i18n] compiled {len(compiled)} .mo file(s)")

    # Generate frontend T dictionary from .po files
    js_out = project_root / "src" / "storyloom" / "web" / "static" / "js" / "i18n-dict.js"
    generate_js_dict(str(locale_dir), str(js_out))
    print(f"[i18n] generated {js_out}")


def _download_model() -> None:
    """Download u2netp.onnx (~4.4 MB) into ``src/storyloom/models/``.

    Idempotent — skips if already cached with the correct SHA256.
    Network failures are warned, not fatal (the install continues).
    """
    import hashlib
    import importlib.util
    import urllib.request

    project_root = Path(__file__).resolve().parent

    # Load config.py standalone to read filename+SHA256 (avoids storyloom
    # __init__ import chain, same pattern as _compile_mo_files above).
    spec = importlib.util.spec_from_file_location(
        "storyloom.config",
        str(project_root / "src" / "storyloom" / "config.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sha256 = mod.BG_REMOVAL_MODEL_SHA256
    filename = mod.BG_REMOVAL_MODEL_FILENAME

    # URL is build-time only; kept here, not in production config.
    url = (
        "https://github.com/danielgatis/rembg/releases/download/"
        "v0.0.0/u2netp.onnx"
    )

    target = project_root / "src" / "storyloom" / "models" / filename

    # --- skip if already cached ---
    if target.exists():
        h = hashlib.sha256()
        with open(target, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        if h.hexdigest() == sha256:
            print(f"[model] {filename} cached (SHA256 ok)")
            return
        print(f"[model] {filename} exists but SHA256 mismatch — re-downloading")

    # --- download ---
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"[model] downloading {filename} (4.4 MB)...")
    try:
        urllib.request.urlretrieve(url, target)
    except Exception as e:
        print(f"[model] WARNING: download failed ({e})")
        print(f"[model] run `pip install -e .` again or place {filename} manually")
        return

    # --- verify ---
    h = hashlib.sha256()
    with open(target, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    if h.hexdigest() != sha256:
        target.unlink()
        print(f"[model] WARNING: SHA256 mismatch — corrupt download removed")
        print(f"[model] run `pip install -e .` again to retry")
        return

    print(f"[model] downloaded {target}")


class build_py(_build_py):
    """Custom build_py — compiles gettext catalogs + frontend JS dict
    + downloads the background-removal model."""

    def run(self) -> None:
        _compile_mo_files()
        _download_model()
        super().run()


class develop(_develop):
    """Custom develop — same hook for editable installs (legacy path)."""

    def run(self) -> None:
        _compile_mo_files()
        _download_model()
        super().run()


class editable_wheel(_editable_wheel):
    """Custom editable_wheel — PEP 660 editable installs (pip install -e)."""

    def run(self) -> None:
        _compile_mo_files()
        _download_model()
        super().run()


setup(cmdclass={
    "build_py": build_py,
    "develop": develop,
    "editable_wheel": editable_wheel,
})

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
    """Atomic swap: app_new → app, with rollback on failure.

    Verifies *app_new* is complete before swapping — an incomplete
    download must never replace a working installation.
    Spec: docs/superpowers/specs/2026-08-10-auto-update-design.md §9
    """
    if not os.path.isdir(APP_NEW):
        return

    # Guard: refuse to swap if the new version is missing the main exe.
    target = os.path.join(APP_NEW, MAIN_EXE)
    if not os.path.isfile(target):
        print(
            f"Warning: {APP_NEW} is incomplete — skipping update",
            file=sys.stderr,
        )
        shutil.rmtree(APP_NEW, ignore_errors=True)
        return

    shutil.rmtree(APP_OLD, ignore_errors=True)
    had_old = os.path.isdir(APP)
    if had_old:
        os.rename(APP, APP_OLD)
    try:
        os.rename(APP_NEW, APP)
    except OSError:
        # Swap failed — restore old version
        if had_old:
            os.rename(APP_OLD, APP)
        raise
    shutil.rmtree(APP_OLD, ignore_errors=True)

    # Ensure the main executable is runnable.  Zip extraction may strip
    # the execute bit, causing os.execv to fail with EACCES.
    new_exe = os.path.join(APP, MAIN_EXE)
    if os.path.isfile(new_exe) and sys.platform != "win32":
        os.chmod(new_exe, 0o755)


def _apply_launcher_update():
    """Self-replace the Launcher binary."""
    if not os.path.isfile(LAUNCHER_NEW):
        return

    if sys.platform == "win32":
        bat = os.path.join(DIR, "_launcher_swap.bat")
        launcher_dest = os.path.join(DIR, LAUNCHER_NAME)
        with open(bat, "w") as f:
            f.write(
                "@echo off\n"
                "timeout /t 1 /nobreak >nul\n"
                f'move /Y "{LAUNCHER_NEW}" "{launcher_dest}"\n'
                f'start "" "{launcher_dest}"\n'
            )
        subprocess.Popen(
            bat,
            shell=True,
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

    try:
        os.execv(target, [target] + sys.argv[1:])
    except OSError as exc:
        print(f"Error: failed to start {target}: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

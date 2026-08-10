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
        bat = os.path.join(DIR, "_launcher_swap.bat")
        with open(bat, "w") as f:
            f.write(
                "@echo off\n"
                "timeout /t 1 /nobreak >nul\n"
                f'move /Y "{LAUNCHER_NEW}" "{LAUNCHER_NAME}"\n'
                f'start "" "{os.path.join(DIR, LAUNCHER_NAME)}"\n'
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

    os.execv(target, [target] + sys.argv[1:])


if __name__ == "__main__":
    main()

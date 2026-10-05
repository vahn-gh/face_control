"""Launch at login via a macOS LaunchAgent."""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

LABEL = "com.face-control.agent"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def log_path() -> Path:
    return Path.home() / "Library" / "Logs" / "face_control.log"


def build_plist(python: str, config: Path | None, log: Path) -> bytes:
    args = [python, "-m", "face_control"]
    if config is not None:
        args += ["--config", str(config)]
    return plistlib.dumps(
        {
            "Label": LABEL,
            "ProgramArguments": args,
            "RunAtLoad": True,
            "KeepAlive": False,
            "ProcessType": "Interactive",
            "StandardOutPath": str(log),
            "StandardErrorPath": str(log),
        }
    )


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def install(config: Path | None = None) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("Launch at login is only supported on macOS")
    path = plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    log_path().parent.mkdir(parents=True, exist_ok=True)
    domain = f"gui/{os.getuid()}"
    _launchctl("bootout", domain, str(path))  # replace any previous version; ok if not loaded
    path.write_bytes(
        build_plist(sys.executable, config.resolve() if config else None, log_path())
    )
    result = _launchctl("bootstrap", domain, str(path))
    if result.returncode != 0:
        raise RuntimeError(f"launchctl bootstrap failed: {result.stderr.strip()}")
    return path


def uninstall() -> bool:
    """Returns False if it wasn't installed."""
    path = plist_path()
    if not path.exists():
        return False
    _launchctl("bootout", f"gui/{os.getuid()}", str(path))
    path.unlink()
    return True

import plistlib
from pathlib import Path

from face_control import launchagent


def test_plist_contents():
    data = plistlib.loads(
        launchagent.build_plist("/venv/bin/python", Path("/c/config.toml"), Path("/l/f.log"))
    )
    assert data["Label"] == launchagent.LABEL
    assert data["ProgramArguments"] == [
        "/venv/bin/python", "-m", "face_control", "--config", "/c/config.toml",
    ]
    assert data["RunAtLoad"] is True and data["KeepAlive"] is False
    assert data["StandardOutPath"] == "/l/f.log"


def test_plist_without_config():
    data = plistlib.loads(launchagent.build_plist("/py", None, Path("/l")))
    assert data["ProgramArguments"] == ["/py", "-m", "face_control"]

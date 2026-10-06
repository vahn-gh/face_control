"""Single TOML config file: defaults, validation, loading."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from face_control.debounce import DebounceConfig
from face_control.profile_store import config_dir
from face_control.rules import Limits, RulesConfig
from face_control.sound import SoundConfig


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CameraConfig:
    index: int = 0
    fps: float = 10.0


@dataclass(frozen=True)
class WindowConfig:
    width: int = 320
    show_on_start: bool = False


@dataclass(frozen=True)
class Config:
    camera: CameraConfig = CameraConfig()
    rules: RulesConfig = RulesConfig()
    debounce: DebounceConfig = DebounceConfig()
    sound: SoundConfig = SoundConfig()
    window: WindowConfig = WindowConfig()


DEFAULT_TOML = """\
# face_control configuration. Every key is optional; these are the defaults.

[camera]
index = 0            # which webcam
fps = 10.0           # capture / detection rate

[rules]
pitch_neutral = 0.0          # degrees; used when no calibrated profile matches
pitch_max_deviation = 15.0   # allowed +/- head tilt up/down from neutral
yaw_max = 25.0               # allowed +/- head turn sideways
away_is_violation = false    # treat "no person in frame" as a violation
margin = 1.0                 # profile tolerance multiplier (>1 = more lenient)

[debounce]
violation_delay = 3.0        # seconds of bad posture before it counts
recover_delay = 1.0          # seconds of good posture before it clears

[sound]
enabled = true
volume = 1.0                 # 0..1
# file = "/path/to/alert.wav"   # default: bundled sound
repeat_interval = 3.0        # seconds between repeats while still bad; 0 = off
cooldown = 3.0             # minimum seconds between any two sounds

[window]
width = 320                  # mini window width in pixels
show_on_start = false        # show the mini window when the app starts
"""


def config_path() -> Path:
    return config_dir() / "config.toml"


def _table(data: dict, name: str, allowed: set[str]) -> dict:
    section = data.get(name, {})
    if not isinstance(section, dict):
        raise ConfigError(f"[{name}] must be a table")
    unknown = sorted(set(section) - allowed)
    if unknown:
        raise ConfigError(f"Unknown key(s) in [{name}]: {', '.join(unknown)}")
    return section


def _value(section: dict, table: str, key: str, default, kind, lo=None, hi=None, lo_open=False):
    if key not in section:
        return default
    v = section[key]
    where = f"[{table}] {key}"
    if kind is bool:
        if not isinstance(v, bool):
            raise ConfigError(f"{where} must be true or false")
        return v
    if kind is str:
        if not isinstance(v, str):
            raise ConfigError(f"{where} must be a string")
        return v
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ConfigError(f"{where} must be a number")
    if kind is int and not isinstance(v, int):
        raise ConfigError(f"{where} must be a whole number")
    v = kind(v)
    if lo is not None and (v <= lo if lo_open else v < lo):
        raise ConfigError(f"{where} must be {'>' if lo_open else '>='} {lo}")
    if hi is not None and v > hi:
        raise ConfigError(f"{where} must be <= {hi}")
    return v


def parse(data: dict) -> Config:
    unknown = sorted(set(data) - {"camera", "rules", "debounce", "sound", "window"})
    if unknown:
        raise ConfigError(f"Unknown section(s): {', '.join(unknown)}")
    d = Config()

    s = _table(data, "camera", {"index", "fps"})
    camera = CameraConfig(
        _value(s, "camera", "index", d.camera.index, int, lo=0),
        _value(s, "camera", "fps", d.camera.fps, float, lo=0, lo_open=True),
    )

    s = _table(
        data,
        "rules",
        {"pitch_neutral", "pitch_max_deviation", "yaw_max", "away_is_violation", "margin"},
    )
    r = d.rules
    rules = RulesConfig(
        limits=Limits(
            pitch_neutral=_value(s, "rules", "pitch_neutral", r.limits.pitch_neutral, float),
            pitch_max_deviation=_value(
                s, "rules", "pitch_max_deviation", r.limits.pitch_max_deviation, float,
                lo=0, lo_open=True,
            ),
        ),
        yaw_max=_value(s, "rules", "yaw_max", r.yaw_max, float, lo=0, hi=180, lo_open=True),
        away_is_violation=_value(s, "rules", "away_is_violation", r.away_is_violation, bool),
        margin=_value(s, "rules", "margin", r.margin, float, lo=0, lo_open=True),
    )

    s = _table(data, "debounce", {"violation_delay", "recover_delay"})
    debounce = DebounceConfig(
        _value(s, "debounce", "violation_delay", d.debounce.violation_delay, float, lo=0),
        _value(s, "debounce", "recover_delay", d.debounce.recover_delay, float, lo=0),
    )

    s = _table(
        data, "sound", {"enabled", "volume", "file", "repeat_interval", "cooldown"}
    )
    file = _value(s, "sound", "file", None, str)
    sound = SoundConfig(
        enabled=_value(s, "sound", "enabled", d.sound.enabled, bool),
        volume=_value(s, "sound", "volume", d.sound.volume, float, lo=0, hi=1),
        file=Path(file).expanduser() if file else None,
        repeat_interval=_value(
            s, "sound", "repeat_interval", d.sound.repeat_interval, float, lo=0
        ),
        cooldown=_value(s, "sound", "cooldown", d.sound.cooldown, float, lo=0),
    )

    s = _table(data, "window", {"width", "show_on_start"})
    window = WindowConfig(
        _value(s, "window", "width", d.window.width, int, lo=160),
        _value(s, "window", "show_on_start", d.window.show_on_start, bool),
    )
    return Config(camera, rules, debounce, sound, window)


def to_data(c: Config) -> dict:
    """Inverse of `parse`: the config as the plain dict a TOML file would produce."""
    sound = {
        "enabled": c.sound.enabled,
        "volume": c.sound.volume,
        "repeat_interval": c.sound.repeat_interval,
        "cooldown": c.sound.cooldown,
    }
    if c.sound.file:
        sound["file"] = str(c.sound.file)
    return {
        "camera": {"index": c.camera.index, "fps": c.camera.fps},
        "rules": {
            "pitch_neutral": c.rules.limits.pitch_neutral,
            "pitch_max_deviation": c.rules.limits.pitch_max_deviation,
            "yaw_max": c.rules.yaw_max,
            "away_is_violation": c.rules.away_is_violation,
            "margin": c.rules.margin,
        },
        "debounce": {
            "violation_delay": c.debounce.violation_delay,
            "recover_delay": c.debounce.recover_delay,
        },
        "sound": sound,
        "window": {"width": c.window.width, "show_on_start": c.window.show_on_start},
    }


def load(path: Path | None = None) -> Config:
    """Load config. A missing default file means defaults; a missing explicit path is an error."""
    explicit = path is not None
    path = path or config_path()
    if not path.exists():
        if explicit:
            raise ConfigError(f"Config file not found: {path}")
        return Config()
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e
    try:
        return parse(data)
    except ConfigError as e:
        raise ConfigError(f"{path}: {e}") from e


def write_default(path: Path | None = None) -> Path:
    path = path or config_path()
    if path.exists():
        raise ConfigError(f"{path} already exists; not overwriting")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_TOML)
    return path

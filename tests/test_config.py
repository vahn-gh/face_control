import tomllib
from pathlib import Path

import pytest

from face_control import config as cfg
from face_control.config import Config, ConfigError, parse


def test_default_toml_matches_defaults():
    assert parse(tomllib.loads(cfg.DEFAULT_TOML)) == Config()


def test_empty_is_defaults():
    assert parse({}) == Config()


def test_to_data_roundtrip():
    c = parse({"sound": {"file": "/tmp/x.wav", "volume": 0.5}, "camera": {"index": 2}})
    assert parse(cfg.to_data(c)) == c


def test_values_override():
    c = parse(
        {
            "camera": {"index": 1, "fps": 5},
            "rules": {"yaw_max": 30, "away_is_violation": True, "pitch_max_deviation": 10},
            "debounce": {"violation_delay": 5},
            "sound": {"enabled": False, "volume": 0.3, "file": "~/a.wav"},
            "window": {"width": 400, "show_on_start": True},
        }
    )
    assert c.camera.index == 1 and c.camera.fps == 5.0
    assert c.rules.yaw_max == 30 and c.rules.away_is_violation
    assert c.rules.limits.pitch_max_deviation == 10
    assert c.debounce.violation_delay == 5 and c.debounce.recover_delay == 1.0
    assert not c.sound.enabled and c.sound.volume == 0.3
    assert c.sound.file == Path("~/a.wav").expanduser()
    assert c.window.width == 400 and c.window.show_on_start


@pytest.mark.parametrize(
    "data, fragment",
    [
        ({"bogus": {}}, "Unknown section"),
        ({"camera": {"idx": 1}}, "Unknown key"),
        ({"camera": {"fps": 0}}, "fps"),
        ({"camera": {"index": -1}}, "index"),
        ({"camera": {"index": 1.5}}, "whole number"),
        ({"camera": {"fps": "fast"}}, "number"),
        ({"camera": {"fps": True}}, "number"),
        ({"rules": {"margin": 0}}, "margin"),
        ({"rules": {"yaw_max": 200}}, "yaw_max"),
        ({"rules": {"away_is_violation": "yes"}}, "true or false"),
        ({"debounce": {"violation_delay": -1}}, "violation_delay"),
        ({"sound": {"volume": 1.5}}, "volume"),
        ({"sound": {"file": 3}}, "string"),
        ({"window": {"width": 50}}, "width"),
        ({"camera": 3}, "table"),
    ],
)
def test_validation_errors(data, fragment):
    with pytest.raises(ConfigError, match=fragment):
        parse(data)


def test_load_missing_default_is_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("FACE_CONTROL_CONFIG_DIR", str(tmp_path))
    assert cfg.load() == Config()


def test_load_missing_explicit_path_errors(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        cfg.load(tmp_path / "nope.toml")


def test_load_invalid_toml_and_bad_value_name_the_file(tmp_path):
    p = tmp_path / "c.toml"
    p.write_text("[camera\n")
    with pytest.raises(ConfigError, match="c.toml.*invalid TOML"):
        cfg.load(p)
    p.write_text("[camera]\nfps = -1\n")
    with pytest.raises(ConfigError, match="c.toml.*fps"):
        cfg.load(p)


def test_write_default_creates_then_refuses_to_overwrite(tmp_path):
    p = tmp_path / "sub" / "config.toml"
    cfg.write_default(p)
    assert cfg.load(p) == Config()
    with pytest.raises(ConfigError, match="already exists"):
        cfg.write_default(p)

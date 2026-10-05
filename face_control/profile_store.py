"""Profile persistence in the user config dir (JSON)."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from face_control.profiles import MetricStat, Profile


def config_dir() -> Path:
    override = os.environ.get("FACE_CONTROL_CONFIG_DIR")
    return Path(override) if override else Path.home() / ".config" / "face_control"


def profiles_path() -> Path:
    return config_dir() / "profiles.json"


def _profile_to_json(p: Profile) -> dict:
    out: dict = {k: {"mean": s.mean, "std": s.std} for k, s in p.stats.items()}
    if p.pitch_range is not None:
        out["pitch_range"] = list(p.pitch_range)
    return out


def _profile_from_json(name: str, raw: dict) -> Profile:
    raw = dict(raw)
    pr = raw.pop("pitch_range", None)
    pitch_range = None if pr is None else (float(pr[0]), float(pr[1]))
    if pitch_range is not None and pitch_range[0] > pitch_range[1]:
        raise ValueError(f"profile '{name}': pitch_range min is above max")
    stats = {k: MetricStat(v["mean"], v["std"]) for k, v in raw.items()}
    return Profile(name, stats, pitch_range)


@dataclass
class ProfileStore:
    profiles: dict[str, Profile] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"profiles": {name: _profile_to_json(p) for name, p in self.profiles.items()}}

    @classmethod
    def from_json(cls, data: dict) -> "ProfileStore":
        profiles = {
            name: _profile_from_json(name, raw) for name, raw in data.get("profiles", {}).items()
        }
        return cls(profiles)


def load(path: Path | None = None) -> ProfileStore:
    path = path or profiles_path()
    if not path.exists():
        return ProfileStore()
    try:
        return ProfileStore.from_json(json.loads(path.read_text()))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise RuntimeError(f"Could not read {path}: {e}. Fix or delete the file.") from e


def save(store: ProfileStore, path: Path | None = None) -> Path:
    path = path or profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(store.to_json(), indent=2) + "\n")
    tmp.replace(path)
    return path

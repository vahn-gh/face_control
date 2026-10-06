"""Posture profiles: build from calibration samples, match against live metrics. Pure logic."""

import argparse
import re
import statistics
from dataclasses import dataclass, field

from face_control.metrics import Metrics

PROFILE_NAMES = ("upright", "reclined", "standing")  # built-in; any other valid name works too



def profile_name(value: str) -> str:
    """argparse type: a profile name such as 'at_cafe' (lowercase letters, digits, _ or -)."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", value):
        raise argparse.ArgumentTypeError(f"invalid profile name '{value}': use lowercase letters, digits, _ or -")
    return value


# Recorded for every profile (pitch is recorded but only supplies the rule's neutral).
RECORDED_METRICS = ("head_y", "shoulder_width", "torso_lean", "head_pitch", "shoulder_tilt")
# Used to decide which profile the current posture matches.
MATCH_METRICS = ("head_y", "shoulder_width", "torso_lean")
# Minimum tolerance per metric, so a very steady calibration doesn't make matching brittle.
TOLERANCE_FLOOR = {
    "head_y": 0.06,
    "shoulder_width": 0.04,
    "torso_lean": 6.0,
}
SIGMA_MULTIPLIER = 3.0  # tolerance band = this many recorded standard deviations
MIN_SAMPLES = 10  # per metric, or the metric is not recorded
REQUIRED_METRICS = ("head_y", "shoulder_width")  # a profile without these can't match


@dataclass(frozen=True)
class MetricStat:
    mean: float
    std: float


@dataclass(frozen=True)
class Profile:
    name: str
    stats: dict[str, MetricStat] = field(default_factory=dict)
    # Optional absolute (min, max) head pitch in degrees that counts as OK for this profile.
    # When unset, the rule uses the calibrated mean +/- the configured deviation.
    pitch_range: tuple[float, float] | None = None

    @property
    def pitch_neutral(self) -> float | None:
        s = self.stats.get("head_pitch")
        return s.mean if s else None


@dataclass(frozen=True)
class MatchResult:
    name: str | None  # None = no profile matched
    distance: float | None  # 0 = exactly the recorded mean, <= 1 = inside tolerance


class CalibrationError(ValueError):
    pass


def build_profile(name: str, samples: list[Metrics]) -> Profile:
    stats: dict[str, MetricStat] = {}
    for metric in RECORDED_METRICS:
        values = [v for m in samples if (v := getattr(m, metric)) is not None]
        if len(values) >= MIN_SAMPLES:
            stats[metric] = MetricStat(statistics.fmean(values), statistics.pstdev(values))
    missing = [m for m in REQUIRED_METRICS if m not in stats]
    if missing:
        raise CalibrationError(
            f"Not enough data for {', '.join(missing)} "
            f"(need {MIN_SAMPLES}+ frames with your head and shoulders visible)."
        )
    return Profile(name, stats)


def _tolerance(metric: str, stat: MetricStat, margin: float) -> float:
    return max(SIGMA_MULTIPLIER * stat.std, TOLERANCE_FLOOR[metric]) * margin


def distance(m: Metrics, profile: Profile, margin: float = 1.0) -> float | None:
    """Worst normalized deviation over the metrics both sides have; None if none shared."""
    worst = None
    for metric in MATCH_METRICS:
        stat = profile.stats.get(metric)
        value = getattr(m, metric)
        if stat is None or value is None:
            continue
        d = abs(value - stat.mean) / _tolerance(metric, stat, margin)
        worst = d if worst is None else max(worst, d)
    return worst


def match_profile(m: Metrics, profiles: list[Profile], margin: float = 1.0) -> MatchResult:
    best = MatchResult(None, None)
    for p in profiles:
        d = distance(m, p, margin)
        if d is None:
            continue
        if best.distance is None or d < best.distance:
            best = MatchResult(p.name, d)
    if best.distance is not None and best.distance > 1.0:
        return MatchResult(None, best.distance)
    return best


def bounds(profile: Profile, metric: str, margin: float = 1.0) -> tuple[float, float] | None:
    stat = profile.stats.get(metric)
    if stat is None or metric not in TOLERANCE_FLOOR:
        return None
    tol = _tolerance(metric, stat, margin)
    return stat.mean - tol, stat.mean + tol


def outside_all(
    metric: str, value: float, profiles: list[Profile], margin: float = 1.0
) -> str | None:
    """"below" / "above" when `value` lies beyond every profile's band for `metric`.

    None when it's inside some band, in a gap between bands, or no profile has the metric.
    """
    ranges = [b for p in profiles if (b := bounds(p, metric, margin)) is not None]
    if not ranges:
        return None
    if all(value < lo for lo, _ in ranges):
        return "below"
    if all(value > hi for _, hi in ranges):
        return "above"
    return None

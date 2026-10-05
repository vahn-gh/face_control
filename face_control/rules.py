"""Posture rules: pure functions over metrics, no I/O."""

import dataclasses
from dataclasses import dataclass

from face_control.metrics import Metrics
from face_control.profiles import MatchResult, Profile, match_profile, outside_all


@dataclass(frozen=True)
class Limits:
    pitch_neutral: float = 0.0  # degrees; replaced by the calibrated value in slice 05
    pitch_max_deviation: float = 15.0  # allowed +/- degrees from neutral
    pitch_range: tuple[float, float] | None = None  # absolute (min, max); overrides the above


@dataclass(frozen=True)
class RuleResult:
    ok: bool
    reason: str = ""


def check_head_pitch(m: Metrics, limits: Limits = Limits()) -> RuleResult:
    """Flag the head tilted up or down too far. Missing data is not a violation."""
    if m.head_pitch is None:
        return RuleResult(True, "no head pitch data")
    if limits.pitch_range is not None:
        lo, hi = limits.pitch_range
        if m.head_pitch > hi:
            return RuleResult(False, f"head tilted up {m.head_pitch - hi:.0f}° above range")
        if m.head_pitch < lo:
            return RuleResult(False, f"head tilted down {lo - m.head_pitch:.0f}° below range")
        return RuleResult(True)
    deviation = m.head_pitch - limits.pitch_neutral
    if deviation > limits.pitch_max_deviation:
        return RuleResult(False, f"head tilted up {deviation:.0f}° from neutral")
    if deviation < -limits.pitch_max_deviation:
        return RuleResult(False, f"head tilted down {-deviation:.0f}° from neutral")
    return RuleResult(True)


@dataclass(frozen=True)
class RulesConfig:
    limits: Limits = Limits()
    yaw_max: float = 25.0  # allowed +/- degrees of head turn before "facing away"
    away_is_violation: bool = False  # no person in frame
    margin: float = 1.0  # profile tolerance multiplier


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reasons: tuple[str, ...] = ()
    match: MatchResult = MatchResult(None, None)
    away: bool = False


def check_head_yaw(m: Metrics, config: RulesConfig = RulesConfig()) -> RuleResult:
    if m.head_yaw is None:
        return RuleResult(True, "no head yaw data")
    if abs(m.head_yaw) > config.yaw_max:
        return RuleResult(False, f"facing sideways ({abs(m.head_yaw):.0f}° turned)")
    return RuleResult(True)


def check_position(
    m: Metrics, profiles: list[Profile], match: MatchResult, margin: float = 1.0
) -> RuleResult:
    """Posture must match a profile; if not, say whether it's too low/high/close/far."""
    if not profiles or match.name is not None:
        return RuleResult(True)
    reasons = []
    if m.head_y is not None:
        side = outside_all("head_y", m.head_y, profiles, margin)
        if side == "above":  # larger y = lower in the frame
            reasons.append("head too low")
        elif side == "below":
            reasons.append("head too high")
    if m.shoulder_width is not None:
        side = outside_all("shoulder_width", m.shoulder_width, profiles, margin)
        if side == "above":
            reasons.append("too close to the camera")
        elif side == "below":
            reasons.append("too far from the camera")
    return RuleResult(False, ", ".join(reasons) or "posture matches no calibrated profile")


def evaluate(
    m: Metrics,
    detected: bool,
    profiles: list[Profile],
    config: RulesConfig = RulesConfig(),
) -> Verdict:
    if not detected:
        if config.away_is_violation:
            return Verdict(False, ("no person detected",), away=True)
        return Verdict(True, away=True)

    match = match_profile(m, profiles, config.margin)
    limits = config.limits
    matched = next((p for p in profiles if p.name == match.name), None)
    if matched is not None:
        if matched.pitch_neutral is not None:
            limits = dataclasses.replace(limits, pitch_neutral=matched.pitch_neutral)
        if matched.pitch_range is not None:
            limits = dataclasses.replace(limits, pitch_range=matched.pitch_range)

    results = [
        check_head_pitch(m, limits),
        check_head_yaw(m, config),
        check_position(m, profiles, match, config.margin),
    ]
    reasons = tuple(r.reason for r in results if not r.ok)
    return Verdict(not reasons, reasons, match)

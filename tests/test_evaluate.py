from face_control.metrics import Metrics
from face_control.profiles import MetricStat, Profile
from face_control.rules import RulesConfig, check_head_yaw, evaluate


def stat(mean):
    return MetricStat(mean, 0.0)


def profile(name, head_y, width, lean=0.0, pitch=0.0):
    return Profile(
        name,
        {
            "head_y": stat(head_y),
            "shoulder_width": stat(width),
            "torso_lean": stat(lean),
            "head_pitch": stat(pitch),
        },
    )


UPRIGHT = profile("upright", 0.40, 0.30)
RECLINED = profile("reclined", 0.55, 0.30, lean=20, pitch=-10)
STANDING = profile("standing", 0.25, 0.20)
ALL = [UPRIGHT, RECLINED, STANDING]


def m(head_y=0.4, width=0.3, lean=0.0, pitch=0.0, yaw=0.0):
    return Metrics(
        head_y=head_y, shoulder_width=width, torso_lean=lean, head_pitch=pitch, head_yaw=yaw
    )


def run(metrics, **kw):
    return evaluate(metrics, kw.pop("detected", True), kw.pop("profiles", ALL), RulesConfig(**kw))


def test_calibrated_postures_are_ok():
    for metrics, name in [
        (m(), "upright"),
        (m(0.55, 0.3, 20, pitch=-10), "reclined"),
        (m(0.25, 0.2), "standing"),
    ]:
        v = run(metrics)
        assert v.ok and v.match.name == name and not v.reasons


def test_facing_sideways():
    v = run(m(yaw=40))
    assert not v.ok and any("sideways" in r for r in v.reasons)
    assert run(m(yaw=-40)).ok is False
    assert run(m(yaw=20)).ok


def test_yaw_limit_configurable():
    assert not check_head_yaw(Metrics(head_yaw=15), RulesConfig(yaw_max=10)).ok


def test_too_low():
    v = run(m(head_y=0.85))
    assert not v.ok and any("too low" in r for r in v.reasons)


def test_too_high_standing_on_chair():
    v = run(m(head_y=0.05))
    assert not v.ok and any("too high" in r for r in v.reasons)


def test_leaning_forward_is_too_close():
    v = run(m(width=0.5))
    assert not v.ok and any("too close" in r for r in v.reasons)


def test_too_far():
    v = run(m(width=0.1))
    assert not v.ok and any("too far" in r for r in v.reasons)


def test_between_profiles_gets_generic_reason():
    v = run(m(head_y=0.32, width=0.25))  # in the gap between standing and upright
    assert not v.ok and any("no calibrated profile" in r for r in v.reasons)


def test_pitch_uses_matched_profile_neutral():
    # reclined neutral is -10: pitch -20 is only 10 off, OK; upright at -20 is not.
    assert run(m(0.55, 0.3, 20, pitch=-20)).ok
    v = run(m(pitch=-20))
    assert not v.ok and any("down" in r for r in v.reasons)


def test_multiple_reasons_collected():
    v = run(m(head_y=0.85, yaw=50, pitch=30))
    assert len(v.reasons) == 3


def test_away_is_not_a_violation_by_default():
    v = evaluate(Metrics(), False, ALL, RulesConfig())
    assert v.ok and v.away


def test_away_can_be_a_violation():
    v = evaluate(Metrics(), False, ALL, RulesConfig(away_is_violation=True))
    assert not v.ok and v.away


def test_no_profiles_only_pitch_and_yaw_apply():
    assert run(m(), profiles=[]).ok
    assert not run(m(yaw=60), profiles=[]).ok


def test_matched_profile_pitch_range_applies():
    import dataclasses

    tight = dataclasses.replace(RECLINED, pitch_range=(-8.0, 5.0))
    profiles = [UPRIGHT, tight, STANDING]
    ok = evaluate(m(0.55, 0.3, 20, pitch=-6), True, profiles, RulesConfig())
    bad = evaluate(m(0.55, 0.3, 20, pitch=-10), True, profiles, RulesConfig())
    assert ok.ok
    assert not bad.ok and any("down" in r for r in bad.reasons)

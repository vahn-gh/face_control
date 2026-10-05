import pytest

from face_control.metrics import Metrics
from face_control.rules import Limits, check_head_pitch
from face_control.smoothing import MetricsSmoother


def pitch(v):
    return Metrics(head_pitch=v)


def test_within_limits_ok():
    assert check_head_pitch(pitch(0)).ok
    assert check_head_pitch(pitch(14.9)).ok
    assert check_head_pitch(pitch(-14.9)).ok


def test_limit_is_inclusive():
    assert check_head_pitch(pitch(15)).ok
    assert check_head_pitch(pitch(-15)).ok


def test_up_and_down_flagged():
    up = check_head_pitch(pitch(25))
    down = check_head_pitch(pitch(-25))
    assert not up.ok and "up" in up.reason
    assert not down.ok and "down" in down.reason


def test_neutral_offset_shifts_window():
    limits = Limits(pitch_neutral=10, pitch_max_deviation=15)
    assert check_head_pitch(pitch(24), limits).ok
    assert not check_head_pitch(pitch(26), limits).ok
    assert check_head_pitch(pitch(-4), limits).ok
    assert not check_head_pitch(pitch(-6), limits).ok


def test_custom_limit():
    assert not check_head_pitch(pitch(11), Limits(pitch_max_deviation=10)).ok


def test_missing_pitch_is_not_a_violation():
    assert check_head_pitch(Metrics()).ok


def test_smoother_first_value_passes_through():
    assert MetricsSmoother(0.5).update(pitch(10)).head_pitch == 10


def test_smoother_blends_and_damps_spikes():
    s = MetricsSmoother(0.5)
    s.update(pitch(0))
    assert s.update(pitch(30)).head_pitch == pytest.approx(15)
    assert s.update(pitch(30)).head_pitch == pytest.approx(22.5)


def test_smoother_resets_when_field_missing():
    s = MetricsSmoother(0.5)
    s.update(pitch(0))
    assert s.update(Metrics()).head_pitch is None
    assert s.update(pitch(40)).head_pitch == 40


def test_smoother_rejects_bad_alpha():
    with pytest.raises(ValueError):
        MetricsSmoother(0)


def test_pitch_range_overrides_neutral_window():
    limits = Limits(pitch_neutral=0, pitch_max_deviation=15, pitch_range=(-10, 5))
    assert check_head_pitch(pitch(-10), limits).ok
    assert check_head_pitch(pitch(5), limits).ok
    down = check_head_pitch(pitch(-12), limits)
    assert not down.ok and "down" in down.reason
    assert not check_head_pitch(pitch(6), limits).ok

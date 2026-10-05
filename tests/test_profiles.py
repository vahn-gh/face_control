import json

import pytest

from face_control import profile_store
from face_control.metrics import Metrics
from face_control.profiles import (
    CalibrationError,
    MetricStat,
    Profile,
    build_profile,
    match_profile,
)


def m(head_y=0.4, width=0.3, lean=0.0, pitch=0.0):
    return Metrics(head_y=head_y, shoulder_width=width, torso_lean=lean, head_pitch=pitch)


def stat(mean, std=0.0):
    return MetricStat(mean, std)


UPRIGHT = Profile("upright", {"head_y": stat(0.4), "shoulder_width": stat(0.3), "torso_lean": stat(0)})
RECLINED = Profile("reclined", {"head_y": stat(0.55), "shoulder_width": stat(0.3), "torso_lean": stat(20)})
STANDING = Profile("standing", {"head_y": stat(0.25), "shoulder_width": stat(0.2), "torso_lean": stat(0)})
ALL = [UPRIGHT, RECLINED, STANDING]


def test_build_profile_mean_and_std():
    samples = [m(head_y=0.4 + (i % 2) * 0.02) for i in range(20)]
    p = build_profile("upright", samples)
    assert p.stats["head_y"].mean == pytest.approx(0.41)
    assert p.stats["head_y"].std == pytest.approx(0.01)
    assert p.pitch_neutral == 0.0


def test_build_profile_skips_sparse_metric_but_keeps_required():
    samples = [m() for _ in range(20)]
    samples = [Metrics(head_y=s.head_y, shoulder_width=s.shoulder_width) for s in samples]
    p = build_profile("upright", samples)
    assert "torso_lean" not in p.stats and p.pitch_neutral is None


def test_build_profile_requires_head_and_shoulders():
    with pytest.raises(CalibrationError):
        build_profile("upright", [Metrics(head_y=0.4)] * 20)
    with pytest.raises(CalibrationError):
        build_profile("upright", [])


def test_each_posture_matches_itself():
    assert match_profile(m(), ALL).name == "upright"
    assert match_profile(m(0.55, 0.3, 20), ALL).name == "reclined"
    assert match_profile(m(0.25, 0.2, 0), ALL).name == "standing"


def test_odd_posture_matches_none():
    r = match_profile(m(head_y=0.9, width=0.5, lean=40), ALL)
    assert r.name is None and r.distance > 1


def test_no_profiles_or_no_data_is_none():
    assert match_profile(m(), []).name is None
    assert match_profile(Metrics(), ALL).name is None


def test_missing_metric_is_skipped_not_failed():
    assert match_profile(Metrics(head_y=0.4, shoulder_width=0.3), ALL).name == "upright"


def test_margin_widens_tolerance():
    slightly_off = m(head_y=0.4 + 0.09)  # floor tolerance is 0.06
    assert match_profile(slightly_off, [UPRIGHT]).name is None
    assert match_profile(slightly_off, [UPRIGHT], margin=2.0).name == "upright"


def test_wider_recorded_spread_widens_band():
    loose = Profile("upright", {"head_y": stat(0.4, 0.05), "shoulder_width": stat(0.3)})
    assert match_profile(m(head_y=0.52), [loose]).name == "upright"  # 3*0.05 = 0.15


def test_store_roundtrip_and_missing_file(tmp_path):
    path = tmp_path / "sub" / "profiles.json"
    assert profile_store.load(path).profiles == {}
    store = profile_store.ProfileStore(profiles={"upright": UPRIGHT})
    profile_store.save(store, path)
    loaded = profile_store.load(path)
    assert loaded.profiles["upright"] == UPRIGHT


def test_store_corrupt_file_gives_readable_error(tmp_path):
    path = tmp_path / "profiles.json"
    path.write_text("{not json")
    with pytest.raises(RuntimeError, match="profiles.json"):
        profile_store.load(path)
    path.write_text(json.dumps({"profiles": {"x": {"head_y": {"mean": 1}}}}))
    with pytest.raises(RuntimeError):
        profile_store.load(path)


def test_pitch_range_round_trips_and_is_optional(tmp_path):
    import dataclasses

    path = tmp_path / "profiles.json"
    ranged = dataclasses.replace(RECLINED, pitch_range=(-8.0, 5.0))
    profile_store.save(profile_store.ProfileStore({"reclined": ranged, "upright": UPRIGHT}), path)
    loaded = profile_store.load(path).profiles
    assert loaded["reclined"].pitch_range == (-8.0, 5.0)
    assert loaded["upright"].pitch_range is None
    assert loaded["reclined"].stats == RECLINED.stats

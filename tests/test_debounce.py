from face_control.debounce import DebounceConfig, Event, State, ViolationTracker


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def make(violation=3.0, recover=1.0):
    clock = Clock()
    return ViolationTracker(DebounceConfig(violation, recover), clock), clock


def feed(tracker, clock, ok, seconds, step=0.1):
    """Feed `ok` verdicts for `seconds`; returns the events emitted."""
    events = []
    for _ in range(round(seconds / step)):
        clock.t += step
        e = tracker.update(ok)
        if e:
            events.append(e)
    return events


def test_starts_ok():
    t, _ = make()
    assert t.state is State.OK


def test_brief_blip_is_ignored():
    t, c = make()
    assert feed(t, c, False, 2.0) == []
    assert t.state is State.OK


def test_sustained_violation_starts_once():
    t, c = make()
    events = feed(t, c, False, 5.0)
    assert events == [Event.VIOLATION_STARTED]
    assert t.state is State.VIOLATING


def test_starts_after_delay_not_before():
    t, c = make()
    c.t = 10.0
    t.update(False)  # streak starts at t=10
    c.t = 12.9
    assert t.update(False) is None
    c.t = 13.0
    assert t.update(False) is Event.VIOLATION_STARTED


def test_recovery_needs_sustained_good():
    t, c = make()
    feed(t, c, False, 4.0)
    assert feed(t, c, True, 0.5) == []
    assert t.state is State.VIOLATING
    assert feed(t, c, True, 1.0) == [Event.VIOLATION_ENDED]
    assert t.state is State.OK


def test_flapping_never_triggers():
    t, c = make()
    events = []
    for _ in range(20):
        events += feed(t, c, False, 2.0)
        events += feed(t, c, True, 0.5)
    assert events == [] and t.state is State.OK


def test_flapping_while_violating_stays_violating():
    t, c = make()
    feed(t, c, False, 4.0)
    events = []
    for _ in range(20):
        events += feed(t, c, True, 0.5)  # shorter than recover_delay
        events += feed(t, c, False, 0.5)
    assert events == [] and t.state is State.VIOLATING


def test_long_violation_then_full_cycle():
    t, c = make()
    events = feed(t, c, False, 30.0) + feed(t, c, True, 5.0) + feed(t, c, False, 4.0)
    assert events == [Event.VIOLATION_STARTED, Event.VIOLATION_ENDED, Event.VIOLATION_STARTED]


def test_custom_delays():
    t, c = make(violation=0.5, recover=0.2)
    assert feed(t, c, False, 0.8) == [Event.VIOLATION_STARTED]
    assert feed(t, c, True, 0.4) == [Event.VIOLATION_ENDED]

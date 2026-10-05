from face_control.debounce import Event, State
from face_control.sound import AlertPolicy, SoundConfig

STARTED, ENDED = Event.VIOLATION_STARTED, Event.VIOLATION_ENDED


class FakePlayer:
    def __init__(self):
        self.plays = 0

    def play(self):
        self.plays += 1


class Clock:
    t = 0.0

    def __call__(self):
        return self.t


def make(**kw):
    clock, player = Clock(), FakePlayer()
    return AlertPolicy(SoundConfig(**kw), player, clock), player, clock


def test_plays_on_violation_start():
    p, player, _ = make()
    p.update(STARTED, State.VIOLATING)
    assert player.plays == 1


def test_silent_when_ok_and_on_recovery():
    p, player, c = make()
    for _ in range(100):
        c.t += 1
        p.update(None, State.OK)
    p.update(ENDED, State.OK)
    assert player.plays == 0


def test_no_repeat_before_interval_then_repeats():
    p, player, c = make(repeat_interval=30)
    p.update(STARTED, State.VIOLATING)
    c.t = 29
    p.update(None, State.VIOLATING)
    assert player.plays == 1
    c.t = 30
    p.update(None, State.VIOLATING)
    assert player.plays == 2
    c.t = 59
    p.update(None, State.VIOLATING)
    assert player.plays == 2
    c.t = 60
    p.update(None, State.VIOLATING)
    assert player.plays == 3


def test_repeat_disabled():
    p, player, c = make(repeat_interval=0)
    p.update(STARTED, State.VIOLATING)
    c.t = 1000
    p.update(None, State.VIOLATING)
    assert player.plays == 1


def test_repeat_stops_after_recovery():
    p, player, c = make(repeat_interval=30)
    p.update(STARTED, State.VIOLATING)
    p.update(ENDED, State.OK)
    c.t = 100
    p.update(None, State.OK)
    assert player.plays == 1


def test_cooldown_blocks_flapping_starts():
    p, player, c = make(cooldown=10)
    p.update(STARTED, State.VIOLATING)
    c.t = 5
    p.update(ENDED, State.OK)
    p.update(STARTED, State.VIOLATING)  # too soon
    assert player.plays == 1
    c.t = 11
    p.update(ENDED, State.OK)
    p.update(STARTED, State.VIOLATING)
    assert player.plays == 2


def test_cooldown_wins_over_short_repeat_interval():
    p, player, c = make(repeat_interval=2, cooldown=10)
    p.update(STARTED, State.VIOLATING)
    c.t = 5
    p.update(None, State.VIOLATING)
    assert player.plays == 1
    c.t = 10
    p.update(None, State.VIOLATING)
    assert player.plays == 2


def test_disabled_never_plays():
    p, player, c = make(enabled=False)
    p.update(STARTED, State.VIOLATING)
    c.t = 1000
    p.update(None, State.VIOLATING)
    assert player.plays == 0

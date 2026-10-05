"""Violation state machine: only sustained bad posture counts. Pure logic, injectable clock."""

import enum
import time
from collections.abc import Callable
from dataclasses import dataclass


class State(enum.Enum):
    OK = "ok"
    VIOLATING = "violating"


class Event(enum.Enum):
    VIOLATION_STARTED = "violation_started"
    VIOLATION_ENDED = "violation_ended"


@dataclass(frozen=True)
class DebounceConfig:
    violation_delay: float = 3.0  # seconds of continuous bad before OK -> VIOLATING
    recover_delay: float = 1.0  # seconds of continuous good before VIOLATING -> OK


class ViolationTracker:
    def __init__(
        self,
        config: DebounceConfig = DebounceConfig(),
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._clock = clock
        self.state = State.OK
        self._opposite_since: float | None = None  # start of the streak that would flip state

    def update(self, verdict_ok: bool) -> Event | None:
        """Feed one verdict; returns the event if the state just changed."""
        now = self._clock()
        # A verdict that agrees with the current state cancels any pending flip.
        wants_flip = verdict_ok == (self.state is State.VIOLATING)
        if not wants_flip:
            self._opposite_since = None
            return None
        if self._opposite_since is None:
            self._opposite_since = now
        delay = (
            self.config.recover_delay
            if self.state is State.VIOLATING
            else self.config.violation_delay
        )
        if now - self._opposite_since < delay:
            return None
        self._opposite_since = None
        if self.state is State.OK:
            self.state = State.VIOLATING
            return Event.VIOLATION_STARTED
        self.state = State.OK
        return Event.VIOLATION_ENDED

"""Sound alerts: when to play (pure policy) and how to play (macOS afplay)."""

import logging
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from face_control.debounce import Event, State

log = logging.getLogger(__name__)

BUNDLED_SOUND = Path(__file__).resolve().parent / "sounds" / "alert.wav"


@dataclass(frozen=True)
class SoundConfig:
    enabled: bool = True
    volume: float = 1.0  # 0..1
    file: Path | None = None  # None = bundled sound
    repeat_interval: float = 30.0  # seconds while still violating; 0 = no repeat
    cooldown: float = 10.0  # minimum seconds between any two sounds

    @property
    def path(self) -> Path:
        return self.file or BUNDLED_SOUND


class Player(Protocol):
    def play(self) -> None: ...


class AfplayPlayer:
    """Non-blocking playback through macOS's built-in `afplay` (no extra dependency)."""

    def __init__(self, path: Path, volume: float) -> None:
        self._cmd = ["afplay", "-v", str(volume), str(path)]
        self._proc: subprocess.Popen | None = None
        self.available = shutil.which("afplay") is not None
        if not self.available:
            log.warning("afplay not found; sound alerts are disabled (macOS only for now)")

    def play(self) -> None:
        if not self.available:
            return
        if self._proc is not None and self._proc.poll() is None:
            return  # previous alert still playing; don't overlap
        self._proc = subprocess.Popen(
            self._cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )


class AlertPolicy:
    """Decides when to sound: on violation start, then every repeat_interval, never in a flap."""

    def __init__(
        self,
        config: SoundConfig,
        player: Player,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._player = player
        self._clock = clock
        self._last_played: float | None = None

    def _due(self, now: float, min_gap: float) -> bool:
        return self._last_played is None or now - self._last_played >= min_gap

    def _play(self, now: float) -> None:
        self._last_played = now
        self._player.play()

    def update(self, event: Event | None, state: State) -> None:
        """Call once per frame with the tracker's event (if any) and current state."""
        if not self.config.enabled:
            return
        now = self._clock()
        if event is Event.VIOLATION_STARTED:
            if self._due(now, self.config.cooldown):
                self._play(now)
        elif state is State.VIOLATING and self.config.repeat_interval > 0:
            gap = max(self.config.repeat_interval, self.config.cooldown)
            if self._due(now, gap):
                self._play(now)
        # Recovery (VIOLATION_ENDED) is silent.


def make_alerts(config: SoundConfig) -> AlertPolicy | None:
    if not config.enabled:
        return None
    if not config.path.is_file():
        raise RuntimeError(f"Sound file not found: {config.path}")
    return AlertPolicy(config, AfplayPlayer(config.path, config.volume))

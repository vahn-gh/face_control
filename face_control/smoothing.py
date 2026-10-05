"""Exponential smoothing of raw metrics to reduce landmark jitter."""

import dataclasses

from face_control.metrics import Metrics


class MetricsSmoother:
    """EMA per field. A field that goes missing resets, so stale values never linger."""

    def __init__(self, alpha: float = 0.4) -> None:
        if not 0 < alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        self.alpha = alpha
        self._state: dict[str, float] = {}

    def update(self, m: Metrics) -> Metrics:
        out = {}
        for f in dataclasses.fields(m):
            v = getattr(m, f.name)
            if v is None:
                self._state.pop(f.name, None)
            else:
                prev = self._state.get(f.name)
                v = v if prev is None else self.alpha * v + (1 - self.alpha) * prev
                self._state[f.name] = v
            out[f.name] = v
        return Metrics(**out)

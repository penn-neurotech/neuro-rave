"""Freeze session-specific theta/beta bounds from the first N windows of a stream."""

from __future__ import annotations

import src.constants as const


class ThetaBetaSessionCalibrator:
    """Collect theta/beta means during warm-up, then fix LOW/HIGH percentiles.

    Until frozen, :meth:`bounds` returns ``None`` and callers should use global
    constants from ``config/constants.json``. After warm-up, use
    :meth:`bounds` with :func:`src.processing.focus_map.focus_from_theta_beta_mean`.
    """

    def __init__(
        self,
        *,
        warmup_windows: int | None = None,
        low_pct: float | None = None,
        high_pct: float | None = None,
        min_spread: float | None = None,
    ) -> None:
        self._warmup_n = int(warmup_windows or const.SESSION_THETA_BETA_WARMUP_WINDOWS)
        self._low_pct = float(low_pct if low_pct is not None else const.SESSION_THETA_BETA_LOW_PERCENTILE)
        self._high_pct = float(high_pct if high_pct is not None else const.SESSION_THETA_BETA_HIGH_PERCENTILE)
        self._min_spread = float(min_spread if min_spread is not None else const.SESSION_THETA_BETA_MIN_SPREAD)
        self._buf: list[float] = []
        self._low: float | None = None
        self._high: float | None = None

    def observe(self, theta_beta_mean: float) -> None:
        if self._low is not None:
            return
        self._buf.append(float(theta_beta_mean))
        if len(self._buf) >= self._warmup_n:
            self._freeze()

    def _freeze(self) -> None:
        import numpy as np

        a = np.asarray(self._buf, dtype=np.float64)
        lo = float(np.percentile(a, self._low_pct))
        hi = float(np.percentile(a, self._high_pct))
        if hi <= lo:
            mid = 0.5 * (lo + hi)
            half = max(self._min_spread / 2, 1e-6)
            lo, hi = mid - half, mid + half
        elif hi - lo < self._min_spread:
            mid = 0.5 * (lo + hi)
            half = self._min_spread / 2
            lo, hi = mid - half, mid + half
        self._low = lo
        self._high = hi

    @property
    def is_ready(self) -> bool:
        return self._low is not None and self._high is not None

    def bounds(self) -> tuple[float, float] | None:
        if not self.is_ready or self._low is None or self._high is None:
            return None
        return (self._low, self._high)

    def reset(self) -> None:
        self._buf.clear()
        self._low = None
        self._high = None

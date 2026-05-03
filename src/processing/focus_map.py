"""Map mean theta/beta ratio to a [0, 1] focus score for real-time EEG.

Higher focus ⇒ relatively more beta than theta (engaged / less “idle” theta).
Bounds come from ``config/constants.json`` (``FOCUS_THETA_BETA_*``).
"""

from __future__ import annotations

import src.constants as const


def focus_from_theta_beta_mean(
    tb_mean: float,
    *,
    low: float | None = None,
    high: float | None = None,
) -> float:
    lo = float(low if low is not None else const.FOCUS_THETA_BETA_LOW)
    hi = float(high if high is not None else const.FOCUS_THETA_BETA_HIGH)
    if hi <= lo:
        hi = lo + 1e-3
    x = (hi - float(tb_mean)) / (hi - lo)
    return max(0.0, min(1.0, x))

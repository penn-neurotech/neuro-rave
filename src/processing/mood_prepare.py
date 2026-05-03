"""Optional MoodStabilizer EMA before ``propose_mood`` (single config switch)."""

from __future__ import annotations

import src.constants as const
from src.music_gen.spotify_controller import MoodStabilizer


def stabilizer_outputs_for_mood(
    stabilizer: MoodStabilizer,
    raw_energy: float,
    raw_focus: float,
) -> tuple[float, float, float]:
    """Return ``(energy, focus, d_energy)`` for :func:`propose_mood`.

    When ``NEURO_APPLY_STABILIZER_SMOOTH`` is false, skip EMA and use
    :meth:`MoodStabilizer.direct_for_mood` (step ``d_energy`` on raw energy).
    """
    if const.NEURO_APPLY_STABILIZER_SMOOTH:
        return stabilizer.smooth(raw_energy, raw_focus)
    return stabilizer.direct_for_mood(raw_energy, raw_focus)

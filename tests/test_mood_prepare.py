from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import src.constants as const
from src.music_gen.spotify_controller import MoodStabilizer
from src.processing.mood_prepare import stabilizer_outputs_for_mood


def test_direct_for_mood_step_delta() -> None:
    m = MoodStabilizer()
    e0, f0, d0 = m.direct_for_mood(0.5, 0.3)
    assert d0 == 0.0 and e0 == 0.5 and f0 == 0.3
    e1, f1, d1 = m.direct_for_mood(0.7, 0.3)
    assert abs(d1 - 0.2) < 1e-9 and e1 == 0.7


def test_stabilizer_outputs_respects_flag(monkeypatch) -> None:
    m = MoodStabilizer()
    monkeypatch.setattr(const, "NEURO_APPLY_STABILIZER_SMOOTH", True)
    stabilizer_outputs_for_mood(m, 0.0, 0.0)
    a1, b1, _c1 = stabilizer_outputs_for_mood(m, 0.8, 0.2)
    monkeypatch.setattr(const, "NEURO_APPLY_STABILIZER_SMOOTH", False)
    m2 = MoodStabilizer()
    a2, b2, c2 = stabilizer_outputs_for_mood(m2, 0.8, 0.2)
    assert a2 == 0.8 and b2 == 0.2 and c2 == 0.0
    assert a1 < 0.8

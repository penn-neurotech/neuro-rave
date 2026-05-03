"""Calibration utilities: session TB, metrics, search (no BDF required)."""

from __future__ import annotations

from src.calibration.metrics import label_free_report, macro_f1_mood, mood_switch_rate_per_minute
from src.calibration.session_theta_beta import ThetaBetaSessionCalibrator
from src.processing.focus_map import focus_from_theta_beta_mean


def test_theta_beta_session_calibrator_spreads_focus() -> None:
    cal = ThetaBetaSessionCalibrator(warmup_windows=5, low_pct=0, high_pct=100, min_spread=0.01)
    samples = [2.0, 2.2, 2.4, 2.6, 2.8]
    for s in samples:
        cal.observe(s)
    b = cal.bounds()
    assert b is not None
    lo, hi = b
    f_mid = focus_from_theta_beta_mean(2.4, low=lo, high=hi)
    assert 0.05 < f_mid < 0.95


def test_label_free_report_basic() -> None:
    rows = [
        {"theta_beta_mean": "2.0", "majority_mood": "calm", "focus_theta_beta_global": "0.0"},
        {"theta_beta_mean": "2.1", "majority_mood": "calm", "focus_theta_beta_global": "0.0"},
        {"theta_beta_mean": "2.2", "majority_mood": "focus", "focus_theta_beta_global": "0.1"},
    ]
    r = label_free_report(rows)
    assert r["n_windows"] == 3
    assert "mood_majority" in r


def test_macro_f1() -> None:
    f = macro_f1_mood(["a", "a", "b"], ["a", "b", "b"])
    assert 0.0 <= f <= 1.0


def test_mood_switch_rate() -> None:
    r = mood_switch_rate_per_minute(["a", "a", "b", "b", "a"], window_s=1.0)
    assert r >= 0

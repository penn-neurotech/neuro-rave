"""Tests for shared dashboard EEG window processing."""

from __future__ import annotations

import numpy as np

import src.constants as const
from src.processing.dashboard_features import DashboardFeatureState, FeatureThresholds


def test_window_shape_enforced() -> None:
    dash = DashboardFeatureState()
    bad = np.zeros((100, const.N_CHANNELS), dtype=np.float32)
    try:
        dash.process_window(bad)
    except ValueError:
        return
    raise AssertionError("expected ValueError for wrong window length")


def test_stable_theta_beta_mean_synthetic() -> None:
    """Band-limited synthetic: many windows should yield finite theta/beta mean."""
    rng = np.random.default_rng(0)
    n = int(const.WINDOW_SIZE)
    t = np.arange(n, dtype=np.float64) / float(const.SAMPLE_RATE)
    # strong ~10 Hz + ~20 Hz across channels
    sig = 40 * np.sin(2 * np.pi * 10.0 * t) + 25 * np.sin(2 * np.pi * 20.0 * t)
    noise = 0.5 * rng.standard_normal((n, const.N_CHANNELS))
    data = (sig[:, None] + noise).astype(np.float32)
    dash = DashboardFeatureState()
    means: list[float] = []
    for _ in range(80):
        means.append(dash.process_window(data).theta_beta_mean)
    assert all(np.isfinite(m) for m in means)
    assert max(means) - min(means) < 5.0


def test_injectable_thresholds_dataclass() -> None:
    th = FeatureThresholds(attention_alpha_sup_threshold=0.11, attention_variability_max=0.33)
    assert th.attention_alpha_sup_threshold == 0.11
    assert th.attention_variability_max == 0.33

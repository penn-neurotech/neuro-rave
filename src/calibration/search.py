"""Small grid over attention thresholds using replayed BDF windows."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Iterable, Sequence

import numpy as np

from src.calibration.metrics import label_free_report
from src.calibration.replay import iter_windows
from src.music_gen.spotify_controller import MoodStabilizer, NeuroFeatures, propose_mood
from src.processing.mood_prepare import stabilizer_outputs_for_mood
from src.processing.dashboard_features import DashboardFeatureState, FeatureThresholds
from src.processing.focus_map import focus_from_theta_beta_mean


def _run_rows(
    data: np.ndarray,
    thresholds: FeatureThresholds,
) -> list[dict[str, Any]]:
    dash = DashboardFeatureState(thresholds)
    stabilizer = MoodStabilizer()
    rows: list[dict[str, Any]] = []
    for _ix, seg in iter_windows(data):
        wf = dash.process_window(seg)
        raw_e = float(wf.energy_index) if wf.energy_index is not None else 0.5
        raw_f = float(wf.sustained_attention_index)
        se, sf, d_e = stabilizer_outputs_for_mood(stabilizer, raw_e, raw_f)
        proposed = propose_mood(NeuroFeatures(energy=se, focus=sf, d_energy=d_e))
        majority = stabilizer.majority_mood(proposed)
        rows.append(
            {
                "theta_beta_mean": wf.theta_beta_mean,
                "majority_mood": majority,
                "focus_theta_beta_global": focus_from_theta_beta_mean(wf.theta_beta_mean),
            }
        )
    return rows


def grid_search_attention(
    data: np.ndarray,
    *,
    alpha_thresholds: Iterable[float] | None = None,
    variability_maxs: Iterable[float] | None = None,
) -> list[dict[str, Any]]:
    """Return scored candidates sorted by composite label-free score (higher better)."""
    if alpha_thresholds is None:
        alpha_thresholds = [0.35, 0.45, 0.5, 0.55, 0.65]
    if variability_maxs is None:
        variability_maxs = [0.15, 0.2, 0.25, 0.3, 0.35]

    base = FeatureThresholds()
    results: list[dict[str, Any]] = []
    for ath in alpha_thresholds:
        for vm in variability_maxs:
            th = replace(
                base,
                attention_alpha_sup_threshold=float(ath),
                attention_variability_max=float(vm),
            )
            rows = _run_rows(data, th)
            rep = label_free_report(rows)
            # Prefer less mood collapse + more theta/beta spread + moderate switching
            spread = float(rep.get("theta_beta_mean", {}).get("stdev") or 0.0)
            dom = float(rep.get("mood_dominant_fraction") or 1.0)
            sat = float(rep.get("focus_theta_beta_global", {}).get("saturation_0_1") or 0.0)
            sw = float(rep.get("mood_switches_per_minute") or 0.0)
            score = spread * (1.0 - dom) * (1.0 - sat) - 0.02 * sw
            results.append(
                {
                    "ATTENTION_ALPHA_SUP_THRESHOLD": ath,
                    "ATTENTION_VARIABILITY_MAX": vm,
                    "score": score,
                    "report": rep,
                }
            )
    results.sort(key=lambda r: r["score"], reverse=True)
    return results


def suggest_theta_beta_bounds(theta_beta_means: Sequence[float]) -> dict[str, float]:
    """Session-style percentiles for global JSON tuning hints."""
    a = np.asarray(list(theta_beta_means), dtype=np.float64)
    if a.size == 0:
        return {}
    return {
        "FOCUS_THETA_BETA_LOW_suggested": float(np.percentile(a, 10)),
        "FOCUS_THETA_BETA_HIGH_suggested": float(np.percentile(a, 90)),
    }

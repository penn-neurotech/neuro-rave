"""Build per-window trace rows (dashboard features + mood + theta/beta focus)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterator

import numpy as np

from src.calibration.replay import iter_windows
from src.calibration.session_theta_beta import ThetaBetaSessionCalibrator
from src.music_gen.spotify_controller import MoodStabilizer, NeuroFeatures, propose_mood
from src.processing.mood_prepare import stabilizer_outputs_for_mood
from src.processing.dashboard_features import DashboardFeatureState
from src.processing.focus_map import focus_from_theta_beta_mean


@dataclass
class TraceRow:
    window_ix: int
    t_start_s: float
    t_end_s: float
    theta_power_mean: float
    alpha_power_mean: float
    beta_power_mean: float
    gamma_power_mean: float
    theta_beta_mean: float
    beta_theta_mean: float
    alpha_sup_mean_pct: float
    alpha_sup_mean_norm: float
    sustained_streak_sec: float
    sustained_attention_index: float
    is_attentive: bool
    rolling_variability: float | None
    energy_index: float | None
    raw_energy: float
    raw_focus: float
    ema_energy: float
    ema_focus: float
    d_energy: float
    proposed_mood: str
    majority_mood: str
    focus_theta_beta_global: float
    focus_theta_beta_session: float | None
    session_tb_low: float | None
    session_tb_high: float | None

    def flat(self) -> dict[str, Any]:
        d = asdict(self)
        return d


def iter_trace_rows(
    data: np.ndarray,
    *,
    window_seconds: float = 1.0,
    session_tb: bool = False,
) -> Iterator[TraceRow]:
    dash = DashboardFeatureState()
    mood = MoodStabilizer()
    tb_cal = ThetaBetaSessionCalibrator() if session_tb else None
    for ix, seg in iter_windows(data):
        wf = dash.process_window(seg)
        raw_e = float(wf.energy_index) if wf.energy_index is not None else 0.5
        raw_f = float(wf.sustained_attention_index)
        se, sf, d_e = stabilizer_outputs_for_mood(mood, raw_e, raw_f)
        proposed = propose_mood(NeuroFeatures(energy=se, focus=sf, d_energy=d_e))
        majority = mood.majority_mood(proposed)

        fg = focus_from_theta_beta_mean(wf.theta_beta_mean)
        fs: float | None = None
        slo = shi = None
        if tb_cal is not None:
            tb_cal.observe(wf.theta_beta_mean)
            b = tb_cal.bounds()
            if b is not None:
                slo, shi = b
                fs = focus_from_theta_beta_mean(wf.theta_beta_mean, low=slo, high=shi)

        t0 = ix * window_seconds
        yield TraceRow(
            window_ix=ix,
            t_start_s=t0,
            t_end_s=t0 + window_seconds,
            theta_power_mean=float(np.mean(wf.theta_power)),
            alpha_power_mean=float(np.mean(wf.alpha_power)),
            beta_power_mean=float(np.mean(wf.beta_power)),
            gamma_power_mean=float(np.mean(wf.gamma_power)),
            theta_beta_mean=wf.theta_beta_mean,
            beta_theta_mean=float(
                np.mean(np.where(wf.theta_power > 0, wf.beta_power / wf.theta_power, 0.0))
            ),
            alpha_sup_mean_pct=wf.alpha_sup_mean,
            alpha_sup_mean_norm=wf.alpha_sup_mean_norm,
            sustained_streak_sec=wf.sustained_streak_sec,
            sustained_attention_index=wf.sustained_attention_index,
            is_attentive=wf.is_attentive,
            rolling_variability=wf.rolling_variability,
            energy_index=wf.energy_index,
            raw_energy=raw_e,
            raw_focus=raw_f,
            ema_energy=float(se),
            ema_focus=float(sf),
            d_energy=float(d_e),
            proposed_mood=str(proposed),
            majority_mood=str(majority),
            focus_theta_beta_global=fg,
            focus_theta_beta_session=fs,
            session_tb_low=slo,
            session_tb_high=shi,
        )

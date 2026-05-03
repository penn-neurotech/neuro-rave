"""One-second dashboard EEG features (shared by main, WebSocket server, calibration).

Uses alpha suppression in **percent** per channel (matching the dashboard WebSocket
path). ``main.py`` previously used a 0–1 clip; it now uses this module so live,
replay, and tuning stay aligned.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, iirnotch, lfilter

import src.constants as const


@dataclass(frozen=True)
class FeatureThresholds:
    """Injectable thresholds for calibration search (defaults from ``constants``)."""

    attention_alpha_sup_threshold: float = float(const.ATTENTION_ALPHA_SUP_THRESHOLD)
    attention_sustained_sec: float = float(const.ATTENTION_SUSTAINED_SEC)
    attention_variability_sec: float = float(const.ATTENTION_VARIABILITY_SEC)
    attention_variability_max: float = float(const.ATTENTION_VARIABILITY_MAX)
    line_freq_hz: float = float(const.LINE_FREQ)
    window_seconds: float = 1.0


@dataclass
class WindowFeatureResult:
    """Outputs for one window ``(WINDOW_SIZE, N_CHANNELS)`` after preprocessing."""

    theta_power: np.ndarray
    alpha_power: np.ndarray
    beta_power: np.ndarray
    gamma_power: np.ndarray
    theta_beta: np.ndarray
    alpha_suppression_percent: np.ndarray
    alpha_sup_mean: float
    alpha_sup_mean_norm: float
    sustained_streak_sec: float
    sustained_attention_index: float
    is_attentive: bool
    rolling_variability: float | None
    energy_index: float | None
    theta_beta_mean: float

    def to_spotify_feature_dict(
        self,
        *,
        energy_index: float | None = None,
        sustained_attention_index: float | None = None,
    ) -> dict:
        """Shape expected by ``SpotifyFeaturePipeline.process``."""
        d: dict = {
            "alpha_suppression": self.alpha_suppression_percent,
            "theta_beta_ratio": self.theta_beta,
            "gamma": self.gamma_power,
        }
        if energy_index is not None:
            d["energy_index"] = energy_index
        if sustained_attention_index is not None:
            d["sustained_attention_index"] = sustained_attention_index
        return d


class DashboardFeatureState:
    """Mutable state + :meth:`process_window` — same logic as ``ws_server`` features."""

    def __init__(self, thresholds: FeatureThresholds | None = None) -> None:
        self.th = thresholds or FeatureThresholds()
        self._feat_alpha_hist: list[np.ndarray] = []
        self._feat_current_streak_sec: float = 0.0
        self._feat_variability_window_size: int = max(
            1,
            round(float(self.th.attention_variability_sec) / self.th.window_seconds),
        )
        self._feat_alpha_sup_history: list[float] = []

    def reset(self) -> None:
        self._feat_alpha_hist.clear()
        self._feat_current_streak_sec = 0.0
        self._feat_alpha_sup_history.clear()

    def process_window(self, data: np.ndarray) -> WindowFeatureResult:
        """``data`` float array shape ``(WINDOW_SIZE, N_CHANNELS)``."""
        fs = float(const.SAMPLE_RATE)
        win = int(const.WINDOW_SIZE)
        if data.shape != (win, int(const.N_CHANNELS)):
            raise ValueError(
                f"Expected data shape ({win}, {const.N_CHANNELS}), got {data.shape}"
            )
        arr = np.asarray(data, dtype=np.float64)

        def _bandpass(d: np.ndarray, lo: float, hi: float) -> np.ndarray:
            b, a = butter(4, [lo / (fs / 2), hi / (fs / 2)], btype="band")
            return lfilter(b, a, d, axis=0)

        lf = float(self.th.line_freq_hz)
        b_notch, a_notch = iirnotch(lf / (fs / 2), 30)
        d = lfilter(b_notch, a_notch, arr, axis=0)
        b_bp, a_bp = butter(4, [1 / (fs / 2), 100 / (fs / 2)], btype="band")
        d = lfilter(b_bp, a_bp, d, axis=0)

        theta = _bandpass(d, 4, 8)
        alpha = _bandpass(d, 8, 13)
        beta = _bandpass(d, 13, 30)
        gamma = _bandpass(d, 30, 100)
        self._feat_alpha_hist.append(alpha.copy())

        def _bandpower(x: np.ndarray) -> np.ndarray:
            return np.mean(x**2, axis=0)

        theta_power = _bandpower(theta)
        alpha_power = _bandpower(alpha)
        beta_power = _bandpower(beta)
        gamma_power = _bandpower(gamma)
        theta_beta = np.where(beta_power > 0, theta_power / beta_power, 0.0)

        alpha_sup = np.zeros(const.N_CHANNELS)
        if len(self._feat_alpha_hist) > 5:
            baseline_data = np.concatenate(self._feat_alpha_hist[:5], axis=0)
            baseline = np.mean(baseline_data**2, axis=0)
            alpha_sup = np.where(
                baseline > 0,
                (baseline - alpha_power) / baseline * 100,
                0.0,
            )

        alpha_sup_mean = float(np.mean(alpha_sup))
        alpha_sup_mean_norm = float(np.clip(alpha_sup_mean / 100.0, 0.0, 1.0))

        if alpha_sup_mean_norm > float(self.th.attention_alpha_sup_threshold):
            self._feat_current_streak_sec += self.th.window_seconds
        else:
            self._feat_current_streak_sec = 0.0

        sustained_streak_sec = self._feat_current_streak_sec
        sustained_attention_index = min(
            sustained_streak_sec / float(self.th.attention_sustained_sec), 1.0
        )
        is_attentive = sustained_streak_sec >= float(self.th.attention_sustained_sec)

        self._feat_alpha_sup_history.append(alpha_sup_mean_norm)
        if len(self._feat_alpha_sup_history) > self._feat_variability_window_size:
            self._feat_alpha_sup_history.pop(0)

        rolling_variability: float | None
        energy_index: float | None
        if len(self._feat_alpha_sup_history) < self._feat_variability_window_size:
            rolling_variability = None
            energy_index = None
        else:
            rolling_variability = float(np.std(self._feat_alpha_sup_history))
            energy_index = min(
                rolling_variability / float(self.th.attention_variability_max), 1.0
            )

        return WindowFeatureResult(
            theta_power=theta_power,
            alpha_power=alpha_power,
            beta_power=beta_power,
            gamma_power=gamma_power,
            theta_beta=theta_beta,
            alpha_suppression_percent=alpha_sup,
            alpha_sup_mean=alpha_sup_mean,
            alpha_sup_mean_norm=alpha_sup_mean_norm,
            sustained_streak_sec=float(sustained_streak_sec),
            sustained_attention_index=float(sustained_attention_index),
            is_attentive=bool(is_attentive),
            rolling_variability=rolling_variability,
            energy_index=energy_index,
            theta_beta_mean=float(np.mean(theta_beta)),
        )

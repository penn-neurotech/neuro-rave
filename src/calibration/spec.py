"""Human-readable calibration / feature definition (export as JSON)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import src.constants as const


def calibration_spec_dict() -> dict[str, Any]:
    """Canonical formulas: same fields previously under ``phase0_spec``."""
    return {
        "implementation": "neuro-rave calibration spec",
        "reference_modules": {
            "dashboard_window": "src.processing.dashboard_features.DashboardFeatureState",
            "theta_beta_focus": "src.processing.focus_map.focus_from_theta_beta_mean",
            "session_theta_beta": "src.calibration.session_theta_beta.ThetaBetaSessionCalibrator",
            "mood": "src.music_gen.spotify_controller.propose_mood",
        },
        "sampling": {
            "SAMPLE_RATE_HZ": const.SAMPLE_RATE,
            "WINDOW_SAMPLES": const.WINDOW_SIZE,
            "window_duration_s": const.WINDOW_SIZE / float(const.SAMPLE_RATE),
            "N_CHANNELS": const.N_CHANNELS,
        },
        "preprocessing": {
            "notch_line_freq_hz": const.LINE_FREQ,
            "notch_Q": 30,
            "broad_bandpass_hz": [1, 100],
            "butter_order": 4,
        },
        "bands_hz": {"theta": [4, 8], "alpha": [8, 13], "beta": [13, 30], "gamma": [30, 100]},
        "theta_beta": {
            "ratio": "theta_power / beta_power per channel; mean -> theta_beta_mean",
            "focus_linear_map": "(HIGH - mean) / (HIGH - LOW) clipped to [0,1]; "
            "lower ratio => higher focus",
            "global_bounds": {
                "FOCUS_THETA_BETA_LOW": const.FOCUS_THETA_BETA_LOW,
                "FOCUS_THETA_BETA_HIGH": const.FOCUS_THETA_BETA_HIGH,
            },
            "session_calibration": {
                "enabled_config": bool(getattr(const, "SESSION_THETA_BETA_CALIBRATION", False)),
                "warmup_windows": const.SESSION_THETA_BETA_WARMUP_WINDOWS,
                "low_percentile": const.SESSION_THETA_BETA_LOW_PERCENTILE,
                "high_percentile": const.SESSION_THETA_BETA_HIGH_PERCENTILE,
            },
        },
        "channels": {
            "live_lsl": "Unlabeled column order from BioSemi bridge — must match lab map.",
            "bdf_default": "Replay uses A1..A8 when labels exist.",
        },
        "neuro_feature_source": {
            "config_key": "NEURO_FEATURE_SOURCE",
            "values": {
                "attention": "MoodStabilizer inputs = energy_index (variability) + sustained_attention_index (streak).",
                "band_pipeline": "MoodStabilizer inputs = SpotifyFeaturePipeline (bands); same smooth + propose_mood after.",
            },
        },
        "neuro_apply_stabilizer_smooth": {
            "config_key": "NEURO_APPLY_STABILIZER_SMOOTH",
            "default": True,
            "false_means": "Skip MoodStabilizer EMA; propose_mood uses routed raw e/f and step d_energy. "
            "attention: one smoothing layer (rolling indices only). "
            "band_pipeline: only SpotifyFeaturePipeline temporal shaping remains.",
        },
    }


def write_calibration_spec_json(path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(calibration_spec_dict(), indent=2) + "\n", encoding="utf-8")
    return p

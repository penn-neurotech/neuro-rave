"""NEURO_FEATURE_SOURCE routing for MoodStabilizer inputs."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import src.constants as const
from src.processing.neuro_raw_inputs import neuro_raw_inputs_for_stabilizer
from src.processing.spotify_feature_pipeline import SpotifyFeaturePipeline


def _minimal_eeg_dict() -> dict:
    return {
        "alpha_suppression": np.array([5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0]),
        "theta_beta_ratio": np.ones(8) * 0.25,
        "gamma": np.ones(8) * 1e-8,
        "energy_index": 0.7,
        "sustained_attention_index": 0.6,
    }


def test_attention_path_matches_direct_indices(monkeypatch) -> None:
    monkeypatch.setattr(const, "NEURO_FEATURE_SOURCE", "attention")
    d = _minimal_eeg_dict()
    e, f = neuro_raw_inputs_for_stabilizer(d, band_pipeline=None)
    assert e == 0.7 and f == 0.6
    d2 = dict(d)
    del d2["energy_index"]
    e2, f2 = neuro_raw_inputs_for_stabilizer(d2, band_pipeline=None)
    assert e2 == 0.5 and f2 == 0.6


def test_band_pipeline_path_uses_pipeline(monkeypatch) -> None:
    monkeypatch.setattr(const, "NEURO_FEATURE_SOURCE", "band_pipeline")
    pipe = SpotifyFeaturePipeline()
    d = _minimal_eeg_dict()
    e, f = neuro_raw_inputs_for_stabilizer(d, band_pipeline=pipe)
    assert 0.0 <= e <= 1.0 and 0.0 <= f <= 1.0
    e2, f2 = neuro_raw_inputs_for_stabilizer(d, band_pipeline=pipe)
    assert isinstance(e2, float) and isinstance(f2, float)

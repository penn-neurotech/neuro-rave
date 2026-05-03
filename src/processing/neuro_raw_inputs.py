"""Choose raw (energy, focus) inputs to ``MoodStabilizer`` before smoothing and ``propose_mood``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import src.constants as const

if TYPE_CHECKING:
    from src.processing.spotify_feature_pipeline import SpotifyFeaturePipeline


def eeg_dict_for_band_pipeline(eeg_features: dict[str, Any]) -> dict[str, Any]:
    """Build the dict expected by ``SpotifyFeaturePipeline.process``."""
    d: dict[str, Any] = {
        "alpha_suppression": eeg_features["alpha_suppression"],
        "theta_beta_ratio": eeg_features["theta_beta_ratio"],
        "gamma": eeg_features["gamma"],
    }
    ei = eeg_features.get("energy_index")
    si = eeg_features.get("sustained_attention_index")
    if ei is not None:
        d["energy_index"] = ei
    if si is not None:
        d["sustained_attention_index"] = si
    return d


def neuro_raw_inputs_for_stabilizer(
    eeg_features: dict[str, Any],
    *,
    band_pipeline: SpotifyFeaturePipeline | None,
) -> tuple[float, float]:
    """Return ``(raw_energy, raw_focus)`` in [0,1] scale for :meth:`MoodStabilizer.smooth`.

    * ``attention`` — same as before: variability index (or 0.5 warm-up) + sustained attention index.
    * ``band_pipeline`` — ``SpotifyFeaturePipeline.process`` (alpha/gamma/theta-beta + optional blends).
    """
    if const.NEURO_FEATURE_SOURCE == "band_pipeline":
        if band_pipeline is None:
            raise RuntimeError(
                "NEURO_FEATURE_SOURCE=band_pipeline requires a SpotifyFeaturePipeline instance"
            )
        nf = band_pipeline.process(eeg_dict_for_band_pipeline(eeg_features))
        return float(nf.energy), float(nf.focus)

    raw_energy = eeg_features.get("energy_index")
    raw_focus = eeg_features.get("sustained_attention_index")
    return (
        float(raw_energy) if raw_energy is not None else 0.5,
        float(raw_focus) if raw_focus is not None else 0.0,
    )

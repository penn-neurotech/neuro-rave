"""Load BioSemi BDF recordings as float32 (n_samples, n_channels) at ``SAMPLE_RATE``."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import mne
import numpy as np

import src.constants as const


def default_eight_channel_labels(raw: mne.io.BaseRaw) -> list[str]:
    """Prefer A1..A8; else first eight EEG picks."""
    names = raw.ch_names
    picked: list[str] = []
    for i in range(1, 9):
        lab = f"A{i}"
        if lab in names:
            picked.append(lab)
    if len(picked) == 8:
        return picked
    eeg = mne.pick_types(raw.info, eeg=True, exclude="bads")
    return [names[j] for j in eeg[:8]]


def load_bdf_array(
    path: str | Path,
    *,
    channel_labels: Sequence[str] | None = None,
    target_sfreq: float | None = None,
) -> tuple[np.ndarray, list[str], float]:
    """Return ``(data, labels, duration_s)`` with ``data`` shape (n_samples, n_ch)."""
    p = Path(path)
    raw = mne.io.read_raw_bdf(p, preload=True, verbose="ERROR")
    labels = list(channel_labels) if channel_labels is not None else default_eight_channel_labels(raw)
    raw.pick(picks=labels, verbose="ERROR")
    sf = float(target_sfreq if target_sfreq is not None else const.SAMPLE_RATE)
    if raw.info["sfreq"] != sf:
        raw.resample(sf, verbose="ERROR")
    arr = np.asarray(raw.get_data(), dtype=np.float32).T
    duration_s = float(raw.times[-1])
    return arr, labels, duration_s

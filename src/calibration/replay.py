"""Slice continuous (n_samples, n_channels) arrays into runtime-sized windows."""

from __future__ import annotations

from typing import Iterator

import numpy as np

import src.constants as const


def iter_windows(data: np.ndarray) -> Iterator[tuple[int, np.ndarray]]:
    """Yield ``(window_index, segment)`` with ``segment.shape == (WINDOW_SIZE, N_CHANNELS)``."""
    win = int(const.WINDOW_SIZE)
    n = data.shape[0] // win
    for i in range(n):
        yield i, data[i * win : (i + 1) * win, :]

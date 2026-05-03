"""Smoke test on real BDF when present (not required in CI)."""

from __future__ import annotations

from itertools import islice
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_BDF = _ROOT / "eeg data" / "Copy of nrt06_eeg_1.bdf"


@pytest.mark.skipif(not _BDF.is_file(), reason="example BDF not in workspace")
def test_bdf_load_and_trace_smoke() -> None:
    from src.calibration.bdf_loader import load_bdf_array
    from src.calibration.metrics import label_free_report
    from src.calibration.tracer import iter_trace_rows

    data, labels, dur = load_bdf_array(_BDF)
    assert data.ndim == 2
    assert len(labels) == 8
    assert dur > 60
    rows = [r.flat() for r in islice(iter_trace_rows(data, session_tb=True), 400)]
    rep = label_free_report(rows)
    assert rep["n_windows"] == 400

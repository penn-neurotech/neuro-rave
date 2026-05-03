"""Label-free (and optional label-based) scores for calibration reports."""

from __future__ import annotations

from collections import Counter
from typing import Any, Sequence


def mood_switch_rate_per_minute(moods: Sequence[str], *, window_s: float = 1.0) -> float:
    if len(moods) < 2:
        return 0.0
    switches = sum(1 for i in range(1, len(moods)) if moods[i] != moods[i - 1])
    minutes = (len(moods) * window_s) / 60.0
    return float(switches / minutes) if minutes > 0 else 0.0


def saturation_fraction(values: Sequence[float], *, lo: float = 0.0, hi: float = 1.0, eps: float = 1e-6) -> float:
    """Fraction of samples on the boundary (clipped regime)."""
    if not values:
        return 0.0
    n = sum(1 for v in values if v <= lo + eps or v >= hi - eps)
    return float(n / len(values))


def label_free_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """``rows`` = list of flat dicts (e.g. CSV rows) with keys from :mod:`tracer`."""
    if not rows:
        return {"error": "no_rows"}

    def col(name: str) -> list[float]:
        out: list[float] = []
        for r in rows:
            v = r.get(name)
            if v is None or v == "":
                continue
            try:
                out.append(float(v))
            except (TypeError, ValueError):
                continue
        return out

    tb = col("theta_beta_mean")
    moods = [str(r.get("majority_mood", "")) for r in rows]
    focus_tb = col("focus_theta_beta_global")
    cnt = Counter(moods)
    dominant_frac = float(cnt.most_common(1)[0][1] / len(rows)) if moods else 0.0

    import statistics

    def spread(xs: list[float]) -> float:
        return float(max(xs) - min(xs)) if len(xs) > 1 else 0.0

    report = {
        "n_windows": len(rows),
        "theta_beta_mean": {
            "min": min(tb) if tb else None,
            "max": max(tb) if tb else None,
            "spread": spread(tb),
            "stdev": float(statistics.pstdev(tb)) if len(tb) > 1 else 0.0,
        },
        "focus_theta_beta_global": {
            "min": min(focus_tb) if focus_tb else None,
            "max": max(focus_tb) if focus_tb else None,
            "saturation_0_1": saturation_fraction(focus_tb),
        },
        "mood_majority": dict(cnt),
        "mood_dominant_fraction": dominant_frac,
        "mood_switches_per_minute": mood_switch_rate_per_minute([m for m in moods if m]),
    }
    return report


def macro_f1_mood(y_true: Sequence[str], y_pred: Sequence[str]) -> float:
    """Per-class F1 then unweighted mean; unknown labels skipped for F1."""
    if len(y_true) != len(y_pred) or not y_true:
        return 0.0
    labels = sorted(set(y_true) | set(y_pred))
    f1s: list[float] = []
    for lab in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p == lab)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != lab and p == lab)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == lab and p != lab)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        f1s.append(f1)
    return float(sum(f1s) / len(f1s)) if f1s else 0.0

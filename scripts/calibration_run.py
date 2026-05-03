#!/usr/bin/env python3
"""Calibration CLI: trace BDF → CSV, report metrics, grid-search attention knobs, export JSON."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _cmd_trace(ns: argparse.Namespace) -> None:
    from src.calibration.bdf_loader import load_bdf_array
    from src.calibration.spec import write_calibration_spec_json
    from src.calibration.tracer import iter_trace_rows

    data, labels, dur = load_bdf_array(ns.bdf)
    ns.out.parent.mkdir(parents=True, exist_ok=True)
    write_calibration_spec_json(ns.out.parent / "calibration_spec.json")
    fieldnames: list[str] | None = None
    with ns.out.open("w", newline="", encoding="utf-8") as f:
        writer: csv.DictWriter[str] | None = None
        for row in iter_trace_rows(data, session_tb=bool(ns.session_tb)):
            d = row.flat()
            if fieldnames is None:
                fieldnames = list(d.keys())
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
            assert writer is not None
            writer.writerow({k: ("" if d[k] is None else d[k]) for k in fieldnames})
    print(f"channels: {labels}  duration_min: {dur/60:.3f}  csv: {ns.out}")


def _cmd_report(ns: argparse.Namespace) -> None:
    import csv

    from src.calibration.metrics import label_free_report
    from src.calibration.search import suggest_theta_beta_bounds

    rows: list[dict[str, str]] = []
    with ns.csv.open(encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(dict(row))
    rep = label_free_report(rows)
    tb_vals = []
    for row in rows:
        v = row.get("theta_beta_mean")
        if v not in (None, ""):
            try:
                tb_vals.append(float(v))
            except ValueError:
                pass
    rep["theta_beta_session_bounds_hint"] = suggest_theta_beta_bounds(tb_vals)
    text = json.dumps(rep, indent=2)
    print(text)
    if ns.json_out:
        ns.json_out.parent.mkdir(parents=True, exist_ok=True)
        ns.json_out.write_text(text + "\n", encoding="utf-8")
        print("wrote", ns.json_out)


def _cmd_search(ns: argparse.Namespace) -> None:
    from src.calibration.bdf_loader import load_bdf_array
    from src.calibration.replay import iter_windows
    from src.calibration.search import grid_search_attention, suggest_theta_beta_bounds
    from src.processing.dashboard_features import DashboardFeatureState, FeatureThresholds

    data, _labels, _dur = load_bdf_array(ns.bdf)
    ranked = grid_search_attention(data)
    best = ranked[0]
    dash = DashboardFeatureState(FeatureThresholds())
    tb_list = [dash.process_window(seg).theta_beta_mean for _, seg in iter_windows(data)]
    best["theta_beta_session_bounds_hint"] = suggest_theta_beta_bounds(tb_list)
    out = {"best": best, "top_5": ranked[:5]}
    txt = json.dumps(out, indent=2, default=str)
    print(txt)
    if ns.json_out:
        ns.json_out.parent.mkdir(parents=True, exist_ok=True)
        ns.json_out.write_text(txt + "\n", encoding="utf-8")


def _cmd_write_calibrated(ns: argparse.Namespace) -> None:
    from src.calibration.bdf_loader import load_bdf_array
    from src.calibration.search import grid_search_attention

    data, _l, _d = load_bdf_array(ns.bdf)
    best = grid_search_attention(data)[0]
    src = _ROOT / "config" / "constants.json"
    cfg = json.loads(src.read_text(encoding="utf-8"))
    cfg["ATTENTION_ALPHA_SUP_THRESHOLD"] = best["ATTENTION_ALPHA_SUP_THRESHOLD"]
    cfg["ATTENTION_VARIABILITY_MAX"] = best["ATTENTION_VARIABILITY_MAX"]
    out = Path(ns.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    print("wrote", out)


def _cmd_apply(ns: argparse.Namespace) -> None:
    cal = Path(ns.calibrated)
    if not cal.is_file():
        print("missing", cal, file=sys.stderr)
        sys.exit(1)
    cfg_dir = _ROOT / "config"
    backup_dir = cfg_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    live = cfg_dir / "constants.json"
    if live.is_file():
        shutil.copy2(live, backup_dir / f"constants.{stamp}.json")
    shutil.copy2(cal, live)
    print("applied", cal, "->", live)


def main() -> None:
    ap = argparse.ArgumentParser(description="EEG calibration tools")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("trace", help="BDF → CSV + calibration_spec.json")
    t.add_argument("bdf", type=Path)
    t.add_argument("--out", type=Path, default=_ROOT / "artifacts" / "calibration" / "windows.csv")
    t.add_argument("--session-tb", action="store_true", help="Include session theta/beta focus columns")
    t.set_defaults(func=_cmd_trace)

    r = sub.add_parser("report", help="Summarize a trace CSV")
    r.add_argument("csv", type=Path)
    r.add_argument("--json-out", type=Path, default=None)
    r.set_defaults(func=_cmd_report)

    s = sub.add_parser("search", help="Grid search attention thresholds on a BDF")
    s.add_argument("bdf", type=Path)
    s.add_argument("--json-out", type=Path, default=None)
    s.set_defaults(func=_cmd_search)

    w = sub.add_parser("write-calibrated", help="Write constants.calibrated.json (full JSON + best attention fields)")
    w.add_argument("bdf", type=Path)
    w.add_argument("--out", type=Path, default=_ROOT / "config" / "constants.calibrated.json")
    w.set_defaults(func=_cmd_write_calibrated)

    a = sub.add_parser("apply", help="Backup constants.json and replace with calibrated file")
    a.add_argument("calibrated", type=Path, nargs="?", default=_ROOT / "config" / "constants.calibrated.json")
    a.set_defaults(func=_cmd_apply)

    ns = ap.parse_args()
    ns.func(ns)


if __name__ == "__main__":
    main()

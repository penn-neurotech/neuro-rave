"""Dashboard-selected Spotify playback mode (context / playlist vs pool), persisted next to other config."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

Mode = Literal["context", "pool", "recommendations"]


def _config_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config"


def dashboard_playback_mode_path() -> Path:
    return _config_dir() / "dashboard_spotify_playback_mode.json"


def read_dashboard_playback_mode() -> Mode:
    """File overrides ``SPOTIFY_PLAYBACK_MODE`` when present and valid."""
    path = dashboard_playback_mode_path()
    if path.is_file():
        try:
            data: Any = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                raw = str(data.get("mode", "")).strip().lower()
                if raw in ("playlist", "context"):
                    return "context"
                if raw == "pool":
                    return "pool"
                if raw == "recommendations":
                    return "recommendations"
        except (OSError, json.JSONDecodeError):
            pass
    em = os.environ.get("SPOTIFY_PLAYBACK_MODE", "context").strip().lower()
    if em in ("playlist", "context"):
        return "context"
    if em == "pool":
        return "pool"
    if em == "recommendations":
        return "recommendations"
    return "context"


def write_dashboard_playback_mode(mode: str) -> Mode:
    """Persist ``context`` (playlist), ``pool``, or ``recommendations``."""
    m = str(mode).strip().lower()
    if m in ("playlist", "context"):
        norm: Mode = "context"
    elif m == "pool":
        norm = "pool"
    elif m == "recommendations":
        norm = "recommendations"
    else:
        raise ValueError(f"unsupported playback mode: {mode!r}")

    path = dashboard_playback_mode_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mode": norm}, indent=2), encoding="utf-8")
    return norm

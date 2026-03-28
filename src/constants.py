import json
import os
from pathlib import Path

# Single source of truth is config/constants.json
_config_path = Path(__file__).parent.parent / "config" / "constants.json"
_config = json.loads(_config_path.read_text())


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


### Mode
# JSON default; override with SIMULATE=1 or EEG_SIM=1 (legacy) for local/Docker without editing the file.
if "EEG_SIM" in os.environ:
    SIMULATE: bool = _env_truthy("EEG_SIM")
elif "SIMULATE" in os.environ:
    SIMULATE: bool = _env_truthy("SIMULATE")
else:
    SIMULATE: bool = bool(_config["SIMULATE"])

### Signal Processing
N_CHANNELS:       int = _config["N_CHANNELS"]
SAMPLE_RATE:      int = _config["SAMPLE_RATE"]
WINDOW_SIZE:      int = _config["WINDOW_SIZE"]

### BioSemi Hardware
# BIOSEMI_HOST can be overridden by environment variable (used by Docker)
BIOSEMI_HOST:     str = os.environ.get("BIOSEMI_HOST", _config["BIOSEMI_HOST"])
BIOSEMI_PORT:     int = _config["BIOSEMI_PORT"]
BYTES_PER_SAMPLE: int = _config["BYTES_PER_SAMPLE"]
WS_HOST:          str = _config["WS_HOST"]
WS_PORT:          int = _config["WS_PORT"]
DASHBOARD_PORT:   int = _config["DASHBOARD_PORT"]

### Spotify API
SPOTIFY_CLIENT_ID:      str = _config["SPOTIFY_CLIENT_ID"]
SPOTIFY_CLIENT_SECRET:  str = _config["SPOTIFY_CLIENT_SECRET"]
SPOTIFY_PLAYLIST_CALM:  str = _config["SPOTIFY_PLAYLIST_CALM"]
SPOTIFY_PLAYLIST_FOCUS: str = _config["SPOTIFY_PLAYLIST_FOCUS"]
SPOTIFY_PLAYLIST_HYPE:  str = _config["SPOTIFY_PLAYLIST_HYPE"]

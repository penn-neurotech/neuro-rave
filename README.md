# NEURO-RAVE

**Real-time EEG-driven music generation system**

NEURO-RAVE streams EEG data from BioSemi hardware, processes neural
features in real time, and uses those features to influence live music
generation.

------------------------------------------------------------------------

# System Overview

BioSemi → ActiView (TCP) → Python TCP Client → LSL Stream → Processing +
Feature Extraction → Dashboard + Music Generation

------------------------------------------------------------------------

# Project Structure

NEURO-RAVE/ ├── dashboard/ \# Real-time visualization ├── hardware/ \#
BioSemi / acquisition logic ├── music-gen/ \# Music generation API logic
├── processing/ \# Signal processing + feature extraction ├── streaming/
\# TCP → LSL bridge ├── Dockerfile ├── requirements.txt └── README.md

Each directory represents a functional module.

------------------------------------------------------------------------
# Environment Setup

## Docker

```bash
docker compose build
docker compose up
```

To stop: `docker compose down`

### Running other scripts in the container

```bash
# Open a shell inside the running container
docker compose exec neuro-rave bash

# Run a one-off script
docker compose run --rm neuro-rave python src/streaming/tcp_test.py
```

Source files are volume-mounted, so local edits are reflected immediately without rebuilding.

### Spotify demos (Docker only)

**Requirements:** Spotify Premium account + active playback device

#### 1) Refresh token (run once on your machine)

The refresh-token helper must run on the host (browser callback to `http://127.0.0.1:8080/callback`).
Add that redirect URI in the Spotify Developer Dashboard if needed. Spotify may warn about
`localhost`; use `127.0.0.1` in the dashboard.

```bash
python3 get_spotify_refresh_token.py
```

That writes `SPOTIFY_REFRESH_TOKEN` into `./.env`. Restart containers after changing `.env`.

#### 2) Activate Spotify on a device

Open the Spotify app and start playing any song so API playback control works.

#### 3) Docker demo — fixed mood (60 seconds each)

Use `-e` so mood and duration are passed into the container (Compose may otherwise set empty values).

```bash
docker compose run --rm \
  -e SPOTIFY_FIXED_MOOD=hype \
  -e SPOTIFY_FIXED_DURATION_S=60 \
  -e SPOTIFY_FIXED_TICK_S=1 \
  neuro-rave python scripts/spotify_fixed_mood_demo.py

docker compose run --rm \
  -e SPOTIFY_FIXED_MOOD=calm \
  -e SPOTIFY_FIXED_DURATION_S=60 \
  -e SPOTIFY_FIXED_TICK_S=1 \
  neuro-rave python scripts/spotify_fixed_mood_demo.py

docker compose run --rm \
  -e SPOTIFY_FIXED_MOOD=focus \
  -e SPOTIFY_FIXED_DURATION_S=60 \
  -e SPOTIFY_FIXED_TICK_S=1 \
  neuro-rave python scripts/spotify_fixed_mood_demo.py
```

**What happens:** The script starts the playlist for that mood and prints progress for 60 seconds.

#### 4) Docker demo — EEG simulator (`main.py`)

Another way to verify Spotify + mood switching without BioSemi: simulated EEG cycles
calm → focus → hype with 60-second steps.

```bash
docker compose run --rm \
  -e EEG_SIM=1 \
  -e EEG_SIM_STEP_S=60 \
  -e SPOTIFY_MIN_SWITCH_S=60 \
  neuro-rave python main.py
```

What to expect:
- Logs show `SIM target=calm/focus/hype ...`.
- Playlists switch about once per minute.
- Keep a Spotify playback device active.

#### 5) Docker demo — auto fallback (real EEG if present, simulator if missing)

Use this mode when you want `main.py` to consume real EEG whenever data is available,
and automatically fall back to simulation when no real chunks arrive.

```bash
docker compose run --rm \
  -e EEG_SIM_AUTO=1 \
  -e EEG_NO_DATA_TIMEOUT_S=2 \
  -e EEG_SIM_STEP_S=60 \
  -e SPOTIFY_MIN_SWITCH_S=60 \
  neuro-rave python main.py
```

What to expect:
- Logs show `EEG mode -> REAL` when incoming real data is detected.
- Logs show `EEG mode -> SIM` after the no-data timeout.
- Spotify switching behavior remains capped by `SPOTIFY_MIN_SWITCH_S`.

## Conda (local development)

```bash
conda create -n neuro-rave python=3.11 -y
conda activate neuro-rave
pip install -r requirements.txt
python main.py
```

#### Troubleshooting Spotify

**❌ "Premium required"**
- You need Spotify Premium for playback control
- Free accounts can only read playlists/metadata

**❌ "No active device found"**
- Open Spotify app and start playing any song first
- This "activates" your device for API control

**❌ "User not registered for this application"**
- Add your Spotify email to the app's user list in Spotify Developer Dashboard
- For >25 users, apply for "Extension Mode"

------------------------------------------------------------------------

# Dependency Rules

All Python dependencies are: - Explicitly version-pinned - Defined in
requirements.txt - Installed only through Docker builds

## Adding a Dependency

1.  Add package with exact version to requirements.txt
2.  Rebuild the container: docker compose build docker compose up

## Removing a Dependency

1.  Delete it from requirements.txt
2.  Rebuild without cache: docker compose build --no-cache docker
    compose up

------------------------------------------------------------------------

# Do NOT

-   Install packages manually inside containers
-   Leave versions unpinned
-   Mix local virtual environments with Docker
-   Upgrade NumPy / MNE without testing the full pipeline

Real-time EEG systems are sensitive to dependency instability.

------------------------------------------------------------------------

# Development Workflow

### Normal Code Changes

If using volume mounting: - Edit Python files locally - No rebuild
required

### Dependency Changes

-   Update requirements.txt
-   Rebuild container

------------------------------------------------------------------------

# ⚡ Reproducibility Policy

The Dockerfile locks: - OS environment - Python version - All dependency
versions

This ensures: - Identical environments across machines - Stable
real-time behavior - Reproducible research

------------------------------------------------------------------------

# FAQ

**`zsh: command not found: docker`**

Docker Desktop must be running. Open it from Applications, wait for the whale icon in the menu bar. If still not found, the symlink may be broken:
```bash
sudo ln -sf /Applications/Docker.app/Contents/Resources/bin/docker /usr/local/bin/docker
```

**`docker-credential-desktop: executable file not found`**

Remove `"credsStore": "desktop"` from `~/.docker/config.json`.

**`ModuleNotFoundError: No module named 'pylsl'`**

You're using the wrong Python. Activate the conda env first:
```bash
conda activate neuro-rave
python main.py
```

**`ConnectionRefused` when running in Docker**

The container can't reach `127.0.0.1` on your host. The `BIOSEMI_HOST` env var in `docker-compose.yml` is set to `host.docker.internal` to handle this. Make sure Docker Desktop is up to date.

**Docker build fails pulling the base image**

Check your internet connection and that Docker Desktop is running. If behind a proxy, configure it in Docker Desktop settings.

**Changes to code not showing in container**

Source files are volume-mounted. If you added a new top-level file (not under `src/`), add it to the `volumes` section in `docker-compose.yml`. Dependency changes always require `docker compose build`.

------------------------------------------------------------------------

# Core Principle

Reproducibility \> Convenience.

A stable neural streaming system is more important than quick local
installs.

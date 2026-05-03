# EEG-Powered Music Dashboard

## Overview

React frontend for the NEURO-RAVE Python backend (`main.py` + WebSocket on **`WS_PORT`**, default **8733**). The server sends **`raw`** and **`features`** JSON packets (see `src/streaming/packets.py` and [docs/dev-reference.md](../docs/dev-reference.md)).

## What it shows

- Live EEG-derived **energy** and **focus** (values after backend routing; when **`NEURO_APPLY_STABILIZER_SMOOTH`** is true in `config/constants.json`, these reflect `MoodStabilizer` smoothing)
- **Mood**: `calm`, `deep_focus`, `focus`, `hype` (from backend `propose_mood`)
- Music mode (Spotify vs Suno), playlist / pool status, activity logs

Backend routing: **`NEURO_FEATURE_SOURCE`** (`attention` vs `band_pipeline`) and **`NEURO_APPLY_STABILIZER_SMOOTH`** — see root **README.md** § Configuration.

## Features

- Live energy and focus bars
- Mood display (including **deep_focus** when the backend proposes it)
- Spotify and Suno panels
- Metric history charts
- Activity log
- Optional mock data for demos (if used in dev)

## Tech stack

- React
- Vite
- CSS

## How to run

From `dashboard/`:

```bash
npm install
npm run dev
```

Start the Python app and WebSocket server from the repo root (**README.md**) so the dashboard receives live packets.

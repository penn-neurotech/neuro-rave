# NEURO-RAVE

**Real-time EEG-driven music generation system**

NEURO-RAVE streams EEG data from BioSemi hardware, processes neural features in
real time, and uses those features to drive live music generation via Spotify and
Suno.

---

## System Overview

```
BioSemi → ActiView (TCP) → LSL Bridge → LSL Stream → EEG Processor
                                                           ↓
                              Dashboard ← WebSocket ← Feature Extraction
                              Spotify / Suno ←────────────┘
```

---

## Project Structure

```
neuro-rave/
├── config/
│   ├── constants.json          # Single source of truth for all config
│   └── spotify_mood_mapping.json
├── src/
│   ├── api/                    # FastAPI REST endpoints (/spotify/*)
│   ├── music_gen/              # Spotify + Suno controllers
│   ├── processing/             # DSP, feature extraction, circular buffer
│   └── streaming/              # Python LSLBridge + WebSocket server
├── native/                     # C and C++ implementations
│   ├── CMakeLists.txt
│   ├── include/                # Headers (config.h, lsl_bridge*.h, ws_server*.h)
│   └── src/                    # C++ (.cpp) and C (.c) source files
├── dashboard/                  # React + Vite frontend
├── scripts/                    # Demo and utility scripts
├── Makefile                    # All run / build targets
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Environment Setup

### Option 1 — Makefile (local, recommended for development)

**Python environment (conda)**

```bash
make setup          # creates neuro-rave conda env + installs all deps
make run            # run main.py inside the conda env
make run-sim        # same (set "SIMULATE": true in config/constants.json first)
make dashboard      # start the React dev server
```

The conda env is created once and only reinstalled when `requirements.txt` changes.
To activate the env for interactive use:

```bash
conda activate neuro-rave
python main.py
```

**JavaScript environment**

```bash
make setup-js       # npm install in dashboard/
make dashboard      # npm run dev
```

### Option 2 — Docker

```bash
docker compose build
docker compose up
```

To stop: `docker compose down`

**Open a shell inside the running container**

```bash
docker compose exec neuro-rave bash
docker compose run --rm neuro-rave python src/streaming/tcp_test.py
```

Source files are volume-mounted, so local edits are reflected immediately
without rebuilding.

---

## C / C++ Native Layer

The `native/` directory contains C and C++ implementations of the LSL bridge and
WebSocket server. These are **standalone binaries** — they run alongside Python
and share `config/constants.json` as the single source of truth.

### Prerequisites

```bash
# macOS
brew install labstreaminglayer/tap/lsl libwebsockets

# Linux (Debian/Ubuntu)
apt install libwebsockets-dev
# liblsl: download from https://github.com/sccn/liblsl/releases
```

### Build

```bash
make build-c                  # runs cmake + make in native/build/
make clean-c                  # remove build artifacts
```

Or directly with CMake:

```bash
cmake -B native/build native/
cmake --build native/build --parallel
```

### Binaries produced

| Binary | Language | Purpose |
|--------|----------|---------|
| `neuro_lsl_bridge` | C++ | BioSemi TCP → LSL outlet |
| `neuro_lsl_bridge_c` | C | BioSemi TCP → LSL outlet |
| `neuro_ws_server` | C++ | LSL inlet → WebSocket broadcast |
| `neuro_ws_server_c` | C | LSL inlet → WebSocket broadcast |

Run from the repo root so `config/constants.json` is found at the expected path:

```bash
./native/build/neuro_lsl_bridge           # C++ LSL bridge
./native/build/neuro_lsl_bridge_c         # C LSL bridge
./native/build/neuro_ws_server            # C++ WebSocket server
./native/build/neuro_ws_server_c          # C WebSocket server

# Pass a custom config path if needed:
./native/build/neuro_lsl_bridge path/to/constants.json
```

The C and C++ classes mirror the Python API exactly — see
[docs/dev-reference.md](docs/dev-reference.md) for the full cross-language
equivalents table.

---

## Configuration

All tuneable values live in **`config/constants.json`** — Python, C, and C++ all
read from this file at startup. Do not add a second source of truth.

Key fields:

| Field | Default | Description |
|-------|---------|-------------|
| `SIMULATE` | `false` | Use generated EEG instead of hardware |
| `BIOSEMI_HOST` | `"127.0.0.1"` | BioSemi TCP host |
| `BIOSEMI_PORT` | `8888` | BioSemi TCP port |
| `WS_PORT` | `8733` | WebSocket server port |
| `N_CHANNELS` | `8` | EEG channel count |
| `SAMPLE_RATE` | `512` | Hz |

To run in simulation mode, set `"SIMULATE": true` in `constants.json`.

---

## Spotify Setup

**Requirements:** Spotify Premium + active playback device

**1. Get a refresh token (run once on your host machine)**

```bash
python get_spotify_refresh_token.py
```

This writes `SPOTIFY_REFRESH_TOKEN` to `.env`. Restart containers after changing
`.env`.

**2. Activate Spotify on a device**

Open the Spotify app and start playing any song.

**3. Fixed-mood demo**

```bash
docker compose run --rm \
  -e SPOTIFY_FIXED_MOOD=hype \
  -e SPOTIFY_FIXED_DURATION_S=60 \
  neuro-rave python scripts/spotify_fixed_mood_demo.py
```

#### Troubleshooting Spotify

| Error | Fix |
|-------|-----|
| "Premium required" | Spotify Premium is required for playback control |
| "No active device found" | Open Spotify and start playing any song first |
| "User not registered" | Add your email in Spotify Developer Dashboard |

---

## Dependency Management

All dependencies are pinned and language-specific:

| Language | File | Install via |
|----------|------|-------------|
| Python | `requirements.txt` | `make setup` or `pip install -r requirements.txt` |
| JavaScript | `dashboard/package.json` | `make setup-js` or `npm install` |
| C / C++ | system libraries | `brew install` / `apt install` (see above) |

**Rules:**
- Pin all Python packages to exact versions in `requirements.txt`
- Do not install packages manually inside containers
- Do not mix local venvs with the conda env or Docker
- Rebuilding C binaries after a `constants.json` change is not required (config is read at runtime)
- Upgrading NumPy or MNE requires testing the full EEG pipeline

---

## Development Workflow

### Python changes
Edit files locally — no rebuild needed (Docker volume-mounts `src/`).

### C / C++ changes
```bash
make build-c
```

### Dependency changes
- Python: update `requirements.txt` → `make setup` (or `docker compose build`)
- JS: update `dashboard/package.json` → `make setup-js`
- C/C++: install system library → re-run `make build-c`

---

## FAQ

**`zsh: command not found: docker`**
Docker Desktop must be running. If the symlink is broken:
```bash
sudo ln -sf /Applications/Docker.app/Contents/Resources/bin/docker /usr/local/bin/docker
```

**`docker-credential-desktop: executable file not found`**
Remove `"credsStore": "desktop"` from `~/.docker/config.json`.

**`ModuleNotFoundError: No module named 'pylsl'`**
```bash
conda activate neuro-rave
python main.py
```

**`ConnectionRefused` when running in Docker**
`BIOSEMI_HOST` in `docker-compose.yml` is set to `host.docker.internal`. Make
sure Docker Desktop is up to date.

**C build: `Could not find LSL` or `Could not find libwebsockets`**
```bash
# macOS
brew install labstreaminglayer/tap/lsl libwebsockets

# Then re-run:
make build-c
```

**C build: headers not found after brew install**
Pass the prefix explicitly:
```bash
cmake -B native/build native/ \
  -DLSL_DIR=$(brew --prefix lsl)/lib/cmake/LSL \
  -DLWS_DIR=$(brew --prefix libwebsockets)/lib/cmake/libwebsockets
```

---

## Core Principle

Reproducibility > Convenience.

A stable neural streaming system is more important than quick local installs.
See [docs/dev-reference.md](docs/dev-reference.md) for the full package and
cross-language reference.

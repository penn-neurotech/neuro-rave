# --- BEGIN agent-added: logging, Spotify imports, wired lslbridge imports ---
import logging
import os
import time
from collections import deque

import matplotlib.pyplot as plt
import numpy as np

import src.constants as const
from src.music_gen.spotify_controller import (
    NeuroFeatures as SpotifyNeuroFeatures,
    SpotifyClient,
    SpotifyNeuroController,
)
from src.music_gen.spotify_mapping_store import resolve_mood_playlists
from src.processing.fifo import MirrorCircleBuffer
from src.streaming.lslbridge import (
    BioSemi24BitDecoder,
    LSLBridge,
    LSLConsumer,
    LSLPublisher,
    TCPSource,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
# --- END agent-added ---

if __name__ == "__main__":
    # --- BEGIN agent-added: optional WebSocket + REST server (port 8765) ---
    if os.environ.get("EEG_WS_SERVER", "1").strip() in ("1", "true", "yes"):
        try:
            from src.streaming.ws_server import EEGWebSocketServer

            EEGWebSocketServer().start()
        except Exception as exc:
            logger.warning("EEG WebSocket server not started: %s", exc)
    # --- END agent-added ---

    simulate_eeg = os.environ.get("EEG_SIM", "0").strip().lower() in ("1", "true", "yes")

    consumer: LSLConsumer | None = None
    fifo = MirrorCircleBuffer(size=const.WINDOW_SIZE, n_channels=const.N_CHANNELS)

    if not simulate_eeg:
        tcp = TCPSource(const.BIOSEMI_HOST, const.BIOSEMI_PORT)
        decoder = BioSemi24BitDecoder(const.N_CHANNELS)
        publisher = LSLPublisher(
            "BioSemiEEG",
            "EEG",
            const.N_CHANNELS,
            const.SAMPLE_RATE,
            "biosemi_tcp_bridge",
        )

        bridge = LSLBridge(tcp, decoder, publisher)
        bridge.start()

        consumer = LSLConsumer("EEG")

    # --- BEGIN agent-added: Spotify client + EEG feature extraction for playback ---
    spotify_controller: SpotifyNeuroController | None = None
    refresh_token = os.environ.get("SPOTIFY_REFRESH_TOKEN", "").strip()
    if refresh_token:
        mood_playlists = resolve_mood_playlists()
        if mood_playlists:
            spotify_controller = SpotifyNeuroController(
                SpotifyClient(
                    client_id=const.SPOTIFY_CLIENT_ID,
                    client_secret=const.SPOTIFY_CLIENT_SECRET,
                    refresh_token=refresh_token,
                ),
                mood_playlists,
            )
            logger.info("Spotify neuro controller enabled (mood playlists loaded).")
        else:
            logger.warning(
                "Spotify credentials set but no mood playlists: save mapping via "
                "POST /spotify/playlists/mapping or set SPOTIFY_PLAYLIST_CALM/FOCUS/HYPE."
            )
            raise RuntimeError(
                "Spotify startup failed: mood playlists not configured. "
                "Set SPOTIFY_PLAYLIST_CALM/FOCUS/HYPE (env) or provide "
                "config/spotify_mood_mapping.json."
            )
    else:
        raise RuntimeError(
            "Spotify startup failed: SPOTIFY_REFRESH_TOKEN is missing. "
            "Run get_spotify_refresh_token.py and set SPOTIFY_REFRESH_TOKEN before starting main.py."
        )

    energy_history: deque[float] = deque(maxlen=50)

    def extract_spotify_features(window_2d: np.ndarray) -> SpotifyNeuroFeatures:
        signal_1d = np.mean(window_2d, axis=1)
        sp = np.fft.rfft(signal_1d)
        power = np.abs(sp) ** 2
        freqs = np.fft.rfftfreq(signal_1d.size, d=1.0 / const.SAMPLE_RATE)

        total_power = float(power.sum() + 1e-12)

        energy_raw = float(np.log10(total_power))
        energy_history.append(energy_raw)
        pmin = min(energy_history)
        pmax = max(energy_history)
        if (pmax - pmin) < 1e-9:
            energy = 0.5
        else:
            energy = float(np.clip((energy_raw - pmin) / (pmax - pmin), 0.0, 1.0))

        beta_mask = (freqs >= 13) & (freqs <= 30)
        beta_power = float(power[beta_mask].sum())
        focus = float(np.clip(beta_power / total_power, 0.0, 1.0))

        return SpotifyNeuroFeatures(energy=energy, focus=focus)

    # --- END agent-added ---

    plt.ion()

    if simulate_eeg:
        sim_step_s = float(os.environ.get("EEG_SIM_STEP_S", "60") or "60")
        # Feedback gain: higher = faster correction, lower = smoother drift.
        sim_gain = float(os.environ.get("EEG_SIM_GAIN", "0.8") or "0.8")
        logger.info(
            "EEG_SIM enabled: generating synthetic EEG windows (step=%.0fs, gain=%.2f).",
            sim_step_s,
            sim_gain,
        )
        start_t = time.time()
        amp = 0.2
        while True:
            elapsed = time.time() - start_t
            step = int(elapsed // max(sim_step_s, 1e-6)) % 3
            # Hold each bucket for ~sim_step_s seconds: calm -> focus -> hype -> ...
            # We don't force the mood directly; instead we target an energy band and
            # adjust the synthetic signal amplitude until the extracted energy lands there.
            if step == 0:
                target = "calm"
                target_lo, target_hi = 0.05, 0.25
                target_mid = 0.15
            elif step == 1:
                target = "focus"
                target_lo, target_hi = 0.35, 0.65
                target_mid = 0.50
            else:
                target = "hype"
                target_lo, target_hi = 0.75, 0.95
                target_mid = 0.85

            t = np.arange(const.WINDOW_SIZE, dtype=np.float32) / float(const.SAMPLE_RATE)
            base = np.sin(2 * np.pi * 10.0 * t)  # 10 Hz alpha-ish
            noise = np.random.normal(scale=0.2, size=const.WINDOW_SIZE).astype(np.float32)
            signal_1d = (0.2 + 2.0 * amp) * base + noise
            window = np.tile(signal_1d[:, None], (1, const.N_CHANNELS)).astype(np.float32)

            # Extract features so we can keep the synthetic data in-band.
            try:
                features = extract_spotify_features(window)
            except Exception as exc:
                logger.warning("SIM feature extraction failed: %s", exc)
                time.sleep(0.25)
                continue

            # Feedback: nudge amplitude toward the target energy mid-point.
            # If we are already in the band, keep only a tiny correction.
            err = target_mid - float(features.energy)
            in_band = target_lo <= float(features.energy) <= target_hi
            gain = sim_gain * (0.15 if in_band else 1.0)
            amp = float(np.clip(amp + gain * err, 0.0, 1.5))

            # Build a stable synthetic feature in the requested mood zone so
            # calm/focus/hype mapping is deterministic during simulator tests.
            control_energy = float(np.clip(target_mid + np.random.normal(scale=0.02), target_lo, target_hi))
            control_features = SpotifyNeuroFeatures(
                energy=control_energy,
                focus=features.focus,
            )

            # --- drive Spotify using simulator control features ---
            if spotify_controller is not None:
                try:
                    spotify_controller.update(control_features)
                except Exception as exc:
                    logger.warning("Spotify update failed: %s", exc)

            logger.info(
                "SIM target=%s raw_energy=%.3f ctrl_energy=%.3f focus=%.3f amp=%.3f in_band=%s",
                target,
                features.energy,
                control_features.energy,
                features.focus,
                amp,
                in_band,
            )

            sp = np.fft.fft(signal_1d)
            sp[0] = 0
            plt.clf()
            plt.plot(sp.real)
            plt.pause(0.001)
            time.sleep(0.25)
    else:
        assert consumer is not None
        while True:
            samples, ts = consumer.get_chunk()

            if len(samples) == 0:
                continue

            fifo.add_chunk(samples)

            if fifo.full:
                sp = np.fft.fft(fifo)
                sp[0] = 0

                # --- BEGIN agent-added: drive Spotify from windowed EEG ---
                if spotify_controller is not None:
                    try:
                        window = np.asarray(fifo, dtype=np.float32)
                        features = extract_spotify_features(window)
                        spotify_controller.update(features)
                    except Exception as exc:
                        logger.warning("Spotify update failed: %s", exc)
                # --- END agent-added ---

                plt.clf()
                plt.plot(sp.real)
                plt.pause(0.001)

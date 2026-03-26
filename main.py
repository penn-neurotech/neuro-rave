# --- BEGIN agent-added: logging, Spotify imports, wired lslbridge imports ---
import logging
import os
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

    tcp = TCPSource(const.BIOSEMI_HOST, const.BIOSEMI_PORT)
    decoder = BioSemi24BitDecoder(const.N_CHANNELS)
    publisher = LSLPublisher(
        "BioSemiEEG", "EEG", const.N_CHANNELS, const.SAMPLE_RATE, "biosemi_tcp_bridge"
    )

    bridge = LSLBridge(tcp, decoder, publisher)
    bridge.start()

    consumer = LSLConsumer("EEG")

    fifo = MirrorCircleBuffer(size=const.WINDOW_SIZE, n_channels=const.N_CHANNELS)

    # --- BEGIN agent-added: Spotify client + EEG feature extraction for playback ---
    spotify_controller: SpotifyNeuroController | None = None
    required_creds = ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN")
    if all(os.environ.get(k, "").strip() for k in required_creds):
        mood_playlists = resolve_mood_playlists()
        if mood_playlists:
            spotify_controller = SpotifyNeuroController(
                SpotifyClient(
                    client_id=os.environ["SPOTIFY_CLIENT_ID"].strip(),
                    client_secret=os.environ["SPOTIFY_CLIENT_SECRET"].strip(),
                    refresh_token=os.environ["SPOTIFY_REFRESH_TOKEN"].strip(),
                ),
                mood_playlists,
            )
            logger.info("Spotify neuro controller enabled (mood playlists loaded).")
        else:
            logger.warning(
                "Spotify credentials set but no mood playlists: save mapping via "
                "POST /spotify/playlists/mapping or set SPOTIFY_PLAYLIST_CALM/FOCUS/HYPE."
            )
    else:
        logger.info("Spotify disabled (set SPOTIFY_* env vars + playlist mapping to enable).")

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

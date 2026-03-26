from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.music_gen.spotify_controller import NeuroFeatures, SpotifyClient, SpotifyNeuroController
from src.music_gen.spotify_mapping_store import resolve_mood_playlists


def _features_for_mood(mood: str) -> NeuroFeatures:
    mood = mood.strip().lower()
    if mood == "calm":
        return NeuroFeatures(energy=0.1, focus=0.5)
    if mood == "focus":
        return NeuroFeatures(energy=0.5, focus=0.8)
    if mood == "hype":
        return NeuroFeatures(energy=0.9, focus=0.5)
    raise ValueError("SPOTIFY_FIXED_MOOD must be one of: calm, focus, hype")


def main() -> None:
    mood = os.environ.get("SPOTIFY_FIXED_MOOD", "focus")
    duration_s = float(os.environ.get("SPOTIFY_FIXED_DURATION_S", "60"))
    tick_s = float(os.environ.get("SPOTIFY_FIXED_TICK_S", "5"))

    mood_playlists = resolve_mood_playlists()
    if not mood_playlists:
        raise RuntimeError(
            "Missing mood playlists. Set SPOTIFY_PLAYLIST_CALM/FOCUS/HYPE in .env "
            "or create config/spotify_mood_mapping.json."
        )

    spotify = SpotifyClient(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
        refresh_token=os.environ["SPOTIFY_REFRESH_TOKEN"],
    )
    controller = SpotifyNeuroController(spotify, mood_playlists)

    features = _features_for_mood(mood)
    controller.update(features)
    print(f"Started mood={mood} features={features} duration_s={duration_s:g}")

    end = time.time() + duration_s
    i = 0
    while time.time() < end:
        # Keep printing so it feels "alive" while the playlist stays fixed.
        print(f"{i:03d} holding mood={mood} ...")
        time.sleep(tick_s)
        i += 1


if __name__ == "__main__":
    main()

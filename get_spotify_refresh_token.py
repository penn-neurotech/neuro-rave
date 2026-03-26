"""
One-time helper script to get a Spotify refresh token.

Usage:
1. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in your environment.
2. Optionally set SPOTIFY_REDIRECT_URI (default: http://127.0.0.1:8080/callback).
2. Run:  python get_spotify_refresh_token.py
3. Open the printed URL in your browser, log in, and approve.
4. After redirect, copy the `code` parameter from the URL.
5. Paste the code into the script when prompted.
6. Copy the printed REFRESH TOKEN and store it securely.
"""

import base64
import os
import urllib.parse

import requests

# --- BEGIN agent-added: read credentials from environment ---
CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "").strip()
CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.environ.get(
    "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8080/callback"
).strip()  # must match app settings
# --- END agent-added ---

# Scopes: playback control + list playlists (for /spotify/playlists/suggestions).
SCOPES = [
    "user-modify-playback-state",
    "user-read-playback-state",
    "playlist-read-private",
    "playlist-read-collaborative",
]


def build_auth_url() -> str:
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
    }
    return "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(params)


def exchange_code_for_tokens(code: str) -> dict:
    token_url = "https://accounts.spotify.com/api/token"
    auth_header = base64.b64encode(
        f"{CLIENT_ID}:{CLIENT_SECRET}".encode("utf-8")
    ).decode("utf-8")

    resp = requests.post(
        token_url,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
        },
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "Missing Spotify credentials. Set SPOTIFY_CLIENT_ID and "
            "SPOTIFY_CLIENT_SECRET in your environment."
        )

    auth_url = build_auth_url()
    print("Open this URL in your browser and approve access:")
    print()
    print(auth_url)
    print()
    print("After you are redirected, copy the 'code' parameter from the URL.")
    code = input("Paste the 'code' value here: ").strip()

    data = exchange_code_for_tokens(code)
    print("\n=== TOKEN RESPONSE ===")
    for k, v in data.items():
        print(f"{k}: {v}")

    print("\nIMPORTANT:")
    print("Save the following values in your environment/config:")
    print(f"SPOTIFY_CLIENT_ID={CLIENT_ID}")
    print(f"SPOTIFY_CLIENT_SECRET={CLIENT_SECRET}")
    print(f"SPOTIFY_REFRESH_TOKEN={data.get('refresh_token')!r}")


if __name__ == "__main__":
    main()


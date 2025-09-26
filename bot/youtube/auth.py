"""Interactive OAuth flow to create YouTube API user credentials.

Writes an authorized user credential file to ``data/creds.json`` (or to the
path set by ``GOOGLE_CREDS_PATH``). Requires a Google Cloud OAuth client file
at ``data/client_secrets.json`` (or ``GOOGLE_CLIENT_SECRETS``).

Usage:
  python -m bot.youtube.auth
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from google_auth_oauthlib.flow import InstalledAppFlow


SCOPES: Sequence[str] = [
    "https://www.googleapis.com/auth/youtube",
]


def _data_path(filename: str) -> Path:
    if filename == "creds.json" and (override := os.getenv("GOOGLE_CREDS_PATH")):
        return Path(override)
    base = Path(os.getenv("DATA_DIR", "data"))
    return base / filename


def main() -> None:
    creds_path = _data_path("creds.json")
    secrets_path = Path(os.getenv("GOOGLE_CLIENT_SECRETS", _data_path("client_secrets.json")))

    if not secrets_path.exists():
        raise SystemExit(
            f"Missing client secrets at {secrets_path}. Place your OAuth client JSON there.")

    creds_path.parent.mkdir(parents=True, exist_ok=True)

    # Google deprecated the out-of-band/console flow. Use a local loopback
    # server flow which is the recommended method for installed apps.
    print("Starting OAuth local-server flow for YouTube API…")
    print(
        "A URL will be shown — open it in a browser on this machine.",
    )

    flow = InstalledAppFlow.from_client_secrets_file(str(secrets_path), SCOPES)

    # Bind to localhost and a fixed port for easier Docker/compose setup.
    # If running inside Docker, either use host networking or map this port.
    port = int(os.getenv("OAUTH_PORT", "8080"))
    creds = flow.run_local_server(
        host="localhost",
        port=port,
        open_browser=False,
        authorization_prompt_message=
            "Please visit this URL to authorize: {url}",
    )

    creds_json = creds.to_json()
    creds_path.write_text(creds_json)
    print(f"Saved credentials to {creds_path}")


if __name__ == "__main__":
    main()

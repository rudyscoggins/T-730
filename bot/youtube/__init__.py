"""YouTube Data API helpers for playlist operations and auth.

This module expects OAuth credentials stored at ``data/creds.json`` by
``python -m bot.youtube.auth``. It exposes minimal helpers used by the bot.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scopes: read + manage YouTube (playlist insert requires write scope)
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
]


def _data_path(filename: str) -> Path:
    """Return path under the repo/container data directory.

    Respects optional env overrides:
    - GOOGLE_CREDS_PATH: full path to creds.json (overrides filename)
    - DATA_DIR: base directory for data files
    """

    # Explicit override for creds path
    if filename == "creds.json" and (override := os.getenv("GOOGLE_CREDS_PATH")):
        return Path(override)

    base = Path(os.getenv("DATA_DIR", "data"))
    return base / filename


def _load_credentials() -> Credentials:
    """Load user credentials from disk and refresh if needed.

    Raises a clear error if credentials are missing, instructing how to create
    them via the auth helper.
    """

    creds_path = _data_path("creds.json")
    if not creds_path.exists():
        raise RuntimeError(
            f"Missing credentials at {creds_path}. Run: python -m bot.youtube.auth",
        )

    creds = Credentials.from_authorized_user_file(str(creds_path), scopes=SCOPES)

    # Refresh if expired and refresh_token is present
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Persist the refreshed token
        creds_path.write_text(creds.to_json())

    return creds


def _get_service():
    """Build and return an authorized YouTube Data API client."""

    creds = _load_credentials()
    # Avoid discovery cache writes inside containers
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def video_exists(video_id: str, playlist_id: str) -> bool:
    """Return True if the given video_id is already in the playlist.

    Paginates through playlist items safely, only including pageToken when
    present to avoid API 400s from empty tokens.
    """

    service = _get_service()
    page_token: Optional[str] = None

    while True:
        params = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token

        try:
            res = (
                service.playlistItems()
                .list(**params)
                .execute()
            )
        except HttpError as e:
            raise RuntimeError(f"YouTube API error checking playlist: {e}") from e

        if any(
            it.get("contentDetails", {}).get("videoId") == video_id
            for it in res.get("items", [])
        ):
            return True

        page_token = res.get("nextPageToken")
        if not page_token:
            return False


def add_to_playlist(video_id: str, playlist_id: str) -> dict:
    """Insert the given video into the playlist. Returns the API response.

    Raises RuntimeError wrapping HttpError for clearer logging upstream.
    """

    service = _get_service()
    body = {
        "snippet": {
            "playlistId": playlist_id,
            "resourceId": {
                "kind": "youtube#video",
                "videoId": video_id,
            },
        }
    }
    try:
        return (
            service.playlistItems()
            .insert(part="snippet", body=body)
            .execute()
        )
    except HttpError as e:
        raise RuntimeError(f"YouTube API error adding video: {e}") from e


__all__ = [
    "video_exists",
    "add_to_playlist",
]

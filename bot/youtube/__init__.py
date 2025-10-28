"""YouTube Data API helpers for playlist operations and auth.

This module expects OAuth credentials stored at ``data/creds.json`` by
``python -m bot.youtube.auth``. It exposes minimal helpers used by the bot.
"""

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Optional, TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    from google.auth.transport.requests import Request as _Request
    from google.oauth2.credentials import Credentials as _Credentials
    from googleapiclient.discovery import build as _build
    from googleapiclient.errors import HttpError as _HttpError
    from google.auth.exceptions import RefreshError as _RefreshError

Request: Any | None = None
Credentials: Any | None = None
build: Any | None = None
HttpError: type[BaseException] = Exception
RefreshError: type[BaseException] = Exception
_GOOGLE_IMPORT_ERROR: Exception | None = None

# Scopes: read + manage YouTube (playlist insert requires write scope)
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
]


class CredentialsExpiredError(RuntimeError):
    """Raised when Google OAuth credentials are invalid/expired and require re-auth."""
    pass


class MissingGoogleDependenciesError(RuntimeError):
    """Raised when optional google-api-python-client dependencies are unavailable."""

    def __init__(self) -> None:
        super().__init__(
            "google-api-python-client dependencies are unavailable. Install"
            " bot/requirements.txt or set up the runtime image before running"
            " YouTube helpers.",
        )


def _ensure_google_dependencies() -> None:
    """Import google-api-python-client pieces lazily with friendly errors."""

    global Request, Credentials, build, HttpError, RefreshError, _GOOGLE_IMPORT_ERROR

    if build is not None and Credentials is not None and Request is not None:
        return

    if _GOOGLE_IMPORT_ERROR is not None:
        raise MissingGoogleDependenciesError() from _GOOGLE_IMPORT_ERROR

    try:
        from google.auth.transport.requests import Request as _Request  # type: ignore
        from google.oauth2.credentials import Credentials as _Credentials  # type: ignore
        from googleapiclient.discovery import build as _build  # type: ignore
        from googleapiclient.errors import HttpError as _HttpError  # type: ignore
        from google.auth.exceptions import RefreshError as _RefreshError  # type: ignore
    except Exception as exc:  # pragma: no cover - triggered when deps missing
        _GOOGLE_IMPORT_ERROR = exc
        raise MissingGoogleDependenciesError() from exc

    Request = _Request
    Credentials = _Credentials
    build = _build
    HttpError = _HttpError
    RefreshError = _RefreshError


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


def _reauth_hint() -> str:
    return (
        "Google credentials invalid or expired. Re-auth by running one of:\n"
        "- Locally: python -m bot.youtube.auth\n"
        "- Docker: docker compose run --rm -e OAUTH_FORCE=1 radiobot\n"
        "This opens a local URL to complete OAuth and regenerates data/creds.json."
    )


def _load_credentials() -> Credentials:
    """Load user credentials from disk and refresh if needed.

    Raises a clear error if credentials are missing, instructing how to create
    them via the auth helper.
    """

    _ensure_google_dependencies()
    assert Credentials is not None  # narrow type after lazy import

    creds_path = _data_path("creds.json")
    if not creds_path.exists():
        raise RuntimeError(
            f"Missing credentials at {creds_path}. Run: python -m bot.youtube.auth",
        )

    creds = Credentials.from_authorized_user_file(str(creds_path), scopes=SCOPES)

    # Refresh if expired and refresh_token is present
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise CredentialsExpiredError(_reauth_hint()) from e
        # Persist the refreshed token
        creds_path.write_text(creds.to_json())

    return creds


def _get_service():
    """Build and return an authorized YouTube Data API client."""

    _ensure_google_dependencies()
    assert build is not None  # for type checkers after lazy import
    creds = _load_credentials()
    # Avoid discovery cache writes inside containers
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def video_exists(video_id: str, playlist_id: str) -> bool:
    """Return True if the given video_id is already in the playlist.

    Paginates through playlist items safely, only including pageToken when
    present to avoid API 400s from empty tokens.
    """

    service = _get_service()
    playlist_items = service.playlistItems()
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
                playlist_items
                .list(**params)
                .execute()
            )
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            if status in (401, 403):
                raise CredentialsExpiredError(_reauth_hint()) from e
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
        status = getattr(getattr(e, "resp", None), "status", None)
        if status in (401, 403):
            raise CredentialsExpiredError(_reauth_hint()) from e
        raise RuntimeError(f"YouTube API error adding video: {e}") from e


def _parse_iso8601_duration(duration: str) -> int:
    """Parse a subset of ISO-8601 durations into total seconds."""

    pattern = re.compile(
        r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
    )
    match = pattern.match(duration)
    if not match:
        raise ValueError(f"Unsupported ISO-8601 duration: {duration}")

    parts = {k: int(v) if v else 0 for k, v in match.groupdict().items()}
    total_seconds = (
        parts["days"] * 24 * 3600
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )
    return total_seconds


def get_video_duration_seconds(video_id: str) -> int:
    """Return the duration of a video in seconds."""

    service = _get_service()
    try:
        response = (
            service.videos()
            .list(part="contentDetails", id=video_id)
            .execute()
        )
    except HttpError as e:
        status = getattr(getattr(e, "resp", None), "status", None)
        if status in (401, 403):
            raise CredentialsExpiredError(_reauth_hint()) from e
        raise RuntimeError(f"YouTube API error fetching video details: {e}") from e

    items = response.get("items", [])
    if not items:
        raise RuntimeError(f"Video {video_id} not found or has no metadata")

    duration = items[0].get("contentDetails", {}).get("duration")
    if not duration:
        raise RuntimeError(f"Video {video_id} missing duration metadata")

    try:
        return _parse_iso8601_duration(duration)
    except ValueError as exc:
        raise RuntimeError(
            f"Video {video_id} has unsupported duration format: {duration}"
        ) from exc


__all__ = [
    "video_exists",
    "add_to_playlist",
    "get_video_duration_seconds",
    "get_video_metadata",
    "CredentialsExpiredError",
    "MissingGoogleDependenciesError",
]


def get_video_metadata(video_id: str) -> dict:
    """Return basic metadata for a video.

    Includes: ``id``, ``title``, ``channel_title``, ``duration_seconds``,
    ``url``, and ``thumbnail_url`` (best-effort).
    """

    service = _get_service()
    try:
        response = (
            service.videos()
            .list(part="snippet,contentDetails", id=video_id)
            .execute()
        )
    except HttpError as e:
        status = getattr(getattr(e, "resp", None), "status", None)
        if status in (401, 403):
            raise CredentialsExpiredError(_reauth_hint()) from e
        raise RuntimeError(f"YouTube API error fetching video details: {e}") from e

    items = response.get("items", [])
    if not items:
        raise RuntimeError(f"Video {video_id} not found or has no metadata")

    item = items[0]
    snippet = item.get("snippet", {})
    content = item.get("contentDetails", {})

    duration_iso = content.get("duration") or "PT0S"
    duration_seconds = _parse_iso8601_duration(duration_iso)

    thumbs = (snippet.get("thumbnails") or {})
    thumb = (
        thumbs.get("maxres") or thumbs.get("standard") or
        thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}
    )

    return {
        "id": video_id,
        "title": snippet.get("title") or video_id,
        "channel_title": snippet.get("channelTitle") or "",
        "duration_seconds": duration_seconds,
        "url": f"https://youtu.be/{video_id}",
        "thumbnail_url": thumb.get("url"),
    }

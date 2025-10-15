"""Utilities to extract canonical YouTube video IDs from arbitrary text.

Handles common URL variants and strips extra parameters. Only returns valid
11-character IDs (A-Za-z0-9_-).
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def _clean_url_token(tok: str) -> str:
    """Strip trailing punctuation commonly stuck to URLs in chat."""
    return tok.rstrip(")],.>\n\r\t ")


def _extract_video_id_from_url(url: str) -> Optional[str]:
    p = urlparse(url)
    host = (p.hostname or "").lower()

    if not host:
        return None

    # Accept youtube.* and youtu.be
    if not (host.endswith("youtube.com") or host == "youtu.be" or host.endswith("youtu.be")):
        return None

    # youtu.be/<id>
    if host.endswith("youtu.be"):
        vid = p.path.lstrip("/").split("/")[0]
        return vid if _ID_RE.match(vid or "") else None

    # youtube.com/watch?v=<id>
    if p.path == "/watch":
        vid = parse_qs(p.query).get("v", [None])[0]
        return vid if _ID_RE.match(vid or "") else None

    # shorts, embed, v, live: first path segment after the prefix is the id
    for prefix in ("/shorts/", "/embed/", "/v/", "/live/"):
        if p.path.startswith(prefix):
            vid = p.path[len(prefix):].split("/")[0]
            return vid if _ID_RE.match(vid or "") else None

    # Fallback: any v param even on other paths
    vid = parse_qs(p.query).get("v", [None])[0]
    return vid if _ID_RE.match(vid or "") else None


def canonical_video_ids_from_text(text: str) -> List[str]:
    """Return ordered unique list of 11-char video IDs found in text.

    Parses URLs and extracts IDs from common YouTube URL variants. Accepts
    scheme-less inputs like ``youtube.com/watch?v=...`` as well.
    """

    # Find explicit http(s) URLs first
    candidates = list(re.findall(r"https?://[^\s<>]+", text))

    # Also accept bare youtube links without scheme (e.g., youtube.com/... or youtu.be/...)
    bare_matches = re.findall(r"(?:(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s<>]+)", text, flags=re.IGNORECASE)
    candidates.extend(bare_matches)

    seen = set()
    out: List[str] = []
    for cand in candidates:
        url = _clean_url_token(cand)
        # Normalize scheme-less links to https for parsing
        if "://" not in url:
            url = "https://" + url
        vid = _extract_video_id_from_url(url)
        if vid and vid not in seen:
            seen.add(vid)
            out.append(vid)
    return out


__all__ = [
    "canonical_video_ids_from_text",
]

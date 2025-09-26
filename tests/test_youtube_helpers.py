import types

import pytest


def make_service(pages=None, insert_behavior=None):
    """Create a fake YouTube API service with controllable behavior.

    pages: list of dicts to return from successive list().execute() calls.
    insert_behavior: either a dict to return, or an Exception to raise.
    """

    class PlaylistItemsResource:
        def __init__(self):
            self._page_index = 0

        def list(self, **params):
            class Exec:
                def __init__(self, outer):
                    self.outer = outer

                def execute(self):
                    i = self.outer._page_index
                    self.outer._page_index += 1
                    return (pages or [])[i]

            return Exec(self)

        def insert(self, part=None, body=None):
            class Exec:
                def execute(self_inner):
                    if isinstance(insert_behavior, Exception):
                        raise insert_behavior
                    return insert_behavior or {"ok": True, "body": body}

            return Exec()

    class Service:
        def playlistItems(self):
            return PlaylistItemsResource()

    return Service()


def test_video_exists_found(monkeypatch):
    from bot import youtube as yt

    # Page contains target id
    pages = [
        {
            "items": [
                {"contentDetails": {"videoId": "foo"}},
                {"contentDetails": {"videoId": "target"}},
            ]
        }
    ]

    monkeypatch.setattr(yt, "_get_service", lambda: make_service(pages=pages))
    assert yt.video_exists("target", "playlist123") is True


def test_video_exists_not_found_with_pagination(monkeypatch):
    from bot import youtube as yt

    pages = [
        {
            "items": [
                {"contentDetails": {"videoId": "a"}},
            ],
            "nextPageToken": "next",
        },
        {
            "items": [
                {"contentDetails": {"videoId": "b"}},
            ]
        },
    ]

    monkeypatch.setattr(yt, "_get_service", lambda: make_service(pages=pages))
    assert yt.video_exists("missing", "playlist123") is False


def test_add_to_playlist_success(monkeypatch):
    from bot import youtube as yt

    service = make_service(insert_behavior={"result": "ok"})
    monkeypatch.setattr(yt, "_get_service", lambda: service)
    res = yt.add_to_playlist("vid123", "pl123")
    assert res["result"] == "ok"


def test_add_to_playlist_wraps_http_error(monkeypatch):
    from bot import youtube as yt

    class FakeHttpError(Exception):
        pass

    # Replace the imported HttpError with our fake to avoid google deps.
    monkeypatch.setattr(yt, "HttpError", FakeHttpError)

    service = make_service(insert_behavior=FakeHttpError("boom"))
    monkeypatch.setattr(yt, "_get_service", lambda: service)

    with pytest.raises(RuntimeError) as ei:
        yt.add_to_playlist("vid123", "pl123")

    assert "YouTube API error adding video" in str(ei.value)


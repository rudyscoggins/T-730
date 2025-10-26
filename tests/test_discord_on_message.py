import asyncio

import pytest


class DummyAuthor:
    def __init__(self, is_bot=False):
        self.bot = is_bot


class DummyChannel:
    def __init__(self, id):
        self.id = id
        self.sent_messages = []

    async def send(self, content=None, *, embed=None):
        self.sent_messages.append({"content": content, "embed": embed})


class DummyMessage:
    def __init__(self, content, channel_id, is_bot=False):
        self.content = content
        self.channel = DummyChannel(channel_id)
        self.author = DummyAuthor(is_bot)
        self.reactions = []
        self.replies = []

    async def add_reaction(self, emoji):
        self.reactions.append(emoji)

    async def reply(self, content):
        self.replies.append(content)


@pytest.mark.asyncio
async def test_on_message_adds_two_videos(monkeypatch):
    from bot import main as m

    # Configure channel and keyword for the test
    m.CHANNEL_ID = 123
    m.KEYWORD = "730radio"
    m.PLAYLIST = "pl123"

    added = []

    def fake_video_exists(video_id, playlist_id):
        return False

    def fake_add_to_playlist(video_id, playlist_id):
        added.append((video_id, playlist_id))

    def fake_metadata(video_id):
        return {
            "id": video_id,
            "title": f"Video {video_id}",
            "channel_title": "Test Channel",
            "duration_seconds": 120,
            "url": f"https://youtu.be/{video_id}",
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/default.jpg",
        }

    monkeypatch.setattr(m, "get_video_metadata", fake_metadata)
    monkeypatch.setattr(m, "video_exists", fake_video_exists)
    monkeypatch.setattr(m, "add_to_playlist", fake_add_to_playlist)

    msg = DummyMessage(
        "730radio https://youtu.be/AAAAAAA1111 and https://www.youtube.com/watch?v=BBBBBBB2222",
        channel_id=123,
    )

    await m.on_message(msg)

    assert added == [("AAAAAAA1111", "pl123"), ("BBBBBBB2222", "pl123")]
    # Two success reactions
    assert msg.reactions.count("✅") == 2
    # Public messages should include the playlist link for visibility
    playlist_link = "https://youtube.com/playlist?list=pl123"
    contents = [entry["content"] for entry in msg.channel.sent_messages]
    assert len(contents) == 2
    assert all(playlist_link in content for content in contents)


@pytest.mark.asyncio
async def test_on_message_duplicate_and_success(monkeypatch):
    from bot import main as m

    m.CHANNEL_ID = 200
    m.KEYWORD = "730radio"
    m.PLAYLIST = "plX"

    def fake_video_exists(video_id, playlist_id):
        return video_id == "DUPLICATE12"

    added = []

    def fake_add_to_playlist(video_id, playlist_id):
        added.append(video_id)

    def fake_metadata(video_id):
        return {
            "id": video_id,
            "title": f"Video {video_id}",
            "channel_title": "Test Channel",
            "duration_seconds": 60,
            "url": f"https://youtu.be/{video_id}",
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/default.jpg",
        }

    monkeypatch.setattr(m, "get_video_metadata", fake_metadata)
    monkeypatch.setattr(m, "video_exists", fake_video_exists)
    monkeypatch.setattr(m, "add_to_playlist", fake_add_to_playlist)

    msg = DummyMessage(
        "some text 730radio https://youtu.be/DUPLICATE12 https://www.youtube.com/watch?v=NEWVIDEO3X4",
        channel_id=200,
    )

    await m.on_message(msg)

    assert added == ["NEWVIDEO3X4"]
    assert "🔁" in msg.reactions
    assert "✅" in msg.reactions


@pytest.mark.asyncio
async def test_on_message_ignores_wrong_channel_or_no_keyword(monkeypatch):
    from bot import main as m

    m.CHANNEL_ID = 999
    m.KEYWORD = "730radio"
    m.PLAYLIST = "plZ"

    called = {"exists": 0, "add": 0}

    def fake_video_exists(video_id, playlist_id):
        called["exists"] += 1
        return False

    def fake_add_to_playlist(video_id, playlist_id):
        called["add"] += 1

    metadata_calls = []

    def fake_metadata(video_id):
        metadata_calls.append(video_id)
        return {
            "id": video_id,
            "title": f"Video {video_id}",
            "channel_title": "Test Channel",
            "duration_seconds": 30,
            "url": f"https://youtu.be/{video_id}",
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/default.jpg",
        }

    monkeypatch.setattr(m, "get_video_metadata", fake_metadata)
    monkeypatch.setattr(m, "video_exists", fake_video_exists)
    monkeypatch.setattr(m, "add_to_playlist", fake_add_to_playlist)

    # Wrong channel
    msg1 = DummyMessage("730radio https://youtu.be/AAAAAAA1111", channel_id=100)
    await m.on_message(msg1)

    # No keyword
    msg2 = DummyMessage("just a link https://youtu.be/AAAAAAA1111", channel_id=999)
    await m.on_message(msg2)

    assert called == {"exists": 0, "add": 0}
    assert metadata_calls == []


@pytest.mark.asyncio
async def test_on_message_credentials_expired_prompts_reauth(monkeypatch):
    from bot import main as m
    from bot.youtube import CredentialsExpiredError

    m.CHANNEL_ID = 77
    m.KEYWORD = "730radio"
    m.PLAYLIST = "pl77"

    def raise_expired(video_id, playlist_id):
        raise CredentialsExpiredError("Please re-auth")

    monkeypatch.setattr(
        m,
        "get_video_metadata",
        lambda video_id: {
            "id": video_id,
            "title": f"Video {video_id}",
            "channel_title": "Test Channel",
            "duration_seconds": 120,
            "url": f"https://youtu.be/{video_id}",
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/default.jpg",
        },
    )
    monkeypatch.setattr(m, "video_exists", lambda v, p: False)
    monkeypatch.setattr(m, "add_to_playlist", raise_expired)

    msg = DummyMessage("730radio https://youtu.be/AAAAAAA1111", channel_id=77)
    await m.on_message(msg)

    assert "❌" in msg.reactions
    assert any("re-auth" in r.lower() or "auth" in r.lower() for r in msg.replies)


@pytest.mark.asyncio
async def test_on_message_rejects_long_video(monkeypatch):
    from bot import main as m

    m.CHANNEL_ID = 55
    m.KEYWORD = "730radio"
    m.PLAYLIST = "pl55"

    added = []

    monkeypatch.setattr(m, "video_exists", lambda v, p: False)
    monkeypatch.setattr(m, "add_to_playlist", lambda v, p: added.append(v))
    monkeypatch.setattr(
        m,
        "get_video_metadata",
        lambda video_id: {
            "id": video_id,
            "title": "Long Video",
            "channel_title": "Test Channel",
            "duration_seconds": 601,
            "url": f"https://youtu.be/{video_id}",
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/default.jpg",
        },
    )

    msg = DummyMessage("730radio https://youtu.be/TOOLONG9999", channel_id=55)
    await m.on_message(msg)

    assert added == []
    assert "⏱️" in msg.reactions
    assert any("10 minutes" in reply for reply in msg.replies)


@pytest.mark.asyncio
async def test_retry_helper_retries_then_succeeds(monkeypatch):
    from bot import main as m

    attempts = 0

    def flaky_call():
        nonlocal attempts
        attempts += 1
        if attempts < 4:
            raise RuntimeError("temporary hiccup")
        return "ok"

    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(m.asyncio, "sleep", fake_sleep)

    result = await m._call_with_retry(flaky_call, description="flaky call")

    assert result == "ok"
    assert attempts == 4
    assert sleeps[:3] == [5, 5, 5]


@pytest.mark.asyncio
async def test_retry_helper_eventually_stops(monkeypatch):
    from bot import main as m

    attempts = 0

    def always_fail():
        nonlocal attempts
        attempts += 1
        raise RuntimeError("still broken")

    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(m.asyncio, "sleep", fake_sleep)

    with pytest.raises(RuntimeError):
        await m._call_with_retry(always_fail, description="always fail")

    assert attempts == len(m._RETRY_WAIT_SECONDS)
    assert sleeps[-3:] == [60, 300, 600]

import asyncio

import pytest


class DummyAuthor:
    def __init__(self, is_bot=False):
        self.bot = is_bot


class DummyChannel:
    def __init__(self, id):
        self.id = id


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

    monkeypatch.setattr(m, "video_exists", fake_video_exists)
    monkeypatch.setattr(m, "add_to_playlist", fake_add_to_playlist)

    msg = DummyMessage(
        "some text 730radio https://youtu.be/DUPLICATE12 https://www.youtube.com/watch?v=NEWVIDEO34",
        channel_id=200,
    )

    await m.on_message(msg)

    assert added == ["NEWVIDEO34"]
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

    monkeypatch.setattr(m, "video_exists", fake_video_exists)
    monkeypatch.setattr(m, "add_to_playlist", fake_add_to_playlist)

    # Wrong channel
    msg1 = DummyMessage("730radio https://youtu.be/AAAAAAA1111", channel_id=100)
    await m.on_message(msg1)

    # No keyword
    msg2 = DummyMessage("just a link https://youtu.be/AAAAAAA1111", channel_id=999)
    await m.on_message(msg2)

    assert called == {"exists": 0, "add": 0}


import pytest


from bot import retry


@pytest.mark.asyncio
async def test_retry_helper_retries_then_succeeds(monkeypatch):

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

    monkeypatch.setattr(retry.asyncio, "sleep", fake_sleep)

    result = await retry.call_with_retry(flaky_call, description="flaky call")

    assert result == "ok"
    assert attempts == 4
    assert sleeps[:3] == [5, 5, 5]


@pytest.mark.asyncio
async def test_retry_helper_eventually_stops(monkeypatch):

    attempts = 0

    def always_fail():
        nonlocal attempts
        attempts += 1
        raise RuntimeError("still broken")

    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(retry.asyncio, "sleep", fake_sleep)

    with pytest.raises(RuntimeError):
        await retry.call_with_retry(always_fail, description="always fail")

    assert attempts == len(retry.RETRY_WAIT_SECONDS)
    assert sleeps[-3:] == [60, 300, 600]

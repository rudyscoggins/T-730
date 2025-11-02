from bot.config import _bool_from_env


def test_bool_from_env_truthy(monkeypatch):
    monkeypatch.setenv("FEATURE_FLAG", "true")

    assert _bool_from_env("FEATURE_FLAG", default=False) is True


def test_bool_from_env_falsey(monkeypatch):
    monkeypatch.setenv("FEATURE_FLAG", "OFF")

    assert _bool_from_env("FEATURE_FLAG", default=True) is False


def test_bool_from_env_invalid_logs_warning(monkeypatch, caplog):
    monkeypatch.setenv("FEATURE_FLAG", "maybe")

    with caplog.at_level("WARNING"):
        result = _bool_from_env("FEATURE_FLAG", default=True)

    assert result is True
    assert any("not a recognized boolean" in message for message in caplog.messages)

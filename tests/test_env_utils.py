def test_bool_from_env_truthy(monkeypatch):
    import bot.main as main

    monkeypatch.setenv("ENABLE_MESSAGE_SCANNING", "true")

    assert main._bool_from_env("ENABLE_MESSAGE_SCANNING", default=False) is True


def test_bool_from_env_falsey(monkeypatch):
    import bot.main as main

    monkeypatch.setenv("ENABLE_MESSAGE_SCANNING", "OFF")

    assert main._bool_from_env("ENABLE_MESSAGE_SCANNING", default=True) is False


def test_bool_from_env_invalid_logs_warning(monkeypatch, caplog):
    import bot.main as main

    monkeypatch.setenv("ENABLE_MESSAGE_SCANNING", "maybe")

    with caplog.at_level("WARNING"):
        result = main._bool_from_env("ENABLE_MESSAGE_SCANNING", default=True)

    assert result is True
    assert any("not a recognized boolean" in message for message in caplog.messages)

import pytest

from integrations.slack import SlackClient, SlackError


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_post_message_returns_ts_on_success(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResponse({"ok": True, "ts": "1234.5678"})

    monkeypatch.setattr("integrations.slack.requests.post", fake_post)

    client = SlackClient(bot_token="xoxb-fake", channel_id="C123")
    ts = client.post_message(text="hello", thread_ts="1111.0000")

    assert ts == "1234.5678"
    assert captured["json"]["channel"] == "C123"
    assert captured["json"]["thread_ts"] == "1111.0000"
    assert captured["headers"]["Authorization"] == "Bearer xoxb-fake"


def test_post_message_raises_slack_error_on_api_failure(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return _FakeResponse({"ok": False, "error": "channel_not_found"})

    monkeypatch.setattr("integrations.slack.requests.post", fake_post)

    client = SlackClient(bot_token="xoxb-fake", channel_id="C123")

    with pytest.raises(SlackError, match="channel_not_found"):
        client.post_message(text="hello")

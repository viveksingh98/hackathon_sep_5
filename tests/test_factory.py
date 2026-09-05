import pytest

from llm import factory


def test_create_client_anthropic_returns_anthropic_client(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(factory, "AnthropicClient", lambda api_key: sentinel)

    assert factory.create_client("anthropic", "key") is sentinel


def test_create_client_openai_returns_openai_client(monkeypatch):
    sentinel = object()
    monkeypatch.setattr(factory, "OpenAIClient", lambda api_key: sentinel)

    assert factory.create_client("openai", "key") is sentinel


def test_create_client_unknown_provider_raises_value_error():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        factory.create_client("unknown", "key")

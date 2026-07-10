"""Unit tests for the multi-provider LLM registry, focused on OpenRouter.

Follows the house style: plain pytest functions, hand-written fakes instead of
unittest.mock, plain asserts.
"""

import pytest

from novel_agent.tools import multi_provider_llm


class FakeOpenAI:
    """Records constructor args instead of talking to a real API."""

    last_instance = None

    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url
        self.api_key = api_key
        FakeOpenAI.last_instance = self


@pytest.fixture(autouse=True)
def reset_client_singletons(monkeypatch):
    """Ensure no cached client leaks between tests, and env vars start clean.

    The module also caches an OpenAI client and an Anthropic client; reset all
    of them for hygiene even though these tests only exercise OpenRouter.
    """
    monkeypatch.setattr(multi_provider_llm, "_openrouter_client", None)
    monkeypatch.setattr(multi_provider_llm, "_hosted_llm_client", None)
    monkeypatch.setattr(multi_provider_llm, "_openai_client", None)
    monkeypatch.setattr(multi_provider_llm, "_anthropic_client", None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    yield


def test_get_openrouter_client_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        multi_provider_llm._get_openrouter_client()


def test_get_openrouter_client_uses_correct_base_url_and_key(monkeypatch):
    monkeypatch.setattr(multi_provider_llm, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")

    client = multi_provider_llm._get_openrouter_client()

    assert isinstance(client, FakeOpenAI)
    assert client.base_url == "https://openrouter.ai/api/v1"
    assert client.api_key == "test-key-123"


def test_send_prompt_openrouter_raises_without_model(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_MODEL"):
        multi_provider_llm.send_prompt_openrouter("hello")


def test_send_prompt_openrouter_falls_back_to_env_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-3.7-sonnet")

    captured = {}

    class FakeMessage:
        content = "reply text"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(multi_provider_llm, "_get_openrouter_client", lambda: FakeClient())

    result = multi_provider_llm.send_prompt_openrouter("hello there")

    assert result == "reply text"
    assert captured["model"] == "anthropic/claude-3.7-sonnet"


def test_openrouter_in_supported_models():
    assert "openrouter" in multi_provider_llm.get_supported_models()


def test_send_prompt_routes_to_openrouter(monkeypatch):
    calls = {}

    def fake_send_prompt_openrouter(prompt, max_tokens=2000):
        calls["prompt"] = prompt
        calls["max_tokens"] = max_tokens
        return "openrouter says hi"

    monkeypatch.setitem(
        multi_provider_llm._model_config,
        "openrouter",
        lambda prompt, max_tokens: fake_send_prompt_openrouter(prompt, max_tokens),
    )

    result = multi_provider_llm.send_prompt("ping", model="openrouter", max_tokens=42)

    assert result == "openrouter says hi"
    assert calls == {"prompt": "ping", "max_tokens": 42}

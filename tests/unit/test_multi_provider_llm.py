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


# ---------------------------------------------------------------------------
# Per-request timeout plumbing (Phase 3 hardening, progress report 2026-07-12
# section 8.1: llm.timeout was inert on the whole api backend, so the SDK
# defaults governed a 22.4-minute hang). Each provider shape gets a fake that
# captures what reached the request.
# ---------------------------------------------------------------------------


class _OpenAIStyleClient:
    """OpenAI-shaped fake (openai / openrouter / hosted-llm): captures create kwargs."""

    def __init__(self, captured):
        class _Message:
            content = "reply"

        class _Choice:
            message = _Message()
            finish_reason = "stop"

        class _Response:
            choices = [_Choice()]

        class _Completions:
            def create(self, **kwargs):
                captured.update(kwargs)
                return _Response()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_openai_timeout_reaches_the_request(monkeypatch):
    captured = {}
    monkeypatch.setattr(multi_provider_llm, "_get_openai_client",
                        lambda: _OpenAIStyleClient(captured))
    text, reason = multi_provider_llm.send_prompt_openai_meta("hi", timeout=45)
    assert text == "reply" and reason == "stop"
    assert captured["timeout"] == 45


def test_openai_without_timeout_omits_the_kwarg(monkeypatch):
    # The convenience-function contract: timeout unset means the SDK default
    # governs, exactly the pre-timeout behavior.
    captured = {}
    monkeypatch.setattr(multi_provider_llm, "_get_openai_client",
                        lambda: _OpenAIStyleClient(captured))
    multi_provider_llm.send_prompt_openai_meta("hi")
    assert "timeout" not in captured


def test_openrouter_timeout_reaches_the_request(monkeypatch):
    captured = {}
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
    monkeypatch.setattr(multi_provider_llm, "_get_openrouter_client",
                        lambda: _OpenAIStyleClient(captured))
    multi_provider_llm.send_prompt_openrouter_meta("hi", timeout=120)
    assert captured["timeout"] == 120


def test_hosted_llm_timeout_reaches_the_request(monkeypatch):
    captured = {}
    monkeypatch.setenv("HOSTED_LLM_MODEL", "qwen")
    monkeypatch.setattr(multi_provider_llm, "_get_hosted_llm_client",
                        lambda: _OpenAIStyleClient(captured))
    multi_provider_llm.send_prompt_hosted_llm_meta("hi", timeout=60)
    assert captured["timeout"] == 60


def test_anthropic_timeout_reaches_the_request(monkeypatch):
    captured = {}

    class _Block:
        text = "claude says hi"

    class _Response:
        content = [_Block()]
        stop_reason = "end_turn"

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Response()

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(multi_provider_llm, "_get_anthropic_client", lambda: _Client())
    text, reason = multi_provider_llm.send_prompt_claude_meta("hi", timeout=90)
    assert text == "claude says hi" and reason == "stop"
    assert captured["timeout"] == 90


def test_gemini_timeout_rides_request_options(monkeypatch):
    captured = {}

    class _Response:
        text = "gemini says hi"
        candidates = []

    class _Model:
        def __init__(self, name):
            self.name = name

        def generate_content(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            return _Response()

    class _Types:
        @staticmethod
        def GenerationConfig(**kwargs):
            return kwargs

    class _FakeGenai:
        GenerativeModel = _Model
        types = _Types()

    monkeypatch.setattr(multi_provider_llm, "genai", _FakeGenai())
    monkeypatch.setattr(multi_provider_llm, "_gemini_configured", True)
    text, _ = multi_provider_llm.send_prompt_gemini_meta("hi", timeout=75)
    assert text == "gemini says hi"
    assert captured["request_options"] == {"timeout": 75}
    assert captured["prompt"] == "hi"


def test_client_rejecting_timeout_kwarg_degrades_gracefully(monkeypatch):
    # A create() with a closed signature (a fake, an older SDK) must not break
    # the call: the request is retried without the timeout kwargs.
    calls = {"count": 0}

    class _Message:
        content = "still works"

    class _Choice:
        message = _Message()
        finish_reason = "stop"

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, model, messages, max_tokens, temperature):
            calls["count"] += 1
            return _Response()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(multi_provider_llm, "_get_openai_client", lambda: _Client())
    text, _ = multi_provider_llm.send_prompt_openai_meta("hi", timeout=45)
    assert text == "still works"
    assert calls["count"] == 1  # the timeout attempt TypeErrored before any work


def test_interface_threads_instance_timeout_into_registry(monkeypatch):
    captured = {}

    def fake_entry(prompt, max_tokens, timeout=None):
        captured.update(prompt=prompt, max_tokens=max_tokens, timeout=timeout)
        return "hi"

    monkeypatch.setitem(multi_provider_llm._model_config, "openrouter", fake_entry)
    client = multi_provider_llm.MultiProviderInterface(model="openrouter", timeout=77)

    assert client.generate("ping", max_tokens=10) == "hi"
    assert captured["timeout"] == 77

    # A per-call timeout overrides the instance default.
    client.generate("ping", max_tokens=10, timeout=12)
    assert captured["timeout"] == 12


def test_interface_without_timeout_keeps_two_arg_registry_contract(monkeypatch):
    # Contract stability: a two-positional-arg registry entry (the shape older
    # tests and code monkeypatch in) keeps working for callers without a
    # timeout, and degrades gracefully when one is set.
    calls = {}

    def two_arg_entry(prompt, max_tokens):
        calls.update(prompt=prompt, max_tokens=max_tokens)
        return "legacy"

    monkeypatch.setitem(multi_provider_llm._model_config, "openrouter", two_arg_entry)

    no_timeout = multi_provider_llm.MultiProviderInterface(model="openrouter")
    assert no_timeout.generate("ping", max_tokens=5) == "legacy"

    with_timeout = multi_provider_llm.MultiProviderInterface(model="openrouter", timeout=30)
    assert with_timeout.generate("ping", max_tokens=5) == "legacy"
    assert calls == {"prompt": "ping", "max_tokens": 5}


def test_initialize_llm_wires_timeout_into_api_backend():
    from novel_agent.tools.llm_interface import initialize_llm

    client = initialize_llm(backend="api", model="openrouter", timeout=120)
    assert isinstance(client, multi_provider_llm.MultiProviderInterface)
    assert client.timeout == 120

    # Unset falls back to 300, same as the CLI backends' default_timeout.
    client = initialize_llm(backend="api", model="openrouter")
    assert client.timeout == 300


def test_clients_constructed_with_capped_sdk_retries(monkeypatch):
    class RetryAwareFakeOpenAI:
        def __init__(self, base_url=None, api_key=None, max_retries=None):
            self.base_url = base_url
            self.max_retries = max_retries

    monkeypatch.setattr(multi_provider_llm, "OpenAI", RetryAwareFakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")

    client = multi_provider_llm._get_openrouter_client()

    assert client.max_retries == multi_provider_llm.SDK_MAX_RETRIES
    assert multi_provider_llm.SDK_MAX_RETRIES == 1


def test_construct_client_drops_kwarg_for_closed_constructors():
    # The existing FakeOpenAI shape (no max_retries) must keep constructing:
    # the retry cap is a nicety, never a break.
    built = multi_provider_llm._construct_client(FakeOpenAI, api_key="k")
    assert isinstance(built, FakeOpenAI)

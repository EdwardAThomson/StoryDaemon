"""Unit tests for the finish-reason seam (Phase 3 segment plumbing).

Per-provider extraction from fake response shapes, the normalized
generate_with_meta path on MultiProviderInterface, and the guarantee that the
existing text-only generate()/send_prompt contract is unchanged.
"""

import pytest

from novel_agent.tools import multi_provider_llm
from novel_agent.tools.multi_provider_llm import (
    MultiProviderInterface,
    _anthropic_finish_reason,
    _gemini_finish_reason,
    _openai_finish_reason,
    send_prompt_meta,
)


@pytest.fixture(autouse=True)
def reset_client_singletons(monkeypatch):
    monkeypatch.setattr(multi_provider_llm, "_openrouter_client", None)
    monkeypatch.setattr(multi_provider_llm, "_venice_client", None)
    monkeypatch.setattr(multi_provider_llm, "_hosted_llm_client", None)
    monkeypatch.setattr(multi_provider_llm, "_openai_client", None)
    monkeypatch.setattr(multi_provider_llm, "_anthropic_client", None)
    yield


# ---- fake response shapes -----------------------------------------------------

class FakeOpenAIResponse:
    """OpenAI-shaped: choices[0].message.content + choices[0].finish_reason."""

    def __init__(self, text, finish_reason):
        class Message:
            content = text

        class Choice:
            message = Message()

        Choice.finish_reason = finish_reason
        self.choices = [Choice()]


class FakeAnthropicResponse:
    """Anthropic-shaped: content blocks + stop_reason."""

    def __init__(self, text, stop_reason):
        class Block:
            pass

        block = Block()
        block.text = text
        self.content = [block]
        self.stop_reason = stop_reason


class FakeGeminiCandidate:
    def __init__(self, finish_reason):
        self.finish_reason = finish_reason


class FakeGeminiResponse:
    def __init__(self, text, finish_reason):
        self.text = text
        self.candidates = [FakeGeminiCandidate(finish_reason)]


class FakeEnum:
    """Mimics a protobuf enum member with a .name attribute."""

    def __init__(self, name):
        self.name = name


# ---- per-provider extraction ----------------------------------------------------

def test_openai_finish_reason_extraction():
    assert _openai_finish_reason(FakeOpenAIResponse("x", "length")) == "length"
    assert _openai_finish_reason(FakeOpenAIResponse("x", "stop")) == "stop"
    assert _openai_finish_reason(FakeOpenAIResponse("x", None)) is None
    assert _openai_finish_reason(object()) is None  # malformed -> None, never raises


def test_anthropic_stop_reason_mapping():
    assert _anthropic_finish_reason(FakeAnthropicResponse("x", "max_tokens")) == "length"
    assert _anthropic_finish_reason(FakeAnthropicResponse("x", "end_turn")) == "stop"
    assert _anthropic_finish_reason(FakeAnthropicResponse("x", "stop_sequence")) == "stop"
    assert _anthropic_finish_reason(FakeAnthropicResponse("x", None)) is None
    assert _anthropic_finish_reason(object()) is None


def test_gemini_finish_reason_mapping():
    assert _gemini_finish_reason(FakeGeminiResponse("x", FakeEnum("MAX_TOKENS"))) == "length"
    assert _gemini_finish_reason(FakeGeminiResponse("x", FakeEnum("STOP"))) == "stop"
    # Raw protobuf ints: STOP == 1, MAX_TOKENS == 2.
    assert _gemini_finish_reason(FakeGeminiResponse("x", 2)) == "length"
    assert _gemini_finish_reason(FakeGeminiResponse("x", 1)) == "stop"
    assert _gemini_finish_reason(FakeGeminiResponse("x", None)) is None
    assert _gemini_finish_reason(object()) is None


# ---- provider meta functions over fake clients -----------------------------------

class _FakeChatClient:
    """OpenAI-compatible client returning a canned response."""

    def __init__(self, response):
        outer = self

        class Completions:
            def create(self, **kwargs):
                outer.kwargs = kwargs
                return response

        class Chat:
            completions = Completions()

        self.chat = Chat()


def test_openai_meta_and_text_contracts(monkeypatch):
    client = _FakeChatClient(FakeOpenAIResponse("prose", "length"))
    monkeypatch.setattr(multi_provider_llm, "_get_openai_client", lambda: client)

    assert multi_provider_llm.send_prompt_openai_meta("p") == ("prose", "length")
    # The existing text-only contract is unchanged.
    assert multi_provider_llm.send_prompt_openai("p") == "prose"


def test_openrouter_meta_is_openai_shaped(monkeypatch):
    client = _FakeChatClient(FakeOpenAIResponse("routed", "stop"))
    monkeypatch.setattr(multi_provider_llm, "_get_openrouter_client", lambda: client)
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")

    assert multi_provider_llm.send_prompt_openrouter_meta("p") == ("routed", "stop")
    assert multi_provider_llm.send_prompt_openrouter("p") == "routed"


def test_venice_meta_is_openai_shaped(monkeypatch):
    client = _FakeChatClient(FakeOpenAIResponse("unfiltered", "stop"))
    monkeypatch.setattr(multi_provider_llm, "_get_venice_client", lambda: client)
    monkeypatch.setenv("VENICE_MODEL", "venice-uncensored")

    assert multi_provider_llm.send_prompt_venice_meta("p") == ("unfiltered", "stop")
    assert multi_provider_llm.send_prompt_venice("p") == "unfiltered"
    # StoryDaemon's prompts must fully govern: Venice's own injected system
    # prompt is disabled on every request.
    vp = client.kwargs["extra_body"]["venice_parameters"]
    assert vp == {"include_venice_system_prompt": False}


def test_venice_requires_model(monkeypatch):
    monkeypatch.delenv("VENICE_MODEL", raising=False)
    with pytest.raises(ValueError):
        multi_provider_llm.send_prompt_venice_meta("p")


def test_hosted_llm_meta_is_openai_shaped(monkeypatch):
    client = _FakeChatClient(FakeOpenAIResponse("hosted", "length"))
    monkeypatch.setattr(multi_provider_llm, "_get_hosted_llm_client", lambda: client)
    monkeypatch.setenv("HOSTED_LLM_MODEL", "qwen")

    assert multi_provider_llm.send_prompt_hosted_llm_meta("p") == ("hosted", "length")
    assert multi_provider_llm.send_prompt_hosted_llm("p") == "hosted"


def test_claude_meta_maps_stop_reason(monkeypatch):
    captured = {}

    class FakeMessages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeAnthropicResponse("claude prose", "max_tokens")

    class FakeAnthropicClient:
        messages = FakeMessages()

    monkeypatch.setattr(
        multi_provider_llm, "_get_anthropic_client", lambda: FakeAnthropicClient()
    )
    assert multi_provider_llm.send_prompt_claude_meta("p") == ("claude prose", "length")
    assert multi_provider_llm.send_prompt_claude("p") == "claude prose"


# ---- registry and interface -------------------------------------------------------

def test_registries_share_keys():
    # The text registry is derived from the meta registry; they can never drift.
    assert set(multi_provider_llm._model_config) == set(multi_provider_llm._model_config_meta)


def test_send_prompt_meta_routes_and_returns_tuple(monkeypatch):
    monkeypatch.setitem(
        multi_provider_llm._model_config_meta,
        "openrouter",
        lambda prompt, max_tokens: (f"echo:{prompt}:{max_tokens}", "length"),
    )
    assert send_prompt_meta("hi", model="openrouter", max_tokens=7) == ("echo:hi:7", "length")


def test_generate_with_meta_on_interface(monkeypatch):
    monkeypatch.setitem(
        multi_provider_llm._model_config_meta,
        "openrouter",
        lambda prompt, max_tokens: ("text", "stop"),
    )
    client = MultiProviderInterface(model="openrouter")
    assert hasattr(client, "generate_with_meta")
    assert client.generate_with_meta("p", max_tokens=5) == ("text", "stop")


def test_generate_text_contract_unchanged(monkeypatch):
    # Existing callers of generate() still get a plain string.
    monkeypatch.setitem(
        multi_provider_llm._model_config,
        "openrouter",
        lambda prompt, max_tokens: "just text",
    )
    client = MultiProviderInterface(model="openrouter")
    assert client.generate("p", max_tokens=5) == "just text"


def test_send_prompt_meta_unsupported_model():
    with pytest.raises(ValueError, match="Unsupported model"):
        send_prompt_meta("p", model="not-a-model")

"""Unit tests for beat-response parsing: JSON extraction, the one-retry path, and
the hardened line fallback.

Regression coverage for the 2026-07-10 smoke-run bug: a single malformed JSON
response sent `_parse_beats_response` into the line fallback, which turned raw
JSON source lines into beat descriptions and poisoned the whole beat horizon.
"""

import tempfile
from pathlib import Path

import pytest

from novel_agent.plot.manager import PlotOutlineManager


class FakeConfig:
    """Minimal dot-notation config for testing."""

    def __init__(self, values=None):
        self._v = values or {}

    def get(self, key, default=None):
        return self._v.get(key, default)


class QueuedLLM:
    """Returns queued responses in order; records call count."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def generate(self, prompt, max_tokens=1000):
        self.calls += 1
        return self._responses.pop(0)


@pytest.fixture()
def manager(tmp_path):
    return PlotOutlineManager(tmp_path, llm_interface=None, config=FakeConfig())


# The live failure shape: fenced, and invalid because of a trailing comma.
MALFORMED_RESPONSE = """```json
{
  "beats": [
    {
      "description": "Mara finds the hidden ledger in the vault",
      "characters_involved": ["C000", "C001"],
      "tension_target": 5,
    }
  ]
}
```"""

VALID_RESPONSE = """{
  "beats": [
    {
      "description": "Mara finds the hidden ledger in the vault",
      "characters_involved": ["C000"],
      "tension_target": 5,
      "postconditions": [{"check": "entity_exists", "id": "C000"}]
    },
    {
      "description": "Joren confronts Mara at the dock",
      "tension_target": 6
    }
  ]
}"""

BULLET_RESPONSE = """- Mara finds the hidden ledger in the vault
- Joren confronts Mara at the dock over the missing funds
- The syndicate learns someone has been inside the vault
"""


# ---- JSON extraction ------------------------------------------------------------

def test_extract_returns_none_on_malformed_json(manager, capsys):
    assert manager._extract_beats_json(MALFORMED_RESPONSE) is None
    assert "JSON parse error" in capsys.readouterr().out


def test_extract_returns_none_when_no_json_present(manager):
    assert manager._extract_beats_json("Here are some ideas for the story.") is None


def test_extract_parses_valid_json_including_conditions(manager):
    beats = manager._extract_beats_json(VALID_RESPONSE)
    assert len(beats) == 2
    assert beats[0].description == "Mara finds the hidden ledger in the vault"
    assert beats[0].postconditions == [{"check": "entity_exists", "id": "C000"}]
    assert beats[1].tension_target == 6


# ---- Hardened line fallback ------------------------------------------------------

def test_fallback_rejects_json_fragment_lines(manager):
    # Every line of a malformed JSON reply is a fragment; none may become a beat.
    beats = manager._fallback_beats_from_lines(MALFORMED_RESPONSE)
    assert beats == []


def test_fallback_accepts_genuine_bullet_lines(manager):
    beats = manager._fallback_beats_from_lines(BULLET_RESPONSE)
    assert [b.description for b in beats] == [
        "Mara finds the hidden ledger in the vault",
        "Joren confronts Mara at the dock over the missing funds",
        "The syndicate learns someone has been inside the vault",
    ]


def test_fallback_rejects_fences_labels_and_fragments(manager):
    assert manager._looks_like_json_fragment("```json")
    assert manager._looks_like_json_fragment('"characters_involved": ["C000", "C001"],')
    assert manager._looks_like_json_fragment('"beats": [')
    assert manager._looks_like_json_fragment("BEAT 3:")
    assert manager._looks_like_json_fragment("Sure!")
    assert not manager._looks_like_json_fragment(
        "Mara finds the hidden ledger in the vault"
    )


def test_parse_beats_response_never_emits_fragment_beats(manager):
    # The wrapper (JSON first, fallback second) must yield zero beats, not garbage,
    # for a malformed JSON reply.
    assert manager._parse_beats_response(MALFORMED_RESPONSE) == []


# ---- One-retry path in generate_next_beats ---------------------------------------

def _wire_for_generation(monkeypatch, manager, llm):
    manager.llm = llm
    monkeypatch.setattr(
        manager, "_build_generation_context",
        lambda count: {"current_tick": 0, "planner_max_tokens": 500},
    )
    import novel_agent.agent.prompts as prompts
    monkeypatch.setattr(prompts, "format_plot_generation_prompt", lambda ctx: "PROMPT")


def test_generate_retries_once_on_malformed_json(monkeypatch, manager):
    llm = QueuedLLM([MALFORMED_RESPONSE, VALID_RESPONSE])
    _wire_for_generation(monkeypatch, manager, llm)

    beats = manager.generate_next_beats(count=2)

    assert llm.calls == 2
    assert [b.description for b in beats] == [
        "Mara finds the hidden ledger in the vault",
        "Joren confronts Mara at the dock",
    ]


def test_generate_does_not_retry_on_valid_json(monkeypatch, manager):
    llm = QueuedLLM([VALID_RESPONSE])
    _wire_for_generation(monkeypatch, manager, llm)

    beats = manager.generate_next_beats(count=2)

    assert llm.calls == 1
    assert len(beats) == 2


def test_generate_falls_back_to_empty_after_two_failures(monkeypatch, manager):
    llm = QueuedLLM([MALFORMED_RESPONSE, MALFORMED_RESPONSE])
    _wire_for_generation(monkeypatch, manager, llm)

    beats = manager.generate_next_beats(count=2)

    assert llm.calls == 2
    assert beats == []  # empty is safe; garbage beats are not


def test_generate_uses_line_fallback_for_bullet_responses(monkeypatch, manager):
    # A model that answers in bullets (no JSON at all, twice) still yields beats.
    llm = QueuedLLM([BULLET_RESPONSE, BULLET_RESPONSE])
    _wire_for_generation(monkeypatch, manager, llm)

    beats = manager.generate_next_beats(count=3)

    assert llm.calls == 2
    assert len(beats) == 3

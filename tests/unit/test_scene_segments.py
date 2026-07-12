"""Unit tests for the Phase 3 segment machinery (write-until-concluded plumbing).

Covers the pure logic in novel_agent/agent/segments.py: word-target mapping,
token-budget sizing, the completion heuristic's truth table, and the
trim-to-last-sentence fallback.
"""

from novel_agent.agent.segments import (
    CONTINUATION_WORD_TARGET,
    DEFAULT_WORD_TARGETS,
    continuation_token_budget,
    scene_incomplete,
    token_budget_for,
    trim_to_last_sentence,
    word_target_for,
)
from novel_agent.agent.writer_context import WriterContextBuilder
from novel_agent.configs.config import Config


# ---- word-target mapping ----------------------------------------------------

def test_word_targets_per_label():
    cfg = Config()
    assert word_target_for("brief", cfg) == 400
    assert word_target_for("short", cfg) == 800
    assert word_target_for("long", cfg) == 1400
    assert word_target_for("extended", cfg) == 2200


def test_word_target_default_when_no_scene_length():
    # No scene_length -> generation.default_scene_length ("long").
    assert word_target_for(None, Config()) == 1400
    assert word_target_for("", Config()) == 1400
    assert word_target_for("unknown-label", Config()) == 1400
    # Pure calls without a config still resolve.
    assert word_target_for(None, None) == DEFAULT_WORD_TARGETS["long"]


def test_word_target_label_is_case_insensitive():
    assert word_target_for("BRIEF", Config()) == 400
    assert word_target_for("  Extended  ", Config()) == 2200


def test_word_target_config_overrides():
    cfg = Config()
    cfg.set("generation.scene_word_targets", {"brief": 250})
    assert word_target_for("brief", cfg) == 250
    # Unspecified labels keep their defaults.
    assert word_target_for("short", cfg) == 800


def test_default_scene_length_override():
    cfg = Config()
    cfg.set("generation.default_scene_length", "short")
    assert word_target_for(None, cfg) == 800
    # A bad default falls back to the built-in "long".
    cfg.set("generation.default_scene_length", "nonsense")
    assert word_target_for(None, cfg) == 1400


# ---- token-budget sizing ----------------------------------------------------

def test_token_budget_sizing():
    cfg = Config()
    # 1400 words * 1.4 tokens/word * 2.0 headroom = 3920 (replaces the flat 3000)
    assert token_budget_for(1400, cfg) == 3920
    assert token_budget_for(400, cfg) == 1120
    assert token_budget_for(2200, cfg) == 6160


def test_token_budget_respects_config_knobs():
    cfg = Config()
    cfg.set("generation.tokens_per_word", 1.0)
    cfg.set("generation.scene_budget_multiplier", 1.5)
    assert token_budget_for(1400, cfg) == 2100


def test_token_budget_floor():
    assert token_budget_for(10, Config()) == 256
    assert token_budget_for("garbage", Config()) == token_budget_for(1400, Config())


def test_continuation_budget_sized_from_conclude_ask():
    # 300 words * 1.4 * 2.0 = 840: room to finish, not to ramble.
    assert CONTINUATION_WORD_TARGET == 300
    assert continuation_token_budget(Config()) == 840


# ---- completion heuristic truth table ---------------------------------------

def test_complete_endings():
    assert scene_incomplete("He closed the door.") is False
    assert scene_incomplete("Was it over?") is False
    assert scene_incomplete("It could not be!") is False
    assert scene_incomplete("The light faded…") is False
    assert scene_incomplete("The light faded...") is False


def test_complete_endings_with_quotes_and_brackets():
    assert scene_incomplete('She said, "Run!"') is False
    assert scene_incomplete("'We leave at dawn.'") is False
    assert scene_incomplete("(He wondered.)") is False
    assert scene_incomplete("[It was done.]") is False
    assert scene_incomplete("*The city slept.*") is False
    assert scene_incomplete('He whispered, "It ends tonight."') is False


def test_dialogue_final_lines():
    assert scene_incomplete('"Run," she said.') is False
    assert scene_incomplete('"We leave at dawn," Mira said, turning to the') is True
    # A quote opened but cut mid-line has no terminal before the cut.
    assert scene_incomplete('She whispered, "maybe') is True


def test_end_markers_count_as_complete():
    assert scene_incomplete("The evidence was public now.\n\nTHE END") is False
    assert scene_incomplete("She walked away.\n\n*END OF NOVEL*") is False
    assert scene_incomplete("The last door closed.\n\nFIN") is False
    # An all-caps line that is NOT a marker does not get a pass.
    assert scene_incomplete("He shouted AND THE") is True


def test_mid_sentence_and_mid_word_cuts():
    assert scene_incomplete("He walked to the") is True
    assert scene_incomplete("She turned and") is True
    assert scene_incomplete("The word was transfor") is True
    assert scene_incomplete("He paused,") is True
    assert scene_incomplete("He considered:") is True
    assert scene_incomplete("He waited; ") is True


def test_empty_text_is_not_incomplete():
    # Nothing to continue; the caller's empty-response handling governs.
    assert scene_incomplete("") is False
    assert scene_incomplete("   \n  ") is False


def test_trailing_whitespace_ignored():
    assert scene_incomplete("It was over.\n\n") is False
    assert scene_incomplete("It was almost\n\n") is True


# ---- trim-to-last-sentence fallback ------------------------------------------

def test_trim_cuts_back_to_last_terminal():
    text, changed = trim_to_last_sentence("He ran. She followed him into the")
    assert text == "He ran."
    assert changed is True


def test_trim_keeps_closing_quote():
    text, changed = trim_to_last_sentence('"Stop!" she cried. And then he')
    assert text == '"Stop!" she cried.'
    assert changed is True

    text, changed = trim_to_last_sentence('He said, "Go home." And')
    assert text == 'He said, "Go home."'
    assert changed is True


def test_trim_no_terminal_returns_unchanged():
    text, changed = trim_to_last_sentence("no terminal anywhere at all")
    assert text == "no terminal anywhere at all"
    assert changed is False


def test_trim_complete_text_unchanged():
    text, changed = trim_to_last_sentence("It ends here.")
    assert text == "It ends here."
    assert changed is False


def test_trim_empty():
    assert trim_to_last_sentence("") == ("", False)


# ---- writer-context length guidance (states the target explicitly) -----------

def _builder(cfg=None):
    b = WriterContextBuilder.__new__(WriterContextBuilder)  # config is all it needs here
    b.config = cfg or Config()
    return b


def test_length_guidance_states_word_target():
    guidance, target = _builder()._get_length_guidance(
        {"metadata": {"scene_length": "brief"}}
    )
    assert target == 400
    assert "roughly 400 words" in guidance
    assert "complete ending" in guidance


def test_length_guidance_default_without_scene_length():
    # No scene_length in the plan -> default "long" target, still stated.
    guidance, target = _builder()._get_length_guidance({})
    assert target == 1400
    assert "roughly 1400 words" in guidance


def test_length_guidance_tolerates_bad_metadata():
    guidance, target = _builder()._get_length_guidance({"metadata": {"scene_length": 7}})
    assert target == 1400
    assert "roughly 1400 words" in guidance

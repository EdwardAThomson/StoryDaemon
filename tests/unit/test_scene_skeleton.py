"""Slice 4 scene skeletons: generator, prompt section, marker stripping,
schema, config gate, and the writer-side wiring (no LLM calls)."""

import pytest

from novel_agent.agent import scene_skeleton as sk
from novel_agent.agent.schemas import validate_plan
from novel_agent.agent.writer import SceneWriter
from novel_agent.configs.config import Config

LABELS = set(sk.MODE_GUIDE)


# ---- generator ---------------------------------------------------------------

def test_generator_deterministic_and_valid():
    a = sk.generate_skeleton(1400, seed=7)
    b = sk.generate_skeleton(1400, seed=7)
    assert a == b
    assert all(m in LABELS for m in a)


def test_generator_length_clamps():
    assert len(sk.generate_skeleton(50, seed=1)) == sk.MIN_BLOCKS
    assert len(sk.generate_skeleton(100000, seed=1)) == sk.MAX_BLOCKS


def test_generator_defaults_to_the_default_word_target():
    assert (sk.generate_skeleton(None, seed=1)
            == sk.generate_skeleton(sk.DEFAULT_WORD_TARGET, seed=1))


# ---- mode-aware sizing -------------------------------------------------------

def test_measured_paragraph_lengths_differ_by_mode():
    w = sk.mode_word_stats()
    # The whole point: a dialogue paragraph is a speech turn, a lore
    # paragraph is a block of exposition. One flat figure cannot serve both.
    assert w["DIALOGUE"]["mean"] < w["ACTION"]["mean"] < w["LORE"]["mean"]
    assert w["TRANSITION"]["mean"] < w["DIALOGUE"]["mean"]


def test_skeletons_are_sized_by_word_budget_not_block_count():
    for target in (400, 800, 1400, 2200):
        got = [sk.expected_words(sk.generate_skeleton(target, seed=s))
               for s in range(40)]
        mean = sum(got) / len(got)
        assert abs(mean - target) / target < 0.15, (target, mean)


def test_dialogue_heavy_plans_buy_more_paragraphs_than_exposition():
    # Same word target, different mix: at measured lengths a dialogue scene
    # needs far more paragraphs than an exposition one. The old flat divisor
    # gave both the same count, which a dialogue scene could only reach by
    # overfilling its paragraphs.
    dialogue = sk.expected_words(["DIALOGUE"] * 20)
    lore = sk.expected_words(["LORE"] * 20)
    assert dialogue < lore / 2


def test_tension_reweights_toward_action():
    # Pooled over many seeds (deterministic), high-tension skeletons carry
    # more ACTION than calm ones: the measured band shift, applied.
    def action_share(tension):
        blocks = [m for s in range(60)
                  for m in sk.generate_skeleton(1400, tension=tension, seed=s)]
        return blocks.count("ACTION") / len(blocks)

    assert action_share(8) > action_share(2)


# ---- prompt section ----------------------------------------------------------

def test_prompt_section_carries_plan_and_gate_b_rules():
    s = sk.skeleton_prompt_section(["SETTING", "DIALOGUE"])
    assert "1. SETTING" in s
    assert "2. DIALOGUE" in s
    assert "square brackets" in s          # marker protocol
    assert "Do not compress" in s          # no-compression rule
    assert "One plan item = one paragraph" in s


def test_prompt_gives_each_item_its_own_measured_word_range():
    s = sk.skeleton_prompt_section(["LORE", "DIALOGUE"])
    lo_lore, hi_lore = sk._word_range("LORE")
    lo_dlg, hi_dlg = sk._word_range("DIALOGUE")
    assert f"1. LORE, {lo_lore}-{hi_lore} words" in s
    assert f"2. DIALOGUE, {lo_dlg}-{hi_dlg} words" in s
    # A dialogue turn is short; the old flat rule demanded 60-130 of every mode.
    assert hi_dlg < lo_lore + hi_lore
    assert "60-130 words" not in s


def test_prompt_declares_one_speech_turn_per_dialogue_item():
    flat = " ".join(
        sk.skeleton_prompt_section(["DIALOGUE"] * 3).split())  # unwrap
    assert "each item is ONE character speaking" in flat
    assert "Never pack several exchanges into a single paragraph." in flat
    # The clause that caused the defect must be gone.
    assert "may hold several exchanges" not in flat


def test_prompt_states_the_plans_own_word_target():
    plan = ["DIALOGUE"] * 8
    s = sk.skeleton_prompt_section(plan)
    assert f"roughly {round(sk.expected_words(plan))} words" in s


# ---- marker stripping --------------------------------------------------------

def test_strip_markers():
    text = '[1] The bay lay grey.\n\n[2] "Hold course," he said.'
    clean, stats = sk.strip_skeleton_markers(text)
    assert "[1]" not in clean and "[2]" not in clean
    assert clean.startswith("The bay lay grey.")
    assert stats == {"markers_found": 2, "markers_distinct": 2}


def test_strip_markers_passthrough_without_markers():
    clean, stats = sk.strip_skeleton_markers("No markers here.")
    assert clean == "No markers here."
    assert stats["markers_found"] == 0


def test_strip_markers_counts_duplicates_distinctly():
    clean, stats = sk.strip_skeleton_markers("[1] A.\n\n[1] B.\n\n[3] C.")
    assert stats == {"markers_found": 3, "markers_distinct": 2}


# ---- plan schema -------------------------------------------------------------

def _plan(**extra):
    return dict({"rationale": "r", "actions": [],
                 "scene_intention": "s"}, **extra)


def test_plan_schema_accepts_skeleton():
    validate_plan(_plan(scene_skeleton=["SETTING", "DIALOGUE", "ACTION"]))
    validate_plan(_plan(scene_skeleton=None))


def test_plan_schema_rejects_unknown_block_type():
    with pytest.raises(ValueError):
        validate_plan(_plan(scene_skeleton=["BOGUS"]))


# ---- config gate -------------------------------------------------------------

def test_flag_defaults_off():
    assert Config().get('generation.enable_scene_skeleton') is False


# ---- writer wiring (pattern from test_writer_segments) ------------------------

class FakeMetaLLM:
    """Scripted (text, finish_reason) segments; records prompts."""

    def __init__(self, segments):
        self.segments = list(segments)
        self.prompts = []
        self.max_tokens = []

    def generate_with_meta(self, prompt, max_tokens=2000, timeout=120):
        self.prompts.append(prompt)
        self.max_tokens.append(max_tokens)
        return self.segments.pop(0)


def _ctx(**overrides):
    ctx = {
        "novel_name": "N",
        "current_tick": 3,
        "recent_context": "(none)",
        "scene_intention": "Mira confronts the archivist",
        "key_change": "the ledger changes hands",
        "progress_milestone": "",
        "plot_beat_section": "",
        "arc_pressure_section": "",
        "scene_mode": "",
        "palette_shift": "",
        "transition_path": "",
        "dialogue_targets": "",
        "tool_results_summary": "(none)",
        "pov_character_id": "C000",
        "pov_character_name": "Mira",
        "pov_character_details": "Mira, an archivist",
        "location_id": "L000",
        "location_details": "The archive",
        "existing_characters": "- Mira (POV)",
        "approved_new_names": "- Tobin Vale",
        "scene_length_guidance": "\n\n**Length Guidance:** Write roughly 1400 words.",
        "word_target": 1400,
    }
    ctx.update(overrides)
    return ctx


def test_writer_strips_markers_and_records_compliance():
    llm = FakeMetaLLM(
        [('[1] "Hold course," she said firmly.\n\n[2] He left the deck.',
          "stop")])
    ctx = _ctx(scene_skeleton=["DIALOGUE", "ACTION"])
    scene = SceneWriter(llm, Config()).write_scene(ctx)
    assert "[1]" not in scene["text"] and "[2]" not in scene["text"]
    assert scene["skeleton_compliance"] == {
        "plan_blocks": 2, "markers_found": 2,
        "markers_distinct": 2, "compliant": True,
    }
    assert scene["word_count"] == len(scene["text"].split())


def test_writer_records_noncompliance_when_markers_missing():
    llm = FakeMetaLLM([("Plain prose without any markers at all.", "stop")])
    ctx = _ctx(scene_skeleton=["DIALOGUE", "ACTION", "SETTING"])
    scene = SceneWriter(llm, Config()).write_scene(ctx)
    assert scene["skeleton_compliance"]["compliant"] is False
    assert scene["skeleton_compliance"]["markers_found"] == 0
    assert scene["text"] == "Plain prose without any markers at all."


def test_writer_unchanged_without_skeleton():
    llm = FakeMetaLLM([("The scene unfolds slowly.\n\nIt ends here.", "stop")])
    scene = SceneWriter(llm, Config()).write_scene(_ctx())
    assert "skeleton_compliance" not in scene

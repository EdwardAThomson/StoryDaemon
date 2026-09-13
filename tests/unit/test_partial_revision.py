"""Selective paragraph revision (DSL Slice 5 repair pass).

Rewriting a whole scene to move its tension destroyed the paragraph plan that
produced it (live, 2026-09-12: 64 -> 36 and 57 -> 28 paragraphs). Revising only
the tension-carrying paragraphs keeps everything else byte-identical. No LLM
calls anywhere here.
"""
import pytest

from novel_agent.agent import partial_revision as pr
from novel_agent.agent.scene_skeleton import generate_skeleton
from novel_agent.agent.writer import SceneWriter
from novel_agent.configs.config import Config


# ---- which paragraphs carry the heat -----------------------------------------

def test_levers_are_read_from_the_corpus_not_guessed():
    ratios = pr.heat_ratios()
    # Measured: ACTION rises with tension, LORE and INTERIORITY fall.
    assert ratios["ACTION"] > 1.2
    assert ratios["LORE"] < 0.8
    assert ratios["INTERIORITY"] < 1.0
    assert "ACTION" in pr.heat_modes()
    assert "LORE" not in pr.heat_modes()


def test_tiny_modes_are_not_levers():
    # TRANSITION has the highest ratio in the corpus but is ~1% of blocks and
    # ten words long, so it is noise rather than where tension lives.
    assert "TRANSITION" not in pr.heat_ratios()


def test_selection_never_rewrites_most_of_a_scene():
    for n in (3, 10, 30, 60):
        sk = ["ACTION"] * n
        sel = pr.select_blocks(sk, max_blocks=99)
        assert 0 < len(sel) <= max(1, int(n * pr.MAX_SCENE_FRACTION))


def test_selection_respects_the_cap_and_spreads_out():
    sk = generate_skeleton(3150, seed=0)
    sel = pr.select_blocks(sk, max_blocks=8)
    assert len(sel) <= 8
    assert sel == sorted(set(sel))
    assert all(sk[i - 1] in pr.heat_modes() for i in sel)
    # spread, not a contiguous clump at one end of the scene
    assert max(sel) - min(sel) > len(sk) // 3


def test_selection_empty_when_the_plan_has_no_levers():
    assert pr.select_blocks(["LORE", "INTERIORITY", "DIALOGUE"]) == []
    assert pr.select_blocks([]) == []


# ---- parsing and splicing ----------------------------------------------------

def test_parse_addressed_paragraphs():
    got = pr.parse_revised_blocks("[3] Revised three.\n\n[7] Revised seven.")
    assert got == {3: "Revised three.", 7: "Revised seven."}


def test_parse_rejects_an_unmarked_response():
    # Splicing blind would put the revision in the wrong place.
    assert pr.parse_revised_blocks("Just some prose with no markers.") == {}
    assert pr.parse_revised_blocks(None) == {}
    assert pr.parse_revised_blocks("") == {}


def test_splice_leaves_untouched_paragraphs_byte_identical():
    paras = ["one", "two", "three", "four"]
    out, applied = pr.splice(paras, {2: "TWO revised"})
    assert out == ["one", "TWO revised", "three", "four"]
    assert applied == 1
    assert out[0] is paras[0] and out[2] is paras[2]


def test_splice_ignores_out_of_range_indices():
    # A revision inventing paragraph 99 must not lengthen the scene.
    out, applied = pr.splice(["a", "b"], {99: "ghost", 0: "ghost", 1: "A"})
    assert out == ["A", "b"] and applied == 1


def test_splice_counts_only_real_changes():
    out, applied = pr.splice(["a", "b"], {1: "a"})
    assert applied == 0 and out == ["a", "b"]


# ---- the writer path ---------------------------------------------------------

class FakeLLM:
    def __init__(self, response):
        self.response = response
        self.prompts = []

    def generate_with_meta(self, prompt, max_tokens=2000, timeout=120):
        self.prompts.append(prompt)
        return self.response, "stop"


SCENE = "First para.\n\nSecond para.\n\nThird para.\n\nFourth para."
SK = ["DIALOGUE", "ACTION", "DIALOGUE", "ACTION"]


def test_revision_preserves_structure_and_length():
    llm = FakeLLM("[2] Second, calmer.\n\n[4] Fourth, calmer.")
    text, meta = SceneWriter(llm, Config()).revise_blocks_for_tension(
        SCENE, SK, [2, 4], target_level=3, current_level=8)
    assert text.split("\n\n") == ["First para.", "Second, calmer.",
                                  "Third para.", "Fourth, calmer."]
    assert meta == {"applied": 2, "requested": 2}


def test_revision_prompt_addresses_only_the_selected_paragraphs():
    llm = FakeLLM("[2] Revised.")
    SceneWriter(llm, Config()).revise_blocks_for_tension(
        SCENE, SK, [2], target_level=3, current_level=8)
    p = llm.prompts[0]
    assert "[1] First para." in p and "[4] Fourth para." in p   # full context
    assert "Rewrite ONLY these paragraphs" in p
    assert "\n[2] ACTION" in p                                  # the target line
    assert "events of the scene do not change" in p


def test_unaddressed_response_changes_nothing():
    llm = FakeLLM("Here is a nicer version of the whole scene.")
    text, meta = SceneWriter(llm, Config()).revise_blocks_for_tension(
        SCENE, SK, [2], target_level=3, current_level=8)
    assert text == ""
    assert meta["applied"] == 0


def test_a_revision_of_an_unselected_paragraph_is_discarded():
    # The model answering about paragraph 3 when asked for 2 must not apply.
    llm = FakeLLM("[3] Sneaky rewrite.")
    text, meta = SceneWriter(llm, Config()).revise_blocks_for_tension(
        SCENE, SK, [2], target_level=3, current_level=8)
    assert text == "" and meta["applied"] == 0


def test_indices_outside_the_scene_are_dropped():
    llm = FakeLLM("[2] Revised.")
    text, _ = SceneWriter(llm, Config()).revise_blocks_for_tension(
        SCENE, SK, [2, 99], target_level=3, current_level=8)
    assert "Revised." in text and len(text.split("\n\n")) == 4

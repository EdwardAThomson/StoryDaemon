"""Unit tests for the write-until-concluded scene loop (Phase 3 segment plumbing).

Scripted fake LLMs drive SceneWriter.write_scene through its segment loop:
completes-first-try, length-cut-then-concluded, never-concludes (cap, then trim
and flag), heuristic-only CLI degradation, and the graceful fallback when a
continuation call fails. Also covers the revise_for_tension completion
guarantee and the agent adopting a trim-flagged revision.
"""

from novel_agent.agent.agent import StoryAgent
from novel_agent.agent.writer import SceneWriter
from novel_agent.configs.config import Config


class FakeMetaLLM:
    """Scripted (text, finish_reason) segments; records prompts and budgets."""

    def __init__(self, segments):
        self.segments = list(segments)
        self.prompts = []
        self.max_tokens = []

    def generate_with_meta(self, prompt, max_tokens=2000, timeout=120):
        self.prompts.append(prompt)
        self.max_tokens.append(max_tokens)
        if not self.segments:
            raise RuntimeError("script exhausted")
        return self.segments.pop(0)


class FakePlainLLM:
    """A CLI-style backend: generate only, no metadata."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []

    def generate(self, prompt, max_tokens=2000):
        self.prompts.append(prompt)
        return self.outputs.pop(0)


def _ctx(**overrides):
    """A minimal but complete writer context (renders the real template)."""
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


# ---- the loop ---------------------------------------------------------------

def test_completes_first_try_single_segment():
    llm = FakeMetaLLM([("The scene unfolds slowly.\n\nIt ends here.", "stop")])
    scene = SceneWriter(llm, Config()).write_scene(_ctx())
    assert scene["segments_used"] == 1
    assert scene["concluded_naturally"] is True
    assert scene["trimmed"] is False
    assert scene["text"].endswith("It ends here.")
    # The first request's ceiling is sized from the word target, not a flat 3000:
    # 1400 words * 1.4 tokens/word * 2.0 headroom.
    assert llm.max_tokens[0] == 3920


def test_ceiling_follows_context_word_target():
    llm = FakeMetaLLM([("Done.", "stop")])
    SceneWriter(llm, Config()).write_scene(_ctx(word_target=800))
    assert llm.max_tokens[0] == 2240  # 800 * 1.4 * 2.0


def test_length_cut_then_concluded_two_segments():
    first = "Mira pressed on through the stacks and reached for the"
    second = "ledger. She took it, and the matter was settled."
    llm = FakeMetaLLM([(first, "length"), (second, "stop")])
    scene = SceneWriter(llm, Config()).write_scene(_ctx())

    assert scene["segments_used"] == 2
    assert scene["concluded_naturally"] is True
    assert scene["trimmed"] is False
    # Mid-sentence stop joins inline: the sentence is finished across segments.
    assert "reached for the ledger." in scene["text"]
    assert scene["text"].endswith("the matter was settled.")

    # The continuation request carried the FULL scene so far plus the firm
    # conclude instruction (never an open-ended "continue").
    cont_prompt = llm.prompts[1]
    assert first in cont_prompt
    assert "CONCLUDE the scene within roughly 200-300 words" in cont_prompt
    assert "pick up exactly where it stops" in cont_prompt
    # And a per-segment budget sized for concluding, not for a fresh scene.
    assert llm.max_tokens[1] == 840


def test_never_concludes_hits_cap_then_trims_and_flags():
    llm = FakeMetaLLM([
        ("Mira ran down the corridor and the", "length"),
        ("lights failed around her while the", "length"),
        ("alarm sounded. She kept running toward the", "length"),
    ])
    scene = SceneWriter(llm, Config()).write_scene(_ctx())

    assert scene["segments_used"] == 3  # generation.scene_max_segments default
    assert scene["trimmed"] is True
    assert scene["concluded_naturally"] is False
    # Trimmed cleanly to the last complete sentence.
    assert scene["text"].endswith("alarm sounded.")
    assert len(llm.prompts) == 3  # cap respected: no fourth request


def test_segment_cap_configurable():
    cfg = Config()
    cfg.set("generation.scene_max_segments", 2)
    llm = FakeMetaLLM([
        ("She reached for the", "length"),
        ("handle and pulled at the", "length"),
    ])
    scene = SceneWriter(llm, cfg).write_scene(_ctx())
    assert scene["segments_used"] == 2
    assert scene["trimmed"] is True
    assert len(llm.prompts) == 2


def test_plain_generate_backend_degrades_to_heuristic():
    # No generate_with_meta (CLI backends): complete text, one segment, no meta calls.
    llm = FakePlainLLM(["A whole scene that ends properly."])
    scene = SceneWriter(llm, Config()).write_scene(_ctx())
    assert scene["segments_used"] == 1
    assert scene["concluded_naturally"] is True
    assert scene["trimmed"] is False


def test_plain_backend_incomplete_text_still_continues():
    # The heuristic alone (finish_reason None) drives the continuation.
    llm = FakePlainLLM([
        "Mira opened the drawer and found the",
        "ledger she had been hunting for weeks. It was over.",
    ])
    scene = SceneWriter(llm, Config()).write_scene(_ctx())
    assert scene["segments_used"] == 2
    assert scene["trimmed"] is False
    assert scene["text"].endswith("It was over.")


def test_continuation_failure_falls_back_to_trimmed_single_shot():
    # Script exhausts after the first segment: the loop's failure is swallowed
    # and the single-shot result ships trimmed and flagged, never truncated.
    llm = FakeMetaLLM([("She spoke first. Then he turned toward the", "length")])
    scene = SceneWriter(llm, Config()).write_scene(_ctx())
    assert scene["segments_used"] == 1
    assert scene["trimmed"] is True
    assert scene["text"].endswith("She spoke first.")


def test_writer_prompt_states_word_target():
    llm = FakeMetaLLM([("Done.", "stop")])
    SceneWriter(llm, Config()).write_scene(_ctx())
    assert "Write roughly 1400 words" in llm.prompts[0]


# ---- revise_for_tension completion guarantee ---------------------------------

def test_revise_with_meta_trims_and_flags_truncated_revision():
    llm = FakeMetaLLM([("She breathed. The storm passed and then the", "length")])
    text, meta = SceneWriter(llm, Config()).revise_for_tension_with_meta(
        "Original tense scene text.", target_level=4, current_level=8
    )
    assert text == "She breathed."
    assert meta["trimmed"] is True


def test_revise_with_meta_complete_revision_not_flagged():
    llm = FakeMetaLLM([("# Title\n\nCalm now.", "stop")])
    text, meta = SceneWriter(llm, Config()).revise_for_tension_with_meta(
        "Original.", target_level=4, current_level=8
    )
    assert text == "Calm now."
    assert meta["trimmed"] is False


def test_revise_budget_sized_from_source_scene():
    # A 2000-word source gets a 2000-word budget (2.8x in tokens), not a flat wall.
    llm = FakeMetaLLM([("Calm now.", "stop")])
    source = " ".join(["word"] * 2000) + "."
    SceneWriter(llm, Config()).revise_for_tension_with_meta(source, 4, 8)
    assert llm.max_tokens[0] == 5600  # 2000 * 1.4 * 2.0


def test_revise_text_only_contract_unchanged():
    llm = FakeMetaLLM([("Calm now.", "stop")])
    out = SceneWriter(llm, Config()).revise_for_tension("Original.", 4, 8)
    assert out == "Calm now."


# ---- agent adoption of a trim-flagged revision --------------------------------

class FakeMetaWriter:
    def __init__(self, revised, trimmed):
        self.revised = revised
        self.trimmed = trimmed

    def revise_for_tension_with_meta(self, text, target, current,
                                     writer_context=None, prev_tension=None):
        return self.revised, {"trimmed": self.trimmed}


class FakeTension:
    def __init__(self, score):
        self.score = score

    def evaluate_tension(self, text, ctx):
        return {"enabled": True, "tension_level": self.score, "tension_category": "x"}


class FakeMemory:
    def list_scenes(self):
        return []


def _agent(writer, tension):
    cfg = Config()
    cfg.set("coherence.arc_phase_mandate", False)  # exercise the rewrite mechanics
    a = StoryAgent.__new__(StoryAgent)
    a.config = cfg
    a.writer = writer
    a.tension_evaluator = tension
    a.memory = FakeMemory()
    return a


def test_adopted_trimmed_revision_carries_the_flag():
    agent = _agent(FakeMetaWriter("calmer prose", trimmed=True), FakeTension(4))
    scene, tr = agent._maybe_rewrite_for_tension(
        {"text": "tense", "word_count": 1, "segments_used": 1,
         "concluded_naturally": True, "trimmed": False},
        {"enabled": True, "tension_level": 8, "tension_category": "high"}, 0, {},
    )
    assert scene["text"] == "calmer prose"
    assert scene["trimmed"] is True  # the committed scene carries the truth
    assert scene["segments_used"] == 1  # original generation metadata preserved
    assert tr["rewritten"] is True


def test_adopted_clean_revision_keeps_flag_false():
    agent = _agent(FakeMetaWriter("calmer prose", trimmed=False), FakeTension(4))
    scene, _tr = agent._maybe_rewrite_for_tension(
        {"text": "tense", "word_count": 1, "trimmed": False},
        {"enabled": True, "tension_level": 8, "tension_category": "high"}, 0, {},
    )
    assert scene["text"] == "calmer prose"
    assert scene["trimmed"] is False

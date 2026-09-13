"""Sectioned scene writing (DSL Slice 5, generation.subblock_generation).

A masters-length chapter is ~3,165 words and one request does not reliably
produce one, so the scene is written across several plan-addressed calls.
Everything here runs on a scripted fake LLM: no API calls.
"""
import pytest

from novel_agent.agent import segments as sg
from novel_agent.agent.prompts import format_scene_section_prompt
from novel_agent.agent.scene_skeleton import plan_rules, skeleton_lines
from novel_agent.agent.writer import SceneWriter
from novel_agent.configs.config import Config


# ---- partitioning ------------------------------------------------------------

def test_partition_covers_every_block_exactly_once():
    for n in range(1, 60):
        bounds = sg.partition_skeleton(n, 10)
        assert bounds[0][0] == 1 and bounds[-1][1] == n
        seen = [i for a, b in bounds for i in range(a, b + 1)]
        assert seen == list(range(1, n + 1))


def test_partition_merges_a_trailing_stub():
    # 21 blocks at 10 would leave a 1-block final section, which would have to
    # open, sustain and land at once. It joins its predecessor instead.
    assert sg.partition_skeleton(21, 10) == [(1, 10), (11, 21)]
    assert sg.partition_skeleton(22, 10) == [(1, 10), (11, 22)]
    # A final section that is already substantial is left alone.
    assert sg.partition_skeleton(26, 10) == [(1, 10), (11, 20), (21, 26)]


def test_partition_degenerate_inputs():
    assert sg.partition_skeleton(0, 10) == []
    assert sg.partition_skeleton(-3, 10) == []
    assert sg.partition_skeleton(5, 99) == [(1, 5)]
    assert sg.partition_skeleton(4, 1) == [(1, 1), (2, 2), (3, 3), (4, 4)]
    assert sg.partition_skeleton(4, 0) == [(1, 4)]      # 0 falls back to default
    assert sg.partition_skeleton(4, None) == [(1, 4)]


def test_section_word_target_follows_the_mode_mix():
    words = {"DIALOGUE": {"mean": 41.5}, "LORE": {"mean": 115.0}}
    sk = ["DIALOGUE", "DIALOGUE", "LORE", "LORE"]
    assert sg.section_word_target(sk, 1, 2, words) == 83
    assert sg.section_word_target(sk, 3, 4, words) == 230
    assert sg.section_word_target(sk, 1, 4, words) == 313


# ---- the section prompt ------------------------------------------------------

def _prompt(first, last, **kw):
    sk = ["SETTING"] + ["DIALOGUE"] * 20
    return format_scene_section_prompt(
        {"scene_intention": "Mira confronts the archivist",
         "pov_character_name": "Mira"},
        plan_lines=skeleton_lines(sk, first, last),
        plan_rules=plan_rules(sectioned=True),
        first=first, last=last, **kw)


def test_plan_lines_keep_absolute_numbering():
    # A section rendered alone keeps the [n] addresses the full plan gives it,
    # otherwise its markers would collide with an earlier section's.
    lines = skeleton_lines(["SETTING"] + ["DIALOGUE"] * 20, 11, 15)
    assert lines.splitlines()[0].startswith("11. ")
    assert lines.splitlines()[-1].startswith("15. ")
    p = _prompt(11, 15, scene_so_far="prior", is_first=False)
    assert lines in p


def test_first_section_opens_and_does_not_close():
    p = _prompt(1, 10, is_first=True)
    assert "OPENING" in p
    assert "Do NOT bring the scene to a close" in p
    assert "The Scene So Far" not in p


def test_middle_section_neither_opens_nor_closes():
    p = _prompt(11, 20, scene_so_far="prior prose")
    assert "MIDDLE" in p
    assert "Do NOT bring the scene to a close" in p
    assert "The Scene So Far" in p
    assert "Later paragraphs are not yours to write" in p


def test_final_section_lands_the_ending():
    p = _prompt(11, 21, scene_so_far="prior prose", is_last=True)
    assert "FINAL" in p
    assert "land the scene's ending" in p
    # The stop-here clause would contradict the instruction to end the scene.
    assert "Later paragraphs are not yours to write" not in p


def test_every_section_carries_the_dialogue_turn_rule():
    for kw in ({"is_first": True}, {"scene_so_far": "x"},
               {"scene_so_far": "x", "is_last": True}):
        flat = " ".join(_prompt(1, 10, **kw).split())
        assert "each item is ONE character speaking" in flat


# ---- the writer loop ---------------------------------------------------------

class FakeLLM:
    """Returns one scripted response per call and records the prompts."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []
        self.budgets = []

    def generate_with_meta(self, prompt, max_tokens=2000, timeout=120):
        self.prompts.append(prompt)
        self.budgets.append(max_tokens)
        return self.responses.pop(0), "stop"


class Cfg:
    def __init__(self, **kw):
        self.kw = kw

    def get(self, key, default=None):
        if key in self.kw:
            return self.kw[key]
        return Config().get(key, default)


def _ctx(skeleton):
    return {
        "novel_name": "N", "current_tick": 3, "recent_context": "(none)",
        "scene_intention": "Mira confronts the archivist",
        "key_change": "the ledger changes hands", "progress_milestone": "",
        "plot_beat_section": "", "arc_pressure_section": "", "scene_mode": "",
        "palette_shift": "", "transition_path": "", "dialogue_targets": "",
        "tool_results_summary": "(none)", "pov_character_id": "C000",
        "pov_character_name": "Mira", "pov_character_details": "an archivist",
        "location_id": "L000", "location_details": "The archive",
        "existing_characters": "- Mira (POV)", "approved_new_names": "",
        "scene_length_guidance": "", "word_target": 1400,
        "scene_skeleton": skeleton,
    }


ON = {"generation.subblock_generation": True,
      "generation.subblock_section_blocks": 10}


def test_writer_makes_one_call_per_section():
    sk = ["DIALOGUE"] * 25
    llm = FakeLLM([f"[{i}] Part {i}." for i in (1, 11)])
    scene = SceneWriter(llm, Cfg(**ON)).write_scene(_ctx(sk))
    assert len(llm.prompts) == 2                 # 25 blocks at 10 -> 2 sections
    assert scene["segments_used"] == 2
    assert scene["sectioned"] is True
    assert "Part 1." in scene["text"] and "Part 11." in scene["text"]


def test_each_section_sees_the_prose_so_far():
    sk = ["DIALOGUE"] * 25
    llm = FakeLLM(["[1] Opening line.", "[11] Second part."])
    SceneWriter(llm, Cfg(**ON)).write_scene(_ctx(sk))
    assert "The Scene So Far" not in llm.prompts[0]
    assert "Opening line." in llm.prompts[1]


def test_flag_off_writes_single_shot():
    sk = ["DIALOGUE"] * 25
    llm = FakeLLM(["[1] The whole scene in one go, complete."])
    scene = SceneWriter(llm, Config()).write_scene(_ctx(sk))
    assert len(llm.prompts) == 1
    assert scene.get("sectioned") is not True


def test_no_skeleton_falls_back_to_single_shot():
    ctx = _ctx(None)
    llm = FakeLLM(["The whole scene, written in one call."])
    scene = SceneWriter(llm, Cfg(**ON)).write_scene(ctx)
    assert len(llm.prompts) == 1
    assert scene.get("sectioned") is not True


def test_single_section_plans_use_single_shot():
    # 8 blocks at 10 is one section, which is just single-shot writing.
    llm = FakeLLM(["[1] Short scene, done."])
    scene = SceneWriter(llm, Cfg(**ON)).write_scene(_ctx(["DIALOGUE"] * 8))
    assert len(llm.prompts) == 1
    assert scene.get("sectioned") is not True


def test_a_failed_section_falls_back_instead_of_losing_the_scene():
    class Boom(FakeLLM):
        def generate_with_meta(self, prompt, max_tokens=2000, timeout=120):
            self.prompts.append(prompt)
            if len(self.prompts) == 2:
                raise RuntimeError("backend fell over")
            return "[1] Something.", "stop"

    llm = Boom([])
    scene = SceneWriter(llm, Cfg(**ON)).write_scene(_ctx(["DIALOGUE"] * 25))
    assert scene.get("sectioned") is not True
    assert scene["text"]                      # the scene survived


def test_markers_are_stripped_from_the_stitched_scene():
    sk = ["DIALOGUE"] * 25
    llm = FakeLLM(["[1] First.", "[11] Second."])
    scene = SceneWriter(llm, Cfg(**ON)).write_scene(_ctx(sk))
    assert "[1]" not in scene["text"] and "[11]" not in scene["text"]
    assert scene["skeleton_compliance"]["markers_found"] == 2


# ---- the structural record ---------------------------------------------------

def test_writer_carries_the_plan_into_scene_data():
    sk = ["DIALOGUE"] * 25
    llm = FakeLLM(["[1] First.", "[11] Second."])
    scene = SceneWriter(llm, Cfg(**ON)).write_scene(_ctx(sk))
    assert scene["scene_skeleton"] == sk
    assert scene["section_bounds"] == [[1, 10], [11, 25]]


def test_commit_metadata_records_how_the_scene_was_written():
    from novel_agent.agent.scene_committer import _scene_metadata
    meta = _scene_metadata(
        {"rationale": "because"},
        {"scene_skeleton": ["DIALOGUE", "ACTION"],
         "skeleton_compliance": {"compliant": True},
         "sectioned": True, "section_bounds": [[1, 1], [2, 2]],
         "segments_used": 2, "trimmed": False,
         "word_count": 400},
    )
    assert meta["plan_rationale"] == "because"
    assert meta["scene_skeleton"] == ["DIALOGUE", "ACTION"]
    assert meta["section_bounds"] == [[1, 1], [2, 2]]
    assert meta["trimmed"] is False
    assert "word_count" not in meta          # only the structural record


def test_commit_metadata_omits_absent_keys():
    from novel_agent.agent.scene_committer import _scene_metadata
    meta = _scene_metadata({"rationale": "r"}, {"word_count": 10})
    assert meta == {"plan_rationale": "r"}


# ---- the tension rewrite must not silently undo the plan ---------------------

def test_compliance_is_recounted_against_the_committed_text():
    """Observed live: the tension rewrite replaced the prose after the writer
    had stripped markers and recorded compliance, so the saved figure
    described a discarded draft (57 paragraphs recorded, 28 on disk)."""
    from novel_agent.agent.scene_committer import _scene_metadata
    scene_data = {
        "scene_skeleton": ["DIALOGUE"] * 4,
        "skeleton_compliance": {"plan_blocks": 4, "markers_found": 4,
                                "markers_distinct": 4, "paragraphs": 4,
                                "extra_paragraphs": 0, "compliant": True},
        # what a rewrite left behind: the same scene, half the paragraphs
        "text": "One para.\n\nTwo para.",
    }
    meta = _scene_metadata({"rationale": "r"}, scene_data)
    c = meta["skeleton_compliance"]
    assert c["paragraphs"] == 2
    assert c["compliant"] is False
    assert c["rewritten_after_planning"] is True


def test_compliance_untouched_when_the_text_still_matches():
    from novel_agent.agent.scene_committer import _scene_metadata
    scene_data = {
        "scene_skeleton": ["DIALOGUE", "ACTION"],
        "skeleton_compliance": {"plan_blocks": 2, "paragraphs": 2,
                                "compliant": True},
        "text": "One para.\n\nTwo para.",
    }
    c = _scene_metadata({"rationale": "r"}, scene_data)["skeleton_compliance"]
    assert c["compliant"] is True
    assert "rewritten_after_planning" not in c


def test_a_planned_scene_takes_the_selective_revision_path():
    """A planned scene must not be handed to the whole-scene rewrite: that is
    what collapsed 64 paragraphs to 36 live. It gets selective revision of the
    tension-carrying paragraphs instead."""
    from novel_agent.agent.agent import StoryAgent

    class Cfg2:
        def get(self, key, default=None):
            return {"coherence.tension_rewrite": True,
                    "coherence.tension_rewrite_threshold": 2,
                    "coherence.target_story_length": 40,
                    "coherence.curve_preset": "house",
                    "coherence.target_tension_curve":
                        Config().get("coherence.target_tension_curve"),
                    "coherence.arc_phase_mandate": True}.get(key, default)

    calls = {}

    class W:
        def revise_blocks_for_tension(self, text, skeleton, indices, *a, **k):
            calls["indices"] = list(indices)
            calls["skeleton"] = list(skeleton)
            return "", {"reason": "test stub"}

        def revise_for_tension_with_meta(self, *a, **k):   # must NOT be called
            calls["whole_scene"] = True
            return "rewritten whole", {}

    class Mem:
        def list_scenes(self):
            return []

    agent = StoryAgent.__new__(StoryAgent)
    agent.config, agent.writer, agent.memory = Cfg2(), W(), Mem()
    planned = {"text": "a\n\nb\n\nc", "scene_skeleton": ["ACTION"] * 3}
    tension = {"enabled": True, "tension_level": 5.5}
    out, t = StoryAgent._maybe_rewrite_for_tension(agent, planned, tension, 1, {})
    assert "whole_scene" not in calls          # the destructive path never ran
    assert calls["indices"]                    # selective revision was asked for
    assert out is planned and t is tension     # stub returned nothing, so unchanged

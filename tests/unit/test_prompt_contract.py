"""Every prompt that reaches a writing model must carry the contract fields.

Sectioned writing and selective revision were each built by hand-picking a
subset of the writer context, and between them dropped four contracts:
approved_new_names (Phase 1 grounded identity), plot_beat_section,
arc_pressure_section and recent_context. Turning on subblock_generation
therefore switched off four features, and nothing caught it because the
prompts were only ever read by eye.

These tests render the prompts as the writer actually produces them, from a
context whose every field is a unique sentinel, and assert the sentinels
arrive. No LLM calls.
"""
import pytest

from novel_agent.agent.prompts import (CONTRACT_EXEMPTIONS, CONTRACT_FIELDS,
                                       contract_fields_for)
from novel_agent.agent.writer import SceneWriter
from novel_agent.configs.config import Config


SENTINEL = {f: f"SENTINEL_{f.upper()}" for f in CONTRACT_FIELDS}


class CapturingLLM:
    """Captures prompts; returns marked prose so the writer path completes."""

    def __init__(self, response="[1] Prose one.\n\n[2] Prose two."):
        self.response = response
        self.prompts = []

    def generate_with_meta(self, prompt, max_tokens=2000, timeout=120):
        self.prompts.append(prompt)
        return self.response, "stop"


def _ctx(**over):
    ctx = {
        "novel_name": "N", "current_tick": 3,
        "key_change": "the ledger changes hands", "progress_milestone": "",
        "scene_mode": "", "palette_shift": "", "transition_path": "",
        "dialogue_targets": "", "tool_results_summary": "(none)",
        "pov_character_id": "C000", "location_id": "L000",
        "scene_length_guidance": "", "word_target": 1400,
    }
    ctx.update(SENTINEL)
    ctx.update(over)
    return ctx


class Cfg:
    def __init__(self, **kw):
        self.kw = kw

    def get(self, key, default=None):
        if key in self.kw:
            return self.kw[key]
        return Config().get(key, default)


def _missing(prompt, task):
    return [f for f in contract_fields_for(task)
            if SENTINEL[f] not in prompt]


# ---- the three paths ---------------------------------------------------------

def test_single_shot_write_carries_every_contract_field():
    llm = CapturingLLM()
    SceneWriter(llm, Config()).write_scene(_ctx())
    assert _missing(llm.prompts[0], "write") == []


def test_sectioned_write_carries_every_contract_field():
    llm = CapturingLLM()
    cfg = Cfg(**{"generation.subblock_generation": True,
                 "generation.subblock_section_blocks": 10})
    SceneWriter(llm, cfg).write_scene(_ctx(scene_skeleton=["DIALOGUE"] * 25))
    assert llm.prompts, "sectioned writing made no call"
    for i, prompt in enumerate(llm.prompts):
        assert _missing(prompt, "write") == [], f"section call {i + 1}"


def test_revision_carries_every_contract_field():
    llm = CapturingLLM(response="[2] Revised.")
    SceneWriter(llm, Config()).revise_blocks_for_tension(
        "One.\n\nTwo.\n\nThree.", ["ACTION"] * 3, [2],
        target_level=3, current_level=8, writer_context=_ctx())
    assert llm.prompts, "revision made no call"
    assert _missing(llm.prompts[0], "revise") == []


# ---- craft discipline reaches every call too ---------------------------------

CRAFT_MARKERS = ["Third-person POV", "Deep POV only", "Show don't tell",
                 "NEVER invent a NEW character's name", "head-hopping"]


def _craft_missing(prompt):
    return [m for m in CRAFT_MARKERS if m not in prompt]


def test_single_shot_write_carries_the_craft_rules():
    llm = CapturingLLM()
    SceneWriter(llm, Config()).write_scene(_ctx())
    assert _craft_missing(llm.prompts[0]) == []


def test_every_section_call_carries_the_craft_rules():
    # Sections had NO craft guidance at all: no POV discipline, no naming
    # rule, no show-don't-tell. Only the whole-scene prompt ever had them.
    llm = CapturingLLM()
    cfg = Cfg(**{"generation.subblock_generation": True,
                 "generation.subblock_section_blocks": 10})
    SceneWriter(llm, cfg).write_scene(_ctx(scene_skeleton=["DIALOGUE"] * 25))
    for i, prompt in enumerate(llm.prompts):
        assert _craft_missing(prompt) == [], f"section call {i + 1}"


def test_revision_carries_the_craft_rules():
    llm = CapturingLLM(response="[2] Revised.")
    SceneWriter(llm, Config()).revise_blocks_for_tension(
        "One.\n\nTwo.\n\nThree.", ["ACTION"] * 3, [2],
        target_level=3, current_level=8, writer_context=_ctx())
    assert _craft_missing(llm.prompts[0]) == []


def test_sections_do_not_get_whole_scene_shape_requirements():
    """A middle section must not be told to open, turn and resolve on its own:
    those describe the arc of a whole scene."""
    llm = CapturingLLM()
    cfg = Cfg(**{"generation.subblock_generation": True,
                 "generation.subblock_section_blocks": 10})
    SceneWriter(llm, cfg).write_scene(_ctx(scene_skeleton=["DIALOGUE"] * 25))
    for prompt in llm.prompts:
        assert "BUILD TO A TURNING POINT" not in prompt
        assert "EXECUTE THE CHANGE" not in prompt


# ---- ordering: static before volatile ----------------------------------------

def _common_prefix(a, b):
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def test_section_calls_share_a_long_identical_prefix():
    """Everything invariant across a scene's sections must come first.

    This is what makes the prefix cacheable (PROMPT_ARCHITECTURE_PLAN.md
    section 3). It was not true before: the growing scene-so-far sat ahead of
    the static plan rules, so the prose poisoned the prefix from the second
    call onward.
    """
    llm = CapturingLLM()
    cfg = Cfg(**{"generation.subblock_generation": True,
                 "generation.subblock_section_blocks": 10})
    SceneWriter(llm, cfg).write_scene(_ctx(scene_skeleton=["DIALOGUE"] * 40))
    assert len(llm.prompts) >= 3, "need several sections to compare"
    shared = min(_common_prefix(llm.prompts[0], p) for p in llm.prompts[1:])
    # The spine, craft rules and plan rules all sit inside the shared prefix.
    assert shared > 1500, f"only {shared} chars shared across section calls"
    prefix = llm.prompts[0][:shared]
    assert "## POV Character" in prefix
    assert "Deep POV only" in prefix
    assert "Plan rules:" in prefix
    # and the volatile parts are outside it: the per-section numbers, the
    # plan lines and the prose so far must all fall after the shared prefix.
    assert "The Scene So Far" not in prefix
    tails = [p[shared:] for p in llm.prompts]
    assert all("items, about" in t for t in tails)     # per-section counts
    assert all("DIALOGUE, ~" in t for t in tails)      # this section's plan


def test_plan_rules_are_identical_across_sections():
    from novel_agent.agent.scene_skeleton import plan_rules
    assert plan_rules(sectioned=True) == plan_rules(sectioned=True)
    assert "{" not in plan_rules(sectioned=True)     # no per-call numbers left


# ---- the contract itself -----------------------------------------------------

def test_every_exemption_names_a_real_field_and_gives_a_reason():
    for (task, field), reason in CONTRACT_EXEMPTIONS.items():
        assert field in CONTRACT_FIELDS, f"{field} is not a contract field"
        assert len(reason.split()) >= 8, f"{task}/{field} needs a real reason"


def test_exemptions_are_narrow():
    # An omission has to be argued for. If this ever grows large, the contract
    # has stopped meaning anything.
    assert len(CONTRACT_EXEMPTIONS) <= 3


def test_revision_is_exempt_from_offering_new_names():
    assert "approved_new_names" not in contract_fields_for("revise")
    assert "approved_new_names" in contract_fields_for("write")

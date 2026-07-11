"""Contracts Slice 1: conditions ride the beats.

PlotBeat carries preconditions/postconditions (flat JSON condition dicts) through
the plot_outline.json round-trip; legacy outlines load unchanged; the writer sees
the postconditions as plain language; the beat-generation prompt documents the
closed vocabulary only when generation.use_contracts is on.
"""

import json
import tempfile
from pathlib import Path

import pytest

from novel_agent.configs.config import Config
from novel_agent.contracts.authoring import (
    GATED_AUTHORING_CHECKS,
    contract_authoring_section,
    describe_condition,
    entity_label,
    sanitize_beat_conditions,
)
from novel_agent.memory.entities import Character, Location
from novel_agent.plot.entities import PlotBeat, PlotOutline


def _config(**overrides):
    config = Config()
    for key, value in overrides.items():
        config.set(key, value)
    return config


# ---------------------------------------------------------------------------
# PlotBeat field round-trip
# ---------------------------------------------------------------------------

def test_conditions_round_trip_through_beat_dict():
    beat = PlotBeat(
        id="PB001",
        description="Joran resolves the debt",
        tension_target=7,
        preconditions=[{"check": "entity_exists", "id": "C000"}],
        postconditions=[
            {"check": "loop_resolved", "loop": "OL001"},
            {"check": "tension_at_least", "value": 5},
        ],
    )
    restored = PlotBeat.from_dict(beat.to_dict())
    assert restored.preconditions == beat.preconditions
    assert restored.postconditions == beat.postconditions
    assert restored.contract_results == {}


def test_legacy_outline_without_condition_fields_loads_unchanged():
    # A plot_outline.json written before Slice 1 has no condition fields at all;
    # dataclass defaults must fill them in (cls(**data) round-trip).
    legacy = {
        "beats": [{
            "id": "PB001",
            "description": "old beat",
            "status": "pending",
            "created_at": "2026-01-01T00:00:00Z",
        }],
        "created_at": "2026-01-01T00:00:00Z",
        "last_updated": "2026-01-01T00:00:00Z",
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "plot_outline.json"
        path.write_text(json.dumps(legacy))
        outline = PlotOutline.from_json(path)

    beat = outline.beats[0]
    assert beat.preconditions == []
    assert beat.postconditions == []
    assert beat.contract_results == {}


def test_cli_manager_reads_beat_with_conditions():
    # The CLI-side manager (memory.plot_outline / memory.entities.PlotBeat) parses
    # the same file via cls(**data); a beat carrying the new fields must not break it.
    from novel_agent.memory.plot_outline import PlotOutlineManager as CliManager

    with tempfile.TemporaryDirectory() as tmpdir:
        project = Path(tmpdir)
        outline = PlotOutline(beats=[
            PlotBeat(id="PB001", description="x",
                     postconditions=[{"check": "tension_at_least", "value": 6}],
                     contract_results={"is_valid": True, "checked": 1, "failed": 0}),
        ], created_at=PlotOutline.now_iso(), last_updated=PlotOutline.now_iso())
        outline.to_json(project / "plot_outline.json")

        cli_beat = CliManager(project).load_outline().beats[0]  # must not raise
        assert cli_beat.postconditions == [{"check": "tension_at_least", "value": 6}]
        assert cli_beat.contract_results["is_valid"] is True


def test_memory_entities_beat_round_trips_conditions():
    from novel_agent.memory.entities import PlotBeat as MemoryBeat

    beat = MemoryBeat(id="PB002", description="y",
                      postconditions=[{"check": "char_in_prose", "char": "C000"}])
    restored = MemoryBeat.from_dict(beat.to_dict())
    assert restored.postconditions == beat.postconditions
    assert restored.preconditions == []


# ---------------------------------------------------------------------------
# Writer prompt rendering
# ---------------------------------------------------------------------------

class FakeMemory:
    """Just enough MemoryManager surface for entity name resolution."""

    def __init__(self, characters=None, locations=None, raises=False):
        self.characters = characters or {}
        self.locations = locations or {}
        self.raises = raises

    def load_character(self, char_id):
        if self.raises:
            raise RuntimeError("disk error")
        return self.characters.get(char_id)

    def load_location(self, loc_id):
        if self.raises:
            raise RuntimeError("disk error")
        return self.locations.get(loc_id)


def _named_memory():
    return FakeMemory(
        characters={
            "C000": Character(id="C000", first_name="Vela", family_name="Starkord"),
            "C003": Character(id="C003", first_name="Grimax", family_name="Texyx"),
        },
        locations={"L002": Location(id="L002", name="Ashhearth Bar")},
    )


def _plot_beat_section(plan, memory=None):
    from novel_agent.agent.writer_context import WriterContextBuilder

    builder = WriterContextBuilder.__new__(WriterContextBuilder)
    if memory is not None:
        builder.memory = memory
    return builder._format_plot_beat_section(plan)


def test_writer_section_renders_postconditions_as_plain_language():
    plan = {"plot_beat": {
        "description": "Joran settles the debt",
        "tension_target": 7,
        "postconditions": [
            {"check": "loop_resolved", "loop": "OL001"},
            {"check": "tension_at_least", "value": 5},
            {"check": "char_in_prose", "char": "C000"},
        ],
    }}
    section = _plot_beat_section(plan)
    assert "This scene must leave the story in a state where:" in section
    assert "open loop OL001 has been resolved" in section
    assert "dramatic tension is at least 5/10" in section
    assert "character C000 appears in the scene" in section


def test_writer_section_without_postconditions_unchanged():
    plan = {"plot_beat": {"description": "Joran settles the debt"}}
    section = _plot_beat_section(plan)
    assert "must leave the story" not in section
    assert "THIS BEAT MUST BE ACCOMPLISHED" in section


def test_writer_section_renders_named_cast_and_contract():
    # Deterministic cast injection: the beat's characters_involved and its
    # char_in_prose postconditions reach the writer as names, not bare ids
    # (descent-run4: "character C003" produced seven ticks of freelance casting).
    plan = {"plot_beat": {
        "description": "Galen is approached by Holtwick security",
        "characters_involved": ["C000", "C003", "C007"],
        "location": "L002",
        "postconditions": [
            {"check": "char_in_prose", "char": "C003"},
            {"check": "tension_at_least", "value": 6},
        ],
    }}
    section = _plot_beat_section(plan, _named_memory())
    # C007 is unknown to memory and stays a bare id inside the named list.
    assert "**Characters who must appear:** Vela Starkord (C000), Grimax Texyx (C003), C007" in section
    assert "**Required Location:** Ashhearth Bar (L002)" in section
    assert "Grimax Texyx (C003) appears in the scene" in section
    assert "dramatic tension is at least 6/10" in section


def test_writer_section_cast_falls_back_to_ids_without_memory():
    plan = {"plot_beat": {
        "description": "Galen is approached by Holtwick security",
        "characters_involved": ["C000", "C003"],
        "location": "L002",
    }}
    section = _plot_beat_section(plan)  # builder has no memory attribute at all
    assert "**Characters who must appear:** C000, C003" in section
    assert "**Required Location:** L002" in section


def test_describe_condition_prefers_authored_description():
    cond = {"check": "prose_contains", "any": ["Skyvault"],
            "description": "the Skyvault Accord is named"}
    assert describe_condition(cond) == "the Skyvault Accord is named"
    assert "Skyvault" in describe_condition({"check": "prose_contains", "any": ["Skyvault"]})


# ---------------------------------------------------------------------------
# Grounded identity on the contract surface (the descent-run4 wedge: a bare
# "character C003" is unactionable when the writer never sees the name)
# ---------------------------------------------------------------------------

def test_describe_condition_renders_names_with_memory():
    memory = _named_memory()
    assert describe_condition({"check": "char_in_prose", "char": "C003"}, memory) == \
        "Grimax Texyx (C003) appears in the scene"
    assert describe_condition(
        {"check": "char_at_location", "char": "C000", "location": "L002"}, memory
    ) == "Vela Starkord (C000) is at Ashhearth Bar (L002)"
    assert describe_condition({"check": "entity_exists", "id": "C000"}, memory) == \
        "Vela Starkord (C000) is established in the story"
    assert describe_condition({"check": "entity_exists", "id": "L002"}, memory) == \
        "Ashhearth Bar (L002) is established in the story"


def test_describe_condition_without_memory_keeps_bare_ids():
    assert describe_condition({"check": "char_in_prose", "char": "C003"}) == \
        "character C003 appears in the scene"
    assert describe_condition({"check": "char_at_location", "char": "C000", "location": "L002"}) == \
        "character C000 is at location L002"
    assert describe_condition({"check": "entity_exists", "id": "C000"}) == \
        "entity C000 is established in the story"


def test_describe_condition_lookup_failure_stays_graceful():
    # A raising memory, an unknown id, and a nameless entity all fall back to
    # the bare-id phrasing instead of failing the prompt build.
    raising = FakeMemory(raises=True)
    assert describe_condition({"check": "char_in_prose", "char": "C003"}, raising) == \
        "character C003 appears in the scene"
    assert describe_condition({"check": "char_in_prose", "char": "C099"}, _named_memory()) == \
        "character C099 appears in the scene"
    unnamed = FakeMemory(characters={"C005": Character(id="C005")})
    assert describe_condition({"check": "char_in_prose", "char": "C005"}, unnamed) == \
        "character C005 appears in the scene"


def test_entity_label_only_resolves_canonical_ids():
    memory = _named_memory()
    assert entity_label("C003", memory) == "Grimax Texyx (C003)"
    assert entity_label("L002", memory) == "Ashhearth Bar (L002)"
    assert entity_label("the docks", memory) is None  # free-text location, not an id
    assert entity_label(None, memory) is None
    assert entity_label("C003", None) is None


# ---------------------------------------------------------------------------
# Beat-generation prompt section (gated)
# ---------------------------------------------------------------------------

def test_contract_section_empty_when_gate_off():
    assert contract_authoring_section(_config()) == ""


def test_contract_section_documents_vocabulary_when_gate_on():
    section = contract_authoring_section(_config(**{"generation.use_contracts": True}))
    for checker in ("entity_exists", "char_in_prose", "prose_contains",
                    "tension_at_least", "tension_at_most"):
        assert checker in section
    # Structurally unsatisfiable today (2026-07-10 run): gated out of authoring
    # entirely, so the prompt must not steer the LLM toward them.
    for gated in GATED_AUTHORING_CHECKS:
        assert gated not in section
    # Section 5 of the landing sketch: steer away from surface-vocabulary checks.
    assert "AVOID prose_contains" in section


def test_plot_prompt_renders_with_and_without_contract_section():
    from novel_agent.agent.prompts import format_plot_generation_prompt

    ctx = {
        "count": 2, "novel_name": "N", "current_tick": 3,
        "genre": "g", "premise": "p", "setting": "s", "tone": "t",
        "characters": "None", "locations": "None", "open_loops": "None",
        "recent_scenes": "None", "tension_history": "None", "recent_beats": "None",
    }
    # Legacy callers omit the section entirely (setdefault covers them).
    assert "Scene contracts" not in format_plot_generation_prompt(ctx)

    ctx["contract_section"] = contract_authoring_section(
        _config(**{"generation.use_contracts": True})
    )
    assert "Scene contracts (postconditions)" in format_plot_generation_prompt(ctx)


def test_schema_example_empty_when_gate_off():
    from novel_agent.contracts.authoring import contract_schema_example

    assert contract_schema_example(_config()) == ""


def test_schema_example_puts_postconditions_in_the_shape_block():
    # The live 2026-07-10 smoke run proved a schema-obedient model never emits a
    # field absent from the "must have this shape" block, whatever the section
    # text says: the example fragment must land inside that block.
    from novel_agent.agent.prompts import format_plot_generation_prompt
    from novel_agent.contracts.authoring import contract_schema_example

    ctx = {
        "count": 2, "novel_name": "N", "current_tick": 3,
        "genre": "g", "premise": "p", "setting": "s", "tone": "t",
        "characters": "None", "locations": "None", "open_loops": "None",
        "recent_scenes": "None", "tension_history": "None", "recent_beats": "None",
    }
    # Gate off (or legacy caller): the shape block has no postconditions field.
    prompt_off = format_plot_generation_prompt(ctx)
    shape_block_off = prompt_off.split("# Current story state")[0]
    assert "postconditions" not in shape_block_off

    ctx["contract_schema_example"] = contract_schema_example(
        _config(**{"generation.use_contracts": True})
    )
    prompt_on = format_plot_generation_prompt(ctx)
    shape_block_on = prompt_on.split("# Current story state")[0]
    # The fragment attaches directly after creates_loops, inside the example object.
    assert '"creates_loops": [],\n      "postconditions"' in shape_block_on
    # The example check must be an authorable one, never a gated one (the shape
    # block is the strongest steer the prompt has).
    assert '{"check": "char_in_prose"' in shape_block_on
    for gated in GATED_AUTHORING_CHECKS:
        assert gated not in shape_block_on


# ---------------------------------------------------------------------------
# Authoring gate in the sanitizer (structurally unsatisfiable checks)
# ---------------------------------------------------------------------------

class _GateLoop:
    def __init__(self, loop_id):
        self.id = loop_id


class _GateMemory:
    """Roster surface where every referenced id resolves, so a drop can only
    come from the authoring gate, not from a phantom ref."""

    def list_characters(self):
        return ["C000"]

    def list_locations(self):
        return ["L000"]

    def load_open_loops(self):
        return [_GateLoop("OL001")]


def _contracts_on():
    return _config(**{"generation.use_contracts": True})


def test_authored_char_at_location_dropped_by_gate():
    beat = PlotBeat(id="PB001", description="x", postconditions=[
        {"check": "char_at_location", "char": "C000", "location": "L000"},
        {"check": "char_in_prose", "char": "C000"},
    ])
    warnings = sanitize_beat_conditions([beat], _GateMemory(), _contracts_on())
    assert beat.postconditions == [{"check": "char_in_prose", "char": "C000"}]
    assert any("gated from authoring" in w and "char_at_location" in w
               for w in warnings)
    # Distinct wording from the unknown-check drop.
    assert not any("unknown check" in w for w in warnings)


def test_authored_loop_resolved_dropped_by_gate():
    beat = PlotBeat(id="PB001", description="x", postconditions=[
        {"check": "loop_resolved", "loop": "OL001"},
    ])
    warnings = sanitize_beat_conditions([beat], _GateMemory(), _contracts_on())
    assert beat.postconditions == []
    assert any("gated from authoring" in w and "loop_resolved" in w
               for w in warnings)


def test_gate_does_not_block_derived_tension_conditions():
    # The gate is authoring-only: system-derived tension conditions (from the
    # beat's own tension_target) still land after gated conditions are dropped.
    beat = PlotBeat(id="PB001", description="x", tension_target=8, postconditions=[
        {"check": "loop_resolved", "loop": "OL001"},
    ])
    sanitize_beat_conditions([beat], _GateMemory(), _contracts_on())
    assert beat.postconditions == [{"check": "tension_at_least", "value": 6}]

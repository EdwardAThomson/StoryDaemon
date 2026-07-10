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
from novel_agent.contracts.authoring import contract_authoring_section, describe_condition
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

def _plot_beat_section(plan):
    from novel_agent.agent.writer_context import WriterContextBuilder

    builder = WriterContextBuilder.__new__(WriterContextBuilder)
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


def test_describe_condition_prefers_authored_description():
    cond = {"check": "prose_contains", "any": ["Skyvault"],
            "description": "the Skyvault Accord is named"}
    assert describe_condition(cond) == "the Skyvault Accord is named"
    assert "Skyvault" in describe_condition({"check": "prose_contains", "any": ["Skyvault"]})


# ---------------------------------------------------------------------------
# Beat-generation prompt section (gated)
# ---------------------------------------------------------------------------

def test_contract_section_empty_when_gate_off():
    assert contract_authoring_section(_config()) == ""


def test_contract_section_documents_vocabulary_when_gate_on():
    section = contract_authoring_section(_config(**{"generation.use_contracts": True}))
    for checker in ("entity_exists", "char_at_location", "char_in_prose",
                    "prose_contains", "tension_at_least", "tension_at_most",
                    "loop_resolved"):
        assert checker in section
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
    assert '{"check": "loop_resolved"' in shape_block_on

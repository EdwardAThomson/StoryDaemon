"""Thread identity grounding tests (Phase 3, interleaving Slice T1.5).

Policy under test: the "select, don't invent" move applied to threads. The T1
backfill over three finished novels showed authored plot_threads labels are
per-beat episode titles, not persistent threads (34 executed beats yielded 30
distinct primary labels; casts, not labels, were the reliable identity
signal), so Python mints thread identity and the LLM selects it: the beat
prompt carries a Story threads roster with exact TH ids, each beat names the
ONE thread it serves via thread_id ("new: <name>" mints a strand),
sanitize_beat_thread_ids holds the authored ids to the roster, and per-tick
attribution prefers the selected id over the T1 first-label fallback. All
gated by coherence.thread_identity (default True); off restores exact T1
behavior.
"""

import json
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.coherence_metrics import CoherenceMetrics
from novel_agent.agent.thread_registry import (
    EMPTY_ROSTER_LINE,
    THREAD_ROSTER_HEADER,
    ThreadRegistry,
    sanitize_beat_thread_ids,
    thread_prompt_rule,
    thread_roster_section,
    thread_schema_example,
)
from novel_agent.configs.config import Config
from novel_agent.memory.entities import Character, PlotBeat as MemoryPlotBeat, Thread
from novel_agent.memory.manager import MemoryManager
from novel_agent.plot.entities import PlotBeat


@pytest.fixture
def project():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def _gate_off_config():
    config = Config()
    config.set("coherence.thread_identity", False)
    return config


def _registry(project_dir, memory=None, config=None):
    return ThreadRegistry(memory or MemoryManager(project_dir), config or Config())


def _beat(beat_id="PB001", thread_id=None, threads=None, characters=None, location=None):
    return PlotBeat(
        id=beat_id,
        description="a beat",
        thread_id=thread_id,
        plot_threads=threads if threads is not None else [],
        characters_involved=characters or [],
        location=location,
    )


def _seed_thread(project_dir, memory=None, characters=None):
    """One attributed scene so the registry holds TH000 (velyn agenda)."""
    memory = memory or MemoryManager(project_dir)
    result = _registry(project_dir, memory).attribute_scene(
        tick=2,
        scene_id="S002",
        beat=_beat("PB001", threads=["velyn_agenda"],
                   characters=characters if characters is not None else ["C000"]),
        tension_level=6,
    )
    assert result["thread_id"] == "TH000"
    return memory


# ---------------------------------------------------------------------------
# Roster rendering (the selection surface)
# ---------------------------------------------------------------------------

def test_roster_resolves_member_names(project):
    memory = MemoryManager(project)
    memory.save_character(Character(id="C000", first_name="Velyn",
                                    family_name="Oskarsdottir"))
    _seed_thread(project, memory)
    section = thread_roster_section(memory, Config())
    assert section.startswith(THREAD_ROSTER_HEADER)
    line = section.splitlines()[1]
    assert line.startswith("TH000: velyn agenda")
    assert "members: Velyn Oskarsdottir (C000)" in line
    assert "scenes: 1" in line
    assert "last active: tick 2" in line
    assert "tension: 6" in line


def test_roster_unresolvable_member_keeps_bare_id(project):
    memory = _seed_thread(project)  # C000 never saved
    section = thread_roster_section(memory, Config())
    assert "members: C000" in section


def test_roster_empty_registry_renders_implicit_main_line(project):
    section = thread_roster_section(MemoryManager(project), Config())
    assert section.startswith(THREAD_ROSTER_HEADER)
    assert EMPTY_ROSTER_LINE in section


def test_roster_gate_off_omits_everything(project):
    memory = _seed_thread(project)
    config = _gate_off_config()
    assert thread_roster_section(memory, config) == ""
    assert thread_schema_example(config) == ""
    assert thread_prompt_rule(config) == ""


def test_roster_unreadable_ledger_omits_section(project):
    memory = MemoryManager(project)
    memory.threads_file.write_text("{not json", encoding="utf-8")
    assert thread_roster_section(MemoryManager(project), Config()) == ""


def test_agent_context_path_populates_thread_section(project):
    from novel_agent.plot.manager import PlotOutlineManager

    _seed_thread(project)
    manager = PlotOutlineManager(project, llm_interface=None, config=Config())
    ctx = manager._build_generation_context(3)
    assert THREAD_ROSTER_HEADER in ctx["thread_section"]
    assert "TH000: velyn agenda" in ctx["thread_section"]
    assert '"thread_id": "TH000"' in ctx["thread_schema_example"]
    assert "Never invent TH ids" in ctx["thread_rule"]


def test_cli_context_path_populates_thread_section(project):
    from novel_agent.cli.commands.plot import _build_plot_generation_prompt

    (project / "state.json").write_text(
        json.dumps({"novel_name": "T", "current_tick": 3}), encoding="utf-8")
    _seed_thread(project)
    prompt = _build_plot_generation_prompt(project, 3)
    assert THREAD_ROSTER_HEADER in prompt
    assert "TH000: velyn agenda" in prompt
    assert '"thread_id": "TH000",' in prompt  # the shape example
    assert 'write "new: <short thread name>"' in prompt


def test_cli_context_path_gate_off_omits_thread_surface(project):
    from novel_agent.cli.commands.plot import _build_plot_generation_prompt

    (project / "state.json").write_text(
        json.dumps({"novel_name": "T", "current_tick": 3}), encoding="utf-8")
    (project / "config.yaml").write_text(
        "coherence:\n  thread_identity: false\n", encoding="utf-8")
    _seed_thread(project)
    prompt = _build_plot_generation_prompt(project, 3)
    assert "Story threads" not in prompt
    assert "thread_id" not in prompt


# ---------------------------------------------------------------------------
# Beat field round-trip (both dataclasses; legacy outlines load unchanged)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("cls", [PlotBeat, MemoryPlotBeat])
def test_thread_id_round_trips(cls):
    beat = cls(id="PB001", description="d", thread_id="TH001")
    data = beat.to_dict()
    assert data["thread_id"] == "TH001"
    assert cls.from_dict(data).thread_id == "TH001"


@pytest.mark.parametrize("cls", [PlotBeat, MemoryPlotBeat])
def test_legacy_beat_dict_loads_with_none_thread_id(cls):
    legacy = cls(id="PB001", description="d").to_dict()
    legacy.pop("thread_id")
    beat = cls.from_dict(legacy)
    assert beat.thread_id is None


# ---------------------------------------------------------------------------
# Resolution/minting sanitizer
# ---------------------------------------------------------------------------

def test_sanitizer_keeps_exact_known_id(project):
    memory = _seed_thread(project)
    beat = _beat("PB010", thread_id="TH000", characters=["C000"])
    warnings = sanitize_beat_thread_ids([beat], memory, Config())
    assert beat.thread_id == "TH000"
    assert warnings == []


def test_sanitizer_canonicalizes_id_casing(project):
    memory = _seed_thread(project)
    beat = _beat("PB010", thread_id="th000", characters=["C000"])
    sanitize_beat_thread_ids([beat], memory, Config())
    assert beat.thread_id == "TH000"


def test_sanitizer_new_mints_and_rewrites(project):
    memory = _seed_thread(project)
    beat = _beat("PB010", thread_id="new: The Merger Countdown")
    warnings = sanitize_beat_thread_ids([beat], memory, Config())
    assert beat.thread_id == "TH001"
    assert warnings == []
    # Minted thread persists on disk: normalized name, raw spelling as label.
    minted = {t.id: t for t in MemoryManager(project).load_threads()}["TH001"]
    assert minted.name == "the merger countdown"
    assert minted.labels == ["The Merger Countdown"]
    assert minted.implicit is False


def test_sanitizer_new_matching_existing_reuses_not_duplicates(project):
    memory = _seed_thread(project)
    beat = _beat("PB010", thread_id="new: Velyn's agenda")
    warnings = sanitize_beat_thread_ids([beat], memory, Config())
    assert beat.thread_id == "TH000"
    assert any("reusing" in w for w in warnings)
    assert len(memory.load_threads()) == 1


def test_sanitizer_new_with_unusable_name_clears(project):
    memory = _seed_thread(project)
    beat = _beat("PB010", thread_id="new: ???")
    warnings = sanitize_beat_thread_ids([beat], memory, Config())
    assert beat.thread_id is None
    assert any("unusable thread name" in w for w in warnings)


def test_sanitizer_junk_matched_by_name(project):
    memory = _seed_thread(project)
    beat = _beat("PB010", thread_id="Velyn's agenda")
    warnings = sanitize_beat_thread_ids([beat], memory, Config())
    assert beat.thread_id == "TH000"
    assert any("resolved to TH000" in w for w in warnings)


def test_sanitizer_unknown_cleared_with_warning(project):
    memory = _seed_thread(project)
    beats = [_beat("PB010", thread_id="TH999"),
             _beat("PB011", thread_id="completely unrelated strand")]
    warnings = sanitize_beat_thread_ids(beats, memory, Config())
    assert beats[0].thread_id is None
    assert beats[1].thread_id is None
    assert sum("matches no known thread" in w for w in warnings) == 2


def test_sanitizer_cast_disjoint_warns_but_keeps(project):
    memory = _seed_thread(project, characters=["C000"])
    beat = _beat("PB010", thread_id="TH000", characters=["C005"])
    warnings = sanitize_beat_thread_ids([beat], memory, Config())
    assert beat.thread_id == "TH000"  # conservative: warn, never reassign
    assert "beat PB010: cast disjoint from thread TH000 (velyn agenda)" in warnings


def test_sanitizer_empty_cast_is_not_disjoint(project):
    memory = _seed_thread(project, characters=["C000"])
    beat = _beat("PB010", thread_id="TH000")
    assert sanitize_beat_thread_ids([beat], memory, Config()) == []


def test_sanitizer_none_and_blank_thread_ids(project):
    memory = _seed_thread(project)
    none_beat = _beat("PB010", thread_id=None)
    blank_beat = _beat("PB011", thread_id="   ")
    warnings = sanitize_beat_thread_ids([none_beat, blank_beat], memory, Config())
    assert none_beat.thread_id is None
    assert blank_beat.thread_id is None
    assert warnings == []


def test_sanitizer_unreadable_ledger_leaves_thread_ids_untouched(project):
    memory = MemoryManager(project)
    memory.threads_file.write_text("{not json", encoding="utf-8")
    memory = MemoryManager(project)
    beat = _beat("PB010", thread_id="TH999")
    warnings = sanitize_beat_thread_ids([beat], memory, Config())
    assert beat.thread_id == "TH999"
    assert any("ledger unreadable" in w for w in warnings)


def test_sanitizer_gate_off_is_noop(project):
    memory = _seed_thread(project)
    beat = _beat("PB010", thread_id="TH999")
    assert sanitize_beat_thread_ids([beat], memory, _gate_off_config()) == []
    assert beat.thread_id == "TH999"  # untouched, exact T1 behavior


# ---------------------------------------------------------------------------
# Attribution preference order (selected > label_fallback > main)
# ---------------------------------------------------------------------------

def test_attribution_prefers_selected_thread_id(project):
    memory = _seed_thread(project)
    registry = _registry(project, memory)
    # A label that would mint its own thread loses to the explicit selection.
    result = registry.attribute_scene(
        tick=3, scene_id="S003",
        beat=_beat("PB002", thread_id="TH000", threads=["some episode title"]),
        tension_level=4)
    assert result["thread_id"] == "TH000"
    assert result["source"] == "selected"
    assert result["created"] is False
    thread = memory.load_threads()[0]
    # Under selection the label is per-beat color, not match material.
    assert "some episode title" not in thread.labels
    assert thread.attribution_sources.get("selected") == 1


def test_attribution_unresolvable_selection_falls_back_to_label(project):
    memory = _seed_thread(project)
    result = _registry(project, memory).attribute_scene(
        tick=3, scene_id="S003",
        beat=_beat("PB002", thread_id="TH999", threads=["Velyn's agenda"]),
        tension_level=4)
    assert result["thread_id"] == "TH000"
    assert result["source"] == "label_fallback"


def test_attribution_no_beat_is_main(project):
    memory = MemoryManager(project)
    result = _registry(project, memory).attribute_scene(
        tick=0, scene_id="S000", beat=None)
    assert result["source"] == "main"
    assert memory.load_threads()[0].attribution_sources == {"main": 1}


def test_attribution_gate_off_restores_t1_behavior(project):
    memory = _seed_thread(project)
    config = _gate_off_config()
    before = {t.id: dict(t.attribution_sources) for t in memory.load_threads()}
    result = ThreadRegistry(memory, config).attribute_scene(
        tick=3, scene_id="S003",
        beat=_beat("PB002", thread_id="TH000", threads=["merger_countdown"]),
        tension_level=4)
    # Selection is ignored: the label mints its own thread, T1 style.
    assert result["thread_name"] == "merger countdown"
    assert result["source"] is None
    # No selection-adoption counters are persisted with the gate off: existing
    # threads keep their counts unchanged, the new thread gets none.
    for thread in memory.load_threads():
        assert thread.attribution_sources == before.get(thread.id, {})


def test_legacy_thread_record_loads_without_sources():
    data = Thread(id="TH000", name="x").to_dict()
    data.pop("attribution_sources")
    assert Thread.from_dict(data).attribution_sources == {}


# ---------------------------------------------------------------------------
# Metrics field (the rubric's never-break pattern)
# ---------------------------------------------------------------------------

class FakeVector:
    def compute_semantic_similarity(self, a, b):
        return 0.5


def _metrics(project_dir):
    return CoherenceMetrics(project_dir, MemoryManager(project_dir), FakeVector(), Config())


def test_metrics_thread_selection_source_recorded(project):
    (project / "memory").mkdir(exist_ok=True)
    rec = _metrics(project).record_tick(
        tick=3, scene_id="S003",
        thread_result={"thread_id": "TH000", "thread_name": "velyn agenda",
                       "created": False, "thread_count": 2, "run_length": 3,
                       "source": "selected"},
    )
    assert rec["thread_selection_source"] == "selected"


def test_metrics_thread_selection_source_none_when_unavailable(project):
    (project / "memory").mkdir(exist_ok=True)
    rec = _metrics(project).record_tick(tick=3, scene_id="S003")
    assert rec["thread_selection_source"] is None

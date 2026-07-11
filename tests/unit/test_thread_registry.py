"""Thread registry tests (Phase 3, interleaving Slice T1).

Policy under test (docs/THREAD_INTERLEAVING_DESIGN.md section 6, Slice T1):
threads become first-class objects seeded by deterministically normalizing the
free-text plot_threads labels beats already carry; each committed scene is
attributed to its beat's FIRST label's thread (implicit "main" when there is
no beat or no labels, so the trace stays total); the rubric records
active_thread / thread_count / thread_run_length per tick. Pure
instrumentation: nothing reads the registry for decisions in this slice, and
no failure may break a tick.
"""

import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.coherence_metrics import CoherenceMetrics
from novel_agent.agent.thread_registry import (
    MAIN_THREAD_NAME,
    ThreadRegistry,
    compute_current_run,
    match_thread,
    normalize_thread_label,
    primary_label,
)
from novel_agent.cli.commands.threads import (
    display_threads,
    display_threads_json,
    get_threads_info,
)
from novel_agent.configs.config import Config
from novel_agent.memory.entities import Thread
from novel_agent.memory.manager import MemoryManager
from novel_agent.plot.entities import PlotBeat


@pytest.fixture
def project():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def _registry(project_dir, memory=None, config=None):
    return ThreadRegistry(memory or MemoryManager(project_dir), config or Config())


def _beat(beat_id="PB001", threads=None, characters=None, location=None):
    return PlotBeat(
        id=beat_id,
        description="a beat",
        plot_threads=threads if threads is not None else [],
        characters_involved=characters or [],
        location=location,
    )


# ---------------------------------------------------------------------------
# Label normalization (deterministic; design open question 1)
# ---------------------------------------------------------------------------

def test_normalize_casefold_and_separators():
    assert normalize_thread_label("Velyn_Agenda") == "velyn agenda"
    assert normalize_thread_label("VELYN-AGENDA") == "velyn agenda"
    assert normalize_thread_label("velyn/agenda") == "velyn agenda"
    assert normalize_thread_label("  Velyn   Agenda  ") == "velyn agenda"


def test_normalize_strips_punctuation():
    assert normalize_thread_label("Velyn's agenda") == "velyns agenda"
    assert normalize_thread_label("the (secret) plan!") == "the secret plan"


def test_normalize_unusable_labels():
    assert normalize_thread_label(None) == ""
    assert normalize_thread_label(42) == ""
    assert normalize_thread_label("???") == ""
    assert normalize_thread_label("") == ""


def test_match_groups_case_and_separator_variants():
    thread = Thread(id="TH000", name="velyn agenda", labels=["velyn_agenda"])
    assert match_thread("Velyn's agenda", [thread]) is thread
    assert match_thread("VELYN AGENDA", [thread]) is thread
    assert match_thread("velyn-agenda", [thread]) is thread


def test_match_fuzzy_boundary():
    thread = Thread(id="TH000", name="data heist scope")
    # ratio("data heist scope", "data heist") is 0.769: below the 0.8
    # threshold, so a shared prefix alone does not merge strands.
    assert match_thread("data heist", [thread]) is None
    # A light plural/typo variant sits well above 0.8 and merges.
    inv = Thread(id="TH001", name="aris investigation")
    assert match_thread("Ariss investigations", [inv]) is inv


def test_match_distinct_labels_stay_distinct():
    threads = [
        Thread(id="TH000", name="aris investigation"),
        Thread(id="TH001", name="merger countdown"),
    ]
    assert match_thread("security monitoring", threads) is None
    assert match_thread("merger timeline", threads) is None  # ratio 0.52


def test_match_prefers_exact_over_fuzzy():
    fuzzy = Thread(id="TH000", name="velyns agenda")
    exact = Thread(id="TH001", name="velyn agenda")
    assert match_thread("velyn_agenda", [fuzzy, exact]) is exact


def test_match_learns_from_label_variants():
    # A raw variant recorded on the thread becomes matchable material.
    thread = Thread(id="TH000", name="velyn agenda", labels=["the Velyn conspiracy"])
    assert match_thread("velyn conspiracy", [thread]) is thread


def test_primary_label_is_first_usable():
    assert primary_label(_beat(threads=["a_thread", "b_thread"])) == "a_thread"
    assert primary_label(_beat(threads=["???", "b_thread"])) == "b_thread"
    assert primary_label(_beat(threads=[])) is None
    assert primary_label(None) is None


# ---------------------------------------------------------------------------
# Registry round-trip and counters
# ---------------------------------------------------------------------------

def test_attribution_creates_thread_and_round_trips(project):
    memory = MemoryManager(project)
    result = _registry(project, memory).attribute_scene(
        tick=2,
        scene_id="S002",
        beat=_beat("PB001", threads=["Velyn's agenda"], characters=["C000"], location="L001"),
        tension_level=6,
    )
    assert result["thread_id"] == "TH000"
    assert result["thread_name"] == "velyns agenda"
    assert result["created"] is True
    assert result["thread_count"] == 1
    assert result["run_length"] == 1

    # Fresh manager instance: the record survives on disk unchanged.
    threads = MemoryManager(project).load_threads()
    assert len(threads) == 1
    t = threads[0]
    assert t.id == "TH000"
    assert t.labels == ["Velyn's agenda"]
    assert t.member_characters == ["C000"]
    assert t.home_locations == ["L001"]
    assert t.beats_served == ["PB001"]
    assert t.scene_ids == ["S002"]
    assert t.tension_trace == [[2, 6]]
    assert t.last_active_tick == 2
    assert t.run_count == 1
    assert t.implicit is False


def test_thread_ids_come_from_shared_counters(project):
    memory = MemoryManager(project)
    assert memory.generate_id("thread") == "TH000"
    assert memory.generate_id("thread") == "TH001"
    # Counter persists across manager instances.
    assert MemoryManager(project).generate_id("thread") == "TH002"


def test_counter_reconciles_against_threads_on_disk(project):
    memory = MemoryManager(project)
    memory.save_threads([Thread(id="TH004", name="x")])
    # A stale counters.json (thread counter behind disk) must not reuse TH004.
    memory.counters["thread"] = 0
    memory._save_counters()
    assert MemoryManager(project).generate_id("thread") == "TH005"


def test_load_threads_missing_file_is_empty(project):
    memory = MemoryManager(project)
    assert memory.load_threads() == []
    # Lazy creation: no registry file until the first save.
    assert not memory.threads_file.exists()


# ---------------------------------------------------------------------------
# Per-tick attribution
# ---------------------------------------------------------------------------

def test_similar_labels_map_to_one_thread(project):
    memory = MemoryManager(project)
    registry = _registry(project, memory)
    first = registry.attribute_scene(
        tick=2, scene_id="S002", beat=_beat("PB001", threads=["velyn_agenda"]), tension_level=5)
    second = registry.attribute_scene(
        tick=3, scene_id="S003", beat=_beat("PB002", threads=["Velyn's agenda"]), tension_level=7)

    assert second["thread_id"] == first["thread_id"]
    assert second["created"] is False
    threads = memory.load_threads()
    assert len(threads) == 1
    assert threads[0].name == "velyn agenda"  # normalized first-seen label
    assert threads[0].labels == ["velyn_agenda", "Velyn's agenda"]
    assert threads[0].tension_trace == [[2, 5], [3, 7]]


def test_primary_label_wins_over_secondary(project):
    registry = _registry(project)
    result = registry.attribute_scene(
        tick=2, scene_id="S002",
        beat=_beat(threads=["aris_investigation", "merger_countdown"]))
    assert result["thread_name"] == "aris investigation"


def test_no_beat_attributes_to_implicit_main(project):
    memory = MemoryManager(project)
    result = _registry(project, memory).attribute_scene(tick=0, scene_id="S000", beat=None)
    assert result["thread_name"] == MAIN_THREAD_NAME
    threads = memory.load_threads()
    assert threads[0].implicit is True
    assert threads[0].tension_trace == [[0, None]]


def test_beat_without_labels_attributes_to_implicit_main(project):
    memory = MemoryManager(project)
    registry = _registry(project, memory)
    registry.attribute_scene(tick=0, scene_id="S000", beat=None)
    result = registry.attribute_scene(
        tick=1, scene_id="S001", beat=_beat("PB001", threads=[], characters=["C000"]))
    assert result["thread_name"] == MAIN_THREAD_NAME
    assert result["thread_count"] == 1  # reused, not a second main
    main = memory.load_threads()[0]
    assert main.beats_served == ["PB001"]
    assert main.member_characters == ["C000"]


def test_run_count_increments_and_resets(project):
    memory = MemoryManager(project)
    registry = _registry(project, memory)
    a = _beat("PB001", threads=["aris_investigation"])
    b = _beat("PB002", threads=["merger_countdown"])

    assert registry.attribute_scene(tick=2, scene_id="S002", beat=a)["run_length"] == 1
    assert registry.attribute_scene(tick=3, scene_id="S003", beat=a)["run_length"] == 2
    assert registry.attribute_scene(tick=4, scene_id="S004", beat=a)["run_length"] == 3
    # Switching threads resets the run.
    assert registry.attribute_scene(tick=5, scene_id="S005", beat=b)["run_length"] == 1
    # Coming back starts a fresh run, not a continuation of the old one.
    assert registry.attribute_scene(tick=6, scene_id="S006", beat=a)["run_length"] == 1

    by_name = {t.name: t for t in memory.load_threads()}
    assert by_name["aris investigation"].run_count == 1  # as of its last activity
    assert by_name["merger countdown"].run_count == 1


def test_members_union_across_scenes(project):
    memory = MemoryManager(project)
    registry = _registry(project, memory)
    registry.attribute_scene(
        tick=2, scene_id="S002",
        beat=_beat("PB001", threads=["t"], characters=["C000", "C001"], location="L000"))
    registry.attribute_scene(
        tick=3, scene_id="S003",
        beat=_beat("PB002", threads=["t"], characters=["C001", "C002"], location="L001"))
    thread = memory.load_threads()[0]
    assert thread.member_characters == ["C000", "C001", "C002"]
    assert thread.home_locations == ["L000", "L001"]
    assert thread.beats_served == ["PB001", "PB002"]


def test_retried_tick_last_wins(project):
    memory = MemoryManager(project)
    registry = _registry(project, memory)
    registry.attribute_scene(tick=2, scene_id="S002", beat=_beat("PB001", threads=["t_a"]),
                             tension_level=5)
    # The tick fails downstream and is retried with a different beat.
    result = registry.attribute_scene(tick=2, scene_id="S002",
                                      beat=_beat("PB002", threads=["t_b"]), tension_level=6)
    assert result["run_length"] == 1
    combined = [(e[0], t.name) for t in memory.load_threads() for e in t.tension_trace]
    assert combined == [(2, "t b")]  # one entry for tick 2, last attribution wins


def test_compute_current_run_empty():
    assert compute_current_run([]) == (None, 0)


# ---------------------------------------------------------------------------
# Graceful paths
# ---------------------------------------------------------------------------

def test_unreadable_registry_returns_none(project):
    memory = MemoryManager(project)
    memory.threads_file.write_text("{not json", encoding="utf-8")
    # MemoryManager construction over the corrupt file must also survive
    # (the counter reconciliation reads threads.json).
    memory = MemoryManager(project)
    result = _registry(project, memory).attribute_scene(
        tick=2, scene_id="S002", beat=_beat(threads=["t"]))
    assert result is None


def test_attribution_never_raises_on_bad_memory(project):
    class BrokenMemory:
        def load_threads(self):
            raise RuntimeError("disk on fire")

    registry = ThreadRegistry(BrokenMemory(), Config())
    assert registry.attribute_scene(tick=2, scene_id="S002", beat=None) is None


# ---------------------------------------------------------------------------
# Metrics fields (the rubric's never-break pattern)
# ---------------------------------------------------------------------------

class FakeVector:
    def compute_semantic_similarity(self, a, b):
        return 0.5


def _metrics(project_dir):
    return CoherenceMetrics(project_dir, MemoryManager(project_dir), FakeVector(), Config())


def test_metrics_thread_fields_recorded(project):
    (project / "memory").mkdir(exist_ok=True)
    rec = _metrics(project).record_tick(
        tick=3, scene_id="S003",
        thread_result={"thread_id": "TH000", "thread_name": "velyn agenda",
                       "created": False, "thread_count": 2, "run_length": 3},
    )
    assert rec["active_thread"] == "velyn agenda"
    assert rec["thread_count"] == 2
    assert rec["thread_run_length"] == 3


def test_metrics_thread_fields_none_when_unavailable(project):
    (project / "memory").mkdir(exist_ok=True)
    rec = _metrics(project).record_tick(tick=3, scene_id="S003")
    assert rec["active_thread"] is None
    assert rec["thread_count"] is None
    assert rec["thread_run_length"] is None


# ---------------------------------------------------------------------------
# CLI rendering (novel threads)
# ---------------------------------------------------------------------------

def test_get_threads_info_empty_project(project):
    info = get_threads_info(project)
    assert info["count"] == 0
    assert info["threads"] == []


def test_get_threads_info_reads_registry_without_mutation(project):
    memory = MemoryManager(project)
    _registry(project, memory).attribute_scene(
        tick=2, scene_id="S002", beat=_beat(threads=["velyn_agenda"]), tension_level=6)
    before = memory.threads_file.read_text(encoding="utf-8")
    info = get_threads_info(project)
    assert info["count"] == 1
    assert info["threads"][0]["name"] == "velyn agenda"
    assert memory.threads_file.read_text(encoding="utf-8") == before


def test_get_threads_info_corrupt_file_is_graceful(project):
    (project / "memory").mkdir(exist_ok=True)
    (project / "memory" / "threads.json").write_text("{not json", encoding="utf-8")
    assert get_threads_info(project)["count"] == 0


def test_display_threads_listing(project, capsys):
    memory = MemoryManager(project)
    registry = _registry(project, memory)
    registry.attribute_scene(tick=0, scene_id="S000", beat=None)
    registry.attribute_scene(
        tick=2, scene_id="S002",
        beat=_beat("PB001", threads=["velyn_agenda"], characters=["C000"], location="L001"),
        tension_level=4)
    registry.attribute_scene(
        tick=3, scene_id="S003",
        beat=_beat("PB002", threads=["Velyn's agenda"], characters=["C002"]),
        tension_level=8)

    display_threads(get_threads_info(project), use_color=False)
    out = capsys.readouterr().out
    assert "Story Threads" in out
    assert "(2 tracked)" in out
    assert "main (implicit)" in out
    assert "velyn agenda" in out
    assert "tension: 4-8" in out
    assert "ticks: 2-3" in out
    assert "members: C000, C002" in out
    assert "locations: L001" in out
    assert "label variants: velyn_agenda, Velyn's agenda" in out
    assert "beats: PB001, PB002" in out


def test_display_threads_empty(project, capsys):
    display_threads(get_threads_info(project), use_color=False)
    out = capsys.readouterr().out
    assert "No threads tracked yet" in out


def test_display_threads_json(project, capsys):
    memory = MemoryManager(project)
    _registry(project, memory).attribute_scene(
        tick=2, scene_id="S002", beat=_beat(threads=["t"]), tension_level=5)
    display_threads_json(get_threads_info(project))
    out = capsys.readouterr().out
    assert '"name": "t"' in out
    assert '"tension_trace"' in out

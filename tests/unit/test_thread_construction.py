"""Unit tests for the construction-pressure detector (Phase 3, interleaving Slice T4a).

Instrument-only: the detector computes whether thread construction WOULD fire
(docs/THREAD_CONSTRUCTION_DESIGN.md section 2) and never changes behavior.
"""

from types import SimpleNamespace

from novel_agent.agent.thread_construction import (
    derive_thread_min_run,
    effective_thread_count,
    evaluate_construction_pressure,
    runway_floor,
)


class FakeConfig:
    """Minimal dot-notation config for testing."""

    def __init__(self, values=None):
        self._v = dict(values or {})

    def get(self, key, default=None):
        return self._v.get(key, default)


class FakeMemory:
    def __init__(self, threads=None, raises=False):
        self._threads = threads or []
        self.raises = raises

    def load_threads(self):
        if self.raises:
            raise RuntimeError("ledger corrupt")
        return self._threads


def _thread(tid="TH000", scene_ids=None, trace=None):
    return SimpleNamespace(id=tid, scene_ids=scene_ids or [], tension_trace=trace or [])


def _cfg(length=15, **extra):
    values = {"coherence.target_story_length": length}
    values.update(extra)
    return FakeConfig(values)


ONE_THREAD = [_thread(scene_ids=["S001", "S002"], trace=[[1, 5], [2, 6]])]
TWO_THREADS = [
    _thread("TH000", scene_ids=["S001"], trace=[[1, 8], [2, 9]]),
    _thread("TH001", scene_ids=["S002"], trace=[[3, 8], [4, 9]]),
]


# ---- derivation arithmetic (section 2.3: masters blocks at ~20 percent) ------

def test_derive_thread_min_run_from_story_length():
    assert derive_thread_min_run(15) == 3    # the spec's worked example
    assert derive_thread_min_run(24) == 5
    assert derive_thread_min_run(40) == 8


def test_derive_thread_min_run_floor_and_garbage():
    assert derive_thread_min_run(5) == 2     # round(1) lifted to the floor
    assert derive_thread_min_run(0) == 2
    assert derive_thread_min_run(None) == 2
    assert derive_thread_min_run("many") == 2


def test_runway_floor_derived_and_explicit():
    # Derived: 2 * 3 + 1 + 1 = 8 at length 15 (the spec's arithmetic).
    assert runway_floor(_cfg(15), 15) == 8
    assert runway_floor(_cfg(24), 24) == 12
    # An explicit thread_min_run overrides the derivation: 2 * 5 + 1 + 1 = 12.
    assert runway_floor(_cfg(15, **{"coherence.thread_min_run": 5}), 15) == 12
    # A non-positive or garbage explicit value falls back to the derivation.
    assert runway_floor(_cfg(15, **{"coherence.thread_min_run": 0}), 15) == 8
    assert runway_floor(_cfg(15, **{"coherence.thread_min_run": "three"}), 15) == 8


def test_effective_thread_count_ignores_unserved_threads():
    assert effective_thread_count([]) == 0
    assert effective_thread_count([_thread()]) == 0          # minted, never served
    assert effective_thread_count(ONE_THREAD) == 1
    assert effective_thread_count(ONE_THREAD + [_thread("TH001")]) == 1
    assert effective_thread_count(TWO_THREADS) == 2


# ---- diversity trigger truth table -------------------------------------------

def test_gate_off_returns_none():
    cfg = _cfg(15, **{"coherence.thread_construction_detector": False})
    assert evaluate_construction_pressure(FakeMemory(ONE_THREAD), cfg, 6) is None


def test_no_story_length_never_fires():
    for length in (None, 0, -3, "novel"):
        res = evaluate_construction_pressure(FakeMemory(ONE_THREAD), _cfg(length), 6)
        assert res["would_fire"] is False
        assert res["trigger"] is None
        assert "story length" in res["reason"]
        assert res["story_fraction"] is None
        assert res["runway"] is None
        assert res["thread_count"] is None


def test_fires_inside_window_with_one_thread():
    # Tick 6 of 15: fraction 0.4, runway 9 >= floor 8.
    res = evaluate_construction_pressure(FakeMemory(ONE_THREAD), _cfg(15), 6)
    assert res["would_fire"] is True
    assert res["trigger"] == "diversity"
    assert res["reason"] == "diversity (1 thread at 40 percent)"
    assert res["story_fraction"] == 0.4
    assert res["thread_count"] == 1
    assert res["runway"] == 9


def test_before_construction_floor_stays_silent():
    # Tick 1 of 15: fraction 0.067 < 0.15.
    res = evaluate_construction_pressure(FakeMemory(ONE_THREAD), _cfg(15), 1)
    assert res["would_fire"] is False
    assert res["trigger"] is None
    assert "construction floor" in res["reason"]
    assert res["thread_count"] == 1     # fields still populated on a no-fire tick


def test_floor_boundary_is_inclusive():
    # Tick 3 of 20: fraction exactly 0.15 sits inside the window.
    res = evaluate_construction_pressure(FakeMemory(ONE_THREAD), _cfg(20), 3)
    assert res["would_fire"] is True
    assert res["reason"] == "diversity (1 thread at 15 percent)"


def test_past_construction_cutoff_stays_silent():
    # Tick 9 of 15: fraction 0.6 > 0.5. Late calm comes from sequencing.
    res = evaluate_construction_pressure(FakeMemory(ONE_THREAD), _cfg(15), 9)
    assert res["would_fire"] is False
    assert "cutoff" in res["reason"]


def test_cutoff_boundary_is_inclusive():
    # Tick 10 of 20: fraction exactly 0.5, runway 10 >= floor 10 (min_run 4).
    res = evaluate_construction_pressure(FakeMemory(ONE_THREAD), _cfg(20), 10)
    assert res["would_fire"] is True


def test_runway_floor_blocks_inside_window():
    # Length 10: tick 5 is fraction 0.5 (in window) but runway 5 < floor 6
    # (derived min_run 2: 2 + 2 + 1 + 1).
    res = evaluate_construction_pressure(FakeMemory(ONE_THREAD), _cfg(10), 5)
    assert res["would_fire"] is False
    assert "runway too short" in res["reason"]
    assert res["runway"] == 5


def test_explicit_min_run_raises_the_runway_floor():
    # Tick 5 of 15 fires with the derived floor (runway 10 >= 8) but an
    # explicit thread_min_run of 5 lifts the floor to 12 and blocks it.
    fires = evaluate_construction_pressure(FakeMemory(ONE_THREAD), _cfg(15), 5)
    assert fires["would_fire"] is True
    blocked = evaluate_construction_pressure(
        FakeMemory(ONE_THREAD), _cfg(15, **{"coherence.thread_min_run": 5}), 5)
    assert blocked["would_fire"] is False
    assert "runway too short" in blocked["reason"]


def test_custom_window_fractions_respected():
    cfg = _cfg(15, **{"coherence.construction_floor": 0.3,
                      "coherence.construction_cutoff": 0.45})
    # Tick 4 of 15 = 0.267 < 0.3: below the custom floor.
    assert evaluate_construction_pressure(FakeMemory(ONE_THREAD), cfg, 4)["would_fire"] is False
    # Tick 5 of 15 = 0.333: inside.
    assert evaluate_construction_pressure(FakeMemory(ONE_THREAD), cfg, 5)["would_fire"] is True
    # Tick 7 of 15 = 0.467 > 0.45: past the custom cutoff.
    assert evaluate_construction_pressure(FakeMemory(ONE_THREAD), cfg, 7)["would_fire"] is False


def test_two_effective_threads_satisfy_diversity():
    res = evaluate_construction_pressure(FakeMemory(TWO_THREADS), _cfg(15), 6)
    assert res["would_fire"] is False
    assert res["trigger"] is None
    assert "diversity satisfied" in res["reason"]
    assert res["thread_count"] == 2


def test_no_attributed_scenes_stays_silent():
    # An empty registry and a minted-but-never-served thread are both count 0.
    for threads in ([], [_thread()]):
        res = evaluate_construction_pressure(FakeMemory(threads), _cfg(15), 6)
        assert res["would_fire"] is False
        assert "no attributed scenes" in res["reason"]
        assert res["thread_count"] == 0


def test_unserved_thread_does_not_break_diversity():
    # One served thread plus a minted-but-unserved one is still effective 1.
    threads = ONE_THREAD + [_thread("TH001")]
    res = evaluate_construction_pressure(FakeMemory(threads), _cfg(15), 6)
    assert res["would_fire"] is True
    assert res["thread_count"] == 1


def test_registry_unreadable_degrades_gracefully():
    res = evaluate_construction_pressure(FakeMemory(raises=True), _cfg(15), 6)
    assert res["would_fire"] is False
    assert res["trigger"] is None
    assert "thread ledger unreadable" in res["reason"]
    assert res["thread_count"] is None
    assert res["story_fraction"] == 0.4     # computed before the registry read


# ---- demand-gap trigger (demoted: experimental, opt-in) ----------------------

# A curve with a mid-story calm valley: tick 8 of 20 looks ahead over targets
# descending to 3 at progress 0.5.
VALLEY_CURVE = [[0.0, 8], [0.5, 3], [1.0, 9]]


def _demand_cfg(**extra):
    values = {
        "coherence.target_story_length": 20,
        "coherence.target_tension_curve": VALLEY_CURVE,
        "coherence.demand_gap_trigger": True,
    }
    values.update(extra)
    return FakeConfig(values)


def test_demand_gap_off_by_default():
    cfg = FakeConfig({"coherence.target_story_length": 20,
                      "coherence.target_tension_curve": VALLEY_CURVE})
    res = evaluate_construction_pressure(FakeMemory(TWO_THREADS), cfg, 8)
    assert res["would_fire"] is False
    assert "demand-gap trigger off" in res["reason"]


def test_demand_gap_fires_when_no_thread_can_serve_calm():
    # Both threads run hot (recent mean 8.5); the horizon's min target is 3.
    res = evaluate_construction_pressure(FakeMemory(TWO_THREADS), _demand_cfg(), 8)
    assert res["would_fire"] is True
    assert res["trigger"] == "demand_gap"
    assert "experimental" in res["reason"]


def test_demand_gap_silent_when_a_thread_can_serve():
    threads = [
        _thread("TH000", scene_ids=["S001"], trace=[[1, 8], [2, 9]]),
        _thread("TH001", scene_ids=["S002"], trace=[[3, 4], [4, 3]]),  # mean 3.5
    ]
    res = evaluate_construction_pressure(FakeMemory(threads), _demand_cfg(), 8)
    assert res["would_fire"] is False
    assert "can serve" in res["reason"]


def test_demand_gap_silent_without_calm_demand():
    # A rising curve keeps every horizon target above the calm threshold.
    cfg = _demand_cfg(**{"coherence.target_tension_curve": [[0.0, 5], [1.0, 9]]})
    res = evaluate_construction_pressure(FakeMemory(TWO_THREADS), cfg, 8)
    assert res["would_fire"] is False
    assert "no calm demand" in res["reason"]


def test_demand_gap_silent_when_curve_disabled():
    cfg = _demand_cfg(**{"coherence.target_tension_curve": None})
    res = evaluate_construction_pressure(FakeMemory(TWO_THREADS), cfg, 8)
    assert res["would_fire"] is False
    assert "arc-pressure disabled" in res["reason"]


def test_diversity_stays_primary_over_demand_gap():
    # One thread inside the window: the diversity trigger reports, even with
    # the experimental trigger on and calm demand present.
    res = evaluate_construction_pressure(FakeMemory(ONE_THREAD), _demand_cfg(), 8)
    assert res["would_fire"] is True
    assert res["trigger"] == "diversity"


def test_demand_gap_respects_window_and_runway():
    # Past the cutoff, the demand-gap never evaluates (same window as 2.1).
    res = evaluate_construction_pressure(FakeMemory(TWO_THREADS), _demand_cfg(), 11)
    assert res["would_fire"] is False
    assert "cutoff" in res["reason"]


# ---- the thin agent hook ------------------------------------------------------

def _agent(memory, config):
    from novel_agent.agent.agent import StoryAgent
    a = StoryAgent.__new__(StoryAgent)  # bypass __init__; the hook reads only these attrs
    a.memory = memory
    a.config = config
    return a


def test_hook_prints_console_line_on_would_fire(capsys):
    a = _agent(FakeMemory(ONE_THREAD), _cfg(15))
    res = a._detect_construction_pressure(6)
    assert res["would_fire"] is True
    out = capsys.readouterr().out
    assert "Construction pressure would fire: diversity (1 thread at 40 percent)" in out


def test_hook_silent_on_no_fire_tick(capsys):
    a = _agent(FakeMemory(ONE_THREAD), _cfg(15))
    res = a._detect_construction_pressure(1)
    assert res["would_fire"] is False
    assert "Construction pressure" not in capsys.readouterr().out


def test_hook_returns_none_when_gate_off():
    cfg = _cfg(15, **{"coherence.thread_construction_detector": False})
    assert _agent(FakeMemory(ONE_THREAD), cfg)._detect_construction_pressure(6) is None


def test_hook_never_raises(monkeypatch, capsys):
    import novel_agent.agent.thread_construction as tc

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(tc, "evaluate_construction_pressure", boom)
    a = _agent(FakeMemory(ONE_THREAD), _cfg(15))
    assert a._detect_construction_pressure(6) is None  # swallowed, tick survives

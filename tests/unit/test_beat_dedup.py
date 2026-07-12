"""Beat-level dedup at authoring time (Phase 3 hardening).

The shared helper (novel_agent/plot/dedup.py) drops a freshly authored beat
whose description fuzzy-matches a pending / recently completed beat or an
earlier beat in the same batch, before it reaches the outline
(docs/progress_report_20260712.md section 8.2: the duplicated PB005/PB006 pair
became ~9,200 characters of verbatim prose plus duplicate loops downstream).

The calibration fixtures below are VERBATIM beat descriptions from the scored
runs in work/, so the threshold tests measure exactly what the live gauge
measured; if the gauge or threshold drifts under these specimens, that is a
real recalibration, not a fixture nit.
"""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.configs.config import Config
from novel_agent.plot.dedup import (
    MIN_DEDUP_WORDS,
    RECENTLY_COMPLETED_WINDOW,
    beat_similarity,
    dedup_new_beats,
)
from novel_agent.plot.entities import PlotBeat
from novel_agent.plot.manager import PlotOutlineManager

# The real offending pair (triple-run_ec75ee96 PB005/PB006): PB006 was authored
# at tick 6 while PB005 was still pending, and the duplicate beat produced the
# verbatim-prose defect. Plain difflib ratio 0.521; the calibrated
# max(plain, sorted-token) gauge measures 0.697.
DUP_PENDING = ("Zelox confronts Darol about her involvement in the investigation, "
               "forcing her to decide whether to trust her manager.")
DUP_AUTHORED = ("Zelox confronts Darol about her investigation and suspicious data "
                "access patterns, testing whether she will reveal her findings or "
                "deny involvement.")

# A legitimately distinct SAME-BATCH pair (grantrate-run_39a993f0 PB001/PB005,
# both authored in batch 1): plain ratio 0.513, calibrated gauge 0.513. This is
# the pair that forbids a plain-ratio threshold anywhere near the duplicate.
DISTINCT_A = ("Taliaoss questions Celira about her discovery methods and access "
              "to the Lower Vernholt server room.")
DISTINCT_B = ("Taliaoss informs Celira that the merger closing has been "
              "accelerated to three days away.")

# The finale pair (triple-run PB014 pending / PB015 authored by the sacred
# finale): distinct denouement beats at gauge 0.475; the dedup must never eat
# the sacred finale's authored replacement.
FINALE_PENDING = ("Six months later, Darol testifies at the regulatory hearing as "
                  "the merger is dissolved and criminal charges are filed against "
                  "Brixoth and complicit executives.")
FINALE_AUTHORED = ("Weeks later, Darol reviews the regulatory findings at her "
                   "workstation, vindicated but forever changed.")


def _config(**overrides):
    config = Config()
    for key, value in overrides.items():
        config.set(key, value)
    return config


def _beat(description, beat_id="", status="pending"):
    return PlotBeat(id=beat_id, description=description, status=status)


# ---------------------------------------------------------------------------
# Gauge calibration (locks the measured separation the threshold rests on)
# ---------------------------------------------------------------------------

def test_real_duplicate_pair_measures_above_default_threshold():
    similarity = beat_similarity(DUP_PENDING, DUP_AUTHORED)
    threshold = Config().get('generation.beat_dedup_threshold')
    assert threshold == 0.65
    assert similarity >= threshold
    assert similarity == pytest.approx(0.697, abs=0.005)


def test_distinct_pairs_measure_below_default_threshold():
    threshold = Config().get('generation.beat_dedup_threshold')
    assert beat_similarity(DISTINCT_A, DISTINCT_B) < threshold
    assert beat_similarity(FINALE_PENDING, FINALE_AUTHORED) < threshold


def test_similarity_is_case_insensitive_and_bounded():
    assert beat_similarity(DUP_PENDING, DUP_PENDING.upper()) == 1.0
    assert beat_similarity("", DUP_PENDING) == 0.0


# ---------------------------------------------------------------------------
# Cross-batch dedup (against pending / recently completed beats)
# ---------------------------------------------------------------------------

def test_duplicate_of_pending_beat_dropped_with_warning():
    existing = [_beat(DUP_PENDING, beat_id="PB005", status="pending")]
    kept, warnings = dedup_new_beats(
        [_beat(DUP_AUTHORED, beat_id="PB006")], existing, _config())
    assert kept == []
    assert len(warnings) == 1
    assert "PB006" in warnings[0] and "PB005" in warnings[0]
    assert "duplicate" in warnings[0]


def test_distinct_beat_kept_against_pending():
    existing = [_beat(DISTINCT_A, beat_id="PB001", status="pending")]
    new = _beat(DISTINCT_B, beat_id="PB005")
    kept, warnings = dedup_new_beats([new], existing, _config())
    assert kept == [new]
    assert warnings == []


def test_finale_authored_beat_survives_the_superseded_pending_beat():
    # The sacred finale persists its authored beat via add_beats while the
    # bypassed beat stays pending; the dedup window sees it and must keep the
    # replacement (measured gauge 0.475, well under 0.65).
    existing = [_beat(FINALE_PENDING, beat_id="PB014", status="pending")]
    new = _beat(FINALE_AUTHORED, beat_id="PB015")
    kept, warnings = dedup_new_beats([new], existing, _config())
    assert kept == [new]
    assert warnings == []


def test_duplicate_of_recently_completed_beat_dropped():
    existing = [_beat(DUP_PENDING, beat_id="PB005", status="completed")]
    kept, warnings = dedup_new_beats(
        [_beat(DUP_AUTHORED, beat_id="PB006")], existing, _config())
    assert kept == []
    assert len(warnings) == 1


def test_old_completed_beats_leave_the_window():
    # A beat completed longer than RECENTLY_COMPLETED_WINDOW ago is legitimate
    # history the story may echo; only the recent tail participates.
    existing = [_beat(DUP_PENDING, beat_id="PB001", status="completed")]
    existing += [_beat(f"Filler beat number {i} advancing an unrelated investigation thread.",
                       beat_id=f"PB{i:03d}", status="completed")
                 for i in range(2, 2 + RECENTLY_COMPLETED_WINDOW)]
    new = _beat(DUP_AUTHORED, beat_id="PB009")
    kept, warnings = dedup_new_beats([new], existing, _config())
    assert kept == [new]
    assert warnings == []


def test_abandoned_and_skipped_beats_are_not_candidates():
    existing = [_beat(DUP_PENDING, beat_id="PB005", status="abandoned"),
                _beat(DUP_PENDING, beat_id="PB006", status="skipped")]
    new = _beat(DUP_AUTHORED, beat_id="PB007")
    kept, warnings = dedup_new_beats([new], existing, _config())
    assert kept == [new]
    assert warnings == []


# ---------------------------------------------------------------------------
# Within-batch dedup
# ---------------------------------------------------------------------------

def test_within_batch_duplicate_dropped_first_kept():
    first = _beat(DUP_PENDING, beat_id="PB010")
    second = _beat(DUP_AUTHORED, beat_id="PB011")
    kept, warnings = dedup_new_beats([first, second], [], _config())
    assert kept == [first]
    assert len(warnings) == 1
    assert "PB011" in warnings[0] and "PB010" in warnings[0]


def test_within_batch_distinct_beats_all_kept():
    batch = [_beat(DISTINCT_A, beat_id="PB001"), _beat(DISTINCT_B, beat_id="PB002")]
    kept, warnings = dedup_new_beats(batch, [], _config())
    assert kept == batch
    assert warnings == []


# ---------------------------------------------------------------------------
# Gate, threshold boundary, and graceful degradation
# ---------------------------------------------------------------------------

def test_gate_off_keeps_all_beats():
    existing = [_beat(DUP_PENDING, beat_id="PB005", status="pending")]
    batch = [_beat(DUP_AUTHORED, beat_id="PB006"), _beat(DUP_AUTHORED, beat_id="PB007")]
    kept, warnings = dedup_new_beats(
        batch, existing, _config(**{"generation.beat_dedup": False}))
    assert kept == batch
    assert warnings == []


def test_threshold_boundary_is_inclusive():
    # Computed in the helper's comparison order (new beat, then existing):
    # SequenceMatcher ratios are not symmetric in argument order.
    similarity = beat_similarity(DUP_AUTHORED, DUP_PENDING)
    existing = [_beat(DUP_PENDING, beat_id="PB005", status="pending")]

    at_threshold = _config(**{"generation.beat_dedup_threshold": similarity})
    kept, _ = dedup_new_beats([_beat(DUP_AUTHORED)], existing, at_threshold)
    assert kept == []

    above = _config(**{"generation.beat_dedup_threshold": similarity + 0.0001})
    kept, warnings = dedup_new_beats([_beat(DUP_AUTHORED)], existing, above)
    assert len(kept) == 1
    assert warnings == []


def test_short_descriptions_exempt_from_the_gauge():
    # difflib is noise on very short strings ("beat 1" vs "beat 2" measures
    # 0.833); descriptions under MIN_DEDUP_WORDS words never dedup.
    short = " ".join(["word"] * (MIN_DEDUP_WORDS - 1))
    batch = [_beat("beat 1"), _beat("beat 2"), _beat(short), _beat(short)]
    kept, warnings = dedup_new_beats(batch, [_beat("beat 3", status="pending")],
                                     _config())
    assert kept == batch
    assert warnings == []


def test_never_raises_keeps_all_beats_on_failure():
    class BrokenConfig:
        def get(self, key, default=None):
            raise RuntimeError("config unreadable")

    existing = [_beat(DUP_PENDING, beat_id="PB005", status="pending")]
    batch = [_beat(DUP_AUTHORED, beat_id="PB006")]
    kept, warnings = dedup_new_beats(batch, existing, BrokenConfig())
    assert kept == batch
    assert warnings == []


# ---------------------------------------------------------------------------
# Wiring: the agent path's add_beats runs the dedup (the CLI path calls the
# same shared helper next to its other sanitizers)
# ---------------------------------------------------------------------------

@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text(json.dumps({"current_tick": 6, "novel_name": "N"}))
    yield d
    shutil.rmtree(d, ignore_errors=True)


def test_add_beats_drops_duplicate_of_pending_beat(project, capsys):
    config = _config()
    manager = PlotOutlineManager(project, None, config)
    manager.add_beats([_beat(DUP_PENDING)])

    added = manager.add_beats([_beat(DUP_AUTHORED), _beat(DISTINCT_B)])

    assert len(added) == 1
    assert added[0].description == DISTINCT_B
    persisted = manager.load_outline().beats
    assert [b.description for b in persisted] == [DUP_PENDING, DISTINCT_B]
    assert "dropped duplicate beat" in capsys.readouterr().out


def test_add_beats_gate_off_keeps_duplicate(project):
    config = _config(**{"generation.beat_dedup": False})
    manager = PlotOutlineManager(project, None, config)
    manager.add_beats([_beat(DUP_PENDING)])

    added = manager.add_beats([_beat(DUP_AUTHORED)])

    assert len(added) == 1
    assert len(manager.load_outline().beats) == 2

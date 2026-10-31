"""Judged deaths and destruction: claims are checked, judged, then enforced."""

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.agent import keep_pov_alive
from novel_agent.agent.consequences import (apply_status_changes, evidence_in_scene,
                                            status_change_rules)
from novel_agent.agent.fact_extractor import FactExtractor
from novel_agent.agent.story_context import cast_roster, location_roster
from novel_agent.agent.writer_context import WriterContextBuilder
from novel_agent.configs.config import Config
from novel_agent.memory.entities import Character, Location
from novel_agent.memory.entity_resolver import EntityResolver
from novel_agent.memory.entity_status import is_unavailable, status_of
from novel_agent.memory.manager import MemoryManager
from novel_agent.plot.entities import PlotBeat

SCENE = ("The reactor blew at dawn. The Kestrel broke apart over the ridge, "
         "and Brann did not get out. Elil watched the wreckage burn.")


class Judge:
    def __init__(self, verdict=True):
        self.verdict = verdict
        self.calls = 0

    def generate(self, prompt, max_tokens=None):
        self.calls += 1
        return json.dumps({"confirmed": self.verdict, "reason": "shown on the page"})


@pytest.fixture
def project():
    d = Path(tempfile.mkdtemp())
    mm = MemoryManager(d)
    mm.save_character(Character(id="C000", first_name="Elil", role="protagonist"))
    mm.save_character(Character(id="C001", first_name="Brann", role="supporting"))
    mm.save_location(Location(id="L000", name="The Kestrel"))
    yield d, mm
    shutil.rmtree(d, ignore_errors=True)


def test_evidence_must_be_on_the_page():
    assert evidence_in_scene("“The Kestrel broke apart over the ridge”", SCENE)
    assert not evidence_in_scene("Brann was killed in the blast", SCENE)
    assert not evidence_in_scene("blew", SCENE)  # too short to point at anything


def test_confirmed_claims_apply_and_are_enforced(project):
    d, mm = project
    claims = [{"id": "C001", "status": "dead", "evidence": "Brann did not get out."},
              {"id": "L000", "status": "destroyed", "evidence": "The Kestrel broke apart over the ridge"}]
    result = apply_status_changes(Judge(), mm, claims, 7, "S007", SCENE, Config())
    assert [c["id"] for c in result["applied"]] == ["C001", "L000"]

    brann = mm.load_character("C001")
    assert status_of(brann) == "dead" and is_unavailable(brann)
    assert brann.metadata["status"]["scene_id"] == "S007"
    assert brann.history[-1].changes == {"status": "dead"}
    assert status_of(mm.load_location("L000")) == "destroyed"

    # Rosters mark them; beats can no longer require Brann.
    assert "C001: Brann (supporting) (deceased, S007)" in cast_roster(mm)
    assert "L000: The Kestrel (destroyed, S007)" in location_roster(mm)
    beat = PlotBeat(id="PB001", description="x", characters_involved=["C000", "Brann"])
    dropped, _ = EntityResolver(mm).resolve_beat(beat)
    assert beat.characters_involved == ["C000"] and dropped == ["Brann (dead or missing)"]

    # The writer is told, in the location block and in the canon.
    (d / "state.json").write_text(json.dumps({"current_tick": 8}))
    wcb = WriterContextBuilder(mm, None, Config())
    _, details = wcb._get_location_details("L000")
    assert "**Status:** destroyed in S007" in details
    assert "- Brann: deceased in S007" in wcb._departed_entities()


def test_unchecked_claims_are_refused_without_a_judge_call(project):
    _, mm = project
    judge = Judge()
    claims = [{"id": "C009", "status": "dead", "evidence": "Brann did not get out."},
              {"id": "C001", "status": "destroyed", "evidence": "Brann did not get out."},
              {"id": "C000", "status": "alive", "evidence": "Elil watched the wreckage burn."},
              {"id": "C001", "status": "dead", "evidence": "Brann died a hero."}]
    result = apply_status_changes(judge, mm, claims, 7, "S007", SCENE, Config())
    assert result["applied"] == []
    assert [r["why"] for r in result["refused"]] == [
        "unknown id", "status not valid for this kind of entity", "unchanged",
        "evidence not found in the scene"]
    assert judge.calls == 0


def test_judge_no_leaves_status_alone(project):
    _, mm = project
    result = apply_status_changes(Judge(verdict=False), mm,
                                  [{"id": "C001", "status": "dead", "evidence": "Brann did not get out."}],
                                  7, "S007", SCENE, Config())
    assert result["applied"] == [] and result["refused"][0]["why"].startswith("judge:")
    assert status_of(mm.load_character("C001")) == "alive"


def test_gate_off_changes_nothing(project):
    _, mm = project
    cfg = Config()
    cfg.set("coherence.entity_status", False)
    assert status_change_rules(cfg) == ""
    assert apply_status_changes(Judge(), mm, [{"id": "C001", "status": "dead",
                                               "evidence": "Brann did not get out."}],
                                7, "S007", SCENE, cfg) is None


def test_dead_pov_falls_back_to_living_active_character(project):
    _, mm = project
    apply_status_changes(Judge(), mm, [{"id": "C001", "status": "dead",
                                        "evidence": "Brann did not get out."}], 7, "S007", SCENE, Config())
    plan = {"pov_character": "C001"}
    keep_pov_alive(mm, {"active_character": "C000"}, plan)
    assert plan["pov_character"] == "C000"


def test_extraction_prompt_carries_roster_and_rules(project):
    _, mm = project
    prompt = FactExtractor(None, mm, Config())._build_extraction_prompt(
        SCENE, {"pov_character_id": "C000", "location_id": "L000"})
    assert "- C001: Brann (supporting)" in prompt
    assert '"status_changes"' in prompt
    parsed = FactExtractor(None, mm, Config())._parse_extraction_response(
        json.dumps({"status_changes": [{"id": "C001", "status": "dead", "evidence": "x"}]}))
    assert parsed["status_changes"][0]["id"] == "C001"
    assert "status_changes" not in FactExtractor(None, mm, Config())._parse_extraction_response("{}")


def test_beat_written_before_a_death_drops_the_dead_when_picked(project):
    from novel_agent.plot.entities import PlotOutline
    from novel_agent.plot.manager import PlotOutlineManager
    d, mm = project
    manager = PlotOutlineManager(d, None, Config())
    beat = PlotBeat(id="PB001", description="Elil and Brann search the wreck",
                    characters_involved=["C000", "C001"])
    manager.save_outline(PlotOutline(beats=[beat]))

    # While Brann is alive the beat keeps him.
    assert manager.get_next_beat().characters_involved == ["C000", "C001"]

    apply_status_changes(Judge(), mm, [{"id": "C001", "status": "dead",
                                        "evidence": "Brann did not get out."}],
                         7, "S007", SCENE, Config())
    assert manager.get_next_beat().characters_involved == ["C000"]


class RefiningJudge(Judge):
    def __init__(self, status):
        super().__init__(True)
        self.status = status
        self.prompts = []

    def generate(self, prompt, max_tokens=None):
        self.prompts.append(prompt)
        return json.dumps({"confirmed": True, "status": self.status, "reason": "a vented ruin"})


def test_judge_picks_destroyed_over_a_claimed_inaccessible(project):
    _, mm = project
    judge = RefiningJudge("destroyed")
    claims = [{"id": "L000", "status": "inaccessible",
               "evidence": "The Kestrel broke apart over the ridge"}]
    result = apply_status_changes(judge, mm, claims, 7, "S007", SCENE, Config())
    assert result["applied"][0]["status"] == "destroyed"
    assert status_of(mm.load_location("L000")) == "destroyed"
    assert '"destroyed" (ruined' in judge.prompts[0]


def test_judge_cannot_turn_a_loss_into_a_restoration(project):
    _, mm = project
    claims = [{"id": "C001", "status": "dead", "evidence": "Brann did not get out."}]
    apply_status_changes(RefiningJudge("alive"), mm, claims, 7, "S007", SCENE, Config())
    assert status_of(mm.load_character("C001")) == "dead"

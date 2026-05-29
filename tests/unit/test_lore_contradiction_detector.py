"""Unit tests for LLM-judged lore contradiction detection (Phase 1 Emergent Coherence)."""

from novel_agent.agent.lore_contradiction_detector import LoreContradictionDetector
from novel_agent.memory.entities import Lore
from novel_agent.configs.config import Config


class FakeMemory:
    """In-memory lore store exposing the MemoryManager surface the detector uses."""

    def __init__(self, lore_items):
        self._lore = {l.id: l for l in lore_items}

    def load_lore(self, lore_id):
        return self._lore.get(lore_id)

    def save_lore(self, lore):
        self._lore[lore.id] = lore

    def load_all_lore(self):
        return list(self._lore.values())


class FakeVector:
    """Returns a fixed candidate neighbour list with distances."""

    def __init__(self, neighbours):
        # neighbours: list of (id, distance)
        self._neighbours = neighbours

    def find_similar_lore(self, lore, n_results=10):
        return [{"id": i, "distance": d} for i, d in self._neighbours]


class FakeLLM:
    def __init__(self, contradicts=True, reason="they conflict"):
        self._contradicts = contradicts
        self._reason = reason
        self.calls = 0

    def generate(self, prompt, max_tokens=200):
        self.calls += 1
        verdict = "true" if self._contradicts else "false"
        return f'{{"contradicts": {verdict}, "reason": "{self._reason}"}}'


class BadLLM:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt, max_tokens=200):
        self.calls += 1
        return "I cannot answer that."


def _pair():
    """Two same-category fact statements that genuinely contradict."""
    a = Lore(id="L001", lore_type="fact", category="technology", tick=1,
             content="A ghost chip is completely passive and emits nothing.")
    b = Lore(id="L002", lore_type="fact", category="technology", tick=3,
             content="A ghost chip can completely destroy any electronics nearby.")
    return a, b


def _detector(lore_items, neighbours, llm, cfg=None):
    return LoreContradictionDetector(
        FakeMemory(lore_items), FakeVector(neighbours), cfg or Config(), llm
    )


def test_llm_confirmed_contradiction_recorded_on_both_sides():
    a, b = _pair()
    det = _detector([a, b], [("L001", 0.35)], FakeLLM(contradicts=True, reason="passive vs destroys"))

    det.update_contradictions("L002")  # L002 is the freshly saved item

    new, old = det.memory.load_lore("L002"), det.memory.load_lore("L001")
    assert old.id in new.potential_contradictions
    assert new.id in old.potential_contradictions
    # Canon is the older item (lower tick), recorded on both sides.
    assert new.contradiction_details[0]["canon"] == "L001"
    assert old.contradiction_details[0]["canon"] == "L001"
    assert new.contradiction_details[0]["reason"] == "passive vs destroys"
    assert new.contradiction_details[0]["method"] == "llm"


def test_llm_says_no_contradiction_records_nothing():
    a, b = _pair()
    det = _detector([a, b], [("L001", 0.35)], FakeLLM(contradicts=False))

    det.update_contradictions("L002")

    assert det.memory.load_lore("L002").potential_contradictions == []
    assert det.memory.load_lore("L001").contradiction_details == []


def test_distant_candidates_are_not_judged():
    a, b = _pair()
    llm = FakeLLM(contradicts=True)
    # Neighbour distance above the 0.5 threshold -> filtered before the LLM.
    det = _detector([a, b], [("L001", 0.9)], llm)

    det.update_contradictions("L002")

    assert llm.calls == 0
    assert det.memory.load_lore("L002").potential_contradictions == []


def test_no_llm_falls_back_to_heuristic():
    # Two rules in the same category -> heuristic flags True without any LLM.
    a = Lore(id="L001", lore_type="rule", category="magic", tick=1, content="Magic needs words.")
    b = Lore(id="L002", lore_type="rule", category="magic", tick=2, content="Magic needs silence.")
    det = _detector([a, b], [("L001", 0.4)], None)

    det.update_contradictions("L002")

    new = det.memory.load_lore("L002")
    assert "L001" in new.potential_contradictions
    assert new.contradiction_details[0]["method"] == "heuristic"


def test_malformed_llm_output_degrades_without_recording():
    a, b = _pair()
    bad = BadLLM()
    det = _detector([a, b], [("L001", 0.35)], bad)

    det.update_contradictions("L002")

    assert bad.calls == 2  # tried once, retried once
    assert det.memory.load_lore("L002").potential_contradictions == []


def test_update_is_idempotent():
    a, b = _pair()
    det = _detector([a, b], [("L001", 0.35)], FakeLLM(contradicts=True))

    det.update_contradictions("L002")
    det.update_contradictions("L002")  # run again

    new = det.memory.load_lore("L002")
    assert new.potential_contradictions == ["L001"]
    assert len(new.contradiction_details) == 1


def test_enforcement_marks_newer_disputed_canon_stays_active():
    a, b = _pair()  # a=L001 tick1 (older), b=L002 tick3 (newer)
    det = _detector([a, b], [("L001", 0.35)], FakeLLM(contradicts=True))

    det.update_contradictions("L002")  # newer item just saved

    assert det.memory.load_lore("L002").status == "disputed"  # newer loses
    assert det.memory.load_lore("L001").status == "active"     # older is canon


def test_enforcement_off_leaves_status_active():
    a, b = _pair()
    cfg = Config()
    cfg.set('lore.enforce_contradictions', False)
    det = _detector([a, b], [("L001", 0.35)], FakeLLM(contradicts=True), cfg)

    det.update_contradictions("L002")

    # Still recorded (detection), but nothing disputed (no enforcement).
    assert "L001" in det.memory.load_lore("L002").potential_contradictions
    assert det.memory.load_lore("L002").status == "active"
    assert det.memory.load_lore("L001").status == "active"


def test_disabled_lore_tracking_short_circuits():
    a, b = _pair()
    cfg = Config()
    cfg.set('generation.enable_lore_tracking', False)
    llm = FakeLLM(contradicts=True)
    det = _detector([a, b], [("L001", 0.35)], llm, cfg)

    det.update_contradictions("L002")

    assert llm.calls == 0
    assert det.memory.load_lore("L002").potential_contradictions == []

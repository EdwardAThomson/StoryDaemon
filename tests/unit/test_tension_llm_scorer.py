"""Unit tests for the LLM-based tension scorer (full dynamic range, heuristic fallback)."""

from novel_agent.agent.tension_evaluator import TensionEvaluator
from novel_agent.configs.config import Config


class FakeLLM:
    def __init__(self, level=8, rationale="stakes are high"):
        self._level = level
        self._rationale = rationale
        self.calls = 0

    def generate(self, prompt, max_tokens=200):
        self.calls += 1
        return f'{{"tension_level": {self._level}, "rationale": "{self._rationale}"}}'


class BadLLM:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt, max_tokens=200):
        self.calls += 1
        return "I can't rate that."


class RaisingLLM:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt, max_tokens=200):
        self.calls += 1
        raise RuntimeError("backend down")


CALM_PROSE = (
    "The afternoon settled softly over the quiet garden, warm and gentle, and she rested, "
    "content, in the slow easy rhythm of an ordinary and familiar day."
)


def test_llm_reaches_top_of_range():
    te = TensionEvaluator(Config(), FakeLLM(level=9))
    r = te.evaluate_tension(CALM_PROSE)  # prose is calm, but the LLM verdict governs
    assert r['tension_level'] == 9
    assert r['tension_category'] == 'climactic'
    assert r['analysis']['method'] == 'llm'
    assert r['enabled'] is True


def test_llm_reaches_bottom_of_range():
    te = TensionEvaluator(Config(), FakeLLM(level=1))
    r = te.evaluate_tension("Blood! Terror! The explosion!")  # pulpy, but LLM says calm
    assert r['tension_level'] == 1
    assert r['tension_category'] == 'calm'
    assert r['analysis']['method'] == 'llm'


def test_llm_level_clamped():
    te = TensionEvaluator(Config(), FakeLLM(level=99))
    assert te.evaluate_tension("x")['tension_level'] == 10


def test_raising_llm_falls_back_to_heuristic():
    llm = RaisingLLM()
    te = TensionEvaluator(Config(), llm)
    r = te.evaluate_tension("Maya walked into the room and considered the strange terminal.")
    assert llm.calls == 2  # tried once, retried once
    assert r['analysis']['method'] == 'heuristic'
    assert r['tension_level'] is not None


def test_malformed_llm_falls_back_to_heuristic():
    te = TensionEvaluator(Config(), BadLLM())
    r = te.evaluate_tension("Maya walked into the room.")
    assert r['analysis']['method'] == 'heuristic'


def test_flag_disables_llm_scorer():
    cfg = Config()
    cfg.set('tension.use_llm_scorer', False)
    llm = FakeLLM(level=9)
    te = TensionEvaluator(cfg, llm)
    r = te.evaluate_tension("Maya walked into the room.")
    assert llm.calls == 0
    assert r['analysis']['method'] == 'heuristic'


def test_no_llm_uses_heuristic():
    te = TensionEvaluator(Config())  # backward-compatible: no LLM
    r = te.evaluate_tension("Maya walked into the room.")
    assert r['analysis']['method'] == 'heuristic'


def test_disabled_tracking_short_circuits():
    cfg = Config()
    cfg.set('generation.enable_tension_tracking', False)
    te = TensionEvaluator(cfg, FakeLLM(level=9))
    r = te.evaluate_tension("anything")
    assert r['enabled'] is False
    assert r['tension_level'] is None


def test_plain_dict_config_still_works():
    # Mirrors test/manual construction via config.to_dict() — no LLM, heuristic path.
    te = TensionEvaluator(Config().to_dict())
    r = te.evaluate_tension("Maya walked into the room.")
    assert r['enabled'] is True
    assert r['analysis']['method'] == 'heuristic'

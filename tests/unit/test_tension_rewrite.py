"""Unit tests for the Phase 3 #2 closed-loop tension rewrite."""

from novel_agent.agent.agent import StoryAgent
from novel_agent.agent.arc_pressure import needs_tension_rewrite, rewrite_improved
from novel_agent.agent.writer import SceneWriter
from novel_agent.configs.config import Config


# ---- pure decision helpers -------------------------------------------------

def test_needs_tension_rewrite():
    assert needs_tension_rewrite(8, 4, 2) is True       # off by 4 > 2
    assert needs_tension_rewrite(6, 5, 2) is False       # off by 1
    assert needs_tension_rewrite(7, 4, 2) is True        # off by 3
    assert needs_tension_rewrite(None, 4, 2) is False
    assert needs_tension_rewrite(8, None, 2) is False


def test_rewrite_improved():
    assert rewrite_improved(5, 8, 4) is True    # 5 (dist 1) closer than 8 (dist 4)
    assert rewrite_improved(8, 8, 4) is False    # no change
    assert rewrite_improved(9, 8, 4) is False    # 9 (dist 5) further than 8 (dist 4)
    assert rewrite_improved(None, 8, 4) is False


# ---- SceneWriter.revise_for_tension ---------------------------------------

class FakeLLM:
    def __init__(self, out):
        self.out = out
        self.prompt = None

    def generate(self, prompt, max_tokens=3000):
        self.prompt = prompt
        return self.out


def test_revise_for_tension_builds_calibrated_prompt_and_cleans_output():
    llm = FakeLLM("# A Title\n\nThe revised, calmer scene.")
    out = SceneWriter(llm, Config()).revise_for_tension("The tense scene.", target_level=4, current_level=8)
    # Prompt carries both scores, the lowering direction, the shared scale, and constraints.
    assert "4/10" in llm.prompt and "8/10" in llm.prompt
    assert "LOWER the tension" in llm.prompt
    assert "graded 0-10" in llm.prompt
    assert "HARD CONSTRAINTS" in llm.prompt
    # Header stripped from the returned prose.
    assert out == "The revised, calmer scene."


# ---- agent orchestration (_maybe_rewrite_for_tension) ---------------------

class FakeWriter:
    def __init__(self, revised):
        self.revised = revised
        self.called = False

    def revise_for_tension(self, text, target, current, writer_context=None, prev_tension=None):
        self.called = True
        return self.revised


class FakeTension:
    def __init__(self, score):
        self.score = score

    def evaluate_tension(self, text, ctx):
        return {"enabled": True, "tension_level": self.score, "tension_category": "x"}


class FakeMemory:
    """No prior scenes -> last_scene_tension returns None."""
    def list_scenes(self):
        return []


def _agent(config, writer, tension):
    a = StoryAgent.__new__(StoryAgent)  # bypass __init__; method only uses these attrs
    a.config = config
    a.writer = writer
    a.tension_evaluator = tension
    a.memory = FakeMemory()
    return a


# At tick 0 with the default curve+length, the target is 3.
def _tr(level):
    return {"enabled": True, "tension_level": level, "tension_category": "high"}


def test_rewrite_kept_when_closer():
    writer = FakeWriter("calmer prose")
    agent = _agent(Config(), writer, FakeTension(4))  # revised 4 -> closer to target 3 than 8
    scene, tr = agent._maybe_rewrite_for_tension({"text": "tense", "word_count": 1}, _tr(8), 0, {})
    assert writer.called
    assert scene["text"] == "calmer prose" and scene["word_count"] == 2
    assert tr["tension_level"] == 4 and tr["rewritten"] is True and tr["tension_pre_rewrite"] == 8


def test_rewrite_discarded_when_not_closer():
    writer = FakeWriter("still tense")
    agent = _agent(Config(), writer, FakeTension(9))  # revised 9 -> not closer to 3 than 8
    scene, tr = agent._maybe_rewrite_for_tension({"text": "tense", "word_count": 1}, _tr(8), 0, {})
    assert writer.called
    assert scene["text"] == "tense"  # original kept
    assert tr["tension_level"] == 8 and tr["rewritten"] is False


def test_no_rewrite_within_threshold():
    writer = FakeWriter("x")
    agent = _agent(Config(), writer, FakeTension(0))
    # current 4 vs target 3 -> off by 1 <= 2 -> skip
    scene, tr = agent._maybe_rewrite_for_tension({"text": "x", "word_count": 1}, _tr(4), 0, {})
    assert not writer.called and tr["tension_level"] == 4


def test_disabled_by_config():
    cfg = Config()
    cfg.set("coherence.tension_rewrite", False)
    writer = FakeWriter("x")
    agent = _agent(cfg, writer, FakeTension(3))
    agent._maybe_rewrite_for_tension({"text": "tense", "word_count": 1}, _tr(8), 0, {})
    assert not writer.called

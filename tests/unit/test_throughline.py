"""Unit tests for the throughline gate (primary-goal pressure on the planner)."""

from novel_agent.agent.throughline import primary_goal, throughline_guidance


class FakeConfig:
    def __init__(self, values=None):
        self._v = values or {}

    def get(self, key, default=None):
        return self._v.get(key, default)


GOAL_STATE = {"story_goals": {"primary": {"description": "expose the corporate data heist"}}}


def test_primary_goal_reads_story_goals_primary():
    assert primary_goal(GOAL_STATE)["description"] == "expose the corporate data heist"
    assert primary_goal({}) is None
    assert primary_goal({"story_goals": {}}) is None
    # Guards against the old singular `story_goal` mistake.
    assert primary_goal({"story_goal": {"description": "x"}}) is None


def test_throughline_guidance_with_goal():
    g = throughline_guidance(GOAL_STATE, FakeConfig())
    assert "## Throughline" in g
    assert "expose the corporate data heist" in g
    assert "advance, complicate, deepen" in g


def test_throughline_guidance_empty_without_goal():
    assert throughline_guidance({}, FakeConfig()) == ""
    assert throughline_guidance({"story_goals": {"primary": {}}}, FakeConfig()) == ""


def test_throughline_guidance_disabled_by_config():
    cfg = FakeConfig({"coherence.throughline_pressure": False})
    assert throughline_guidance(GOAL_STATE, cfg) == ""

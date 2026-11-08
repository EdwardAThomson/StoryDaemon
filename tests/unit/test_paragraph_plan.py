"""The model plans the paragraphs; Python sets the shares and checks the plan
(agent/paragraph_plan.py). Scripted fakes only: no API calls."""
import json

from novel_agent.agent import paragraph_plan as pp
from novel_agent.agent.scene_skeleton import skeleton_lines, skeleton_prompt_section

ROSTER = [("C000", "Petronilla Carpenter", "protagonist, female, adult"),
          ("C003", "William Somerville", "leadsman, male, young")]
SKELETON = ["ACTION"] * 4 + ["DIALOGUE"] * 4 + ["INTERIORITY"] * 2


def _reply(items):
    return json.dumps({"paragraphs": items})


def _good():
    return ([{"kind": "ACTION", "what": "She sketches the cliff."}] * 2
            + [{"kind": "DIALOGUE", "speaker": "C003", "what": "He calls the depth."},
               {"kind": "DIALOGUE", "speaker": "C000", "what": "She asks about the bottom."},
               {"kind": "DIALOGUE", "speaker": "C003", "what": "He shows the tallow."},
               {"kind": "DIALOGUE", "speaker": "C000", "what": "She thanks him."}]
            + [{"kind": "ACTION", "what": "She goes below."}] * 2
            + [{"kind": "INTERIORITY", "what": "She thinks of Arthur."}] * 2)


def test_targets_and_ranges_come_from_the_sampled_skeleton():
    assert pp.targets(SKELETON) == {"ACTION": 4, "DIALOGUE": 4, "INTERIORITY": 2}
    assert pp.allowed_range(4) == (3, 5)
    assert pp.allowed_range(12) == (9, 15)
    assert pp.allowed_range(1) == (0, 2)
    assert pp.total_range(10) == (8, 12)


def test_a_good_plan_is_accepted_first_time():
    calls = []
    kinds, notes, report = pp.plan_paragraphs(
        lambda p: calls.append(p) or _reply(_good()), "BRIEF", SKELETON, ROSTER)
    assert len(calls) == 1 and report["accepted"]
    assert kinds[:3] == ["ACTION", "ACTION", "DIALOGUE"]
    assert notes[2] == "William Somerville speaks. He calls the depth."
    assert notes[0] == "She sketches the cliff."
    # the prompt carries the brief, the cast by id and the targets
    assert "BRIEF" in calls[0] and "- C003: William Somerville" in calls[0]
    assert "- DIALOGUE: 4 (anything from 3 to 5)" in calls[0]


def test_dialogue_needs_a_speaker_from_the_cast_by_id():
    items = _good()
    items[2] = {"kind": "DIALOGUE", "speaker": "Old Hollis", "what": "x"}
    items[3] = {"kind": "DIALOGUE", "what": "y"}
    problems = pp.check(pp.parse(_reply(items)), SKELETON, ["C000", "C003"])
    assert any("'Old Hollis' is not an id" in p for p in problems)
    assert any("paragraph 4: DIALOGUE with no speaker id" in p for p in problems)


def test_shares_and_total_are_held_to_the_targets():
    items = [{"kind": "DIALOGUE", "speaker": "C003", "what": "x"}] * 10
    problems = pp.check(pp.parse(_reply(items)), SKELETON, ["C003"])
    assert "10 DIALOGUE paragraphs; use 3 to 5" in problems
    assert "0 ACTION paragraphs; use 3 to 5" in problems
    short = pp.check(pp.parse(_reply(_good()[:5])), SKELETON, ["C000", "C003"])
    assert any("5 paragraphs; the scene needs 8 to 12" in p for p in short)


def test_an_unrecorded_person_in_the_plan_text_is_refused():
    problems = pp.check(pp.parse(_reply(_good())), SKELETON, ["C000", "C003"],
                        name_check=lambda text: ["Old Hollis"])
    assert any("'Old Hollis' is not in the cast list" in p for p in problems)


def test_one_retry_with_the_problems_then_accept():
    bad = _good()
    bad[2]["speaker"] = "C999"
    replies = iter([_reply(bad), _reply(_good())])
    prompts = []
    kinds, notes, report = pp.plan_paragraphs(
        lambda p: prompts.append(p) or next(replies), "B", SKELETON, ROSTER)
    assert report["accepted"] and report["attempts"] == 2
    assert "Your Previous Plan Was Refused" in prompts[1]
    assert "'C999' is not an id" in prompts[1]


def test_two_refusals_leave_the_sampled_plan():
    kinds, notes, report = pp.plan_paragraphs(
        lambda p: "not json", "B", SKELETON, ROSTER)
    assert kinds is None and notes is None
    assert not report["accepted"] and report["attempts"] == 2


def test_parse_tolerates_fences_and_rejects_junk():
    assert pp.parse("```json\n" + _reply(_good()) + "\n```")[0]["kind"] == "ACTION"
    assert pp.parse("") is None
    assert pp.parse('{"paragraphs": []}') is None
    assert pp.parse('{"paragraphs": ["x"]}') is None


def test_plan_lines_carry_the_notes_and_are_unchanged_without_them():
    sk = ["ACTION", "DIALOGUE"]
    plain = skeleton_lines(sk)
    assert "What happens" not in plain
    with_notes = skeleton_lines(sk, notes=["She sketches.", "William speaks. Depth."])
    assert "1. ACTION" in with_notes and "   What happens: She sketches." in with_notes
    assert skeleton_lines(sk, 2, 2, notes=["a", "b"]).endswith("What happens: b")
    assert skeleton_prompt_section(sk) == skeleton_prompt_section(sk, None)
    assert "What happens: a" in skeleton_prompt_section(sk, ["a", "b"])


# ---- the agent hook ------------------------------------------------------------

class _Char:
    def __init__(self, cid, first, family, role, gender, age):
        self.id, self.first_name, self.family_name = cid, first, family
        self.full_name = self.display_name = f"{first} {family}"
        self.role, self.gender, self.age_group = role, gender, age
        self.nicknames, self.metadata = [], {}


class _Memory:
    chars = {"C000": _Char("C000", "Petronilla", "Carpenter", "protagonist", "female", "adult"),
             "C003": _Char("C003", "William", "Somerville", "leadsman", "male", "young")}

    def list_characters(self):
        return list(self.chars)

    def load_character(self, cid):
        return self.chars.get(cid)

    def list_locations(self):
        return []

    def list_factions(self):
        return []


class _Writer:
    def __init__(self, reply):
        self.reply, self.prompts = reply, []

    def _generate_segment(self, prompt, budget):
        self.prompts.append((prompt, budget))
        return self.reply, "stop"


def _agent(reply, on=True):
    from types import SimpleNamespace
    from novel_agent.agent.agent import StoryAgent
    from novel_agent.configs.config import Config
    cfg = Config()
    cfg.set("generation.paragraph_plan_by_model", on)
    stub = SimpleNamespace(config=cfg, memory=_Memory(), writer=_Writer(reply),
                           state={"story_foundation": {}})
    stub._known_names = lambda: StoryAgent._known_names(stub)
    return stub, (lambda ctx: StoryAgent._plan_paragraphs(stub, ctx))


def _context():
    return {"scene_skeleton": list(SKELETON), "pov_character_name": "Petronilla Carpenter",
            "scene_intention": "She learns the cove's name.",
            "scene_length_guidance": "Write about 600 words." + skeleton_prompt_section(SKELETON)}


def test_hook_replaces_the_plan_and_its_prompt_section():
    stub, plan = _agent(_reply(_good()))
    ctx = plan(_context())
    assert ctx["paragraph_plan_report"]["accepted"]
    assert ctx["scene_skeleton"][2] == "DIALOGUE"
    assert ctx["paragraph_notes"][2] == "William Somerville speaks. He calls the depth."
    assert "What happens: William Somerville speaks." in ctx["scene_length_guidance"]
    assert ctx["scene_length_guidance"].startswith("Write about 600 words.")
    assert stub.writer.prompts[0][1] == 4000


def test_hook_off_or_refused_leaves_the_context_alone():
    for reply, on in ((_reply(_good()), False), ("junk", True)):
        before = _context()
        _stub, plan = _agent(reply, on)
        after = plan(dict(before))
        assert after["scene_skeleton"] == before["scene_skeleton"]
        assert after["scene_length_guidance"] == before["scene_length_guidance"]
        assert "paragraph_notes" not in after


def test_hook_refuses_a_person_the_plan_text_invents():
    bad = _good()
    bad[4] = {"kind": "DIALOGUE", "speaker": "C003",
              "what": "He says a sealer called Hollis told him the name."}
    _stub, plan = _agent(_reply(bad))
    ctx = plan(_context())
    assert not ctx["paragraph_plan_report"]["accepted"]
    assert any("'Hollis' is not in the cast list" in p
               for p in ctx["paragraph_plan_report"]["problems"][0])

"""Names come from the generator and from nowhere else.

The records always did; the leak was the text beside them (2026-11-02): the
protagonist's description was the archetype with a name in it, and the
planner's character descriptions used the premise's names. These tests pin
the hygiene that closes both, and the gauge that counts what is left.
"""
import logging
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.agent.name_hygiene import (
    candidate_names, clean_description, foreign_names, frequent_names,
    prose_gauge, strip_name_head, world_words,
)
from novel_agent.cli.protagonist import create_protagonist
from novel_agent.memory.manager import MemoryManager

PREMISE = ("In 1871 the survey brig Alcyone is charting a volcanic archipelago while "
           "secretly searching for the lost Meridian expedition. Elena Marsh, a "
           "naturalist, carries her missing brother's cipher notebook; Captain Reeve "
           "owes a debt he will not name; Yusuf, the quartermaster, has sailed these "
           "waters before and says little about it.")


def test_people_in_a_premise_are_found_and_the_ship_is_not():
    assert candidate_names(PREMISE) == ["Elena Marsh", "Reeve", "Yusuf"]
    assert "Alcyone" in world_words(PREMISE)
    assert "Elena" not in world_words(PREMISE)


def test_a_role_only_premise_names_nobody():
    assert candidate_names("A naturalist carries her missing brother's notebook; "
                           "the captain owes a debt he will not name.") == []


def test_minted_names_are_not_foreign():
    assert foreign_names(PREMISE + " Rowland Bosworth stood at the rail.",
                         ["Rowland Bosworth"]) == ["Elena Marsh", "Reeve", "Yusuf"]
    assert foreign_names("Rowland lifted the lamp.", ["Rowland Bosworth"]) == []


def test_a_bare_repeated_name_is_found_even_at_sentence_starts():
    text = "Yusuf took the line. Yusuf said nothing. The oars came in while Yusuf waited."
    assert frequent_names(text) == ["Yusuf"]
    assert frequent_names("Salt dried on the rail. The salt was everywhere. Salt. Salt.") == []


def test_strip_name_head_drops_only_a_name():
    assert strip_name_head("Elena Marsh, a determined naturalist searching for her brother") == (
        "A determined naturalist searching for her brother", "Elena Marsh")
    assert strip_name_head("A tired surveyor, out of money") == ("A tired surveyor, out of money", "")
    assert strip_name_head("Captain Ahab") == ("Captain Ahab", "")


def test_clean_description_renames_the_subject_and_reports_the_rest():
    text, left = clean_description(
        "Yusuf is an experienced quartermaster. Yusuf's charts are exact.",
        "Richard", "Huntington", ["Rowland Bosworth"])
    assert text == "Richard is an experienced quartermaster. Richard's charts are exact."
    assert left == []
    text, left = clean_description("Elena's brother, missing since the Meridian sailed.",
                                   "William", "Somerville", ["Charles Cavendish"])
    assert text.startswith("Elena's brother")
    assert left == ["Elena"]
    text, left = clean_description("A woman connected to Charles through the survey.",
                                   "Violante", "Percy", ["Charles Cavendish"])
    assert left == []


def test_prose_gauge_separates_foundation_names_from_other_noise():
    foundation = {"premise": PREMISE, "protagonist_archetype": "Elena Marsh, a naturalist",
                  "setting": "a survey brig, 1871"}
    prose = ("Rowland watched the Alcyone swing. Yusuf took the line. Yusuf said nothing. "
             "The oars came in while Yusuf waited. Pierford Keep stood on the headland. Rowland went below.")
    g = prose_gauge(prose, ["Rowland Bosworth"], foundation)
    assert g["foundation_names_in_prose"] == ["Yusuf"]
    assert g["foundation_name_mentions"] == 3
    assert "Alcyone" not in g["unregistered_names"]
    assert "Pierford Keep" not in g["unregistered_names"]


class Foundation:
    def __init__(self, archetype, name=None, genre="historical adventure"):
        self.protagonist_archetype = archetype
        self.protagonist_name = name
        self.genre = genre


class Gen:
    def generate_name(self, gender="male", genre="scifi"):
        self.gender = gender
        return {"first_name": "Rell", "last_name": "Tavish"}

    def register_used_name(self, name):
        pass


@pytest.fixture
def memory():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text("{}")
    yield MemoryManager(d)
    shutil.rmtree(d, ignore_errors=True)


def test_protagonist_description_carries_no_second_name(memory, caplog):
    with caplog.at_level(logging.WARNING):
        cid = create_protagonist(memory, Foundation("Elena Marsh, a determined naturalist"), Gen())
    c = memory.load_character(cid)
    assert c.first_name == "Rell"
    assert c.description == "A determined naturalist"
    assert c.metadata["archetype_name_dropped"] == "Elena Marsh"
    assert "dropped" in caplog.text


def test_an_explicit_protagonist_name_keeps_its_archetype(memory):
    cid = create_protagonist(memory, Foundation("Elena Marsh, a naturalist", name="Elena Marsh"), Gen())
    c = memory.load_character(cid)
    assert c.first_name == "Elena"
    assert c.description == "Elena Marsh, a naturalist"
    assert "archetype_name_dropped" not in c.metadata


# --- Gender is recorded with the minted name (2026-11-04) -------------------

from novel_agent.agent.name_hygiene import gender_from_text, replace_name, unminted_people_in_plan
from novel_agent.memory.entities import Character


def test_gender_from_text_reads_only_a_clear_statement():
    assert gender_from_text("a naturalist searching for her missing brother") == "female"
    assert gender_from_text("a captain who keeps his own counsel") == "male"
    assert gender_from_text("a naturalist searching for a missing brother") == ""
    assert gender_from_text("she asked him") == ""


def test_the_protagonist_gets_the_gender_its_name_was_drawn_for(memory):
    gen = Gen()
    cid = create_protagonist(memory, Foundation("A naturalist searching for her missing brother"), gen)
    assert gen.gender == "female"
    assert memory.load_character(cid).gender == "female"


def test_the_protagonist_is_not_male_by_default(memory):
    seen = set()
    for _ in range(40):
        gen = Gen()
        cid = create_protagonist(memory, Foundation("A naturalist searching for a lost expedition"), gen)
        seen.add(memory.load_character(cid).gender)
    assert seen == {"male", "female"}


def test_character_pronouns_follow_the_recorded_gender():
    assert Character(id="C1", first_name="Hugh", gender="male").pronouns == "he/him"
    assert Character(id="C2", first_name="Ada", gender="female").pronouns == "she/her"
    assert Character(id="C3", first_name="Old").pronouns == ""
    assert Character.from_dict({"id": "C4", "first_name": "Legacy"}).gender == ""


def test_the_plan_names_people_who_have_no_record():
    plan = {"scene_intention": "Theobald quietly obtains the eastern-approach log from Yusuf, "
                                "who warns that one page was replaced.",
            "rationale": "The scene stays aboard the Alcyone."}
    found = unminted_people_in_plan(plan, ["Theobald Thornbury"], ignore={"Alcyone"})
    assert [n for n, _ in found] == ["Yusuf"]
    assert unminted_people_in_plan({"scene_intention": "Theobald boards the Valdhold."},
                                   ["Theobald Thornbury"]) == []


def test_replace_name_puts_the_minted_name_in_place():
    assert replace_name("the log from Yusuf, who warns", "Yusuf", "Septimus", "Percy") == \
        "the log from Septimus, who warns"
    assert replace_name("Elena Marsh found it; Elena kept it.", "Elena Marsh", "Ada", "Vane") == \
        "Ada Vane found it; Ada kept it."

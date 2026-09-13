"""The protagonist is minted in Python at project creation, from an explicit
name field. Nothing parses prose for a name.

The parser this replaced split the archetype on its first comma and accepted
one to three capitalised words, so "Doctor Miriam Vale, a field surgeon"
produced a character whose first name was "Doctor" and Miriam was lost. It
also hid a deeper mistake: the wizard asks for an archetype
("personality/role") and our projects had names written into it, so the field
was filled wrongly and the code quietly compensated.
"""
import logging
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.cli.protagonist import create_protagonist, split_name
from novel_agent.memory.manager import MemoryManager


class Foundation:
    def __init__(self, archetype, name=None, genre="historical adventure"):
        self.protagonist_archetype = archetype
        self.protagonist_name = name
        self.genre = genre


class Gen:
    def __init__(self, first="Rell", last="Tavish"):
        self.first, self.last, self.registered = first, last, None

    def generate_name(self, genre="scifi"):
        return {"first_name": self.first, "last_name": self.last}

    def register_used_name(self, name):
        self.registered = name


@pytest.fixture
def memory():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text("{}")
    yield MemoryManager(d)
    shutil.rmtree(d, ignore_errors=True)


# ---- splitting a name the author actually typed ------------------------------

def test_split_name_keeps_every_word():
    # Not guessing: every word in a name field is part of the name.
    assert split_name("Miriam Vale") == ("Miriam", "Vale")
    assert split_name("Ruth Kade Ellery") == ("Ruth", "Kade Ellery")
    assert split_name("Mary-Jane O'Hara") == ("Mary-Jane", "O'Hara")
    assert split_name("Ahab") == ("Ahab", "")      # mononym
    assert split_name("") == ("", "")


def test_a_title_is_never_mistaken_for_a_first_name():
    # The old parser turned "Doctor Miriam Vale" into first name "Doctor".
    # Given explicitly, the author's words are used as written.
    assert split_name("Doctor Miriam Vale") == ("Doctor", "Miriam Vale")


# ---- creation ----------------------------------------------------------------

def test_uses_the_explicit_name(memory):
    cid = create_protagonist(
        memory, Foundation("a field surgeon", name="Miriam Vale"))
    char = memory.load_character(cid)
    assert (char.first_name, char.family_name) == ("Miriam", "Vale")
    assert char.role == "protagonist"
    assert char.metadata["minted"] == "foundation"


def test_mints_when_no_name_is_given(memory):
    gen = Gen()
    cid = create_protagonist(memory, Foundation("a weary detective"), gen)
    char = memory.load_character(cid)
    assert (char.first_name, char.family_name) == ("Rell", "Tavish")
    assert char.metadata["minted"] == "generated"
    assert gen.registered == "Rell Tavish"


def test_the_archetype_is_never_mined_for_a_name(memory):
    # A legacy foundation with a name buried in the archetype gets a GENERATED
    # protagonist, not "Elena". The old code would have produced Elena Marsh.
    cid = create_protagonist(
        memory, Foundation("Elena Marsh, a naturalist"), Gen())
    char = memory.load_character(cid)
    assert char.first_name == "Rell"
    assert "Elena" not in char.first_name


def test_a_name_shaped_archetype_is_reported_not_used(memory, caplog):
    with caplog.at_level(logging.WARNING):
        create_protagonist(memory, Foundation("Elena Marsh, a naturalist"), Gen())
    msg = " ".join(r.getMessage() for r in caplog.records)
    assert "Elena Marsh" in msg
    assert "protagonist_name" in msg


def test_a_plain_archetype_triggers_no_warning(memory, caplog):
    with caplog.at_level(logging.WARNING):
        create_protagonist(memory, Foundation("a weary detective"), Gen())
    assert not [r for r in caplog.records if "reads like a name" in str(r.msg)]


def test_refuses_rather_than_inventing(memory):
    with pytest.raises(ValueError):
        create_protagonist(memory, Foundation("a weary detective"), None)


def test_an_empty_generated_name_is_refused(memory):
    with pytest.raises(ValueError):
        create_protagonist(memory, Foundation("x"), Gen(first="", last=""))

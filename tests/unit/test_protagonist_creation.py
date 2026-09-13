"""The protagonist is minted in Python at project creation, deterministically.

A project used to start with zero characters and rely on the planner to call
character.generate unprompted. When planning degraded, nothing was created,
nothing said so, and the writer was handed a name parsed out of the
foundation's free text with no entity behind it.
"""
import shutil
import tempfile
from pathlib import Path

import pytest

from novel_agent.cli.protagonist import create_protagonist, name_from_archetype
from novel_agent.memory.manager import MemoryManager


class Foundation:
    def __init__(self, archetype, genre="historical adventure"):
        self.protagonist_archetype = archetype
        self.genre = genre


@pytest.fixture
def memory():
    d = Path(tempfile.mkdtemp())
    (d / "state.json").write_text("{}")
    yield MemoryManager(d)
    shutil.rmtree(d, ignore_errors=True)


# ---- reading a name the author already gave ----------------------------------

def test_name_is_taken_from_the_foundation_when_it_has_one():
    assert name_from_archetype(
        "Elena Marsh, a naturalist carrying her brother's notebook"
    ) == ("Elena", "Marsh")
    assert name_from_archetype("Captain Ahab") == ("Captain", "Ahab")
    assert name_from_archetype("Mary-Jane O'Hara, a pilot") == ("Mary-Jane", "O'Hara")


def test_a_description_is_not_mistaken_for_a_name():
    # Guessing wrong here is what produced a phantom protagonist.
    assert name_from_archetype("a weary detective with nothing left") is None
    assert name_from_archetype("the protagonist") is None
    assert name_from_archetype("") is None
    assert name_from_archetype("A B C D E, someone") is None


# ---- creation ----------------------------------------------------------------

def test_creates_a_real_character_entity(memory):
    cid = create_protagonist(memory, Foundation("Elena Marsh, a naturalist"))
    char = memory.load_character(cid)
    assert char is not None
    assert char.first_name == "Elena" and char.family_name == "Marsh"
    assert char.role == "protagonist"
    assert char.metadata["minted"] == "foundation"


def test_mints_a_name_when_the_foundation_gives_none(memory):
    class Gen:
        def generate_name(self, genre="scifi"):
            return {"first_name": "Rell", "last_name": "Tavish"}

        def register_used_name(self, name):
            self.registered = name

    gen = Gen()
    cid = create_protagonist(memory, Foundation("a weary detective"), gen)
    char = memory.load_character(cid)
    assert char.first_name == "Rell" and char.family_name == "Tavish"
    assert char.metadata["minted"] == "generated"
    assert gen.registered == "Rell Tavish"


def test_refuses_rather_than_inventing(memory):
    # No name in the foundation and no generator: fail at creation, not eight
    # scenes later.
    with pytest.raises(ValueError):
        create_protagonist(memory, Foundation("a weary detective"), None)


def test_creation_is_deterministic_for_a_named_foundation(memory):
    a = create_protagonist(memory, Foundation("Elena Marsh, a naturalist"))
    b = create_protagonist(memory, Foundation("Elena Marsh, a naturalist"))
    assert memory.load_character(a).first_name == memory.load_character(b).first_name
    assert a != b          # distinct ids, same deterministic name

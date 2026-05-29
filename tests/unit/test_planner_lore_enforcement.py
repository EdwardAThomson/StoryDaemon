"""Phase 3 enforcement: disputed lore is hidden from the multi-stage planner."""
import tempfile
from pathlib import Path

import pytest

from novel_agent.memory.manager import MemoryManager
from novel_agent.memory.entities import Lore
from novel_agent.configs.config import Config
from novel_agent.agent.multi_stage_planner import MultiStagePlanner


@pytest.fixture
def project():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "memory").mkdir()
        yield project_dir


def test_active_lore_excludes_disputed(project):
    mem = MemoryManager(project)
    mem.save_lore(Lore(id="L001", content="canon fact", category="tech", tick=1, status="active"))
    mem.save_lore(Lore(id="L002", content="disputed fact", category="tech", tick=2, status="disputed"))
    mem.save_lore(Lore(id="L003", content="another active", category="tech", tick=3))  # default active

    # __init__ just stores args; _active_lore only touches self.memory.
    planner = MultiStagePlanner(None, mem, None, None, Config())
    visible = {l.id for l in planner._active_lore()}

    assert visible == {"L001", "L003"}
    assert "L002" not in visible

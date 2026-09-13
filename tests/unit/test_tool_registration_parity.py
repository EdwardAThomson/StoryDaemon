"""tick() and run() must register the same tools.

CLAUDE.md warns that the two registration blocks in cli/main.py are
duplicated and that updating only one silently breaks the multi-tick flow.
They had in fact drifted: run() was missing FactionUpdateTool and
FactionQueryTool, so a tool the planner was offered in a single tick vanished
in a multi-tick run. Parsed from source rather than executed, so no project,
no vector store and no LLM are needed.
"""
import pathlib
import re

MAIN = pathlib.Path(__file__).resolve().parents[2] / "novel_agent" / "cli" / "main.py"


def _registered(fn_name):
    src = MAIN.read_text()
    i = src.index(f"\ndef {fn_name}(")
    nxt = src.find("\ndef ", i + 5)
    body = src[i:nxt if nxt > 0 else len(src)]
    return set(re.findall(r"register\(\s*([A-Za-z_]+)", body))


def test_tick_and_run_register_the_same_tools():
    tick, run = _registered("tick"), _registered("run")
    assert tick, "no tools found in tick(); the parser needs updating"
    missing_in_run = tick - run
    missing_in_tick = run - tick
    assert not missing_in_run, f"run() is missing: {sorted(missing_in_run)}"
    assert not missing_in_tick, f"tick() is missing: {sorted(missing_in_tick)}"


def test_the_registry_is_not_empty():
    # A planner offered no tools writes plans with no actions, which is how a
    # run produces no characters and no locations while reporting success.
    assert len(_registered("tick")) >= 8

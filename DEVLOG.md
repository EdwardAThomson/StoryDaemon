# Development Log

## 2026-06-20

Tightened test coverage on two pure, self-contained modules without touching any production code. `novel_agent/utils/file_ops.py` went from 61% to 100%, covering `load_schema` (success, missing file, invalid JSON), `save_prompt_to_file` (content, name sanitization, custom subfolder/extension, IOError wrapping), `write_json` Unicode preservation (`ensure_ascii=False`), and the reachable error-wrapping branches in `open_file`/`write_file`/`read_json`. A new `tests/unit/test_plot_outline.py` brought `novel_agent/memory/plot_outline.py` from 75% to 100%, exercising every `PlotOutlineManager` method and the `PlotBeat`/`PlotOutline` `to_dict`/`from_dict` round-trips. The suite grew from 261 to 299 passing tests.

**Decisions & notes:** Deliberately scoped to pure modules with no side effects as a first coverage pass, keeping it tests-only so there was no risk to behavior.

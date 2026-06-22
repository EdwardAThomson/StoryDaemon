# Dev Log

## 2026-06-20

Scoped test-coverage pass over two pure, self-contained modules to push them to full coverage with no production-code changes. `utils/file_ops.py` went from 61% to 100% — covering `load_schema` (success, missing-file, invalid-JSON paths), `save_prompt_to_file` (content handling, name sanitization, custom subfolder/extension, IOError wrapping), `write_json`'s Unicode preservation (`ensure_ascii=False`), and the reachable error-wrapping branches in `open_file`/`write_file`/`read_json`. `memory/plot_outline.py` went from 75% to 100% via a new `tests/unit/test_plot_outline.py` that exercises every `PlotOutlineManager` method plus `PlotBeat`/`PlotOutline` `to_dict`/`from_dict` round-trips. The suite grew from 261 to 299 passing.

**Decisions & notes:** Tests-only by design — no production code was touched. This is a first targeted pass at the two simplest modules; the picks were deliberately "pure and self-contained" to make 100% coverage cheap and safe.

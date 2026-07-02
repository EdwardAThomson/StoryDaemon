# Dev Log

## 2026-07-01

Ran a full documentation audit against the current code and fixed the drift. The README's CLI Commands section was missing the shipped `novel metrics` and `novel titles` commands, so those got documented. `spec.md` had accumulated several inaccuracies: it referenced a `location.update` tool that doesn't exist (corrected to the real `location.generate`, in both the tools list and the example plan), and its Tech Stack table and API note still described the system as "Codex CLI (GPT-5)" with "API support can be added later" (replaced with the reality of the shipped multi-backend LLM support: Codex / api / claude-cli / gemini-cli, plus hosted-llm). Finally, `beats_and_loops.md` had stale source line-number citations that rot as code moves; those were swapped for more durable file+function references.

**Decisions & notes:** Docs-only sweep, no production code touched. Preferring file+function references over line numbers in docs is a deliberate anti-rot choice worth applying elsewhere.

## 2026-06-20

Scoped test-coverage pass over two pure, self-contained modules to push them to full coverage with no production-code changes. `utils/file_ops.py` went from 61% to 100% — covering `load_schema` (success, missing-file, invalid-JSON paths), `save_prompt_to_file` (content handling, name sanitization, custom subfolder/extension, IOError wrapping), `write_json`'s Unicode preservation (`ensure_ascii=False`), and the reachable error-wrapping branches in `open_file`/`write_file`/`read_json`. `memory/plot_outline.py` went from 75% to 100% via a new `tests/unit/test_plot_outline.py` that exercises every `PlotOutlineManager` method plus `PlotBeat`/`PlotOutline` `to_dict`/`from_dict` round-trips. The suite grew from 261 to 299 passing.

**Decisions & notes:** Tests-only by design — no production code was touched. This is a first targeted pass at the two simplest modules; the picks were deliberately "pure and self-contained" to make 100% coverage cheap and safe.

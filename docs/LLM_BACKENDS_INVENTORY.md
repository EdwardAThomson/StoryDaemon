# LLM Backends: Cross-Repo Inventory and Extraction Plan

**Status:** Inventory + plan (no code changes; nothing migrated yet)
**Date:** 2026-07-14
**Extends:** `CROSS_POLLINATION.md` ("Scope: shared LLM-backend library"). That doc scoped the package for StoryDaemon + NovelWriter only; this one inventories the whole family across every repo under `~/Projects`, revises the source-of-truth story, and turns the sketch into a concrete extraction plan. It does not repeat the CROSS_POLLINATION prose; read that first for the two-project framing.
**Method:** every claim below was verified against the working trees on 2026-07-14 (file reads, grep sweeps of `~/Projects` for `send_prompt` / `multi_provider` / `ai_helper` / `cli_backends` in Python files, and `git log` per file). Line references are to the files as of that date.

---

## 1. Executive summary

The `send_prompt` backend family exists in **seven Python repos** (four were known going in; the sweep found three more live ones plus one dead copy), plus a **TypeScript sibling** (LLM-Remote-Runner) and its predecessor (Codex-Remote-Runner). Roughly **4,700 lines** of near-duplicate Python are drifting by hand, and no single copy is a superset:

- **StoryDaemon** is the most advanced API layer: finish_reason meta contract, per-request timeout plumbing, hosted-llm + OpenRouter + Venice providers, and the only real test coverage (~36 direct tests).
- **llm_creative_writing-analyser** (hereafter "the analyzer") is the most hardened CLI layer and the only repo with four fixes that exist nowhere else: subscription-billing key-stripping, the codex bubblewrap/user-namespace workaround, the `openrouter:<model>` prefix passthrough, and the OpenRouter `max_retries=6` client hardening.
- Everyone else (NovelWriter, Prompt-Injection-Testing, CryptoAlertBot, DungeonGPT) runs older, partially broken forks.

Recommendation: extract one package (`llm-backends`) using StoryDaemon's API layer as the base and the analyzer's CLI package as the CLI base, fold in NovelWriter's `is_available()` probes, and make the package registry the **superset source of truth for model naming**, demoting LLM-Remote-Runner reconciliation to an optional alignment step (Section 6, this revises CROSS_POLLINATION step 4).

---

## 2. Repo census

Repo tags used throughout: **SD** = StoryDaemon, **AN** = llm_creative_writing-analyser, **NW** = NovelWriter, **PIT** = Prompt-Injection-Testing, **CAB** = CryptoAlertBot, **DG** = DungeonGPT, **SG** = ScrambleGate, **RR** = LLM-Remote-Runner.

| Repo | Backend code | LOC | API providers | CLI backends | Tests on this layer | Layer last touched |
|---|---|---|---|---|---|---|
| **SD** | `novel_agent/tools/` (6 files) | 1,390 | OpenAI, Anthropic, Gemini, hosted-llm, OpenRouter, Venice | codex, claude, gemini | ~36 direct (+~18 adjacent) | 2026-07-15 (Venice) |
| **AN** | `ai_helper.py` + `cli_backends/` (5 files) | 937 | OpenAI, Anthropic, Gemini, OpenRouter (incl. prefix passthrough) | codex, claude, gemini | 17 (OpenRouter routing) | 2026-07-14 |
| **NW** | `core/generation/ai_helper.py` + `llm_interface/` (7 files) | 1,278 | OpenAI (chat + reasoning), Anthropic, Gemini | codex, claude, gemini | none | 2026-01-23 |
| **PIT** | `ai_helper.py` + `cli_backends.py` | 631 | OpenAI (chat + o-series), Anthropic, Gemini | codex, claude, gemini (unhardened single file) | none | 2026-04-07 |
| **CAB** | `src/ai_helper.py` | 221 | OpenAI, Gemini (Claude path is dead code, see 3.5) | none | none | 2025-12-17 |
| **DG** | `ai_helper.py` | 37 | OpenAI only | none | none | 2026-02-18 |
| **SG** | `archive/analysis/ai_helper.py` | 220 | OpenAI, Anthropic, Gemini | none | none | 2025-08-20 (dead code) |
| **RR** (TS) | `gateway/src/adapters/` + `app.config.ts` | n/a | OpenAI, Anthropic, Gemini | codex, claude, gemini (as gateway adapters) | (not audited) | 2026-05-21 |

NW additionally carries an **untracked** 817-line snapshot of StoryDaemon's backend under `NovelWriter/temp/llm_interface_reference/` (docstrings literally say "LLM interface for StoryDaemon"; zero git history). It is stale and should be deleted once NW adopts the package.

**Codex-Remote-Runner** is RR's predecessor, not a family member: same NestJS/pnpm scaffold, identical `@codex/gateway` package name, and RR's second-ever commit (2025-12-03) is "Update repository URLs from Codex-Remote-Runner to LLM-Remote-Runner". It has no adapter/registry layer at all, just a single hardcoded `spawn(codexBinPath, ...)` in `gateway/src/tasks/tasks.service.ts:159-175`. No shared git ancestry (snapshot fork, not a branch). Verdict: related predecessor, out of scope for the extraction.

### Lineage (evidence-based, not overclaimed)

All the `ai_helper.py` forks share one ancestor: identical `# ai_helper.py` header, `load_dotenv()` bootstrap, registry-of-lambdas `_model_config`, `send_prompt(prompt, model)` dispatcher, and byte-identical provider worker bodies (only defaults and model lists differ). Observable chain:

- AN's `ai_helper.py` is the oldest living fork (first commit 2025-03-31).
- SG's copy (frozen 2025-08-20) is the complete ancestor form with Anthropic wired; CAB (2025-12) is a copy of that shape which **dropped the `anthropic` import but kept the Claude functions** (hence the dead path); DG (2026-02) is the primitive single-function form.
- PIT (2026-04) is a "ScrambleGate port" (its own commit message) that added CLI backends and a modern model list; its `cli_backends.py:16` header says "Adapted from NovelWriter".
- The hardened CLI wrappers evolved separately: NW's live package (files dated 2025-11-27) -> SD's copies (last touched 2026-05-30, added `neutral_cwd` + codex de-fang) -> AN's package (2026-06-02, `cli_backends/__init__.py` says "Ported from the StoryDaemon writing ecosystem", then added key-stripping and the userns workaround on 2026-06-10).

---

## 3. Per-repo inventory

### 3.1 StoryDaemon (`novel_agent/tools/`)

| File | LOC | Last commit |
|---|---|---|
| `multi_provider_llm.py` | 789 | 2026-07-15 `d080f77` (Venice backend) |
| `llm_interface.py` | 130 | 2026-07-12 `083b9d1` (hardening batch) |
| `codex_interface.py` | 155 | 2026-05-30 `75a1a49` |
| `claude_cli_interface.py` | 158 | 2026-05-30 `38a0e0b` |
| `gemini_cli_interface.py` | 134 | 2026-05-30 `75a1a49` |
| `agent_cwd.py` | 24 | 2026-05-30 `38a0e0b` |

**Registry** (`_model_config_meta`, `multi_provider_llm.py:569-619`, 14 keys): `hosted-llm`, `openrouter`, `venice`, `gpt-5.5`, `gpt-5.4`, `gpt-5.2`, `claude-sonnet-4.5`, `claude-haiku-4.5`, `claude-4.5` (alias -> Sonnet), `gemini-3-flash-preview`, `gemini-3-pro-preview`, `gemini-3.1-pro-preview`, `gemini-2.5-pro`, `gemini-2.5-flash`. `_resolve_model_key` (`:658`) retries with a `-latest` suffix before erroring.

**Unique features** (file:line):
- **finish_reason meta contract**: every provider has `send_prompt_<provider>_meta(...) -> (text, finish_reason)`; normalizers at `multi_provider_llm.py:270` (OpenAI), `:281` (Anthropic), `:294` (Gemini), normalized to `"stop"`/`"length"`/lowercased-other/`None`. `MultiProviderInterface.generate_with_meta` (`:762`); CLI backends deliberately lack it, callers probe `hasattr`. This feeds the write-until-concluded scene loop.
- **Per-request timeout plumbing**: `_call_with_timeout` (`:79`) attaches provider-shaped timeout kwargs and degrades gracefully on `TypeError`; rationale documented in `docs/progress_report_20260712.md` section 8.1 (a 22.4-minute OpenRouter hang when `llm.timeout` was inert).
- **SDK internal-retry cap**: `SDK_MAX_RETRIES = 1` (`:66`), bounding worst-case wall time to ~2x the configured timeout.
- **hosted-llm provider** (`:100`, `:319`): self-hosted OpenAI-compatible endpoint (`HOSTED_LLM_URL:PORT`), with vLLM/Qwen `chat_template_kwargs: enable_thinking: False` extra_body (`:353`).
- **Venice provider** (`:164`, `:409`): `https://api.venice.ai/api/v1`, `venice_parameters.include_venice_system_prompt: False` (`:445`). Added 2026-07-15; **SD's own `CLAUDE.md` registry section does not mention Venice yet** (stale relative to `d080f77`).
- **OpenRouter provider** (`:135`, `:363`): env-model fallback via `OPENROUTER_MODEL`; deliberately no provider-specific extra_body (`:396` comment).
- `neutral_cwd()` isolation for all three CLI backends (`agent_cwd.py:19`; used at codex `:95`, claude `:73`, gemini `:86`).

**Gaps** (things SD would lose without merging others): no API-key stripping in CLI subprocess env (no `env=` on any `subprocess.run` in the three CLI files), no bubblewrap/userns workaround in `codex_interface.py`, no `is_available()` static probes, no `openrouter:` prefix passthrough, OpenRouter client uses SDK-default retries.

**Env vars**: `OPENAI_API_KEY`, **`CLAUDE_API_KEY`** (not `ANTHROPIC_API_KEY`), `GEMINI_API_KEY`, `HOSTED_LLM_URL`, `HOSTED_LLM_PORT`, `HOSTED_LLM_API_KEY`, `HOSTED_LLM_MODEL`, `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `VENICE_API_KEY`, `VENICE_MODEL`. No dotenv loading in this layer.

**Tests**: `tests/unit/test_multi_provider_llm.py` (18), `test_llm_finish_reason.py` (14, includes Venice extra_body verification), `test_agent_cwd.py` (4); adjacent `test_writer_segments.py` (15) and `test_run_retries.py` (3) exercise the meta loop. No dedicated CLI-interface test files.

**CLAUDE.md coupling**: `CLAUDE.md:76` declares the registry "kept in sync with the LLM-Remote-Runner repo (the model source of truth)" and requires updating the `gpt-5.5` fallback literals in `cli/main.py` / `cli/commands/*.py` together with the registry. Both rules change under this plan (Sections 6 and 7).

### 3.2 llm_creative_writing-analyser

| File | LOC | Last commit |
|---|---|---|
| `ai_helper.py` | 370 | 2026-07-14 `e263af6` (OpenRouter max_tokens fix) |
| `cli_backends/codex_interface.py` | 222 | 2026-06-10 `2fed1b0` (billing fix) |
| `cli_backends/claude_cli_interface.py` | 166 | 2026-06-10 `2fed1b0` |
| `cli_backends/gemini_cli_interface.py` | 142 | 2026-06-10 `2fed1b0` |
| `cli_backends/agent_cwd.py` | 24 | 2026-06-02 `f122298` |
| `cli_backends/__init__.py` | 13 | 2026-06-02 `f122298` |

**Registry** (`ai_helper.py:130-169`, 20 keys): `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.2`; `gemini-3.1-pro-preview`, `gemini-3.1-flash-preview`, `gemini-3-pro-preview`, `gemini-3-flash-preview`, `gemini-2.5-pro`, `gemini-2.5-flash`; `claude-fable-5`, `claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5`; `openrouter-deepseek`, `openrouter-haiku`; `codex-cli`, `claude-cli`, `claude-cli-opus`, `claude-cli-sonnet`, `claude-cli-haiku`, `claude-cli-fable`, `gemini-cli-pro`, `gemini-cli-flash`. Plus the open-ended `openrouter:<model>` prefix form.

**Unique hardening (exists nowhere else in the family)**:
1. **Subscription-billing key-stripping in every CLI backend.** `codex_interface.py:146` strips `OPENAI_API_KEY`; `claude_cli_interface.py:71` strips `ANTHROPIC_API_KEY`; `gemini_cli_interface.py:72-73` strips `GEMINI_API_KEY` + `GOOGLE_API_KEY` from the subprocess env. Without this, a key loaded from `.env` into `os.environ` outranks the CLI's subscription login and the "keyless" CLI path silently bills the metered API (documented in this repo's `CLAUDE.md`).
2. **Codex bubblewrap/user-namespace workaround for hardened Linux.** `codex_interface.py:25-70`: probes `unshare --map-root-user`; when `kernel.apparmor_restrict_unprivileged_userns` blocks codex's bundled bwrap, wraps codex in an identity-mapped userns via setuid `newuidmap`/`newgidmap` with codex's own sandbox disabled (`:137-141`). Requires `uidmap` installed. On unrestricted hosts it leaves codex's own read-only sandbox in place.
3. **`openrouter:<upstream-id>` prefix passthrough** (`ai_helper.py:83-90`): any OpenRouter model works with no code change; checked before the exact-match registry lookup. Covered by 17 routing tests.
4. **Hardened OpenRouter client** (`ai_helper.py:52-57`): `max_retries=6`, `timeout=120.0`, with measured evidence in the docstring (20-26% paragraph loss at 4-way fan-out under SDK-default 2 retries). Plus the `max_tokens=4096` over-reservation fix (`:315-321`): OpenRouter 402-gates on reserved max_tokens, not actual usage.

Also unique: `temperature=None` omission for Claude models that reject sampling params (Fable 5 / Opus 4.8; `ai_helper.py:119-128`, `:302-303`), `reasoning_effort` on OpenAI calls (`:225`), and the claude-CLI model heuristic includes `"fable"` (`claude_cli_interface.py:40`; SD's list is haiku/sonnet/opus/claude only).

**Gaps**: no meta/finish_reason contract, no per-request timeout plumbing on the API path, no hosted-llm or Venice provider, no `initialize_llm` dispatch (three registries to sync by hand: `ai_helper.py`, `DEFAULT_MODELS` in `llm_creative_tester.py:29`, `AVAILABLE_MODELS` in `llm_tester_ui.py:22`), Gemini/Claude/OpenRouter API errors are swallowed into `return None`.

**Env vars**: `OPENAI_API_KEY`, **`ANTHROPIC_API_KEY`** (note the SD/NW conflict), `GEMINI_API_KEY`, `OPENROUTER_API_KEY`; strips `GOOGLE_API_KEY` too. Loads `.env` via `load_dotenv()` (`ai_helper.py:11`), which is exactly why the key-stripping is necessary.

**Benchmark status**: this repo is a longitudinal benchmark. Its v1 analysis code is frozen and its runs are only comparable if the generation path (model params, defaults, system prompts) stays fixed. Package adoption here has special rules (Section 7, step 3).

### 3.3 NovelWriter (`core/generation/`)

Live files: `ai_helper.py` (303), `llm_interface/__init__.py` (64), `llm_interface.py` (177), `multi_provider_llm.py` (312), `codex_interface.py` (132), `gemini_cli_interface.py` (133), `claude_cli_interface.py` (157). Layer static since **2026-01-23** (`95bb5bf`); repo HEAD moved only for docs since.

**Two internal registries, out of sync with each other**:
- `multi_provider_llm.py:197-229` (what the GUI sees via `get_supported_models()`): `gpt-4o`, `o3`, `o4-mini`, `gpt-5-2025-08-07`, `gemini-2.5-pro-exp-03-25`, `claude-4-5-sonnet`.
- `ai_helper.py:67-102` (legacy facade): the same six **plus** `gemini-3-pro-preview` and `claude-4-5-opus`.

**Unique features worth absorbing**: `is_available()` static probes on all three CLI classes (`codex_interface.py:38-48`, `gemini_cli_interface.py:42-52`, `claude_cli_interface.py:41-51`), aggregated by `check_cli_availability()` (`llm_interface.py:167-177`) and consumed by the GUI (`core/gui/app.py:44-71`, `:253`). CROSS_POLLINATION already scoped these into the package.

**Gaps / hazards**: no key-stripping (no `env=` anywhere) **and** it loads `.env` (`ai_helper.py:31`), so NW's CLI backends are live exposed to the billing gotcha the analyzer fixed: an `OPENAI_API_KEY`/`CLAUDE_API_KEY` in NW's `.env` is inherited by `codex`/`claude` subprocesses. Codex runs with `--dangerously-bypass-approvals-and-sandbox` from the **project cwd** (no `neutral_cwd`), the worst combination in the family. `MultiProviderInterface.generate` accepts `timeout=120` but ignores it (`multi_provider_llm.py:296-298`). Model list is 2025-era. Env var is `CLAUDE_API_KEY` (`multi_provider_llm.py:69`). Zero tests.

### 3.4 Prompt-Injection-Testing

`ai_helper.py` (333) + `cli_backends.py` (298, single file), both last touched 2026-04-07 (`61e0d97`). Providers: OpenAI (chat + o-series), Gemini, Anthropic, plus the three CLIs. 36-key registry spanning `gpt-4o` through `gpt-5.4`, `claude-3-5-sonnet` through `claude-opus-4.6`, `gemini-1.5` through `gemini-3.1-pro-preview`, and `codex*`/`claude-cli*`/`gemini-cli*` keys. Only fork with lazy try/except client init (`ai_helper.py:14-35`). Its `cli_backends.py` is an earlier, lighter sibling of the analyzer package: **no** `neutral_cwd`, **no** key-stripping, **no** userns workaround; codex runs `--dangerously-bypass-approvals-and-sandbox` (`cli_backends.py:188-190`). Consumers: `judge.py`, `expand.py`, `gui.py`, `detectors/`. Env: `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`. No tests.

### 3.5 CryptoAlertBot

`src/ai_helper.py` (221), last touched 2025-12-17 (first commit). OpenAI + Gemini live; **the Claude path is dead code**: `send_prompt_claude` references `anthropic_client` (`src/ai_helper.py:203`) but the module never imports `anthropic` nor defines the client, so selecting `claude-3-5-sonnet`/`claude-3-7-sonnet` raises `NameError`. Registry: `gpt-4o`, `o1`, `o1-mini`, `o3`, `o4-mini`, `gemini-1.5-pro-latest`, `gemini-2.0-pro-exp-02-05`, `gemini-2.5-pro-exp-03-25`, plus the two broken Claude keys. Eager client init at import (`:14`). Consumers: `src/reporters/ai_market_reporter.py` and `_alt.py`. No tests.

### 3.6 DungeonGPT

`ai_helper.py` (37), last touched 2026-02-18. The primitive ancestor form: one OpenAI-only `send_prompt(prompt, model="gpt-4o-mini", max_tokens=1500, temperature=0.7, role_description=...)` (`:18`), no registry, plus a dead `google.generativeai` import (`:7`). Its consumers (`character_creation.py:250`, `chat_interface.py:171`) pass generation params directly, a different signature from every registry fork; migration needs a shim.

### 3.7 ScrambleGate

`archive/analysis/ai_helper.py` (220), frozen 2025-08-20. Confirmed dead: the only occurrence of `ai_helper` in the repo is the file's own header; nothing imports it. Value is archaeological (it is the complete ancestor that CAB copied badly). **Excluded from migration.**

### 3.8 LLM-Remote-Runner (TypeScript, for the source-of-truth question)

Adapters under `gateway/src/adapters/`: API adapters `openai-api.adapter.ts`, `anthropic-api.adapter.ts`, `gemini-api.adapter.ts`; CLI adapters `codex.adapter.ts`, `claude-cli.adapter.ts`, `gemini-cli.adapter.ts`. Model catalogs live in each adapter's `getAvailableModels()`, not in `app.config.ts` (which holds env-defaults only):

- OpenAI (`openai-api.adapter.ts:23`): `gpt-5.5`, `gpt-5.4`, `gpt-5.2`
- Anthropic (`anthropic-api.adapter.ts:24`): `claude-sonnet-4-5-20250929`, `claude-haiku-4-5-20251001`
- Gemini (`gemini-api.adapter.ts:23`): `gemini-3.1-pro-preview`, `gemini-3-pro-preview`, `gemini-3-flash-preview`, `gemini-2.5-pro`, `gemini-2.5-flash`

**No OpenRouter, no Venice, no local/self-hosted support**: grep over `gateway/src/` finds zero hits for `openrouter`, `venice`, `ollama`, `self-hosted` (only an optional `*_BASE_URL` override env per provider, with no first-class UI/config). Repo last commit 2026-05-21; adapters last touched 2026-05-19.

---

## 4. Model registry drift at a glance

| Repo | OpenAI keys | Anthropic keys | Gemini keys | Other |
|---|---|---|---|---|
| SD | gpt-5.5 / 5.4 / 5.2 | sonnet-4.5, haiku-4.5, `claude-4.5` alias | 3-flash-p, 3-pro-p, 3.1-pro-p, 2.5-pro, 2.5-flash | hosted-llm, openrouter, venice |
| AN | gpt-5.5 / 5.4 / 5.4-mini / 5.2 | fable-5, opus-4-8, sonnet-4-6, haiku-4-5 | 3.1-pro-p, 3.1-flash-p, 3-pro-p, 3-flash-p, 2.5-pro, 2.5-flash | openrouter-* keys + `openrouter:` prefix; 8 CLI keys |
| NW | gpt-4o, o3, o4-mini, gpt-5-2025-08-07 | claude-4-5-sonnet (+opus in one of its two registries) | gemini-2.5-pro-exp-03-25 (+3-pro-p in one) | none |
| PIT | gpt-4o..gpt-5.4 (12 keys) | claude-3-5..opus-4.6 (6 keys) | 1.5..3.1-pro-p (7 keys) | 11 CLI keys |
| CAB | gpt-4o, o1, o1-mini, o3, o4-mini | 2 broken keys | 3 keys (2025-era) | none |
| RR (TS) | gpt-5.5 / 5.4 / 5.2 | sonnet-4-5-2025..., haiku-4-5-2025... | same 5 as SD minus 3.1-flash | none |

Note the naming-convention split even where models overlap: SD uses `claude-sonnet-4.5`, AN uses `claude-sonnet-4-6`, RR uses full dated IDs, NW uses `claude-4-5-sonnet`. The package registry must pick one convention and alias the rest (assumption A6).

---

## 5. Divergence matrix

Feature by repo. SG omitted (dead). "y" = present, "." = absent, "p" = partial.

| Feature (evidence) | SD | AN | NW | PIT | CAB | DG |
|---|---|---|---|---|---|---|
| finish_reason meta contract (SD `multi_provider_llm.py:270,281,294,762`) | y | . | . | . | . | . |
| Per-request timeout plumbing + SDK retry cap (SD `:79,:66`) | y | . | p (accepted, ignored) | . | . | . |
| hosted-llm provider (SD `:100`) | y | . | . | . | . | . |
| Venice provider (SD `:164,:445`) | y | . | . | . | . | . |
| OpenRouter provider | y | y | . | . | . | . |
| `openrouter:<model>` prefix passthrough (AN `ai_helper.py:83`) | . | y | . | . | . | . |
| OpenRouter client max_retries=6 / timeout=120 (AN `:52-57`) | . | y | . | . | . | . |
| OpenRouter max_tokens over-reservation fix (AN `:315`) | . | y | . | . | . | . |
| CLI subprocess key-stripping (AN codex `:146`, claude `:71`, gemini `:72`) | . | y | . | . | n/a | n/a |
| Codex bubblewrap/userns workaround (AN codex `:25-70`) | . | y | . | . | n/a | n/a |
| Codex read-only sandbox + never-approve flags | y | y | . (bypass) | . (bypass) | n/a | n/a |
| Codex `--output-last-message` capture | y | y | . | . (stdout parser) | n/a | n/a |
| `neutral_cwd()` CLI isolation | y | y | . | . | n/a | n/a |
| Gemini CLI `--skip-trust` | y | y | . | . | n/a | n/a |
| `is_available()` probes + `check_cli_availability()` (NW `llm_interface.py:167`) | . | . | y | p (availability fn only) | n/a | n/a |
| `initialize_llm` backend dispatch + aliases | y | . | y | p | . | . |
| `generate_with_retry` on every backend | y | y (CLI only) | y | y (CLI only) | . | . |
| Claude sampling-param omission for Fable 5 / Opus 4.8 (AN `:119-128`) | n/a (older models) | y | . | . | . | . |
| OpenAI `reasoning_effort` (AN `:225`) | . | y | . | . | . | . |
| `-latest` suffix fallback in dispatch | y | . | y | y | y | . |
| Tests on this layer | ~36 | 17 | 0 | 0 | 0 | 0 |
| Anthropic env var | CLAUDE_API_KEY | ANTHROPIC_API_KEY | CLAUDE_API_KEY | ANTHROPIC_API_KEY | (broken) | n/a |

### What a single-base choice would lose

- **SD as base, no merge**: loses all four analyzer hardenings (key-stripping means SD/NW CLI runs can silently bill metered API keys today; the userns workaround means codex-cli fails outright on hardened Ubuntu), loses `openrouter:` passthrough, Fable/Opus sampling-param handling, `reasoning_effort`, and NW's `is_available()` GUI probes.
- **AN as base, no merge**: loses the meta/finish_reason contract (SD's write-until-concluded loop breaks), per-request timeout plumbing (reintroduces the 22.4-minute hang class), hosted-llm and Venice providers, the `initialize_llm` dispatch layer, and the bulk of the test suite.
- **NW as base, no merge**: loses essentially everything above, plus keeps a 2025 model list and the ignored-timeout bug.

Conclusion: the package must be a deliberate merge, SD API layer + AN CLI layer + NW probes. No copy is safe to promote alone.

---

## 6. Source-of-truth revision (supersedes CROSS_POLLINATION step 4)

CROSS_POLLINATION (and SD's `CLAUDE.md:76`) treat LLM-Remote-Runner's TS list as the canonical model-name registry. That assumption is now stale on the facts:

1. RR supports **only** OpenAI, Anthropic, Gemini (plus CLI adapters). It has no OpenRouter, no Venice, no hosted/self-hosted support (verified by grep, Section 3.8).
2. The Python apps are **ahead on providers**: SD alone adds hosted-llm, OpenRouter, and Venice; the analyzer adds the open-ended OpenRouter passthrough.
3. RR's layer was last touched 2026-05-19; SD's registry moved as recently as 2026-07-15. A "TS is truth" rule where the truth lags the consumers inverts the sync burden.

**Revised recommendation (assumption A1, Edward can veto):** the new package's registry becomes the **superset source of truth** for model naming across the Python apps. LLM-Remote-Runner reconciliation becomes a separate, optional alignment step: a short doc note plus, if wanted, a small script that diffs the package registry against the TS `getAvailableModels()` lists and reports drift for the three providers RR actually supports. RR is not blocked on, and does not block, package releases. SD's `CLAUDE.md:76` sentence should be rewritten at adoption time (that edit belongs to migration step 2, not to this doc).

---

## 7. Extraction plan

### 7.1 Package contents (superset interface)

Working name `llm-backends` (per CROSS_POLLINATION), standalone repo (assumption A2).

- **API layer, from SD**: `MultiProviderInterface` with the meta contract (`generate`, `generate_with_meta`, `generate_with_retry`), `_call_with_timeout`, `SDK_MAX_RETRIES=1`, providers OpenAI / Anthropic / Gemini / hosted-llm / OpenRouter / Venice.
- **Absorbed into the API layer, from AN**: `openrouter:<model>` prefix passthrough in dispatch; OpenRouter client `max_retries=6`, `timeout=120`; conservative OpenRouter `max_tokens` default with per-call override; `temperature=None` omission handling for sampling-param-free Claude models; optional `reasoning_effort` on OpenAI calls.
- **CLI layer, from AN's `cli_backends/` package** (the hardened branch): key-stripping (default ON, see A4), userns/bubblewrap workaround, `neutral_cwd()`, codex read-only sandbox flags + `--output-last-message`, gemini `--skip-trust`, claude JSON parsing with the model heuristic **including `fable`**; merge SD's per-call timeout style (identical already) and NW's `is_available()` static probes on all three classes.
- **Dispatch, from SD/NW**: `initialize_llm(backend, model, ..., timeout)` with back-compat aliases, `check_cli_availability()`, `get_supported_models()`, `-latest` fallback, explicit-instance pattern preserved alongside the module-level convenience singleton (CROSS_POLLINATION's singleton watch-item stands).
- **One registry** in one naming convention with an alias table for each app's legacy keys (A6).
- **Tests**: port SD's ~36 backend tests and AN's 17 routing tests; add CLI-interface tests with fake subprocesses (the family currently has zero direct CLI-wrapper tests anywhere).

**What each repo contributes / receives:**

| Repo | Contributes | Receives on adoption |
|---|---|---|
| SD | API layer base, meta contract, timeouts, hosted-llm/Venice, tests | key-stripping, userns workaround, `openrouter:` passthrough, probes |
| AN | CLI hardening x4, OpenRouter client fixes, Fable/Opus handling | meta contract, timeout plumbing, dispatch layer, hosted-llm/Venice, one registry instead of three |
| NW | `is_available()` probes, GUI wiring pattern | everything: current models, isolation, key-stripping, working timeouts, tests |
| PIT | availability-check pattern (already covered) | hardened CLI layer, current registry |
| CAB | nothing | working Claude path (its `NameError` bug dies with the fork) |
| DG | nothing | optional shim only |

### 7.2 Lazy-import contract

Provider SDKs (`openai`, `anthropic`, `google.generativeai`) are imported **inside** the client getters / send functions, never at module top level. The CLI layer stays stdlib-only (`subprocess`, `shutil`, `tempfile`, `json`, `os`). Consequence: `import llm_backends` and the whole CLI path work in a venv with zero third-party packages. This mirrors two existing house patterns: the analyzer's `benchmarks/narrative_dynamics` package (stdlib until a real call, works in the minimal pytest venv) and its lazy `_send_via_*_cli` shims. This is a hard contract, enforced by a test that imports the package with the SDKs blocked.

`load_dotenv()` is **not** called by the package (SD's layer already does not; AN/NW call it at app level). Apps own their env loading; the package only reads `os.environ`.

### 7.3 Versioning and pinning policy (benchmark caveat)

- Semver git tags from `v0.1.0`. **Every behavioral default is part of the versioned contract**: registry contents, per-model `max_tokens` / `temperature` / `reasoning_effort` defaults, retry counts, timeout defaults, and which params are omitted per model. Changing any of these is at least a minor bump with a changelog line; silent default drift is the failure mode this package exists to kill.
- Default system prompts (`role_description`) are app-specific today (fiction writer vs security expert vs crypto analyst). The package ships a neutral default and every app passes its own explicitly. Defaults never silently change under an app (A5).
- **The analyzer pins an exact tag** (`llm-backends @ git+...@vX.Y.Z`) and upgrades only deliberately, between benchmark campaigns, because its longitudinal series is only valid if the generation path is frozen. Adoption itself must be payload-identical: verified with a fake-client test asserting the request kwargs (model, max_tokens, temperature presence/absence, system prompt) are byte-equal to the pre-migration ones for every registry key. Other repos may track a branch; the analyzer never does.

### 7.4 Migration order and effort

| Step | Repo | Work | Estimate |
|---|---|---|---|
| 1 | (new repo) | Extract package: SD base + AN merges + NW probes; port SD + AN tests; add CLI fake-subprocess tests; lazy-import guard test | 2-3 days |
| 2 | SD | Replace the six `novel_agent/tools/` modules with package imports; keep explicit-instance pattern; make `cli/main.py` / `commands/*.py` fallbacks read the package default (kills the dual-update footgun); update `CLAUDE.md:76` source-of-truth wording + add Venice | 1 day |
| 3 | AN | Adopt at a pinned tag; `ai_helper.send_prompt` becomes a shim; keep `DEFAULT_MODELS`/`AVAILABLE_MODELS` reading from the package (restores the 1:1 registry check); payload-equality test; only between campaigns | 1 day |
| 4 | NW | `ai_helper.py` becomes a shim; GUI dropdowns read `get_supported_models()` / `is_available()`; model-list bump off `gpt-4o`; switch `CLAUDE_API_KEY` reads to the package env handling; delete untracked `temp/llm_interface_reference/` | 1 day |
| 5 | PIT | Replace `ai_helper.py` + `cli_backends.py`; keep `config.DEFAULT_MODEL` indirection | 0.5 day |
| 6 | CAB | Replace `src/ai_helper.py`; note this un-breaks the Claude keys (behavior change: `NameError` becomes a working call, callers should be sanity-checked) | 0.5 day |
| 7 | DG | Optional: thin shim preserving its direct-param `send_prompt` signature, or skip entirely (37 lines, OpenAI-only, working) | 0-0.5 day |
| n/a | SG | None: dead code stays archived | 0 |

Total: roughly 6-7.5 days. Steps 2 and 3 are the validation gate; 4-7 are mechanical after that.

### 7.5 Distribution

Git-URL dependency with pinned tags (`pip install git+https://github.com/<user>/llm-backends@v0.1.0` or the local-path equivalent in requirements files). No PyPI (A3). `pip install -e` from a sibling checkout for day-to-day development, exactly as CROSS_POLLINATION suggested; the tag pin is what the analyzer records.

### 7.6 Risks

- **Benchmark continuity (highest).** Any accidental default change in step 3 quietly forks the analyzer's longitudinal series. Mitigation: pinned tag + the payload-equality test; adoption only between campaigns.
- **Anthropic env-var split.** SD/NW read `CLAUDE_API_KEY`; AN/PIT read `ANTHROPIC_API_KEY`. The package reads `ANTHROPIC_API_KEY` first, falls back to `CLAUDE_API_KEY` with a deprecation warning (A6). Risk: a machine with both set changes which key wins for SD/NW.
- **Key-stripping default flips billing behavior for SD/NW/PIT.** Today their CLI subprocesses inherit API keys; after adoption they authenticate via CLI login by default. That is the intended fix, but any workflow that deliberately relied on key auth inside a CLI backend breaks until it passes the opt-out flag (A4).
- **CLI flag drift.** Codex flags are pinned for codex-cli ~0.118; gemini `--skip-trust` and claude `--output-format json` are similarly version-coupled. The package centralizes them (one place to fix), but a CLI update now breaks five repos at once instead of one. Mitigation: `is_available()`-style smoke test in the package CI.
- **NW model bump.** Moving NW off `gpt-4o`/`claude-4-5-*` may perturb its generation quality expectations; CROSS_POLLINATION already flags checking callers for hardcoded defaults.
- **Singleton semantics.** SD's agent path must keep receiving an explicit instance; the package keeps both patterns, and step 2 verifies no caller silently lands on the module singleton.
- **RR drift.** With reconciliation demoted to optional, the TS list can lag. Accepted by design (Section 6); the diff script keeps it visible instead of pretending it cannot happen.

### 7.7 Stated assumptions (in place of open questions; each is vetoable)

- **A1. Source of truth**: the package registry becomes the superset model-naming truth; RR reconciliation is a separate optional alignment step (Section 6). This deliberately overrides CROSS_POLLINATION step 4 and SD `CLAUDE.md:76`.
- **A2. Home**: standalone repo named `llm-backends`, matching CROSS_POLLINATION's "recommended" option. Not inside SD, so that non-fiction consumers (PIT, CAB) do not depend on a fiction project.
- **A3. Distribution**: git-URL dependency with pinned tags; no PyPI. Revisit only if a repo needs CI installs without repo access.
- **A4. Key-stripping default ON** in all CLI backends, with an explicit `strip_provider_keys=False` opt-out per interface. Chosen because the failure mode of OFF is silent money (the analyzer's June billing incident), while the failure mode of ON is a visible auth error.
- **A5. System prompts stay app-owned**: the package default `role_description` is a neutral assistant string; every migrating app passes its current prompt explicitly so no app's outputs change from prompt drift.
- **A6. Naming**: registry adopts the analyzer-style hyphenated convention (`claude-sonnet-4-6`) as primary, since it is the most current list, with an alias table covering SD (`claude-sonnet-4.5`), NW (`claude-4-5-sonnet`), and `-latest` fallbacks; `ANTHROPIC_API_KEY` is canonical with `CLAUDE_API_KEY` as a warned fallback.
- **A7. Scope**: SG is excluded (dead code); DG is optional; Codex-Remote-Runner is out of scope (predecessor, no shared layer); RR itself is not migrated (TypeScript stays where it is).
- **A8. Timing for the analyzer**: adoption happens between benchmark campaigns, never mid-corpus; if a campaign is running when the package ships, the analyzer simply stays on its current in-repo code until the campaign ends.

---

## Appendix: sweep coverage

The repo sweep grepped every `*.py` under `/home/edward/Projects/` (excluding venv/node_modules/.git trees) for `send_prompt`, `multi_provider`, `ai_helper`, `cli_backends`, `MultiProviderLLM`, `neutral_cwd`. Hits: SD (41 files), NW (15), AN (13), PIT (7), CAB (4), DG (3), SG (1). No other repo contains this family; other LLM-using repos (e.g. nanochat, PromptDesk) do not share this code lineage and are out of scope.

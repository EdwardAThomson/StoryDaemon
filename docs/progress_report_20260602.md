# Progress Report — 2nd June 2026 (Opus 4.8)

End-to-end **validation** of the Phase 3 coherence pressures (active roadmap:
`EMERGENT_COHERENCE_PLAN.md`), plus the backend fix that finally made long
unattended runs possible. This is a findings log — the headline is *what we
learned by running the system at length*, not new features.

## 1. Backend reliability — the prerequisite

Long validation runs were blocked because no backend survived a multi-tick `run`.

- **gemini-cli (`gemini-3-flash-preview`) times out on the *planner* call ~tick 2.**
  Root cause is **not** request size — inputs are modest and calls are stateless.
  It's *generation time*: `gemini -p` is a full agent wrapper, and the preview model
  does extended "thinking" on the heaviest prompt (the multi-stage planner, which
  grows as the story does). Variance-driven — the same tick succeeded on a standalone
  retry.
- **`claude-cli` + `haiku` is reliable:** 15/15 and 16/16 ticks with **0 retries /
  0 timeouts**, once Windsurf (which was silently clobbering the `claude`/`codex`
  binaries every few minutes) was closed. Now the recommended local backend for
  multi-tick runs. (For unattended production, the `api` backend is still ideal but
  needs a key; `google-generativeai` is not installed, so Gemini-via-API needs a
  `pip install` first. OpenAI + Anthropic SDKs are present.)
- **Architecture note (worth remembering):** every LLM call is a **fresh, stateless
  `claude -p` subprocess** with the entire context in the prompt; the `run` loop even
  rebuilds the `StoryAgent` from disk each tick. Continuity lives entirely in
  StoryDaemon's files (`state.json`, `memory/`, vector store), never in an LLM
  session. That's *why* retries are safe — there is no session to corrupt.
- **Shipped:** `novel run --retries N` (default 1) retries a failed tick before
  stopping the whole run (commit `82ac2fc`).

## 2. Arc-pressure validation — works on the rise, fails the resolution

Two sustained runs (`claude-cli`/`haiku`, corporate-thriller foundation, a
user-specified goal):

- **Rising arc** (`claudetest`, `target_story_length=40`, 20 scenes, ~29k words):
  tension tracks the rising target; mean `|tension − target|` drift **1.36**, with a
  consistent **~+1.4 upward bias** — the thriller generator runs hot against the
  gentle early targets.
- **Full arc incl. descending tail** (`descent`, `target_story_length=15`, 16 scenes,
  ~29k words): rise tracked well (drift **1.20**; the prose rewrite trimmed *moderate*
  overshoot down on several ticks, e.g. 9→6). **But the resolution DROP failed** —
  the final scene's target was **4**, actual **8**. The rewrite fired
  (`Tension 8/10 off target 4 — revising once`) but `revision not closer (8);
  keeping original`.

## 3. Diagnostic — why low tension is unreachable, and whose fault it is

Scored controls + real scenes through the live LLM tension scorer (`claude-cli`):

| scene | score | scorer's reasoning (abridged) |
|---|---|---|
| calm denouement (control) | **1/10** | "crisis resolved and in the past… no active threat or stakes" |
| moderate planning (control) | 5/10 | "investigative setup, mounting complications… rising, not high" |
| real opening (target 3.5) | 5/10 | "rising stakes… impossible gaps in security logs… someone tampered" |
| real ending (target 4) | 7/10 | "physical containment, active confrontation… 90 minutes to a critical statement" |

Conclusions:

- **The scorer is sound** — it emits **1/10** for a genuinely calm scene. The floor is
  *not* a gauge artifact (contrast the earlier keyword-heuristic and embedding-similarity
  failures).
- **The generator *can* write calm** — the 1/10 control proves it.
- **The floor is the PLANNER.** It chose tense *events* (a discovery, a confrontation)
  regardless of the low target. The opening "5" and the ending "7–8" are *correct*
  scores of *genuinely tense events*. This is the project's founding thesis confirmed
  empirically: **tension lives in the events, not the prose.**
- **The prose rewrite is the wrong tool for a big drop** — you cannot re-word a
  confrontation into calm; only changing the *events* lowers it.
- **Pacing blindness:** at the *final* scene the planner was still writing the *climax*
  ("90 minutes to a critical statement"), not the aftermath. It doesn't know it is past
  the peak — it reads the target as a scalar "how tense should the prose *feel*," not as
  an arc *phase*.
- **Throughline ↔ arc-pressure conflict:** "always advance the goal" pushes stakes up
  while "now be calm" pushes them down; the planner resolves toward stakes every time.

## 4. Goal-relevance (throughline) — ceiling effect, gauge sound

On a goal-aligned foundation, `goal_relevance` stays high (~7–10) with the throughline
pressure on *or* off. The LLM judge clearly discriminates (1 vs 10 on controls), but the
story has no headroom to drift off-goal when the premise *is* the goal. Validating the
pressure needs a looser / multi-thread foundation.

## 5. Next concrete step (not yet implemented)

**Arc-*phase* planner mandate.** Give the planner the arc phase (rising / at-peak /
falling), not just a scalar number → **escalate / confront / resolve**. In the falling
phase, *mandate* (don't nudge) low-stakes events with concrete ingredients: resolve an
open loop, aftermath/fallout, time-skip, show the cost. Skip the prose rewrite for big
drops. Let arc-pressure win over throughline pressure during the resolution phase. Then
re-run `descent` and check whether the ending finally lands calm.

(Related code: `agent/arc_pressure.py`, `agent/multi_stage_planner.py` strategic prompt,
`agent/writer.py:revise_for_tension`. Knobs: `coherence.target_tension_curve`,
`target_story_length`, `tension_step_for_transition`, `tension_rewrite`.)

## Artifacts

- Preserved scratch stories (gitignored `work/`): `work/novels/claudetest_*/manuscript.md`
  (~29k words, the rising-arc run) and `work/novels/descent_*/manuscript.md` (~29k words —
  note it stays tense through the ending; the gap made visible).
- The same findings are mirrored in the agent's memory store
  (`arc-pressure-validation`, `throughline-ab-ceiling-effect`).

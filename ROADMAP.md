# Roadmap — StoryDaemon

_Status: active · updated 2026-05-31_

An agentic long-form fiction generator: an autonomous LLM agent runs iterative
"story tick" cycles (plan → tools → write → evaluate) that grow characters, lore,
and plot emergently rather than from a pre-plan. Python, multi-backend. The active
strategic plan is `docs/EMERGENT_COHERENCE_PLAN.md`.

## Shipped

- [x] Agentic story-tick loop (plan → tool use → write → evaluate)
- [x] Multi-backend LLM support (Codex / Gemini / Claude Code CLIs + OpenAI / Claude / Gemini APIs / Self-hosted OpenAI compatible)
- [x] Deep-POV writing with POV validation + character-continuity checks
- [x] Dynamic memory — characters, locations, factions, relationships, scenes persist and evolve
- [x] ChromaDB vector search for semantic context retrieval
- [x] Story Foundation system (immutable constraints + interactive setup)
- [x] Emergent plot-first mode — rolling-horizon beats, beat-constrained writing + verification (Phase 2)
- [x] Multi-stage planner (strategic → semantic → tactical, with token reduction)
- [x] Tension tracking (LLM 0–10 scoring, dynamic pacing, arc-pressure control)
- [x] Contradiction detection (lore contradictions, dispute quarantine)
- [x] Per-tick coherence rubric (loop churn, contradictions, tension vs. target, goal relevance) via `novel metrics`
- [x] Goal hierarchy (immediate / arc / story goals, auto-promotion, throughline gate + LLM goal-relevance judge)
- [x] Lore system (rules, constraints, facts, capabilities per tick, dedup)
- [x] Checkpointing (project snapshots + restore)
- [x] Manuscript compilation (Markdown / HTML export, scene filtering)
- [x] Grounded name generator (syllable-based, culture/era banks) (Phase 1)
- [x] Full CLI (`novel new`, `tick`, `run`, `resume`, `status`, `goals`, `lore`, `compile`, `plot`, …)
- [x] Neutral-CWD isolation for CLI backends (avoid repo-awareness derailment)
- [x] 250+ tests (unit, integration, manual scenarios)

## Next

- [ ] **Arc-_phase_ planner mandate** — validation (`docs/progress_report_20260602.md`) showed arc-pressure tracks *rising* targets but can't de-escalate for a resolution: the planner keeps choosing tense events and the prose rewrite can't lower them. Give the planner rising/peak/falling phase → escalate/confront/**resolve** (aftermath, close a loop, time-skip); skip the rewrite for big drops.
- [ ] Add support for guided generation per tick
- [ ] Loop-aging pressure (older open loops surface louder for payoff)
- [ ] Block / sub-block DSL contracts (per-beat deterministic checks)
- [ ] Validate the throughline gate with a headroom scenario (goal-aligned foundations hit a ceiling — the LLM gauge is sound, but the pressure shows no lift when the story is already on-goal)
- [ ] Resolve embedding-similarity placeholders in `multi_stage_planner.py`
- [ ] Scene-summarization callback stub in `cli/main.py` (Phase 2)

## Backlog

- [ ] Phase 4 — setup/payoff foresight (planted-element ledger for Chekhov's guns)
- [ ] Plan explicit low-tension beats if arc-pressure proves insufficient

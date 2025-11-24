# Implementation Checklist: Emergent Plot-First Architecture

This checklist merges the plans from `ARCHITECTURE_PROPOSAL_EMERGENT_PLOTTING.md` and `PROPOSED_CHANGES_FORWARD_MOMENTUM.md` into a single ordered sequence of work.

---

## Phase 0 – Align with Reality (Current State)

- [x] **Confirm current planner/writer prompts**
  - [x] Verify planner is already producing `key_change` or `progress_milestone` / `progress_step`.
  - [x] Verify writer prompt explicitly requires accomplishing `key_change` or the milestone.
  - [x] Confirm tool guidance (memory.search, character/location/relationship tools) is present.

- [x] **Update docs if needed**
  - [x] Make sure the “current architecture” description acknowledges existing forward-momentum constraints (so it’s not purely reactive anymore).

---

## Phase 1 – Prompt-Only Additions + QA Loop (Near-Term)

### 1. Planner fields and heuristics

- [x] **Extend planner output schema** to include:
  - [x] `scene_mode`: `"dialogue" | "political" | "action" | "technical" | "introspective"`.
  - [x] `palette_shift`: short bullet list of sensory/emotional palette elements.
  - [x] `transition_path`: 1–3 sentence outline of how we move from previous location/time.
  - [x] `dialogue_targets`: e.g. `{ min_exchanges, conflict_axis, participants }`.

- [x] **Prompt changes**
  - [x] Update planner prompt to explain each field and show examples.
  - [x] Add heuristics:
    - [x] Prefer a different `scene_mode` than the previous scene.
    - [x] If last scene was technical, bias to dialogue/political for next.

### 2. Writer enforcement

- [x] **Update writer prompt** to enforce new fields:
  - [x] If `transition_path` exists, include a brief bridge paragraph (anchor-from → traversal → anchor-to).
  - [x] If `dialogue_targets.min_exchanges` exists, ensure at least that many exchanges and a visible power shift or decision in dialogue.
  - [x] Use `palette_shift` elements in description (without overdoing it).

### 3. QA step + planner feedback

- [x] **Implement QA module** that runs after each scene:
  - [x] `achieved_change`: boolean + explanation (did `key_change`/milestone land?).
  - [x] `dialogue_count` and `met_target` vs `dialogue_targets`.
  - [x] `transition_clarity`: 0–10 + `notes`.
  - [x] `mode_used` and `mode_diversity_warning` if repeating modes.
  - [x] `novelty_score`: 0–10 against last N scenes.
  - [x] `continuity_flags`: list of potential issues.

- [x] **Persist QA results** (e.g., JSON per scene).

- [x] **Feed QA into planner**
  - [x] Surface key QA warnings in planner context (e.g., “last scene repeated tech mode; prefer dialogue/political”).
  - [x] Update planner prompt to reference `qa_feedback` and self-correct.

---

## Phase 2 – Factions (World Grounding)

- [x] **Define Faction schema** in memory layer:
  - [x] Fields: `id`, `name`, `type`, `summary`, `mandate_objectives`, `influence_domains`,
        `assets_resources`, `methods_tactics`, `stance_by_character`, `relationships`,
        `importance`, `tags`.

- [x] **Implement faction tools**
  - [x] `faction.generate` (creates new `F#`, initial fields).
  - [x] `faction.update` (partial updates, esp. stances, assets, relationships).
  - [x] `faction.query` (filters: type, tags, importance, name_contains).

- [x] **Prompt integration**
  - [x] Planner: add a “Factions” context section summarizing relevant factions.
  - [x] Planner: allow/encourage plans that call `faction.generate/update/query`.
  - [x] Writer: first time a faction appears in a scene, include one-line identity grounding.

- [ ] **QA integration**
  - [ ] QA flags ungrounded named groups and suggests creating a faction.

---

## Phase 3 – PlotBeat Phase 1 (CLI-Only, Non-Invasive)

- [x] **Implement PlotBeat / PlotOutline entities** (data layer)
  - [x] `PlotBeat` struct/class with fields from both docs:
    - [x] `id`, `description`, `characters_involved`, `location`, `plot_threads`,
          `tension_target?`, `prerequisites`, `status`, `created_at`,
          `executed_in_scene?`, plus metadata like `advances_character_arcs`,
          `resolves_loops`, `creates_loops`.
  - [x] `PlotOutline` struct/class with:
    - [x] `beats`, `created_at`, `last_updated`, `current_arc`, `arc_progress`,
          `to_dict` / `from_dict` (backed by `plot_outline.json` at project root).

- [x] **Implement PlotOutlineManager (non-agent, data-layer only)**
  - [x] `load_outline` / `save_outline`.
  - [ ] `generate_next_beats(count)` using LLM + plot-generation prompt (deferred to Plot generation prompt section).
  - [x] `add_beats` (append validated beats).
  - [x] `get_next_beat` (next pending).
  - [x] Basic validation (duplicates, feasibility, prerequisites).

- [ ] **CLI commands**
  - [x] `novel plot generate --count N` → generate & append beats to outline.
  - [x] `novel plot status` → show pending/completed beats + arc progress (implemented via `novel plot status`).
  - [x] `novel plot next` → preview the next pending beat (implemented via `novel plot next`).
  - [x] CLI scaffolding for `novel plot generate --count N` stub (no LLM integration yet).
  - [x] `novel plot status --detailed` → show detailed beat list including status and execution info.

- [ ] **Plot generation prompt**
  - [x] Define Beat JSON contract for LLM output (see `docs/PLOTBEAT_BEAT_SCHEMA_AND_TRANSITIONS.md`).
  - [x] Implement the factual, non-prose beat prompt + JSON parsing for CLI `novel plot generate` (open loops, arcs, recent scenes, tension history in → JSON beats out).
  - [ ] Wire prompt + parsing into `PlotOutlineManager.generate_next_beats(count)` for future agent integration.

- [ ] **Manual evaluation loop**
  - [x] Run beats for the current story, review directionality & coherence manually.
  - [ ] Tweak prompt/validation based on observed beat quality.

---

## Phase 4 – Soft Integration into the Agent Loop

- [x] **Expose beats softly to planner**
  - [x] Pass `next_beat.description` (and maybe characters/location) into planner context as a hint, not a hard constraint.
  - [x] Observe whether planner naturally moves in that direction.

- [x] **Add `plan_for_beat` path**
  - [x] Implement `planner.plan_for_beat(beat, context=story_state())`.
  - [x] Ensure resulting plan still includes:
    - [x] `key_change` / `progress_milestone`.
    - [x] `scene_mode`, `palette_shift`, `transition_path`, `dialogue_targets`.
  - [x] Use this path under a feature flag/config (e.g. `use_plot_first_soft`).

- [x] **Integrate with QA**
  - [x] Add QA field `beat_hint_alignment` (did the scene generally follow the suggested beat?).

### Phase 4B – Guided Beat Contract (Design)

- [x] **Planner beat targeting**
  - [x] Extend planner plan schema with optional `beat_target` object:
    - [x] `beat_id` (current pending beat ID or null).
    - [x] `strategy` (e.g. `direct | setup | followup | skip`).
    - [x] `notes` explaining why the beat is executed, deferred, or skipped.

- [x] **Beat lifecycle tracking in plot_outline**
  - [x] Use `status` values such as `pending | in_progress | executed | skipped`.
  - [x] Record `executed_in_scene` when QA `beat_hint_alignment` is `medium`/`high` for `beat_target.beat_id`.
  - [x] Append brief auto-generated `execution_notes` describing how/when the beat was completed.

- [x] **Configuration for beat integration strictness**
  - [x] Add `plot.beat_mode` config: `off | soft_hint | guided | strict`.
  - [x] Implement `guided` mode first (planner fills `beat_target`, beats updated using QA), leaving `strict` as a future enhancement.

---

## Phase 5 – Full Emergent Plot-First Tick

- [ ] **Integrate PlotOutlineManager into `StoryAgent`**
  - [ ] Add `self.plot_manager` initialization.
  - [ ] In `tick`:
    - [ ] Call `needs_regeneration()` and `generate_next_beats()` when pending beats < threshold.
    - [ ] Fallback to reactive tick if no beats and generation fails (per config).

- [ ] **Beat-constrained planning**
  - [ ] Implement `_generate_plan_for_beat(beat)` or equivalent:
    - [ ] Build planner context + beat info (description, characters, location).
    - [ ] Call `planner.plan_for_beat`.
  - [ ] Ensure this path is controlled by config (e.g. `use_plot_first: true`).

- [ ] **Beat-constrained writer context**
  - [ ] Inject into writer context:
    - [ ] `plot_beat` description.
    - [ ] `plot_beat_requirements` (characters, location, tension target, etc.).
  - [ ] Update writer prompt to treat the beat as a hard goal.

- [ ] **Verification + status updates**
  - [ ] Move beat-execution verification into QA (or `_verify_beat_execution` wrapper that uses QA).
  - [ ] On verified completion:
    - [ ] `plot.mark_beat_complete(beat.id, scene_id)`.

- [ ] **Configuration & defaults**
  - [ ] `use_plot_first`, `plot_beats_ahead`, `plot_regeneration_threshold`,
        `verify_beat_execution`, `allow_beat_skip`, `fallback_to_reactive`.
  - [ ] Initially disabled / opt-in; later, make plot-first the default for new projects.
  - [ ] Add migration note/tool for existing projects.

---

## Phase 6 – Advanced / Optimization

- [ ] **Multi-arc management**
  - [ ] Track multiple arcs; associate beats with arcs; compute `arc_progress`.

- [ ] **Beat branching / alternative paths**
  - [ ] Support optional/branching beats, reordering for pacing.

- [ ] **Tension curve optimization**
  - [ ] Use tension history + metrics to adjust future `tension_target`s.

- [ ] **Metrics + dashboards**
  - [ ] Track: loop progress rate, mode diversity, dialogue density, novelty vs N, QA compliance, beat completion rate.

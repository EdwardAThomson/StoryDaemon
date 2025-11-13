# Proposed Changes: Momentum, Variety, and Emergent Plotting

## Goals

- Reduce repetitive feel across scenes while preserving coherence.
- Ensure each scene makes meaningful progress (change or milestone) without rushing resolutions.
- Increase dialogue density and diversify scene modes (technical, dialogue, political, action, introspective).
- Establish a feedback loop (QA) that informs subsequent planning.
- Lay groundwork for an emergent plot-first workflow (beats → prose).

## Summary of Near-Term Changes (Prompt + Context)

- **Already implemented**
  - **Forward momentum prompts**: Planner now requires `key_change` or a `progress_milestone`, `progress_step` (optional), and encourages loop advancement without forcing premature resolutions.
  - **Writer constraint**: Writer receives `key_change` and optional `progress_milestone` and must accomplish one or clearly achieve the other, with a turning point or clear setup beat.
  - **Tool guidance restored**: Explicit instructions for memory.search, character/location/relationship tools.

- **Proposed additions (prompt-only, low risk)**
  - **Planner new fields**
    - `scene_mode`: "dialogue" | "political" | "action" | "technical" | "introspective" (prefer different from previous scene)
    - `palette_shift`: short bullet list to vary sensory/emotional palette (e.g., heat, copper, crowd-noise; or administrative neon, recycled air, clipped voices)
    - `transition_path`: 1–3 sentence outline for the physical/temporal move between locations to avoid abrupt jumps
    - `dialogue_targets`: `{ min_exchanges: 6, conflict_axis: "leverage vs trust", participants: ["C0","corp_proxy"] }`
  - **Writer enforcement**
    - If `transition_path` exists, include a brief bridging paragraph (anchor-from → traversal → anchor-to).
    - If `dialogue_targets.min_exchanges` exists, include at least that many back-and-forths and ensure a power shift or decision within dialogue.
    - Apply `palette_shift` details to vary texture.
  - **Planning heuristics**
    - Prefer a different `scene_mode` than the last scene.
    - If last scene was technical, bias next toward dialogue/political.

## Scene QA (Feedback Loop)

- **Add a post-writing QA step** (LLM-generated JSON), persisted and shown in planner context next tick.
- **QA checks**
  - `achieved_change`: boolean + explanation (did the scene accomplish `key_change` or milestone?)
  - `dialogue_count`: integer; `met_target`: boolean
  - `transition_clarity`: 0–10; `notes`
  - `mode_used`: detected mode; `mode_diversity_warning`: bool if repeating
  - `novelty_score`: 0–10 similarity vs last N scenes (embedding or heuristic)
  - `continuity_flags`: list of potential issues
- **Planner input**
  - Surface warnings (e.g., "Last scene repeated tech-puzzle mode; prefer dialogue/political").
  - Pass `qa_feedback` slice into planner prompt for self-correction.

## Faction System (Entities + Tools)

- Introduce a first-class Faction entity to ground any organization (corporate, agency, guild, cult, AI collective, etc.).

### Faction schema (memory)
- `id`: F0, F1, ...
- `name`: string
- `type`: corporate | government | guild | criminal | cult | ai_collective | syndicate | consortium | other
- `summary`: 1–2 sentence description
- `mandate_objectives`: list of goals
- `influence_domains`: list (e.g., logistics, security, research, media)
- `assets_resources`: list (ships, labs, proxies, budgets)
- `methods_tactics`: list (legal pressure, blackmail, sabotage, propaganda)
- `stance_by_character`: map character_id -> friendly|neutral|hostile|exploitative|unknown
- `relationships`: links to other factions (ally/rival/parent/subsidiary)
- `importance`: low|medium|high|critical
- `tags`: list

### Tools
- `faction.generate`
  - Args: `name?`, `type`, `summary`, `mandate_objectives?`, `initial_stance_by_character?`, `importance?`, `tags?`
  - Behavior: creates `F#` and stores to memory
- `faction.update`
  - Args: `id`, partial fields (e.g., `stance_by_character`, `assets_resources`)
- `faction.query`
  - Args: filters (`type`, `tags`, `importance`, `name_contains`)

### Planner prompt changes
- Show a "Factions" context section summarizing relevant factions.
- Allow actions with `faction.generate`, `faction.update`, `faction.query`.
- When a new faction is introduced, suggest generating a representative face via `character.generate` and adding `dialogue_targets` with that representative.

### Writer prompt changes
- If factions are involved, briefly ground who they are (one-line identity) the first time they appear in a scene.

### QA addition
- Flag ungrounded references to groups; suggest generating a faction when undefined.

### Example for this story (optional)
- Faction: "Eidolon Logistics Directorate (ELD)" (type: corporate), mandate: custody of relay assets; method: contractual coercion; importance: high.
- Representative: "Proxy Aram Vesc" created via `character.generate` when first needed.

## Testing Plan (Near-Term)

1. Run 2–3 ticks with new planner/writer fields enabled.
2. Verify plans include `scene_mode`, `palette_shift`, `transition_path`, `dialogue_targets` (when applicable).
3. Confirm writer output:
   - Transition paragraph exists on location change.
   - Dialogue exchanges ≥ target when requested.
   - Palette noticeably differs from prior scene.
4. Review QA JSON and confirm its warnings appear in next planner context.

## Risks & Mitigations (Near-Term)

- **Risk**: Over-constraining the writer → stilted prose.
  - Mitigation: Keep targets soft (minimums), and palette guidance as suggestions.
- **Risk**: Planner ignores new fields.
  - Mitigation: Add validation nudge; synthesize defaults if fields absent; echo QA reminders in planner context.

---

## Medium-Term: PlotBeat Phase 1 (Non-invasive CLI)

- **Components**
  - `PlotBeat`, `PlotOutline` entities
  - `PlotOutlineManager` with `load/save/generate_next_beats/add_beats/get_next_beat`
  - `plot_outline.json` stored at project root
- **CLI commands**
  - `novel plot generate --count 5` — generate and append beats
  - `novel plot status` — show pending/completed beats
  - `novel plot next` — preview next pending beat
- **Usage**
  - Generate beats for the current story and evaluate directionality before integrating with the planner.
- **Risk**: Beat quality variability.
  - Mitigation: Beat validation via QA-like checklist (duplicates, feasibility, prerequisites).

---

## Long-Term: Emergent Plot-First (Pseudocode)

Below is a high-level pseudocode sketch for a middle-out pipeline where the agent drafts plot beats emergently and then writes prose to execute them.

```pseudo
function tick(project_state):
  if plot.needs_regeneration(min_pending = 2):
    beats = plot.generate_next_beats(count = 5, context = story_state())
    plot.add_beats(beats)

  beat = plot.get_next_beat()
  if not beat:
    # Fallback to reactive planning if no beats
    return reactive_tick(project_state)

  # Planning constrained by beat
  plan = planner.plan_for_beat(beat, context = story_state())
  plan = validate_and_fill(plan)  # ensure key_change/progress_milestone, scene_mode, etc.

  # Tool execution + prose
  exec_results = runtime.execute_plan(plan)
  writer_ctx = writer_context.build(plan, exec_results, project_state)
  writer_ctx.plot_beat = beat
  scene = writer.write_scene(writer_ctx)

  # QA + verification
  qa = qa.evaluate(scene, plan, last_scenes = N)
  verified = qa.verify_beat_execution(scene, beat)

  # Commit + update
  scene_id = committer.commit_scene(scene, qa)
  if verified:
    plot.mark_beat_complete(beat.id, scene_id)

  memory.extract_and_update(scene)
  lore.extract(scene)
  state.advance_tick()
  return artifacts(plan, scene, qa)
```

### Data Structures (sketch)

```pseudo
struct PlotBeat:
  id: PBnnn
  description: string (factual)
  characters_involved: [C ids]
  location: L id | null
  plot_threads: [strings]
  tension_target: 0..10 | null
  prerequisites: [PB ids]
  status: pending|in_progress|completed|skipped
  created_at: iso
  executed_in_scene: S id | null
```

### Generation Prompt (sketch)

- Input: open loops, character arcs, recent scenes, tension history.
- Rules: factual beats, no prose; unique; prerequisite-aware; escalate/resolution mix.
- Output: list of candidate beats (JSON), validated before adding.

### Integration Strategy

1. Start CLI-only beats (observe quality).
2. Add soft hint of `next_beat.description` into planner context (no hard constraint).
3. Enable constrained planning path (`plan_for_beat`) once beat quality is sufficient.
4. Add beat execution verification, then mark as completed.

## Metrics

- Loop progress rate (per 5 scenes)
- Mode diversity (no more than 2 same-mode scenes in a row)
- Dialogue density (lines/exchanges)
- Novelty vs last N scenes (embedding cosine)
- QA compliance rate (warnings reduced over time)

## Next Steps

- Implement prompt-only additions (scene_mode, palette_shift, transition_path, dialogue_targets) and QA step.
- Add Faction entity + tools to ground organizations, and introduce an appropriate representative in the next plan when needed.
- Use PlotBeat CLI to generate and review beats for the current story before planner integration.

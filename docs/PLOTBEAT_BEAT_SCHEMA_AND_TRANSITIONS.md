# PlotBeat JSON Schema and Transitions (Phase 3 Notes)

This document captures the concrete JSON schema expected from the PlotBeat
LLM when generating new beats, and a first-pass design for how transitions
between beats are handled. It is a companion to:

- `ARCHITECTURE_PROPOSAL_EMERGENT_PLOTTING.md`
- `IMPLEMENTATION_CHECKLIST_EMERGENT_PLOTTING.md`

The goal is to keep the **plot layer** factual and structured, while allowing
the **prose layer** (planner + writer) to handle scene-level transitions and
bridges.

---

## 1. LLM Output Shape for Beat Generation

When `novel plot generate --count N` is fully implemented, it will call a
plot-generation prompt that asks the LLM to return **JSON only**, with this
shape:

```json
{
  "beats": [
    {
      "description": "...",
      "characters_involved": ["C0", "C1"],
      "location": "L2",
      "plot_threads": ["extraction_negotiation", "identity_theft"],
      "tension_target": 8,
      "prerequisites": [],
      "advances_character_arcs": ["C0_trust", "C1_identity"],
      "resolves_loops": [],
      "creates_loops": ["new_threat_sink"]
    }
  ]
}
```

### 1.1 Beat Object Schema (LLM-Facing)

Each element of `beats` is a single PlotBeat specification with the following
fields. All keys should be present; some may be empty lists or `null`.

- **`description: string` (required)**
  - One or two factual sentences describing what happens.
  - No prose stylization; this is plot-level pseudo-code.

- **`characters_involved: string[]` (optional, default `[]`)**
  - Character IDs that are materially involved in the beat.
  - Prefer canonical IDs (`"C0"`, `"C1"`, etc.).
  - If an entity is new and has no ID yet, use a clear placeholder like
    `"NEW_CTA_LIAISON"`; the system will still store it as text.

- **`location: string | null` (optional, default `null`)**
  - Location ID where the beat primarily occurs (e.g. `"L2"`).
  - If unknown/new, use `null` or a placeholder like `"NEW_LOCATION_FAR_POST"`.

- **`plot_threads: string[]` (optional, default `[]`)**
  - Free-form labels for which plot threads this beat advances, e.g.:
    - `"gravity_sink_threat"`
    - `"extraction_window"`
    - `"C0_C1_relationship"`

- **`tension_target: integer | null` (optional, default `null`)**
  - Target tension level **0–10** for this beat.
  - This is used for planning the tension curve, not hard enforcement.

- **`prerequisites: string[]` (optional, default `[]`)**
  - Beat IDs that should occur before this beat.
  - For v1, the prompt should bias toward referencing **existing beats** in
    `plot_outline.json` rather than intra-batch dependencies.

- **`advances_character_arcs: string[]` (optional, default `[]`)**
  - Labels of character arcs this beat intentionally advances
    (`"C0_trust_arc"`, `"Belia_identity_arc"`, etc.).

- **`resolves_loops: string[]` (optional, default `[]`)**
  - IDs/names of open loops this beat resolves.

- **`creates_loops: string[]` (optional, default `[]`)**
  - IDs/names of new loops this beat introduces.

### 1.2 Fields Set by the System, Not the LLM

The LLM **must not** attempt to set the following `PlotBeat` fields. They are
owned by the system:

- `id` – Assigned by the outline manager (`PB001`, `PB002`, …).
- `status` – Initialized to `"pending"`.
- `created_at` – Filled automatically in `PlotBeat.__post_init__`.
- `executed_in_scene` – Set when a beat is actually executed by a scene.
- `execution_notes` – Filled by QA or verification after execution.

The prompt should explicitly say: *"Do not include `id`, `status`, `created_at`,
`executed_in_scene`, or `execution_notes` in your JSON; the system will set
those fields."*

---

## 2. Mapping to `PlotBeat` and `PlotOutline`

Given a single beat object `b` from the LLM, the CLI-level parser will:

1. Assign a new PlotBeat ID (`PBxxx`) based on the existing outline.
2. Construct a `PlotBeat` instance:

   ```python
   PlotBeat(
       id=next_id,
       description=b["description"],
       characters_involved=b.get("characters_involved", []),
       location=b.get("location"),
       plot_threads=b.get("plot_threads", []),
       tension_target=b.get("tension_target"),
       prerequisites=b.get("prerequisites", []),
       status="pending",
       executed_in_scene=None,
       execution_notes="",
       advances_character_arcs=b.get("advances_character_arcs", []),
       resolves_loops=b.get("resolves_loops", []),
       creates_loops=b.get("creates_loops", []),
   )
   ```

3. Append these beats to the current `PlotOutline` using
   `PlotOutlineManager.add_beats` and revalidate with
   `PlotOutlineManager.validate_outline`.

The `PlotOutline` object continues to track outline-level metadata:

- `beats: List[PlotBeat]`
- `created_at`, `last_updated`
- `current_arc`, `arc_progress`

---

## 3. Transition Handling Between Beats

`PlotBeat` is intentionally **factual** and does not include prose transitions.
There are two levels of transition to consider:

1. **Scene-level transitions** (already present in planner/writer prompts).
2. **Beat-sequence transitions** (moving cleanly between more distant beats).

### 3.1 Scene-Level Transitions (Existing)

Phase 1 already added fields such as `transition_path` to the planner/writer
prompts. For each scene, the planner can specify, roughly:

- How we move from the previous location/time to the new one.
- What bridge paragraph(s) the writer should include.

When we introduce PlotBeats, the **scene writer** will still be responsible for
local transitions:

- Last executed scene → Next scene (executing a given beat).
- Using `transition_path` plus beat metadata (location, characters, etc.).

### 3.2 Beat-Sequence Transitions (Design Idea)

For sequences of beats that represent larger jumps (e.g. time skips, arc
boundaries), it may be useful to have an explicit **transition prompt** that
operates at the beat layer.

**Concept:**

- A separate CLI/agent helper (later phase) that, given:
  - The last executed beat (and its scene summary).
  - The next planned beat.
  - Recent tension history and open loops.
- Returns a short **transition description** or **bridge snippet** that
  explains how the story plausibly moves from the first beat to the second.

This could be implemented in several ways:

- **A. Transition description only**
  - Prompt returns 1–3 sentences of *factual* description, which are then fed
    into the writer context as extra guidance.
  - Example fields:

    ```json
    {
      "from_beat_id": "PB010",
      "to_beat_id": "PB011",
      "transition_summary": "Three days pass as the relay comes back under nominal load; Kyras and Belia avoid direct contact while the investigation spins up." 
    }
    ```

- **B. Transition prose snippet**
  - Prompt returns a short paragraph of actual prose meant to be used as a
    bridge between scenes.
  - Risk: entangles prose generation with plot generation; probably better as a
    later-phase experiment.

For now, the design bias is toward **A. transition description only**, so that
PlotBeats stay factual and prose remains the writer's responsibility.

### 3.3 Where Transitions Live in the Architecture

Short term (Phase 3 / CLI-only):

- `novel plot generate` only deals with **beats**, not transitions.
- Transitions are implicitly handled by the existing planner/writer
  `transition_path` logic on a per-scene basis.

Medium term (Phase 4–5, optional):

- Introduce an optional `transition.generate` helper:
  - Given `(last_beat, next_beat, recent_scenes, tension_history)`
  - Returns `transition_summary` as additional context.
- This summary can be injected into the planner/writer context when planning
  the scene that executes `next_beat`.

All of this should remain **configurable and optional**:

- Projects can use PlotBeats without any special transition prompt
  (relying on existing `transition_path`).
- Transition generation can be turned on via a future config flag if/when it
  proves valuable.

---

## 4. Open Questions / Future Extensions

- Should beats be allowed to specify explicit **time deltas** (e.g. `+3 days`)
  to help both transitions and pacing tools?
- Do we want to attach a simple `importance` field to beats
  (`low|medium|high|critical`) to help choose which beats to execute when
  we are behind schedule or need to compress the outline?
- How aggressively should we validate cross-beat dependencies (prerequisites)
  at generation time vs. at execution time?

These questions can be revisited in Phases 4–5 once the basic CLI-only
PlotBeat generation and inspection workflow is stable.

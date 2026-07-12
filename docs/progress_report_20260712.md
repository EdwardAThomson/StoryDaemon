# Progress Report: 12th July 2026 (Fable 5)

The triple validation run at d78cb9a: first live exercise of the
**write-until-concluded segment loop** (d78cb9a, truncation cannot ship), the
**thread registry** (Slice T1, merged at 3cddc73), and **thread identity by
selection** (Slice T1.5, merged at 7ef9779), plus the third measurement of
**beat claim precision** after the resolves-vs-advances reframe (baseline 3/13,
grantrate-run 6/12, un-gating bar 60-70 percent). One honesty note up front:
this arm carries three new subsystems versus grantrate-run, so single-metric
deltas against that arm are not clean A/Bs; the per-metric evidence below says
which subsystem owns which result.

Headline, in three parts. **The truncation invariant held everywhere:** 16 of
16 scenes committed with a detected ending, 13 concluded naturally in one
segment, 3 concluded on request via exactly one continuation each, zero trims,
zero segment-cap hits, and `scene_incomplete()` re-run over every committed
file confirms 0 of 16 incomplete (grantrate-run: 8 of 16 ended mid-sentence).
**Thread selection adopted completely and monotonously:** 14 of 14
batch-authored beats selected `TH000` from the roster (zero sanitizer clears,
zero invented ids, zero "new:" mints), which validates the machinery and
simultaneously answers the design question the hard way: nothing in a
single-protagonist premise ever pressures the model to mint a second strand.
**Claim precision cleared the bar:** 9 beat claims judged, 7 honest (77.8
percent), both refusals genuine edge cases with defensible scene-grounded
reasons, and the truncation-caused refusal species is extinct.
**Recommendation: un-gate `loop_resolved`, with the finale beat exempt**
(section 4). The run also delivered the sharpest discrimination specimen yet
(OL19: the scene delivered the opposite of the beat's planned outcome and the
judge graded the page) and two first-class defect findings with numbers: the
api backend's inert `llm.timeout` (one 22.4-minute stall, root-caused to the
line), and beat-level duplication escalating to 9,200 characters of verbatim
prose across scenes 6/7.

## 1. Methodology

Fresh project `work/novels/triple-run_ec75ee96/`, executed at d78cb9a (local,
unpushed; this run validates those commits before they publish). Foundation
and user goal copied verbatim from the grantrate/slice0/run-5 lineage
(corporate thriller, junior-analyst-discovers-heist, "Expose the corporate
data heist before the merger closes and the evidence is buried"). Config diff
against grantrate-run's config.yaml is exactly one line: `writer_max_tokens:
3000` is gone, because d78cb9a removed the flat ceiling from the project
template; word-target sizing governs instead. Everything else default, and the
defaults are the measurement: `loop_closure`, `thread_identity`,
`sacred_finale` all default True. Backend api / model openrouter
(`OPENROUTER_MODEL=anthropic/claude-haiku-4.5`), timeout 120 (see section 8.1
for what that setting actually does), plot-first, contracts, rolling horizon,
`target_story_length: 15`.

16 scenes (ticks 0-15), 28,574 words, executed in five gated chunks (0-2 with
`--save-prompts`, 3-5, 6-9, 10-12, 13-15) with a stop-and-report digest after
each. Zero manual interventions, zero tick retries consumed, `errors/` empty
all run. Pre-flight: the 82 unit tests covering the three new subsystems all
pass at d78cb9a.

## 2. Verdict 1: the truncation invariant (segment loop, first live outing)

| quantity | value |
|---|---|
| scenes committed | 16 |
| concluded naturally (1 segment) | 13 |
| concluded on request (2 segments) | 3 (ticks 4, 5, 6) |
| reached segment 3 (cap) | 0 |
| trimmed | 0 |
| `scene_truncated` in metrics | 0 of 16 |
| `scene_incomplete()` re-run over committed files | 0 of 16 incomplete |
| mid-sentence endings (manual check per gate) | 0 |

**PASS against the pre-registered bar** (zero trims, zero mid-sentence
endings). The three continuations are the machinery working, not straining:
each fired once, carried the full scene so far, and the model concluded within
the continuation ask every time. Every plan carried `scene_length: None`, so
the default "long" (1400 words) governed throughout.

Word tracking against the stated target: first renders opened within 8 percent
of target (1292/1307/1413 at ticks 0-2), drifted to +40-67 percent mid-run
(1920-2340 at ticks 6-10, including the three continuation scenes at
1849/2113/2340), then fell back toward target (1490-1895, ticks 11-15).
Overshoot is context pressure, not loop mechanics: single-segment scenes 7-10
overshot as much as the continuation scenes. A pacing observation, not an
invariant issue; nothing brushed a ceiling (the "length" finish_reason never
fired after tick 6).

Direct comparison: grantrate-run's 8-of-16 mid-sentence truncations, its OL37
judged-closure casualty, and run 5's missing end marker were all
ceiling-caused. This run had zero truncation casualties of any kind.

## 3. Verdict 2: thread identity adoption (T1.5, first live outing)

The beat-generation prompt rendered all three T1.5 surfaces correctly
(inspected offline between ticks 1 and 2, byte-identical to what the tick-2
batch saw): the `"thread_id": "TH000"` line inside the authoritative JSON
shape block, the roster section with the implicit-main entry (`TH000: main
(implicit main) | members: none yet | scenes: 2 | last active: tick 1 |
tension: 7`), and the selection rule with the "new:" minting escape.

| batch | authored at tick | beats | thread_id authored | sanitizer outcome |
|---|---|---|---|---|
| 1 | 2 | PB001-PB005 | `TH000` x5 | all exact match, kept |
| 2 | 6 (populated roster) | PB006-PB010 | `TH000` x5 | all exact match, kept |
| 3 | 11 (slot-aligned, capped to 4) | PB011-PB014 | `TH000` x4 | all exact match, kept |

Adoption 14 of 14, zero clears, zero invented TH ids, zero "new:" usages,
zero cast-disjoint warnings. `thread_selection_source` per tick: `main` at
ticks 0-1 (pre-beat), `selected` at ticks 2-14 (13 consecutive),
`label_fallback` at tick 15 (see below). Final registry state
(`memory/threads.json`): 2 threads.

- `TH000` "main" (implicit): 15 scenes, members C000-C004+C013 (the whole
  cast), sources {main: 2, selected: 13}, run length 15 at tick 14.
- `TH001` "evidence exposure": 1 scene (S015), sources {label_fallback: 1},
  minted AT THE FINALE because the sacred finale's authored beat (PB015)
  carries no `thread_id` (the finale authoring prompt is not the
  beat-generation prompt and has no roster), so attribution fell through to
  the T1 label path and minted a thread from PB015's label. A T1.5 gap worth
  one line of code someday (stamp the finale beat with the active thread id or
  let attribution prefer the implicit thread at the finale), cosmetic today.

Two findings ride on the clean adoption. First, **labels went vestigial under
selection**: batch 1 authored episode-title labels (investigation, cover-up,
trust); batches 2-3 authored `plot_threads: ["main"]` on 8 of 9 beats,
echoing the roster entry's name. The T1 backfill conclusion (labels are
per-beat color, not identity) is now confirmed prospectively. Second, and the
real result of the selection test: **all-main-forever**. With a roster
containing only "main" and a premise with one protagonist and one
investigation, the model never has a reason to mint. Selection works; nothing
exercises the portfolio. The interleaving design's next step (a selection
policy, or construction pressure that seeds genuine secondary strands, for
example from faction or antagonist POV) now has its baseline: emergent
single-POV stories do not diversify on their own, exactly as the design's
riskiest open question feared.

## 4. Verdict 3: grant rate, and the un-gating recommendation

Every beat claim carried by an executed beat, in order (a claim counts as
honest when the judge confirmed the loop resolved in the claimed scene,
through either judge path, the grantrate methodology):

| tick | beat | claimed loop | verdict |
|---|---|---|---|
| 3 | PB002 (alert-system reveal) | OL4 how did Orul detect her so fast | **YES** (beat judge) |
| 4 | PB003 (Brixoth orders the scrub) | OL6 will the logs be scrubbed, whose authority | **YES** (beat judge) |
| 5 | PB004 (races to extract metadata) | OL3 can she retrieve evidence before the scrub | **YES** (same-scene extractor grant; beat claim preempted) |
| 8 | PB007 (Brixoth learns of the backup access) | OL20 did Brixoth discover it | **YES** (same-scene extractor grant) |
| 12 | PB011 (drive retrieval attempt) | OL19 will the hidden drive remain undiscovered | **YES** (beat judge) |
| 13 | PB012 (scrub protocol incomplete) | OL37 will the protocol succeed before authorities | no: "the actual outcome of whether the protocol will successfully scrub evidence before authorities access it remains uncertain and unresolved" |
| 14 | PB013 (Oror's evidence reaches the DPA) | OL9 true scope of the export scheme | no: "initiates an investigation but does not reveal the true scope of the data export scheme" |
| 14 | PB013 | OL18 will Oror betray Brixoth by escalating | **YES** (same-scene extractor grant) |
| 14 | PB013 | OL33 will Oror's documentation trigger an investigation | **YES** (beat judge) |

Totals: **9 claims, 7 honest (77.8 percent)**; through the beat-judge path
alone 4 of 6 (67 percent; 3 grants were extractor-preempted same-scene).
Baseline 3/13 (23 percent), grantrate-run 6/12 (50 percent). 0 parse failures,
0 sanitizer strips, 0 truncation-caused refusals (grantrate had 1 certain, 3
plausible). Both refusals are the designed skepticism, verbatim above, and
both loops were in fact still open on the page.

The discrimination specimen of the run, worth quoting anywhere the judge needs
defending: **OL19**. PB011's authored description said Darol retrieves the
hidden drive before the surveillance team intercepts her. The scene delivered
the opposite: Brixoth's team takes the drive while she stands down. The judge
granted the claim anyway, because the question ("will the drive remain
undiscovered / be recovered") was answered on the page, in the negative:
"The scene conclusively answers when and how the drive will be recovered:
Brixoth's security team retrieves it from the maintenance panel while Darol is
forced to stand down, settling the question of its discovery and recovery."
The judge grades the page, not the plan. Answered-in-the-negative is answered.

**The finale over-claim species was structurally sidestepped, not measured.**
The planner did author a 7-claim finale beat (PB014: resolves OL0, OL2, OL16,
OL25, OL28, OL31, OL32, advances nothing, the exact over-claim shape that
depressed grantrate's rate), but the sacred finale's LLM screen rejected it as
a non-denouement (it is an active courtroom event) and the chain authored
PB015 instead, which claims nothing. So the finale contributed zero claims to
the measurement, and 7/9 is a genuinely non-finale number. Two consequences:
(1) the sacred-finale authored path already produces claim-free finale beats,
which is half the finale exemption for free; (2) a pending finale beat that
PASSES the screen would still carry its over-claims into `loop_resolved`.

**Recommendation: un-gate `loop_resolved`, exempting the finale beat.** The
pre-registered bar was 60-70 percent with refusals as genuine edge cases; this
run measures 77.8 percent overall, 67 percent through the beat judge alone,
and both refusals are edge cases, not a systematic species. Cost accounting,
honestly: had the contract been live this run, the two refusals would have
been contract failures at ticks 13 and 14, each firing the rolling horizon in
the endgame (the horizon's one live firing to date recovered cleanly, so this
is churn, not breakage, but it is why the finale exemption matters: PB014's 7
claims would have been 4-5 more failures if a screen-passing finale beat ever
carries them). Exempt beats executed via the sacred-finale path (or any beat
in the final slot) from `loop_resolved`, un-gate for everything else, and let
the next run measure the horizon-churn rate at live precision.

**Extractor claims facing the judge, at scale for the first time:** 11 judged,
9 granted, 2 refused across the run. The finale is the story: the extractor
claimed **45 loop resolutions in one tick** (82 percent of the open ledger,
the same mass-sweep instinct that closed 47 unaudited in the slice0 run). The
judged cap took the first 5, granted 3 (OL0, OL5, OL7, real audit trails, for
example OL0: "Brixoth Zexirn, Executive Director of Data Operations,
authorized the unauthorized data exports and evidence destruction, with the
DPA investigation conclusively documenting his culpability"), refused 2 with
specific reasons (OL1: the scene is in her own office, not Brixoth's office as
the question specifies; OL2: the merger-scheme half was never addressed), and
ignored the other 40, which then **expired honestly** (status `expired`, "left
open at story end"). The side door stayed closed under maximal pressure:
grantrate proved the sweep gone on a 3-claim finale, this run proves it gone
on a 45-claim one.

## 5. The ending and the sacred path

Second consecutive live outing for the authored fallback, chain step (b). The
pending final-slot beat PB014 satisfied the tension precheck (target 4.0) but
failed the denouement screen and was superseded (outline note: "Superseded by
the sacred finale at tick 15; left pending"). Screening out "Six months later,
Darol testifies at the regulatory hearing as the merger is dissolved and
criminal charges are filed" is defensible (testimony at a live hearing is an
event, not aftermath) but stricter than obviously necessary, and the screen's
negative reason is not printed or persisted anywhere, an observability gap
symmetric to the judge-refusal one fixed last iteration (section 8.4).

The authored replacement, PB015: "Weeks later, Darol reviews the regulatory
findings at her workstation, vindicated but forever changed." Ask source
`authored`, `finale_retries_used: 0` (second arm in a row needing no re-roll),
single render scored **3 against target 4.0 and cap 5**, calm band, 3
extracted hook loops suppressed before application, contract verified (1
postcondition, score 0.51), 42 still-open loops expired with honest statuses,
`dangling_threads: 42` (35 critical, 7 high).

The scene stays settled to the last line: regulatory findings on the terminal,
a private accounting, packing up, departure. Closing lines, verbatim: "Darol
gathered her personal items from the desk and prepared to leave the Port
Yorhold facility for the last time. Behind her, the regulatory findings
remained on the terminal screen, sixty-eight pages of documentation that
proved she'd been right about everything. Everything except what it would
cost." **No explicit END marker this time** (slice0-run2's END OF NOVEL was
incidental; grantrate's absence was truncation-caused; here the scene is
complete and settled, the writer simply did not emit one and the settled
ending instruction does not ask for one). If the marker is wanted as a
guarantee, it belongs in the finale writer instruction, not in hope. The
segment loop's contribution is what it promised: the ending is detected and
complete, `concluded_naturally: true`, no trim.

Goal outcome: succeeds on the page (investigation vindicated, Brixoth's
culpability documented, merger consequences underway). The lineage now reads:
run 5 settled failure, slice0-run2 settled success, grantrate settled success,
this run settled success at a personal cost. Goal relevance 7-9 throughout, 9
at the finale.

## 6. Per-tick trace and regression

| tick | target | actual | phase | beat | seg | cc | opened/ded/cap | closed | open total |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 3.0 | (not scored) | rising | (first tick) | 1 | | 4/-/1* | | 4 |
| 1 | 3.5 | 7 | rising | | 1 | | 4/0/0 | | 8 |
| 2 | 4.1 | 7 | rising | PB001 ok (batch 1) | 1 | 3/0 | 3/0/0 | | 11 |
| 3 | 4.6 | 7 | rising | PB002 ok | 1 | 2/0 | 4/0/0 | **1** (beat) | 14 |
| 4 | 5.1 | 8 | rising | PB003 ok | 2 | 2/0 | 4/0/1 | **1** (beat) | 17 |
| 5 | 5.3 | 7 | rising | PB004 ok | 2 | 2/0 | 4/0/1 | **1** (extr) | 20 |
| 6 | 5.6 | 7 | rising | PB005 ok (batch 2) | 2 | 3/0 | 4/0/1 | | 24 |
| 7 | 5.9 | 7 | rising | PB006 ok (duplicate beat, section 8.2) | 1 | 3/0 | 2/2/2 | | 26 |
| 8 | 6.3 | 7 | rising | PB007 ok | 1 | 2/0 | 4/0/1 | **1** (extr) | 29 |
| 9 | 6.8 | 7 | rising | PB008 ok | 1 | 2/0 | 4/0/0 | | 33 |
| 10 | 7.3 | 8 | rising | PB009 ok | 1 | 3/0 | 4/0/1 | | 37 |
| 11 | 7.9 | 7 | rising | PB010 ok (batch 3, capped to 4) | 1 | 2/0 | 3/1/1 | **3** (extr) | 37 |
| 12 | 8.3 | 8 | rising | PB011 ok | 1 | 2/0 | 4/0/1 | **1** (beat) | 40 |
| 13 | 8.8 | 7 | peak | PB012 ok; OL37 refused | 1 | 2/0 | 3/0/0 | 0 of 1 | 43 |
| 14 | 7.3 | 6 | resolution | PB013 ok; OL9 refused | 1 | 2/0 | 4/0/0 | **2** (beat+extr) | 45 |
| 15 | 4.0 | 3 | resolution | PB015 ok (sacred finale, authored) | 1 | 1/0 | 0 opened, 3 suppressed | **3** (extr) + 42 expired | 0 |

*tick 0's cap drop is log-only; `loops_capped` is null on the first-tick path
(known cosmetic gap, still unfixed).

Contract totals: 31 conditions checked, 0 failed, no horizon firing, no wedge.
Two live firsts in the beat pipeline: **slot alignment fired** ("Capping batch
to 4 beat(s): story ends at tick 15", landing the denouement beat exactly at
slot 15 with tension_target 4.0), and the **contract tension-floor clamp
fired** (PB011/PB012 authored `tension_at_least: 8`, clamped to 7 as
unsatisfiable). Also a first: the extractor judged cap (5 per tick) was
actually reached, at the finale.

Nine-arm comparison (grantrate's table plus this run):

| metric | run 5 | grantrate-run | this run |
|---|---|---|---|
| overall drift, scored ticks | 1.39 | **1.23** | 1.52 (mid-band; historical band 1.20-1.73) |
| overall bias (signed) | +0.81 | **+0.61** | +0.81 |
| rising drift (1-12) | 1.56 | | 1.56 |
| peak drift (tick 13) | 1.8 (7 vs 8.8) | 1.8 | 1.8, now 9 of 9 arms |
| resolution drift (14-15) | **0.15** | **0.15** | 1.15 |
| final scene vs target 4.0 | **4** (exact) | **4** (exact, 1 re-roll) | 3 (undershoot 1, 0 re-rolls) |
| final-scene content | denouement | denouement (truncated on paper) | denouement, complete on paper |
| ending regression bar (at or under 5, settled) | pass | pass | **pass** |
| manual interventions | 0 | 0 | 0 |

**Regression check: passed.** Ending at 3 (calm, settled, complete), inside
the cap, no re-roll needed. Drift mid-band; resolution drift (1.15) is worse
than the two exact-hit arms because tick 14 undershot (6 vs 7.3) and the
finale undershot by 1, the same soft-landing direction as slice0-run2, still
far from the pre-arc-phase-mandate failure mode (inability to come DOWN).

## 7. Ledger accounting

| quantity | this run | grantrate-run | slice0-run2 | run 5 |
|---|---|---|---|---|
| loops opened (applied) | 55 | 55 | 50 | 78 |
| capped at creation | 10 (9 in metrics + 1 tick-0 log-only) | 9 | 16 | (no cap) |
| deduped at creation | 3 | 2 | 1 | (no dedup) |
| suppressed at finale | 3 | 4 | 5 | 8 |
| judged closures (beat + extractor) | **13** (4 + 9) | 9 (3 + 6) | 3 (3 + 0) | (feature off) |
| unaudited extractor closures | 0 | 0 | 47 (the sweep) | 4 |
| extractor claims judged/granted/refused | 11 / 9 / 2 | 8 / 6 / 2 | | |
| extractor claims ignored over cap | 40 (one finale tick) | 0 | | |
| expired at story end | 42 (35 critical, 7 high) | 46 | 0 (swept) | 0 (left open) |
| open at tick 14 | 45 | 49 | 47 | 77 |
| open at end | 0 (honest statuses) | 0 (honest) | 0 (sweep-dominated) | 74 |

## 8. Findings (the run's fix candidates, each with its evidence)

**8.1 `llm.timeout` is inert on the api backend.** Tick 5 stalled for 22.4
minutes (inter-scene gaps otherwise 67-229 seconds all run) with the process
network-blocked, then recovered by itself: zero tick retries consumed, run
exit 0. Root cause is in the code, not guessed:
`MultiProviderInterface.generate()` accepts `timeout` and does not use it (the
comment at `tools/multi_provider_llm.py:558` says so explicitly), and every
provider client, including the OpenRouter one, is constructed without a
timeout, so the OpenAI SDK defaults govern (600 seconds per attempt, 2
internal retries: worst case ~30 minutes per call). The config's `timeout:
120` has never done anything on this backend, in any arm; prior runs simply
never drew a hung connection. Fix candidate: construct the clients with
`timeout=llm.timeout` (and consider `max_retries` explicit) so the knob means
what every config in `work/` believes it means.

**8.2 Beat-level duplication is now a page defect, not a cosmetic note.** The
tick-6 batch authored PB006 as a near-duplicate of the still-pending PB005
("Zelox confronts Darol about her investigation...", same cast, same
confrontation), the exact species grantrate flagged as watch-item. This run
shows what it costs: scene 7 shares **~9,200 characters of verbatim text with
scene 6** (SequenceMatcher ratio 0.668 against a 0.017-0.051 baseline for
every other adjacent pair; five verbatim blocks up to 3,142 characters,
including an identical closing passage). Downstream, the duplicated prose
minted duplicated loops: OL23 (S006) and OL27 (S007) are the same legal-firm
question. Beat-level dedup does not exist (loop dedup cannot see beats); the
generation prompt does carry recent beats, so the cheap first step is a
dedup/similarity check on freshly authored beats against pending ones, the
same sanitize-not-trust slot the other beat sanitizers occupy. The story
self-recovered at tick 8 (ratio 0.020), so this is quality pressure, not a
stability risk.

**8.3 The dedup threshold has a measured blind spot at ~0.78-0.79.** OL23 vs
OL27 measure 0.788, under the 0.8 threshold by 0.012, and slice0-run2's
OL29/OL33 measured 0.784. Two specimens of the same just-under species in two
runs, both semantically identical questions, both double-created (this run's
pair was then double-closed by the same event at tick 11, pure noise).
Recommendation: lower `dedup threshold` to 0.75 now (distinct strands sit far
lower, per the same difflib-behavior rationale the thread matcher documents),
and keep semantic dedup on the roadmap for the paraphrase species character
matching can never see (slice0's OL23/OL32 pair at 0.341).

**8.4 Observability gaps, one new, two known.** New: a finale screen "no" is
silent; PB014 was superseded without its reason being printed or persisted
(the screen returns one, `_ask_finale_beat` only prints it on "yes"). Print
and stamp it into the superseded beat's execution notes, exactly like the
judge-refusal fix last iteration. Known, still open: `loops_capped` is null on
the first-tick path (tick 0 dropped a loop, invisible in metrics); the
character detector's noise hit its worst case yet at the finale (17 junk
"characters" including "Compliance Violations" and "Witness Vindication",
skipped gracefully as always).

**8.5 The sacred finale's authored beat bypasses thread selection** (section
3): PB015 carried no thread_id, attribution fell to label_fallback, and TH001
was minted at the story's last tick. Harmless today; wrong the day a selection
policy reads the registry.

## 9. Stability, silent-issue audit

- 16 of 16 ticks completed first try, 0 of 2 run-level retries used in any
  chunk, `errors/` empty all run. OpenRouter: no 5xx, no 429, one hung
  connection (section 8.1). Inter-scene gaps 67-229s (mean 81s excluding the
  hang and chunk boundaries).
- Beat pipeline: 3 batches + 1 authored finale beat, all parsed first try, no
  beat ever failed (14 of 14 executed beats completed, all via the trusted
  contract path, scores 0.32-0.66). No wedge at any point.
- Zero fact-extraction failures (slice0 had 2, grantrate 0). Zero judge parse
  failures across 20 judge calls (9 beat-claim + 11 extractor-claim).
- Tension rewrites: attempted at ticks 2, 3, 4 (all "revision not closer,
  original kept"), transition guard fired correctly at tick 1 ("drop too big
  for a prose rewrite"), nothing needed after tick 4.
- advances_loops adoption held: 13 of 14 batch beats carried real advances
  lists; the only resolves-heavy beat was the superseded finale PB014, the
  known over-claim shape.
- Metrics semantics held: null vs 0 distinction correct everywhere observed;
  `loops_expired`/`dangling_threads` populated exactly once, at the finale.

## 10. Verdict

All three subsystems validated on their first (or first-at-scale) live
outing. The segment loop delivered a 16-for-16 clean-ending run and killed the
truncation defect class that cost grantrate a grant and run 5 its end marker;
the invariant surviving 3 continuations without ever reaching the cap says the
budget coordination (targets sized to ceilings) is doing the real work, with
the loop as insurance. Thread selection adopted 14-for-14 with zero sanitizer
interventions and produced the design's answer: single-premise stories never
mint, so the interleaving work's next slice must create the portfolio it wants
to select over. Claim precision cleared the un-gating bar at 77.8 percent with
genuinely edge-case refusals: **un-gate `loop_resolved` with the finale
exempt**, and while at it flip nothing else; the judged cap plus expiry
handled a 45-claim finale sweep exactly as designed. The fix queue, in value
order: api-backend client timeouts (8.1), beat dedup at authoring (8.2), dedup
threshold to 0.75 (8.3), finale-screen reason persistence and the finale
thread stamp (8.4, 8.5).

## Artifacts

- Scored run (gitignored `work/`): `work/novels/triple-run_ec75ee96/` (16
  scenes, 28,574 words; `memory/metrics.jsonl` with the segment and thread
  fields live; `memory/threads.json` with the 2-thread registry;
  `plot_outline.json` with PB014's supersession note and the claim-free
  authored PB015; `memory/open_loops.json` holding all 55 dispositions: 13
  judged `resolution_summary` audit trails, 42 honest expiries).
- Run logs: scratchpad copies (`triple-t0.log`, `triple-t1.log`,
  `triple-t2.log`, `triple-t3-5.log`, `triple-t6-9.log`, `triple-t10-12.log`,
  `triple-t13-15.log`), not committed. The rendered beat-generation prompt as
  inspected: `beat-prompt-pre-tick2.txt` (scratchpad).
- Executed at d78cb9a (local, unpushed), config diff vs grantrate-run exactly
  one removed line (`writer_max_tokens: 3000`); no code changes during the
  run, no commits, no manual interventions.

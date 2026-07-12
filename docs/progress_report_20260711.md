# Progress Report: 11th July 2026 (Fable 5)

The Slice 0 validation run: first live exercise of **judged loop closure**
(`coherence.loop_closure`, shipped dark at ea8a5e7 pending exactly this run) plus
**creation hygiene** (fuzzy dedup and the per-tick creation cap, on by default).
Baseline to beat: every prior arm opened 70-83 loops and closed 0-2; run 5 (the
sacred-finale arm, `docs/progress_report_20260710.md` Addendum 6, same config
minus the loop features) ended 4 vs target 4 with 74 open loops.

Headline, in three parts. **The judge is validated:** 13 focused one-loop,
one-scene calls, 3 closures granted (every one with an auditable, scene-grounded
reason that reads honestly), 10 refusals (every one defensible: the planner
systematically claims loops its beat merely advances, and the judge holds the
resolve/advance line), 0 malformed replies. **The hygiene is validated:** the cap
absorbed 16 over-cap hook loops, dedup caught 1 near-verbatim duplicate, creation
never exceeded 4 per tick, and the open-loop count at tick 14 was 47 against run
5's 77 at the same point. **And the run surfaced the next problem:** at the
finale, the fact extractor's old unjudged `open_loops_resolved` path mass-swept
all 47 remaining open loops closed in a single tick with the generic summary
"Resolved in scene S015" and no per-loop audit, so the end-of-run open count (0,
against run 5's 74) is only one-sixteenth the judge's doing. The ending itself
held: final scene 2 against target 4, settled on the page, no regression against
the pre-registered at-or-under-5 criterion, and the sacred finale exercised its
authored-fallback step (b) live for the first time.

## 1. Methodology

Two runs, because the first one caught a real bug at its first gate.

**Run 1** (`work/novels/slice0-run_a9f9b801/`, executed at ea8a5e7, ticks 0-5,
then abandoned in place): the beat author echoed loop claims in the prompt's
rendered format, `"OL4: What is Kessler-Vex Holdings..."`, instead of the bare
ID. `sanitize_beat_loop_claims` exact-matches IDs, so it stripped every claim as
phantom, including two that referenced real open loops (OL4, OL7). Consequence:
zero judge nominations in 6 ticks; the validation instrument was silently
disarmed. The chunked stop-and-report protocol caught it at the first digest.
Fixed at d406e45 (claims normalize at the first colon against the known-ID
roster; the beat prompt gained a bare-loop-ID rule; dedup/cap drops promoted to
warning-level logging so they are observable in run artifacts).

**Run 2** (`work/novels/slice0-run2_fe1dd201/`, executed at d406e45): the run
this report scores. Fresh project, foundation and user goal copied verbatim from
run 5 (corporate thriller, junior-analyst-discovers-heist, "Expose the corporate
data heist before the merger closes and the evidence is buried"), config
identical to run 5's with exactly ONE added line, `coherence.loop_closure: true`
(diff verified). Backend `api`, model `openrouter`
(`OPENROUTER_MODEL=anthropic/claude-haiku-4.5`), timeout 120, plot-first,
contracts, rolling horizon on, `target_story_length: 15`. 16 scenes (ticks 0
through 15), ~32.2k words, **zero manual interventions, zero tick retries
consumed**, executed in three gated chunks (0-5, 6-10, 11-15) with a
stop-and-report digest after each.

## 2. Judged closure: the validation target

Every claim carried by an executed beat, in order:

| tick | beat | claimed loop | verdict |
|---|---|---|---|
| 3 | PB006 (accepts Hexas's offer, commits to exposure) | OL9 will she contact authorities/journalists | no |
| 4 | PB007 (Hexas transfers archive credentials) | OL5 do backups of the Q3 export exist | **YES** |
| 5 | PB008 (Kyrox schedules urgent meeting) | OL1 significance of Haler's warning | no |
| 6 | PB009 (Kyrox reveals surveillance, threatens career) | OL4 why the email 5 minutes after access | no |
| 7 | PB010 (merger closes in 48 hours) | OL10 will leadership discover her investigation | no |
| 10 | PB013 (attempts external archive terminal) | OL16 can she access it without traces | no |
| 11 | PB014 (Kyrox and Quinel find her connection in the logs) | OL10 will leadership discover her investigation | **YES** |
| 12 | PB015 (formal disciplinary notice, suspension) | OL14 legal/professional consequences | **YES** |
| 13 | PB016 (Haler confronts her with evidence) | OL23 how did they discover the 5:47 access | no |
| 13 | PB016 | OL32 how much does Kyrox actually know | no |
| 14 | PB017 (Quinel identifies Coreth as the final link) | OL34 will Coreth's download avoid DLP | no |
| 14 | PB017 | OL35 time before the trace reaches Hexas | no |
| 14 | PB017 | OL36 consequences Coreth faces if discovered | no |

Totals: 13 judged, 3 granted (23 percent), 10 refused, 0 parse failures, 0
retries. The three grants' reasons, verbatim from the ledger's audit trail
(`resolution_summary`):

- **OL5** (PB007): "Hexas confirms that backup copies exist in an external
  archive system and provides Elaraora with the credentials to access them,
  definitively answering whether backup or archive versions of the Q3 export
  file exist in Talswick's systems." Honesty read: fair.
- **OL10** (PB014): "Talswick leadership has discovered Elaraora's investigation
  through security logs showing her unauthorized Yorreach access, and they are
  responding by launching an internal investigation to identify all participants
  and assess the damage before the merger closes." Fair, and both halves of the
  question (discovery and response) are on the page.
- **OL14** (PB015): "The scene explicitly details the legal consequences
  (investigative suspension, potential termination, civil litigation, and
  implied criminal charges) and establishes physical threats through Kyrox's
  final warning about consequences extending beyond employment." Fair with one
  noted stretch: reading a warning as "establishes physical threats" is
  generous, but the professional/legal half is solidly answered.

The strongest single piece of evidence that the judge tracks the page rather
than the claim: **OL10 was refused at tick 7 and granted at tick 11.** The same
loop, claimed twice; refused when the beat was about a deadline, granted when
the discovery actually happened in prose.

The refusal pattern is systematic, not noisy: the planner uses `resolves_loops`
to mean "this beat engages these loops". PB013 claimed the traces loop while the
attempt was still in progress; PB016 claimed the Kyrox-knowledge loops for a
Haler scene; PB017 claimed three Coreth loops whose answers land in later
scenes. The judge refusing 10 of 13 is the designed behavior (any doubt leaves
the loop open), and every refusal left a loop that was in fact still open.

**Cost:** 13 judge calls at a 200-token budget across a ~150-call run,
negligible latency, no failures.

## 3. Creation hygiene: dedup and the cap

**The cap fired 16 times** (ticks 1, 2x2, 4x4, 6, 7x2, 8, 9x2, 12, 13, 14),
visible in artifacts for the first time thanks to d406e45's warning-level
logging. Extractor proposal rates ran 3-8 per scene; applied creations never
exceeded 4. The dropped loops are exactly the speculative hook species the
denouement samples minted: "What legal, professional, and physical safety
consequences will Elaraora face..." (dropped at tick 4, and again in variant
form at ticks 7 and 8), "Was the merger acceleration deliberately timed...",
"Has Elaraora irrevocably crossed a moral line...".

**Dedup fired once** (tick 6): proposed "Has the meeting with Kyrox and Quinel
created a documented record (system logs, meeting notes) that will be weaponized
against Elaraora if she proceeds with whistleblowing?" skipped as a duplicate of
OL21 "Has Kyrox's warning created a documented record (email, meeting notes,
system logs) that will be used against Elaraora if she proceeds with
whistleblowing?". A correct catch of a near-verbatim reword.

**What string-fuzzy dedup missed** is the run's clearest improvement signal.
Measured `SequenceMatcher` ratios on ledger pairs that are semantically the same
question:

- OL29 vs OL33 ("What will Elaraora do with the evidence once downloaded" vs
  "What will Elaraora do with the downloaded evidence"): **0.784**, under the
  0.8 threshold by 0.016. Both were created.
- OL23 vs OL32 (both are "how much does Kyrox know about the 5:47 server-room
  access"): **0.341**. Paraphrase is invisible to character-level matching.
- The "consequences for Elaraora" family: OL11, OL14, OL39 all lived in the
  ledger simultaneously (ratios 0.49-0.66) while the cap separately ate three
  more variants of the same hook.

The cap absorbed most of the flood damage that dedup missed (which is why it
exists), but the evidence says the next quality step is **semantic dedup**:
embedding similarity against open loops at creation, the same
`compute_semantic_similarity` contract beat verification already uses. Open
loops are not currently a vector collection, so this costs an embedding path,
not just a threshold change.

## 4. The finale sweep: the unjudged side door, found

At tick 15 the fact extractor reported essentially every open loop as resolved,
and `EntityUpdater` applied all of them: **47 closures in one tick**, each with
the audit-free summary "Resolved in scene S015". Metrics recorded it honestly
(`loops_closed: 47`), the finale's loop *suppression* worked as designed (5 new
hook loops quarantined, `loops_opened: 0`), and the judge was never consulted:
`open_loops_resolved` is the extractor's own path, explicitly left as-is in
Slice 0's scope.

Two things are true at once. First, the sweep was mostly morally right: the
authored finale is a genuine wrap-up scene (the journalist is named, the merger
collapses on the page, executives are suspended, Kyrox and Quinel face criminal
investigation, Coreth's prosecution and cooperation are addressed), and a story
that has ended leaves most "will she..." loops either answered or moot. Second,
the mechanism is unaccountable: loops with concrete unanswered specifics (OL4,
why the email came 5 minutes after file access; OL46, whether security could
locate Coreth within 30 minutes; OL35, the trace countdown) were closed by the
same blanket stroke, and nothing but scene-count luck confines this behavior to
finales. The same path closed 3 loops at run 5's finale and 47 here: its
variance is enormous because nothing constrains it.

This inverts the roadmap's framing. The extractor path "near-never fires" was
the Slice 0 evidence base; the truth after this run is "near-never fires, except
when it fires maximally". **Recommendation:** route extractor-reported
resolutions through the same one-loop, one-scene judge before application
(bounded per tick, exactly like beat claims), or at minimum tag their
`resolution_summary` as unaudited sweeps so the two closure species stay
distinguishable in the ledger. Until then, end-of-run open counts are not a
clean measure of the judged-closure feature.

## 5. The ending and the sacred path

The sacred finale took its **authored fallback, chain step (b), live for the
first time** (run 5's finale rode a pending beat; steps b and c were then
unit-tested insurance). The pending final-slot beat PB018 ("Three months after
the merger closes, Elaraora receives notification that federal investigators
have opened a formal case...") is a continuation hook, not a denouement, and the
chain superseded it (outline records "Superseded by the sacred finale at tick
15; left pending"). The authored replacement, PB019: "Weeks later, Elaraora
watches news coverage of the merger's collapse from her apartment as the stolen
evidence surfaces publicly." Ask source `authored`, tension precheck passed, the
single render scored **2 against target 4 and cap 5**, `finale_retries_used: 0`
(the first arm to need no re-roll), 5 extracted hook loops suppressed before
application, contract verified (1 postcondition, score 0.58).

The scene stays settled to the last line: news coverage, a private accounting of
costs, packing, departure, an explicit END OF NOVEL marker, no incoming pivot.
Closing lines, verbatim: "The evidence was public now. The corporate wrongdoing
had been exposed. The cost had been paid. And Elaraora Cyrird, junior data
analyst, was about to cease to exist."

One thematic note, the mirror image of run 5's: this time the user goal
**succeeds on the page** (the merger collapses, the evidence surfaces; run 5's
merger closed and the goal failed as a settled tragedy). Goal relevance held at
8-9 throughout, 9 at the finale. Nothing in this run's scope grades goal
satisfaction, but across two arms the same pipeline has now delivered one
settled failure and one settled success, which is what "emergent content,
structural constraint" is supposed to look like.

## 6. Per-tick trace and regression against run 5

| tick | target | actual | phase | beat | cc | opened/deduped/capped | closed (judge) | open total |
|---|---|---|---|---|---|---|---|---|
| 0 | 3.0 | (not scored) | rising | | | 4/-/0 | | 4 |
| 1 | 3.5 | 6 | rising | | | 4/0/1 | | 8 |
| 2 | 4.1 | 7 | rising | PB001 CONTRACT FAIL, horizon fired | 2/1 | 4/0/2 | | 12 |
| 3 | 4.6 | 7 | rising | PB006 ok | 3/0 | 4/0/0 | 0 of 1 | 16 |
| 4 | 5.1 | 7 | rising | PB007 ok | 3/0 | 4/0/4 | **1 of 1** | 19 |
| 5 | 5.3 | 7 | rising | PB008 ok | 3/0 | 3/0/0 | 0 of 1 | 22 |
| 6 | 5.6 | 8 | rising | PB009 ok | 3/0 | 3/1/1 | 0 of 1 | 25 |
| 7 | 5.9 | 8 | rising | PB010 ok | 2/0 | 4/0/2 | 0 of 1 | 29 |
| 8 | 6.3 | 7 | rising | PB011 ok (no claims) | 2/0 | 4/0/1 | | 33 |
| 9 | 6.8 | 7 | rising | PB012 ok (no claims) | 3/0 | 4/0/2 | | 37 |
| 10 | 7.3 | 7 | rising | PB013 ok | 2/0 | 0/-/0 (extraction failed) | 0 of 1 | 37 |
| 11 | 7.9 | 7 | rising | PB014 ok | 3/0 | 0/-/0 (extraction failed) | **1 of 1** | 36 |
| 12 | 8.3 | 7 | rising | PB015 ok; batch capped to 3 (slot alignment) | 3/0 | 4/0/1 | **1 of 1** | 39 |
| 13 | 8.8 | 7 | peak | PB016 ok | 3/0 | 4/0/1 | 0 of 2 | 43 |
| 14 | 7.3 | 6 | resolution | PB017 ok | 3/0 | 4/0/1 | 0 of 3 | 47 |
| 15 | 4.0 | 2 | resolution | PB019 ok (sacred finale, authored) | 1/0 | 0 opened, 5 suppressed | extractor sweep: 47 | 0 |

Contract totals: 36 conditions checked, 1 failed (tick 2, `tension_at_most` on
PB001). That single failure triggered the **rolling horizon's first live firing
ever**: "abandoned 5, generated 5 beat(s)" at tick 2, and the replacement queue
(PB006-010) then completed 5 for 5. The relief valve run 5 armed but never
exercised is now live-validated: one firing, clean recovery, no churn.

Eight-arm comparison (run 5's seven-way table plus this run):

| metric | run 5 (sacred finale) | this run (Slice 0) |
|---|---|---|
| overall drift, scored ticks | **1.39** | 1.63 (4th of 8, within the 1.20-1.73 band) |
| overall bias (signed) | +0.81 | **+0.61** (2nd best of 8) |
| rising drift (1-12) | 1.56 | 1.61 |
| peak drift (tick 13) | 1.8 (7 vs 8.8) | 1.8 (7 vs 8.8), 8 of 8 arms |
| resolution drift (14-15) | **0.15** | 1.65 |
| final scene: target 4.0 | **4** | 2 (first undershoot; settled) |
| final-scene event kind | six-months-later denouement | weeks-later collapse-aftermath denouement |
| manual interventions | 0 | 0 |

**Regression check: passed.** The ending stays at or under the pre-registered
cap of 5 with a settled scene (2, calm band, END OF NOVEL on the page), the
descent de-escalated without a re-roll, and drift stays inside the historical
band with the second-best bias. Run 5 keeps the best resolution tracking (0.15
vs 1.65): this run's finale undershot the target by 2 where run 5 hit exactly,
so the loop features cost nothing structural, and the sacred chain's authored
step is now live-proven at the price of a softer landing than asked.

## 7. Ledger accounting

| quantity | this run | run 5 |
|---|---|---|
| loops opened (applied) | 50 | 78 |
| capped at creation | 16 | (no cap) |
| deduped at creation | 1 | (no dedup) |
| suppressed at finale | 5 | 8 |
| closed by judged beat claims | **3** | (feature off) |
| closed by extractor, ticks 1-14 | 0 | 1 |
| closed by extractor at finale | 47 (the sweep) | 3 |
| open at tick 14 | **47** | 77 |
| open at end | 0 | 74 |

The honest hygiene-only number is the tick-14 comparison: 47 vs 77, roughly 30
loops of flood prevented by cap plus dedup plus 3 judged closures. The
end-of-run 0 vs 74 is dominated by the unaudited sweep (section 4) and should
not be quoted as the Slice 0 result.

## 8. Should `loop_resolved` be un-gated?

**Not yet.** The judge is validated, but the *claims* are not yet trustworthy
enough to be load-bearing. Un-gating the `loop_resolved` contract check today
would attach postconditions to claims the judge refuses 77 percent of the time,
converting 10 honest refusals into contract failures, and this run demonstrated
what one contract failure does: it fires the rolling horizon and abandons the
queue (tick 2). The wedge species this would create is "beat honestly advances a
loop, claims it, fails its own contract, queue churns".

Prerequisite first: **reframe claim authoring.** The beat prompt should
distinguish "this beat RESOLVES the loop, the question is answered on the page"
from "this beat ADVANCES the loop" (either a separate `advances_loops` field or
an explicit resolves-means-answered rule with an example). The claim stream is
plentiful (10 of 14 executed beats carried claims) and the judge is a reliable
referee, so claim precision is measurable per run: when a reframed-prompt run
grants at a usefully higher rate, un-gate `loop_resolved` for beats that still
claim resolution. The judge, not the gauge, is what makes that iteration cheap.

Separately: `coherence.loop_closure` itself has now had its validation run and
behaved exactly as designed (closes only confirmed claims, full audit trail,
never broke a tick). **Recommend flipping its default to True.**

## 9. Stability, silent-issue audit, observability

- 16 of 16 ticks completed first try, 0 of 2 run-level retries used per chunk,
  `errors/` empty all run. OpenRouter clean (no 5xx, no 429, no timeouts).
  Inter-scene gaps 64-119s (mean ~81s excluding the two chunk-boundary gaps).
- Beat pipeline: 5 batches (initial, horizon revision, tick 7, tick 12 capped
  to 3 by slot alignment, finale authored), all parsed first try. No beat ever
  failed twice (no wedge). Run 1 additionally saw one stage-3 planner JSON parse
  failure whose empty-plan fallback still produced a passing scene.
- Two graceful fact-extraction degradations (ticks 10 and 11, malformed
  extractor JSON after retry; run 5 had one). Cost: those ticks applied no loop
  or entity updates, so `loops_opened: 0` there is a data gap, not calm. At tick
  15 the extractor invented `C_`-prefixed character IDs so entity updates
  skipped gracefully (usual noise, worth keeping an eye on).
- Tension rewrites: 5 attempted (ticks 1-3, 6-7), all "revision not closer,
  original kept", none needed after tick 7. Character-detector noise persists
  ("It", "That", "Corporate Security", "Meridian News").
- Metrics semantics held everywhere: `loops_closed_by_beat` distinguishes null
  (no claims, did not run) from 0 (ran, closed nothing) exactly as specified;
  no nulls where numbers belong.
- Observability follow-ups (minor, from the run): (1) a judge "no" logs its
  reason at info level only, so refusal reasons are absent from artifacts while
  grant reasons persist in `resolution_summary`; worth persisting refusals
  (e.g. on the beat's execution notes) for honesty audits. (2) capped-loop
  counts are log-only; a `loops_capped` metrics field would complete the
  creation-hygiene picture d406e45 started.

## 10. Verdict

Slice 0 is validated: the discriminative inversion works. Thirteen cheap judge
calls produced three closures that read honestly and ten refusals that were each
correct on the page, with zero parse failures and zero tick impact; the
deterministic hygiene held creation to the cap and is now fully observable. The
run also bought two live firsts for free (rolling horizon recovery, sacred
finale authored fallback) and confirmed the ending problem stays closed with the
loop features on. The next numbers to move: claim precision (reframe
resolves-vs-advances at authoring, then un-gate `loop_resolved`), the extractor
sweep (route through the judge or tag as unaudited), and semantic dedup (the
0.784 near-miss). Flip `coherence.loop_closure` to default True.

## Artifacts

- Scored run (gitignored `work/`): `work/novels/slice0-run2_fe1dd201/` (16
  scenes, `memory/metrics.jsonl` with the Slice 0 fields live,
  `plot_outline.json` with PB018's supersession note and PB019,
  `memory/open_loops.json` holding all 50 dispositions including the 3 judged
  `resolution_summary` audit trails and the 47 sweep entries).
- Abandoned first attempt (kept for the record): `work/novels/slice0-run_a9f9b801/`
  (ticks 0-5 at ea8a5e7, the claim-format kill).
- Run logs: scratchpad copies (`slice0r2-tick0.log`, `slice0r2-t1-5.log`,
  `slice0r2-t6-10.log`, `slice0r2-t11-15.log`), not committed.
- Executed at d406e45 with `coherence.loop_closure: true` as the single config
  difference from run 5; no code changes during the runs, no commits, no manual
  interventions.

## Addendum: grant-rate re-measurement (12th July 2026, at 6575bb1)

The re-measurement run this report's section 8 asked for: same protocol, same
premise, first live exercise of the honest-accounting batch (6575bb1). One
question: under the resolves-vs-advances reframe, does beat claim precision
rise from 3/13 (23 percent)? **Answer: yes, roughly doubled, 6/12 (50 percent),
and the refusal species transformed from systematic advance-claiming to genuine
edge cases. Recommendation: one more cheap iteration before un-gating
`loop_resolved`** (details below; two mechanical depressors identified, both
fixable outside the claim pipeline).

**Method.** Fresh project `work/novels/grantrate-run_39a993f0/`, foundation and
user goal copied verbatim from slice0-run2, config identical except the
`loop_closure: true` line is now absent (it defaults True at 6575bb1; the
defaults are the measurement, diff verified). Backend api / openrouter
(`anthropic/claude-haiku-4.5`), timeout 120, plot-first, contracts, rolling
horizon, `target_story_length: 15`. 16 scenes (ticks 0-15), 31,153 words, three
gated chunks, zero manual interventions, zero tick retries, `errors/` empty all
run.

**Beat claims, all 12, in order** (a claim counts as honest when the judge
confirmed the loop resolved in the claimed scene, through either judge path):

| tick | beat | claimed loop | verdict |
|---|---|---|---|
| 3 | PB002 (Haler privately meets Celira) | OL3 does Haler already know | **YES** (beat judge) |
| 10 | PB009 (forensics finds the money trail) | OL5 purpose/recipient of the data | **YES** (beat judge) |
| 12 | PB011 (formal forensic interview) | OL37 what the specialists found | no: "cuts off before presenting the specific forensic details" (scene truncation, see below) |
| 13 | PB012 (Liros implicates Zephas) | OL14 will Zephas manipulate Liros | **YES** (beat judge) |
| 13 | PB012 | OL33 how Zephas responds to Liros | no: "contains no response from Zephas to this action" (a true advance-claim, the only one) |
| 14 | PB013 (board reports to law enforcement) | OL31 will the board escalate | **YES** (same-scene extractor grant; beat claim preempted) |
| 14 | PB013 | OL39 charges filed by end of day | no: "does not reveal whether criminal charges will actually be filed" |
| 15 | PB014 (six-weeks-later finale) | OL36 consequences for Zephas | **YES** (same-scene extractor grant) |
| 15 | PB014 | OL6 criminal charges outcome | **YES** (same-scene extractor grant) |
| 15 | PB014 | OL28 will Vernholt discover the exports | no: specifics not depicted |
| 15 | PB014 | OL22 Vernholt forensics response | no: same family |
| 15 | PB014 | OL27 what data, sold to whom, how long | no: "provides no specific details" |

Totals: 12 claims, 6 honest (50 percent) vs baseline 3/13 (23 percent); through
the beat-judge path alone 3 of 9 (extractor judging runs first in the tick and
granted 3 loops the beat had also claimed). 0 parse failures, 0 sanitizer
strips. The OL10-style discriminative evidence recurred: **OL39 was refused at
tick 14 (complaint filed, charges pending) and granted at tick 15** when the
arraignment landed on the page.

**The refusal composition is the real result.** Baseline: 10 of 10 refusals
were the planner claiming loops its beat merely advanced. This run: 1 clear
advance-claim (OL33), 1 refusal caused by scene truncation (OL37, the judge's
reason literally says the scene cut off), 1 timing edge granted the next tick
(OL39), and 3 finale wrap-up over-claims of specifics (OL28/OL22/OL27, all on
the single 5-claim finale beat). Non-finale beat claims ran 4 of 7 honest (57
percent), and 4 of 6 (67 percent) setting aside the truncation casualty.

**advances_loops adoption: complete.** 13 of 14 authored beats carried
advances_loops (2-3 real IDs each, no phantom references); the only empty one
is the finale wrap-up, where advances would be wrong anyway. The enthusiasm
that produced the baseline's refusals now has its home, and resolves stayed
scarce and mostly honest.

**Un-gating recommendation: not yet, but the systematic failure mode is gone.**
50 percent overall sits under the 60-70 bar, and each refusal would have been a
contract failure firing the rolling horizon (ticks 12, 13, 14 and the finale
would all have churned). But the two depressors are mechanical, not
claim-pipeline: (1) the finale beat over-claims by nature (5 claims, 3
refusals; exempt it from `loop_resolved` or judge-prescreen its claims), and
(2) 8 of 16 scenes hit the 3000-token writer ceiling and end mid-sentence,
which directly caused OL37's refusal and plausibly OL28/OL22/OL27's. Fix those
two (finale exemption plus a larger or end-aware writer budget) and the
measured non-finale precision (57-67 percent) says the next run clears the bar.

**Extractor claims facing the judge (first live exercise): 8 judged, 6 granted,
2 refused, cap 5 never reached** (max 3 in one tick). Grants all carry real
audit trails (OL16 Liros chooses cooperation, OL25 Celira refuses the
settlement, OL31 board files the complaint, OL6/OL39/OL36 charges and
arraignment at the finale). The tick-8 refusal is exactly the designed
skepticism: "the scene does not depict him forming or executing any defense
strategy during the meeting itself." The unaccountable side door is closed: the
same path that swept 47 loops in the validation run produced 6 audited closures
here.

**Finale accounting (first live expiry): the mass-sweep is gone.** At tick 15,
3 loops closed via judged extractor claims, and the remaining **46 open loops
expired** with status `expired` and summary "left open at story end", never
counted as closures (`loops_closed: 3`, `loops_expired: 46`). `dangling_threads:
45` (23 critical, 22 high), an honest editorial signal the baseline's sweep
fabricated away. 4 fresh hook loops suppressed, `loops_opened: 0`.

**Ending.** Sacred path: pending beat PB014 passed the finale screen (ask
source `pending_beat`; the authored fallback was not needed this time), tension
precheck passed, first render scored 6 over the cap, **one re-roll landed the
final scene at 4 against target 4.0, the second exact-hit ending across arms**
(run 5: 4/4; slice0-run2: 2/4). Regression check passed (at or under 5,
settled aftermath content, six-weeks-later frame, goal succeeds on the page
with charges filed and the merger proceeding with full disclosure). One page
flaw: the scene is truncated mid-sentence by the writer token ceiling, so there
is no clean final line or end marker; settled in substance, clipped on paper.
Drift over 15 scored ticks: 1.23 (best in the historical 1.20-1.73 band), bias
+0.61, resolution drift 0.15 (ties run 5's best). Also a run first worth
recording: **the first successful tension rewrite in any arm** (tick 5, 8 down
to 6 against target 5.3; every prior attempt across arms failed to get
closer), and the new transition guard fired correctly at tick 1 ("drop too big
for a prose rewrite; events set the floor").

**Ledger accounting** (vs slice0-run2 and run 5):

| quantity | this run | slice0-run2 | run 5 |
|---|---|---|---|
| loops opened (applied) | 55 | 50 | 78 |
| capped at creation | 9 | 16 | (no cap) |
| deduped at creation | 2 | 1 | (no dedup) |
| suppressed at finale | 4 | 5 | 8 |
| judged closures (beat + extractor) | **9** (3 + 6) | 3 (3 + 0) | (feature off) |
| unaudited extractor closures | **0** | 47 (the sweep) | 4 |
| expired at story end | 46 | 0 (swept instead) | 0 (left open) |
| open at tick 14 | 49 | 47 | 77 |
| open at end | 0 (honest statuses) | 0 (sweep-dominated) | 74 |

**Stability and observability.** 16 of 16 ticks first try, no timeouts or rate
limits, inter-scene gaps 60-112s (mean 81s). 36 contract conditions checked, 0
failed, no horizon firing, no wedge. Zero fact-extraction failures (baseline
had 2 data gaps). 17 judge calls total, 17 parsed first try. Refusal reasons
now surface in console output as designed; `loops_capped` is live in metrics
(null only on the tick-0 first-tick path, a cosmetic gap). Known noise
persists: character detector ("He", "She", "East Norholt"), one extractor batch
with invented prefixed entity IDs (skipped gracefully). One new watch item:
near-duplicate beats across batches (PB005/PB006 both narrate the merger
acceleration; beat-level dedup does not exist and loop-level dedup cannot see
it).

**Verdict.** The reframe works: precision doubled, advance-claiming as a
systematic species is extinct, and every closure in the run (9 of 9) carries an
auditable scene-grounded reason while 46 unanswered questions are now honestly
labeled as such instead of swept. Hold `loop_resolved` gated for one more
iteration: exempt the finale beat and lift the writer token ceiling, then
re-measure; the non-finale numbers say that run clears the 60-70 bar.

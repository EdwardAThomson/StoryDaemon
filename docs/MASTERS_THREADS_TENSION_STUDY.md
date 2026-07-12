# Masters Corpus Study: Story Threads and Tension Curves at Chapter Granularity

**Status:** Offline corpus experiment, complete (no pipeline code changes)
**Date:** 2026-07-12
**Serves:** the thread interleaving design (`THREAD_INTERLEAVING_DESIGN.md`) and the arc-pressure tension curve (`coherence.target_tension_curve`, whose default `[[0,3],[0.25,5],[0.5,6],[0.75,8],[0.9,9],[1.0,4]]` was invented, not measured)
**Artifacts:** raw texts, per-chapter annotations, and driver scripts (`extract_chapters.py`, `mts_annotate.py`, `mts_stats.py`, `mts_extra.py`, `out/mts_*.jsonl`, `out/mts_results.json`) live in the session scratchpad; only aggregates and short quotes appear here

Everything in this document is **informative, not prescriptive**: it describes what four master novels measurably do, as calibration for design decisions. We do not have to mimic any of it.

## Motivation

Two questions from the thread interleaving work:

1. **How many story threads do master novels actually run, and how do they interleave them?** The Slice T1 backfill showed that StoryDaemon's own free-authored thread labels are noise (30 distinct "threads" over 34 beats) and that character casts are the more reliable thread signal. This study applies cast-based thread identity to real books.
2. **What do master tension curves actually look like?** Arc-pressure steers scenes toward `coherence.target_tension_curve`, but that curve's shape (slow monotonic ramp from 3 to a 0.9-position peak of 9, then a drop to 4) was authored from intuition. The 2026-06 validation showed the pipeline tracks rising targets but cannot de-escalate; before engineering a fix, it is worth knowing whether the target shape itself resembles anything masters do.

The tension scale used throughout is the project's own `TENSION_ANCHORS` rubric (`novel_agent/agent/tension_scale.py`), quoted verbatim into the scorer prompt, so every number here is on the same 0-10 scale as `novel metrics` and the arc-pressure targets.

## Corpus

Four public-domain novels, fetched as plain text from gutenberg.org, chosen for structural variety. Full books, chapter-level granularity.

| Book | Author | PG # | Role in the study | Units | Words |
|---|---|---|---|---|---|
| The Thirty-Nine Steps (1915) | John Buchan | 558 | presumed single-thread chase thriller, genre-matched baseline | 10 | 40.8k |
| The Moonstone (1868) | Wilkie Collins | 155 | multi-narrator mystery, explicit thread structure | 51 | 194.6k |
| Dracula (1897) | Bram Stoker | 345 | epistolary, famously parallel strands that converge | 27 | 161.0k |
| Pride and Prejudice (1813) | Jane Austen | 1342 | domestic multi-arc, the calm-register contrast | 61 | 121.7k |

Total: 149 chapter-level units, 518k words. "Units" are chapters, except in The Moonstone, where the prologue, the epilogue, and the five unchaptered late narratives (Ezra Jennings's journal and the four short closing statements) each count as one unit; its chaptered narratives (Betteredge's 23 chapters, Miss Clack's 8, Bruff's 3, Blake's 10) contribute a unit per chapter. Gutenberg frontmatter, footers, and the 1894 P&P edition's illustration blocks were stripped.

## Method

### Annotation

Annotator: `anthropic/claude-haiku-4.5` via OpenRouter, temperature 0, one call per chapter per task, strict JSON output, one re-ask on malformed JSON. Two tasks:

1. **Cast/strand extraction:** per chapter, the POV or focal character (for diary/letter chapters, the writer of the dominant entry), the principal cast (3 to 6 characters present and driving events, fullest canonical names, mentioned-only characters excluded), and a one-line strand summary ("WHO is doing WHAT toward WHAT end"). Chapters over ~8,200 words were sent as first 4,000 plus last 4,000 words with the omission noted.
2. **Tension scoring:** 0-10 against the `TENSION_ANCHORS` rubric rendered verbatim by `scorer_anchor_block()`, with the project scorer's framing (rate stakes, threat, uncertainty, and pressure, not dramatic words; rate the chapter as a whole, letting a genuine climax raise the score). Long-chapter policy, applied uniformly: chapters over ~4,200 words were sent as the first 2,000 plus last 2,000 words with a bracketed note giving the size of the omitted middle.

### Thread identity (deterministic clustering)

Names are normalized in Python (lowercase, punctuation stripped, honorifics removed) and resolved through a hand-built per-book alias table (e.g. `mina murray` = `mina harker`; the table looks up the raw form before title-stripping so `mr bennet` and `mrs bennet` stay distinct). The clustering rule, fixed before interpretation:

- A chapter's **signature** is its canonical principal cast plus a `pov:` token for its POV character. POV participates in identity because it is the strongest thread signal in epistolary and single-narrator books.
- Chapters are processed in narrative order. Each thread's **profile** is the set of signature elements present in at least 50 percent of its chapters (majority cast).
- A chapter joins the thread with the highest Jaccard overlap between its signature and the thread profile if that overlap is **>= 0.3** (ties go to the most recently active thread); otherwise it opens a new thread.
- **Convergence detection** is cast-only (POV tokens excluded): a chapter whose cast covers at least half of the cast profile of two or more established (2+ chapter) threads records a merge event at that chapter. The first merge per thread pair is reported as the convergence point, as a fraction of the book.

Threshold sensitivity (thread count at Jaccard 0.2 / 0.3 / 0.4): Steps 1/5/7, Moonstone 6/8/13, Dracula 3/4/7, P&P 3/3/7. Thread counts are rule-dependent within a range; 0.3 is reported as primary and the sensitivity is kept in view below.

## Reliability

A 20-chapter stratified sample (5 per book at position quantiles 0.1/0.3/0.5/0.7/0.9) was re-annotated for both tasks in shuffled order at temperature 0.8 (the first pass being temperature 0, a same-temperature re-run would mostly measure API determinism; the higher-temperature re-pass measures stability of the judgment).

| Check | Result |
|---|---|
| Tension within +-1 | **20/20 = 100 percent** (gate was 70; exact match 17/20 = 85 percent, MAD 0.15) |
| Cast set overlap | mean Jaccard **0.95** (17/20 identical sets) |
| POV match | 20/20 = 100 percent |

The three cast disagreements were borderline-presence characters (a collective antagonist counted or not, an offstage official). Chapter-level tension on an anchored rubric is a highly stable judgment, notably more stable than the paragraph-level block labels of the block decomposition study (80 to 96 percent). Single-annotator self-consistency, not human ground truth, with the same caveat as that study.

## Results: thread structure

### Per-book thread tables (threads with 2+ chapters; singletons noted in text)

**The Thirty-Nine Steps (10 chapters).** Thread count at the primary rule: 5 (three with 2+ chapters), but this is the method showing its edge, not the book having five strands: every unit has POV Hannay and the supporting cast rotates completely at each stage of the chase, so cast identity fragments into episodes (Scudder/London, moors pursuit, Bullivant/London). At threshold 0.2 the book is **one thread**, which is the correct reading. No merges (nothing to converge). Cut-away structure: none; it is a relay of episodes on one strand.

**The Moonstone (51 units).** Six threads with 2+ chapters, organized as sequential narrator blocks, plus prologue and epilogue singletons:

| Thread | Units | Span | Majority cast (POV) | Mean tension | Range |
|---|---|---|---|---|---|
| Betteredge: household and first investigation | 23 | ch 3-50 | Betteredge, Blake, Rachel, Lady Verinder, Cuff | 5.6 | 1-7 |
| Betteredge: frame/editorial chapters | 5 | ch 2-39 | Betteredge, Blake, Rosanna | 5.2 | 2-8 |
| Miss Clack: London aftermath | 9 | ch 25-33 | Clack, Rachel, Lady Verinder, Godfrey, Bruff | 5.3 | 1-7 |
| Bruff: lawyer's strand | 2 | ch 34-35 | Bruff, Blake, Rachel, Murthwaite, Luker | 5.0 | 5-5 |
| Blake: return and resolution | 8 | ch 38-49 | Blake, Betteredge, Jennings, Candy | 6.4 | 2-9 |
| Cuff: wrap-up | 2 | ch 47-48 | Cuff, Blake, Bruff, Godfrey | 6.0 | 3-9 |

The two Betteredge rows are one narrator strand that the rule split (frame chapters where he writes about writing); read the book as ~5 strands. Runs are long blocks (a 14-chapter run, then 9, then 6): Collins interleaves by **hand-off**, not alternation. Convergence is late: the Blake thread first covers the Betteredge-strand cast at 0.83, and the Clack, Bruff, and Cuff threads **never** merge in a co-present chapter; narrators pass the baton and leave.

**Dracula (27 chapters).** Two threads at chapter granularity, plus two singleton chapters (the Demeter newspaper-cutting chapter, and Lucy's death chapter with its mixed documents):

| Thread | Units | Span | Majority cast (POV) | Mean tension | Range |
|---|---|---|---|---|---|
| Jonathan in Transylvania | 4 | ch 1-4 | Jonathan, Dracula | 8.0 | 7-9 |
| England: Lucy, the asylum, then the hunt | 21 | ch 5-27 | Seward, Van Helsing, Mina, Jonathan, Arthur, Quincey | 6.9 | 2-9 |

First convergence at **0.28** of the book (Mina reconnects the Transylvania strand to the England strand). The famous parallel strands *within* England (Mina/Lucy at Whitby versus Seward/Renfield at the asylum) are real but live **below chapter granularity**: Stoker interleaves diary entries from different strands inside single chapters, so chapter-level clustering sees one broad England thread. The final 16 chapters are a single unbroken run of the converged full-cast thread.

**Pride and Prejudice (61 chapters).** Three threads, which correspond to recognizable arcs sharing one POV (Elizabeth) and one household:

| Thread | Units | Span | Majority cast (POV) | Mean tension | Range |
|---|---|---|---|---|---|
| Bennet household / Collins arc | 15 | ch 1-57 | Elizabeth, Mr Bennet, Mrs Bennet, Collins | 3.9 | 2-7 |
| Jane-Bingley / Darcy courtship arc | 33 | ch 3-61 | Elizabeth, Jane, Bingley, Darcy | 4.3 | 1-8 |
| Wickham / Gardiners / Lydia arc | 13 | ch 16-52 | Elizabeth, Jane, Wickham, Gardiners | 4.6 | 2-6 |

Arcs braid tightly (switch rate 0.35, mean run 2.8 chapters, longest run 11) and merge **constantly** from 0.07 onward: they are not parallel strands with separate casts but interleaved concerns of one social world, always one chapter away from co-presence.

### Interleave summary

| Book | Threads (primary rule) | Honest reading | Switch rate | Mean / max run | First convergence | Never-merged threads |
|---|---|---|---|---|---|---|
| Steps | 5 | **1** thread, rotating episode casts | (0.56, artifact) | 1.7 / 3 | n/a | all (nothing converges) |
| Moonstone | 8 | **~5** narrator strands, block hand-off | 0.36 | 2.7 / 14 | 0.83 | Clack, Bruff, Cuff strands |
| Dracula | 4 | **2** chapter-level strands (+ sub-chapter braiding) | 0.19 | 4.5 / 16 | 0.28 | none |
| P&P | 3 | **3** braided arcs on one POV | 0.35 | 2.8 / 11 | 0.07 | none |

Four books, four different interleaving regimes, and none of them is the rapid A/B/A/B alternation of parallel equal strands. Masters either commit to long blocks (Collins: 8-23 chapter narrator blocks; Stoker: a 16-chapter converged run), braid arcs inside a single POV (Austen), or run one strand flat out (Buchan). Chapter-level cut-aways to a genuinely different cast are rare events.

## Results: tension curves

### Book registers

| Book | Mean | SD | Min-max | Chapter-to-chapter volatility (mean abs delta) | Calm chapters (<=3) |
|---|---|---|---|---|---|
| Steps | 7.1 | 0.7 | 6-8 | 0.9 | 0/10 (0%) |
| Dracula | 7.1 | 1.6 | 2-9 | 1.5 | 1/27 (4%) |
| Moonstone | 5.6 | 1.9 | 1-9 | 1.7 | 8/51 (16%) |
| P&P | 4.3 | 1.5 | 1-8 | 1.1 | 18/61 (30%) |

Register is a **book-level** property spanning three full points (thriller 7, domestic comedy 4.3), and every book oscillates chapter to chapter (volatility 0.9 to 1.7) rather than ramping smoothly. No chapter in 149 scored 10 (the rubric reserves it for the story-defining breaking point; observed ceiling is 9).

### Decile tables (mean tension by tenth of the book, chapter midpoints)

| Decile | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
|---|---|---|---|---|---|---|---|---|---|---|
| **Default curve** (at decile midpoints) | 3.4 | 4.2 | 5.0 | 5.4 | 5.8 | 6.4 | 7.2 | 8.0 | 8.7 | 6.5 |
| Steps | 8.0 | 7.0 | 7.0 | 6.0 | 7.0 | 7.0 | 6.0 | 8.0 | 7.0 | 8.0 |
| Moonstone | 3.6 | 5.0 | 6.8 | 7.0 | 5.6 | 5.0 | 5.8 | 7.0 | 6.6 | 3.6 |
| Dracula | 7.7 | 5.5 | 6.3 | 7.0 | 8.0 | 7.7 | 6.0 | 7.7 | 7.5 | 7.7 |
| P&P | 2.5 | 3.8 | 4.0 | 4.7 | 3.0 | 5.0 | 4.3 | 6.2 | 4.5 | 4.7 |

Correlation of each book's decile means with the default curve: P&P 0.70, Moonstone 0.45, Dracula 0.27, Steps -0.07. The invented curve resembles Austen's domestic shape far more than the genre-matched thriller.

### Where the default curve diverges from the masters

**Openings: masters open at or above their register, the default opens cold.** Steps opens at 8 (Scudder's murder is chapter 2), Dracula at 8 (the castle chapters are among its tensest), Moonstone at 6 (the cursed-diamond prologue) before dropping to its true calm start, P&P at its own calm register. Z-scored within book, master openings average -0.14; the default's opening is z -1.7 against its own curve. Only P&P and Moonstone's chapter-2 trough look anything like "start at 3."

**Peaks: masters peak around 0.7-0.8 as a decile, and thrillers save the single highest chapter for the very end.** The highest decile is d7 in P&P (6.2, the Lydia crisis; single-chapter peak 8 at position 0.75) and jointly d3/d7 in Moonstone (7.0 twin peaks: the theft investigation, then Blake's discovery; single-chapter 9s at 0.74 and 0.91). Dracula plateaus at 7.5-8 from mid-book with 9s scattered from Lucy's death onward, and its final chapter is a 9. Steps ends on 8. The default's peak *height* (9) matches the observed single-chapter ceiling, but its *position* (0.9) is later than the domestic/mystery peak deciles and earlier than the thriller climaxes, which land in the final chapter itself.

**Valleys: mid-story dips are real but shallow at decile resolution.** Moonstone's post-theft lull (d4-d5, ~5.0 against a 7.0 peak: a 2-point valley), Dracula's d6 (6.0, the regrouping chapters), P&P's d4 (3.0, the Hunsford calm before the proposal). Masters de-escalate by about 1.5 to 2 points from local peaks, repeatedly; the sawtooth is the texture (individual calm chapters land at 1-2 even mid-book: Dracula's chapter V scores 2 one chapter after a 9).

**Tails: the default's "end at 4" matches nobody.** Masters end one of two ways: **wind-down books descend well below 4** (Moonstone's last three units score 2, 1, 3; P&P's last two score 2, 1: full denouement, warm and stakes-free), while **climax-ending thrillers stay at 8-9 to the final page** (Steps ends 8; Dracula's last chapter is 9, its brief warm coda living inside that final chapter, below this study's granularity). The scorer demonstrably recognizes calm endings when they exist (P&P final chapter, rationale: "an epilogue summarizing the peaceful aftermath and resolution of all conflicts, with no active stakes"), so the 3-4 endings StoryDaemon's own runs produce are a real behavior, not a gauge floor; what the masters show is that a *committed* ending goes lower (1-3) or does not descend at all.

### Per-thread tension: is there a calm B-thread?

No. Within each book, every 2+ chapter thread sits within **0.9 points** of the book mean (largest deviation: Dracula's Transylvania strand, which is *hotter* at +0.9; Moonstone's Blake strand +0.8; everything else within 0.6). No master here maintains a persistently calm secondary strand to cut to. Instead:

- **Calm lives in chapters, not threads.** P&P's 18 calm chapters and Moonstone's 8 are distributed across their threads (every P&P arc contains calm chapters; the hottest Moonstone thread contains a 2).
- **Within-thread range is wide everywhere** (typically 5-7 points), i.e. each thread carries its own local sawtooth.

This matches the Slice T1 backfill finding from the generated side (no calm thread existed there either) but reframes it: the masters suggest the interleaving design's relief resource is calm *chapters* (and where they are placed), not a calm *thread*.

## Results: the interleave-tension link (cut-away deltas)

At each of the 49 chapter transitions where the thread assignment changes, the tension delta (incoming minus outgoing):

| | Cooler (delta < 0) | Same | Hotter (delta > 0) | Mean delta | Mean abs delta |
|---|---|---|---|---|---|
| Thread switches (n=49) | 19 (39%) | 13 (27%) | 17 (35%) | -0.04 | 1.35 |
| Same-thread transitions (n=96) | 35 (36%) | | | -0.01 | 1.39 |

Histogram of switch deltas: -7 x1, -4 x1, -3 x1, -2 x4, -1 x12, 0 x13, +1 x6, +2 x7, +3 x4.

**The routine cut-away is tension-neutral**: switches are statistically indistinguishable from staying on the same thread (39 percent cooler either way, near-zero mean). Masters do not run a standing hot-to-cool relief rhythm at thread boundaries.

**But the three largest drops in the entire corpus all coincide with thread switches**: Dracula ch IV to V (9 to 2: Jonathan trapped among the vampire women, cut to Lucy's cheerful marriage-proposal letters), Moonstone prologue to ch 1 (6 to 2: the curse, cut to Betteredge's comic domestic opening), and Moonstone N3 ch III to IV (9 to 6, off Blake's nightgown discovery). The hot-to-cool relief cut the interleaving design describes is a real master device, used **three times in 149 chapters** at structurally loud moments, not a scheduling policy. The +3 cuts (four of them) are the mirror device: cutting away *into* trouble.

## Implications for the thread-construction design (informative, not prescriptive)

1. **Observed thread counts are small: 1 to ~5-6, and only 2-3 ever alive concurrently.** The genre-matched thriller is genuinely single-thread; the maximal case (Moonstone) runs ~5 narrator strands *sequentially*, not in parallel. A design targeting 2-3 threads is at the masters' ceiling, not their floor, and a single-thread mode should remain a first-class shape for chase-structured stories.
2. **Interleaving is commitment plus hand-off, not alternation.** Long single-thread runs (8-16+ chapters) are normal; braiding tighter than ~2-3 chapters per run appears only when arcs share a POV and cast (Austen). This echoes the block study's paragraph-level finding: the master signature is commitment, and generated fiction's instinct to rotate rapidly has no support here either, one level up.
3. **Convergence timing varies by architecture**: parallel strands with separate casts either converge early and run converged (Dracula, first contact at 0.28, fully merged cast for the last 40 percent) or hand off and never co-converge until a final-quarter gathering (Moonstone, 0.83+, with three strands never merging at all). "All threads converge at the climax" is one option, not a law.
4. **The calm B-thread assumption is not supported.** Per-thread mean registers differ by under a point within a book. If the scheduler wants relief material, the data points to calm chapters placeable on any thread (16-30 percent of chapters in the calmer half of the corpus) plus the occasional deliberate big-drop cut at a structural boundary, rather than a dedicated low-tension strand.
5. **The default tension curve could be replaced by register + sawtooth + ending mode rather than a single ramp.** What masters actually exhibit: (a) a genre register (4.3 to 7.1 mean) that the whole book oscillates around with volatility ~1-1.7 and local drops of 1.5-2 points; (b) an opening at or above register, not below it; (c) a peak block at ~0.7-0.8 (mystery/domestic) or a final-chapter climax (thrillers); (d) an explicit ending mode: descend to 1-3 for a denouement, or hold 8-9 to the last page. The current curve's cold open, smooth monotonic rise, 0.9 peak, and 4-tail is a shape none of the four books traces (best correlation 0.70, with the calmest book; the genre-matched thriller is at -0.07). Given the 2026-06 finding that the planner cannot de-escalate into a descending tail, it is also worth noting the masters' descents are short (1-3 chapters of denouement after the climax), which is a much smaller de-escalation demand than the current curve's long falling segment.
6. **Tension targets of 9-10 should be rare or absent at chapter scale.** 149 master chapters produced no 10 and only ~10 percent 9s; sustained 8+ deciles occur only in the two thrillers.

## Caveats

Chapter granularity hides real structure twice over: Dracula's Whitby/asylum braiding happens between diary entries inside chapters, and both thriller codas live inside their final chapters, so this study understates both fine-grained interleaving and terminal wind-downs. The cast-based clustering rule fragments single-POV books with rotating supporting casts (Steps) and splits one Moonstone narrator strand; thread counts are threshold-dependent within the reported sensitivity range. One annotator model (claude-haiku-4.5), self-consistency checked once at 20 chapters (100 percent within-1 tension, 0.95 cast Jaccard), no human gold labels; long chapters were scored on their first and last 2,000 words, which can miss mid-chapter peaks. Four books is a corpus for orientation, not statistics; all four are pre-1920 and their pacing conventions differ from modern genre fiction.

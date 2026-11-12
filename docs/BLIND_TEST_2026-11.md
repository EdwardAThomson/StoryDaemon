# Blind Test, November 2026: Can a Reader Tell StoryDaemon From an 1800s Novel?

**Status:** reader page built and tried by one reader (the project owner). Sharing with more readers is next.
**Code:** `experiments/blind_test/` on branch `claude/project-thread-oqxwxt` (PR #32). Inputs live under the gitignored `work/blind/` (see section 8).
**Writer:** Opus 5.5 via OpenRouter, through the real StoryDaemon writer path. **Cost:** about $1.22 in all.

## 1. The short version

A reader is shown two passages: a real chapter from an 1800s novel with every name swapped, and a StoryDaemon scene of the same events using the same swapped names. They are asked which one a person wrote.

With the paragraph plan taken from the real chapter and style targets measured from the rest of the novel, StoryDaemon's sentence lengths, paragraph sizes, speech share and punctuation land close to the author's. Our one reader so far scored the StoryDaemon passages equal to Susan Ferrier's on enjoyment and on how much they read like the 1800s. He still picked Ferrier both times, once with certainty, once as a guess, and his reasons were about **word choice**: "more archaic words", "a French phrase", "a few words that I want to say are more human".

So sentence structure is now about right for this period. Word choice is the next gap, and the next piece of work.

Two side findings matter for anyone repeating this. Opus can recite *Pride and Prejudice* word for word, so Austen cannot be used. And telling it to write Austen's events in Austen's style made it recite her.

## 2. The test

- **Pairs:** a real passage, renamed, against a StoryDaemon scene of the same events. Every name in both comes from the StoryDaemon name generator (victorian bank, gentry register), never from the book or from the model.
- **StoryDaemon's version** is written from the real chapter's own paragraph plan: one line per paragraph saying its kind (dialogue, action, inner thought and so on), who speaks, and what happens, in plain words with no phrase longer than three words taken from the book. Lengths are the book's own, cut by 12 to 30% because Opus writes long.
- **Plain Opus** is also written for comparison: the same lines as a simple list of events, with no paragraph plan and no style targets. It is never shown to readers.
- **The reader page** shows each reader two pairs in a shuffled order. For each passage it asks how much they enjoyed it and how much it reads like a novel from the 1800s (1 to 5), and whether they have seen it before. For each pair it asks which one a person wrote, how sure they are, and why. Answers are saved for readers with access and also given to every reader as a short answer code. The answer key is never in the page.

## 3. Austen first, and why she was dropped

The first pair used *Pride and Prejudice* chapter 32 (Darcy calls on Elizabeth at Hunsford).

- **Sampled paragraph plan (2026-11-09, $0.17):** paragraphs came out twice Austen's length (median 58 words against 29). The plan's sizes are averaged over the 21-book corpus, and Opus writes 15 to 20% over any target. Using Austen's own paragraph plan fixed this: 26 paragraphs with a median of 30 words, against her 26 and 29.
- **But both versions echoed her.** About 7% of the words in both StoryDaemon and plain Opus sat in five-word runs shared with the chapter. Opus knows this chapter.
- **Style targets made it worse (2026-11-10, $0.19).** Targets measured from the rest of the novel moved every count toward Austen. Sentences went from 12.4 to 15.2 words against her 16.2. Semicolons went from 0 to 8.8 per 1,000 words against her 10.7. Contractions dropped to none, and "seemed/felt" words fell from 7.6 to 2.2. But 20% of the words were now in eight-word runs copied from her: whole lines. Her events plus her style told it to recite.
- **The recall check (2026-11-11, $0.075)** confirmed it. Opus was given the first 50 words of four paragraphs from deep in each book and asked for the next 80 words exactly. `recall_probe.py`:

| Book | Words in true five-word runs | Longest correct run (words) |
|---|---|---|
| Austen, *Pride and Prejudice* (1813) | 92% | 80, 80, 82, 80 |
| Ferrier, *Marriage* (1818) | 1% | 5, 3, 3, 3 |
| Edgeworth, *Patronage* (1814) | 0% | 2, 2, 1, 2 |
| Oliphant, *Miss Marjoribanks* (1866) | 0% | 4, 2, 2, 2 |
| Brunton, *Self-Control* (1811) | 0% | 3, 1, 4, 4 |

A reader could also simply search a line of Austen and find the answer. So the test moved to Ferrier's *Marriage*, which Opus cannot recite.

## 4. Style targets on a scene no book contains

Before switching books, the style targets were tried on a new incident: a gentleman brings the heroine a letter that went to his aunt's house by mistake ($0.17). StoryDaemon planned its own paragraphs, and the Austen style targets were added.

| Measure | Austen's profile | Opus without targets | This scene |
|---|---|---|---|
| Mean sentence words | 18.1 | 12 to 13.5 | 18.9 |
| Sentence length spread | 15.0 | 6 to 10 | 11.6 |
| Semicolons per 1,000 words | 13.5 | 0 to 2 | 15.1 |
| Dashes per 1,000 words | 3.8 | 0 | 3.2 |
| Contractions per 1,000 words | 0.1 | 0 to 2 | 0 |
| % of words in speech | 47 | 25 to 53 | 31 (missed) |
| Words in eight-word runs found anywhere in the novel | | | 0% |

The targets carry over to fresh events without copying. They missed the speech share and the spread of sentence lengths. Two slips turned up on reading: "a new bonnet for Kitty" (an Austen name the names gauge did not catch) and "a gentleman with ten thousand a year" (Darcy's income, not in the brief). Opus still borrows from Austen's world when told to write like her.

## 5. The Ferrier pairs

Two passages from *Marriage* (1818), volume II, renamed with the generator (`mint_ferrier.py`, which leaves out any name Ferrier or Austen uses and a few with famous owners such as Emma and Harriet):

- **Pair 1:** the condolence call (chapter 13), 1,416 words, 37 paragraphs.
- **Pair 2:** the arranged match (chapter 18), 1,263 words, 16 paragraphs.

Ferrier's profile, measured from the whole book with these two chapters left out: sentences average 24.6 words (Austen 18), 31% run to 30 words or more, semicolons 16.4 and dashes 8.1 per 1,000 words, half the words in speech, and a few contractions in speech (3.8 per 1,000).

| Measure | Ferrier's targets | P1 Ferrier | P1 StoryDaemon | P1 plain Opus | P2 Ferrier | P2 StoryDaemon | P2 plain Opus |
|---|---|---|---|---|---|---|---|
| Words | | 1,448 | 1,340 | 1,284 | 1,290 | 1,144 | 1,326 |
| Paragraphs | | 37 | 37 | 48 | 16 | 16 | 27 |
| Median paragraph words | 42 | 20 | 19 | 19.5 | 59.5 | 55.5 | 45 |
| Mean sentence words | 24.6 | 15.1 | 14.4 | 9.3 | 18.7 | 20.1 | 11.7 |
| Sentence length spread | 17.9 | 12.2 | 11.7 | 7.0 | 13.3 | 12.2 | 8.4 |
| % of sentences 30+ words | 31 | 12 | 10 | 1 | 17 | 23 | 4 |
| % of words in speech | 50 | 37 | 30 | 28 | 68 | 65 | 50 |
| Semicolons per 1,000 | 16.4 | 15.2 | 23.1 | 0 | 12.4 | 19.2 | 0 |
| Dashes per 1,000 | 8.1 | 15.2 | 3.7 | 0 | 14.7 | 5.2 | 0 |
| Contractions per 1,000 | 3.8 | 1.4 | 1.5 | 0 | 7.0 | 2.6 | 0 |

What the table says:

- **StoryDaemon tracks Ferrier** on paragraphs, sentence length and speech share, passage by passage. Plain Opus does not: short sentences, no semicolons, no dashes, and about a third more paragraphs.
- **Punctuation is off in a consistent way.** StoryDaemon uses too many semicolons and too few dashes. The targets were for the whole book, and these two passages are dash-heavy scenes.
- **No copying.** No version has an eight-word run found anywhere in *Marriage*, and at most 3.7% of any version's words sit in five-word runs (unrelated text scores about 0.5%).

Cost: $0.37 for the four scenes, plus $0.09 to rewrite pair 1's StoryDaemon scene after a plan line of ours was ambiguous (it had the widow tell her visitor that *she* looked well after her loss).

## 6. One reader's answers

The project owner took the test on 2026-11-12. He reads pre-1900 novels rarely and looked nothing up.

| Pair | Picked | How sure | Enjoyment (Ferrier / StoryDaemon) | Reads like the 1800s (Ferrier / StoryDaemon) |
|---|---|---|---|---|
| 1, condolence call | Ferrier, correct | a guess | 4 / 4 | 5 / 5 |
| 2, arranged match | Ferrier, correct | certain | 5 / 5 | 5 / 5 |

His reasons:

- Pair 2: "Word choice feels more natural. There are more archaic words. The use of a French phrase too. The paragraphs seem slightly smaller too."
- Pair 1: "This one is much harder. There are a few words in A that I want to say are more human." He noted that the repetition he expected to give the human away appears in both versions. He also asked whether the style would carry over to a scene with no source behind it. Section 4 is a first answer for Austen's style: the counts carry over and nothing is copied.

One reader is not a result. It does say where to look next.

## 7. What we learned

1. **The paragraph plan and the style targets do their job for this period.** Paragraph sizes, sentence lengths, speech share and punctuation move to the author's numbers, which plain Opus never reaches by itself.
2. **Word choice is the gap.** Both the reader's reasons and our own reading point at vocabulary: period words, French phrases, the odd modern word. Nothing in StoryDaemon targets word choice yet. The plan is a free word-choice gauge first, checked on these texts, then a word list in the style targets.
3. **Choose source books Opus cannot recite.** Check with `recall_probe.py` before building pairs. Austen fails it.
4. **Style targets on a known book's own events invite recitation.** Use them on fresh events, or on a book the model does not know.
5. **Hold the targets to the scene, not just the book.** The punctuation gap came from whole-book targets on dash-heavy scenes.
6. **Thinking needs room.** With style targets in the prompt, Opus thought for 2,318 tokens on one scene and ran out of budget. The test now allows 8 times the word target in tokens (`generation.scene_budget_multiplier: 8`).

Open: whether the structure holds for other genres (the books we can use are out of copyright, so roughly before 1930), and the historical name bank, which mixes periods.

## 8. Repeating it

- **Scripts (committed):** `experiments/blind_test/write_scenes.py` (writes each arm through the real writer path, with a spend cap, and checks plan compliance, names and copying), `austen_plans.py` (drafts the one-line-per-paragraph plan with Haiku, then flags four-word echoes of the source), `recall_probe.py`.
- **Inputs (not committed, `work/blind/`):** the Project Gutenberg texts (*Pride and Prejudice* #1342, *Marriage* #12669, *Patronage* #8937, *Miss Marjoribanks* #41286, *Self-Control* #41196), the name draws (`mint.py` seed 20261110, `mint_ferrier.py` seed 20261111), the renaming script `swap_ferrier.py`, the briefs, the hand-checked paragraph plans and the style profiles. Copies are kept with the project's files outside the repository.
- **Reader page:** a private page with the answer key held separately, never in the page.

# Name banks: one genre exists, every story gets it

Status: open, unscheduled. Written 2026-09-15 after a live run.
Code: `novel_agent/tools/name_generator.py`, data in `novel_agent/data/names/`.

## What happens

Every character and place name in every StoryDaemon novel is coined from the
same science-fiction syllable bank, whatever the story's genre. A tick run on
2026-09-15 against a foundation reading

> historical adventure. The survey brig Alcyone, charting a volcanic
> archipelago in 1871, searches for the lost Meridian expedition.

produced this cast:

| id | name | role |
|---|---|---|
| C001 | Novaine Starkath | ship's cartographer and chart-keeper |
| C002 | Joren Prenoth | ship's navigator |
| L000 | Vynridge ship's deck | |
| L001 | Brenwick archipelago | |

The two place names happen to land well for a British maritime setting. The
two crew names do not. A Royal Navy survey brig in 1871 has a Hollis, a
Pemberton, a Gale; it does not have a Novaine Starkath.

## Why

This is not a broken lookup. It is a deliberate fallback that has simply
outlived the single-genre phase it was written for, and the code says so:

```python
self.scifi_data = self._load_json("scifi_syllables.json")
# Only scifi person-name banks exist today; fantasy/modern fall back to it.
self.banks = {"scifi": self.scifi_data}
```

`_normalize_genre()` already does the classifying work, mapping free text to
one of three keys:

```python
if any(k in g for k in ["fantasy", "myth", "medieval", "sword"]):
    return "fantasy"
if any(k in g for k in ["modern", "contemp", "thriller", "noir", "realis", "crime"]):
    return "modern"
return "scifi"
```

but `_bank_for_genre()` resolves every one of those keys through a dict with a
single entry:

```python
return self.banks.get(self._normalize_genre(genre), self.scifi_data)
```

So `"fantasy"` and `"modern"` are both misses and both fall through to
`scifi_data`. The classifier is live, correct, and currently has nothing to
choose between.

Note also that the three keys do not cover the corpus we are calibrating
against. "historical adventure" is not fantasy, modern, or science fiction; it
matches none of the keyword lists and reaches the scifi bank by the default
branch rather than by the fallback. Most of the 21-masterwork corpus is in the
same position.

## What exists today

```
novel_agent/data/names/
  scifi_syllables.json    first_name: {male, female} x {start, end}
                          last_name:  {start: 60, end: 50}
  place_syllables.json    start: 40, end: 30, prefixes: 10, patterns: 6
  titles.json             military: 3, civilian: 3, noble: 3, specialized: 4
```

`place_syllables.json` is genre-neutral by design (the LLM supplies the
common-noun descriptor, Python owns the proper noun), so places are less
wrong than people, but they are still coined from one sound palette.

The generator itself is sound and is not what needs changing. It coins by
syllable, dedups against existing entities within a process, and in a 3,000-
sample draw produced 1,161 distinct first names. The gap is that there is one
palette to draw them from.

## Why it matters more than it looks

Names are the most visible output of the Phase 1 grounded-identity pattern,
which is one of the project's better ideas: Python mints identity, the LLM
selects it, so a name can never be hallucinated or drift. That guarantee is
exactly what makes this gap load-bearing. The LLM cannot quietly correct a
wrong-sounding name, because it is not allowed to invent one. Whatever the
bank produces is what the reader gets, on every page, for the whole novel.

It also cuts against the goal the DSL work exists to serve. The masters
corpus is the reference for making generated prose read as human-written, and
a chapter can match the corpus on paragraph mode, paragraph length, dialogue
turns and chapter length, and still announce itself as machine-made in the
first proper noun on the page.

## What would fix it

Authoring data, not writing code. Three tasks, in order of value:

1. **A `modern` bank.** Anglophone contemporary and historical given names and
   surnames. This is the widest net: it covers the historical, literary,
   crime, and contemporary genres that most of the masters corpus sits in, and
   it is the bank whose absence produced the run above.
2. **A `fantasy` bank.** The classifier already routes to it.
3. **Widen `_normalize_genre` beyond three keys**, or replace the keyword
   lists with something that degrades more honestly. "historical adventure"
   reaching the scifi bank through a default branch is the part that is
   actually wrong, as distinct from merely unfinished.

Two decisions to make first, neither of which the code can settle:

- **Coined or drawn?** The current design coins names from syllables, which
  guarantees novelty and avoids reusing a real person's name. A historical or
  contemporary bank probably wants real given names and surnames drawn from a
  list instead, since coined-from-syllables English names read as neither
  invented nor real. That is a different generation mode, not a different
  data file, so `NameGenerator` would need a drawn-list path alongside the
  syllable path.
- **Period.** "Modern" and "1871 British" are not the same name distribution.
  A single Anglophone bank will be wrong for one of them. Whether periodized
  banks are worth it depends on how far the historical genres matter.

## How to tell it is fixed

Generate a cast against a historical foundation and read the names aloud. The
2026-09-15 run is the baseline to beat, and it is recorded above in full so
the comparison is against something specific rather than an impression.

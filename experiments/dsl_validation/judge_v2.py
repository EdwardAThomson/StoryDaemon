#!/usr/bin/env python3
"""Judge v2: score each scene alone against the house target register.

Three parts, from the plan doc's "Judge v2" section:
  register  1-5 register fit against the masters' register, with the worst
            lapse quoted and classed (fragmented | packed | exposition | none)
  craft     five 1-5 scores that reward no paragraph style: movement, voices,
            subtext, economy, grounding
  plan      skeleton scenes only: per-paragraph mode match (judge), one
            speaker per DIALOGUE item and word range per item (Python)

Start/stop/resume is built in:
  - every LLM call is cached on disk, so a re-run never re-pays a call;
  - every finished (item, part) is appended to results.jsonl at once, and a
    re-run skips what is already there;
  - --max-usd / --max-calls stop the run cleanly between calls, and Ctrl-C
    finishes the row in flight and exits; re-run the same command to resume.
  - --fake uses a canned judge (no network) to exercise all of the above.

    venv/bin/python experiments/dsl_validation/judge_v2.py --max-usd 0.10
    venv/bin/python experiments/dsl_validation/judge_v2.py --fake --max-calls 5

Items: every scene of the e1-* cells (kind = cell name), plus any .txt files
in experiments/dsl_validation/calibration/ (kind = "calibration:<stem>"),
which is where known-answer passages go.
"""

import argparse
import hashlib
import json
import os
import re
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
WORK = REPO / "work" / "dsl"
OUT = WORK / "judged" / "v2"
CACHE = OUT / "cache"
RESULTS = OUT / "results.jsonl"
USAGE = OUT / "usage.jsonl"
CALIB = HERE / "calibration"

JUDGE_MODEL = "anthropic/claude-sonnet-5.5"
LABEL_MODEL = "anthropic/claude-haiku-5.5"

sys.path.insert(0, str(REPO))
sys.path.insert(0, str(HERE))
from novel_agent.agent.scene_skeleton import MODE_GUIDE, mode_word_stats  # noqa: E402
from judge import cells, paragraphs, parse_json, scenes  # noqa: E402


# --- stop / resume -------------------------------------------------------------------

class StopRun(Exception):
    """The run stopped cleanly (budget spent or Ctrl-C). Re-run to resume."""


class Budget:
    def __init__(self, max_usd=None, max_calls=None):
        self.max_usd, self.max_calls = max_usd, max_calls
        self.usd, self.calls = 0.0, 0
        self.interrupted = False
        signal.signal(signal.SIGINT, self._sigint)

    def _sigint(self, *_):
        self.interrupted = True
        print("\n[judge] Ctrl-C: finishing the row in flight, then stopping", flush=True)

    def check(self):
        if self.interrupted:
            raise StopRun("interrupted")
        if self.max_calls is not None and self.calls >= self.max_calls:
            raise StopRun(f"call cap reached ({self.calls})")
        if self.max_usd is not None and self.usd >= self.max_usd:
            raise StopRun(f"spend cap reached (${self.usd:.3f})")

    def charge(self, cost):
        self.calls += 1
        self.usd += cost or 0.0


FAKE = {
    "register": '{"register_fit": 3, "worst_lapse_kind": "packed", "worst_lapse_quote": "fake", "reason": "fake"}',
    "craft": '{"movement": 3, "voices": 3, "subtext": 3, "economy": 3, "grounding": 3, "reason": "fake"}',
    "label": None,  # built per call
}


def call(model, prompt, budget, max_tokens=700, fake=None):
    """One cached, budgeted chat call. A cache hit costs nothing and is not
    counted; a billed call is checked against the budget first."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps([model, prompt, max_tokens]).encode()).hexdigest()
    cpath = CACHE / f"{key}.json"
    if cpath.exists():
        return json.loads(cpath.read_text())["text"]
    budget.check()
    if fake is not None:
        text, cost = fake, 0.001
        time.sleep(float(os.environ.get("FAKE_DELAY", "0.05")))
    else:
        text, cost = _transport(model, prompt, max_tokens)
    budget.charge(cost)
    with open(USAGE, "a") as f:
        f.write(json.dumps({"t": time.time(), "model": model, "cost": cost}) + "\n")
    cpath.write_text(json.dumps({"text": text}))
    return text


def _transport(model, prompt, max_tokens):
    body = json.dumps({"model": model, "max_tokens": max_tokens, "temperature": 0,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', 'x')}",
                 "Content-Type": "application/json"})
    last = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                out = json.load(r)
            return (out["choices"][0]["message"]["content"] or "",
                    (out.get("usage") or {}).get("cost") or 0.0)
        except urllib.error.HTTPError as e:
            if e.code == 402:
                raise StopRun("OpenRouter credits exhausted (402)")
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2 ** attempt)
    raise RuntimeError(f"judge call failed: {last}")


# --- prompts --------------------------------------------------------------------------

TARGET = """THE TARGET REGISTER. This scene was written to a house target: the register of the \
19th-century novel, as measured on a corpus of 21 classic novels. In that register:
- a paragraph does a full unit of work (about 35 to 60 words on average; longer for history, \
setting and reflection, shorter for speech), and white space is paragraphing, not rhythm;
- each dialogue paragraph is ONE speaker's turn, with its tag and perhaps a beat of business; \
a conversation runs as a sequence of such paragraphs, never packed into one;
- history, backstory and setting are carried inside the action and the talk, not dropped as a \
standalone block;
- the narration stays in the scene; it does not summarise what the scene could show.
You are judging how well the scene lands in THAT register. Your own taste for a modern, \
fragmented style is not the standard here."""

REGISTER_PROMPT = TARGET + """

Score the scene's REGISTER FIT on this scale:
5: reads as a page from the corpus: full paragraphs, each speech turn in its own paragraph, \
history and setting woven into the action.
4: in register with one visible lapse (one packed exchange, or one standalone exposition paragraph).
3: mixed: stretches in register, stretches that fragment into one-line beats or pack several speakers.
2: mostly out of register: modern fragmentation (one-sentence paragraphs, isolated words as beats) \
OR dense blocks that pack whole conversations.
1: no trace of the target register.

Also name the single worst lapse and quote it. Its kind is one of:
"fragmented" (paragraphs too short, beats isolated), "packed" (several speakers or exchanges in \
one paragraph), "exposition" (a standalone block of history or explanation), "none".

=== SCENE ===
{text}
=== END ===

Reply with JSON only:
{{"register_fit": <1-5>, "worst_lapse_kind": "fragmented"|"packed"|"exposition"|"none", \
"worst_lapse_quote": "<up to 25 words copied from the scene, or empty>", "reason": "<two sentences>"}}"""

CRAFT_PROMPT = """Score this scene from a novel on five craft questions, each 1 to 5. None of them \
is about paragraph length or style, so do not let paragraphing move any score.

movement:  5 = something is different by the end and the scene built to it; 1 = nothing changes, it circles.
voices:    5 = each speaker could be identified with the tags removed; 1 = everyone speaks alike.
subtext:   5 = characters mean more than they say at least once; 1 = all speech is on the nose.
economy:   5 = no padding, no repeated beat, no sentence restating the last; 1 = padded or repetitive.
grounding: 5 = concrete objects and sensory detail carry the scene; 1 = abstract summary carries it.

=== SCENE ===
{text}
=== END ===

Reply with JSON only:
{{"movement": <1-5>, "voices": <1-5>, "subtext": <1-5>, "economy": <1-5>, "grounding": <1-5>, \
"reason": "<two sentences naming the weakest and strongest>"}}"""

LABEL_PROMPT = """Label each numbered paragraph below with its single DOMINANT mode, from:
{modes}

Paragraphs:
{paras}

Reply with JSON only: {{"labels": ["<MODE for paragraph 1>", "<MODE for paragraph 2>", ...]}} \
with exactly {n} entries."""


# --- items ----------------------------------------------------------------------------

def items():
    """[(item_id, kind, text, skeleton or None)]."""
    out = []
    for name, proj in cells().items():
        if not name.startswith("e1-"):
            continue
        for sid, prose, meta in scenes(proj):
            out.append((f"{name}/{sid}", name, prose,
                        (meta.get("metadata") or {}).get("scene_skeleton")))
    if CALIB.exists():
        for p in sorted(CALIB.glob("*.txt")):
            out.append((f"calibration/{p.stem}", f"calibration:{p.stem}",
                        p.read_text().strip(), None))
    return out


def done_set():
    if not RESULTS.exists():
        return set()
    return {(r["item"], r["part"]) for r in map(json.loads, RESULTS.read_text().splitlines())}


def record(row):
    with open(RESULTS, "a") as f:
        f.write(json.dumps(row) + "\n")


# --- part 3: plan adherence -----------------------------------------------------------

_QUOTE_OPEN = re.compile(r'[“"](?=\S)')


def plan_checks(paras, skeleton, labels):
    stats = mode_word_stats()
    n = min(len(paras), len(skeleton))
    mode_ok = sum(1 for i in range(n) if labels and i < len(labels) and labels[i] == skeleton[i])
    in_range = 0
    one_turn_ok = dial = 0
    misses = []
    for i in range(n):
        mode = skeleton[i]
        words = len(paras[i].split())
        dec = (stats.get(mode) or {}).get("deciles")
        lo, hi = (dec[0], dec[-1]) if dec else (5, 250)
        if lo <= words <= hi:
            in_range += 1
        else:
            misses.append({"item": i + 1, "mode": mode, "words": words, "range": [lo, hi]})
        if mode == "DIALOGUE":
            dial += 1
            spans = len(_QUOTE_OPEN.findall(paras[i]))
            if spans <= 2:
                one_turn_ok += 1
            else:
                misses.append({"item": i + 1, "mode": mode, "quote_spans": spans})
    return {
        "plan_items": len(skeleton), "paragraphs": len(paras),
        "mode_match": round(mode_ok / n, 3) if n and labels else None,
        "word_in_range": round(in_range / n, 3) if n else None,
        "dialogue_one_turn": round(one_turn_ok / dial, 3) if dial else None,
        "dialogue_items": dial, "misses": misses[:40],
    }


# --- main -----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-usd", type=float)
    ap.add_argument("--max-calls", type=int)
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--only", help="substring filter on item id")
    ap.add_argument("--parts", default="register,craft,plan")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    budget = Budget(args.max_usd, args.max_calls)
    parts = args.parts.split(",")
    done = done_set()
    todo = [(iid, k, t, sk) for iid, k, t, sk in items() if not args.only or args.only in iid]
    print(f"[judge] {len(todo)} items, {len(done)} (item,part) rows already done", flush=True)
    try:
        for iid, kind, text, skeleton in todo:
            paras = paragraphs(text)
            if "register" in parts and (iid, "register") not in done:
                v = parse_json(call(JUDGE_MODEL, REGISTER_PROMPT.format(text=text), budget,
                                    fake=FAKE["register"] if args.fake else None)) or {}
                record({"item": iid, "kind": kind, "part": "register", **v})
                print(f"  {iid} register={v.get('register_fit')} lapse={v.get('worst_lapse_kind')}", flush=True)
            if "craft" in parts and (iid, "craft") not in done:
                v = parse_json(call(JUDGE_MODEL, CRAFT_PROMPT.format(text=text), budget,
                                    fake=FAKE["craft"] if args.fake else None)) or {}
                record({"item": iid, "kind": kind, "part": "craft", **v})
                print(f"  {iid} craft={[v.get(k) for k in ('movement','voices','subtext','economy','grounding')]}", flush=True)
            if "plan" in parts and skeleton and (iid, "plan") not in done:
                modes = "\n".join(f"- {m}: {g}" for m, g in MODE_GUIDE.items())
                numbered = "\n\n".join(f"({i+1}) {p}" for i, p in enumerate(paras))
                fake = json.dumps({"labels": list(skeleton)[:len(paras)]}) if args.fake else None
                v = parse_json(call(LABEL_MODEL, LABEL_PROMPT.format(modes=modes, paras=numbered, n=len(paras)),
                                    budget, max_tokens=1500, fake=fake)) or {}
                checks = plan_checks(paras, skeleton, v.get("labels"))
                record({"item": iid, "kind": kind, "part": "plan", **checks})
                print(f"  {iid} plan mode={checks['mode_match']} words={checks['word_in_range']} "
                      f"one_turn={checks['dialogue_one_turn']}", flush=True)
    except StopRun as e:
        print(f"[judge] stopped: {e}. {budget.calls} billed calls, ${budget.usd:.3f}. "
              f"Re-run the same command to resume.", flush=True)
        return 3
    print(f"[judge] complete. {budget.calls} billed calls this run, ${budget.usd:.3f}.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

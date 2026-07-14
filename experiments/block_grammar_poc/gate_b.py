#!/usr/bin/env python3
"""Gate B: skeleton-to-prose round-trip.

Render Gate-A skeletons to prose with a writer LLM (the skeleton rides inside
one single-shot prompt, the Slice 4 shape), then re-annotate the prose with
the SAME judge protocol the masters corpus was annotated with (DeepSeek via
OpenRouter, the analyzer repo's block rubric, batches of 20, one re-ask,
lenient parsing), and measure skeleton-in vs labels-out agreement.

This gate tests instruction-following only, not prose quality: can a writer
actually produce the block sequence it was asked for, as judged by the same
instrument that measured the masters?

Usage:
    python3 gate_b.py --fake                    # plumbing test, no network
    python3 gate_b.py --chapters 4 --seed 11    # real run (OPENROUTER_API_KEY)
    python3 gate_b.py --rescore runs/gateb-s11-c4   # recompute from artifacts

Provisional pass bar (revisit after the first real runs): paragraph-count
compliance >= 0.75 of chapters, mean label agreement >= 0.60, pooled
mode-share total-variation distance <= 0.15.

The judge rubric and lenient batch parser are imported from the analyzer
repo (stdlib-only imports) so the annotation protocol cannot drift from the
one the corpus numbers came from. Set ANALYZER_REPO if it lives elsewhere.
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYZER_REPO = os.environ.get(
    "ANALYZER_REPO",
    os.path.expanduser("~/Projects/llm_creative_writing-analyser"))
sys.path.insert(0, ANALYZER_REPO)
sys.path.insert(0, HERE)

from benchmarks.narrative_dynamics import block_rhythm          # noqa: E402
from benchmarks.narrative_dynamics.rubrics import block_types   # noqa: E402
from sampler import Grammar, Params, Sampler                    # noqa: E402

JUDGE_MODEL = "deepseek/deepseek-chat"
# Transport parameters mirror ai_helper.send_prompt_openrouter, which is what
# annotated the masters corpus: same system prompt, temperature, max_tokens.
SYSTEM_PROMPT = ("You are a helpful fiction writing assistant. "
                 "You will create original text only.")
TEMPERATURE = 0.7
MAX_TOKENS = 16384

MODE_GUIDE = {
    "SETTING": "description of place, atmosphere, weather, light, objects",
    "CHARACTER_DESC": "a character's appearance, dress, manner, bearing",
    "LORE": "history, backstory, world facts, how things came to be",
    "DIALOGUE": "dominated by quoted speech between characters",
    "ACTION": "events happening now: movement, physical or procedural activity",
    "INTERIORITY": "a character's thoughts, feelings, reasoning, judgments",
    "TRANSITION": "brief connective tissue moving time or place",
}

PREMISE = (
    "Novel premise (mid-book chapter; pick up mid-voyage, no recaps): the "
    "survey brig Alcyone, charting a volcanic archipelago in 1871, is "
    "searching for the lost Meridian expedition. Aboard: Elena Marsh, a "
    "naturalist with her missing brother's cipher notebook; Captain Reeve, "
    "who owes a debt he will not name; and Yusuf, the quartermaster, who has "
    "sailed these waters before and says little about it.")


# --- LLM transport (stdlib only) -----------------------------------------------------

def _load_env_key(name):
    if os.environ.get(name):
        return os.environ[name]
    for root in (os.path.join(HERE, "..", ".."), ANALYZER_REPO):
        path = os.path.join(root, ".env")
        if os.path.exists(path):
            for line in open(path):
                line = line.strip()
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


class OpenRouterLLM:
    """Minimal chat-completions client with retries and a disk cache."""

    def __init__(self, model, cache_dir=os.path.join(HERE, "cache")):
        self.model = model
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.key = _load_env_key("OPENROUTER_API_KEY")
        self.calls = 0

    def _cache_path(self, prompt):
        h = hashlib.sha256(json.dumps(
            [self.model, TEMPERATURE, SYSTEM_PROMPT, prompt],
            ensure_ascii=False).encode()).hexdigest()
        return os.path.join(self.cache_dir, f"{h}.json")

    def __call__(self, prompt):
        cpath = self._cache_path(prompt)
        if os.path.exists(cpath):
            return json.load(open(cpath))["text"]
        if not self.key:
            raise RuntimeError("OPENROUTER_API_KEY not found (env or .env)")
        body = json.dumps({
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": prompt}],
        }).encode()
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/chat/completions", data=body,
            headers={"Authorization": f"Bearer {self.key}",
                     "Content-Type": "application/json"})
        last = None
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    out = json.load(resp)
                text = out["choices"][0]["message"]["content"]
                self.calls += 1
                json.dump({"model": self.model, "text": text},
                          open(cpath, "w"))
                return text
            except (urllib.error.HTTPError, urllib.error.URLError,
                    TimeoutError, KeyError) as e:
                last = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"OpenRouter call failed after retries: {last}")


# --- writer ---------------------------------------------------------------------------

def writer_prompt(skeleton, chapter_no):
    lines = [f"{i+1}. {m}: {MODE_GUIDE[m]}" for i, m in enumerate(skeleton)]
    return f"""{PREMISE}

Write chapter {chapter_no} of this novel following the paragraph plan below
EXACTLY. The plan lists {len(skeleton)} paragraphs; each numbered item names
the single dominant mode that paragraph must have.

Paragraph plan:
{chr(10).join(lines)}

Hard rules:
- Output exactly {len(skeleton)} paragraphs, separated by single blank lines.
- Begin every paragraph with its plan number in square brackets and a space,
  e.g. "[7] ", then the prose. Every plan item appears exactly once, in
  order. The markers are removed mechanically afterwards; never refer to
  them in the prose.
- No headings, no commentary: marked prose paragraphs only.
- One plan item = one paragraph. Never split an item into several paragraphs;
  a DIALOGUE paragraph may hold several exchanges of quoted speech inside one
  paragraph.
- Each paragraph should be roughly 50-130 words.
- A paragraph's dominant mode must match its plan item (e.g. a DIALOGUE
  paragraph is mostly quoted speech; an ACTION paragraph narrates events
  happening now; INTERIORITY stays inside a character's head).
- Do not compress, summarize, or wrap the story up early: all
  {len(skeleton)} items, one paragraph each, even if the chapter ends
  mid-situation.
- Continue the story continuously across paragraphs; the plan is structure,
  not scene breaks."""


_MARKER = re.compile(r"\[(\d+)\]\s*")


def split_paragraphs(text):
    """Split writer output on [n] markers; fall back to blank-line splitting.

    Returns (numbers, paragraphs): parallel lists, numbers[i] is the plan
    item the writer claimed for paragraphs[i] (None when unmarked).
    """
    marks = list(_MARKER.finditer(text))
    if marks:
        nums, paras = [], []
        for m, nxt in zip(marks, marks[1:] + [None]):
            chunk = text[m.end(): nxt.start() if nxt else len(text)].strip()
            if chunk:
                nums.append(int(m.group(1)))
                paras.append(chunk)
        return nums, paras
    paras = [p.strip() for p in re.split(r"\n\s*\n", text.strip())
             if p.strip()]
    return [None] * len(paras), paras


# --- judge (corpus protocol) -----------------------------------------------------------

def judge_labels(paragraphs, llm):
    """Batches of 20, one re-ask, lenient parse: the corpus protocol.

    _parse_batch raises on a totally unusable response (the analyzer's
    ask_json catches that and re-asks once); we mirror that here, and a batch
    that fails both attempts becomes a hole (all-None), never a hard failure.
    """
    labels = []
    for start in range(0, len(paragraphs), block_rhythm.BATCH_SIZE):
        batch = paragraphs[start:start + block_rhythm.BATCH_SIZE]
        prompt = block_types.render_annotation_prompt(batch)
        parsed = None
        for retry_pad in ("", "\n"):
            try:
                parsed = block_rhythm._parse_batch(llm(prompt + retry_pad),
                                                   len(batch))
                break
            except ValueError:
                continue
        labels.extend(parsed if parsed is not None else [None] * len(batch))
    return [(x or {}).get("primary") for x in labels]


# --- fakes (plumbing test, no network) --------------------------------------------------

FAKE_PARA = {
    "SETTING": "The bay lay grey under a low sky, ash drifting on the water.",
    "CHARACTER_DESC": "Reeve was a spare, weathered man with careful eyes.",
    "LORE": "Years before, the Meridian had vanished beyond these reefs.",
    "DIALOGUE": '"We hold course," said Reeve. "Until dark," Elena answered.',
    "ACTION": "They hauled the boat over the shingle and ran for the treeline.",
    "INTERIORITY": "Elena wondered, not for the first time, what Yusuf knew.",
    "TRANSITION": "Three days later they raised the second island.",
}
_FAKE_KEYS = {"SETTING": "grey under", "CHARACTER_DESC": "weathered",
              "LORE": "Years before", "DIALOGUE": '"', "ACTION": "hauled",
              "INTERIORITY": "wondered", "TRANSITION": "days later"}


class FakeLLM:
    def __init__(self, noise_every=0):
        self.noise_every = noise_every
        self.n = 0

    def __call__(self, prompt):
        if "Paragraph plan:" in prompt:      # writer
            modes = re.findall(r"^\d+\. ([A-Z_]+):", prompt, re.M)
            return "\n\n".join(f"[{i+1}] {FAKE_PARA[m]}"
                               for i, m in enumerate(modes))
        # judge: classify the [n]-numbered paragraphs by keyword
        paras = re.findall(r"^\[\d+\] (.+)$", prompt, re.M)
        out = []
        for i, p in enumerate(paras):
            lab = next((m for m, k in _FAKE_KEYS.items() if k in p), "ACTION")
            self.n += 1
            if self.noise_every and self.n % self.noise_every == 0:
                lab = "SETTING"
            out.append({"n": i + 1, "primary": lab, "secondary": None})
        return json.dumps(out)


# --- scoring ---------------------------------------------------------------------------

def score_chapter(skeleton, numbers, judged):
    """Score one round-trip.

    Marker alignment is primary: a paragraph marked [n] is compared with
    skeleton item n. Sequence agreement (order-preserving matching over the
    label sequences) is kept as a secondary, marker-independent view.
    """
    N = len(skeleton)
    m = difflib.SequenceMatcher(a=skeleton, b=judged, autojunk=False)
    matched = sum(b.size for b in m.get_matching_blocks())
    seq_agreement = matched / max(N, len(judged))

    by_n = Counter(n for n in numbers if n is not None)
    valid = {n for n, c in by_n.items() if c == 1 and 1 <= n <= N}
    coverage = len(valid) / N
    hits, judged_n, confusion = 0, 0, Counter()
    for n, lab in zip(numbers, judged):
        if n in valid and lab is not None:
            judged_n += 1
            if lab == skeleton[n - 1]:
                hits += 1
            else:
                confusion[(skeleton[n - 1], lab)] += 1
    marker_agreement = hits / judged_n if judged_n else 0.0

    return {
        "n_blocks": N,
        "n_paragraphs": len(judged),
        "count_compliant": len(judged) == N and coverage == 1.0,
        "marker_coverage": round(coverage, 3),
        "agreement": round(marker_agreement, 3),
        "seq_agreement": round(seq_agreement, 3),
        "n_unlabeled": sum(1 for x in judged if x is None),
        "confusion": {f"{a}->{b}": n for (a, b), n in confusion.most_common()},
    }


def mode_share_tv(skeletons, judgeds):
    modes = list(MODE_GUIDE)
    a = Counter(m for s in skeletons for m in s)
    b = Counter(m for j in judgeds for m in j if m)
    ta, tb = sum(a.values()), sum(b.values())
    return 0.5 * sum(abs(a[m] / ta - b[m] / tb) for m in modes)


# --- driver ----------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chapters", type=int, default=4)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--max-blocks", type=int, default=40,
                    help="resample skeletons longer than this (writer context)")
    ap.add_argument("--writer-model", default=JUDGE_MODEL)
    ap.add_argument("--fake", action="store_true")
    ap.add_argument("--rescore", metavar="RUN_DIR")
    args = ap.parse_args()

    if args.rescore:
        chapters = [json.load(open(os.path.join(args.rescore, f)))
                    for f in sorted(os.listdir(args.rescore))
                    if f.startswith("chapter_")]
        report(chapters, args.rescore)
        return

    tag = "fake" if args.fake else f"s{args.seed}-c{args.chapters}"
    run_dir = os.path.join(HERE, "runs", f"gateb-{tag}")
    os.makedirs(run_dir, exist_ok=True)

    sampler = Sampler(Grammar(os.path.join(HERE, "grammar_reference.json")),
                      Params(), seed=args.seed)
    skeletons = []
    while len(skeletons) < args.chapters:
        sk = sampler.chapter()
        if len(sk) <= args.max_blocks:
            skeletons.append(sk)

    writer = FakeLLM() if args.fake else OpenRouterLLM(args.writer_model)
    judge = writer if args.fake else OpenRouterLLM(JUDGE_MODEL)

    chapters = []
    for i, sk in enumerate(skeletons):
        prose = writer(writer_prompt(sk, chapter_no=i + 2))
        numbers, paras = split_paragraphs(prose)
        judged = judge_labels(paras, judge)
        rec = {"skeleton": sk, "prose": prose, "numbers": numbers,
               "paragraphs": paras, "judged": judged,
               "metrics": score_chapter(sk, numbers, judged)}
        chapters.append(rec)
        json.dump(rec, open(os.path.join(run_dir, f"chapter_{i}.json"), "w"),
                  indent=1)
        print(f"chapter {i}: {rec['metrics']['n_blocks']} blocks -> "
              f"{rec['metrics']['n_paragraphs']} paragraphs, "
              f"coverage {rec['metrics']['marker_coverage']}, "
              f"agreement {rec['metrics']['agreement']}")
    report(chapters, run_dir)


def report(chapters, run_dir):
    ms = [c["metrics"] for c in chapters]
    compliance = sum(m["count_compliant"] for m in ms) / len(ms)
    agreement = sum(m["agreement"] for m in ms) / len(ms)
    tv = mode_share_tv([c["skeleton"] for c in chapters],
                       [c["judged"] for c in chapters])
    confusion = Counter()
    for m in ms:
        for k, n in m["confusion"].items():
            confusion[k] += n

    checks = [
        ("count compliance", compliance, 0.75, ">="),
        ("mean label agreement", agreement, 0.60, ">="),
        ("mode-share TV", tv, 0.15, "<="),
    ]
    print(f"\nGate B scorecard ({len(chapters)} chapters) -> {run_dir}")
    ok_all = True
    for name, val, bar, op in checks:
        ok = val >= bar if op == ">=" else val <= bar
        ok_all &= ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {val:.3f} "
              f"(bar {op} {bar})")
    if confusion:
        print("top confusions (skeleton -> judged):",
              ", ".join(f"{k} x{n}" for k, n in confusion.most_common(5)))
    summary = {"compliance": compliance, "agreement": agreement,
               "mode_share_tv": tv,
               "confusion": dict(confusion.most_common())}
    json.dump(summary, open(os.path.join(run_dir, "summary.json"), "w"),
              indent=1)
    print("ALL CHECKS PASS" if ok_all else "GATE NOT PASSED")
    sys.exit(0 if ok_all else 1)


if __name__ == "__main__":
    main()

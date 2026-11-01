#!/usr/bin/env python3
"""Judge the DSL validation cells with shared, cross-family judges.

Three passes, each cached under work/dsl/judged/ so a re-run is free:

  tension   every scene re-scored by ONE fixed model with StoryDaemon's own
            anchored rubric (TENSION_RUBRIC_PROMPT), so arms are compared on
            the same yardstick instead of each writer scoring itself.
  pairwise  matched scenes (same writer, premise and tick; arm A vs arm B)
            judged blind by a model from a different family than the writers,
            in BOTH orders to cancel position bias.
  seams     for sectioned scenes, the ~300 words either side of every section
            boundary; control windows come from single-shot scenes at the same
            paragraph index. The judge does not know which is which.

    venv/bin/python experiments/dsl_validation/judge.py tension pairwise seams
"""

import glob
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / "work" / "dsl"
OUT = WORK / "judged"
CACHE = OUT / "cache"
TENSION_MODEL = "anthropic/claude-haiku-5.5"
PAIR_MODEL = "anthropic/claude-sonnet-5.5"

sys.path.insert(0, str(REPO))


# --- transport ------------------------------------------------------------------------

def call(model, prompt, max_tokens=600, system=None):
    """One cached chat call. Cost is appended to judged/usage.jsonl."""
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps([model, system, prompt, max_tokens]).encode()).hexdigest()
    cpath = CACHE / f"{key}.json"
    if cpath.exists():
        return json.loads(cpath.read_text())["text"]
    msgs = ([{"role": "system", "content": system}] if system else []) + \
        [{"role": "user", "content": prompt}]
    body = json.dumps({"model": model, "max_tokens": max_tokens,
                       "temperature": 0, "messages": msgs}).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', 'x')}",
                 "Content-Type": "application/json"})
    last = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                out = json.load(r)
            text = out["choices"][0]["message"]["content"] or ""
            with open(OUT / "usage.jsonl", "a") as f:
                f.write(json.dumps({"model": model, "cost": (out.get("usage") or {}).get("cost")}) + "\n")
            cpath.write_text(json.dumps({"text": text}))
            return text
        except urllib.error.HTTPError as e:
            if e.code == 402:
                raise SystemExit("OpenRouter credits exhausted (402)")
            last = e
        except Exception as e:  # noqa: BLE001
            last = e
        time.sleep(2 ** attempt)
    raise RuntimeError(f"judge call failed: {last}")


def parse_json(text):
    """First JSON object in the text (a judge sometimes adds a second)."""
    i = (text or "").find("{")
    if i < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(text[i:])[0]
    except ValueError:
        return None


# --- corpus ---------------------------------------------------------------------------

def cells():
    """{cell_name: project_dir} for every campaign project."""
    out = {}
    for p in sorted(WORK.glob("e[123]-*_*")):
        if (p / "state.json").exists():
            out[p.name.rsplit("_", 1)[0]] = p
    return out


def scenes(project):
    """[(scene_id, prose, metadata_json)] in tick order."""
    res = []
    for meta_path in sorted((project / "memory" / "scenes").glob("S*.json")):
        meta = json.loads(meta_path.read_text())
        md = project / meta.get("markdown_file", f"scenes/scene_{meta['tick']:03d}.md")
        if not md.exists():
            md = project / "scenes" / f"scene_{meta['tick']:03d}.md"
        prose = md.read_text().split("\n---\n", 1)[-1].strip()
        res.append((meta["id"], prose, meta))
    return res


def paragraphs(prose):
    return [p.strip() for p in re.split(r"\n\s*\n", prose) if p.strip()]


# --- tension --------------------------------------------------------------------------

def run_tension():
    from novel_agent.agent.tension_evaluator import TensionEvaluator

    class Judge:
        def generate(self, prompt, max_tokens=200, **kw):
            return call(TENSION_MODEL, prompt, max_tokens=max(max_tokens, 300))

    ev = TensionEvaluator({"generation": {}, "tension": {}}, llm_interface=Judge())
    results = {}
    for name, proj in cells().items():
        metrics = {}
        mpath = proj / "memory" / "metrics.jsonl"
        if mpath.exists():
            for line in mpath.read_text().splitlines():
                r = json.loads(line)
                metrics[r.get("scene_id")] = r
        rows = []
        for sid, prose, meta in scenes(proj):
            r = ev.evaluate_tension(prose)
            m = metrics.get(sid, {})
            rows.append({"scene": sid, "tick": meta["tick"], "shared": r.get("tension_level"),
                         "self": meta.get("tension_level"), "target": m.get("target_tension"),
                         "rewritten": m.get("tension_rewritten"), "pre": m.get("tension_pre_rewrite")})
        results[name] = rows
        print(f"tension {name}: {[x['shared'] for x in rows]}", flush=True)
    (OUT / "tension.json").write_text(json.dumps(results, indent=1))


# --- pairwise -------------------------------------------------------------------------

PAIR_PROMPT = """You are judging two scenes from two different drafts of the same novel. Both were written from the same premise at the same point in the story, but the drafts have diverged, so judge each scene as a piece of fiction in its own right. Do not reward length for its own sake.

Premise: {premise}

Judge on: prose quality (precision, rhythm, freshness, no padding), scene craft (a clear dramatic movement, a scene that changes something), dialogue (distinct voices, subtext), and how well paragraphing serves the reading.

=== SCENE A ===
{a}

=== SCENE B ===
{b}

Reply with JSON only: {{"winner": "A" or "B" or "tie", "margin": "slight" or "clear" or "strong", "reason": "<two sentences>"}}"""


def premise_of(proj):
    st = json.loads((proj / "state.json").read_text())
    return (st.get("story_foundation") or st.get("foundation") or {}).get("premise", "")


PROSE_ONLY_PROMPT = PAIR_PROMPT.replace(
    ", and how well paragraphing serves the reading", "").replace(
    "Do not reward length for its own sake.",
    "Do not reward length for its own sake. Both scenes have been mechanically "
    "re-paragraphed into equal groups of sentences, so ignore paragraphing entirely.")


def reflow(prose, per=4):
    """Re-paragraph into fixed groups of sentences, so a judge cannot see the
    original paragraphing (the register control)."""
    flat = " ".join(paragraphs(prose))
    sents = re.split(r'(?:(?<=[.!?])|(?<=[.!?][\u201d"\']))\s+(?=[\u201c"A-Z])', flat)
    return "\n\n".join(" ".join(sents[i:i + per]) for i in range(0, len(sents), per))


def run_pairwise(exp, arm_a, arm_b, prose_only=False):
    """arm_a vs arm_b over every matched (writer, premise, tick)."""
    cs = cells()
    out = []
    for name, proj in cs.items():
        if not (name.startswith(f"{exp}-") and name.endswith(f"-{arm_a}")):
            continue
        twin = name[: -len(arm_a)] + arm_b
        if twin not in cs:
            continue
        sa = {m["tick"]: p for _, p, m in scenes(proj)}
        sb = {m["tick"]: p for _, p, m in scenes(cs[twin])}
        premise = premise_of(proj)
        for tick in sorted(set(sa) & set(sb)):
            votes = []
            for first, second, order in ((sa[tick], sb[tick], "ab"), (sb[tick], sa[tick], "ba")):
                if prose_only:
                    v = parse_json(call(PAIR_MODEL, PROSE_ONLY_PROMPT.format(
                        premise=premise, a=reflow(first), b=reflow(second))))
                else:
                    v = parse_json(call(PAIR_MODEL, PAIR_PROMPT.format(premise=premise, a=first, b=second)))
                w = (v or {}).get("winner")
                if order == "ba" and w in ("A", "B"):
                    w = "B" if w == "A" else "A"
                votes.append({"winner": {"A": arm_a, "B": arm_b}.get(w, "tie"),
                              "margin": (v or {}).get("margin"), "reason": (v or {}).get("reason")})
            out.append({"cell": name[: -len(arm_a) - 1], "tick": tick, "votes": votes})
            print(f"pair {name} t{tick}: {[x['winner'] for x in votes]}", flush=True)
    (OUT / f"pairwise_{exp}{'_prose' if prose_only else ''}.json").write_text(json.dumps(out, indent=1))


# --- seams ----------------------------------------------------------------------------

SEAM_PROMPT = """Below is a short passage from a novel. It may or may not have been written in more than one sitting, with a join somewhere inside it. Read it closely for continuity: voice, tense, point of view, what each character knows, repeated or contradicted details, a reset in rhythm, or a paragraph that restarts rather than continues.

=== PASSAGE ===
{text}
=== END ===

Reply with JSON only: {{"continuity": <1-5, 5 = reads as one continuous piece>, "join_detected": true or false, "after_paragraph": <number of the paragraph a join follows, or null>, "evidence": "<one sentence>"}}"""


def window(paras, boundary, words=300):
    """Paragraphs either side of `boundary` (index of the first paragraph
    after the join), about `words` each way, numbered."""
    before, n = [], 0
    for p in reversed(paras[:boundary]):
        before.insert(0, p); n += len(p.split())
        if n >= words:
            break
    after, n = [], 0
    for p in paras[boundary:]:
        after.append(p); n += len(p.split())
        if n >= words:
            break
    chunk = before + after
    return "\n\n".join(f"({i+1}) {p}" for i, p in enumerate(chunk)), len(before)


def run_seams():
    cs = cells()
    out = []
    rng = random.Random(7)
    for name, proj in cs.items():
        if not (name.startswith("e2-") and name.endswith("-sect")):
            continue
        control = cs.get(name[: -len("sect")] + "single")
        ctrl_scenes = {m["tick"]: paragraphs(p) for _, p, m in scenes(control)} if control else {}
        for sid, prose, meta in scenes(proj):
            md = meta.get("metadata", {})
            paras = paragraphs(prose)
            if not md.get("sectioned"):
                out.append({"cell": name, "scene": sid, "kind": "fallback"})
                continue
            for start, _end in md.get("section_bounds", [])[1:]:
                for kind, ps in (("seam", paras), ("control", ctrl_scenes.get(meta["tick"]))):
                    if not ps or start >= len(ps):
                        continue
                    text, join_after = window(ps, start)
                    v = parse_json(call(PAIR_MODEL, SEAM_PROMPT.format(text=text), max_tokens=300)) or {}
                    out.append({"cell": name, "scene": sid, "kind": kind, "boundary": start,
                                "true_join_after": join_after if kind == "seam" else None, **v})
            print(f"seams {name} {sid}", flush=True)
    (OUT / "seams.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for step in sys.argv[1:]:
        if step == "tension":
            run_tension()
        elif step == "pairwise":
            run_pairwise("e1", "on", "off")
            run_pairwise("e2", "sect", "single")
            # e3 is judged on beats and contracts, not prose preference.
        elif step == "prose":
            run_pairwise("e1", "on", "off", prose_only=True)
        elif step == "seams":
            run_seams()

#!/usr/bin/env python3
"""Aggregate the DSL validation cells into one JSON + printed tables.

Reads every work/dsl/e*-* project plus the judge outputs in work/dsl/judged/
and writes work/dsl/judged/summary.json. LLM-free except the optional
premise-event gauge (`--premise`), which asks the pairwise judge model one
yes/no question per cell over the scene summaries.
"""

import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from judge import OUT, PAIR_MODEL, call, cells, paragraphs, parse_json, scenes  # noqa: E402

PREMISE_EVENT = {
    "alcyone": "the crew finds physical evidence of the lost Meridian expedition (wreckage, remains, a camp, a record or a survivor)",
    "orehauler": "the captain is found murdered",
}


def mean(xs):
    xs = [x for x in xs if x is not None]
    return round(st.mean(xs), 2) if xs else None


def usage(proj):
    p = proj / "usage.jsonl"
    rows = [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
    return rows


def cell_summary(name, proj, tension):
    sc = scenes(proj)
    us = usage(proj)
    cost = sum(r.get("cost") or 0 for r in us)
    words = [m.get("word_count") for _, _, m in sc]
    paras = [len(paragraphs(p)) for _, p, _ in sc]
    md = [m.get("metadata", {}) for _, _, m in sc]
    comp = [x.get("skeleton_compliance", {}).get("compliant") for x in md if x.get("skeleton_compliance")]
    tr = tension.get(name, [])
    metrics = []
    mp = proj / "memory" / "metrics.jsonl"
    if mp.exists():
        metrics = [json.loads(line) for line in mp.read_text().splitlines()]
    out = {
        "scenes": len(sc),
        "cost": round(cost, 4),
        "cost_per_scene": round(cost / len(sc), 4) if sc else None,
        "calls": len(us),
        "length_cutoffs": sum(1 for r in us if r.get("finish") == "length"),
        "words_mean": mean(words),
        "paragraphs_mean": mean(paras),
        "words_per_para": round(sum(w or 0 for w in words) / sum(paras), 1) if sum(paras) else None,
        "skeleton_scenes": len(comp),
        "compliant": sum(1 for c in comp if c),
        "sectioned": sum(1 for x in md if x.get("sectioned")),
        "trimmed": sum(1 for x in md if x.get("trimmed")),
        "segments_mean": mean([x.get("segments_used") for x in md]),
        "tension_self_mean": mean([r["self"] for r in tr]),
        "tension_shared_mean": mean([r["shared"] for r in tr]),
        "tension_target_mean": mean([r["target"] for r in tr]),
        "tension_shared_dist": mean([abs(r["shared"] - r["target"]) for r in tr
                                     if r["shared"] is not None and r["target"] is not None]),
        "rewrites": sum(1 for m in metrics if m.get("tension_rewritten")),
        "rewrite_ticks": [{"tick": m["tick"], "pre": m.get("tension_pre_rewrite"),
                           "post": m.get("tension_level"), "target": m.get("target_tension")}
                          for m in metrics if m.get("tension_rewritten")],
    }
    return out


def beats_summary(proj):
    p = proj / "plot_outline.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    beats = data.get("beats", data if isinstance(data, list) else [])
    status = Counter(b.get("status") for b in beats)
    checked = failed = 0
    per_checker = defaultdict(lambda: [0, 0])
    attempts = []
    for b in beats:
        res = b.get("contract_results") or []
        if isinstance(res, dict):
            res = res.get("results") or res.get("postconditions") or []
        for r in res:
            ok = r.get("passed", r.get("ok"))
            kind = r.get("check") or r.get("type") or (r.get("condition") or {}).get("check") or "?"
            checked += 1
            per_checker[kind][0] += 1
            if not ok:
                failed += 1
                per_checker[kind][1] += 1
        attempts.append(b.get("attempts") or b.get("verification_attempts") or 0)
    metrics = []
    mp = proj / "memory" / "metrics.jsonl"
    if mp.exists():
        metrics = [json.loads(line) for line in mp.read_text().splitlines()]
    return {
        "beats": len(beats), "status": dict(status),
        "methods": dict(Counter(b.get("verification_method") for b in beats if b.get("status") == "completed")),
        "postconditions_checked": checked, "postconditions_failed": failed,
        "per_checker": {k: {"checked": v[0], "failed": v[1]} for k, v in per_checker.items()},
        "tick_contract_checked": sum(m.get("contract_conditions_checked") or 0 for m in metrics),
        "tick_contract_failed": sum(m.get("contract_conditions_failed") or 0 for m in metrics),
    }


def premise_gauge(name, proj):
    foundation = "alcyone" if "alcyone" in name else "orehauler"
    lines = [f"Scene {m['tick']}: {m.get('summary') or ''} Key events: {'; '.join(m.get('key_events') or [])}"
             for _, _, m in scenes(proj)]
    prompt = (f"Below are summaries of the scenes of a novel, in order.\n\n" + "\n".join(lines) +
              f"\n\nQuestion: does this event actually happen on the page in any scene: {PREMISE_EVENT[foundation]}? "
              "It must be staged as happening, not merely feared, suspected or discussed.\n"
              'Reply with JSON only: {"happened": true or false, "first_scene": <number or null>, "evidence": "<one sentence>"}')
    return parse_json(call(PAIR_MODEL, prompt, max_tokens=300))


def main():
    tension = {}
    tp = OUT / "tension.json"
    if tp.exists():
        tension = json.loads(tp.read_text())
    summary = {}
    for name, proj in cells().items():
        s = cell_summary(name, proj, tension)
        b = beats_summary(proj)
        if b:
            s["beats"] = b
        if "--premise" in sys.argv:
            s["premise_event"] = premise_gauge(name, proj)
        summary[name] = s
    pw = {}
    for exp in ("e1", "e2", "e3"):
        p = OUT / f"pairwise_{exp}.json"
        if p.exists():
            rows = json.loads(p.read_text())
            per = defaultdict(Counter)
            for r in rows:
                for v in r["votes"]:
                    per[r["cell"]][v["winner"]] += 1
                    per["ALL"][v["winner"]] += 1
                    per[r["cell"].split("-")[1]][v["winner"]] += 1
                agree = Counter(v["winner"] for v in r["votes"])
                per["consistent_pairs"]["yes" if len(agree) == 1 else "no"] += 1
            pw[exp] = {k: dict(v) for k, v in per.items()}
    sp = OUT / "seams.json"
    seams = None
    if sp.exists():
        rows = json.loads(sp.read_text())
        seams = {}
        for kind in ("seam", "control"):
            rs = [r for r in rows if r.get("kind") == kind]
            seams[kind] = {
                "n": len(rs),
                "continuity_mean": mean([r.get("continuity") for r in rs]),
                "join_detected": sum(1 for r in rs if r.get("join_detected")),
                "join_located": sum(1 for r in rs if kind == "seam" and r.get("join_detected")
                                    and r.get("after_paragraph") == r.get("true_join_after")),
            }
        seams["fallback_scenes"] = sum(1 for r in rows if r.get("kind") == "fallback")
    usage_j = OUT / "usage.jsonl"
    judge_cost = sum((json.loads(line).get("cost") or 0) for line in usage_j.read_text().splitlines()) if usage_j.exists() else 0
    result = {"cells": summary, "pairwise": pw, "seams": seams,
              "writer_cost": round(sum(s["cost"] for s in summary.values()), 3),
              "judge_cost": round(judge_cost, 3)}
    (OUT / "summary.json").write_text(json.dumps(result, indent=1))
    keys = ["scenes", "cost", "cost_per_scene", "words_mean", "paragraphs_mean", "words_per_para",
            "compliant", "skeleton_scenes", "sectioned", "trimmed", "tension_shared_mean",
            "tension_self_mean", "tension_target_mean", "tension_shared_dist", "rewrites"]
    print("cell".ljust(30) + " ".join(k[:9].rjust(9) for k in keys))
    for n, s in summary.items():
        print(n.ljust(30) + " ".join(str(s.get(k)).rjust(9) for k in keys))
    print(json.dumps({"pairwise": pw, "seams": seams, "writer_cost": result["writer_cost"],
                      "judge_cost": result["judge_cost"]}, indent=1))


if __name__ == "__main__":
    main()

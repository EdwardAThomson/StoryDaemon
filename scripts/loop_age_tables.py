#!/usr/bin/env python3
"""Loop-aging corpus baseline (Phase 3, loop-aging Slice L1).

Walks the novels under ``work/novels/`` read-only and prints the tables that
docs/LOOP_AGING_BASELINE.md records: closure rate, age at close, age of the
loops left unresolved, and the horizon mix from the deterministic classifier in
``novel_agent/agent/loop_aging.py``. The precedent is
``scripts/block_grammar_tables.py`` plus docs/MASTERS_BLOCK_GRAMMAR_STUDY.md:
the numbers that justify a pressure live in a doc, and the script that produced
them ships beside it so they can be recomputed after any run.

Nothing here writes to a project. Usage:

    venv/bin/python scripts/loop_age_tables.py
    venv/bin/python scripts/loop_age_tables.py --root work/novels --json
    venv/bin/python scripts/loop_age_tables.py --sample 60 --seed 7
"""

import argparse
import json
import random
import re
import sys
from pathlib import Path
from statistics import median
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from novel_agent.agent.loop_aging import (  # noqa: E402
    HORIZONS,
    classify_horizon,
)

_SCENE_ID = re.compile(r"^S(\d+)$")


def _tick(scene_id: Any) -> Optional[int]:
    match = _SCENE_ID.match((scene_id or "").strip() if isinstance(scene_id, str) else "")
    return int(match.group(1)) if match else None


def load_corpus(root: Path) -> List[Dict[str, Any]]:
    """One record per novel: its loops, its last tick, and its name."""
    novels = []
    for loops_file in sorted(root.glob("*/memory/open_loops.json")):
        project = loops_file.parent.parent
        try:
            loops = json.loads(loops_file.read_text(encoding="utf-8")).get("loops", [])
        except (json.JSONDecodeError, ValueError, OSError):
            continue
        if not loops:
            continue
        last_tick = None
        state_file = project / "state.json"
        if state_file.exists():
            try:
                last_tick = json.loads(state_file.read_text(encoding="utf-8")).get("current_tick")
            except (json.JSONDecodeError, ValueError, OSError):
                last_tick = None
        novels.append({"name": project.name, "last_tick": last_tick, "loops": loops})
    return novels


def summarise(novels: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The corpus-level numbers, plus one row per novel."""
    rows = []
    closed_ages: List[int] = []
    unresolved_ages: List[int] = []
    horizon_counts = {h: 0 for h in HORIZONS}
    horizon_closed = {h: 0 for h in HORIZONS}
    total = 0
    mentioned = 0

    for novel in novels:
        last = (novel["last_tick"] or 1) - 1
        novel_closed: List[int] = []
        novel_open: List[int] = []
        for loop in novel["loops"]:
            total += 1
            if loop.get("scenes_mentioned"):
                mentioned += 1
            horizon = loop.get("horizon") or classify_horizon(loop.get("description"))
            if horizon in horizon_counts:
                horizon_counts[horizon] += 1
            born = loop.get("created_tick")
            if not isinstance(born, int):
                born = _tick(loop.get("created_in_scene"))
            if born is None:
                continue
            status = loop.get("status") or "open"
            if status == "resolved":
                died = _tick(loop.get("resolved_in_scene"))
                if died is not None:
                    novel_closed.append(max(died - born, 0))
                    if horizon in horizon_closed:
                        horizon_closed[horizon] += 1
            elif status in ("open", "expired"):
                novel_open.append(max(last - born, 0))
        closed_ages.extend(novel_closed)
        unresolved_ages.extend(novel_open)
        rows.append({
            "novel": novel["name"],
            "ticks": (novel["last_tick"] or 0),
            "loops": len(novel["loops"]),
            "closed": len(novel_closed),
            "unresolved": len(novel_open),
            "median_age_at_close": median(novel_closed) if novel_closed else None,
            "median_age_unresolved": median(novel_open) if novel_open else None,
        })

    within = {n: sum(1 for a in closed_ages if a <= n) for n in (1, 2, 3)}
    return {
        "novels": len(novels),
        "loops_total": total,
        "loops_with_a_mention_count": mentioned,
        "closed_total": len(closed_ages),
        "closed_median_age": median(closed_ages) if closed_ages else None,
        "closed_max_age": max(closed_ages) if closed_ages else None,
        "closed_within": within,
        "unresolved_total": len(unresolved_ages),
        "unresolved_median_age": median(unresolved_ages) if unresolved_ages else None,
        "unresolved_max_age": max(unresolved_ages) if unresolved_ages else None,
        "unresolved_15_plus": sum(1 for a in unresolved_ages if a >= 15),
        "horizon_counts": horizon_counts,
        "horizon_closed": horizon_closed,
        "rows": rows,
    }


def sample_for_labelling(novels: List[Dict[str, Any]], size: int, seed: int) -> List[Dict[str, Any]]:
    """A stratified sample of loops with the classifier's verdict, for hand-labelling.

    The classifier is cheap and deterministic, which is exactly why its accuracy
    has to be published rather than assumed: the project has twice replaced a
    crude gauge (keyword tension, embedding goal-relevance) with an anchored
    judge. Stratified by the classifier's own verdict so the rare horizons are
    represented.
    """
    pool = []
    for novel in novels:
        for loop in novel["loops"]:
            description = loop.get("description") or ""
            if description:
                pool.append({
                    "novel": novel["name"],
                    "id": loop.get("id"),
                    "description": description,
                    "classified": classify_horizon(description),
                })
    rng = random.Random(seed)
    per = max(1, size // len(HORIZONS))
    sample: List[Dict[str, Any]] = []
    for horizon in HORIZONS:
        bucket = [p for p in pool if p["classified"] == horizon]
        rng.shuffle(bucket)
        sample.extend(bucket[:per])
    rng.shuffle(sample)
    return sample


def print_tables(summary: Dict[str, Any]):
    print(f"Novels: {summary['novels']}   loops: {summary['loops_total']}")
    print(f"Loops whose scenes_mentioned is non-zero: {summary['loops_with_a_mention_count']}"
          "   (the field is never written; 0 is the expected answer)")
    print()
    header = (f"{'novel':28} {'ticks':>5} {'loops':>5} {'closed':>6} {'unres':>5} "
              f"{'med age close':>13} {'med age unres':>13}")
    print(header)
    print("-" * len(header))
    for row in summary["rows"]:
        print(f"{row['novel']:28} {row['ticks']:5} {row['loops']:5} {row['closed']:6} "
              f"{row['unresolved']:5} {str(row['median_age_at_close']):>13} "
              f"{str(row['median_age_unresolved']):>13}")
    print()
    closed = summary["closed_total"]
    total = summary["loops_total"]
    print(f"Ever closed: {closed}/{total} ({100 * closed / max(total, 1):.0f}%)"
          f"   median age at close {summary['closed_median_age']}"
          f"   max {summary['closed_max_age']}")
    for n, count in sorted(summary["closed_within"].items()):
        print(f"   closed within {n} tick(s): {count} of {closed}"
              f" ({100 * count / max(closed, 1):.0f}% of all closures)")
    print(f"Left unresolved: {summary['unresolved_total']}"
          f"   median age {summary['unresolved_median_age']}"
          f"   max {summary['unresolved_max_age']}"
          f"   15+ ticks old: {summary['unresolved_15_plus']}")
    print()
    print("Horizon mix (deterministic classifier):")
    for horizon in HORIZONS:
        count = summary["horizon_counts"][horizon]
        closed_h = summary["horizon_closed"][horizon]
        print(f"   {horizon:12} {count:5} ({100 * count / max(total, 1):.0f}%)"
              f"   ever closed {closed_h} ({100 * closed_h / max(count, 1):.0f}%)")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default="work/novels",
                        help="Directory of novel projects (default: work/novels)")
    parser.add_argument("--json", action="store_true", help="Emit the summary as JSON")
    parser.add_argument("--sample", type=int, default=0,
                        help="Also emit N loops (stratified) for hand-labelling")
    parser.add_argument("--seed", type=int, default=7, help="Sample seed (default 7)")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.is_absolute():
        root = REPO_ROOT / root
    if not root.exists():
        print(f"No such corpus directory: {root}", file=sys.stderr)
        return 1

    novels = load_corpus(root)
    if not novels:
        print(f"No novels with loops found under {root}", file=sys.stderr)
        return 1

    summary = summarise(novels)
    if args.sample:
        summary["sample"] = sample_for_labelling(novels, args.sample, args.seed)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print_tables(summary)
        for item in summary.get("sample", []):
            print(f"[{item['classified']:12}] {item['novel']}/{item['id']}: {item['description']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

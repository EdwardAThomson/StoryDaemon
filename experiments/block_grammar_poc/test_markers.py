#!/usr/bin/env python3
"""No-network test of the marker retry/fallback logic (render_marked).

Cases:
  1. writer marks correctly first time -> no retry, no fallback
  2. writer omits markers, complies on the re-ask -> retry, no fallback
  3. writer omits markers twice but count matches -> positional fallback
  4. writer omits markers twice AND count differs -> no fallback (caller
     sees the raw non-compliance in the scores)

    python3 test_markers.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gate_b import MARKER_REMINDER, render_marked  # noqa: E402

MARKED = "[1] Alpha para.\n\n[2] Beta para.\n\n[3] Gamma para."
UNMARKED3 = "Alpha para.\n\nBeta para.\n\nGamma para."
UNMARKED2 = "Alpha para.\n\nBeta para."


def writer_for(first, on_retry):
    def w(prompt):
        return on_retry if prompt.endswith(MARKER_REMINDER) else first
    return w


def main():
    failures = []

    def check(name, ok):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            failures.append(name)

    _, nums, paras, f = render_marked(writer_for(MARKED, MARKED), "p", 3)
    check("compliant first try: no retry, no fallback, aligned",
          nums == [1, 2, 3] and not f["marker_retry"]
          and not f["positional_fallback"])

    _, nums, paras, f = render_marked(writer_for(UNMARKED3, MARKED), "p", 3)
    check("unmarked then compliant on re-ask",
          nums == [1, 2, 3] and f["marker_retry"]
          and not f["positional_fallback"])

    _, nums, paras, f = render_marked(writer_for(UNMARKED3, UNMARKED3),
                                      "p", 3)
    check("unmarked twice, count matches: positional fallback recorded",
          nums == [1, 2, 3] and f["marker_retry"]
          and f["positional_fallback"])

    _, nums, paras, f = render_marked(writer_for(UNMARKED2, UNMARKED2),
                                      "p", 3)
    check("unmarked twice, count differs: no fake alignment",
          nums == [None, None] and f["marker_retry"]
          and not f["positional_fallback"])

    print("ALL MARKER CHECKS PASS" if not failures
          else f"{len(failures)} CHECKS FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

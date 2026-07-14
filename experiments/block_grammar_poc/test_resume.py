#!/usr/bin/env python3
"""No-network test of the write-stop-resume cycle.

Simulates two sessions against the same cache directory:
  session 1: budget of 3 billed calls -> PauseRun on the 4th unique prompt
  session 2: no budget -> resumes; the 3 cached prompts must cost nothing

Asserts that across both sessions every unique prompt hits the network
exactly once (no double billing, no lost work), and that repeats are free.

    python3 test_resume.py
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gate_b import OpenRouterLLM, PauseRun  # noqa: E402


class StubLLM(OpenRouterLLM):
    """Deterministic transport; counts what would have been billed."""

    transports = []          # shared across "sessions", like a real ledger

    def _transport(self, prompt):
        StubLLM.transports.append(prompt)
        return f"response::{prompt}"


def main():
    tmp = tempfile.mkdtemp(prefix="resume-test-")
    prompts = [f"prompt-{i}" for i in range(5)]
    failures = []

    def check(name, ok):
        print(f"[{'PASS' if ok else 'FAIL'}] {name}")
        if not ok:
            failures.append(name)

    # session 1: pause after 3 billed calls
    budget1 = {"calls": 0, "max": 3}
    s1 = StubLLM("stub-model", cache_dir=tmp, budget=budget1)
    done, paused = [], False
    try:
        for p in prompts:
            done.append(s1(p))
    except PauseRun:
        paused = True
    check("session 1 pauses on the 4th unique prompt",
          paused and len(done) == 3)
    check("session 1 billed exactly its budget",
          budget1["calls"] == 3 and len(StubLLM.transports) == 3)

    # session 2: fresh process (new instance), same cache, no budget
    budget2 = {"calls": 0, "max": None}
    s2 = StubLLM("stub-model", cache_dir=tmp, budget=budget2)
    out = [s2(p) for p in prompts]
    check("session 2 completes all prompts",
          out == [f"response::{p}" for p in prompts])
    check("session 2 bills only the 2 un-cached prompts",
          budget2["calls"] == 2)
    check("across sessions each unique prompt billed exactly once",
          sorted(StubLLM.transports) == sorted(prompts))

    # repeats are free forever
    s2(prompts[0])
    check("repeated prompt after resume is free",
          budget2["calls"] == 2 and len(StubLLM.transports) == 5)

    # a different model must NOT share cache entries
    s3 = StubLLM("other-model", cache_dir=tmp,
                 budget={"calls": 0, "max": None})
    s3(prompts[0])
    check("cache is model-keyed (other model re-bills)",
          len(StubLLM.transports) == 6)

    shutil.rmtree(tmp)
    print("ALL RESUME CHECKS PASS" if not failures
          else f"{len(failures)} CHECKS FAILED")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

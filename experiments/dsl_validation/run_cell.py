#!/usr/bin/env python3
"""Run one cell of the DSL validation campaign: create a fresh novel from a
foundation, apply config overrides, run N ticks, and log every LLM call's
exact OpenRouter cost to <project>/usage.jsonl.

    venv/bin/python experiments/dsl_validation/run_cell.py \
        --name e1-luna-alcyone-on --foundation alcyone --model openai/gpt-5.6-luna \
        --set generation.enable_scene_skeleton=true --ticks 8

Novels land in work/dsl/ (gitignored). Re-running with an existing --name
resumes that project instead of creating a new one.
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
WORK = REPO / "work" / "dsl"


def parse_value(raw):
    try:
        return yaml.safe_load(raw)
    except yaml.YAMLError:
        return raw


def set_dotted(cfg, key, value):
    node = cfg
    parts = key.split(".")
    for p in parts[:-1]:
        node = node.setdefault(p, {}) or {}
    node[parts[-1]] = value


def find_project(name):
    hits = sorted(glob.glob(str(WORK / f"{name}_*")))
    return Path(hits[0]) if hits else None


def install_cost_logger(log_path):
    """Wrap the OpenAI client's chat completions so each call's usage lands in
    usage.jsonl. OpenRouter returns usage.cost (USD) on every response."""
    from openai.resources.chat.completions import Completions

    original = Completions.create

    def logged(self, *args, **kwargs):
        t0 = time.time()
        resp = original(self, *args, **kwargs)
        try:
            usage = getattr(resp, "usage", None)
            u = usage.model_dump() if usage is not None else {}
            msgs = kwargs.get("messages") or []
            prompt = msgs[-1].get("content", "") if msgs else ""
            rec = {
                "t": t0,
                "secs": round(time.time() - t0, 2),
                "model": kwargs.get("model"),
                "max_tokens": kwargs.get("max_tokens") or kwargs.get("max_completion_tokens"),
                "finish": resp.choices[0].finish_reason if resp.choices else None,
                "prompt_head": prompt[:160] if isinstance(prompt, str) else "",
                "prompt_chars": len(prompt) if isinstance(prompt, str) else 0,
                "out_chars": len(resp.choices[0].message.content or "") if resp.choices else 0,
                "cost": u.get("cost"),
                "prompt_tokens": u.get("prompt_tokens"),
                "completion_tokens": u.get("completion_tokens"),
                "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            }
            with open(log_path, "a") as f:
                f.write(json.dumps(rec) + "\n")
        except Exception as e:  # logging must never break a tick
            print(f"[cost-logger] {e}", file=sys.stderr)
        return resp

    Completions.create = logged


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--foundation", required=True, help="stem in foundations/")
    ap.add_argument("--model", required=True, help="OpenRouter upstream id")
    ap.add_argument("--ticks", type=int, required=True)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    args = ap.parse_args()

    WORK.mkdir(parents=True, exist_ok=True)
    project = find_project(args.name)
    if project is None:
        subprocess.run(
            [str(REPO / "venv" / "bin" / "novel"), "new", args.name,
             "--dir", str(WORK), "--no-interactive",
             "--foundation", str(HERE / "foundations" / f"{args.foundation}.yaml")],
            check=True, cwd=str(REPO))
        project = find_project(args.name)
        cfg_path = project / "config.yaml"
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
        set_dotted(cfg, "llm.backend", "api")
        set_dotted(cfg, "llm.model", f"openrouter:{args.model}")
        for item in args.set:
            k, v = item.split("=", 1)
            set_dotted(cfg, k, parse_value(v))
        cfg_path.write_text(yaml.dump(cfg, default_flow_style=False, sort_keys=False))
        (project / "cell.json").write_text(json.dumps(vars(args), indent=2))

    state = json.loads((project / "state.json").read_text())
    remaining = args.ticks - state.get("current_tick", 0)
    print(f"[cell] {project.name}: tick {state.get('current_tick')} -> {args.ticks}")
    if remaining <= 0:
        return

    install_cost_logger(project / "usage.jsonl")
    os.chdir(project)
    from novel_agent.cli.main import run
    run(n=remaining, project=str(project), checkpoint_interval=0, retries=1)


if __name__ == "__main__":
    main()

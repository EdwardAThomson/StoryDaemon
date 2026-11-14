#!/usr/bin/env python3
"""What does Opus write for fantasy with no style targets? (2026-11-14)

The word-origin gauge puts Tolkien at about 8% French/Latin words (the
Legendarium table), the old-fantasy shelf (Morris, Dunsany, Eddison) at 10%,
and plain Opus writing an 1815 drawing room at 13-14%. Whether Opus needs to
be told anything for fantasy depends on where it lands unprompted, so this
writes two fantasy scenes through the real StoryDaemon writer with no
skeleton, no paragraph plan and no style profile (the blind test's "plain"
arm), then measures them.

Every name comes from the StoryDaemon name generator (fantasy bank); the
briefs describe people by role. Requests go through the blind test's
wrapper: spend cap, usage log, stop on a cut-off response.

    venv/bin/python experiments/blind_test/fantasy_baseline.py --fake
    venv/bin/python experiments/blind_test/fantasy_baseline.py --max-usd 0.25
"""
import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import write_scenes as ws  # noqa: E402

OUT = ws.WORK / "out" / "fantasy"
FOUNDATION = {
    "genre": "fantasy",
    "setting": "An invented northern kingdom of hill forts, old roads and long winters, "
               "before gunpowder; a neighbouring realm across the mountains is hostile.",
    "tone": "grave and quiet, with an old-fashioned seriousness",
    "premise": "A young keeper of the king's roads is drawn into a coming war when the "
               "waystations on the mountain pass begin to burn.",
}
SCENES = {
    "pass": {
        "words": 1000,
        "cast": [("pov", "female", "young",
                  "a young keeper of the king's roads, two seasons in the post, steady but untried"),
                 ("guide", "male", "old",
                  "an old hillman who has guided travellers over the pass for forty years")],
        "place": ("pass", "A stone waystation high on the mountain pass, its roof burned out, "
                          "snow drifting through the doorway; evening is coming on."),
        "intention": "The keeper and the old guide reach the waystation at dusk and find it burned, "
                     "the keeper of the station gone and no body to be found. The guide reads the "
                     "signs in the ash and the snow and says the burners came from over the mountains. "
                     "They argue about whether to press on to the next station in the dark or shelter "
                     "in the ruin; the keeper decides to stay, and they make what shelter they can.",
        "key_change": "The keeper understands this was not an accident or a raid for plunder, but the "
                      "first move of a war.",
    },
    "hall": {
        "words": 1000,
        "cast": [("pov", "female", "young",
                  "a young keeper of the king's roads, summoned to the hall to report what she found "
                  "on the pass"),
                 ("lord", "male", "old", "the old lord of the hill fort, the king's warden of the border"),
                 ("envoy", "male", "adult",
                  "an envoy from the realm across the mountains, courteous and cold")],
        "place": ("hall", "The great hall of the hill fort: a long timber hall with a fire down "
                          "its middle and shields along the walls."),
        "intention": "The keeper has given her report when the envoy from across the mountains is "
                     "brought in. He denies all knowledge of the burnings and asks, with great "
                     "courtesy, that the border stations be pulled back a day's ride 'to avoid "
                     "misunderstandings'. The old lord hears him out, then refuses, and names the "
                     "burned station. The envoy takes his leave with a courteous warning.",
        "key_change": "The lord's refusal makes open war likely, and the keeper sees he has chosen it "
                      "with his eyes open.",
    },
}


def make_project(sid, brief):
    from novel_agent.cli.foundation import StoryFoundation
    from novel_agent.cli.project import create_novel_project
    from novel_agent.memory.entities import Character, Location
    from novel_agent.memory.manager import MemoryManager
    from novel_agent.tools.name_generator import NameGenerator

    gen = NameGenerator(REPO / "novel_agent" / "data" / "names",
                        person_bank="fantasy", place_bank="fantasy")
    minted = {key: gen.generate_name(gender=g, genre="fantasy") for key, g, _, _ in brief["cast"]}
    _, pov_gender, pov_age, pov_role = brief["cast"][0]
    pov = minted["pov"]
    f = StoryFoundation(genre=FOUNDATION["genre"], setting=FOUNDATION["setting"],
                        tone=FOUNDATION["tone"], premise=FOUNDATION["premise"],
                        protagonist_archetype=pov_role, protagonist_name=pov["full_name"],
                        protagonist_gender=pov_gender, protagonist_age=pov_age)
    base = ws.WORK / "projects"
    base.mkdir(parents=True, exist_ok=True)
    path = Path(create_novel_project(
        "untitled", base_dir=str(base), foundation=f, llm_backend="api", llm_model=ws.MODEL,
        name_banks={"person_bank": "fantasy", "place_bank": "fantasy"}))
    memory = MemoryManager(path)
    pov_id = next(cid for cid in memory.list_characters()
                  if memory.load_character(cid).first_name == pov["first_name"])
    for key, gender, age, role in brief["cast"][1:]:
        n = minted[key]
        memory.save_character(Character(
            id=memory.generate_id("character"), first_name=n["first_name"],
            family_name=n["last_name"], gender=gender, age_group=age, role=role, description=role,
            metadata={"source": "fantasy_baseline", "minted": "generated (fantasy bank)"}))
    place = gen.generate_place_name(descriptor=brief["place"][0], genre="fantasy")["full_name"]
    lid = memory.generate_id("location")
    memory.save_location(Location(id=lid, name=place, description=brief["place"][1]))
    return path, memory, pov_id, lid, {k: v["full_name"] for k, v in minted.items()}, place


def write(sid, brief, llm_factory):
    from novel_agent.agent.writer import SceneWriter
    from novel_agent.agent.writer_context import WriterContextBuilder
    from novel_agent.cli.project import get_project_config

    ws.STATE["arm"], ws.STATE["scene"] = "plain", f"fantasy_{sid}"
    path, memory, pov_id, lid, names, place = make_project(sid, brief)
    config = get_project_config(str(path))
    total = round(brief["words"] * 0.85)
    for k, v in {**ws.COMMON, **ws.ARMS["plain"],
                 "generation.default_scene_length": "long",
                 "generation.scene_word_targets": {"brief": 300, "short": total,
                                                   "long": total, "extended": total}}.items():
        config.set(k, v)
    state = json.loads((path / "state.json").read_text())
    state["current_tick"] = 6
    plan = {"scene_intention": brief["intention"], "key_change": brief["key_change"],
            "pov_character": pov_id, "target_location": lid, "metadata": {}}
    writer = SceneWriter(llm_factory(), config)
    ctx = WriterContextBuilder(memory, None, config).build_writer_context(plan, {}, state)
    ctx["recent_context"] = ctx["recent_context"].replace(
        "This is the first scene of the novel.", "This scene comes from the middle of the novel.")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{sid}_prompt.txt").write_text(writer._format_writer_prompt(ctx))
    text = writer.write_scene(ctx).get("text", "")
    (OUT / f"{sid}.md").write_text(text)
    (OUT / f"{sid}.json").write_text(json.dumps({"names": names, "place": place,
                                                 "project": str(path)}, indent=1))
    return text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-usd", type=float, default=0.0)
    ap.add_argument("--fake", action="store_true")
    args = ap.parse_args()
    if not args.fake and args.max_usd <= 0:
        raise SystemExit("a real run needs --max-usd")
    ws.STATE["log"] = ws.WORK / ("usage_fake.jsonl" if args.fake else "usage.jsonl")
    ws.install_requests(args.max_usd if not args.fake else 1.0, args.fake)

    def llm_factory():
        from novel_agent.tools.llm_setup import initialize_llm_with_persona
        return initialize_llm_with_persona(backend="api", model=ws.MODEL, timeout=300)

    from novel_agent.agent.style_profile import measure
    try:
        for sid, brief in SCENES.items():
            print(f"[fantasy] {sid}", flush=True)
            text = write(sid, brief, llm_factory)
            m = measure(text)
            print(f"  {len(text.split())} words, latinate {m['latinate_pct']}% "
                  f"(content {m['latinate_content_pct']}%), long words {m['long_words_per_1k']}/1k",
                  flush=True)
    except ws.StopRun as e:
        print(f"[fantasy] STOPPED: {e}", flush=True)
    print(f"[fantasy] spent ${ws.STATE['usd']:.3f}", flush=True)


if __name__ == "__main__":
    main()

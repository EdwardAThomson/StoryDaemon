from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Dict, Any
import json
from datetime import datetime

from ..memory.manager import MemoryManager
from ..memory.entity_resolver import EntityResolver
from ..configs.config import Config
from .entities import PlotBeat, PlotOutline


class PlotOutlineManager:
    """Manages the emergent plot outline (Phase 1, CLI-only).

    Stores beats in project_root/plot_outline.json
    """

    def __init__(self, project_dir: Path, llm_interface, config=None):
        self.project_dir = Path(project_dir)
        self.llm = llm_interface
        self.outline_file = self.project_dir / "plot_outline.json"
        self.memory = MemoryManager(self.project_dir)
        # Config is needed for the arc-pressure beat schedule (Phase 3 bridge). The
        # agent passes its own instance; standalone callers fall back to the project
        # config.yaml over defaults, matching what the agent would read.
        if config is None:
            config = Config(str(self.project_dir / "config.yaml"))
        self.config = config

    # ---------- Persistence ----------
    def load_outline(self) -> PlotOutline:
        if self.outline_file.exists():
            try:
                return PlotOutline.from_json(self.outline_file)
            except Exception:
                # Corrupt file; start fresh but keep backup
                backup = self.outline_file.with_suffix(".json.bak")
                self.outline_file.replace(backup)
        outline = PlotOutline(beats=[], created_at=self._now(), last_updated=self._now())
        return outline

    def save_outline(self, outline: PlotOutline) -> None:
        outline.last_updated = self._now()
        outline.to_json(self.outline_file)

    # ---------- ID helpers ----------
    def _next_id(self, existing_ids: List[str]) -> str:
        max_n = 0
        for bid in existing_ids:
            try:
                if bid.startswith("PB"):
                    n = int(bid[2:])
                    max_n = max(max_n, n)
            except ValueError:
                continue
        return f"PB{max_n+1:03d}"

    def _assign_ids(self, outline: PlotOutline, beats: List[PlotBeat]) -> List[PlotBeat]:
        existing_ids = [b.id for b in outline.beats if b.id]
        assigned: List[PlotBeat] = []
        for b in beats:
            if not b.id:
                b.id = self._next_id(existing_ids)
                existing_ids.append(b.id)
            if not b.created_at:
                b.created_at = self._now()
            assigned.append(b)
        return assigned

    # ---------- Generation ----------
    def generate_next_beats(self, count: int = 5) -> List[PlotBeat]:
        """Generate candidate beats from current story state via LLM.
        Returns beats without assigning IDs; call add_beats() to persist.
        """
        # Imported lazily to avoid a module-load circular import
        # (agent package __init__ imports StoryAgent, which imports this module).
        from ..agent.prompts import format_plot_generation_prompt

        ctx = self._build_generation_context(count)
        prompt = format_plot_generation_prompt(ctx)
        # Use planner token budget as a safe default
        max_tokens = ctx.get("planner_max_tokens", 1000)
        response = self.llm.generate(prompt, max_tokens=max_tokens)
        beats = self._parse_beats_response(response)
        self._reconcile_beat_tension(beats, ctx.get("current_tick", 0))
        return beats

    def _reconcile_beat_tension(self, beats: List[PlotBeat], current_tick: int) -> None:
        """Hold authored tension targets to the arc schedule (Phase 3 bridge).

        Sanitize-not-trust, like _resolve_beat_references: fill missing targets from
        the schedule and clamp far-off ones toward it. Never raises; a reconciliation
        problem must not break beat generation (fallback_to_reactive relies on that).
        """
        try:
            from ..agent.arc_pressure import reconcile_beat_tension_targets

            for warning in reconcile_beat_tension_targets(beats, current_tick, self.config):
                print(f"        ⚠️  {warning}")
        except Exception as e:
            print(f"        ⚠️  Beat tension reconciliation skipped: {e}")

    def add_beats(self, beats: List[PlotBeat]) -> List[PlotBeat]:
        outline = self.load_outline()
        beats_assigned = self._assign_ids(outline, beats)
        self._resolve_beat_references(beats_assigned)
        outline.beats.extend(beats_assigned)
        self.save_outline(outline)
        return beats_assigned

    def _resolve_beat_references(self, beats: List[PlotBeat]) -> None:
        """Force every beat's entity references to real IDs; drop phantoms.

        The roster in the generation prompt tells the LLM the real IDs, but it
        can still emit one that matches nothing (or a short form like "C0").
        Resolution here is the deterministic guardrail: references become
        canonical IDs by selection, never free-typed.
        """
        resolver = EntityResolver(self.memory)
        for beat in beats:
            dropped_chars, dropped_loc = resolver.resolve_beat(beat)
            if dropped_chars:
                print(f"        ⚠️  Beat {beat.id}: dropped unresolved character refs {dropped_chars}")
            if dropped_loc:
                print(f"        ⚠️  Beat {beat.id}: dropped unresolved location ref '{dropped_loc}'")

    def get_next_beat(self) -> Optional[PlotBeat]:
        outline = self.load_outline()
        for b in outline.beats:
            if b.status == "pending":
                return b
        return None

    # ---------- Rolling horizon (Phase 2) ----------
    def revise_horizon(
        self,
        reason: str = "",
        count: int = 5,
        current_tick: Optional[int] = None,
    ) -> Dict[str, List[str]]:
        """Discard the stale pending lookahead and regenerate it from current canon.

        This is the rolling-horizon mechanism: the next few beats are re-derived
        from what actually happened (recent scenes, open loops, live rosters)
        rather than executed from a plan laid down before the prose existed.

        Generation runs *first*; only if it yields beats do we abandon the
        existing pending horizon, so a generation failure never strands the story
        with no beats to execute. Completed / in-progress beats are never touched.

        Returns ``{"abandoned": [ids], "generated": [ids]}``.
        """
        new_beats = self.generate_next_beats(count=count)
        if not new_beats:
            return {"abandoned": [], "generated": []}

        outline = self.load_outline()
        abandoned: List[str] = []
        for b in outline.beats:
            if b.status == "pending":
                b.status = "abandoned"
                b.abandoned_reason = reason
                b.revised_at_tick = current_tick
                abandoned.append(b.id)
        self.save_outline(outline)

        added = self.add_beats(new_beats)
        return {"abandoned": abandoned, "generated": [b.id for b in added]}

    # ---------- Utilities ----------
    def _build_generation_context(self, count: int) -> Dict[str, Any]:
        state = self._load_state()
        novel_name = state.get("novel_name", "Untitled Novel")
        current_tick = state.get("current_tick", 0)
        foundation = state.get("story_foundation") or {}

        # Open loops
        loops = self.memory.load_open_loops()
        open_loops_desc = []
        for l in loops:
            if l.status == "open":
                line = f"{l.id}: ({l.importance}) {l.description}"
                open_loops_desc.append(line)
        open_loops_text = "\n".join(open_loops_desc) if open_loops_desc else "None"

        # Recent scenes (last 3, oldest first so "most recent last" holds)
        scene_ids = self.memory.list_scenes()
        scene_ids_sorted = sorted(scene_ids)
        recent_ids = scene_ids_sorted[-3:]
        recent_lines = []
        tension_lines = []
        for sid in recent_ids:
            s = self.memory.load_scene(sid)
            if not s:
                continue
            summ = "; ".join(s.summary) if getattr(s, "summary", None) else ""
            recent_lines.append(f"{sid}: {s.title or ''} — {summ}")
            tension_level = getattr(s, "tension_level", None)
            if tension_level is not None:
                tension_lines.append(f"{sid}: tension {tension_level}/10")
        recent_text = "\n".join(recent_lines) if recent_lines else "None"
        tension_text = "\n".join(tension_lines) if tension_lines else "None"

        # Existing outline beats (last few) for continuity
        outline = self.load_outline()
        recent_beats_lines = [
            f"{b.id}: {b.description} [status={b.status}]"
            for b in outline.beats[-5:]
        ]
        recent_beats_text = "\n".join(recent_beats_lines) if recent_beats_lines else "None"

        # Character roster (real IDs the beat generator must reference)
        char_lines = []
        for cid in sorted(self.memory.list_characters()):
            c = self.memory.load_character(cid)
            if not c:
                continue
            char_lines.append(f"{c.id}: {c.name} ({c.role})")
        characters_text = "\n".join(char_lines) if char_lines else "None"

        # Location roster (real IDs the beat generator must reference)
        loc_lines = []
        for lid in sorted(self.memory.list_locations()):
            loc = self.memory.load_location(lid)
            if not loc:
                continue
            loc_lines.append(f"{loc.id}: {loc.name}")
        locations_text = "\n".join(loc_lines) if loc_lines else "None"

        # Arc schedule for the beats about to be authored (Phase 3 bridge). Imported
        # lazily for the same circular-import reason as format_plot_generation_prompt;
        # renders "" when arc-pressure or the mandate gate is off. Never a hard failure.
        try:
            from ..agent.arc_pressure import arc_guidance_for_beats
            arc_guidance_section = arc_guidance_for_beats(current_tick, count, self.config)
        except Exception:
            arc_guidance_section = ""

        return {
            "novel_name": novel_name,
            "current_tick": current_tick,
            "genre": foundation.get("genre", "unknown"),
            "premise": foundation.get("premise", "unknown"),
            "setting": foundation.get("setting", "unknown"),
            "tone": foundation.get("tone", "unknown"),
            "open_loops": open_loops_text,
            "recent_scenes": recent_text,
            "tension_history": tension_text,
            "recent_beats": recent_beats_text,
            "characters": characters_text,
            "locations": locations_text,
            "arc_guidance_section": arc_guidance_section,
            "count": count,
            "planner_max_tokens": 1000,
        }

    def _parse_beats_response(self, response: str) -> List[PlotBeat]:
        # Try JSON extraction - look for code blocks first
        import re
        
        # Try to extract from markdown code block
        code_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", response, re.S)
        if code_block_match:
            json_str = code_block_match.group(1)
        else:
            # Try to find raw JSON object with beats array
            # Use greedy match to get the full JSON object
            match = re.search(r"\{\s*\"beats\"\s*:\s*\[.*\]\s*\}", response, re.S)
            json_str = match.group(0) if match else None
        
        data = None
        if json_str:
            try:
                data = json.loads(json_str)
            except Exception as e:
                print(f"        ⚠️  JSON parse error: {e}")
                data = None
        
        if not data:
            # Fallback: try to parse line-based bullets into descriptions
            lines = [ln.strip(" -\t") for ln in response.splitlines() if ln.strip()]
            # Filter out JSON syntax lines
            descs = [ln for ln in lines if ln and not ln.startswith("BEAT") 
                     and not ln.startswith("{") and not ln.startswith("}")
                     and not ln.startswith("[") and not ln.startswith("]")
                     and not ln.startswith('"beats"')]
            return [PlotBeat(id="", description=d) for d in descs[:5]]

        beats_data = data.get("beats", [])
        beats: List[PlotBeat] = []
        for b in beats_data:
            beats.append(
                PlotBeat(
                    id="",
                    description=b.get("description", ""),
                    characters_involved=b.get("characters_involved", []) or [],
                    location=b.get("location"),
                    plot_threads=b.get("plot_threads", []) or [],
                    tension_target=b.get("tension_target"),
                    prerequisites=b.get("prerequisites", []) or [],
                    advances_character_arcs=b.get("advances_character_arcs", []) or [],
                    resolves_loops=b.get("resolves_loops", []) or [],
                    creates_loops=b.get("creates_loops", []) or [],
                )
            )
        return beats

    def _load_state(self) -> Dict[str, Any]:
        state_path = self.project_dir / "state.json"
        try:
            with open(state_path) as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().isoformat() + "Z"

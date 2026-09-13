"""Scene writer for generating prose."""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple

from .segments import (
    continuation_token_budget,
    scene_incomplete,
    token_budget_for,
    trim_to_last_sentence,
    word_target_for,
)

logger = logging.getLogger(__name__)


class SceneWriter:
    """Generates scene prose using LLM."""

    def __init__(self, llm_interface, config):
        """Initialize scene writer.

        Args:
            llm_interface: CodexInterface instance
            config: Configuration object
        """
        self.llm = llm_interface
        self.config = config

    def write_scene(self, writer_context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate scene prose via the write-until-concluded segment loop.

        Phase 3 (segment plumbing for the block DSL): the request ceiling is
        sized from the scene's word target (2x headroom, so an on-target scene
        never brushes it), and a first render that still ends cut (finish_reason
        "length" or the completion heuristic) gets bounded continuation
        segments, each carrying the full scene so far with a firm instruction to
        conclude. A scene that exhausts the cap still incomplete is trimmed to
        the last complete sentence and flagged: truncation is a state this path
        cannot ship.

        Args:
            writer_context: Context dictionary from WriterContextBuilder

        Returns:
            Dictionary with:
                - text: Scene prose
                - word_count: Number of words
                - title: Extracted or generated title
                - segments_used: How many LLM segments produced the text
                - concluded_naturally: Ended on its own (no trim, no length cut)
                - trimmed: The trim fallback fired (flagged truncation)
        """
        # Format the writer prompt (carries the explicit word target)
        prompt = self._format_writer_prompt(writer_context)

        # Size the ceiling from the word target instead of a flat token wall
        word_target = writer_context.get("word_target") or word_target_for(None, self.config)
        max_tokens = token_budget_for(word_target, self.config)

        # Sectioned writing (DSL Slice 5, generation.subblock_generation):
        # write the scene across several plan-addressed calls instead of one.
        # A masters-length chapter is ~3,165 words and a single request does
        # not reliably produce one. Falls back to single-shot on any failure,
        # and needs a skeleton, since the plan is what addresses the sections.
        sectioned = self._write_in_sections(writer_context)
        if sectioned is not None:
            text, meta = sectioned
        else:
            # First segment: as today. A failure here raises, exactly as before.
            text, finish_reason = self._generate_segment(prompt, max_tokens)

            # Continue until concluded (bounded), then trim-and-flag as a last resort.
            text, meta = self._write_until_concluded(
                text, finish_reason, writer_context)

        # Parse and return scene data plus generation metadata
        scene_data = self._parse_scene_response(text, writer_context)
        scene_data.update(meta)

        # Scene skeleton (Slice 4, experimental): strip the [n] paragraph
        # markers from the prose and record compliance. Guarded: a stripping
        # failure must never cost the scene.
        skeleton = writer_context.get("scene_skeleton")
        if skeleton:
            try:
                from .scene_skeleton import strip_skeleton_markers
                clean, stats = strip_skeleton_markers(scene_data["text"])
                scene_data["text"] = clean
                scene_data["word_count"] = len(clean.split())
                scene_data["scene_skeleton"] = list(skeleton)
                split = stats["paragraphs"] - len(skeleton)
                scene_data["skeleton_compliance"] = {
                    "plan_blocks": len(skeleton),
                    "markers_found": stats["markers_found"],
                    "markers_distinct": stats["markers_distinct"],
                    "paragraphs": stats["paragraphs"],
                    "extra_paragraphs": max(0, split),
                    # Both halves matter: every plan item written, and nothing
                    # written that was not a plan item.
                    "compliant": (stats["markers_distinct"] == len(skeleton)
                                  and stats["paragraphs"] == len(skeleton)),
                }
                note = ""
                if stats["markers_distinct"] != len(skeleton):
                    note = " (markers missing)"
                elif split > 0:
                    note = f" ({split} item(s) split across paragraphs)"
                elif split < 0:
                    note = f" ({-split} item(s) merged)"
                print(f"        scene skeleton: "
                      f"{stats['markers_distinct']}/{len(skeleton)} plan "
                      f"markers, {stats['paragraphs']} paragraphs{note}")
            except Exception as e:
                logger.warning(f"skeleton marker stripping failed: {e}")
        return scene_data

    def _write_in_sections(self, writer_context: Dict[str, Any]):
        """Write the scene as several plan-addressed calls. None = not used.

        Gated by generation.subblock_generation (default False) and requires a
        scene skeleton, which is what gives each section its [n] addresses.
        generation.subblock_section_blocks sets the granularity; 1 is the
        landing sketch's literal per-sub-block mode.

        Graceful degradation is the whole safety story here: any failure
        returns None and the caller writes the scene single-shot exactly as
        before, so switching the flag on can cost quality but never a scene.
        """
        if not self.config.get('generation.subblock_generation', False):
            return None
        skeleton = writer_context.get("scene_skeleton")
        if not skeleton:
            return None
        try:
            from .prompts import format_scene_section_prompt
            from .scene_skeleton import (mode_word_stats, plan_rules,
                                         skeleton_lines)
            from .segments import (DEFAULT_SECTION_BLOCKS, partition_skeleton,
                                   section_word_target, token_budget_for)

            bounds = partition_skeleton(
                len(skeleton),
                self.config.get('generation.subblock_section_blocks',
                                DEFAULT_SECTION_BLOCKS))
            if len(bounds) < 2:
                return None          # one section is just single-shot writing

            mode_words = mode_word_stats()
            parts, text = [], ""
            for i, (first, last) in enumerate(bounds):
                words = section_word_target(skeleton, first, last, mode_words)
                prompt = format_scene_section_prompt(
                    writer_context,
                    plan_lines=skeleton_lines(skeleton, first, last),
                    plan_rules=plan_rules(last - first + 1, words,
                                          sectioned=True),
                    first=first, last=last,
                    scene_so_far=text,
                    is_first=(i == 0),
                    is_last=(i == len(bounds) - 1),
                )
                part, _ = self._generate_segment(
                    prompt, token_budget_for(words, self.config))
                part = self._strip_llm_header((part or "").strip())
                if not part:
                    raise ValueError(
                        f"empty response for plan blocks {first}-{last}")
                parts.append(part)
                text = self._join_segments(text, part) if text else part
                print(f"        section {i + 1}/{len(bounds)}: plan blocks "
                      f"{first}-{last}, {len(part.split())} words "
                      f"(target {words})")
            return text, {
                "segments_used": len(bounds),
                "sectioned": True,
                "section_bounds": [list(b) for b in bounds],
                "concluded_naturally": True,
                "trimmed": False,
            }
        except Exception as e:
            logger.warning(
                f"Sectioned writing failed; falling back to single-shot: {e}")
            return None

    def _generate_segment(self, prompt: str, max_tokens: int) -> Tuple[str, Optional[str]]:
        """One LLM request, with the finish_reason when the backend exposes it.

        The api backend's MultiProviderInterface implements generate_with_meta
        (authoritative "length"/"stop" signal); the CLI backends (codex,
        claude-cli, gemini-cli) do not, so they return (text, None) and the
        completion heuristic governs. The plain generate() contract is untouched.
        """
        if hasattr(self.llm, "generate_with_meta"):
            return self.llm.generate_with_meta(prompt, max_tokens=max_tokens)
        return self.llm.generate(prompt, max_tokens=max_tokens), None

    def _write_until_concluded(
        self, text: str, finish_reason: Optional[str], writer_context: Dict[str, Any]
    ) -> Tuple[str, Dict[str, Any]]:
        """The segment loop: continue-and-conclude until an ending is detected.

        Loop invariant (the whole point): the returned text always has a
        detected ending, either natural, concluded on request, or trimmed to the
        last complete sentence with trimmed=True. Graceful degradation: a
        continuation failure falls back to the text so far, worst case trimmed.
        """
        from .prompts import format_scene_continuation_prompt

        max_segments = int(self.config.get('generation.scene_max_segments', 3))
        segments_used = 1
        try:
            while ((finish_reason == "length" or scene_incomplete(text))
                   and segments_used < max_segments):
                cont_prompt = format_scene_continuation_prompt(text, writer_context)
                cont_text, finish_reason = self._generate_segment(
                    cont_prompt, continuation_token_budget(self.config)
                )
                cont_text = self._strip_llm_header((cont_text or "").strip())
                if not cont_text:
                    break
                text = self._join_segments(text, cont_text)
                segments_used += 1
                print(f"        scene continued (segment {segments_used} of {max_segments})")
        except Exception as e:
            # A loop failure never loses the scene: keep what we have (the
            # single-shot result at worst) and let the trim guarantee below hold.
            logger.warning(f"Scene continuation failed; keeping the text so far: {e}")

        trimmed = False
        if scene_incomplete(text):
            text, _changed = trim_to_last_sentence(text)
            trimmed = True
            print("        scene trimmed to last complete sentence, flagged")

        meta = {
            "segments_used": segments_used,
            "concluded_naturally": (not trimmed) and finish_reason != "length",
            "trimmed": trimmed,
        }
        return text, meta

    @staticmethod
    def _join_segments(text: str, continuation: str) -> str:
        """Append a continuation segment to the scene so far.

        A mid-sentence stop joins inline (the continuation finishes the
        sentence); a clean sentence boundary joins as a new paragraph.
        """
        base = text.rstrip()
        if scene_incomplete(base):
            return base + " " + continuation.lstrip()
        return base + "\n\n" + continuation.lstrip()


    def revise_for_tension(self, scene_text: str, target_level: float, current_level: float,
                           writer_context: Dict[str, Any] = None, prev_tension: float = None) -> str:
        """Revise a scene's tension toward `target_level`, keeping the plot outcome.

        Text-only wrapper around revise_for_tension_with_meta (original contract).
        """
        text, _meta = self.revise_for_tension_with_meta(
            scene_text, target_level, current_level, writer_context, prev_tension
        )
        return text

    def revise_for_tension_with_meta(
        self, scene_text: str, target_level: float, current_level: float,
        writer_context: Dict[str, Any] = None, prev_tension: float = None
    ) -> Tuple[str, Dict[str, Any]]:
        """Revise a scene's tension toward `target_level`, keeping the plot outcome.

        Uses the shared 0-10 tension scale (so the instruction matches the grader), the real
        story context, and continuity with the previous scene's tension: a big drop is framed
        as a deliberate transition, not an unmotivated whiplash. Returns (cleaned prose or "",
        meta) where meta carries the completion guarantee's trimmed flag.

        Phase 3 (segment plumbing): the budget is sized from the INPUT scene's length
        (the old flat 3000-token wall truncated long revisions), and the output gets
        detect+trim+flag. No continuation loop here, a deliberate judgment call: this
        is a bounded polish pass whose result is kept only when it scores closer to
        the target, the complete original scene remains the fallback, and a
        trimmed-at-sentence revision already satisfies the no-truncation invariant.
        """
        from .prompts import format_tension_revision_prompt
        from .tension_scale import band_for, scale_overview

        writer_context = writer_context or {}
        target_band = band_for(target_level)
        current_band = band_for(current_level)
        direction = (f"LOWER the tension toward the target — {target_band.directive}."
                     if target_level < current_level else
                     f"RAISE the tension toward the target — {target_band.directive}.")

        # Continuity: frame a large drop from the previous scene as a deliberate transition.
        continuity_line = ""
        if prev_tension is not None:
            step = self.config.get('coherence.tension_step_for_transition', 3)
            if prev_tension - target_level >= step:
                continuity_line = (
                    f"The previous scene was {prev_tension:g}/10; this is a deliberate transition to "
                    f"a calmer beat — lean into the new location or aftermath this scene establishes, "
                    f"do not sustain the prior intensity.\n")
            else:
                continuity_line = f"The previous scene was {prev_tension:g}/10.\n"

        prompt = format_tension_revision_prompt({
            "recent_context": writer_context.get("recent_context", "(none)"),
            "pov_character_details": writer_context.get("pov_character_details", "(unknown)"),
            "location_details": writer_context.get("location_details", "(unknown)"),
            "scene_intention": writer_context.get("scene_intention", ""),
            "key_change": writer_context.get("key_change", ""),
            "current_level": f"{current_level:g}",
            "current_band": current_band.name,
            "target_level": f"{target_level:g}",
            "target_band": target_band.name,
            "target_definition": target_band.definition,
            "continuity_line": continuity_line,
            "direction_line": direction,
            "scale_overview": scale_overview(),
            "scene_text": scene_text,
        })
        # Size from the input scene: a revision roughly matches its source's length.
        source_words = max(len(scene_text.split()), word_target_for(None, self.config))
        max_tokens = token_budget_for(source_words, self.config)
        response, finish_reason = self._generate_segment(prompt, max_tokens)
        text = self._strip_llm_header((response or "").strip())

        meta = {"trimmed": False}
        if text and (finish_reason == "length" or scene_incomplete(text)):
            text, _changed = trim_to_last_sentence(text)
            meta["trimmed"] = True
            print("        revision trimmed to last complete sentence, flagged")
        return text, meta

    def revise_blocks_for_tension(
        self, scene_text: str, skeleton, indices, target_level: float,
        current_level: float, writer_context: Dict[str, Any] = None,
        prev_tension: float = None
    ) -> Tuple[str, Dict[str, Any]]:
        """Revise selected paragraphs toward a tension target; splice them back.

        Everything not selected is returned byte-identical, so the paragraph
        plan, the scene's length and its marker compliance all survive the
        pass by construction. Returns ("", meta) when nothing could be applied,
        which the caller treats as "no revision" and keeps the original scene.
        """
        from .partial_revision import (check_lengths, parse_revised_blocks,
                                       splice)
        from .prompts import format_partial_revision_prompt, number_scene
        from .scene_skeleton import block_word_targets, MODE_GUIDE, plan_rules
        from .tension_scale import band_for, scale_overview

        writer_context = writer_context or {}
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", scene_text)
                      if p.strip()]
        indices = [i for i in indices if 1 <= i <= len(paragraphs)]
        if not indices:
            return "", {"applied": 0, "reason": "no revisable paragraphs"}

        targets = block_word_targets(list(skeleton))
        want_words_hint = sum(
            targets[i - 1] if i - 1 < len(targets)
            else len(paragraphs[i - 1].split()) for i in indices)
        target_band, current_band = band_for(target_level), band_for(current_level)
        lines = []
        for i in indices:
            mode = skeleton[i - 1] if i - 1 < len(skeleton) else ""
            want = targets[i - 1] if i - 1 < len(targets) else len(paragraphs[i - 1].split())
            gloss = MODE_GUIDE.get(mode, "")
            lines.append(f"[{i}] {mode}, ~{want} words: {gloss}")

        continuity_line = ""
        if prev_tension is not None:
            step = self.config.get('coherence.tension_step_for_transition', 3)
            if prev_tension - target_level >= step:
                continuity_line = (
                    f"The previous scene was {prev_tension:g}/10; this is a deliberate "
                    f"transition to a calmer beat.\n")
            else:
                continuity_line = f"The previous scene was {prev_tension:g}/10.\n"
        direction = (f"LOWER the tension toward the target: {target_band.directive}"
                     if target_level < current_level else
                     f"RAISE the tension toward the target: {target_band.directive}")

        prompt = format_partial_revision_prompt({
            "plan_rules": plan_rules(len(indices), want_words_hint,
                                     sectioned=True),
            "numbered_scene": number_scene(paragraphs),
            "scale_overview": scale_overview(),
            "current_level": f"{current_level:g}", "current_band": current_band.name,
            "target_level": f"{target_level:g}", "target_band": target_band.name,
            "target_definition": target_band.definition,
            "continuity_line": continuity_line,
            "direction_line": direction,
            "target_lines": chr(10).join(lines),
        }, writer_context=writer_context)
        # Only the selected paragraphs come back, so the budget is sized from
        # them rather than from the whole scene.
        want_words = sum(targets[i - 1] if i - 1 < len(targets)
                         else len(paragraphs[i - 1].split()) for i in indices)
        response, _ = self._generate_segment(
            prompt, token_budget_for(max(want_words, 120), self.config))
        revised = parse_revised_blocks(self._strip_llm_header((response or "").strip()))
        # Only what was asked for: a revision addressed elsewhere is not ours.
        revised = {i: t for i, t in revised.items() if i in set(indices)}
        revised, over_length = check_lengths(revised, targets, paragraphs)
        merged, applied = splice(paragraphs, revised)
        if not applied:
            return "", {"applied": 0, "requested": len(indices),
                        "rejected_length": over_length,
                        "reason": "no usable paragraphs returned"}
        before = sum(len(paragraphs[i - 1].split()) for i in revised)
        after = sum(len(t.split()) for t in revised.values())
        meta = {"applied": applied, "requested": len(indices),
                "rejected_length": over_length,
                "words_before": before, "words_after": after,
                "scene_paragraphs": len(merged)}
        if over_length:
            print(f"        {len(over_length)} revision(s) rejected on length "
                  f"({', '.join(str(i) for i in over_length)})")
        return "\n\n".join(merged), meta

    def _format_writer_prompt(self, context: Dict[str, Any]) -> str:
        """Format writer prompt with context.
        
        Args:
            context: Context dictionary
        
        Returns:
            Formatted prompt string
        """
        from .prompts import format_writer_prompt
        return format_writer_prompt(context)
    
    def _parse_scene_response(self, response: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Parse LLM response into scene data.
        
        Args:
            response: Raw LLM response
            context: Original context (for fallback title generation)
        
        Returns:
            Dictionary with text, word_count, and title
        """
        # Clean up response
        text = response.strip()
        
        # Strip obvious meta-reasoning header that some backends may emit
        # (e.g., lines about listing directories or inspecting project files
        #  before starting the actual scene prose). We only remove a leading
        #  block of such lines; once we see normal prose, we keep everything.
        lines = text.split('\n')
        cleaned_lines = []
        skipping_meta = True
        meta_markers = [
            "I'll start by listing the current directory",
            "I'll start by listing the current directory's files",
            "current directory's files",
            "I'll check `docs`",
            "I'll check `work`",
            "Python project, `novel_agent` package",
            "I'm writing a scene for",
        ]
        for line in lines:
            stripped = line.strip()
            if skipping_meta and stripped:
                if any(marker in stripped for marker in meta_markers):
                    # Skip this meta line and continue looking for real prose
                    continue
                else:
                    skipping_meta = False
            if not skipping_meta or not stripped:
                cleaned_lines.append(line)
        text = "\n".join(cleaned_lines).strip()
        
        # Extract title first (before stripping it from text)
        lines = text.split('\n')
        title = self._extract_title(lines, context)
        
        # Strip the LLM-generated title/header from the text to avoid duplication
        # The scene_committer will add its own standardized header
        text = self._strip_llm_header(text)
        
        # Calculate word count
        word_count = len(text.split())
        
        return {
            "text": text,
            "word_count": word_count,
            "title": title
        }
    
    def _extract_title(self, lines: List[str], context: Dict[str, Any]) -> str:
        """Extract or generate scene title.
        
        Args:
            lines: Lines of the scene text
            context: Original context
        
        Returns:
            Scene title
        """
        # Check if first line looks like a title
        # (short, no period at end, possibly markdown header)
        if lines:
            first_line = lines[0].strip()
            
            # Remove markdown header markers
            if first_line.startswith('#'):
                first_line = first_line.lstrip('#').strip()
            
            # If it's short and doesn't end with a period, use it as title
            if len(first_line) < 60 and not first_line.endswith('.'):
                return first_line
        
        # Generate from scene intention
        intention = context.get('scene_intention', '')
        if intention:
            # Use full intention if it's short enough, otherwise truncate smartly
            if len(intention) <= 60:
                title = intention
            else:
                # Truncate at word boundary near 60 chars
                words = intention.split()
                title = ''
                for word in words:
                    if len(title) + len(word) + 1 <= 60:
                        title += (' ' if title else '') + word
                    else:
                        break
            
            # Capitalize first letter and ensure no trailing punctuation
            if title:
                title = title.rstrip('.,;:!?')
                return title[0].upper() + title[1:]
        
        # Fallback to tick number
        tick = context.get('current_tick', 0)
        return f"Scene {tick}"
    
    def _strip_llm_header(self, text: str) -> str:
        """Strip LLM-generated markdown header and metadata from scene text.
        
        The LLM often generates a title like "# Title" followed by metadata
        like "*Scene ID: ...*" and "---". We strip this to avoid duplication
        since the scene_committer adds its own standardized header.
        
        Args:
            text: Raw scene text from LLM
        
        Returns:
            Text with header stripped
        """
        lines = text.split('\n')
        start_index = 0
        
        # Skip leading markdown title (# Title)
        if lines and lines[0].strip().startswith('#'):
            start_index = 1
        
        # Skip blank lines after title
        while start_index < len(lines) and not lines[start_index].strip():
            start_index += 1
        
        # Skip metadata lines (*Scene ID: ...*, *Tick: ...*)
        while start_index < len(lines):
            stripped = lines[start_index].strip()
            if stripped.startswith('*') and stripped.endswith('*'):
                start_index += 1
            else:
                break
        
        # Skip blank lines after metadata
        while start_index < len(lines) and not lines[start_index].strip():
            start_index += 1
        
        # Skip horizontal rule (---)
        if start_index < len(lines) and lines[start_index].strip().startswith('---'):
            start_index += 1
        
        # Skip blank lines after horizontal rule
        while start_index < len(lines) and not lines[start_index].strip():
            start_index += 1
        
        # Return remaining text
        return '\n'.join(lines[start_index:]).strip()

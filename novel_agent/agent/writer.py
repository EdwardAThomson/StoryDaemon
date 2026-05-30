"""Scene writer for generating prose."""

from typing import Dict, Any, List


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
        """Generate scene prose.
        
        Args:
            writer_context: Context dictionary from WriterContextBuilder
        
        Returns:
            Dictionary with:
                - text: Scene prose
                - word_count: Number of words
                - title: Extracted or generated title
        """
        # Format the writer prompt
        prompt = self._format_writer_prompt(writer_context)
        
        # Get max tokens from config
        max_tokens = self.config.get('llm.writer_max_tokens', 3000)
        
        # Call LLM
        response = self.llm.generate(prompt, max_tokens=max_tokens)
        
        # Parse and return scene data
        return self._parse_scene_response(response, writer_context)
    
    def revise_for_tension(self, scene_text: str, target_level: float, current_level: float,
                           writer_context: Dict[str, Any] = None, prev_tension: float = None) -> str:
        """Revise a scene's tension toward `target_level`, keeping the plot outcome.

        Uses the shared 0-10 tension scale (so the instruction matches the grader), the real
        story context, and continuity with the previous scene's tension — a big drop is framed
        as a deliberate transition, not an unmotivated whiplash. Returns cleaned prose, or "".
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
        max_tokens = self.config.get('llm.writer_max_tokens', 3000)
        response = self.llm.generate(prompt, max_tokens=max_tokens)
        return self._strip_llm_header(response.strip())

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

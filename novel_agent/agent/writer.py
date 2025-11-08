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
        
        # Calculate word count
        word_count = len(text.split())
        
        # Extract or generate title
        lines = text.split('\n')
        title = self._extract_title(lines, context)
        
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

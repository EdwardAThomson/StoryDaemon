"""Scene summarization using LLM."""

from typing import List


class SceneSummarizer:
    """Generates concise bullet-point summaries of scenes."""
    
    def __init__(self, llm_interface):
        """Initialize summarizer.
        
        Args:
            llm_interface: LLM interface for text generation
        """
        self.llm = llm_interface
    
    def summarize_scene(self, scene_text: str, max_bullets: int = 5) -> List[str]:
        """Generate bullet-point summary of a scene.
        
        Args:
            scene_text: Full scene text
            max_bullets: Maximum number of bullet points (default: 5)
        
        Returns:
            List of summary bullet points
        """
        prompt = self._build_summary_prompt(scene_text, max_bullets)
        
        # Call LLM
        response = self.llm.send_prompt(prompt)
        
        # Parse bullet points
        bullets = self._parse_bullets(response)
        
        return bullets[:max_bullets]
    
    def _build_summary_prompt(self, scene_text: str, max_bullets: int) -> str:
        """Build prompt for scene summarization.
        
        Args:
            scene_text: Scene text to summarize
            max_bullets: Max bullet points
        
        Returns:
            Formatted prompt
        """
        prompt = f"""Read the following scene and generate {max_bullets} concise bullet points summarizing:
- Key events that occurred
- Important character actions or decisions
- New information revealed
- Emotional or relationship changes

Be specific and factual. Each bullet should be a complete sentence.

Scene:
{scene_text}

Summary (bullet points only, one per line):"""
        
        return prompt
    
    def _parse_bullets(self, response: str) -> List[str]:
        """Parse bullet points from LLM response.
        
        Args:
            response: Raw LLM response
        
        Returns:
            List of cleaned bullet points
        """
        lines = response.strip().split('\n')
        bullets = []
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Remove common bullet markers
            for marker in ['- ', '* ', '• ', '1. ', '2. ', '3. ', '4. ', '5. ']:
                if line.startswith(marker):
                    line = line[len(marker):].strip()
                    break
            
            # Skip if too short
            if len(line) < 10:
                continue
            
            bullets.append(line)
        
        return bullets
    
    def summarize_multiple_scenes(self, scene_texts: List[str]) -> str:
        """Generate an overall summary of multiple scenes.
        
        Args:
            scene_texts: List of scene texts
        
        Returns:
            Overall summary paragraph
        """
        prompt = f"""Read the following {len(scene_texts)} scenes and generate a concise paragraph summarizing the overall story progression.

Scenes:
"""
        for i, text in enumerate(scene_texts, 1):
            prompt += f"\n--- Scene {i} ---\n{text}\n"
        
        prompt += "\nOverall Summary:"
        
        response = self.llm.send_prompt(prompt)
        return response.strip()

"""Scene committer for saving scenes to disk and memory."""

from pathlib import Path
from typing import Dict, Any, List

from novel_agent.memory.entities import Scene


class SceneCommitter:
    """Commits scenes to disk and memory systems."""
    
    def __init__(self, memory_manager, vector_store, summarizer, project_path):
        """Initialize scene committer.
        
        Args:
            memory_manager: MemoryManager instance
            vector_store: VectorStore instance
            summarizer: SceneSummarizer instance
            project_path: Path to project directory
        """
        self.memory = memory_manager
        self.vector = vector_store
        self.summarizer = summarizer
        self.project_path = Path(project_path)
        self.scenes_dir = self.project_path / "scenes"
    
    def commit_scene(
        self,
        scene_data: Dict[str, Any],
        tick: int,
        plan: Dict[str, Any]
    ) -> str:
        """Commit scene to disk and memory.
        
        Args:
            scene_data: From SceneWriter (text, word_count, title)
            tick: Current tick number
            plan: Original plan from planner
        
        Returns:
            Scene ID
        """
        # 1. Generate scene ID
        scene_id = self.memory.generate_id("scene")
        
        # 2. Save markdown file
        markdown_file = self._save_markdown(
            scene_id,
            scene_data["text"],
            scene_data["title"],
            tick
        )
        
        # 3. Generate summary
        summary = self.summarizer.summarize_scene(
            scene_data["text"],
            max_bullets=5
        )
        
        # 4. Extract characters from plan
        characters_present = self._extract_characters(plan)
        
        # 5. Create Scene entity
        scene = Scene(
            id=scene_id,
            tick=tick,
            title=scene_data["title"],
            pov_character_id=plan.get("pov_character", ""),
            location_id=plan.get("target_location", ""),
            markdown_file=str(markdown_file.relative_to(self.project_path)),
            word_count=scene_data["word_count"],
            summary=summary,
            characters_present=characters_present,
            key_events=[],  # Could extract from summary in future
            metadata={"plan_rationale": plan.get("rationale", "")}
        )
        
        # 6. Save scene metadata
        self.memory.save_scene(scene)
        
        # 7. Index in vector database
        self.vector.index_scene(scene)
        
        return scene_id
    
    def _save_markdown(
        self,
        scene_id: str,
        text: str,
        title: str,
        tick: int
    ) -> Path:
        """Save scene text to markdown file.
        
        Args:
            scene_id: Scene ID
            text: Scene prose
            title: Scene title
            tick: Tick number
        
        Returns:
            Path to saved file
        """
        # Ensure scenes directory exists
        self.scenes_dir.mkdir(parents=True, exist_ok=True)
        
        # Create filename
        filename = f"scene_{tick:03d}.md"
        filepath = self.scenes_dir / filename
        
        # Write markdown file with metadata header
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"# {title}\n\n")
            f.write(f"*Scene ID: {scene_id}*  \n")
            f.write(f"*Tick: {tick}*\n\n")
            f.write("---\n\n")
            f.write(text)
            f.write("\n")
        
        return filepath
    
    def _extract_characters(self, plan: Dict[str, Any]) -> List[str]:
        """Extract character IDs from plan.
        
        Args:
            plan: Plan dictionary
        
        Returns:
            List of character IDs present in scene
        """
        characters = set()
        
        # Add POV character
        pov_char = plan.get("pov_character")
        if pov_char:
            characters.add(pov_char)
        
        # TODO: In future, could extract from tool results
        # For example, if character.generate was used, add that character
        # For now, just return POV character
        
        return list(characters)

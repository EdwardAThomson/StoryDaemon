"""Title suggestion command - generate story title ideas using LLM."""
import json
from pathlib import Path
from typing import List, Optional
from datetime import datetime


def build_title_prompt(
    foundation: dict,
    scene_summaries: List[str],
    character_names: List[str],
    themes: List[str],
    count: int = 10,
) -> str:
    """Build prompt for title generation.
    
    Args:
        foundation: Story foundation dict (genre, premise, tone, etc.)
        scene_summaries: List of scene summaries for context
        character_names: List of main character names
        themes: List of story themes
        count: Number of title suggestions to generate
        
    Returns:
        Formatted prompt string
    """
    parts = []
    parts.append("You are a creative writing assistant specializing in book titles.")
    parts.append(f"Generate {count} compelling title suggestions for this story.\n")
    
    # Foundation info
    if foundation:
        parts.append("## Story Foundation")
        if foundation.get("genre"):
            parts.append(f"**Genre:** {foundation['genre']}")
        if foundation.get("premise"):
            parts.append(f"**Premise:** {foundation['premise']}")
        if foundation.get("tone"):
            parts.append(f"**Tone:** {foundation['tone']}")
        if foundation.get("setting"):
            parts.append(f"**Setting:** {foundation['setting']}")
        parts.append("")
    
    # Themes
    if themes:
        parts.append("## Themes")
        parts.append(", ".join(themes))
        parts.append("")
    
    # Characters
    if character_names:
        parts.append("## Main Characters")
        parts.append(", ".join(character_names[:5]))  # Top 5
        parts.append("")
    
    # Story content (sample of summaries)
    if scene_summaries:
        parts.append("## Story Summary (sample scenes)")
        # Take first few and last few for beginning/end context
        sample = scene_summaries[:3] + scene_summaries[-2:] if len(scene_summaries) > 5 else scene_summaries
        for summary in sample:
            if summary:
                parts.append(f"- {summary}")
        parts.append("")
    
    parts.append("## Requirements")
    parts.append("- Generate exactly {count} title suggestions".format(count=count))
    parts.append("- Titles should be evocative and memorable")
    parts.append("- Mix of styles: poetic, punchy, mysterious, thematic")
    parts.append("- Each title on its own line, numbered 1-{count}".format(count=count))
    parts.append("- No explanations, just the titles")
    parts.append("")
    parts.append("## Title Suggestions")
    
    return "\n".join(parts)


def parse_titles(response: str) -> List[str]:
    """Parse title suggestions from LLM response.
    
    Args:
        response: Raw LLM response text
        
    Returns:
        List of title strings
    """
    titles = []
    for line in response.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        # Remove numbering (1. or 1) or - prefix)
        if line[0].isdigit():
            # Strip "1. " or "1) " prefix
            for sep in [". ", ") ", ": ", " "]:
                if sep in line:
                    _, _, rest = line.partition(sep)
                    if rest:
                        line = rest.strip()
                        break
        elif line.startswith("-"):
            line = line[1:].strip()
        
        # Remove quotes if present
        if line.startswith('"') and line.endswith('"'):
            line = line[1:-1]
        elif line.startswith("'") and line.endswith("'"):
            line = line[1:-1]
        
        if line:
            titles.append(line)
    
    return titles


def generate_titles(
    project_dir: Path,
    count: int = 10,
    output_file: Optional[Path] = None,
) -> List[str]:
    """Generate title suggestions for the story.
    
    Args:
        project_dir: Path to project directory
        count: Number of titles to generate
        output_file: Optional file to write suggestions to
        
    Returns:
        List of title suggestions
    """
    from ..project import load_project_state, get_project_config
    from ...tools.llm_interface import initialize_llm, send_prompt
    from ...memory.manager import MemoryManager
    
    # Load state and config
    state = load_project_state(str(project_dir))
    config = get_project_config(str(project_dir))
    
    # Initialize LLM
    backend = config.get("llm.backend", "codex")
    codex_bin = config.get("llm.codex_bin_path", "codex")
    model = config.get("llm.model") or config.get("llm.openai_model", "gpt-5.1")
    
    try:
        initialize_llm(backend=backend, codex_bin=codex_bin, model=model)
    except RuntimeError as e:
        print(f"❌ Failed to initialize LLM: {e}")
        return []
    
    # Gather context
    foundation = state.get("story_foundation", {})
    themes = foundation.get("themes", [])
    
    # Get character names
    memory = MemoryManager(project_dir)
    character_ids = memory.list_characters()
    character_names = []
    for cid in character_ids[:10]:  # Top 10
        char = memory.load_character(cid)
        if char:
            character_names.append(char.name)
    
    # Get scene summaries
    scene_ids = memory.list_scenes()
    scene_summaries = []
    for sid in scene_ids:
        scene = memory.load_scene(sid)
        if scene and scene.summary:
            # Join summary list into single string
            summary_text = " ".join(scene.summary) if isinstance(scene.summary, list) else scene.summary
            scene_summaries.append(summary_text)
    
    # Build and send prompt
    prompt = build_title_prompt(
        foundation=foundation,
        scene_summaries=scene_summaries,
        character_names=character_names,
        themes=themes,
        count=count,
    )
    
    print(f"🎯 Generating {count} title suggestions...")
    
    try:
        response = send_prompt(prompt, max_tokens=500)
        titles = parse_titles(response)
    except Exception as e:
        print(f"❌ Error generating titles: {e}")
        return []
    
    if not titles:
        print("❌ No titles could be parsed from response")
        return []
    
    # Output results
    print(f"\n📚 Title Suggestions:\n")
    for i, title in enumerate(titles, 1):
        print(f"  {i}. {title}")
    
    # Write to file if requested
    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(f"# Title Suggestions for {state.get('novel_name', 'Story')}\n")
            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for i, title in enumerate(titles, 1):
                f.write(f"{i}. {title}\n")
        print(f"\n✅ Saved to: {output_file}")
    
    return titles

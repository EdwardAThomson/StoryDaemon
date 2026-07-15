"""The chapter seam: map scene files to book chapters.

v1 maps scene to chapter 1:1. A future chapter-grouping pass replaces only
build_chapters(); everything downstream (epub.py, pdf.py) consumes Chapter
objects and never touches scene files directly.
"""
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class Chapter:
    number: int
    title: str
    html_body: str
    source_file: Path


def extract_scene_title(content: str) -> Optional[str]:
    """Extract the scene title from the first line's `# Title` header.

    Returns None when the first line is not a markdown h1, so callers can
    fall back to "Chapter N".
    """
    if not content:
        return None
    first_line = content.lstrip().split("\n", 1)[0].strip()
    if first_line.startswith("# "):
        title = first_line[2:].strip()
        return title or None
    return None


def strip_scene_header(content: str) -> str:
    """Strip the scene header (title, metadata lines, `---` separator).

    Mirrors read_scene_content(strip_header=True) in cli/commands/compile.py,
    including its leniency: no separator means the full content comes back.
    """
    separator_match = re.search(r'^---\s*$', content, re.MULTILINE)
    if separator_match:
        return content[separator_match.end():].strip()
    return content.strip()


def escape_html(text: str) -> str:
    """Escape only `&<>`: EPUB XHTML must be well-formed XML, but em-dashes,
    smart quotes and other unicode pass through untouched (UTF-8 throughout).
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def prose_to_html(prose: str) -> str:
    """Convert scene prose to HTML paragraphs.

    Escapes `&<>`, splits on blank lines into <p> elements, and converts
    markdown emphasis non-greedily: **bold** before *italic*, so the
    single-star pattern never eats bold markers.
    """
    paragraphs = []
    for block in re.split(r'\n\s*\n', prose):
        block = block.strip()
        if not block:
            continue
        block = escape_html(block)
        block = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', block, flags=re.DOTALL)
        block = re.sub(r'\*(.+?)\*', r'<em>\1</em>', block, flags=re.DOTALL)
        paragraphs.append(f"<p>{block}</p>")
    return "\n".join(paragraphs)


def build_chapters(scene_files: List[Path]) -> List[Chapter]:
    """Map scene files to chapters, 1:1 in v1.

    Chapters renumber sequentially from 1 within the given subset, so
    --scenes selections read correctly (titles come from scene headers).
    """
    chapters = []
    for number, scene_file in enumerate(scene_files, 1):
        try:
            content = scene_file.read_text(encoding="utf-8").strip()
        except Exception as e:
            content = f"[Error reading scene: {e}]"
        title = extract_scene_title(content) or f"Chapter {number}"
        body = strip_scene_header(content)
        chapters.append(Chapter(
            number=number,
            title=title,
            html_body=prose_to_html(body),
            source_file=scene_file,
        ))
    return chapters

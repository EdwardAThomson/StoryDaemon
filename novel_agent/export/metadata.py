"""Book-level metadata: state.json + config, with fallbacks for old projects.

Mapping (docs/EPUB_PDF_EXPORT_PLAN.md section 4): title from novel_name,
author/language from the config export section, identifier from project_id,
description/subjects/title-page extras from story_foundation. A project with
no story_foundation degrades to title/author/identifier only: no crash, no
empty elements.
"""
import json
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional


@dataclass
class BookMetadata:
    title: str = "Untitled"
    author: str = "StoryDaemon"
    identifier: str = ""
    language: str = "en"
    description: Optional[str] = None
    subjects: List[str] = field(default_factory=list)
    date: str = ""
    # Title-page extras (PDF byline block); None means omit the line.
    genre: Optional[str] = None
    setting: Optional[str] = None
    tone: Optional[str] = None


def build_book_metadata(project_dir: Path, config=None) -> BookMetadata:
    """Build BookMetadata from the project's state.json and the config.

    Args:
        project_dir: Path to project directory
        config: Config object (or None); read via dot-notation get()

    Returns:
        BookMetadata with every field populated or deliberately None
    """
    meta = BookMetadata()

    if config is not None:
        meta.author = config.get('export.author', meta.author) or meta.author
        meta.language = config.get('export.language', meta.language) or meta.language

    state = {}
    state_file = project_dir / "state.json"
    if state_file.exists():
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f) or {}
        except Exception:
            state = {}

    meta.title = state.get('novel_name') or "Untitled"

    project_id = state.get('project_id')
    if project_id:
        meta.identifier = f"urn:storydaemon:{project_id}"
    else:
        meta.identifier = uuid.uuid4().urn

    created_at = state.get('created_at') or ""
    # Date part only: created_at is an ISO timestamp like 2026-07-15T12:29:00.
    meta.date = created_at.split('T')[0] if created_at else date.today().isoformat()

    foundation = state.get('story_foundation') or {}
    if foundation:
        meta.description = foundation.get('premise') or None
        meta.genre = foundation.get('genre') or None
        meta.setting = foundation.get('setting') or None
        meta.tone = foundation.get('tone') or None
        subjects = []
        if meta.genre:
            subjects.append(meta.genre)
        for theme in foundation.get('themes') or []:
            if theme:
                subjects.append(theme)
        meta.subjects = subjects

    return meta

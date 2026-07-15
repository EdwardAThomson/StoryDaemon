"""Unit tests for book metadata and the EPUB writer, plus the compile dispatch.

The EPUB assertions open the written file with zipfile and parse a chapter
with ElementTree: that parse is the guard that catches escaping bugs.
"""
import json
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from novel_agent.cli.commands.compile import (
    compile_manuscript,
    default_output_for_format,
)
from novel_agent.configs.config import Config
from novel_agent.export import build_chapters, build_book_metadata, write_epub


SCENE_TEMPLATE = """\
# {title}

*Scene ID: {scene_id}*
*Tick: {tick}*

---

{prose}
"""


def make_project(tmp_path, num_scenes=3, foundation=True, state=True):
    project_dir = tmp_path / "test_novel"
    (project_dir / "scenes").mkdir(parents=True)
    (project_dir / "memory" / "characters").mkdir(parents=True)
    (project_dir / "memory" / "locations").mkdir(parents=True)

    if state:
        state_data = {
            "novel_name": "The Alcyone",
            "project_id": "abc123",
            "created_at": "2026-07-15T12:29:00.071264",
        }
        if foundation:
            state_data["story_foundation"] = {
                "genre": "historical adventure",
                "premise": "A survey brig searches for a lost expedition.",
                "setting": "A volcanic archipelago, 1871",
                "tone": "tense & atmospheric",
                "themes": ["duty", "dread"],
            }
        (project_dir / "state.json").write_text(json.dumps(state_data))

    for i in range(num_scenes):
        scene = project_dir / "scenes" / f"scene_{i:03d}.md"
        scene.write_text(
            SCENE_TEMPLATE.format(
                title=f"Scene Title {i}",
                scene_id=f"S{i:03d}",
                tick=i,
                prose=f"Prose & more prose—scene {i} with “smart quotes”.",
            ),
            encoding="utf-8",
        )
    return project_dir


def epub_chapter_names(path):
    with zipfile.ZipFile(path) as zf:
        return sorted(
            n for n in zf.namelist()
            if n.split("/")[-1].startswith("chapter_") and n.endswith(".xhtml")
        )


# ---- build_book_metadata --------------------------------------------------------

def test_build_book_metadata_full_project(tmp_path):
    project_dir = make_project(tmp_path)
    meta = build_book_metadata(project_dir, Config())

    assert meta.title == "The Alcyone"
    assert meta.author == "StoryDaemon"
    assert meta.identifier == "urn:storydaemon:abc123"
    assert meta.language == "en"
    assert meta.description == "A survey brig searches for a lost expedition."
    assert meta.subjects == ["historical adventure", "duty", "dread"]
    assert meta.date == "2026-07-15"
    assert meta.genre == "historical adventure"
    assert meta.setting == "A volcanic archipelago, 1871"
    assert meta.tone == "tense & atmospheric"


def test_build_book_metadata_config_overrides(tmp_path):
    project_dir = make_project(tmp_path)
    config = Config()
    config.set("export.author", "E. A. Thomson")
    config.set("export.language", "en-GB")

    meta = build_book_metadata(project_dir, config)

    assert meta.author == "E. A. Thomson"
    assert meta.language == "en-GB"


def test_build_book_metadata_missing_foundation(tmp_path):
    # Old projects without story_foundation degrade, no crash.
    project_dir = make_project(tmp_path, foundation=False)
    meta = build_book_metadata(project_dir, Config())

    assert meta.title == "The Alcyone"
    assert meta.description is None
    assert meta.subjects == []
    assert meta.genre is None


def test_build_book_metadata_missing_state(tmp_path):
    project_dir = make_project(tmp_path, state=False)
    meta = build_book_metadata(project_dir, Config())

    assert meta.title == "Untitled"
    assert meta.identifier.startswith("urn:uuid:")
    assert meta.date  # falls back to today


# ---- write_epub -----------------------------------------------------------------

def test_write_epub_structure(tmp_path):
    project_dir = make_project(tmp_path, num_scenes=3)
    scene_files = sorted((project_dir / "scenes").glob("scene_*.md"))
    output = tmp_path / "book.epub"

    result = write_epub(
        output,
        build_book_metadata(project_dir, Config()),
        build_chapters(scene_files),
    )

    assert result is True
    with zipfile.ZipFile(output) as zf:
        assert zf.read("mimetype").decode() == "application/epub+zip"
        assert "META-INF/container.xml" in zf.namelist()

        opf_name = next(n for n in zf.namelist() if n.endswith(".opf"))
        opf = zf.read(opf_name).decode("utf-8")
        assert "The Alcyone" in opf
        assert "StoryDaemon" in opf
        assert "A survey brig searches for a lost expedition." in opf

    assert len(epub_chapter_names(output)) == 3


def test_write_epub_chapter_is_wellformed_xml(tmp_path):
    # The escaping guard: prose contains & < > and unicode; the chapter
    # XHTML must still parse as XML.
    project_dir = make_project(tmp_path, num_scenes=1)
    scene = project_dir / "scenes" / "scene_000.md"
    scene.write_text(
        SCENE_TEMPLATE.format(
            title="Salt & Smoke <II>",
            scene_id="S000",
            tick=0,
            prose="Fish & chips, 1 < 2, 3 > 2—and **bold** *waves*.",
        ),
        encoding="utf-8",
    )
    output = tmp_path / "book.epub"

    write_epub(
        output,
        build_book_metadata(project_dir, Config()),
        build_chapters([scene]),
    )

    with zipfile.ZipFile(output) as zf:
        chapter_name = epub_chapter_names(output)[0]
        root = ET.fromstring(zf.read(chapter_name))
    text = ET.tostring(root, encoding="unicode")
    assert "Salt &amp; Smoke" in text
    assert "—" in text


def test_write_epub_appendix_chapter(tmp_path):
    project_dir = make_project(tmp_path, num_scenes=2)
    scene_files = sorted((project_dir / "scenes").glob("scene_*.md"))
    output = tmp_path / "book.epub"

    write_epub(
        output,
        build_book_metadata(project_dir, Config()),
        build_chapters(scene_files),
        appendix_html="<p><strong>Characters:</strong> 2</p>",
    )

    with zipfile.ZipFile(output) as zf:
        appendix_name = next(
            n for n in zf.namelist() if n.endswith("appendix.xhtml")
        )
        assert "Characters" in zf.read(appendix_name).decode("utf-8")


# ---- compile_manuscript dispatch --------------------------------------------------

def test_compile_manuscript_epub(tmp_path):
    project_dir = make_project(tmp_path, num_scenes=3)
    output = tmp_path / "book.epub"

    result = compile_manuscript(project_dir, output, format="epub", config=Config())

    assert result is True
    assert len(epub_chapter_names(output)) == 3


def test_compile_manuscript_epub_no_metadata_skips_appendix(tmp_path):
    project_dir = make_project(tmp_path, num_scenes=1)
    output = tmp_path / "book.epub"

    compile_manuscript(project_dir, output, format="epub",
                       include_metadata=False, config=Config())

    with zipfile.ZipFile(output) as zf:
        assert not any(n.endswith("appendix.xhtml") for n in zf.namelist())


def test_compile_manuscript_epub_scene_subset(tmp_path):
    project_dir = make_project(tmp_path, num_scenes=4)
    output = tmp_path / "book.epub"

    result = compile_manuscript(project_dir, output, format="epub",
                                scene_range="1-2", config=Config())

    assert result is True
    assert len(epub_chapter_names(output)) == 2


def test_compile_manuscript_epub_empty_project(tmp_path, capsys):
    project_dir = tmp_path / "empty_novel"
    (project_dir / "scenes").mkdir(parents=True)

    result = compile_manuscript(project_dir, tmp_path / "book.epub",
                                format="epub", config=Config())

    assert result is False
    assert "No scenes found" in capsys.readouterr().out


def test_default_output_for_format():
    assert default_output_for_format("markdown") == "manuscript.md"
    assert default_output_for_format("html") == "manuscript.html"
    assert default_output_for_format("prose") == "manuscript.txt"
    assert default_output_for_format("epub") == "manuscript.epub"
    assert default_output_for_format("pdf") == "manuscript.pdf"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

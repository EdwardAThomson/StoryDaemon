"""Unit tests for the export chapter seam (novel_agent/export/chapters.py)."""
import pytest

from novel_agent.export.chapters import (
    Chapter,
    build_chapters,
    escape_html,
    extract_scene_title,
    prose_to_html,
    strip_scene_header,
)


SCENE_TEMPLATE = """\
# {title}

*Scene ID: {scene_id}*
*Tick: {tick}*

---

{prose}
"""


def make_scene(tmp_path, number, title, prose):
    scene_file = tmp_path / f"scene_{number:03d}.md"
    scene_file.write_text(
        SCENE_TEMPLATE.format(
            title=title, scene_id=f"S{number:03d}", tick=number, prose=prose
        ),
        encoding="utf-8",
    )
    return scene_file


# ---- title extraction ---------------------------------------------------------

def test_extract_scene_title():
    assert extract_scene_title("# The Storm Breaks\n\nProse.") == "The Storm Breaks"


def test_extract_scene_title_no_header():
    assert extract_scene_title("Just prose, no header.") is None


def test_extract_scene_title_empty():
    assert extract_scene_title("") is None
    assert extract_scene_title("# ") is None


# ---- header stripping -----------------------------------------------------------

def test_strip_scene_header():
    content = "# Title\n\n*Scene ID: S000*\n*Tick: 0*\n\n---\n\nThe prose begins."
    assert strip_scene_header(content) == "The prose begins."


def test_strip_scene_header_no_separator_falls_back_to_full_content():
    # Mirrors read_scene_content leniency: malformed header means full content.
    content = "No header here, just prose."
    assert strip_scene_header(content) == content


# ---- escaping and emphasis ------------------------------------------------------

def test_escape_html_ampersand_and_angles():
    assert escape_html("Fish & Chips <now> 1 > 0") == "Fish &amp; Chips &lt;now&gt; 1 &gt; 0"


def test_prose_to_html_escapes_entities():
    html = prose_to_html("Salt & smoke <rising>.")
    assert html == "<p>Salt &amp; smoke &lt;rising&gt;.</p>"


def test_prose_to_html_unicode_passthrough():
    # Em-dashes and smart quotes must survive: only &<> are escaped.
    prose = "Morning light made promises—flat water, “clean” horizons’ end."
    html = prose_to_html(prose)
    assert "—" in html
    assert "“" in html
    assert "’" in html


def test_prose_to_html_paragraph_split():
    html = prose_to_html("First paragraph.\n\nSecond paragraph.")
    assert html == "<p>First paragraph.</p>\n<p>Second paragraph.</p>"


def test_prose_to_html_emphasis_conversion():
    html = prose_to_html("A **bold** word and an *italic* word.")
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "*" not in html


def test_prose_to_html_emphasis_non_greedy():
    html = prose_to_html("*one* plain *two*")
    assert html == "<p><em>one</em> plain <em>two</em></p>"


# ---- build_chapters -------------------------------------------------------------

def test_build_chapters_maps_scene_to_chapter(tmp_path):
    files = [
        make_scene(tmp_path, 0, "The Sounding", "Lead line prose."),
        make_scene(tmp_path, 1, "The Meridian Mark", "Charred canvas prose."),
    ]
    chapters = build_chapters(files)

    assert len(chapters) == 2
    assert chapters[0] == Chapter(
        number=1,
        title="The Sounding",
        html_body="<p>Lead line prose.</p>",
        source_file=files[0],
    )
    assert chapters[1].number == 2
    assert chapters[1].title == "The Meridian Mark"


def test_build_chapters_subset_renumbers_from_one(tmp_path):
    # A --scenes subset renumbers 1..N; titles still come from the headers.
    files = [
        make_scene(tmp_path, 5, "Fifth Scene", "Prose five."),
        make_scene(tmp_path, 9, "Ninth Scene", "Prose nine."),
    ]
    chapters = build_chapters(files)

    assert [c.number for c in chapters] == [1, 2]
    assert [c.title for c in chapters] == ["Fifth Scene", "Ninth Scene"]


def test_build_chapters_title_fallback(tmp_path):
    scene_file = tmp_path / "scene_000.md"
    scene_file.write_text("No header, just prose.", encoding="utf-8")

    chapters = build_chapters([scene_file])

    assert chapters[0].title == "Chapter 1"
    assert chapters[0].html_body == "<p>No header, just prose.</p>"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

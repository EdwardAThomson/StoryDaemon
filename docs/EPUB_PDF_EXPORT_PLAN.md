# EPUB and PDF Export: Implementation Plan

**Status:** IMPLEMENTED same day (all 7 steps; 36 tests; real EPUB and PDF
rendered from the Slice 4 test novel). Kept as the design record; deviations
noted in the implementing commit.
**Date:** 2026-07-15
**Serves:** `novel compile` (novel_agent/cli/commands/compile.py)
**Decisions already made:** ebooklib is the default EPUB route; WeasyPrint
is the PDF engine as an optional `[export]` extra (needs Pango/Cairo system
libs, never a hard dependency); pandoc used opportunistically if present;
scene = chapter for v1 with a clean seam for future chapter grouping; CLI
surface is `--format epub|pdf` on the existing command.

## Context findings (verified in repo)

- `compile_manuscript()` already dispatches on format and has a dead `pdf`
  branch ("requires pandoc (not yet implemented)"): that branch gets
  replaced.
- Scene files start with `# <Title>`, then `*Scene ID:*` / `*Tick:*` lines,
  then `---`, then prose. `read_scene_content(strip_header=True)` strips
  through the separator but discards the title; chapter titles need a small
  new extractor.
- Prose contains markdown emphasis and em-dashes; the existing
  `compile_to_html` neither escapes HTML nor converts emphasis. EPUB XHTML
  must be well-formed XML, so a shared escaping/emphasis helper is required.
- Foundation lives in `state.json` under `story_foundation` (genre,
  premise, protagonist_archetype, setting, tone, themes, primary_goal);
  `novel_name`, `project_id`, `created_at` are top-level.
- House "not installed" pattern: `shutil.which` + RuntimeError with an
  install pointer; CLI-level failures print a `❌` line and return False.
- setup.py has `extras_require={"dev": ...}`; neither ebooklib nor
  weasyprint is installed today. No `pytest.importorskip` usage exists yet;
  this feature introduces the pattern.

## 1. Files to create / modify

New package `novel_agent/export/` (export logic stays out of the CLI
command body; `compile.py` remains the dispatcher):

| File | Responsibility |
|---|---|
| `export/__init__.py` | Re-export `build_chapters`, `build_book_metadata`, `write_epub`, `write_pdf` |
| `export/chapters.py` | The chapter seam. `Chapter` dataclass (number, title, html_body, source_file); `build_chapters(scene_files)` maps scene to chapter 1:1 in v1 (a future grouping pass replaces only this function); `extract_scene_title` (line-1 `# Title`, fallback "Chapter N"); `prose_to_html` (escape `&<>`, blank-line split into `<p>`, non-greedy `**bold**`/`*italic*` conversion, unicode passthrough) |
| `export/metadata.py` | `BookMetadata` dataclass + `build_book_metadata(project_dir, config)` reading state.json with all fallbacks (section 4) |
| `export/epub.py` | `write_epub(...)`: ebooklib at module top (core dep). dc metadata, title-page XHTML, one `EpubHtml` per chapter, optional appendix chapter, TOC + spine + NCX/nav, embedded book CSS constant |
| `export/pdf.py` | `write_pdf(...)`: print-oriented HTML doc (title page + chapters, reusing chapters.py), `PRINT_CSS` embedded constant. Engine selection: try `import weasyprint` inside the function (catch ImportError AND OSError, which WeasyPrint raises when Pango/Cairo are missing); else `shutil.which("pandoc")` shell-out on tempfile HTML; else graceful error, return False |

Modify: `compile.py` (replace dead pdf branch, add epub branch, binary
output written before the text-open block, `default_output_for_format`
helper), `cli/main.py` (`--format` help, `--output` default None resolved
per format, backward compatible), `configs/config.py` (new `export`
section), `setup.py`/`requirements.txt` (section 3), ROADMAP.md when done.

Tests: `tests/unit/test_export_chapters.py`, `test_export_epub.py`,
`test_export_pdf.py`.

## 2. CLI surface and config

```
novel compile --format epub                      # -> manuscript.epub
novel compile --format pdf -o draft.pdf
novel compile --format epub --scenes 1-10 --no-metadata
```

`--scenes` filters as today; chapters renumber sequentially from 1 within
the subset (titles come from scene headers so subsets read correctly).
`--include-metadata` (default True): appendix chapter in EPUB, appendix
page in PDF; `--no-metadata` yields the reader-clean book.

```python
'export': {
    'author': 'StoryDaemon',   # dc:creator / title-page byline
    'language': 'en',          # dc:language and html lang (enables hyphenation)
    'page_size': 'a5',         # @page size for PDF; any CSS size token
    'pdf_engine': 'auto',      # auto | weasyprint | pandoc
}
```

## 3. Dependency strategy

- `install_requires` gains `ebooklib>=0.18,<1.0` (pulls lxml + six, wheels
  everywhere, no system libs). Mirrored in requirements.txt.
- `extras_require["export"]` gains `weasyprint>=61`; never a hard dep.
- Graceful error text (house `❌` convention):

```
❌ PDF export requires WeasyPrint (or pandoc).
   Install with: pip install storydaemon[export]
   WeasyPrint also needs the Pango/Cairo system libraries — see
   https://doc.courtbouillon.org/weasyprint/stable/first_steps.html
   Alternatively, install pandoc and it will be used automatically.
```

- Pandoc is a silent bonus, never advertised as the primary route.

## 4. Metadata mapping

| Book field | Source | Fallback |
|---|---|---|
| Title | `state.novel_name` | "Untitled" |
| Author | config `export.author` | "StoryDaemon" |
| dc:identifier | `urn:storydaemon:{project_id}` | uuid4 urn |
| dc:language | config `export.language` | en |
| dc:description | `story_foundation.premise` | omit element |
| dc:subject (repeated) | genre + each theme | omit |
| dc:date | `state.created_at` (date part) | today |
| PDF title page | title, byline, genre/setting/tone line, premise as epigraph | title + byline only |

Missing `story_foundation` entirely (old projects) degrades to
title/author/identifier only: no crash, no empty XML elements.

## 5. Print stylesheet key decisions

- Page: `@page { size: a5; margin: 20mm 18mm; @bottom-center page counter;
  @top-center running book title (via string-set on the title h1) }`;
  `@page :first` suppresses header/footer on the title page. A named
  chapter page (no header on chapter openers) is a refinement v1 can skip.
- Front matter: title page with `page-break-after: always`; each chapter
  `page-break-before: always`, chapter title with a ~2in drop in the
  classic novel style.
- Body: Georgia/Liberation Serif 11pt, line-height 1.5, justified,
  `hyphens: auto` (works in WeasyPrint when html lang is set); first
  paragraph of a chapter unindented, subsequent `text-indent: 1.5em`.
- Widows/orphans: `p { orphans: 2; widows: 2; }` (supported).
- Scene breaks: `.scene-break` rendering `* * *`, unused while
  scene = chapter but defined now so the future grouping pass touches only
  chapters.py.

## 6. Test plan

Base suite (ebooklib becomes a core dep, so these run everywhere):

- chapters: title extraction + fallback; header stripping; escaping of
  `&<>`; em-dash/smart-quote passthrough; emphasis conversion; subset
  renumbering.
- epub: build a tmp project, `write_epub`, then open with `zipfile`:
  assert `mimetype` (`application/epub+zip`), `META-INF/container.xml`,
  OPF contains dc:title/dc:creator/premise; chapter XHTML count == scene
  count; ElementTree-parse one chapter to prove well-formed XHTML (the
  test that catches escaping bugs). Missing-foundation project exports;
  empty project returns False via the existing "No scenes found" path.
- pdf (fake-based): inject a fake `weasyprint` module into `sys.modules`
  recording the HTML/CSS handed to it (assert title, chapter titles, page
  size token); graceful-error test (import failure + no pandoc -> False +
  message); pandoc path (fake `shutil.which` + fake `subprocess.run`).

Extra-installed only: one real-render test behind
`pytest.importorskip("weasyprint")`: assert output starts with `%PDF-`.
First importorskip in the suite; note the precedent in the PR.

## 7. Edge cases

- Empty project / no scenes dir: existing early returns cover it; test it.
- Scene-range subsets: renumber 1..N; TOC from the subset only.
- Unicode: XML-escape only `&<>`; UTF-8 throughout; em-dashes and smart
  quotes must survive round-trip.
- Very long single scene: one XHTML per chapter is fine into hundreds of
  KB; no splitting in v1 (documented limit).
- Missing foundation / state.json: section 4 fallbacks; minimal title page.
- Malformed scene header: title falls back to "Chapter N", body falls back
  to full content (mirrors `read_scene_content` leniency).
- pandoc-only PDF path: loses WeasyPrint-only CSS effects; acceptable for
  the opportunistic route.

## 8. Build order and effort

| Step | Work | Est. |
|---|---|---|
| 1 | chapters.py + tests | 1.5 h |
| 2 | metadata.py + tests | 1 h |
| 3 | deps: ebooklib core, `[export]` extra | 0.5 h |
| 4 | epub.py + zip/OPF/XHTML tests | 2.5 h |
| 5 | pdf.py + PRINT_CSS + engine selection + fake tests | 2.5 h |
| 6 | compile.py dispatch + CLI + config + integration test | 1.5 h |
| 7 | importorskip render test, manual pass, docs touch-up | 1 h |
| | **Total** | **~10.5 h** |

Steps 1-4 ship EPUB alone as a coherent increment if PDF slips.

## 9. Risks and maintainer decisions

Risks: WeasyPrint's system-library support burden (mitigated by the extra
plus error text; both ImportError and OSError handled); ebooklib brings
lxml as the first new compiled transitive dep (wheels ubiquitous, low
risk, state it in the PR); EPUB XHTML strictness (the ElementTree test is
the guard; run epubcheck once manually before merge).

Decided at planning review (2026-07-15):

1. **ebooklib goes in core `install_requires`** so EPUB tests run in the
   base suite.
2. **PDF default page size: A5** (provisional; maintainer can override
   with one word in `export.page_size`, e.g. `'6in 9in'` for US Trade if
   print-on-demand ever matters).

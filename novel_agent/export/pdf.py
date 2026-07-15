"""PDF writer: WeasyPrint preferred, pandoc opportunistic, graceful otherwise.

WeasyPrint is an optional [export] extra because it needs the Pango/Cairo
system libraries; it is imported inside write_pdf and both ImportError and
OSError are treated as "not available" (OSError is what WeasyPrint raises
when the system libraries are missing). pandoc, if installed, is a silent
bonus route, never the advertised one.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from .chapters import Chapter, escape_html
from .metadata import BookMetadata

# The page size token is substituted at render time from config
# export.page_size (any CSS size token, e.g. 'a5' or '6in 9in').
_PAGE_SIZE_TOKEN = "__PAGE_SIZE__"

PRINT_CSS = """\
@page {
    size: __PAGE_SIZE__;
    margin: 20mm 18mm;
    @bottom-center { content: counter(page); }
    @top-center { content: string(book-title); }
}
@page :first {
    @bottom-center { content: none; }
    @top-center { content: none; }
}
body {
    font-family: Georgia, "Liberation Serif", serif;
    font-size: 11pt;
    line-height: 1.5;
    text-align: justify;
    hyphens: auto;
}
p {
    margin: 0;
    text-indent: 1.5em;
    orphans: 2;
    widows: 2;
}
h1 + p, .title-page p {
    text-indent: 0;
}
.title-page {
    page-break-after: always;
    text-align: center;
    margin-top: 35%;
}
h1.book-title {
    string-set: book-title content();
    font-size: 24pt;
    margin-bottom: 0.5em;
}
.byline {
    font-style: italic;
    font-size: 13pt;
}
.foundation-line {
    margin-top: 2em;
    font-size: 10pt;
    color: #444;
}
.epigraph {
    font-style: italic;
    margin-top: 4em;
}
section.chapter {
    page-break-before: always;
}
section.chapter h1 {
    margin-top: 2in;
    margin-bottom: 1.5em;
    text-align: center;
    font-size: 16pt;
}
.scene-break {
    text-align: center;
    text-indent: 0;
    margin: 1em 0;
}
.scene-break::before {
    content: "* * *";
}
"""

MISSING_ENGINE_MESSAGE = """\
❌ PDF export requires WeasyPrint (or pandoc).
   Install with: pip install storydaemon[export]
   WeasyPrint also needs the Pango/Cairo system libraries: see
   https://doc.courtbouillon.org/weasyprint/stable/first_steps.html
   Alternatively, install pandoc and it will be used automatically."""


def _title_page_html(metadata: BookMetadata) -> str:
    parts = ['<section class="title-page">']
    parts.append(f'<h1 class="book-title">{escape_html(metadata.title)}</h1>')
    parts.append(f'<p class="byline">{escape_html(metadata.author)}</p>')
    foundation_bits = [b for b in (metadata.genre, metadata.setting, metadata.tone) if b]
    if foundation_bits:
        line = escape_html(" | ".join(foundation_bits))
        parts.append(f'<p class="foundation-line">{line}</p>')
    if metadata.description:
        parts.append(f'<p class="epigraph">{escape_html(metadata.description)}</p>')
    parts.append("</section>")
    return "\n".join(parts)


def build_print_html(metadata: BookMetadata, chapters: List[Chapter],
                     appendix_html: Optional[str] = None,
                     page_size: str = "a5") -> str:
    """Build the single print-oriented HTML document (CSS embedded)."""
    css = PRINT_CSS.replace(_PAGE_SIZE_TOKEN, page_size)
    parts = [
        "<!DOCTYPE html>",
        # lang enables hyphenation in WeasyPrint (hyphens: auto).
        f'<html lang="{escape_html(metadata.language)}">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>{escape_html(metadata.title)}</title>",
        f"<style>\n{css}</style>",
        "</head>",
        "<body>",
        _title_page_html(metadata),
    ]
    for chapter in chapters:
        parts.append('<section class="chapter">')
        parts.append(f"<h1>{escape_html(chapter.title)}</h1>")
        parts.append(chapter.html_body)
        parts.append("</section>")
    if appendix_html:
        parts.append('<section class="chapter">')
        parts.append("<h1>Appendix</h1>")
        parts.append(appendix_html)
        parts.append("</section>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def _render_with_weasyprint(html: str, output_path: Path) -> bool:
    try:
        import weasyprint
    except (ImportError, OSError):
        # OSError covers a pip-installed WeasyPrint whose Pango/Cairo
        # system libraries are missing.
        return False
    weasyprint.HTML(string=html).write_pdf(str(output_path))
    return True


def _render_with_pandoc(html: str, output_path: Path) -> bool:
    pandoc = shutil.which("pandoc")
    if not pandoc:
        return False
    tmp = tempfile.NamedTemporaryFile(
        mode='w', suffix='.html', delete=False, encoding='utf-8')
    try:
        tmp.write(html)
        tmp.close()
        result = subprocess.run(
            [pandoc, tmp.name, "-o", str(output_path)],
            capture_output=True, text=True,
        )
    finally:
        os.unlink(tmp.name)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        print(f"❌ pandoc failed to render the PDF: {stderr}")
        return False
    return True


def write_pdf(output_path: Path, metadata: BookMetadata, chapters: List[Chapter],
              appendix_html: Optional[str] = None, page_size: str = "a5",
              engine: str = "auto") -> bool:
    """Write a PDF book to output_path.

    Args:
        output_path: Destination .pdf path
        metadata: BookMetadata (title page and html lang)
        chapters: Chapters from build_chapters()
        appendix_html: Optional appendix body; None omits the appendix page
        page_size: CSS @page size token (config export.page_size)
        engine: 'auto' (WeasyPrint then pandoc), 'weasyprint', or 'pandoc'

    Returns:
        True on success, False with a printed ❌ message otherwise
    """
    html = build_print_html(metadata, chapters, appendix_html, page_size)

    if engine in ("auto", "weasyprint"):
        if _render_with_weasyprint(html, output_path):
            return True
    if engine in ("auto", "pandoc"):
        if _render_with_pandoc(html, output_path):
            return True
        if engine == "pandoc":
            # which() missed it, or pandoc itself failed (already reported).
            if not shutil.which("pandoc"):
                print("❌ pdf_engine is 'pandoc' but pandoc is not installed")
            return False

    print(MISSING_ENGINE_MESSAGE)
    return False

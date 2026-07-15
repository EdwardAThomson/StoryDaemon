"""EPUB writer built on ebooklib (a core dependency, so imported at module top)."""
from pathlib import Path
from typing import List, Optional

from ebooklib import epub

from .chapters import Chapter, escape_html
from .metadata import BookMetadata

# Reader-oriented stylesheet embedded in the book. Kept modest: EPUB readers
# override most of this, so only structure and indent conventions matter.
BOOK_CSS = """\
body {
    font-family: Georgia, "Liberation Serif", serif;
    line-height: 1.5;
}
h1 {
    text-align: center;
    margin: 2em 0 1.5em 0;
}
p {
    margin: 0;
    text-indent: 1.5em;
}
h1 + p, .title-page p, .epigraph, .byline {
    text-indent: 0;
}
.title-page {
    text-align: center;
    margin-top: 20%;
}
.byline {
    font-style: italic;
    margin-top: 1em;
}
.epigraph {
    font-style: italic;
    margin-top: 3em;
}
.scene-break {
    text-align: center;
    text-indent: 0;
    margin: 1em 0;
}
"""


def _title_page_html(metadata: BookMetadata) -> str:
    parts = ['<div class="title-page">']
    parts.append(f"<h1>{escape_html(metadata.title)}</h1>")
    parts.append(f'<p class="byline">{escape_html(metadata.author)}</p>')
    if metadata.description:
        parts.append(f'<p class="epigraph">{escape_html(metadata.description)}</p>')
    parts.append("</div>")
    return "\n".join(parts)


def write_epub(output_path: Path, metadata: BookMetadata, chapters: List[Chapter],
               appendix_html: Optional[str] = None) -> bool:
    """Write an EPUB book to output_path.

    Args:
        output_path: Destination .epub path
        metadata: BookMetadata (dc:* fields and title page)
        chapters: Chapters from build_chapters()
        appendix_html: Optional appendix body; None omits the appendix chapter

    Returns:
        True on success (errors propagate to the caller's guard)
    """
    book = epub.EpubBook()

    book.set_identifier(metadata.identifier)
    book.set_title(metadata.title)
    book.set_language(metadata.language)
    book.add_author(metadata.author)
    if metadata.description:
        book.add_metadata('DC', 'description', metadata.description)
    for subject in metadata.subjects:
        book.add_metadata('DC', 'subject', subject)
    if metadata.date:
        book.add_metadata('DC', 'date', metadata.date)

    css_item = epub.EpubItem(
        uid="style_book",
        file_name="style/book.css",
        media_type="text/css",
        content=BOOK_CSS,
    )
    book.add_item(css_item)

    title_page = epub.EpubHtml(
        title=metadata.title,
        file_name="title.xhtml",
        lang=metadata.language,
    )
    title_page.content = _title_page_html(metadata)
    title_page.add_item(css_item)
    book.add_item(title_page)

    chapter_items = []
    for chapter in chapters:
        item = epub.EpubHtml(
            title=chapter.title,
            file_name=f"chapter_{chapter.number:03d}.xhtml",
            lang=metadata.language,
        )
        item.content = f"<h1>{escape_html(chapter.title)}</h1>\n{chapter.html_body}"
        item.add_item(css_item)
        book.add_item(item)
        chapter_items.append(item)

    appendix_item = None
    if appendix_html:
        appendix_item = epub.EpubHtml(
            title="Appendix",
            file_name="appendix.xhtml",
            lang=metadata.language,
        )
        appendix_item.content = f"<h1>Appendix</h1>\n{appendix_html}"
        appendix_item.add_item(css_item)
        book.add_item(appendix_item)

    toc = list(chapter_items)
    if appendix_item is not None:
        toc.append(appendix_item)
    book.toc = toc

    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())

    spine = ['nav', title_page] + chapter_items
    if appendix_item is not None:
        spine.append(appendix_item)
    book.spine = spine

    epub.write_epub(str(output_path), book)
    return True

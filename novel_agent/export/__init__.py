"""Book export package: EPUB and PDF output for `novel compile`.

The chapter seam lives in chapters.py (scene = chapter in v1), book-level
metadata mapping in metadata.py, and the two writers in epub.py / pdf.py.
compile.py stays the dispatcher; nothing here talks to the CLI.
"""
from .chapters import Chapter, build_chapters
from .metadata import BookMetadata, build_book_metadata
from .epub import write_epub
from .pdf import write_pdf

__all__ = [
    "Chapter",
    "build_chapters",
    "BookMetadata",
    "build_book_metadata",
    "write_epub",
    "write_pdf",
]

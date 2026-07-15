"""Unit tests for the PDF writer: engine selection with hand-rolled fakes.

WeasyPrint is an optional extra, so the base-suite tests never import the
real module: a fake goes into sys.modules (or None, which makes the import
fail). The single real-render test at the bottom skips unless WeasyPrint
and its Pango/Cairo system libraries are actually present.
"""
import sys
import types
from pathlib import Path

import pytest

from novel_agent.export import pdf as pdf_module
from novel_agent.export import write_pdf
from novel_agent.export.chapters import Chapter
from novel_agent.export.metadata import BookMetadata


def make_book():
    metadata = BookMetadata(
        title="The Alcyone",
        author="StoryDaemon",
        identifier="urn:storydaemon:abc123",
        genre="historical adventure",
        setting="A volcanic archipelago, 1871",
        tone="tense",
        description="A survey brig searches for a lost expedition.",
    )
    chapters = [
        Chapter(1, "The Sounding", "<p>Lead line prose.</p>", Path("scene_000.md")),
        Chapter(2, "The Meridian Mark", "<p>Charred canvas.</p>", Path("scene_001.md")),
    ]
    return metadata, chapters


class FakeWeasyHTML:
    """Records the HTML string handed to weasyprint.HTML and fakes the render."""

    recorded = {}

    def __init__(self, string=None, **kwargs):
        FakeWeasyHTML.recorded["html"] = string

    def write_pdf(self, target):
        FakeWeasyHTML.recorded["target"] = target
        Path(target).write_bytes(b"%PDF-fake")


@pytest.fixture
def fake_weasyprint(monkeypatch):
    FakeWeasyHTML.recorded = {}
    module = types.ModuleType("weasyprint")
    module.HTML = FakeWeasyHTML
    monkeypatch.setitem(sys.modules, "weasyprint", module)
    return FakeWeasyHTML.recorded


@pytest.fixture
def no_weasyprint(monkeypatch):
    # A None entry in sys.modules makes `import weasyprint` raise ImportError.
    monkeypatch.setitem(sys.modules, "weasyprint", None)


# ---- weasyprint path -------------------------------------------------------------

def test_write_pdf_weasyprint(fake_weasyprint, tmp_path):
    metadata, chapters = make_book()
    output = tmp_path / "book.pdf"

    result = write_pdf(output, metadata, chapters, page_size="a5")

    assert result is True
    assert output.read_bytes() == b"%PDF-fake"

    html = fake_weasyprint["html"]
    assert "The Alcyone" in html
    assert "The Sounding" in html
    assert "The Meridian Mark" in html
    assert "size: a5;" in html
    assert 'lang="en"' in html
    # Title-page extras from the foundation
    assert "historical adventure" in html
    assert "A survey brig searches for a lost expedition." in html


def test_write_pdf_page_size_token(fake_weasyprint, tmp_path):
    metadata, chapters = make_book()

    write_pdf(tmp_path / "book.pdf", metadata, chapters, page_size="6in 9in")

    assert "size: 6in 9in;" in fake_weasyprint["html"]


def test_write_pdf_appendix_page(fake_weasyprint, tmp_path):
    metadata, chapters = make_book()

    write_pdf(tmp_path / "book.pdf", metadata, chapters,
              appendix_html="<p><strong>Characters:</strong> 2</p>")

    html = fake_weasyprint["html"]
    assert "Appendix" in html
    assert "Characters" in html


# ---- graceful degradation ----------------------------------------------------------

def test_write_pdf_no_engine_graceful_error(no_weasyprint, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pdf_module.shutil, "which", lambda name: None)
    metadata, chapters = make_book()

    result = write_pdf(tmp_path / "book.pdf", metadata, chapters)

    assert result is False
    out = capsys.readouterr().out
    assert "❌ PDF export requires WeasyPrint (or pandoc)." in out
    assert "pip install storydaemon[export]" in out
    assert "Pango/Cairo" in out


def test_write_pdf_weasyprint_oserror_treated_as_missing(monkeypatch, tmp_path, capsys):
    # A pip-installed WeasyPrint with missing Pango/Cairo raises OSError at
    # import time; that must hit the same graceful path as ImportError.
    import importlib.util

    class BrokenLoader:
        def find_spec(self, name, path=None, target=None):
            if name == "weasyprint":
                return importlib.util.spec_from_loader(name, self)
            return None

        def create_module(self, spec):
            raise OSError("cannot load library 'gobject-2.0-0'")

        def exec_module(self, module):
            pass

    monkeypatch.delitem(sys.modules, "weasyprint", raising=False)
    monkeypatch.setattr(sys, "meta_path", [BrokenLoader()] + sys.meta_path)
    monkeypatch.setattr(pdf_module.shutil, "which", lambda name: None)
    metadata, chapters = make_book()

    result = write_pdf(tmp_path / "book.pdf", metadata, chapters)

    assert result is False
    assert "❌ PDF export requires WeasyPrint" in capsys.readouterr().out


# ---- pandoc path -------------------------------------------------------------------

def test_write_pdf_pandoc_fallback(no_weasyprint, monkeypatch, tmp_path):
    calls = {}

    def fake_which(name):
        return "/usr/bin/pandoc" if name == "pandoc" else None

    def fake_run(cmd, capture_output=True, text=True):
        calls["cmd"] = cmd
        calls["html"] = Path(cmd[1]).read_text(encoding="utf-8")
        Path(cmd[3]).write_bytes(b"%PDF-pandoc")
        return types.SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(pdf_module.shutil, "which", fake_which)
    monkeypatch.setattr(pdf_module.subprocess, "run", fake_run)
    metadata, chapters = make_book()
    output = tmp_path / "book.pdf"

    result = write_pdf(output, metadata, chapters)

    assert result is True
    assert calls["cmd"][0] == "/usr/bin/pandoc"
    assert calls["cmd"][2:] == ["-o", str(output)]
    assert "The Alcyone" in calls["html"]
    assert output.read_bytes() == b"%PDF-pandoc"


def test_write_pdf_pandoc_failure_reports(no_weasyprint, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(pdf_module.shutil, "which",
                        lambda name: "/usr/bin/pandoc" if name == "pandoc" else None)
    monkeypatch.setattr(
        pdf_module.subprocess, "run",
        lambda cmd, capture_output=True, text=True: types.SimpleNamespace(
            returncode=1, stderr="pdflatex not found"),
    )
    metadata, chapters = make_book()

    result = write_pdf(tmp_path / "book.pdf", metadata, chapters)

    assert result is False
    assert "pandoc failed" in capsys.readouterr().out


def test_write_pdf_engine_weasyprint_only_skips_pandoc(no_weasyprint, monkeypatch,
                                                       tmp_path, capsys):
    # pandoc is "installed" but the config pins weasyprint: no shell-out.
    def unexpected_run(*args, **kwargs):
        raise AssertionError("pandoc must not run when engine='weasyprint'")

    monkeypatch.setattr(pdf_module.shutil, "which",
                        lambda name: "/usr/bin/pandoc" if name == "pandoc" else None)
    monkeypatch.setattr(pdf_module.subprocess, "run", unexpected_run)
    metadata, chapters = make_book()

    result = write_pdf(tmp_path / "book.pdf", metadata, chapters, engine="weasyprint")

    assert result is False
    assert "❌ PDF export requires WeasyPrint" in capsys.readouterr().out


def test_write_pdf_engine_pandoc_only_skips_weasyprint(fake_weasyprint, monkeypatch,
                                                       tmp_path, capsys):
    # weasyprint fake is importable but the config pins pandoc, which is absent.
    monkeypatch.setattr(pdf_module.shutil, "which", lambda name: None)
    metadata, chapters = make_book()

    result = write_pdf(tmp_path / "book.pdf", metadata, chapters, engine="pandoc")

    assert result is False
    assert "html" not in fake_weasyprint
    assert "pandoc is not installed" in capsys.readouterr().out


# ---- real render (extra installed only) ---------------------------------------------

def test_write_pdf_real_render(tmp_path):
    # First pytest.importorskip in the suite: runs only where the [export]
    # extra is installed. The try/except also skips when WeasyPrint is
    # installed but its Pango/Cairo system libraries are missing (OSError).
    try:
        pytest.importorskip("weasyprint")
    except OSError:
        pytest.skip("weasyprint installed but Pango/Cairo system libraries missing")

    metadata, chapters = make_book()
    output = tmp_path / "book.pdf"

    result = write_pdf(output, metadata, chapters, engine="weasyprint")

    assert result is True
    assert output.read_bytes().startswith(b"%PDF-")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

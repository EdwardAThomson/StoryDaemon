"""Paragraph-word measurement in scripts/block_grammar_tables.py.

The measurement aligns per-paragraph judge labels to the source markdown,
and the shipped grammar's paragraph_words section comes from it, so the
alignment invariant (exact match or skip the book) is worth a guard: a
silently misaligned book would attach the wrong length to every mode.
No corpus and no LLM needed.
"""
import importlib.util
import os

import pytest

_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                     "scripts", "block_grammar_tables.py")
_spec = importlib.util.spec_from_file_location("block_grammar_tables", _PATH)
bgt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bgt)


def _write(tmp_path, text):
    p = tmp_path / "book.md"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_md_units_split_on_headings_and_blank_lines(tmp_path):
    units = bgt._md_units(_write(tmp_path, """# Front matter

Ignore me.

## CHAPTER I

First para.

Second para.

## CHAPTER II

Only one here.
"""))
    assert [len(u) for u in units] == [1, 2, 1]


def test_align_offset_skips_front_matter(tmp_path):
    md = bgt._md_units(_write(tmp_path, """# Title

Front matter para.

## CHAPTER I

A.

B.

## CHAPTER II

C.
"""))
    per_unit = [{"n_paragraphs": 2}, {"n_paragraphs": 1}]
    assert bgt._align_offset(per_unit, md) == 1


def test_align_offset_refuses_a_partial_match(tmp_path):
    # One unit's paragraph count disagrees: the judge's split is not ours,
    # so the book must be skipped rather than measured against wrong text.
    md = bgt._md_units(_write(tmp_path, """## CHAPTER I

A.

B.

## CHAPTER II

C.
"""))
    assert bgt._align_offset([{"n_paragraphs": 2}, {"n_paragraphs": 9}], md) is None


def test_measure_skips_books_without_markdown(tmp_path, monkeypatch):
    monkeypatch.setattr(bgt, "MD_DIR", str(tmp_path))
    words, aligned, skipped = bgt.measure_paragraph_words(
        {"ghost-book": {"metrics": {"block_rhythm": {"per_unit": []}}}})
    assert words == {} and aligned == []
    assert skipped == [("ghost-book", "no extracted markdown")]


def test_measure_counts_words_per_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(bgt, "MD_DIR", str(tmp_path))
    (tmp_path / "b.md").write_text("""## CHAPTER I

one two three four five.

six seven.
""", encoding="utf-8")
    books = {"b": {"metrics": {"block_rhythm": {"per_unit": [
        {"index": 0, "n_paragraphs": 2,
         "labels": [["SETTING", None], ["DIALOGUE", None]]}]}}}}
    words, aligned, skipped = bgt.measure_paragraph_words(books)
    assert aligned == ["b"] and skipped == []
    assert words["SETTING"] == [5]
    assert words["DIALOGUE"] == [2]


def test_word_stats_shape():
    s = bgt._word_stats([10, 20, 30, 40])
    assert s["n"] == 4 and s["mean"] == 25
    assert s["p25"] <= s["median"] <= s["p75"] <= s["p90"]


def test_shipped_grammar_carries_measured_paragraph_words():
    import json
    g = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..",
                                    "novel_agent", "data",
                                    "block_grammar_v1.json")))
    pw = g["paragraph_words"]
    assert pw["n_books"] == g["meta"]["n_books"]
    assert pw["overall"]["n"] == g["meta"]["n_paragraphs"]
    assert set(pw["by_mode"]) == set(g["modes"])

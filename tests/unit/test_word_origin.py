"""Word origin (agent/word_origin.py): Old English vs French/Latin shares. No model calls."""
from novel_agent.agent import style_profile as sp
from novel_agent.agent import word_origin as wo


def test_known_words_take_their_group():
    assert wo.origin("hand") == "G"          # a hand label (the Wordnet lacks it)
    assert wo.origin("sword") == "G"
    assert wo.origin("manner") == "R"
    assert wo.origin("the") == "G"           # grammar words are in the table
    assert wo.origin("melancholy") == "Gk"


def test_inflections_and_latin_suffixes_are_placed():
    assert wo.origin("swords") == "G"
    assert wo.origin("walked") == "G"
    assert wo.origin("reconfiguration") == "R"   # by the suffix rule
    assert wo.origin("zzxq") is None


def test_shares_separate_plain_from_latinate_prose():
    plain = "The old man took his sword in hand and went down to the dark water."
    ornate = "The gentleman expressed considerable satisfaction at the occasion of her departure."
    a, b = wo.origin_shares(plain), wo.origin_shares(ornate)
    assert a["latinate_pct"] < 10 < b["latinate_pct"]
    assert b["latinate_content_pct"] > b["latinate_pct"]   # grammar words dilute it
    assert a["origin_known_pct"] > 90


def test_names_are_left_out():
    # "Montmorency" is only ever capitalised, so it is a name and not an
    # unknown word that would lower the known share.
    text = "Montmorency took the sword. Montmorency went home."
    assert wo.origin_shares(text)["origin_known_pct"] == 100.0


def test_profiles_carry_the_origin_shares():
    m = sp.measure("She spoke with considerable indignation of the occasion; he went home.")
    assert "latinate_pct" in m and "latinate_content_pct" in m
    p = sp.load_profile("marriage")
    assert 15 < p["latinate_pct"] < 25                      # Ferrier about 20%
    fantasy = sp.load_profile("old_fantasy")
    assert fantasy["latinate_pct"] < p["latinate_pct"]       # Morris, Dunsany, Eddison


def test_shipped_profiles_have_chapter_ranges():
    for name in ("marriage", "pride", "old_fantasy"):
        p = sp.load_profile(name)
        low, high = p["ranges"]["latinate_pct"]
        assert low <= p["latinate_pct"] <= high


def _chapter(word, n=900):
    return " ".join([word] * n) + "."


def test_chapter_ranges_span_the_chapters():
    chapters = [_chapter("sword"), _chapter("manner"), _chapter("hand"), _chapter("occasion")]
    r = sp.chapter_ranges(chapters)
    low, high = r["latinate_pct"]
    assert low < 50 < high
    assert sp.chapter_ranges(chapters[:2]) == {}             # too few chapters


def test_book_chapters_takes_another_heading():
    body = "\n\n".join(f"      {n}: THE {t} OF LORD JUSS\n\n{_chapter('word', 300)}"
                       for n, t in (("I", "CASTLE"), ("II", "HALL")))
    assert len(sp.book_chapters(body)) == 1                  # no CHAPTER lines: one piece
    two = sp.book_chapters(body, heading=r"^\s*[IVXLC]+[:.]\s+[A-Z][A-Z' ]+\s*$")
    assert len(two) == 2

"""Repetition gauge (agent/repetition.py): pure logic over a fake embedder."""
from novel_agent.agent import repetition as rp


def fake_embed(texts):
    """Bag-of-words vectors over a tiny vocabulary, so meaning similarity is
    word overlap and tests can reason about it."""
    vocab = sorted({w for t in texts for w in rp._WORD.findall(t.lower())})
    return [[float(w in rp._WORD.findall(t.lower())) for w in vocab] for t in texts]


PROSE = """The tide was falling fast across the black sand, and Walter watched it go.

“We should record the marks separately before we compare them,” Walter said.

Walter thought they ought to record the marks separately before comparing them at all.

The lantern swung on its chain and threw a yellow circle over the chart table.

“We should record the marks separately before we compare them,” Walter said again.
"""


def test_sentences_carry_paragraph_and_speech():
    s = rp.sentences(PROSE)
    assert [x.paragraph for x in s] == [0, 1, 2, 3, 4]
    assert [x.speech for x in s] == [False, True, False, False, True]


def test_literal_layer_finds_the_duplicated_line_only():
    s = rp.sentences(PROSE)
    lit = rp.literal_matches(s)
    assert [(m.later, m.earlier) for m in lit] == [(4, 1)]
    assert lit[0].score >= 0.75


def test_meaning_layer_finds_narration_restating_speech_as_an_echo():
    rep, best = rp.analyse(PROSE, fake_embed, threshold=0.5)
    laters = {m.later for m in rep.meaning}
    assert 2 in laters                      # the paraphrase of the line above it
    assert any(e.later == 2 and e.earlier == 1 for e in rep.echo)
    assert len(best) == rep.sentences and all(0.0 <= b <= 1.0 for b in best)


def test_no_embedder_skips_the_meaning_layer():
    rep, best = rp.analyse(PROSE, None)
    assert rep.meaning == [] and rep.echo == [] and best == []
    assert rep.as_dict()["literal"] == 1


def test_empty_prose_is_a_zero_report():
    rep, best = rp.analyse("", fake_embed)
    assert rep.sentences == 0 and rep.rate("literal") == 0.0

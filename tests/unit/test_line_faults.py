"""Line-fault counts: free measures of sentence-level habits (gauge only)."""

import pytest

from novel_agent.agent import line_faults as lf


def test_every_measure_is_returned_and_described():
    m = lf.measure('"Come in," she said.\n\nHe sat down by the fire.')
    assert set(lf.MEASURES) <= set(m)
    assert all(lf.MEASURES.values())


def test_empty_text_raises():
    with pytest.raises(ValueError):
        lf.measure("   \n\n  ")


def test_stock_cues_and_named_feelings_are_counted_once():
    text = ("She clenched her jaw. Her heart pounded.\n\n"
            "He felt a surge of anger at the sight of the letter on the table.")
    found = lf.found(text)
    assert found["stock_cues"] == ["clenched her jaw", "heart pounded"]
    # "felt a surge of" and "surge of anger" overlap: one named feeling.
    assert found["named_feelings"] == ["felt a surge of anger"]
    assert lf.measure(text)["named_feelings_per_1k"] == pytest.approx(1000 / 22, abs=0.1)


def test_speech_is_left_out_of_the_pattern_counts():
    spoken = '"I was furious, and I saw him just as my heart pounded," she said.'
    m = lf.measure(spoken)
    assert m["named_feelings_per_1k"] == 0
    assert m["stock_cues_per_1k"] == 0
    assert m["filter_verbs_per_1k"] == 0
    assert m["hedges_per_1k"] == 0


def test_filter_verbs_in_narration():
    m = lf.measure("She saw the lamp go out. He could hear the rain on the glass.")
    assert lf.found("She saw the lamp go out. He could hear the rain.")["filter_verbs"] == [
        "she saw", "he could hear"]
    assert m["filter_verbs_per_1k"] > 0


def test_a_feeling_word_before_a_noun_is_not_a_named_feeling():
    assert lf.found("It was a sad day. She was a happy woman.")["named_feelings"] == []
    assert lf.found("She was very sorry.")["named_feelings"] == ["was very sorry"]


def test_speech_with_business_share():
    text = ('"Go," he said.\n\n'
            '"I will not," she said, and crossed the room to stand with her back against the door.\n\n'
            "The clock struck nine.")
    m = lf.measure(text)
    assert m["speech_paragraphs"] == 2
    assert m["speech_with_business_pct"] == 50.0


def test_no_speech_gives_none_not_zero():
    m = lf.measure("The clock struck nine. Nobody came.")
    assert m["speech_with_business_pct"] is None
    assert m["fancy_tag_pct"] is None


def test_fancy_tags_and_tag_adverbs():
    text = ('"No," he said softly.\n\n"Yes," she snapped.\n\n'
            '"Why?" he asked.\n\n"Because," she murmured.')
    m = lf.measure(text)
    assert m["fancy_tag_pct"] == 50.0
    assert m["tag_adverbs_per_1k"] > 0


def test_senses_other_than_sight():
    sight = lf.measure("She looked at the bright window and saw the pale light.")
    mixed = lf.measure("She heard the rattle of the cart and felt the cold damp air.")
    assert sight["non_sight_sense_pct"] == 0.0
    assert mixed["non_sight_sense_pct"] == 100.0


def test_sentence_length_variation():
    same = lf.measure("He went to town. She went to town. They went to town.")
    varied = lf.measure("He went. She followed him down the long road to the town by the river. Rain.")
    assert same["sentence_length_variation"] == 0
    assert varied["sentence_length_variation"] > 0.5


def test_closing_reflection():
    summed_up = "She shut the door.\n\nPerhaps nothing would ever be the same."
    plain = "She shut the door.\n\nThe rain went on all night."
    spoken = 'She shut the door.\n\n"Perhaps nothing would ever be the same," he said.'
    assert lf.closing_reflection(summed_up) == 1
    assert lf.closing_reflection(plain) == 0
    assert lf.closing_reflection(spoken) == 0


def test_similes_hedges_and_began_to():
    m = lf.measure("The fog lay like a blanket. She somehow began to laugh, as if it were a joke.")
    assert m["similes_per_1k"] > 0
    assert m["hedges_per_1k"] > 0
    assert m["began_to_per_1k"] > 0

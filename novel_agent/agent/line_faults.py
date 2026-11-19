"""Line-fault counts: free measures of the sentence-level habits editors flag.

The writing-advice research (seven working editors and authors, private notes)
agrees on a list of line-level faults: a gesture after every line of speech,
stock body cues, feelings named outright, perception reported through "she
saw" and "he felt", description by sight alone, fancy speech tags, hedging
words, sentences all one length, a closing paragraph that states the moral.

Those sources write for the modern commercial market, so their thresholds are
modern taste and are NOT used here. This module only counts. What a count
should be is read off a reference shelf (the older novels the house style is
drawn from), the same way a style profile is: measure the books, then compare.
``experiments/line_faults/compare.py`` does that.

Deliberately not counted, because the research found they are not reliable
signs of weak fiction: em dashes, "not X but Y", lists of three, and tense.

Pure and stdlib only. Gauge only: nothing reads these counts for decisions
(the project's instrument-first rule).
"""

from __future__ import annotations

import re
import statistics

# What each count means, in one plain line. Also the order they are shown in.
MEASURES = {
    "speech_with_business_pct":
        "of paragraphs with speech, the share that also carry 8+ words of narration (gesture, action, comment)",
    "stock_cues_per_1k":
        "stock body cues (clenched jaw, held breath, pounding heart) per 1,000 words of narration",
    "named_feelings_per_1k":
        "feelings named outright ('felt a surge of anger', 'was furious') per 1,000 words of narration",
    "filter_verbs_per_1k":
        "perception reported at one remove ('she saw', 'he noticed', 'could hear') per 1,000 words of narration",
    "non_sight_sense_pct":
        "of sense words, the share that are sound, smell, touch or taste rather than sight",
    "fancy_tag_pct":
        "of speech tags, the share that are not 'said' or 'asked'",
    "tag_adverbs_per_1k":
        "speech tags with a manner adverb ('said softly') per 1,000 words of narration",
    "hedges_per_1k":
        "hedging and filler words (somehow, sort of, seemed to, just, suddenly) per 1,000 words of narration",
    "began_to_per_1k":
        "'began to' / 'started to' per 1,000 words of narration",
    "similes_per_1k":
        "similes ('like a', 'as if', 'as though', 'as cold as') per 1,000 words of narration",
    "sentence_length_variation":
        "spread of sentence lengths divided by their average (0 = every sentence the same length)",
    "closing_reflection":
        "1 if the last paragraph is narration that sums up or looks ahead in general terms, else 0",
}

_QUOTE = re.compile(r'["“]([^"”]*)["”]')

_PRON = r"(?:he|she|they|i|we|it)"
_POSS = r"(?:his|her|their|my|our|the|a|an)"

_STOCK_CUES = [
    rf"\bclench(?:ed|ing)? {_POSS} (?:jaw|teeth|fists?|hands?)\b",
    r"\b(?:jaw|fists?|throat|chest|stomach|shoulders|grip) (?:tightened|clenched|tensed|knotted)\b",
    r"\b(?:let out|released|blew out|exhaled) a (?:\w+ )?breath\b",
    r"\bbreath (?:\w+ ){0,3}(?:didn'?t|did not) (?:know|realize|realise)\b",
    r"\b(?:held|caught) (?:his|her|their|my) breath\b",
    r"\bbreath (?:caught|hitched)\b",
    r"\bheart (?:pounded|raced|hammered|thudded|thumped|skipped|sank|leapt|lurched|stuttered)\b",
    r"\bpulse (?:quickened|raced|hammered|pounded|jumped)\b",
    r"\bswallowed (?:hard|thickly)\b",
    r"\beyes (?:widened|narrowed|flashed|flicked|darted|softened)\b",
    r"\bstomach (?:dropped|churned|twisted|lurched|turned|knotted|clenched)\b",
    r"\b(?:shiver|chill) (?:ran|went|crept|slid) (?:down|up|through)\b",
    r"\bbit (?:his|her|their|my) lip\b",
    r"\b(?:raised|arched|lifted|quirked) (?:an|one|a|his|her) (?:eye)?brow\b",
    r"\brolled (?:his|her|their|my) eyes\b",
    r"\bknuckles (?:whitened|went white|were white|white)\b",
    r"\b(?:ran|raked|dragged) a hand (?:through|over|down)\b",
    r"\bpinched the bridge of\b",
    r"\b(?:shrugged|smirked|grimaced|winced|gulped)\b",
    r"\blet out a (?:\w+ )?(?:sigh|laugh|groan)\b",
    r"\bmouth (?:went dry|tightened|thinned|twitched|quirked)\b",
    r"\blips (?:thinned|pressed|twitched|quirked|curled)\b",
    r"\bmuscle (?:\w+ ){0,2}(?:ticked|jumped|twitched|worked) in\b",
    r"\bblood (?:ran cold|drained|rushed|roared)\b",
    r"\bhairs? (?:\w+ ){0,4}(?:stood up|prickled|rose)\b",
]

_FEELINGS = (
    "anger|rage|fury|fear|dread|terror|panic|relief|guilt|shame|grief|sorrow|"
    "joy|sadness|hope|despair|anxiety|unease|jealousy|envy|pride|regret|"
    "frustration|irritation|annoyance|excitement|disappointment|loneliness|"
    "resentment|embarrassment|mortification|indignation|vexation|delight|"
    "alarm|dismay|pity|affection|tenderness|longing|satisfaction|horror|"
    "astonishment|surprise|contempt|gratitude|determination|confusion")
_FEELING_ADJ = (
    "angry|furious|afraid|frightened|terrified|scared|relieved|guilty|ashamed|"
    "sad|happy|hopeful|anxious|uneasy|jealous|envious|proud|sorry|frustrated|"
    "irritated|annoyed|excited|disappointed|lonely|resentful|embarrassed|"
    "mortified|indignant|vexed|delighted|alarmed|dismayed|horrified|"
    "astonished|surprised|grateful|determined|confused|nervous|miserable|"
    "nettled|pleased|agitated|distressed|overwhelmed|exhausted")
_VERY = ("very|so|quite|rather|too|most|extremely|exceedingly|not|a little|somewhat|"
         "half|really|truly|more|less|almost|suddenly|perfectly|heartily")
_NAMED_FEELINGS = [
    rf"\b(?:felt|feeling|feel|feels) (?:a |an |the |some |such |no |only |\w+ )?(?:sudden |sharp |quick |deep |strange |odd |faint |fresh |cold |hot |familiar )?"
    rf"(?:surge|wave|pang|flash|rush|stab|flicker|twinge|prickle|spike|jolt|swell|flood|thrill|glow|sense) of\b",
    rf"\b(?:felt|feeling|feel|feels|was|were|grew|looked|seemed|became) (?:(?:{_VERY}) )?(?:{_FEELING_ADJ})\b(?! (?:man|woman|girl|boy|child|day|time|thing|life|person|people|party|one)\b)",
    rf"\b(?:{_FEELINGS}) (?:washed|flooded|surged|rose|coursed|gripped|welled|bubbled|swept|seized|filled|overcame|flared|twisted|stabbed|settled|crept|shot|rushed|ran|tightened)\b",
    rf"\b(?:surge|wave|pang|flash|rush|stab|flicker|twinge|prickle|spike|jolt|swell|flood|thrill) of (?:\w+ )?(?:{_FEELINGS})\b",
    rf"\b(?:filled|overcome|overwhelmed|seized|consumed|flushed|trembled|trembling) with (?:\w+ )?(?:{_FEELINGS})\b",
]

_FILTERS = [
    rf"\b{_PRON} (?:could |couldn't |could not )?(?:saw|see|heard|hear|felt|feel|noticed|notice|watched|watch|realized|realised|"
    r"wondered|observed|sensed|smelled|smelt|perceived|glimpsed|spotted|knew that|thought that|was aware|became aware)\b",
]

_SENSE = {
    "sight": "saw|see|seen|looked|look|watched|glanced|gazed|stared|glimpsed|peered|"
             "bright|dark|dim|shadow|shadows|gleam|gleamed|glint|glow|glowed|pale|"
             "colour|color|red|blue|green|black|white|grey|gray|yellow|golden|light",
    "sound": "heard|hear|sound|sounds|noise|silence|silent|quiet|loud|whisper|whispered|"
             "murmur|rang|ring|rattle|rattled|creak|creaked|hum|hummed|hiss|hissed|"
             "roar|roared|thud|echo|echoed|voice|voices|click|clicked|clatter|rustle|rustled",
    "smell": "smell|smelled|smelt|scent|odour|odor|stink|stank|reek|reeked|fragrance|perfume|whiff|stench|aroma",
    "touch": "warm|cold|cool|hot|rough|smooth|soft|hard|damp|wet|dry|sticky|sharp|heavy|"
             "touched|touch|pressed|gripped|rubbed|stroked|ache|ached|sting|stung|chill|heat|numb",
    "taste": "taste|tasted|bitter|sweet|sour|salt|salty|savour|savor|flavour|flavor|tang",
}

_PLAIN_TAGS = r"said|asked"
_FANCY_TAGS = (
    "replied|answered|cried|whispered|muttered|called|snapped|murmured|"
    "exclaimed|shouted|growled|hissed|sighed|breathed|demanded|added|"
    "continued|observed|remarked|returned|rejoined|retorted|declared|"
    "interrupted|whimpered|barked|snarled|grumbled|gasped|drawled|"
    "stammered|pleaded|insisted|admitted|agreed|countered|offered|managed")
_TAG = re.compile(rf"\b({_PLAIN_TAGS}|{_FANCY_TAGS})\b")
_TAG_ADVERB = re.compile(rf"\b(?:{_PLAIN_TAGS}|{_FANCY_TAGS})(?: \w+){{0,2}}? (\w{{3,}}ly)\b")
_NOT_ADVERBS = {"only", "family", "early", "reply", "lady", "holy", "lovely", "elderly",
                "friendly", "likely", "lonely", "ugly", "silly", "july", "italy", "folly",
                "jolly", "rally", "belly", "bully", "fly", "ally", "supply", "apply"}

_HEDGES = re.compile(
    r"\b(?:somehow|something|sort of|kind of|seemed to|seemed like|appeared to|"
    r"a bit|a little|just|suddenly|almost|nearly|slightly|simply|really|quite possibly)\b")
_BEGAN = re.compile(r"\b(?:began|started|begun|beginning|starting) to\b")
_SIMILE = re.compile(r"\b(?:like an?|like the|like some|as if|as though|as \w+ as an?|as \w+ as the)\b")

_CLOSING = re.compile(
    r"\b(?:perhaps|maybe|whatever (?:came|happened|lay)|for now|for the first time|"
    r"would never|nothing would|everything (?:had|would)|no going back|"
    r"only (?:just )?(?:begun|beginning)|had changed|would change|some things|"
    r"knew(?: then)? that|understood(?: then)? that|realized that|realised that|"
    r"the future|tomorrow would|one thing was (?:certain|clear)|"
    r"and that was enough|it would have to be enough|whatever the cost)\b")


def _paragraphs(text: str) -> list:
    return [p.strip() for p in re.split(r"\n\s*\n", text)
            if p.strip() and not p.strip().startswith("#")]


def _sentences(text: str) -> list:
    return [s for s in re.split(r'(?<=[.!?])["”’]?\s+(?=[A-Z"“‘])', text) if s.split()]


def _words(text: str) -> list:
    return re.findall(r"[A-Za-z']+", text)


def _matches(patterns, text: str) -> list:
    """Matched phrases, with overlapping matches merged into one, so that
    "felt a surge of anger" is one named feeling and not two."""
    spans = sorted(m.span() for p in patterns for m in re.finditer(p, text))
    merged = []
    for start, end in spans:
        if merged and start < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [text[a:b] for a, b in merged]


def _count(patterns, text: str) -> int:
    return len(_matches(patterns, text))


def split_speech(paragraph: str):
    """(speech, narration) for one paragraph: the quoted words and the rest."""
    speech = " ".join(_QUOTE.findall(paragraph))
    return speech, _QUOTE.sub(" ", paragraph)


def closing_reflection(text: str) -> int:
    """1 when the last paragraph is narration that sums up or looks ahead."""
    paras = _paragraphs(text)
    if not paras:
        return 0
    last = paras[-1]
    if _QUOTE.search(last):
        return 0
    return 1 if _CLOSING.search(last.lower().replace("’", "'")) else 0


def measure(text: str) -> dict:
    """Every count in MEASURES for one text. Raises ValueError on an empty text.

    Rates are per 1,000 words of narration: every pattern count is taken
    outside the quotation marks, since a character is free to say "I just saw
    him" or "I was so vexed".
    """
    text = text.replace("\r", "").replace("’", "'")
    paras = _paragraphs(text)
    n = len(_words(text))
    if not n:
        raise ValueError("no words to measure")

    narration_parts, speech_paras, busy = [], 0, 0
    for p in paras:
        speech, narration = split_speech(p)
        narration_parts.append(narration)
        if speech.strip():
            speech_paras += 1
            if len(_words(narration)) >= 8:
                busy += 1
    narration = " ".join(narration_parts).lower()
    n_narr = len(_words(narration)) or 1

    def per_1k(count, base):
        return round(1000 * count / base, 2)

    senses = {k: len(re.findall(rf"\b(?:{v})\b", narration)) for k, v in _SENSE.items()}
    sense_total = sum(senses.values())

    tags = _TAG.findall(narration)
    fancy = sum(1 for t in tags if t not in ("said", "asked"))
    tag_adverbs = sum(1 for a in _TAG_ADVERB.findall(narration) if a not in _NOT_ADVERBS)

    lengths = [len(_words(s)) for s in _sentences(" ".join(paras)) if _words(s)]
    mean = statistics.mean(lengths) if lengths else 0
    variation = (statistics.pstdev(lengths) / mean) if mean and len(lengths) > 1 else 0.0

    return {
        "words": n,
        "speech_paragraphs": speech_paras,
        "speech_with_business_pct": round(100 * busy / speech_paras, 1) if speech_paras else None,
        "stock_cues_per_1k": per_1k(_count(_STOCK_CUES, narration), n_narr),
        "named_feelings_per_1k": per_1k(_count(_NAMED_FEELINGS, narration), n_narr),
        "filter_verbs_per_1k": per_1k(_count(_FILTERS, narration), n_narr),
        "non_sight_sense_pct": round(100 * (sense_total - senses["sight"]) / sense_total, 1) if sense_total else None,
        "fancy_tag_pct": round(100 * fancy / len(tags), 1) if tags else None,
        "tag_adverbs_per_1k": per_1k(tag_adverbs, n_narr),
        "hedges_per_1k": per_1k(len(_HEDGES.findall(narration)), n_narr),
        "began_to_per_1k": per_1k(len(_BEGAN.findall(narration)), n_narr),
        "similes_per_1k": per_1k(len(_SIMILE.findall(narration)), n_narr),
        "sentence_length_variation": round(variation, 2),
        "closing_reflection": closing_reflection(text),
    }


def found(text: str, limit: int = 8) -> dict:
    """Examples of what the pattern counts matched, for reading the counts
    against the page (a count nobody has read is not yet a measure)."""
    low = " ".join(split_speech(p)[1] for p in _paragraphs(text.replace("’", "'"))).lower()
    out = {}
    for key, patterns in (("stock_cues", _STOCK_CUES), ("named_feelings", _NAMED_FEELINGS),
                          ("filter_verbs", _FILTERS)):
        out[key] = _matches(patterns, low)[:limit]
    return out

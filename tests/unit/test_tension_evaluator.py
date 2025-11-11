"""Tests for tension evaluator."""
import pytest
from novel_agent.agent.tension_evaluator import TensionEvaluator
from novel_agent.configs.config import Config


@pytest.fixture
def config():
    """Create test config."""
    return Config()


@pytest.fixture
def evaluator(config):
    """Create tension evaluator."""
    return TensionEvaluator(config.to_dict())


def test_tension_evaluator_enabled_by_default(evaluator):
    """Test that tension tracking is enabled by default."""
    assert evaluator.enabled is True


def test_tension_evaluator_can_be_disabled():
    """Test that tension tracking can be disabled."""
    config = {'generation': {'enable_tension_tracking': False}}
    evaluator = TensionEvaluator(config)
    
    assert evaluator.enabled is False
    
    result = evaluator.evaluate_tension("Some scene text")
    assert result['enabled'] is False
    assert result['tension_level'] is None


def test_high_tension_keywords(evaluator):
    """Test high tension keyword detection."""
    high_tension_text = """
    The explosion rocked the building. Sarah screamed as debris rained down.
    Blood streamed from the wound on her arm. The danger was immediate and terrifying.
    She had to escape before the next attack came.
    """
    
    result = evaluator.evaluate_tension(high_tension_text)
    
    assert result['enabled'] is True
    assert result['tension_level'] is not None
    assert result['tension_level'] >= 7  # Should be high tension
    assert result['tension_category'] in ['high', 'climactic']


def test_low_tension_keywords(evaluator):
    """Test low tension keyword detection."""
    low_tension_text = """
    Sarah sat in the quiet garden, enjoying the peaceful afternoon.
    The warm sun felt gentle on her face. She smiled, feeling safe and content.
    Everything was calm and normal, just another ordinary day.
    """
    
    result = evaluator.evaluate_tension(low_tension_text)
    
    assert result['enabled'] is True
    assert result['tension_level'] is not None
    assert result['tension_level'] <= 4  # Should be low tension
    assert result['tension_category'] in ['calm', 'rising']


def test_medium_tension_keywords(evaluator):
    """Test medium tension keyword detection."""
    medium_tension_text = """
    Sarah felt uneasy as she approached the door. Something seemed wrong.
    She questioned whether she should enter. The situation was strange,
    and doubt crept into her mind. A conflict was brewing.
    """
    
    result = evaluator.evaluate_tension(medium_tension_text)
    
    assert result['enabled'] is True
    assert result['tension_level'] is not None
    assert result['tension_level'] >= 4
    assert result['tension_level'] <= 7


def test_short_sentences_increase_tension(evaluator):
    """Test that short sentences indicate higher tension."""
    short_sentence_text = """
    Run. Now. The door slammed. She fled. No time. Must escape.
    Danger everywhere. Heart pounding. Can't stop. Keep going.
    """
    
    result = evaluator.evaluate_tension(short_sentence_text)
    
    # Short sentences should contribute to higher tension
    assert result['analysis']['structure_score'] >= 6.0


def test_long_sentences_decrease_tension(evaluator):
    """Test that long sentences indicate lower tension."""
    long_sentence_text = """
    Sarah walked slowly through the peaceful garden, taking time to appreciate
    the beautiful flowers that bloomed in abundance along the winding path,
    their colors vibrant and their fragrance filling the air with a gentle
    sweetness that reminded her of simpler times when life moved at a slower pace.
    """
    
    result = evaluator.evaluate_tension(long_sentence_text)
    
    # Long sentences should contribute to lower tension
    assert result['analysis']['structure_score'] <= 5.0


def test_emotional_intensity_markers(evaluator):
    """Test emotional intensity detection."""
    intense_text = """
    "No!" she shouted. "Get back!" Her heart raced. She gasped—couldn't breathe.
    Everything was wrong! Why was this happening? She had to... she needed to...
    """
    
    result = evaluator.evaluate_tension(intense_text)
    
    # Exclamations, questions, dashes should increase emotion score
    assert result['analysis']['emotion_score'] >= 5.0


def test_tension_categories(evaluator):
    """Test tension category assignment."""
    assert evaluator._get_category(0) == 'calm'
    assert evaluator._get_category(3) == 'calm'
    assert evaluator._get_category(4) == 'rising'
    assert evaluator._get_category(6) == 'rising'
    assert evaluator._get_category(7) == 'high'
    assert evaluator._get_category(8) == 'high'
    assert evaluator._get_category(9) == 'climactic'
    assert evaluator._get_category(10) == 'climactic'


def test_tension_level_clamped_to_range(evaluator):
    """Test that tension level is always 0-10."""
    # Test with extreme high tension text
    extreme_text = """
    Danger! Explosion! Death! Terror! Panic! Attack! Fight! Blood! Scream!
    Emergency! Crisis! Threat! Fear! Horror! Alarm! Wound! Pain! Dying!
    """ * 10  # Repeat to maximize score
    
    result = evaluator.evaluate_tension(extreme_text)
    
    assert result['tension_level'] >= 0
    assert result['tension_level'] <= 10


def test_empty_text_returns_neutral(evaluator):
    """Test that empty text returns neutral tension."""
    result = evaluator.evaluate_tension("")
    
    assert result['tension_level'] is not None
    # Should be around neutral (5)
    assert 3 <= result['tension_level'] <= 7


def test_loop_context_affects_tension(evaluator):
    """Test that open loops context affects tension."""
    text = "Sarah walked down the hallway."
    
    # Context with loops created (raises tension)
    context_raising = {
        'open_loops_created': ['OL1', 'OL2'],
        'open_loops_resolved': []
    }
    result_raising = evaluator.evaluate_tension(text, context_raising)
    
    # Context with loops resolved (lowers tension)
    context_lowering = {
        'open_loops_created': [],
        'open_loops_resolved': ['OL1', 'OL2']
    }
    result_lowering = evaluator.evaluate_tension(text, context_lowering)
    
    # Raising context should have higher loop score
    assert result_raising['analysis']['loop_score'] > result_lowering['analysis']['loop_score']


def test_format_tension_history_empty(evaluator):
    """Test formatting empty tension history."""
    result = evaluator.format_tension_history([])
    assert result == "No tension history available"


def test_format_tension_history_with_scenes(evaluator):
    """Test formatting tension history with scenes."""
    from novel_agent.memory.entities import Scene
    
    scenes = [
        Scene(id="S001", tick=1, tension_level=3, tension_category="calm"),
        Scene(id="S002", tick=2, tension_level=5, tension_category="rising"),
        Scene(id="S003", tick=3, tension_level=7, tension_category="high"),
    ]
    
    result = evaluator.format_tension_history(scenes)
    
    assert "3, 5, 7" in result
    assert "calm → rising → high" in result


def test_tension_result_structure(evaluator):
    """Test that result has expected structure."""
    result = evaluator.evaluate_tension("Some text")
    
    assert 'tension_level' in result
    assert 'tension_category' in result
    assert 'enabled' in result
    assert 'analysis' in result
    
    if result['enabled']:
        assert 'keyword_score' in result['analysis']
        assert 'structure_score' in result['analysis']
        assert 'emotion_score' in result['analysis']
        assert 'loop_score' in result['analysis']


def test_realistic_scene_tension(evaluator):
    """Test tension evaluation on realistic scene text."""
    realistic_scene = """
    Sarah pushed through the crowded market, her eyes scanning for any sign
    of Marcus. Where was he? The message had been urgent—meet at noon, no delays.
    
    But noon had come and gone. Something was wrong.
    
    She felt the weight of the package in her coat pocket. If Marcus didn't show,
    she'd have to make the drop herself. The thought made her stomach tighten.
    She wasn't ready for this. Not yet.
    
    A hand grabbed her shoulder. Sarah spun around, heart racing.
    
    "Easy," Marcus said, his voice low. "We've got a problem."
    """
    
    result = evaluator.evaluate_tension(realistic_scene)
    
    # Should detect rising tension (mystery, urgency, surprise)
    assert result['enabled'] is True
    assert result['tension_level'] is not None
    assert 4 <= result['tension_level'] <= 8  # Rising to high tension
    assert result['tension_category'] in ['rising', 'high']

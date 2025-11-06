"""Unit tests for FactExtractor."""

import pytest
import json
from unittest.mock import Mock, MagicMock
from novel_agent.agent.fact_extractor import FactExtractor


@pytest.fixture
def mock_llm():
    """Mock LLM interface."""
    llm = Mock()
    llm.send_prompt = Mock()
    return llm


@pytest.fixture
def mock_memory():
    """Mock memory manager."""
    memory = Mock()
    memory.get_open_loops = Mock(return_value=[])
    return memory


@pytest.fixture
def mock_config():
    """Mock configuration."""
    config = Mock()
    config.get = Mock(side_effect=lambda key, default=None: {
        'llm.extractor_max_tokens': 2000
    }.get(key, default))
    return config


@pytest.fixture
def fact_extractor(mock_llm, mock_memory, mock_config):
    """Create FactExtractor instance."""
    return FactExtractor(mock_llm, mock_memory, mock_config)


def test_extract_facts_valid_json(fact_extractor, mock_llm):
    """Test extracting facts with valid JSON response."""
    # Mock LLM response
    response = json.dumps({
        "character_updates": [
            {
                "id": "C0",
                "changes": {
                    "emotional_state": "anxious",
                    "inventory": ["key"]
                }
            }
        ],
        "location_updates": [],
        "open_loops_created": [],
        "open_loops_resolved": [],
        "relationship_changes": []
    })
    mock_llm.send_prompt.return_value = response
    
    # Extract facts
    scene_text = "Sarah clutched the key nervously."
    scene_context = {"pov_character_id": "C0", "location_id": "L0"}
    
    facts = fact_extractor.extract_facts(scene_text, scene_context)
    
    # Verify
    assert len(facts["character_updates"]) == 1
    assert facts["character_updates"][0]["id"] == "C0"
    assert facts["character_updates"][0]["changes"]["emotional_state"] == "anxious"


def test_extract_facts_with_markdown_wrapper(fact_extractor, mock_llm):
    """Test extracting facts when JSON is wrapped in markdown code blocks."""
    # Mock LLM response with markdown
    response = """```json
{
  "character_updates": [],
  "location_updates": [],
  "open_loops_created": [],
  "open_loops_resolved": [],
  "relationship_changes": []
}
```"""
    mock_llm.send_prompt.return_value = response
    
    # Extract facts
    scene_text = "Test scene"
    scene_context = {"pov_character_id": "C0", "location_id": "L0"}
    
    facts = fact_extractor.extract_facts(scene_text, scene_context)
    
    # Verify
    assert facts["character_updates"] == []
    assert facts["location_updates"] == []


def test_extract_facts_invalid_json(fact_extractor, mock_llm):
    """Test extracting facts with invalid JSON response."""
    # Mock LLM response with invalid JSON
    mock_llm.send_prompt.return_value = "This is not JSON"
    
    # Extract facts
    scene_text = "Test scene"
    scene_context = {"pov_character_id": "C0", "location_id": "L0"}
    
    facts = fact_extractor.extract_facts(scene_text, scene_context)
    
    # Should return empty facts on error
    assert facts["character_updates"] == []
    assert facts["location_updates"] == []


def test_extract_facts_llm_error(fact_extractor, mock_llm):
    """Test extracting facts when LLM raises error."""
    # Mock LLM to raise error
    mock_llm.send_prompt.side_effect = Exception("LLM error")
    
    # Extract facts
    scene_text = "Test scene"
    scene_context = {"pov_character_id": "C0", "location_id": "L0"}
    
    facts = fact_extractor.extract_facts(scene_text, scene_context)
    
    # Should return empty facts on error
    assert facts["character_updates"] == []
    assert facts["location_updates"] == []


def test_format_open_loops(fact_extractor, mock_memory):
    """Test formatting open loops for prompt."""
    from novel_agent.memory.entities import OpenLoop
    
    # Mock open loops
    loop1 = OpenLoop(
        id="OL1",
        description="Find the missing artifact",
        importance="high",
        created_in_scene="S001"
    )
    mock_memory.get_open_loops.return_value = [loop1]
    
    # Format loops
    formatted = fact_extractor._format_open_loops()
    
    # Verify
    assert "OL1" in formatted
    assert "Find the missing artifact" in formatted
    assert "high" in formatted

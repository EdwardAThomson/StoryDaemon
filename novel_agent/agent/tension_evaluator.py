"""Tension evaluator for scene analysis (Phase 7A.3).

Tension is scored 0-10 per scene. The default scorer is an LLM that rates
*dramatic* tension against an anchored rubric (full dynamic range); a keyword
heuristic is kept as a no-LLM fallback. The heuristic alone collapses real
literary prose to ~6 (it measures pulp surface vocabulary, not stakes), which is
why the LLM scorer is preferred when an interface is wired in.
"""
import re
import json
import logging
from typing import Dict, Any, Optional

from .tension_scale import scorer_anchor_block

logger = logging.getLogger(__name__)


TENSION_RUBRIC_PROMPT = """You are rating the DRAMATIC TENSION of a single scene from a story, 0 to 10.

Rate stakes, threat, uncertainty, and pressure on the point-of-view character's goals — NOT the presence of dramatic words. A quiet conversation can be highly tense; a loud action scene can be low-stakes. Use the FULL range; do not default to the middle.

{anchors}

Scene:
\"\"\"
{scene_text}
\"\"\"

Respond with JSON only, no other text:
{{"tension_level": <integer 0-10>, "rationale": "<one short sentence>"}}"""


class TensionEvaluator:
    """Evaluates tension level in scene prose.
    
    Analyzes scene text for tension indicators and assigns a 0-10 score.
    Categories: calm (0-3), rising (4-6), high (7-8), climactic (9-10)
    """
    
    # Tension indicator keywords with weights
    HIGH_TENSION_KEYWORDS = [
        'danger', 'threat', 'attack', 'fight', 'battle', 'death', 'dying',
        'terror', 'panic', 'desperate', 'crisis', 'emergency', 'urgent',
        'scream', 'blood', 'pain', 'wound', 'injury', 'fear', 'afraid',
        'horror', 'dread', 'alarm', 'warning', 'explosion', 'collapse'
    ]
    
    MEDIUM_TENSION_KEYWORDS = [
        'conflict', 'argument', 'disagree', 'tension', 'stress', 'worry',
        'concern', 'anxious', 'nervous', 'uneasy', 'suspicious', 'doubt',
        'question', 'challenge', 'confront', 'reveal', 'discover', 'shock',
        'surprise', 'unexpected', 'strange', 'odd', 'wrong', 'mistake'
    ]
    
    LOW_TENSION_KEYWORDS = [
        'calm', 'peace', 'quiet', 'rest', 'relax', 'comfort', 'safe',
        'gentle', 'soft', 'slow', 'easy', 'routine', 'normal', 'ordinary',
        'familiar', 'warm', 'pleasant', 'smile', 'laugh', 'content'
    ]
    
    def __init__(self, config: dict, llm_interface=None):
        """Initialize tension evaluator.

        Args:
            config: Project configuration
            llm_interface: Optional LLM used to rate dramatic tension. When absent,
                the keyword heuristic is used (backward-compatible).
        """
        self.config = config
        self.llm = llm_interface
        # Handle both Config object (dot notation) and plain dict (nested access).
        self._is_plain_dict = isinstance(config, dict) and 'generation' in config
        self.enabled = self._cfg('generation.enable_tension_tracking', True)

    def _cfg(self, dotted_key: str, default):
        """Read a config value, supporting both Config (dot) and plain dict (nested)."""
        if self._is_plain_dict:
            section, _, leaf = dotted_key.partition('.')
            return self.config.get(section, {}).get(leaf, default)
        return self.config.get(dotted_key, default)
    
    def evaluate_tension(
        self,
        scene_text: str,
        scene_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Evaluate tension level in scene text.
        
        Args:
            scene_text: Scene prose text
            scene_context: Optional context (character state, open loops, etc.)
            
        Returns:
            Dictionary with tension_level (0-10), tension_category, and analysis
        """
        if not self.enabled:
            return {
                'tension_level': None,
                'tension_category': None,
                'enabled': False
            }

        # Preferred path: LLM rates dramatic tension across the full 0-10 range.
        if self.llm is not None and self._cfg('tension.use_llm_scorer', True):
            llm_result = self._llm_tension(scene_text)
            if llm_result is not None:
                level = llm_result['tension_level']
                return {
                    'tension_level': level,
                    'tension_category': self._get_category(level),
                    'enabled': True,
                    'analysis': {
                        'method': 'llm',
                        'rationale': llm_result.get('rationale', ''),
                    },
                }
            # LLM unavailable/failed for this scene — fall through to the heuristic.

        # Fallback: keyword/structure heuristic (no LLM, disabled, or LLM failed).
        # Calculate base tension from keywords
        keyword_score = self._analyze_keywords(scene_text)
        
        # Analyze sentence structure (short sentences = higher tension)
        structure_score = self._analyze_structure(scene_text)
        
        # Analyze emotional intensity
        emotion_score = self._analyze_emotion(scene_text)
        
        # Check for open loops/revelations
        loop_score = self._analyze_loops(scene_context) if scene_context else 0
        
        # Weighted average
        tension_level = int(round(
            keyword_score * 0.4 +
            structure_score * 0.2 +
            emotion_score * 0.3 +
            loop_score * 0.1
        ))
        
        # Clamp to 0-10
        tension_level = max(0, min(10, tension_level))
        
        # Determine category
        tension_category = self._get_category(tension_level)
        
        return {
            'tension_level': tension_level,
            'tension_category': tension_category,
            'enabled': True,
            'analysis': {
                'method': 'heuristic',
                'keyword_score': keyword_score,
                'structure_score': structure_score,
                'emotion_score': emotion_score,
                'loop_score': loop_score
            }
        }

    def _llm_tension(self, scene_text: str) -> Optional[Dict[str, Any]]:
        """Rate dramatic tension with the LLM. Returns None on failure (graceful).

        Retries once, mirroring the lore extractor / contradiction judge pattern,
        so a transient failure falls back to the heuristic rather than breaking a tick.
        """
        prompt = TENSION_RUBRIC_PROMPT.format(
            anchors=scorer_anchor_block(),
            scene_text=(scene_text or "")[:6000],
        )
        max_tokens = self._cfg('tension.max_tokens', 200)

        for attempt in (1, 2):
            try:
                response = self.llm.generate(prompt, max_tokens=max_tokens)
                return self._parse_tension(response)
            except Exception as e:
                if attempt == 1:
                    logger.warning(f"LLM tension scorer failed, retrying: {e}")
                else:
                    logger.error(f"LLM tension scorer failed after retry: {e}")
        return None

    @staticmethod
    def _parse_tension(response: str) -> Dict[str, Any]:
        """Parse the rater's JSON into ``{tension_level, rationale}`` (level clamped 0-10)."""
        start = response.find('{')
        end = response.rfind('}') + 1
        if start == -1 or end == 0:
            raise ValueError("no JSON object in tension rating")
        data = json.loads(response[start:end])
        level = int(round(float(data['tension_level'])))
        level = max(0, min(10, level))
        return {'tension_level': level, 'rationale': str(data.get('rationale', '')).strip()}

    def _analyze_keywords(self, text: str) -> float:
        """Analyze tension keywords in text.
        
        Args:
            text: Scene text
            
        Returns:
            Score from 0-10
        """
        text_lower = text.lower()
        word_count = len(text.split())
        
        if word_count == 0:
            return 5.0  # Neutral default
        
        # Count keyword occurrences
        high_count = sum(1 for kw in self.HIGH_TENSION_KEYWORDS if kw in text_lower)
        medium_count = sum(1 for kw in self.MEDIUM_TENSION_KEYWORDS if kw in text_lower)
        low_count = sum(1 for kw in self.LOW_TENSION_KEYWORDS if kw in text_lower)
        
        # Calculate density (per 100 words)
        high_density = (high_count / word_count) * 100
        medium_density = (medium_count / word_count) * 100
        low_density = (low_count / word_count) * 100
        
        # Weight the densities
        score = (
            high_density * 3.0 +
            medium_density * 1.5 -
            low_density * 1.0
        )
        
        # Scale to 0-10 range (empirically tuned)
        score = min(10, max(0, score * 2 + 5))
        
        return score
    
    def _analyze_structure(self, text: str) -> float:
        """Analyze sentence structure for tension.
        
        Short, choppy sentences = higher tension
        Long, flowing sentences = lower tension
        
        Args:
            text: Scene text
            
        Returns:
            Score from 0-10
        """
        # Split into sentences
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return 5.0
        
        # Calculate average sentence length
        avg_length = sum(len(s.split()) for s in sentences) / len(sentences)
        
        # Shorter sentences = higher tension
        # Typical ranges: 5-10 words = high tension, 15-25 = medium, 30+ = low
        if avg_length < 10:
            score = 8.0
        elif avg_length < 15:
            score = 6.0
        elif avg_length < 25:
            score = 4.0
        else:
            score = 2.0
        
        return score
    
    def _analyze_emotion(self, text: str) -> float:
        """Analyze emotional intensity markers.
        
        Args:
            text: Scene text
            
        Returns:
            Score from 0-10
        """
        text_lower = text.lower()
        
        # Count intensity markers
        exclamations = text.count('!')
        questions = text.count('?')
        ellipses = text.count('...')
        dashes = text.count('—') + text.count('--')
        
        # Emotional action verbs
        action_verbs = [
            'gasped', 'shouted', 'yelled', 'screamed', 'cried', 'sobbed',
            'lunged', 'grabbed', 'seized', 'jerked', 'flinched', 'recoiled',
            'rushed', 'raced', 'sprinted', 'fled', 'escaped', 'chased'
        ]
        action_count = sum(1 for verb in action_verbs if verb in text_lower)
        
        word_count = len(text.split())
        if word_count == 0:
            return 5.0
        
        # Calculate intensity score
        punctuation_intensity = (exclamations * 2 + questions + ellipses + dashes) / word_count * 100
        action_intensity = (action_count / word_count) * 100
        
        score = (punctuation_intensity * 3 + action_intensity * 5) + 3
        score = min(10, max(0, score))
        
        return score
    
    def _analyze_loops(self, context: Optional[Dict[str, Any]]) -> float:
        """Analyze open loops for tension contribution.
        
        Args:
            context: Scene context with open loops info
            
        Returns:
            Score from 0-10
        """
        if not context:
            return 5.0
        
        # Check if loops were created or resolved
        loops_created = len(context.get('open_loops_created', []))
        loops_resolved = len(context.get('open_loops_resolved', []))
        
        # Creating loops = raising tension
        # Resolving loops = lowering tension
        if loops_created > loops_resolved:
            return 7.0
        elif loops_resolved > loops_created:
            return 3.0
        else:
            return 5.0
    
    def _get_category(self, tension_level: int) -> str:
        """Get tension category from level.
        
        Args:
            tension_level: Tension level (0-10)
            
        Returns:
            Category string
        """
        if tension_level <= 3:
            return 'calm'
        elif tension_level <= 6:
            return 'rising'
        elif tension_level <= 8:
            return 'high'
        else:
            return 'climactic'
    
    def format_tension_history(self, scenes: list) -> str:
        """Format tension history for context display.
        
        Args:
            scenes: List of recent scenes with tension data
            
        Returns:
            Formatted string for context
        """
        if not scenes:
            return "No tension history available"
        
        # Get last N scenes with tension data
        tension_scenes = [
            s for s in scenes
            if hasattr(s, 'tension_level') and s.tension_level is not None
        ]
        
        if not tension_scenes:
            return "No tension data tracked yet"
        
        # Take last 5 scenes
        recent = tension_scenes[-5:]
        
        levels = [str(s.tension_level) for s in recent]
        categories = [s.tension_category for s in recent]
        
        # Create arrow progression
        progression = ' → '.join(categories)
        
        return f"Recent tension: [{', '.join(levels)}] ({progression})"

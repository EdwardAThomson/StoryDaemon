"""Configuration management for StoryDaemon."""
import os
import yaml
from typing import Dict, Any, Optional


# Default configuration
DEFAULT_CONFIG = {
    'llm': {
        'backend': 'codex',
        'codex_bin_path': 'codex',
        'default_max_tokens': 2000,
        'planner_max_tokens': 1000,
        'writer_max_tokens': 3000,  # Legacy flat scene ceiling, superseded by the Phase 3
                                    # write-until-concluded loop: the writer now sizes each
                                    # request from generation.scene_word_targets (word target
                                    # x tokens_per_word x scene_budget_multiplier). Kept so
                                    # old project configs load cleanly; nothing reads it.
        'extractor_max_tokens': 2000,
        'timeout': 300,  # Per-call timeout (seconds), applied on every backend: the CLI
                         # backends' subprocess timeout (claude -p is a full agent, slower
                         # than a completion API) and, since 2026-07-12, the api backend's
                         # per-request HTTP timeout on all provider clients (previously
                         # inert there: SDK defaults governed and a hung OpenRouter
                         # connection ran 22.4 minutes, docs/progress_report_20260712.md
                         # section 8.1). Any positive int; no hard max, but huge values
                         # just delay failure when a call derails.
        'model': 'gpt-5.5',  # Generic model name for API backend (OpenAI/Gemini/Claude)
        'openai_model': 'gpt-5.5',
        'openai_api_key_env': 'OPENAI_API_KEY',
    },
    'paths': {
        'novels_dir': os.path.expanduser('~/novels'),
    },
    'generation': {
        'max_tools_per_tick': 3,
        'recent_scenes_count': 3,
        'full_text_scenes_count': 2,  # Number of recent scenes to include as full text in writer context
        'summary_scenes_count': 3,    # Number of older scenes to include as summaries in writer context
        'include_overall_summary': True,
        'enable_fact_extraction': True,
        'enable_entity_updates': True,
        'enable_tension_tracking': True,  # Phase 7A.3: Track scene tension levels
        'enable_lore_tracking': True,  # Phase 7A.4: Track world rules and lore
        
        # Character detection (Phase 6)
        'auto_detect_characters': True,  # Detect new character names in scenes
        'auto_create_minor_characters': False,  # Auto-create stubs for detected characters
        'prompt_for_character_creation': True,  # Show tips about detected characters
        
        # Plot-first mode configuration
        'use_plot_first': False,  # Enable emergent plot-first architecture
        'plot_first_start_tick': 2,  # Start plot-first mode from this tick (allows character setup)
        'plot_beats_ahead': 5,  # Generate this many beats at a time
        'plot_regeneration_threshold': 2,  # Regenerate when pending beats < this
        'verify_beat_execution': True,  # Verify beat was accomplished via LLM
        'allow_beat_skip': False,  # Allow skipping beats that aren't accomplished
        'fallback_to_reactive': True,  # Fall back to reactive mode if beat generation fails
        'rolling_horizon': False,  # Phase 2: when a beat diverges from the written scene, abandon the pending horizon and regenerate it from current canon
        # Token budget for beat-generation LLM calls (read by BOTH the agent path,
        # plot/manager.py, and the CLI path, cli/commands/plot.py). Beat batches
        # carry contract and arc-guidance lines and truncate deterministically at
        # 1000 tokens; the CLI path's 2000 parsed first-try on the 2026-07-10 run.
        'beat_max_tokens': 2000,

        # Write-until-concluded scene loop (Phase 3, segment plumbing for the block
        # DSL). Evidence: docs/progress_report_20260711.md grant-rate addendum, where
        # the old flat 3000-token writer ceiling truncated 8 of 16 scenes mid-sentence.
        # The planner's optional scene_length metadata (brief|short|long|extended) maps
        # to an explicit word target stated in the writer prompt; the request ceiling is
        # sized at word_target x tokens_per_word x scene_budget_multiplier, so instructed
        # length and allowed length finally agree. When the first render still ends cut
        # (finish_reason "length" or the completion heuristic), bounded continuation
        # segments (each seeing the full scene so far, each told to CONCLUDE) run up to
        # scene_max_segments total; a scene still incomplete after the cap is trimmed to
        # the last complete sentence and flagged (scene_truncated in metrics).
        'scene_word_targets': {'brief': 400, 'short': 800, 'long': 1400, 'extended': 2200},
        'default_scene_length': 'long',   # target label when the plan gives no scene_length
        'tokens_per_word': 1.4,           # words-to-tokens sizing factor for prose
        'scene_budget_multiplier': 2.0,   # ceiling headroom over the stated word target
        'scene_max_segments': 3,          # total segments per scene (first render + continuations)

        # Scene skeletons (Slice 4 of the block DSL, experimental). When on, a
        # typed paragraph plan sampled from the masters' block grammar
        # (agent/scene_skeleton.py; evidence: experiments/block_grammar_poc
        # Gates A-C, docs/MASTERS_BLOCK_GRAMMAR_STUDY.md) rides the writer
        # prompt with the [n] marker protocol; markers are stripped from the
        # prose and compliance is recorded on the scene result. Off = the
        # pipeline is byte-identical to before.
        'enable_scene_skeleton': False,

        # Beat-level dedup at authoring time (Phase 3 hardening,
        # docs/progress_report_20260712.md section 8.2): a freshly authored beat
        # whose description fuzzy-matches a pending / recently completed beat, or
        # an earlier beat in the same batch, is dropped with a warning before it
        # reaches the outline (the triple run's duplicated PB005/PB006 produced
        # ~9,200 characters of verbatim prose across two scenes plus duplicate
        # loops downstream). Deterministic, no LLM; shared by both authoring
        # paths (plot/manager.py and cli/commands/plot.py).
        'beat_dedup': True,
        # Similarity at or above which a new beat is a duplicate. The gauge is
        # max(difflib ratio, sorted-token difflib ratio) on case-insensitive
        # descriptions: plain difflib alone cannot separate the species (the
        # triple run's real duplicate pair measures 0.521 while a legitimately
        # distinct same-batch pair in grantrate-run measures 0.513); the
        # sorted-token variant lifts word-order-shuffled duplicates (that same
        # duplicate pair rises to 0.697) while distinct beats stay low.
        # Calibrated across the work/ corpus: confirmed duplicates measure
        # 0.697-0.770, legitimately distinct pairs top out at 0.574, and 0.65
        # splits the gap while deliberately keeping the one ambiguous
        # escalation-retread specimen (0.644): dropping a legitimate beat is
        # worse than letting a near-dup through (see plot/dedup.py).
        'beat_dedup_threshold': 0.65,

        # Beat contracts (Phase 3, docs/BLOCKS_CONTRACTS_LANDING_SKETCH.md Slice 1):
        # postconditions are authored with each beat at generation time, sanitized
        # against the closed checker vocabulary, shown to the writer, and checked at
        # beat verification (tick step 11.5). All passing upgrades the verification
        # method to "contract"; any failing keeps the beat pending (or triggers a
        # rolling-horizon revision when generation.rolling_horizon is on).
        'use_contracts': False,
    },
    'lore': {
        'contradiction_threshold': 0.5,  # Similarity threshold for the candidate pre-filter (0.0-2.0)
        'llm_contradiction_check': True,  # Use the LLM to judge flagged candidate pairs; falls back to the
                                          # type heuristic when False or no LLM is wired in
        'contradiction_max_tokens': 200,  # Token budget for each contradiction-judging LLM call
        'enforce_contradictions': True,   # Phase 3: mark the non-canon (newer) item "disputed" and
                                          # filter it from planner context; False = detection-only
    },
    'tension': {
        # Scene tension scoring (0-10). The LLM scorer rates dramatic tension across the
        # full range; the keyword heuristic is the no-LLM fallback (collapses to ~6 on real
        # prose). generation.enable_tension_tracking is the master on/off switch.
        'use_llm_scorer': True,
        'max_tokens': 200,
    },
    'coherence': {
        # Phase 3 coherence rubric — per-tick instrumentation, no behavior change.
        'enabled': True,                  # Master switch for recording memory/metrics.jsonl
        'goal_relevance_chars': 3000,     # Scene-prose truncation for the goal-relevance check
        # Goal-relevance gauge (0-10): how much each scene serves the primary goal. The LLM
        # judge rates *advancing the goal* (not topical overlap); the embedding-similarity
        # gauge (scaled to 0-10) is the no-LLM fallback. Recorded as goal_relevance in the rubric.
        'use_llm_goal_relevance': True,
        'goal_relevance_max_tokens': 200,
        # Arc-pressure (Phase 3): nudge the planner toward a target tension trajectory.
        # target_story_length is the "story position" denominator — set it to the
        # intended length (in ticks): short story vs. novella vs. novel. The curve is
        # [progress_fraction, tension_level] control points (linearly interpolated);
        # set it to None to disable arc-pressure.
        'target_story_length': 40,
        'target_tension_curve': [[0.0, 3], [0.25, 5], [0.5, 6], [0.75, 8], [0.9, 9], [1.0, 4]],
        # Tension-curve preset (Phase 3, interleaving Slice T4a): named control-point
        # sets grounded in the masters study's decile tables (arc_pressure.CURVE_PRESETS;
        # docs/MASTERS_THREADS_TENSION_STUDY.md). "house" resolves to exactly the default
        # curve above (the quiet-epilogue house style), so default behavior is
        # byte-identical; "thriller-register", "wind-down", and "domestic-arc" are
        # opt-in. An explicitly customized target_tension_curve always wins over the
        # preset, and target_tension_curve None still disables arc-pressure entirely.
        'curve_preset': 'house',
        # Phase 3 #2: closed-loop tension control. When a scored scene is more than
        # tension_rewrite_threshold off the arc-pressure target, do ONE revision pass
        # toward the target (kept only if it lands closer). Adds ~2 LLM calls per
        # off-target scene; set False to disable (back to open-loop nudging only).
        'tension_rewrite': True,
        'tension_rewrite_threshold': 2,
        # A target that is this far below the previous scene's tension is treated as a
        # deliberate drop that needs a transition (new location / aftermath / time skip)
        # rather than a continuation — used by the planner and the rewrite to avoid whiplash.
        'tension_step_for_transition': 3,
        # Arc-phase planner mandate (Phase 3): derive the arc phase (rising / peak /
        # falling / resolution) from the target curve and give the planner firm,
        # event-level instructions per phase (escalate / confront / resolve). Also skips
        # the tension rewrite when the scene is a full transition step or more ABOVE the
        # target, since only different events (not re-wording) can lower it that far.
        # False = numeric-target guidance only (pre-mandate behavior). The derived phase
        # is still recorded in metrics either way, so on/off runs stay comparable.
        'arc_phase_mandate': True,
        # Throughline gate: inject the primary goal into the planner so scenes serve it.
        # Dormant until a primary goal exists; goal_relevance in the rubric measures adherence.
        'throughline_pressure': True,
        # Sacred finale (Phase 3): Python owns the story's final scene. On the finale
        # tick (current_tick == target_story_length, plot-first active) the beat ask is
        # guaranteed (pending-beat screen, then an authored finale beat, then a
        # deterministic template), the written scene gets bounded fresh re-rolls against
        # the finale tension cap (curve endpoint + 1) in place of the prose rewrite, and
        # settled endings quarantine the finale's freshly minted open loops. False
        # restores existing behavior exactly.
        'sacred_finale': True,
        # Max fresh writer re-rolls when the finale scene scores above the cap (the
        # sunshine test showed the hot flips are staging choices a rewrite cannot
        # unstage; one or two re-rolls turn a coin flip into near certainty).
        'finale_retries': 2,
        # Ending mode: False = settled (firm no-hook writer instruction plus the loop
        # quarantine); True = end on ONE deliberate hook and let its loops through.
        'ending_hook': False,
        # Judged loop closure (Phase 3, Slice 0 of the interleaving design): when a
        # beat completes verification and claims resolves_loops, each claimed loop
        # gets one focused LLM check (that loop's description against the scene) and
        # is closed only on a confirmed yes, with an auditable resolution summary.
        # Default True: its validation run passed (docs/progress_report_20260711.md:
        # 13 claims judged, 3 honest scene-grounded closures, 10 correct refusals,
        # 0 parse failures, zero tick impact). The same gate covers the judged
        # extractor-resolution path and the finale loop expiry (Phase 3, Slice 0
        # follow-ups), so False restores the pre-Slice-0 behavior exactly for A/B.
        'loop_closure': True,
        'loop_closure_max_tokens': 200,   # Token budget per judge call (verdict JSON only)
        # Scene-prose cap per judge call: generous, because the resolving moment is
        # often the scene's ENDING, which the 3000-char caps used elsewhere would cut
        # off; 12000 chars covers a full typical scene (~2000-2500 words).
        'loop_closure_scene_chars': 12000,
        # Max extractor-claimed loop resolutions judged per tick (Phase 3, Slice 0
        # follow-ups): the finale sweep reported 47 resolutions in one tick
        # (docs/progress_report_20260711.md section 4), and judging all of them
        # would turn one tick into a judge marathon. Claims beyond the cap are
        # ignored with a warning naming them. None or 0 disables the cap.
        'extractor_resolutions_judged_cap': 5,
        # Creation hygiene (Slice 0): dedup new open loops against existing OPEN loops
        # at creation (difflib SequenceMatcher on case-insensitive descriptions,
        # deterministic, no LLM) and cap creations per tick so one scene cannot flood
        # the ledger. Pure hygiene, so it defaults on.
        'loop_dedup': True,
        # Ratio at or above which a new loop is a duplicate. Lowered 0.8 -> 0.75
        # (Phase 3 hardening, docs/progress_report_20260712.md section 8.3): the
        # 0.8 threshold had a measured blind spot at ~0.78-0.79, with two
        # documented near-misses of semantically identical double-created
        # questions in two runs (slice0-run2's OL29/OL33 at 0.784 and the triple
        # run's OL23/OL27 at 0.788, the latter then double-closed by one event).
        # Genuinely distinct strands sit far lower (the same difflib-behavior
        # rationale the thread matcher documents), so 0.75 closes the gap.
        # Semantic dedup remains the roadmap fix for the paraphrase species that
        # character matching can never see (slice0's OL23/OL32 pair at 0.341).
        'loop_dedup_threshold': 0.75,
        # Max new loops per tick; entries beyond the cap are dropped lowest-importance
        # first. None or 0 disables the cap.
        'loop_creation_cap': 4,
        # Thread registry (Phase 3, interleaving Slice T1): ratio at or above which
        # a beat's plot_threads label maps to an existing thread instead of minting
        # a new one (difflib SequenceMatcher on normalized labels, deterministic,
        # no LLM). 0.8 follows the loop-dedup precedent: label variants of one
        # strand ("velyn_agenda" / "Velyn's agenda") score well above 0.85, while
        # distinct strands sharing scaffolding sit lower. Pure instrumentation:
        # nothing reads the registry for decisions in this slice, so there is no
        # on/off gate beyond coherence.enabled for the metric fields.
        'thread_match_threshold': 0.8,
        # Thread identity grounding (Phase 3, interleaving Slice T1.5): the
        # "select, don't invent" move applied to threads. The T1 backfill over
        # three finished novels showed authored plot_threads labels are per-beat
        # episode titles, not persistent threads (34 executed beats yielded 30
        # distinct primary labels; the reliable identity signal was the cast),
        # so Python mints thread identity and the LLM selects it: the beat
        # prompt carries a thread roster with exact TH ids, each beat names the
        # ONE thread it serves via thread_id ("new: <name>" mints a strand), a
        # sanitizer holds authored ids to the roster, and per-tick attribution
        # prefers the selected id over the T1 first-label fallback. False
        # restores exact T1 behavior (label normalization only).
        'thread_identity': True,
        # Construction-pressure detector (Phase 3, interleaving Slice T4a;
        # docs/THREAD_CONSTRUCTION_DESIGN.md section 2). Per tick, computes whether
        # thread construction WOULD fire (recorded as construction_would_fire /
        # construction_trigger in the rubric, reason in the tick result). Pure
        # instrumentation, so it defaults on (the coherence-rubric precedent);
        # nothing constructs until Slice T4b's coherence.thread_construction gate.
        'thread_construction_detector': True,
        'construction_floor': 0.15,   # story fraction: earliest construction
        'construction_cutoff': 0.5,   # story fraction: latest construction (early/mid only)
        # Whiplash-guard minimum run per thread. None = derived from story length:
        # max(2, round(0.2 * target_story_length)), the masters' committed blocks at
        # roughly 15-30 percent of book length (length 15 gives 3, 24 gives 5, 40
        # gives 8). An explicit positive integer overrides the derivation.
        'thread_min_run': None,
        'convergence_reserve': 1,     # runway slots held for the merge beat
        # Demand-gap trigger (EXPERIMENTAL, demoted per the masters study: no corpus
        # book keeps a calm B-thread to cut to, so the construct-calm-supply premise
        # is unsupported; kept opt-in because the pipeline's measured inability to
        # de-escalate is a real problem the masters do not have). Evaluated only
        # when the diversity trigger did not fire.
        'demand_gap_trigger': False,
        'calm_threshold': 4,          # demand-gap: the calm band's top
        'serve_margin': 2,            # demand-gap: a thread serves a target within this
    },
    'export': {
        # Book export settings for `novel compile --format epub|pdf`
        # (docs/EPUB_PDF_EXPORT_PLAN.md).
        'author': 'StoryDaemon',   # dc:creator / title-page byline
        'language': 'en',          # dc:language and html lang (enables hyphenation)
        'page_size': 'a5',         # @page size for PDF; any CSS size token
        'pdf_engine': 'auto',      # auto | weasyprint | pandoc
    },
    'plot': {
        # Beat integration mode: controls how strongly the agent treats plot beats.
        #
        #   off       - no beat hints or QA integration
        #   soft_hint - expose next_plot_beat and compute beat_hint_alignment (default)
        #   guided    - planner expected to fill beat_target and beats may be updated
        #   strict    - future: hard validation around beat usage
        'beat_mode': 'soft_hint',
    }
}


class Config:
    """Configuration manager for StoryDaemon."""
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize configuration.
        
        Args:
            config_path: Path to YAML config file (optional)
        """
        self.config = self._deep_copy(DEFAULT_CONFIG)
        
        if config_path and os.path.exists(config_path):
            self.load(config_path)
    
    def load(self, config_path: str):
        """Load configuration from YAML file.
        
        Args:
            config_path: Path to YAML config file
            
        Raises:
            IOError: If file cannot be read
            ValueError: If YAML is invalid
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                user_config = yaml.safe_load(f)
                if user_config:
                    self._merge_config(user_config)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {config_path}: {e}")
        except Exception as e:
            raise IOError(f"Error reading config from {config_path}: {e}")
    
    def _merge_config(self, user_config: Dict[str, Any]):
        """Merge user config with defaults (deep merge).
        
        Args:
            user_config: User configuration dictionary
        """
        self._deep_merge(self.config, user_config)
    
    def _deep_merge(self, base: Dict, update: Dict):
        """Recursively merge update dict into base dict.
        
        Args:
            base: Base dictionary to merge into
            update: Dictionary with updates
        """
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def _deep_copy(self, d: Dict) -> Dict:
        """Create a deep copy of a dictionary.
        
        Args:
            d: Dictionary to copy
            
        Returns:
            Deep copy of dictionary
        """
        result = {}
        for key, value in d.items():
            if isinstance(value, dict):
                result[key] = self._deep_copy(value)
            else:
                result[key] = value
        return result
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-notation key.
        
        Args:
            key: Dot-notation key (e.g., 'llm.codex_bin_path')
            default: Default value if key not found
            
        Returns:
            Config value or default
            
        Examples:
            >>> config.get('llm.codex_bin_path')
            'codex'
            >>> config.get('llm.planner_max_tokens')
            1000
        """
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """Set config value by dot-notation key.
        
        Args:
            key: Dot-notation key (e.g., 'llm.codex_bin_path')
            value: Value to set
            
        Examples:
            >>> config.set('llm.codex_bin_path', '/usr/local/bin/codex')
        """
        keys = key.split('.')
        target = self.config
        
        # Navigate to the parent dict
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        
        # Set the value
        target[keys[-1]] = value
    
    def save(self, config_path: str):
        """Save current configuration to YAML file.
        
        Args:
            config_path: Path to save config file
            
        Raises:
            IOError: If file cannot be written
        """
        try:
            dir_name = os.path.dirname(config_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)
            
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            raise IOError(f"Error saving config to {config_path}: {e}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Get configuration as dictionary.
        
        Returns:
            Configuration dictionary
        """
        return self._deep_copy(self.config)

"""Unit tests for the multi-provider LLM registry, focused on OpenRouter.

Follows the house style: plain pytest functions, hand-written fakes instead of
unittest.mock, plain asserts.
"""

import pytest

from novel_agent.tools import multi_provider_llm


class FakeOpenAI:
    """Records constructor args instead of talking to a real API."""

    last_instance = None

    def __init__(self, base_url=None, api_key=None):
        self.base_url = base_url
        self.api_key = api_key
        FakeOpenAI.last_instance = self


@pytest.fixture(autouse=True)
def reset_client_singletons(monkeypatch):
    """Ensure no cached client leaks between tests, and env vars start clean.

    The module also caches an OpenAI client and an Anthropic client; reset all
    of them for hygiene even though these tests only exercise OpenRouter.
    """
    monkeypatch.setattr(multi_provider_llm, "_openrouter_client", None)
    monkeypatch.setattr(multi_provider_llm, "_hosted_llm_client", None)
    monkeypatch.setattr(multi_provider_llm, "_openai_client", None)
    monkeypatch.setattr(multi_provider_llm, "_anthropic_client", None)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    yield


def test_get_openrouter_client_raises_when_key_missing(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        multi_provider_llm._get_openrouter_client()


def test_get_openrouter_client_uses_correct_base_url_and_key(monkeypatch):
    monkeypatch.setattr(multi_provider_llm, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-123")

    client = multi_provider_llm._get_openrouter_client()

    assert isinstance(client, FakeOpenAI)
    assert client.base_url == "https://openrouter.ai/api/v1"
    assert client.api_key == "test-key-123"


def test_send_prompt_openrouter_raises_without_model(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    with pytest.raises(ValueError, match="OPENROUTER_MODEL"):
        multi_provider_llm.send_prompt_openrouter("hello")


def test_send_prompt_openrouter_falls_back_to_env_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-3.7-sonnet")

    captured = {}

    class FakeMessage:
        content = "reply text"

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        choices = [FakeChoice()]

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return FakeResponse()

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    monkeypatch.setattr(multi_provider_llm, "_get_openrouter_client", lambda: FakeClient())

    result = multi_provider_llm.send_prompt_openrouter("hello there")

    assert result == "reply text"
    assert captured["model"] == "anthropic/claude-3.7-sonnet"


def test_openrouter_in_supported_models():
    assert "openrouter" in multi_provider_llm.get_supported_models()


def test_send_prompt_routes_to_openrouter(monkeypatch):
    calls = {}

    def fake_send_prompt_openrouter(prompt, max_tokens=2000):
        calls["prompt"] = prompt
        calls["max_tokens"] = max_tokens
        return "openrouter says hi"

    monkeypatch.setitem(
        multi_provider_llm._model_config,
        "openrouter",
        lambda prompt, max_tokens: fake_send_prompt_openrouter(prompt, max_tokens),
    )

    result = multi_provider_llm.send_prompt("ping", model="openrouter", max_tokens=42)

    assert result == "openrouter says hi"
    assert calls == {"prompt": "ping", "max_tokens": 42}


# ---------------------------------------------------------------------------
# Per-request timeout plumbing (Phase 3 hardening, progress report 2026-07-12
# section 8.1: llm.timeout was inert on the whole api backend, so the SDK
# defaults governed a 22.4-minute hang). Each provider shape gets a fake that
# captures what reached the request.
# ---------------------------------------------------------------------------


class _OpenAIStyleClient:
    """OpenAI-shaped fake (openai / openrouter / hosted-llm): captures create kwargs."""

    def __init__(self, captured):
        class _Message:
            content = "reply"

        class _Choice:
            message = _Message()
            finish_reason = "stop"

        class _Response:
            choices = [_Choice()]

        class _Completions:
            def create(self, **kwargs):
                captured.update(kwargs)
                return _Response()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_openai_timeout_reaches_the_request(monkeypatch):
    captured = {}
    monkeypatch.setattr(multi_provider_llm, "_get_openai_client",
                        lambda: _OpenAIStyleClient(captured))
    text, reason = multi_provider_llm.send_prompt_openai_meta("hi", timeout=45)
    assert text == "reply" and reason == "stop"
    assert captured["timeout"] == 45


def test_openai_without_timeout_omits_the_kwarg(monkeypatch):
    # The convenience-function contract: timeout unset means the SDK default
    # governs, exactly the pre-timeout behavior.
    captured = {}
    monkeypatch.setattr(multi_provider_llm, "_get_openai_client",
                        lambda: _OpenAIStyleClient(captured))
    multi_provider_llm.send_prompt_openai_meta("hi")
    assert "timeout" not in captured


def test_openrouter_timeout_reaches_the_request(monkeypatch):
    captured = {}
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-haiku-4.5")
    monkeypatch.setattr(multi_provider_llm, "_get_openrouter_client",
                        lambda: _OpenAIStyleClient(captured))
    multi_provider_llm.send_prompt_openrouter_meta("hi", timeout=120)
    assert captured["timeout"] == 120


def test_hosted_llm_timeout_reaches_the_request(monkeypatch):
    captured = {}
    monkeypatch.setenv("HOSTED_LLM_MODEL", "qwen")
    monkeypatch.setattr(multi_provider_llm, "_get_hosted_llm_client",
                        lambda: _OpenAIStyleClient(captured))
    multi_provider_llm.send_prompt_hosted_llm_meta("hi", timeout=60)
    assert captured["timeout"] == 60


def test_anthropic_timeout_reaches_the_request(monkeypatch):
    captured = {}

    class _Block:
        text = "claude says hi"

    class _Response:
        content = [_Block()]
        stop_reason = "end_turn"

    class _Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Response()

    class _Client:
        messages = _Messages()

    monkeypatch.setattr(multi_provider_llm, "_get_anthropic_client", lambda: _Client())
    text, reason = multi_provider_llm.send_prompt_claude_meta("hi", timeout=90)
    assert text == "claude says hi" and reason == "stop"
    assert captured["timeout"] == 90


def test_gemini_timeout_rides_request_options(monkeypatch):
    captured = {}

    class _Response:
        text = "gemini says hi"
        candidates = []

    class _Model:
        def __init__(self, name):
            self.name = name

        def generate_content(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured.update(kwargs)
            return _Response()

    class _Types:
        @staticmethod
        def GenerationConfig(**kwargs):
            return kwargs

    class _FakeGenai:
        GenerativeModel = _Model
        types = _Types()

    monkeypatch.setattr(multi_provider_llm, "genai", _FakeGenai())
    monkeypatch.setattr(multi_provider_llm, "_gemini_configured", True)
    text, _ = multi_provider_llm.send_prompt_gemini_meta("hi", timeout=75)
    assert text == "gemini says hi"
    assert captured["request_options"] == {"timeout": 75}
    assert captured["prompt"] == "hi"


def test_client_rejecting_timeout_kwarg_degrades_gracefully(monkeypatch):
    # A create() with a closed signature (a fake, an older SDK) must not break
    # the call: the request is retried without the timeout kwargs.
    calls = {"count": 0}

    class _Message:
        content = "still works"

    class _Choice:
        message = _Message()
        finish_reason = "stop"

    class _Response:
        choices = [_Choice()]

    class _Completions:
        def create(self, model, messages, max_tokens, temperature):
            calls["count"] += 1
            return _Response()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    monkeypatch.setattr(multi_provider_llm, "_get_openai_client", lambda: _Client())
    text, _ = multi_provider_llm.send_prompt_openai_meta("hi", timeout=45)
    assert text == "still works"
    assert calls["count"] == 1  # the timeout attempt TypeErrored before any work


def test_interface_threads_instance_timeout_into_registry(monkeypatch):
    captured = {}

    def fake_entry(prompt, max_tokens, timeout=None):
        captured.update(prompt=prompt, max_tokens=max_tokens, timeout=timeout)
        return "hi"

    monkeypatch.setitem(multi_provider_llm._model_config, "openrouter", fake_entry)
    client = multi_provider_llm.MultiProviderInterface(model="openrouter", timeout=77)

    assert client.generate("ping", max_tokens=10) == "hi"
    assert captured["timeout"] == 77

    # A per-call timeout overrides the instance default.
    client.generate("ping", max_tokens=10, timeout=12)
    assert captured["timeout"] == 12


def test_interface_without_timeout_keeps_two_arg_registry_contract(monkeypatch):
    # Contract stability: a two-positional-arg registry entry (the shape older
    # tests and code monkeypatch in) keeps working for callers without a
    # timeout, and degrades gracefully when one is set.
    calls = {}

    def two_arg_entry(prompt, max_tokens):
        calls.update(prompt=prompt, max_tokens=max_tokens)
        return "legacy"

    monkeypatch.setitem(multi_provider_llm._model_config, "openrouter", two_arg_entry)

    no_timeout = multi_provider_llm.MultiProviderInterface(model="openrouter")
    assert no_timeout.generate("ping", max_tokens=5) == "legacy"

    with_timeout = multi_provider_llm.MultiProviderInterface(model="openrouter", timeout=30)
    assert with_timeout.generate("ping", max_tokens=5) == "legacy"
    assert calls == {"prompt": "ping", "max_tokens": 5}


def test_initialize_llm_wires_timeout_into_api_backend():
    from novel_agent.tools.llm_interface import initialize_llm

    client = initialize_llm(backend="api", model="openrouter", timeout=120)
    assert isinstance(client, multi_provider_llm.MultiProviderInterface)
    assert client.timeout == 120

    # Unset falls back to 300, same as the CLI backends' default_timeout.
    client = initialize_llm(backend="api", model="openrouter")
    assert client.timeout == 300


def test_clients_constructed_with_capped_sdk_retries(monkeypatch):
    class RetryAwareFakeOpenAI:
        def __init__(self, base_url=None, api_key=None, max_retries=None,
                     timeout=None):
            self.base_url = base_url
            self.max_retries = max_retries
            self.timeout = timeout

    monkeypatch.setattr(multi_provider_llm, "OpenAI", RetryAwareFakeOpenAI)
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    # llm-backends adoption (intended change): the OpenRouter client uses the
    # analyzer's hardened settings (max_retries=6, client timeout=120s;
    # measured 20-26% paragraph loss under the SDK default), NOT the general
    # SDK_MAX_RETRIES cap. Previously this asserted SDK_MAX_RETRIES here.
    client = multi_provider_llm._get_openrouter_client()
    assert client.max_retries == multi_provider_llm.OPENROUTER_MAX_RETRIES
    assert multi_provider_llm.OPENROUTER_MAX_RETRIES == 6
    assert client.timeout == multi_provider_llm.OPENROUTER_TIMEOUT

    # Every other client keeps the wall-time-bounding internal-retry cap.
    plain = multi_provider_llm._get_openai_client()
    assert plain.max_retries == multi_provider_llm.SDK_MAX_RETRIES
    assert multi_provider_llm.SDK_MAX_RETRIES == 1


def test_construct_client_drops_kwarg_for_closed_constructors():
    # The existing FakeOpenAI shape (no max_retries) must keep constructing:
    # the retry cap is a nicety, never a break.
    built = multi_provider_llm._construct_client(FakeOpenAI, api_key="k")
    assert isinstance(built, FakeOpenAI)


# ---- planner robustness to an empty backend response -------------------------

def test_planner_survives_a_none_response():
    """A live run lost a tick to this: the tactical stage got None from the
    backend and raised AttributeError from inside the JSON parser, then the
    run loop spent its retries reproducing it."""
    from novel_agent.agent.multi_stage_planner import MultiStagePlanner

    class _Mem:
        def get_active_character(self):
            return "C000"

    p = MultiStagePlanner.__new__(MultiStagePlanner)
    p.memory = _Mem()
    for bad in (None, "", 42, b"bytes"):
        plan = MultiStagePlanner._parse_plan_response(p, bad)
        assert isinstance(plan, dict), bad
        assert plan["scene_intention"] == "Continue the story"
        assert plan["actions"] == []
    # A real response still parses.
    ok = MultiStagePlanner._parse_plan_response(
        p, 'noise {"scene_intention": "Elena opens the notebook"} trailing')
    assert ok["scene_intention"] == "Elena opens the notebook"


class _Cfg:
    """Minimal config stand-in: the planner reads only its token budget."""

    def __init__(self, planner_max_tokens=4000):
        self._budget = planner_max_tokens

    def get(self, key, default=None):
        if key == 'llm.planner_max_tokens':
            return self._budget
        return default


def test_tactical_planning_retries_before_degrading():
    """The backend returns None whenever the provider sends null content, and
    the degraded plan has no POV character, no intention and no tool actions.
    Four consecutive live runs produced 4/4 degraded plans while reporting
    success, so this path gets the same retry-once treatment as every other
    LLM-dependent step."""
    from novel_agent.agent.multi_stage_planner import MultiStagePlanner

    class Mem:
        def get_active_character(self):
            return "C000"

    class LLM:
        def __init__(self, responses):
            self.responses = list(responses)
            self.calls = 0

        def generate(self, prompt, max_tokens=2000):
            self.calls += 1
            return self.responses.pop(0)

    p = MultiStagePlanner.__new__(MultiStagePlanner)
    p.memory, p.save_prompts, p.prompts_dir = Mem(), False, None
    p.stage_stats, p.tool_registry = {}, None
    p.config = _Cfg()
    p._build_tactical_prompt = lambda *a, **k: "PROMPT"

    # first call empty, retry succeeds
    p.llm = LLM([None, '{"scene_intention": "Elena opens the notebook"}'])
    plan = MultiStagePlanner._tactical_planning(p, "an intention", {}, {"active_character": "C000"})
    assert p.llm.calls == 2
    assert plan["scene_intention"] == "Elena opens the notebook"
    assert not MultiStagePlanner._is_degraded(plan)

    # both empty: degrade, but only after trying twice
    p.llm = LLM([None, None])
    plan = MultiStagePlanner._tactical_planning(p, "an intention", {}, {"active_character": "C000"})
    assert p.llm.calls == 2
    assert MultiStagePlanner._is_degraded(plan)


def test_a_good_plan_is_not_retried():
    from novel_agent.agent.multi_stage_planner import MultiStagePlanner

    class LLM:
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, max_tokens=2000):
            self.calls += 1
            return '{"scene_intention": "fine"}'

    class Mem2:
        def get_active_character(self):
            return "C000"

    p = MultiStagePlanner.__new__(MultiStagePlanner)
    p.save_prompts, p.prompts_dir, p.stage_stats = False, None, {}
    p.memory, p.tool_registry = Mem2(), None
    p.config = _Cfg()
    p._build_tactical_prompt = lambda *a, **k: "PROMPT"
    p.llm = LLM()
    MultiStagePlanner._tactical_planning(p, "an intention", {}, {"active_character": "C000"})
    assert p.llm.calls == 1


def test_looks_truncated_separates_a_cut_off_plan_from_a_malformed_one():
    """A truncated plan and a malformed one need different fixes, and a live
    session lost its time to them reading identically in the log. Truncation
    means the token budget; malformed means the prompt or the model."""
    from novel_agent.agent.multi_stage_planner import MultiStagePlanner as M

    # cut off mid-string, which is what a live tick produced twice running
    assert M.looks_truncated('{"tool": "location.generate", "description": "A small isl')
    # cut off between members, braces still open
    assert M.looks_truncated('{"actions": [{"tool": "x"}, {"tool": "y"}')
    # complete, even wrapped in a fence and trailing prose
    assert not M.looks_truncated('```json\n{"scene_intention": "fine"}\n```\nThat is the plan.')
    # malformed but complete: a missing comma is not a budget problem
    assert not M.looks_truncated('{"a": 1 "b": 2}')
    # a brace inside a string must not count as structure
    assert not M.looks_truncated('{"description": "a {brace} in prose"}')
    assert M.looks_truncated('{"description": "a {brace} in prose"')
    # nothing to judge
    assert not M.looks_truncated("")
    assert not M.looks_truncated(None)
    assert not M.looks_truncated("no json here at all")


def test_a_truncated_plan_is_retried_with_a_bigger_budget():
    """Retrying a cut-off response at the same budget cuts it off again. A live
    tick truncated at 3,062 characters, retried, and truncated at 2,695."""
    from novel_agent.agent.multi_stage_planner import MultiStagePlanner

    class Mem:
        def get_active_character(self):
            return "C000"

    class LLM:
        def __init__(self, responses):
            self.responses = list(responses)
            self.budgets = []

        def generate(self, prompt, max_tokens=2000):
            self.budgets.append(max_tokens)
            return self.responses.pop(0)

    def planner(llm):
        p = MultiStagePlanner.__new__(MultiStagePlanner)
        p.memory, p.save_prompts, p.prompts_dir = Mem(), False, None
        p.stage_stats, p.tool_registry = {}, None
        p.config = _Cfg(planner_max_tokens=4000)
        p._build_tactical_prompt = lambda *a, **k: "PROMPT"
        p.llm = llm
        return p

    truncated = '{"scene_intention": "Elena opens the notebook", "actions": [{"tool": "x'
    good = '{"scene_intention": "Elena opens the notebook"}'

    p = planner(LLM([truncated, good]))
    plan = MultiStagePlanner._tactical_planning(p, "an intention", {}, {})
    assert p.llm.budgets == [4000, 8000]
    assert not MultiStagePlanner._is_degraded(plan)

    # a malformed response is not a budget problem, so the retry does not grow
    p = planner(LLM(['{"a": 1 "b": 2}', good]))
    MultiStagePlanner._tactical_planning(p, "an intention", {}, {})
    assert p.llm.budgets == [4000, 4000]

    # and an empty one is not either
    p = planner(LLM([None, good]))
    MultiStagePlanner._tactical_planning(p, "an intention", {}, {})
    assert p.llm.budgets == [4000, 4000]


def test_a_backend_reported_length_cut_counts_as_truncation():
    """The api backend says "length" outright when the ceiling cut a response
    off. The planner never asked, so a budget problem was reported for a whole
    session as a parse failure. Use the authoritative signal where it exists,
    and keep the structural check for the CLI backends, which expose nothing."""
    from novel_agent.agent.multi_stage_planner import MultiStagePlanner

    class Mem:
        def get_active_character(self):
            return "C000"

    good = '{"scene_intention": "Elena opens the notebook"}'

    class MetaLLM:
        """Returns valid-looking JSON that the backend still reports as cut."""

        def __init__(self):
            self.budgets = []

        def generate_with_meta(self, prompt, max_tokens=2000):
            self.budgets.append(max_tokens)
            if len(self.budgets) == 1:
                # complete braces, so only finish_reason reveals the cut
                return '{"a": 1 "b": 2}', "length"
            return good, "stop"

    p = MultiStagePlanner.__new__(MultiStagePlanner)
    p.memory, p.save_prompts, p.prompts_dir = Mem(), False, None
    p.stage_stats, p.tool_registry = {}, None
    p.config = _Cfg(planner_max_tokens=4000)
    p._build_tactical_prompt = lambda *a, **k: "PROMPT"
    p.llm = MetaLLM()

    plan = MultiStagePlanner._tactical_planning(p, "an intention", {}, {})
    assert p.llm.budgets == [4000, 8000]
    assert not MultiStagePlanner._is_degraded(plan)


def test_a_backend_without_meta_still_plans():
    """The CLI backends have no generate_with_meta; the planner must not
    require one."""
    from novel_agent.agent.multi_stage_planner import MultiStagePlanner

    class Mem:
        def get_active_character(self):
            return "C000"

    class PlainLLM:
        def __init__(self):
            self.calls = 0

        def generate(self, prompt, max_tokens=2000):
            self.calls += 1
            return '{"scene_intention": "fine"}'

    p = MultiStagePlanner.__new__(MultiStagePlanner)
    p.memory, p.save_prompts, p.prompts_dir = Mem(), False, None
    p.stage_stats, p.tool_registry = {}, None
    p.config = _Cfg()
    p._build_tactical_prompt = lambda *a, **k: "PROMPT"
    p.llm = PlainLLM()

    plan = MultiStagePlanner._tactical_planning(p, "an intention", {}, {})
    assert p.llm.calls == 1
    assert plan["scene_intention"] == "fine"

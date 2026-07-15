"""Multi-provider LLM interface (ai_helper-style).

This module provides a model→function registry and a single send_prompt
entry point that can route prompts to different providers (OpenAI, Gemini,
Claude) based on the model name.

It is inspired by the NovelWriter ai_helper.py design and is intended to be
flexible: you choose a model string (e.g. "gpt-5.5", "claude-sonnet-4.5",
"claude-haiku-4.5", "gemini-3-flash-preview"), and the correct client will be
used under the hood. See `_model_config` for the full supported set.

Environment variables expected (if using those providers):

- OPENAI_API_KEY   – for OpenAI Chat API
- GEMINI_API_KEY   – for Google Gemini
- CLAUDE_API_KEY – for Anthropic Claude
- HOSTED_LLM_URL / HOSTED_LLM_PORT / HOSTED_LLM_API_KEY / HOSTED_LLM_MODEL
                   – for a self-hosted, OpenAI-compatible endpoint (model "hosted-llm")
- OPENROUTER_API_KEY / OPENROUTER_MODEL
                   – for OpenRouter, a hosted OpenAI-compatible router over many
                     providers (model "openrouter")
- VENICE_API_KEY / VENICE_MODEL
                   – for Venice (https://venice.ai), an OpenAI-compatible host of
                     open-weight models including uncensored variants (model "venice")

The rest of StoryDaemon can either call send_prompt(model=..., ...) directly
or use the MultiProviderInterface wrapper, which exposes generate/
generate_with_retry methods.
"""

from typing import Callable, Dict, List, Optional, Tuple
import os


try:  # OpenAI is a declared dependency
    from openai import OpenAI  # type: ignore
except ImportError:  # pragma: no cover - should be installed via setup.py
    OpenAI = None  # type: ignore

try:
    import google.generativeai as genai  # type: ignore
except ImportError:  # pragma: no cover - optional, only needed for Gemini
    genai = None  # type: ignore

try:
    import anthropic  # type: ignore
except ImportError:  # pragma: no cover - optional, only needed for Claude
    anthropic = None  # type: ignore


_openai_client: Optional["OpenAI"] = None
_hosted_llm_client: Optional["OpenAI"] = None
_openrouter_client: Optional["OpenAI"] = None
_venice_client: Optional["OpenAI"] = None
_anthropic_client: Optional["anthropic.Anthropic"] = None
_gemini_configured: bool = False

# Cap the SDKs' INTERNAL retries (Phase 3 hardening, docs/progress_report_20260712.md
# section 8.1). The OpenAI and Anthropic SDKs default to 2 internal retries per
# request, which multiplies a per-attempt timeout into ~3x worst-case wall time
# (with the SDK's default 600s attempt timeout that was a possible ~30 minutes per
# call; the triple run drew a 22.4-minute stall from exactly this). One internal
# retry keeps transient-blip resilience while bounding worst-case wall time near
# 2x the configured timeout; StoryDaemon's own retry layers (generate_with_retry,
# the extractors' retry-once policy, `novel run --retries`) sit above this.
SDK_MAX_RETRIES = 1


def _construct_client(ctor, **kwargs):
    """Build an SDK client with the internal-retry cap, dropping the kwarg when
    the constructor rejects it (test fakes, older SDKs). A hardening nicety must
    never break client construction (graceful degradation)."""
    try:
        return ctor(max_retries=SDK_MAX_RETRIES, **kwargs)
    except TypeError:
        return ctor(**kwargs)


def _call_with_timeout(fn, timeout_kwargs: Optional[Dict], *args, **kwargs):
    """Invoke a provider request, attaching per-request timeout kwargs when set.

    Phase 3 hardening (docs/progress_report_20260712.md section 8.1): llm.timeout
    was inert on the whole api backend, so SDK defaults governed a 22.4-minute
    hang. Each provider spells the timeout differently (OpenAI-shaped and
    Anthropic take ``timeout=...`` on the request; Gemini takes
    ``request_options={"timeout": ...}``), so callers pass the provider-shaped
    kwargs. A client that rejects them (a test fake, an older SDK) must not
    break the call: on TypeError the request is retried once without the
    timeout kwargs, restoring the pre-timeout behavior exactly. Real SDKs all
    accept the kwargs, so the fallback never fires against a live provider.
    """
    if timeout_kwargs:
        try:
            return fn(*args, **kwargs, **timeout_kwargs)
        except TypeError:
            pass
    return fn(*args, **kwargs)


def _get_hosted_llm_client() -> "OpenAI":
    """Return a shared OpenAI client pointed at a self-hosted, OpenAI-compatible endpoint.

    Configured from HOSTED_LLM_URL, HOSTED_LLM_PORT and HOSTED_LLM_API_KEY. Kept
    separate from the OpenAI client so the two backends can coexist in one process.
    """
    global _hosted_llm_client

    if OpenAI is None:
        raise RuntimeError(
            "openai package is not installed. Install it with 'pip install openai' "
            "or switch llm.backend to 'codex'."
        )

    if _hosted_llm_client is None:
        url = os.environ.get("HOSTED_LLM_URL")
        port = os.environ.get("HOSTED_LLM_PORT")
        api_key = os.environ.get("HOSTED_LLM_API_KEY")
        if not url or not port:
            raise RuntimeError(
                "Environment variables 'HOSTED_LLM_URL' and 'HOSTED_LLM_PORT' must both be set "
                "for the 'hosted-llm' backend. Set them or use a different backend (e.g. Codex)."
            )
        if not api_key:
            raise RuntimeError(
                "Environment variable 'HOSTED_LLM_API_KEY' is not set. "
                "Set your HOSTED_LLM_API_KEY or use a different backend (e.g. Codex)."
            )
        _hosted_llm_client = _construct_client(
            OpenAI, base_url=f"http://{url}:{port}/v1", api_key=api_key
        )

    return _hosted_llm_client


def _get_openrouter_client() -> "OpenAI":
    """Return a shared OpenAI client pointed at OpenRouter (https://openrouter.ai).

    OpenRouter is a hosted, OpenAI-compatible router over many upstream models.
    Configured from OPENROUTER_API_KEY. Kept separate from the other clients so
    the backends can coexist in one process.
    """
    global _openrouter_client

    if OpenAI is None:
        raise RuntimeError(
            "openai package is not installed. Install it with 'pip install openai' "
            "or switch llm.backend to 'codex'."
        )

    if _openrouter_client is None:
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Environment variable 'OPENROUTER_API_KEY' is not set. "
                "Set your OpenRouter API key or use a different backend (e.g. Codex)."
            )
        _openrouter_client = _construct_client(
            OpenAI, base_url="https://openrouter.ai/api/v1", api_key=api_key
        )

    return _openrouter_client


def _get_venice_client() -> "OpenAI":
    """Return a shared OpenAI client pointed at Venice (https://venice.ai).

    Venice is an OpenAI-compatible host of open-weight models, including
    uncensored variants some writers want for unfiltered fiction. Configured
    from VENICE_API_KEY. Kept separate from the other clients so the backends
    can coexist in one process.
    """
    global _venice_client

    if OpenAI is None:
        raise RuntimeError(
            "openai package is not installed. Install it with 'pip install openai' "
            "or switch llm.backend to 'codex'."
        )

    if _venice_client is None:
        api_key = os.environ.get("VENICE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Environment variable 'VENICE_API_KEY' is not set. "
                "Set your Venice API key or use a different backend (e.g. Codex)."
            )
        _venice_client = _construct_client(
            OpenAI, base_url="https://api.venice.ai/api/v1", api_key=api_key
        )

    return _venice_client


def _get_openai_client() -> "OpenAI":
    """Return a shared OpenAI client, initialized from OPENAI_API_KEY."""
    global _openai_client

    if OpenAI is None:
        raise RuntimeError(
            "openai package is not installed. Install it with 'pip install openai' "
            "or switch llm.backend to 'codex'."
        )

    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Environment variable 'OPENAI_API_KEY' is not set. "
                "Set your OpenAI API key or use a different backend (e.g. Codex)."
            )
        _openai_client = _construct_client(OpenAI, api_key=api_key)

    return _openai_client


def _get_anthropic_client() -> "anthropic.Anthropic":
    """Return a shared Anthropic client, initialized from CLAUDE_API_KEY."""
    global _anthropic_client

    if anthropic is None:
        raise RuntimeError(
            "anthropic package is not installed. Install it with 'pip install anthropic' "
            "or use a different model that does not require Claude."
        )

    if _anthropic_client is None:
        api_key = os.environ.get("CLAUDE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Environment variable 'CLAUDE_API_KEY' is not set. "
                "Set your Anthropic API key or use a different model."
            )
        _anthropic_client = _construct_client(anthropic.Anthropic, api_key=api_key)

    return _anthropic_client


def _ensure_gemini_configured():
    """Configure Gemini client using GEMINI_API_KEY if available."""
    global _gemini_configured

    if _gemini_configured:
        return

    if genai is None:
        raise RuntimeError(
            "google-generativeai package is not installed. Install it with "
            "'pip install google-generativeai' or use a different model."
        )

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Environment variable 'GEMINI_API_KEY' is not set. "
            "Set your Gemini API key or use a different model."
        )

    genai.configure(api_key=api_key)
    _gemini_configured = True


# --- Finish-reason extraction (Phase 3, segment plumbing for the block DSL) ----------
#
# The write-until-concluded scene loop needs to know when a response was cut by
# the token ceiling. Each provider reports this differently; these helpers
# normalize to "length" (cut by max_tokens), "stop" (natural stop), any other
# provider string lowercased, or None (unavailable). Extraction is best-effort:
# a malformed response yields None and the caller's completion heuristic governs.

def _openai_finish_reason(response) -> Optional[str]:
    """choices[0].finish_reason from an OpenAI-shaped response ("length" is native)."""
    try:
        reason = response.choices[0].finish_reason
    except (AttributeError, IndexError, TypeError):
        return None
    if reason is None:
        return None
    return str(reason).strip().lower() or None


def _anthropic_finish_reason(response) -> Optional[str]:
    """Anthropic stop_reason, mapped: max_tokens -> "length", end_turn/stop_sequence -> "stop"."""
    reason = getattr(response, "stop_reason", None)
    if reason is None:
        return None
    reason = str(reason).strip().lower()
    if reason == "max_tokens":
        return "length"
    if reason in ("end_turn", "stop_sequence"):
        return "stop"
    return reason or None


def _gemini_finish_reason(response) -> Optional[str]:
    """Gemini candidates[0].finish_reason (enum, int, or string), normalized."""
    try:
        candidates = getattr(response, "candidates", None)
        reason = getattr(candidates[0], "finish_reason", None) if candidates else None
    except (IndexError, TypeError):
        return None
    if reason is None:
        return None
    if isinstance(reason, int):
        return {1: "stop", 2: "length"}.get(reason, str(reason))
    name = (getattr(reason, "name", None) or str(reason)).upper()
    if "MAX_TOKENS" in name:
        return "length"
    if name.endswith("STOP"):
        return "stop"
    return name.lower() or None


# --- Provider-specific prompt helpers -------------------------------------------------
#
# Each provider has a *_meta variant returning (text, finish_reason) for the
# segment loop, and keeps its original text-only function (contract unchanged)
# as a thin wrapper.

def send_prompt_hosted_llm_meta(
    prompt: str,
    model: str = "",
    max_tokens: int = 2000,
    temperature: float = 0.7,
    role_description: str = (
        "You are a helpful fiction writing assistant. You will create original text only."
    ),
    timeout: Optional[float] = None,
) -> Tuple[str, Optional[str]]:
    """Send a prompt to a self-hosted, OpenAI-compatible chat endpoint.

    Returns (text, finish_reason): hosted endpoints are OpenAI-shaped.
    ``timeout`` (seconds) is applied per request; None keeps the SDK default.
    """
    if model == "":
        model = os.environ.get("HOSTED_LLM_MODEL", None)
    if not model:
        raise ValueError(
            "Model name must be specified either as a parameter or via HOSTED_LLM_MODEL environment variable."
        )
    client = _get_hosted_llm_client()
    response = _call_with_timeout(
        client.chat.completions.create,
        {"timeout": timeout} if timeout is not None else None,
        model=model,
        messages=[
            {"role": "system", "content": role_description},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        # Disable "thinking" for more deterministic output (only honored by hosts
        # that support it, e.g. vLLM/Qwen; ignored by servers that don't).
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    return response.choices[0].message.content, _openai_finish_reason(response)


def send_prompt_hosted_llm(*args, **kwargs) -> str:
    """Text-only wrapper around send_prompt_hosted_llm_meta (original contract)."""
    return send_prompt_hosted_llm_meta(*args, **kwargs)[0]


def send_prompt_openrouter_meta(
    prompt: str,
    model: str = "",
    max_tokens: int = 2000,
    temperature: float = 0.7,
    role_description: str = (
        "You are a helpful fiction writing assistant. You will create original text only."
    ),
    timeout: Optional[float] = None,
) -> Tuple[str, Optional[str]]:
    """Send a prompt to OpenRouter, a hosted OpenAI-compatible router over many models.

    Returns (text, finish_reason): OpenRouter responses are OpenAI-shaped.
    ``timeout`` (seconds) is applied per request; None keeps the SDK default
    (this client drew the 22.4-minute hang the timeout plumbing exists for).
    """
    if model == "":
        model = os.environ.get("OPENROUTER_MODEL", None)
    if not model:
        raise ValueError(
            "Model name must be specified either as a parameter or via OPENROUTER_MODEL environment variable."
        )
    client = _get_openrouter_client()
    response = _call_with_timeout(
        client.chat.completions.create,
        {"timeout": timeout} if timeout is not None else None,
        model=model,
        messages=[
            {"role": "system", "content": role_description},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        # Note: unlike hosted-llm, no provider-specific extra_body is set here.
        # OpenRouter fans out to many different upstream backends, so a hack tuned
        # for one of them (e.g. vLLM/Qwen's enable_thinking flag) would be silently
        # ignored by most others and would be misleading to carry as a default.
    )
    return response.choices[0].message.content, _openai_finish_reason(response)


def send_prompt_openrouter(*args, **kwargs) -> str:
    """Text-only wrapper around send_prompt_openrouter_meta (original contract)."""
    return send_prompt_openrouter_meta(*args, **kwargs)[0]


def send_prompt_venice_meta(
    prompt: str,
    model: str = "",
    max_tokens: int = 2000,
    temperature: float = 0.7,
    role_description: str = (
        "You are a helpful fiction writing assistant. You will create original text only."
    ),
    timeout: Optional[float] = None,
) -> Tuple[str, Optional[str]]:
    """Send a prompt to Venice (https://venice.ai), an OpenAI-compatible host.

    Returns (text, finish_reason): Venice responses are OpenAI-shaped.
    ``timeout`` (seconds) is applied per request; None keeps the SDK default.
    """
    if model == "":
        model = os.environ.get("VENICE_MODEL", None)
    if not model:
        raise ValueError(
            "Model name must be specified either as a parameter or via VENICE_MODEL environment variable."
        )
    client = _get_venice_client()
    response = _call_with_timeout(
        client.chat.completions.create,
        {"timeout": timeout} if timeout is not None else None,
        model=model,
        messages=[
            {"role": "system", "content": role_description},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
        # Venice injects its own default system prompt unless told not to; this
        # pipeline supplies its own system + writer prompts, so Venice's must not
        # stack on top (per the Venice API docs' venice_parameters; an
        # OpenAI-compatible server that doesn't know the field ignores it).
        extra_body={"venice_parameters": {"include_venice_system_prompt": False}},
    )
    return response.choices[0].message.content, _openai_finish_reason(response)


def send_prompt_venice(*args, **kwargs) -> str:
    """Text-only wrapper around send_prompt_venice_meta (original contract)."""
    return send_prompt_venice_meta(*args, **kwargs)[0]


def send_prompt_openai_meta(
    prompt: str,
    model: str = "gpt-5.5",
    max_tokens: int = 2000,
    temperature: float = 0.7,
    role_description: str = (
        "You are a helpful fiction writing assistant. You will create original text only."
    ),
    timeout: Optional[float] = None,
) -> Tuple[str, Optional[str]]:
    """Send a prompt to the OpenAI Chat API. Returns (text, finish_reason).

    ``timeout`` (seconds) is applied per request; None keeps the SDK default.
    """
    client = _get_openai_client()
    response = _call_with_timeout(
        client.chat.completions.create,
        {"timeout": timeout} if timeout is not None else None,
        model=model,
        messages=[
            {"role": "system", "content": role_description},
            {"role": "user", "content": prompt},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content, _openai_finish_reason(response)


def send_prompt_openai(*args, **kwargs) -> str:
    """Text-only wrapper around send_prompt_openai_meta (original contract)."""
    return send_prompt_openai_meta(*args, **kwargs)[0]


def send_prompt_gemini_meta(
    prompt: str,
    model_name: str = "gemini-2.5-pro",
    max_output_tokens: int = 2048,
    temperature: float = 0.9,
    timeout: Optional[float] = None,
) -> Tuple[str, Optional[str]]:
    """Send a prompt to the Gemini API. Returns (text, finish_reason).

    ``timeout`` (seconds) rides ``request_options``; None keeps the SDK default.
    """
    _ensure_gemini_configured()
    model = genai.GenerativeModel(model_name)
    response = _call_with_timeout(
        model.generate_content,
        {"request_options": {"timeout": timeout}} if timeout is not None else None,
        prompt,
        generation_config=genai.types.GenerationConfig(  # type: ignore[attr-defined]
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        ),
        stream=False,
    )
    return getattr(response, "text", ""), _gemini_finish_reason(response)


def send_prompt_gemini(*args, **kwargs) -> str:
    """Text-only wrapper around send_prompt_gemini_meta (original contract)."""
    return send_prompt_gemini_meta(*args, **kwargs)[0]


def send_prompt_claude_meta(
    prompt: str,
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 4096,
    temperature: float = 0.7,
    role_description: str = (
        "You are a skilled creative writer focused on producing original fiction."
    ),
    timeout: Optional[float] = None,
) -> Tuple[str, Optional[str]]:
    """Send a prompt to Anthropic Claude. Returns (text, finish_reason).

    ``timeout`` (seconds) is applied per request; None keeps the SDK default.
    """
    client = _get_anthropic_client()
    response = _call_with_timeout(
        client.messages.create,
        {"timeout": timeout} if timeout is not None else None,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=role_description,
        messages=[{"role": "user", "content": prompt}],
    )
    finish_reason = _anthropic_finish_reason(response)
    # Anthropic returns a list of content blocks; we take the first text block
    if response.content and hasattr(response.content[0], "text"):
        return response.content[0].text, finish_reason  # type: ignore[no-any-return]
    return "", finish_reason


def send_prompt_claude(*args, **kwargs) -> str:
    """Text-only wrapper around send_prompt_claude_meta (original contract)."""
    return send_prompt_claude_meta(*args, **kwargs)[0]


# --- Model registry (ai_helper-style) --------------------------------------------------


ModelFn = Callable[..., str]
ModelMetaFn = Callable[..., Tuple[str, Optional[str]]]


# The meta registry is the single source of truth (Phase 3, segment plumbing):
# every entry returns (text, finish_reason) and accepts an optional per-request
# timeout in seconds (Phase 3 hardening; None keeps the SDK default). The
# text-only _model_config below is derived from it, so the two can never drift.
# When refreshing models, update THIS registry (and the gpt-5.5 fallback
# literals in cli/main.py/commands/*.py).
_model_config_meta: Dict[str, ModelMetaFn] = {
    # Self-hosted, OpenAI-compatible endpoint (configured via HOSTED_LLM_* env vars)
    "hosted-llm": lambda prompt, max_tokens, timeout=None: send_prompt_hosted_llm_meta(
        prompt=prompt, max_tokens=max_tokens, timeout=timeout,
    ),
    # OpenRouter, a hosted OpenAI-compatible router over many models (configured via OPENROUTER_* env vars)
    "openrouter": lambda prompt, max_tokens, timeout=None: send_prompt_openrouter_meta(
        prompt=prompt, max_tokens=max_tokens, timeout=timeout,
    ),
    # Venice, an OpenAI-compatible host of open-weight/uncensored models (configured via VENICE_* env vars)
    "venice": lambda prompt, max_tokens, timeout=None: send_prompt_venice_meta(
        prompt=prompt, max_tokens=max_tokens, timeout=timeout,
    ),
    # OpenAI GPT-5 family (kept in sync with LLM-Remote-Runner)
    "gpt-5.5": lambda prompt, max_tokens, timeout=None: send_prompt_openai_meta(
        prompt=prompt, model="gpt-5.5", max_tokens=max_tokens, timeout=timeout,
    ),
    "gpt-5.4": lambda prompt, max_tokens, timeout=None: send_prompt_openai_meta(
        prompt=prompt, model="gpt-5.4", max_tokens=max_tokens, timeout=timeout,
    ),
    "gpt-5.2": lambda prompt, max_tokens, timeout=None: send_prompt_openai_meta(
        prompt=prompt, model="gpt-5.2", max_tokens=max_tokens, timeout=timeout,
    ),
    # Anthropic Claude 4.5 family
    "claude-sonnet-4.5": lambda prompt, max_tokens, timeout=None: send_prompt_claude_meta(
        prompt=prompt, model="claude-sonnet-4-5-20250929", max_tokens=max_tokens, timeout=timeout,
    ),
    "claude-haiku-4.5": lambda prompt, max_tokens, timeout=None: send_prompt_claude_meta(
        prompt=prompt, model="claude-haiku-4-5-20251001", max_tokens=max_tokens, timeout=timeout,
    ),
    # Back-compat alias -> Sonnet (referenced by existing configs/docs)
    "claude-4.5": lambda prompt, max_tokens, timeout=None: send_prompt_claude_meta(
        prompt=prompt, model="claude-sonnet-4-5-20250929", max_tokens=max_tokens, timeout=timeout,
    ),
    # Google Gemini
    "gemini-3-flash-preview": lambda prompt, max_tokens, timeout=None: send_prompt_gemini_meta(
        prompt=prompt, model_name="gemini-3-flash-preview", max_output_tokens=max_tokens, timeout=timeout,
    ),
    "gemini-3-pro-preview": lambda prompt, max_tokens, timeout=None: send_prompt_gemini_meta(
        prompt=prompt, model_name="gemini-3-pro-preview", max_output_tokens=max_tokens, timeout=timeout,
    ),
    "gemini-3.1-pro-preview": lambda prompt, max_tokens, timeout=None: send_prompt_gemini_meta(
        prompt=prompt, model_name="gemini-3.1-pro-preview", max_output_tokens=max_tokens, timeout=timeout,
    ),
    "gemini-2.5-pro": lambda prompt, max_tokens, timeout=None: send_prompt_gemini_meta(
        prompt=prompt, model_name="gemini-2.5-pro", max_output_tokens=max_tokens, timeout=timeout,
    ),
    "gemini-2.5-flash": lambda prompt, max_tokens, timeout=None: send_prompt_gemini_meta(
        prompt=prompt, model_name="gemini-2.5-flash", max_output_tokens=max_tokens, timeout=timeout,
    ),
}


def _call_model_fn(fn, prompt: str, max_tokens: int, timeout: Optional[float]):
    """Invoke a registry entry, forwarding the timeout only when one is set.

    Callers without a timeout keep the exact positional (prompt, max_tokens)
    contract (tests and older code monkeypatch two-arg entries into the
    registries); an entry that rejects the timeout kwarg degrades to the
    timeout-less call rather than breaking (same graceful rule as
    _call_with_timeout).
    """
    if timeout is not None:
        try:
            return fn(prompt, max_tokens, timeout=timeout)
        except TypeError:
            pass
    return fn(prompt, max_tokens)


def _text_only(meta_fn: ModelMetaFn) -> ModelFn:
    """Adapt a (text, finish_reason) model function to the text-only contract."""
    def call(prompt: str, max_tokens: int, timeout: Optional[float] = None) -> str:
        return _call_model_fn(meta_fn, prompt, max_tokens, timeout)[0]
    return call


# Text-only registry, derived from the meta registry (existing generate()
# callers and get_supported_models() keep their exact contract).
_model_config: Dict[str, ModelFn] = {
    name: _text_only(fn) for name, fn in _model_config_meta.items()
}


def get_supported_models() -> List[str]:
    """Return the list of supported model identifiers."""
    return list(_model_config.keys())


def _resolve_model_key(model: str, registry: Dict) -> str:
    """Resolve a model key against a registry, trying a "-latest" suffix before failing."""
    if model in registry:
        return model
    alt = f"{model}-latest"
    if alt in registry:
        return alt
    supported = ", ".join(sorted(get_supported_models()))
    raise ValueError(
        f"Unsupported model: {model}. Supported models are: {supported}"
    )


def send_prompt(
    prompt: str,
    model: str = "gpt-5.5",
    max_tokens: int = 2000,
    timeout: Optional[float] = None,
) -> str:
    """Send a prompt using the configured model registry.

    If the model key is not found, tries a "-latest" suffix before failing.
    ``timeout`` (seconds) is forwarded per request; None (the default, so
    standalone convenience callers keep their exact old behavior) leaves the
    SDK defaults in charge.
    """
    model = _resolve_model_key(model, _model_config)
    try:
        return _call_model_fn(_model_config[model], prompt, max_tokens, timeout)
    except Exception as e:  # noqa: BLE001 - we want a simple wrapper
        raise RuntimeError(f"Error calling model '{model}': {e}") from e


def send_prompt_meta(
    prompt: str,
    model: str = "gpt-5.5",
    max_tokens: int = 2000,
    timeout: Optional[float] = None,
) -> Tuple[str, Optional[str]]:
    """Send a prompt and return (text, finish_reason).

    finish_reason is normalized across providers: "length" means the response
    was cut by the token ceiling, "stop" means a natural stop, None means the
    provider reported nothing usable. Phase 3 segment plumbing for the
    write-until-concluded scene loop. ``timeout`` as in ``send_prompt``.
    """
    model = _resolve_model_key(model, _model_config_meta)
    try:
        return _call_model_fn(_model_config_meta[model], prompt, max_tokens, timeout)
    except Exception as e:  # noqa: BLE001 - we want a simple wrapper
        raise RuntimeError(f"Error calling model '{model}': {e}") from e


def send_prompt_with_retry(
    prompt: str,
    model: str = "gpt-5.5",
    max_tokens: int = 2000,
    max_retries: int = 3,
    timeout: Optional[float] = None,
) -> str:
    """Send a prompt with simple retry logic on failure."""
    last_error: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            return send_prompt(prompt, model=model, max_tokens=max_tokens,
                               timeout=timeout)
        except Exception as e:  # noqa: BLE001
            last_error = e
            if attempt < max_retries - 1:
                continue

    raise RuntimeError(
        f"Model '{model}' failed after {max_retries} attempts. Last error: {last_error}"
    ) from last_error


class MultiProviderInterface:
    """Thin adapter exposing generate / generate_with_retry.

    This class allows the rest of StoryDaemon to treat the ai_helper-style
    functions as a simple LLM client with generate(...) and
    generate_with_retry(...), similar to CodexInterface.

    ``timeout`` (seconds) is the per-request ceiling applied on every provider
    path (Phase 3 hardening, docs/progress_report_20260712.md section 8.1: the
    old signature ACCEPTED a timeout and ignored it, so ``llm.timeout`` was
    inert on the whole api backend and the SDK defaults governed a 22.4-minute
    hang). initialize_llm wires it from ``llm.timeout``; a per-call timeout
    argument overrides the instance default; None means SDK defaults.
    """

    def __init__(self, model: str = "gpt-5.5", timeout: Optional[float] = None):
        self.model = model
        self.timeout = timeout

    def _effective_timeout(self, timeout: Optional[float]) -> Optional[float]:
        return timeout if timeout is not None else self.timeout

    def generate(self, prompt: str, max_tokens: int = 2000,
                 timeout: Optional[float] = None) -> str:
        return send_prompt(prompt, model=self.model, max_tokens=max_tokens,
                           timeout=self._effective_timeout(timeout))

    def generate_with_meta(
        self, prompt: str, max_tokens: int = 2000, timeout: Optional[float] = None
    ) -> Tuple[str, Optional[str]]:
        """Generate and return (text, finish_reason). Phase 3 segment plumbing.

        finish_reason is normalized to "length" (cut by the token ceiling),
        "stop" (natural stop), another provider string, or None. Callers opt in
        via hasattr(client, "generate_with_meta"); the CLI backends (codex,
        claude-cli, gemini-cli) do not expose response metadata and simply lack
        this method, so everything degrades to the completion heuristic.
        """
        return send_prompt_meta(prompt, model=self.model, max_tokens=max_tokens,
                                timeout=self._effective_timeout(timeout))

    def generate_with_retry(
        self,
        prompt: str,
        max_tokens: int = 2000,
        timeout: Optional[float] = None,
        max_retries: int = 3,
    ) -> str:
        return send_prompt_with_retry(
            prompt,
            model=self.model,
            max_tokens=max_tokens,
            max_retries=max_retries,
            timeout=self._effective_timeout(timeout),
        )

"""The fiction persona must ride the api backend and only the api backend.

llm-backends 0.2.0 made the system prompt opt-in; StoryDaemon's opt-in lives in
novel_agent.tools.llm_setup. If the wrapper stops forwarding FICTION_ROLE, api
generations silently lose their persona: mocked suites cannot catch that at the
provider level, so it is pinned here at the wiring level.
"""
from llm_backends import FICTION_ROLE
from llm_backends.multi_provider_llm import MultiProviderInterface

from novel_agent.tools.llm_setup import initialize_llm_with_persona


def test_api_backend_carries_fiction_role():
    client = initialize_llm_with_persona(backend="api", model="gpt-5.5")
    assert isinstance(client, MultiProviderInterface)
    assert client.role_description == FICTION_ROLE


def test_cli_backend_gets_no_role_and_does_not_raise():
    client = initialize_llm_with_persona(backend="codex")
    assert not hasattr(client, "role_description")

"""Example entity IDs in prompts must use the real zero-padded form.

The model copies the IDs it sees in a prompt's example JSON. An example
written as "C0" gets echoed back as "C0", which no lookup finds (real IDs
are C000), so the update is silently skipped. This has been fixed prompt by
prompt more than once; the test covers every template so a stale copy
cannot survive in one nobody thought to check.
"""
import re

from novel_agent.agent import prompts

# A quoted character/location/scene/faction ID with fewer than three digits.
# Open-loop IDs (OL1) really are unpadded and do not match.
UNPADDED_ID = re.compile(r'"[CLSF]\d{1,2}"')


def test_no_prompt_uses_unpadded_example_ids():
    offenders = {
        name: UNPADDED_ID.findall(value)
        for name, value in vars(prompts).items()
        if isinstance(value, str) and UNPADDED_ID.search(value)
    }
    assert not offenders, f"unpadded example IDs in prompts: {offenders}"

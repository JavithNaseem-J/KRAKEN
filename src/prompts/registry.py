"""
Prompt version registry — maps each agent node to its active prompt module.

To change a prompt: create a new versioned file (e.g. decider_v2.py),
update the ACTIVE_VERSIONS entry, and restart the service.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import import_module

ACTIVE_VERSIONS: dict[str, str] = {
    "reasoner": "src.prompts.reasoner_v1",
    "decider": "src.prompts.decider_v1",
    "responder": "src.prompts.responder_v1",
}


@lru_cache
def get_prompt(node_name: str, prompt_key: str = "SYSTEM_PROMPT") -> str:
    """Load the active prompt for a given node. Raises KeyError if node not registered."""
    if node_name not in ACTIVE_VERSIONS:
        raise KeyError(
            f"No prompt registered for node '{node_name}'. Available: {list(ACTIVE_VERSIONS)}"
        )
    module = import_module(ACTIVE_VERSIONS[node_name])
    return getattr(module, prompt_key)

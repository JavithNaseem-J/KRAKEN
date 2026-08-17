
"""
Edge routing decisions for agent graph.
"""

from __future__ import annotations

from typing import Any


def route_after_decision(state: dict[str, Any]) -> str:
    """Route after decider node."""
    if state.get("selected_action"):
        return "executor"
    return "responder"

"""
Unit tests for the prompt registry and versioned prompts.
All tests run with zero network calls and zero LLM invocations.
"""

from __future__ import annotations

import pytest

from src.prompts.registry import ACTIVE_VERSIONS, get_prompt


def test_get_prompt_returns_string_for_registered_node() -> None:
    prompt = get_prompt("reasoner")
    assert isinstance(prompt, str)
    assert len(prompt.strip()) > 0
    assert "security reasoning analyst" in prompt


def test_get_prompt_raises_key_error_for_unknown_node() -> None:
    with pytest.raises(KeyError) as exc_info:
        get_prompt("nonexistent_node")
    assert "No prompt registered for node 'nonexistent_node'" in str(exc_info.value)
    assert "reasoner" in str(exc_info.value)


def test_decider_prompt_contains_available_actions_placeholder() -> None:
    prompt = get_prompt("decider", "SYSTEM_PROMPT_TEMPLATE")
    assert isinstance(prompt, str)
    assert "{available_actions}" in prompt
    assert "lead security triage decider" in prompt


def test_responder_prompt_contains_approval_status_section() -> None:
    prompt = get_prompt("responder")
    assert isinstance(prompt, str)
    assert "### **APPROVAL STATUS**" in prompt
    assert "### **ANALYSIS**" in prompt
    assert "### **ACTION TAKEN**" in prompt


def test_responder_approval_mandate_template_contains_format_vars() -> None:
    template = get_prompt("responder", "APPROVAL_MANDATE_TEMPLATE")
    assert isinstance(template, str)
    assert "{selected_action}" in template
    assert "{truncated_res}" in template


def test_active_versions_covers_all_llm_nodes() -> None:
    expected_nodes = {"reasoner", "decider", "responder"}
    assert set(ACTIVE_VERSIONS.keys()) == expected_nodes

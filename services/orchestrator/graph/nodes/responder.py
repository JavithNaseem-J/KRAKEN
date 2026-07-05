"""
Responder Node — composes the final answer and explanation for the user.

Synthesises everything in state into a clear, structured response:
  - What the agent found (from reasoning)
  - What action was taken (from action_result)
  - Why that action was selected (explanation)
  - If HITL was involved, whether it was approved or rejected

This node always produces a final_answer — even on error, the user gets
a meaningful message rather than an unhandled exception.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from services.orchestrator.graph.state import GraphState
from services.orchestrator.llm import get_llm

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """You are a professional security operations assistant for Xiarch security consultancy.

Compose a clear, structured response to the user based on:
1. What security policies, pentesting rules, or ticket details were analyzed.
2. What action was taken (e.g., auto_respond, escalate, request_info, close) and its results.
3. The specific evidence and facts from the knowledge base that led to the action or decision. You MUST explicitly list the cited evidence/facts in a dedicated section titled "EVIDENCE CITED:".
4. Whether human approval was required and the approval status.

Make sure to be concise, professional, and clear. Under a separate section "EVIDENCE CITED:", point out the exact facts from the SLA guidelines, policy files, or ticketing system that directly justified this triage decision.
"""

_MAX_RESULT_CHARS = 2_000


def _truncate_result(result: Any) -> str:
    """Helper to safely serialize and truncate the action result to prevent prompt bloating."""
    if result is None:
        return "None"
    try:
        data_str = json.dumps(result, indent=2)
    except Exception:
        data_str = str(result)

    if len(data_str) > _MAX_RESULT_CHARS:
        return data_str[:_MAX_RESULT_CHARS] + "\n... [Truncated for token budget]"
    return data_str


def responder_node(state: GraphState) -> dict:
    """
    Produce the final answer for the user.
    Falls back to a canned error message if the LLM fails.
    """
    session_id = state.get("session_id", "")
    log.info("responder.start", session_id=session_id)

    user_message = state.get("user_message", "")
    reasoning = state.get("reasoning", "")
    selected_action = state.get("selected_action", "auto_respond")
    action_result = state.get("action_result")
    approval_status = state.get("approval_status")
    evidence = state.get("evidence")
    error = state.get("error")

    # Build context for the LLM
    context_parts = [f"User request: {user_message}", f"\nReasoning:\n{reasoning}"]

    has_real_evidence = False
    if evidence and not evidence.startswith("System fallback"):
        context_parts.append(f"\nEvidence found in knowledge base: {evidence}")
        has_real_evidence = True

    if selected_action:
        context_parts.append(f"\nAction selected: {selected_action}")
        if approval_status:
            context_parts.append(f"Approval status: {approval_status}")
        if action_result:
            truncated_res = _truncate_result(action_result)
            context_parts.append(f"Action result:\n{truncated_res}")

    if error:
        context_parts.append(f"\nNote: An error occurred during processing: {error}")

    human_content = "\n".join(context_parts)

    try:
        llm = get_llm()
        response = llm.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=human_content),
            ]
        )
        final_answer = response.content.strip()
    except Exception as exc:
        log.error("responder.llm_error", error=str(exc))
        final_answer = (
            "I encountered an issue composing a response. "
            "Please try again or contact support if the issue persists."
        )

    # Build action explanation (used in audit log)
    explanation = f"Action '{selected_action}' was selected."
    if has_real_evidence:
        explanation += f" Evidence: {evidence}."
    if approval_status:
        explanation += f" Human approval status: {approval_status}."

    log.info("responder.done", session_id=session_id)

    return {
        "final_answer": final_answer,
        "action_explanation": explanation,
        "messages": [{"role": "assistant", "content": final_answer}],
    }

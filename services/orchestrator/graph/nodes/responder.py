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

from langchain_core.messages import HumanMessage, SystemMessage

import structlog

from ..graph.state import GraphState
from ..llm import get_llm

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """You are a helpful IT helpdesk agent.

Compose a clear, friendly response to the user based on:
1. What knowledge was found and analysed.
2. What action was taken (if any) and its result.
3. Whether human approval was required and what the outcome was.

Keep the response concise and professional. Explain what you did and why.
If an action was rejected or cancelled, explain that and offer alternatives.
Do not mention internal system details (node names, session IDs, etc.).
"""


def responder_node(state: GraphState) -> dict:
    """
    Produce the final answer for the user.
    Falls back to a canned error message if the LLM fails.
    """
    session_id = state.get("session_id", "")
    log.info("responder.start", session_id=session_id)

    user_message     = state.get("user_message", "")
    reasoning        = state.get("reasoning", "")
    selected_action  = state.get("selected_action", "respond_only")
    action_result    = state.get("action_result")
    approval_status  = state.get("approval_status")
    error            = state.get("error")

    # Build context for the LLM
    context_parts = [f"User request: {user_message}", f"\nReasoning:\n{reasoning}"]

    if selected_action and selected_action != "respond_only":
        context_parts.append(f"\nAction taken: {selected_action}")
        if approval_status:
            context_parts.append(f"Approval status: {approval_status}")
        if action_result:
            context_parts.append(f"Action result: {action_result}")

    if error:
        context_parts.append(f"\nNote: An error occurred during processing: {error}")

    human_content = "\n".join(context_parts)

    try:
        llm = get_llm()
        response = llm.invoke([
            SystemMessage(content=_SYSTEM_PROMPT),
            HumanMessage(content=human_content),
        ])
        final_answer = response.content.strip()
    except Exception as exc:
        log.error("responder.llm_error", error=str(exc))
        final_answer = (
            "I encountered an issue composing my response. "
            f"Here is what I found: {reasoning[:500]}"
        )

    # Build action explanation (used in audit log)
    explanation = f"Action '{selected_action}' was selected based on the reasoning above."
    if approval_status:
        explanation += f" Human approval status: {approval_status}."

    log.info("responder.done", session_id=session_id)

    return {
        "final_answer":       final_answer,
        "action_explanation": explanation,
        "messages": [{"role": "assistant", "content": final_answer}],
    }

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.state import GraphState
from src.prompts.registry import get_prompt
from src.utils.llm import get_llm, stream_llm, visible_chunk_text

log = structlog.get_logger(__name__)

_MAX_RESULT_CHARS = 2_000
_PROVIDER_UNAVAILABLE_ANSWER = (
    "The AI provider is temporarily unavailable, so KRAKEN cannot compose a "
    "grounded answer right now. No operational action was performed. Please retry shortly."
)


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


def _action_result_payload(action_result: Any) -> dict[str, Any] | None:
    if not isinstance(action_result, dict):
        return None
    nested = action_result.get("result")
    if isinstance(nested, dict):
        return nested
    return action_result


def _fallback_answer_from_action_result(action_result: Any) -> str:
    payload = _action_result_payload(action_result)
    if not payload:
        return ""

    if payload.get("action") == "get_ticket_status" or (
        payload.get("ticket_id") and payload.get("status")
    ):
        return (
            f"### Ticket Information: {payload.get('ticket_id')}\n\n"
            f"- **Subject:** {payload.get('subject') or payload.get('title', 'Untitled')}\n"
            f"- **Status:** `{payload.get('status', 'UNKNOWN')}`\n"
            f"- **Priority:** `{payload.get('priority', 'N/A')}`\n"
            f"- **Category:** {payload.get('category', 'General')}\n"
            f"- **User:** {payload.get('user_id') or payload.get('user', 'Unknown')}\n"
            f"- **Updated:** {payload.get('updated_at', 'Unknown')}\n"
            f"- **Description:** {payload.get('description', 'No description.')}"
        )

    if payload.get("message"):
        return str(payload["message"])

    if payload.get("response"):
        return str(payload["response"])

    return ""


def _action_receipt(
    selected_action: str | None, action_result: Any, approval_status: str | None
) -> str:
    """Describe only action outcomes established by structured state."""
    results = action_result if isinstance(action_result, list) else [action_result]
    lines: list[str] = []
    if approval_status == "approved":
        lines.append("Approval was granted for the critical action.")
    elif approval_status in {"reject", "rejected", "denied", "timeout"}:
        lines.append("The critical action was not approved. No critical action was performed.")
    elif approval_status == "failed":
        lines.append(
            "The approval request could not be completed. No critical action was performed."
        )
    else:
        lines.append("No human approval was required for the completed safe action.")

    for item in results:
        if not isinstance(item, dict):
            continue
        name = str(item.get("action_name") or selected_action or "Action")
        payload = _action_result_payload(item) or {}
        if item.get("cancelled"):
            lines.append(f"{name}: not executed ({item.get('reason') or 'approval denied'}).")
            continue
        if item.get("success") is False or payload.get("success") is False:
            lines.append(
                f"{name}: execution failed ({item.get('error') or payload.get('error') or 'unknown error'})."
            )
            continue
        if item.get("success") is not True and payload.get("success") is not True:
            lines.append(
                f"{name}: execution status is unverified; no successful mutation is claimed."
            )
            continue
        detail = payload.get("message") or payload.get("response")
        summary = f"{name}: completed successfully."
        if name == "create_ticket" and payload.get("ticket_id"):
            summary += f" Ticket ID: {payload['ticket_id']}."
        if detail:
            summary += f" {detail}"
        if payload.get("synthetic") is True:
            summary += " This changed Northstar demo records only."
        for key, label in (("transaction_id", "Transaction ID"), ("job_id", "Job ID")):
            if payload.get(key):
                summary += f" {label}: {payload[key]}."
        if payload.get("verification_status"):
            summary += f" Verification: {payload['verification_status']}."
        lines.append(summary)

    if len(lines) == 1:
        lines.append("No verified execution result is available.")
    return "\n\n".join(lines)


def _fallback_answer_from_retrieved_chunks(
    user_message: str,
    retrieved_chunks: Sequence[Mapping[str, Any]],
    threshold: float = 0.40,
) -> str:
    chunks = [
        chunk
        for chunk in retrieved_chunks
        if float(chunk.get("relevance_score", 0.0)) >= threshold
        and str(chunk.get("content", "")).strip()
    ]
    if not chunks:
        return ""

    msg_lower = user_message.lower()
    if not any(term in msg_lower for term in ("vpn", "sla", "critical", "vulnerability")):
        return ""

    chunks = sorted(chunks, key=lambda c: float(c.get("relevance_score", 0.0)), reverse=True)[:3]
    source_names = []
    content_blocks = []
    for chunk in chunks:
        source = str(chunk.get("source") or chunk.get("metadata", {}).get("source") or "knowledge")
        source_names.append(source)
        content = str(chunk.get("content", "")).strip()
        content_blocks.append(content[:900])

    title = "Grounded Knowledge Answer"
    if "vpn" in msg_lower:
        title = "Corporate VPN Guidance"
    elif "sla" in msg_lower or "vulnerability" in msg_lower:
        title = "Security SLA Guidance"

    return (
        f"### {title}\n\n"
        + "\n\n".join(content_blocks)
        + "\n\n**Sources:** "
        + ", ".join(dict.fromkeys(source_names))
    )


async def responder_node(state: GraphState) -> dict:
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
    retrieved_chunks = state.get("retrieved_chunks", [])

    if state.get("insufficient_knowledge") and selected_action in (None, "auto_respond"):
        final_answer = (
            "KRAKEN does not have enough permitted internal evidence to answer this request. "
            "No operational action was performed."
        )
        return {
            "final_answer": final_answer,
            "action_explanation": "Grounded refusal: insufficient permitted evidence.",
            "messages": [{"role": "assistant", "content": final_answer}],
        }

    early_answer = _fallback_answer_from_action_result(action_result) if selected_action else ""
    if selected_action not in (None, "auto_respond") and (
        action_result is not None or approval_status is not None
    ):
        early_answer = (
            f"{early_answer}\n\n" if selected_action == "get_ticket_status" and early_answer else ""
        ) + _action_receipt(selected_action, action_result, approval_status)
    if early_answer:
        explanation = f"Action '{selected_action}' was selected."
        if evidence:
            explanation += f" Evidence: {evidence}."
        log.info("responder.done", session_id=session_id)
        return {
            "final_answer": early_answer,
            "action_explanation": explanation,
            "messages": [{"role": "assistant", "content": early_answer}],
        }

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

    system_prompt_to_use = get_prompt("responder")

    try:
        llm = get_llm()
        messages = [
            SystemMessage(content=system_prompt_to_use),
            HumanMessage(content=human_content),
        ]
        answer_parts = []
        async for chunk in stream_llm(llm, messages):
            answer_parts.append(visible_chunk_text(chunk))
        final_answer = "".join(answer_parts).strip()
        if not final_answer:
            raise ValueError("LLM stream completed without visible answer text.")
    except Exception as exc:
        log.error("responder.llm_error", error=exc.__class__.__name__)
        fallback_answer = _fallback_answer_from_action_result(action_result)
        if fallback_answer:
            final_answer = fallback_answer
        else:
            grounded_answer = _fallback_answer_from_retrieved_chunks(user_message, retrieved_chunks)
            final_answer = grounded_answer or _PROVIDER_UNAVAILABLE_ANSWER

    if not final_answer or not final_answer.strip():
        fallback_answer = _fallback_answer_from_action_result(action_result)
        if fallback_answer:
            final_answer = fallback_answer
        else:
            final_answer = (
                "The agent completed the request but did not produce a user-facing response."
            )

    # Build action explanation (used in audit log)
    if selected_action:
        explanation = f"Action '{selected_action}' was selected."
    else:
        explanation = "No specific action was selected."
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

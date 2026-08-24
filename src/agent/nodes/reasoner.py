from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.state import GraphState
from src.prompts.registry import get_prompt
from src.utils.constants import TICKET_ID_REGEX
from src.utils.llm import get_llm, invoke_llm

log = structlog.get_logger(__name__)

_MAX_USER_MESSAGE_LEN = 4_000
_STATUS_QUERY_KEYWORDS: tuple[str, ...] = (
    "status of",
    "ticket status",
    "check status",
    "what is the status",
)


def _is_ticket_status_query(user_message: str) -> bool:
    msg_lower = user_message.lower()
    return any(keyword in msg_lower for keyword in _STATUS_QUERY_KEYWORDS) and bool(
        TICKET_ID_REGEX.search(user_message)
    )


def _format_chunks(
    chunks: Sequence[Mapping[str, Any]], threshold: float = 0.40, max_chars: int = 8000
) -> tuple[str, bool]:
    filtered_chunks = [c for c in chunks if c.get("relevance_score", 0.0) >= threshold]
    if not filtered_chunks:
        return "No high-relevance knowledge chunks were retrieved.", False

    # Prioritize authoritative knowledge base chunks (tickets, faq, sla) over past episodic memory
    auth_chunks = [c for c in filtered_chunks if c.get("source") != "episodic_memory"]
    epi_chunks = [c for c in filtered_chunks if c.get("source") == "episodic_memory"]
    sorted_chunks = auth_chunks + epi_chunks

    parts = []
    current_chars = 0
    for i, chunk in enumerate(sorted_chunks, 1):
        source = chunk.get("source", "unknown")
        content = chunk.get("content", "")
        score = chunk.get("relevance_score", 0.0)
        part = f"[{i}] Source: {source} (score: {score:.2f})\n{content}"

        if current_chars + len(part) > max_chars:
            log.info("reasoner.budget_exceeded", max_chars=max_chars, index=i)
            break

        parts.append(part)
        current_chars += len(part)

    return "\n\n---\n\n".join(parts), True


async def reasoner_node(state: GraphState) -> dict:
    """
    Reason over retrieved chunks to produce analysis for the decider.
    """
    session_id = state.get("session_id", "")
    log.info("reasoner.start", session_id=session_id)

    user_message = state.get("user_message", "")
    if len(user_message) > _MAX_USER_MESSAGE_LEN:
        log.warning(
            "reasoner.user_message_truncated", session_id=session_id, original_len=len(user_message)
        )
        user_message = user_message[:_MAX_USER_MESSAGE_LEN] + "\n... [Truncated for token budget]"

    if _is_ticket_status_query(user_message):
        ticket_id = TICKET_ID_REGEX.search(user_message)
        resolved_ticket_id = ticket_id.group(0).upper() if ticket_id else "the requested ticket"
        reasoning = (
            f"The user is asking for the current status of {resolved_ticket_id}. "
            "This is a read-only ticket lookup and does not require LLM reasoning."
        )
        log.info(
            "reasoner.ticket_status_fast_path",
            session_id=session_id,
            ticket_id=resolved_ticket_id,
        )
        return {"reasoning": reasoning, "insufficient_knowledge": False}

    retrieved_chunks = state.get("retrieved_chunks", [])
    # pyrefly: ignore [bad-argument-type]
    chunks_text, has_valid_chunks = _format_chunks(retrieved_chunks, threshold=0.40)

    operational_intent = any(
        term in user_message.lower()
        for term in (
            "create ticket",
            "open ticket",
            "close ticket",
            "escalate",
            "unlock",
            "quarantine",
        )
    )
    if not has_valid_chunks and not operational_intent:
        log.warning("reasoner.insufficient_knowledge", session_id=session_id)
        refusal_reasoning = (
            "RELEVANT INFORMATION:\n"
            "None. No internal documentation or ticket history met the minimum relevance threshold (0.40).\n\n"
            "GAPS OR CONFLICTS:\n"
            "Insufficient internal knowledge to safely answer or perform actions.\n\n"
            "CONCLUSION:\n"
            "Cannot answer or execute actions from external parametric memory alone. Please provide additional context."
        )
        return {"reasoning": refusal_reasoning, "insufficient_knowledge": True}

    human_content = f"User request: {user_message}\n\nRetrieved knowledge:\n{chunks_text}"

    try:
        llm = get_llm()
        response = await invoke_llm(
            llm,
            [
                SystemMessage(content=get_prompt("reasoner")),
                HumanMessage(content=human_content),
            ],
        )
        reasoning = response.content.strip()
        log.info("reasoner.done", session_id=session_id, chars=len(reasoning))
        return {"reasoning": reasoning, "insufficient_knowledge": not has_valid_chunks}

    except Exception as exc:
        log.error("reasoner.error", session_id=session_id, error=exc.__class__.__name__)
        fallback = (
            "Reasoning is unavailable because the AI provider could not complete the request. "
            f"Retrieved evidence count: {len(retrieved_chunks)}."
        )
        return {
            "reasoning": fallback,
            "error": "llm_provider_unavailable",
            "insufficient_knowledge": not has_valid_chunks,
        }

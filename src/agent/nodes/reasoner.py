from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.state import GraphState
from src.prompts.registry import get_prompt
from src.utils.llm import get_llm

log = structlog.get_logger(__name__)

_MAX_USER_MESSAGE_LEN = 4_000


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

    retrieved_chunks = state.get("retrieved_chunks", [])
    # pyrefly: ignore [bad-argument-type]
    chunks_text, has_valid_chunks = _format_chunks(retrieved_chunks, threshold=0.40)

    if not has_valid_chunks and retrieved_chunks:
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
        response = await llm.ainvoke(
            [
                SystemMessage(content=get_prompt("reasoner")),
                HumanMessage(content=human_content),
            ]
        )
        reasoning = response.content.strip()
        log.info("reasoner.done", session_id=session_id, chars=len(reasoning))
        return {"reasoning": reasoning, "insufficient_knowledge": not has_valid_chunks}

    except Exception as exc:
        log.error("reasoner.error", session_id=session_id, error=str(exc))
        fallback = (
            f"Reasoning unavailable due to LLM error: {exc}. "
            f"Retrieved {len(retrieved_chunks)} chunks."
        )
        return {
            "reasoning": fallback,
            "error": str(exc),
            "insufficient_knowledge": not has_valid_chunks,
        }

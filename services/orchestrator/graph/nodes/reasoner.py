"""
Reasoner Node — analyses retrieved chunks and produces structured reasoning.

Takes the user message + retrieved knowledge chunks and asks the LLM to:
  1. Identify which chunks are most relevant.
  2. Note any gaps or conflicts in the knowledge.
  3. Summarise what is known and what actions might be appropriate.

Output is stored in state["reasoning"] and fed into the decider.
This is the only node that "thinks" — the decider only decides.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from services.orchestrator.graph.state import GraphState
from services.orchestrator.llm import get_llm

log = structlog.get_logger(__name__)

_SYSTEM_PROMPT = """You are a security reasoning analyst for Xiarch, a cybersecurity consultancy.

You will receive a user's request and a set of retrieved knowledge chunks.
Your task is to analyse the chunks and produce clear, structured reasoning.

Structure your response as:
RELEVANT INFORMATION:
(bullet points of what the chunks tell you, citing specific SLA rules, policy lines, pentesting rules, or ticket status)

GAPS OR CONFLICTS:
(note anything missing or contradictory — write "None" if all is clear)

CONCLUSION:
(what you know, what action if any seems appropriate)

Be factual. Only use what is in the provided chunks. Do not invent information.
"""

_MAX_USER_MESSAGE_LEN = 4_000


def _format_chunks(chunks: list[dict], threshold: float = 0.45, max_chars: int = 8000) -> str:
    # Chunks are already sorted descending by score in retriever
    filtered_chunks = [c for c in chunks if c.get("relevance_score", 0.0) >= threshold]
    if not filtered_chunks:
        return "No high-relevance knowledge chunks were retrieved."

    parts = []
    current_chars = 0
    for i, chunk in enumerate(filtered_chunks, 1):
        source = chunk.get("source", "unknown")
        content = chunk.get("content", "")
        score = chunk.get("relevance_score", 0.0)
        part = f"[{i}] Source: {source} (score: {score:.2f})\n{content}"

        if current_chars + len(part) > max_chars:
            log.info("reasoner.budget_exceeded", max_chars=max_chars, index=i)
            break

        parts.append(part)
        current_chars += len(part)

    return "\n\n---\n\n".join(parts)


def reasoner_node(state: GraphState) -> dict:
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
    chunks_text = _format_chunks(retrieved_chunks)

    human_content = f"User request: {user_message}\n\n" f"Retrieved knowledge:\n{chunks_text}"

    try:
        llm = get_llm()
        response = llm.invoke(
            [
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=human_content),
            ]
        )
        reasoning = response.content.strip()
        log.info("reasoner.done", session_id=session_id, chars=len(reasoning))
        return {"reasoning": reasoning}

    except Exception as exc:
        log.error("reasoner.error", session_id=session_id, error=str(exc))
        fallback = (
            f"Reasoning unavailable due to LLM error: {exc}. "
            f"Retrieved {len(retrieved_chunks)} chunks."
        )
        return {"reasoning": fallback, "error": str(exc)}

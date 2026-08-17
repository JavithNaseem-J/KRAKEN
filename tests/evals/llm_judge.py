"""
LLM-as-a-Judge RAG Evaluator.

Uses ChatOpenAI (any OpenAI-compatible provider, default: Groq) with Pydantic
structured output to score RAG quality on three axes:
  - Faithfulness:      Does the answer stay within retrieved chunks?
  - Context Recall:    How many relevant facts were retrieved?
  - Answer Relevance:  Is the answer helpful and on-topic?

Zero extra dependencies — uses only langchain-openai + pydantic (core deps).
"""

from __future__ import annotations

import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field


class EvaluationResult(BaseModel):
    """Structured output from the LLM judge."""

    faithfulness: float = Field(
        ge=0.0, le=1.0,
        description="0.0-1.0: How well the answer stays within the retrieved chunks (no hallucination)",
    )
    context_recall: float = Field(
        ge=0.0, le=1.0,
        description="0.0-1.0: How many relevant facts from the chunks are reflected in the answer",
    )
    answer_relevance: float = Field(
        ge=0.0, le=1.0,
        description="0.0-1.0: How well the answer addresses the user query",
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of the scores",
    )


_JUDGE_SYSTEM_PROMPT = """\
You are a strict, factual RAG evaluation judge. You score retrieval-augmented \
generation outputs on three axes, each from 0.0 to 1.0:

- **faithfulness**: How well the answer stays within the provided context chunks. \
1.0 = every claim is grounded in the chunks. 0.0 = mostly hallucinated.
- **context_recall**: How many relevant facts from the chunks are reflected in the \
answer. 1.0 = all key facts used. 0.0 = key facts ignored.
- **answer_relevance**: How well the answer addresses the user query directly. \
1.0 = directly on-topic and helpful. 0.0 = off-topic or unhelpful.

Be strict. Do NOT inflate scores. Return ONLY valid JSON matching the schema."""

_JUDGE_USER_TEMPLATE = """\
<user_query>
{query}
</user_query>

<retrieved_chunks>
{chunks}
</retrieved_chunks>

<generated_answer>
{answer}
</generated_answer>

Score the answer on faithfulness, context_recall, and answer_relevance. \
Return valid JSON only."""


def _get_judge_llm() -> Any:
    """Return a ChatOpenAI instance pointing at the configured LLM provider."""
    base_url = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    api_key = os.getenv("LLM_API_KEY", "gsk_placeholder")
    model = os.getenv("LLM_JUDGE_MODEL", os.getenv("LLM_MODEL", "llama-3.3-70b-versatile"))

    return ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=0.0,
    ).with_structured_output(EvaluationResult)


def evaluate_rag_response(
    query: str,
    chunks: list[dict[str, Any]],
    answer: str,
) -> EvaluationResult:
    """
    Score a RAG response using the LLM judge.

    Args:
        query:   The user's original question.
        chunks:  List of retrieved chunk dicts (must have 'content' key).
        answer:  The generated answer text.

    Returns:
        EvaluationResult with faithfulness, context_recall, answer_relevance scores.
    """
    chunks_text = "\n\n".join(
        f"[Chunk {i+1}] {c.get('content', c.get('text', str(c)))}"
        for i, c in enumerate(chunks)
    ) or "(no chunks retrieved)"

    llm = _get_judge_llm()
    result = llm.invoke([
        SystemMessage(content=_JUDGE_SYSTEM_PROMPT),
        HumanMessage(content=_JUDGE_USER_TEMPLATE.format(
            query=query,
            chunks=chunks_text,
            answer=answer,
        )),
    ])
    return result

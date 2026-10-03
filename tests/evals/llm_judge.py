"""RAGAS scoring for answers with observed retrieval context."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from ragas.llms import llm_factory
from ragas.metrics.collections import ContextRecall, Faithfulness

from src.utils.config import get_settings


class EvaluationResult(BaseModel):
    faithfulness: float | None = Field(default=None, ge=0.0, le=1.0)
    context_recall: float | None = Field(default=None, ge=0.0, le=1.0)


def _get_ragas_llm() -> Any:
    settings = get_settings()
    if not settings.llm_api_key:
        raise ValueError("LLM_API_KEY is required for RAGAS evaluation")
    client = AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=60.0,
        max_retries=0,
    )
    return llm_factory(settings.llm_model, client=client)


def evaluate_rag_response(
    query: str,
    chunks: list[dict[str, Any]],
    answer: str,
    reference_facts: list[str] | None = None,
) -> EvaluationResult:
    """Score faithfulness and reference-fact context recall with RAGAS."""
    contexts = [
        content
        for chunk in chunks
        if isinstance(chunk, dict)
        if isinstance(content := chunk.get("content"), str) and content.strip()
    ]
    if not contexts:
        return EvaluationResult()
    llm = _get_ragas_llm()
    faithfulness = (
        Faithfulness(llm=llm)
        .score(user_input=query, response=answer, retrieved_contexts=contexts)
        .value
    )
    context_recall = (
        ContextRecall(llm=llm)
        .score(
            user_input=query,
            retrieved_contexts=contexts,
            reference=". ".join(reference_facts),
        )
        .value
        if reference_facts
        else None
    )
    return EvaluationResult(faithfulness=faithfulness, context_recall=context_recall)

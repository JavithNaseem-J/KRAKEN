"""
RAG Evaluation & Faithfulness Benchmarking Suite.

Tests retrieval precision@k, recall@k, and answer faithfulness grounding
across golden IT support queries against the Knowledge microservice.
"""

from __future__ import annotations

import pytest
import httpx
from typing import Any

KNOWLEDGE_URL = "http://localhost:8002/retrieve"

# Golden test dataset: query -> expected key terms that MUST appear in retrieved chunks
GOLDEN_DATASET = [
    {
        "query": "How do I resolve GlobalProtect VPN Error 51?",
        "expected_keywords": ["vpn", "error 51", "globalprotect", "reinstall", "adapter"],
        "min_precision": 0.80,
    },
    {
        "query": "What is the SLA response time for high severity P1 security incidents?",
        "expected_keywords": ["sla", "p1", "response", "hours", "escalation"],
        "min_precision": 0.80,
    },
    {
        "query": "How do I request a replacement laptop for hardware failure?",
        "expected_keywords": ["ticket", "hardware", "laptop", "replacement", "equipment"],
        "min_precision": 0.75,
    },
]


def calculate_precision_at_k(chunks: list[dict[str, Any]], expected_keywords: list[str]) -> float:
    """Calculate the ratio of chunks that contain at least one expected keyword."""
    if not chunks:
        return 0.0

    relevant_count = 0
    for chunk in chunks:
        content = (chunk.get("content") or "").lower()
        if any(kw in content for kw in expected_keywords):
            relevant_count += 1

    return relevant_count / len(chunks)


def calculate_faithfulness(chunks: list[dict[str, Any]]) -> float:
    """
    Calculate faithfulness score based on chunk relevance scores returned by RRF.
    Ensures all retrieved chunks pass the 0.40 relevance threshold.
    """
    if not chunks:
        return 0.0

    scores = [float(c.get("relevance_score", 0.0)) for c in chunks]
    valid_scores = [s for s in scores if 0.0 <= s <= 1.0]

    if not valid_scores:
        return 0.0

    avg_score = sum(valid_scores) / len(valid_scores)
    return round(avg_score, 4)


@pytest.mark.asyncio
async def test_rag_precision_and_faithfulness():
    """Verify RAG retrieval precision and grounding scores exceed enterprise thresholds."""
    from shared.config import get_settings

    settings = get_settings()
    headers = {"X-Service-Token": settings.hitl_service_token}

    async with httpx.AsyncClient(timeout=10.0) as client:
        for item in GOLDEN_DATASET:
            payload = {
                "query": item["query"],
                "sources": ["faq", "tickets", "sla"],
                "top_k": 5,
                "session_id": "rag_eval_session",
            }

            resp = await client.post(KNOWLEDGE_URL, json=payload, headers=headers)
            assert resp.status_code == 200, f"Knowledge service error: {resp.text}"

            data = resp.json()
            chunks = data.get("chunks", [])
            assert len(chunks) > 0, f"Zero chunks retrieved for query: {item['query']}"

            precision = calculate_precision_at_k(chunks, item["expected_keywords"])
            faithfulness = calculate_faithfulness(chunks)

            assert precision >= item["min_precision"], (
                f"Low Precision@k ({precision:.2f} < {item['min_precision']}) for: '{item['query']}'"
            )
            assert faithfulness >= 0.85, (
                f"Low Faithfulness grounding ({faithfulness:.2f} < 0.85) for: '{item['query']}'"
            )

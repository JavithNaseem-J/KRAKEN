from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from src.agent.state import GraphState
from src.api.orchestrator import _build_response
from src.utils.models.action import ActionRequest
from src.utils.models.agent import QueryResponse
from src.utils.models.audit import AuditLogRequest


def test_public_models_reject_reasoning_fields() -> None:
    with pytest.raises(ValidationError):
        QueryResponse(session_id="session", answer="safe", reasoning="private")
    with pytest.raises(ValidationError):
        ActionRequest(
            action_name="auto_respond",
            payload={},
            session_id="session",
            user_id="user",
            reasoning="private",
        )
    with pytest.raises(ValidationError):
        AuditLogRequest(
            session_id="session",
            user_id="user",
            action_type="READ",
            action_name="auto_respond",
            risk_level="SAFE",
            hitl_required=False,
            status="success",
            reasoning="private",
        )


def test_response_builder_never_uses_reasoning_as_answer() -> None:
    response = _build_response(
        "session",
        {
            "reasoning": "private model analysis",
            "final_answer": "Safe answer",
            "action_result": {
                "result": "complete",
                "nested": {"reasoning": "private nested analysis"},
            },
            "retrieved_chunks": [
                {
                    "source": "faq",
                    "content": "grounded content",
                    "relevance_score": 1.0,
                    "metadata": {"reasoning": "private retrieval analysis"},
                }
            ],
        },
    )

    payload = response.model_dump(mode="json")
    assert "reasoning" not in str(payload).lower()
    assert "private model analysis" not in response.answer
    assert payload["action_result"]["result"] == "complete"


def test_nested_reasoning_is_removed_from_service_contracts() -> None:
    action = ActionRequest(
        action_name="auto_respond",
        payload={"result": "safe", "nested": {"reasoning": "private"}},
        session_id="session",
        user_id="user",
    )
    audit = AuditLogRequest(
        session_id="session",
        user_id="user",
        action_type="READ",
        action_name="auto_respond",
        risk_level="SAFE",
        hitl_required=False,
        status="success",
        payload={"nested": {"reasoning": "private"}},
        result={"reasoning": "private", "status": "safe"},
    )

    assert "reasoning" not in str(action.model_dump(mode="json")).lower()
    assert "reasoning" not in str(audit.model_dump(mode="json")).lower()


@pytest.mark.asyncio
async def test_reasoning_is_not_checkpointed() -> None:
    builder = StateGraph(GraphState)
    builder.add_node("reason", lambda _: {"reasoning": "private model analysis"})
    builder.add_edge(START, "reason")
    builder.add_edge("reason", END)
    graph = builder.compile(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "reasoning-boundary"}}

    await graph.ainvoke(
        {"session_id": "session", "user_message": "question", "messages": []},
        config,
    )
    snapshot = await graph.aget_state(config)

    assert "reasoning" not in snapshot.values

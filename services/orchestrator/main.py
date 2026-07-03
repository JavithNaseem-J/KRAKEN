"""
Orchestrator Service — hosts the LangGraph agent and manages the request lifecycle.

Two critical endpoints:
  POST /run
      Starts a new agent run. Returns either:
        a) final QueryResponse if the run completed (SAFE action or respond_only)
        b) {"status": "pending_approval", "approval_id": "..."} if HITL fired

  POST /approval-callback
      Called by the approval service after human decision.
      Resumes the paused graph with Command(resume={"decision": "approve"|"reject"}).
      Returns the final QueryResponse.

State management:
  LangGraph MemorySaver stores graph state keyed by thread_id (= session_id).
  A pending approvals dict maps approval_id → session_id for the callback.
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import structlog
from fastapi import FastAPI, HTTPException
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from shared.config import get_settings
from shared.models.agent import QueryRequest, QueryResponse
from .graph.agent_graph import build_graph

log = structlog.get_logger(__name__)
settings = get_settings()

# approval_id → session_id (populated when graph pauses for HITL)
_pending_approvals: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("orchestrator.startup", model=settings.llm_model)
    app.state.agent_graph = build_graph()
    log.info("orchestrator.graph_ready")
    yield
    log.info("orchestrator.shutdown")


app = FastAPI(
    title="AKEA Orchestrator",
    description="LangGraph Agent Orchestrator — Autonomous Knowledge Execution Agent",
    version="0.3.0",
    lifespan=lifespan,
)


def _graph_config(session_id: str) -> dict:
    """LangGraph thread config — all state for a session lives under this key."""
    return {"configurable": {"thread_id": session_id}}


@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "orchestrator"}


@app.post("/run", tags=["agent"])
async def run(body: QueryRequest) -> Any:
    """
    Execute the agent graph for a user query.
    Returns QueryResponse on completion, or pending_approval dict on HITL pause.
    """
    log.info("orchestrator.run", session_id=body.session_id, user_id=body.user_id)

    graph = app.state.agent_graph
    config = _graph_config(body.session_id)

    initial_state = {
        "session_id":   body.session_id,
        "user_id":      body.user_id,
        "user_message": body.message,
        "messages":     [],
    }

    try:
        result = graph.invoke(initial_state, config)
    except Exception as exc:
        log.error("orchestrator.run_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # ── Check if graph paused for HITL ────────────────────────────────────────
    snapshot = graph.get_state(config)
    if snapshot.next:
        # Graph is interrupted — extract approval_id from interrupt value
        interrupt_val: dict = {}
        for task in snapshot.tasks:
            for interrupt in getattr(task, "interrupts", []):
                interrupt_val = interrupt.value
                break

        approval_id = interrupt_val.get("approval_id", str(uuid.uuid4()))
        _pending_approvals[approval_id] = body.session_id

        log.info(
            "orchestrator.hitl_paused",
            session_id=body.session_id,
            approval_id=approval_id,
        )
        return {
            "status":      "pending_approval",
            "approval_id": approval_id,
            "session_id":  body.session_id,
            "message":     "A WRITE action requires human approval. Check the approval service.",
        }

    # ── Graph completed — build response ──────────────────────────────────────
    return _build_response(body.session_id, result)


@app.post("/approval-callback", tags=["hitl"])
async def approval_callback(payload: dict) -> Any:
    """
    Resume a paused graph after human approves or rejects a WRITE action.
    Called by the approval service.
    """
    approval_id = payload.get("approval_id", "")
    decision    = payload.get("decision", "reject")

    session_id = _pending_approvals.pop(approval_id, None)
    if not session_id:
        log.warning("orchestrator.callback_unknown", approval_id=approval_id)
        raise HTTPException(status_code=404, detail="Approval ID not found or already processed.")

    log.info(
        "orchestrator.resuming",
        session_id=session_id,
        approval_id=approval_id,
        decision=decision,
    )

    graph = app.state.agent_graph
    config = _graph_config(session_id)

    try:
        result = graph.invoke(
            Command(resume={"decision": decision}),
            config,
        )
    except Exception as exc:
        log.error("orchestrator.resume_error", error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _build_response(session_id, result)


def _build_response(session_id: str, state: dict) -> QueryResponse:
    """Convert final graph state into a QueryResponse."""
    action_result = state.get("action_result")
    return QueryResponse(
        session_id=session_id,
        answer=state.get("final_answer", "No answer generated."),
        reasoning=state.get("reasoning", ""),
        action_taken=state.get("selected_action"),
        action_result=action_result,
        sources=[
            c.get("metadata", {}).get("source", "unknown")
            for c in state.get("retrieved_chunks", [])[:3]
        ],
    )

"""
KRAKEN Enterprise Typed Microservice Client SDK.

Provides typed, resilient client interfaces for all KRAKEN subsystems
(Approval, Action, Knowledge, Memory, Audit, Orchestrator) with automatic
tracing, authentication header propagation, and dual-mode transport
(In-process ASGI short-circuiting + remote Kubernetes HTTP).
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from pydantic import BaseModel, Field

from src.utils.config import get_settings
from src.utils.http_client import internal_request, service_headers

log = structlog.get_logger(__name__)


# ── Typed DTO Models ──────────────────────────────────────────────────────────
class ApprovalRegistrationResponse(BaseModel):
    approval_id: str
    url: str


class ApprovalDetailsResponse(BaseModel):
    approval_id: str
    action_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""
    session_id: str = ""
    status: str = "PENDING"
    created_at: str | None = None
    csrf_token: str = ""


class ActionExecutionResponse(BaseModel):
    success: bool
    action: str | None = None
    result: dict[str, Any] | None = None
    receipt: dict[str, Any] | None = None
    verification_status: str | None = None
    error: str | None = None


class KnowledgeQueryResponse(BaseModel):
    query: str
    chunks: list[dict[str, Any]] = Field(default_factory=list)
    total: int = 0


# ── Subsystem Client Interfaces ───────────────────────────────────────────────
class ApprovalServiceClient:
    """Typed client for the HITL Approval Service."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or get_settings().approval_url).rstrip("/")

    async def create_pending(
        self,
        action_name: str,
        payload: dict[str, Any],
        reasoning: str,
        session_id: str,
        client: httpx.AsyncClient | None = None,
    ) -> ApprovalRegistrationResponse:
        """Register a pending approval request."""
        url = f"{self._base_url}/pending"
        resp = await internal_request(
            "POST",
            url,
            json_payload={
                "action_name": action_name,
                "payload": payload,
                "reasoning": reasoning,
                "session_id": session_id,
            },
            headers=service_headers(trace_id=session_id),
            client=client,
        )
        data = resp.json()
        return ApprovalRegistrationResponse(
            approval_id=data["approval_id"],
            url=data.get("url", ""),
        )

    async def get_details(
        self, approval_id: str, client: httpx.AsyncClient | None = None
    ) -> ApprovalDetailsResponse:
        """Fetch details and CSRF token for a pending approval."""
        url = f"{self._base_url}/approve/{approval_id}/details"
        resp = await internal_request(
            "GET", url, headers=service_headers(), client=client
        )
        return ApprovalDetailsResponse(**resp.json())

    async def submit_decision(
        self,
        approval_id: str,
        decision: str,
        csrf_token: str,
        approver_role: str | None = None,
        approver_id: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """Submit approval or rejection with Four-Eyes approver attribution."""
        url = f"{self._base_url}/approve/{approval_id}/decision"
        form_data = {
            "decision": decision,
            "csrf_token": csrf_token,
            "approver_role": approver_role or "admin",
            "approver_id": approver_id or "system",
        }
        resp = await internal_request(
            "POST", url, data=form_data, headers=service_headers(), client=client
        )
        try:
            return resp.json()
        except Exception:
            return {"status": "ok", "decision": decision}


class ActionServiceClient:
    """Typed client for the Action Execution Service."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or get_settings().action_url).rstrip("/")

    async def execute_action(
        self,
        action_name: str,
        payload: dict[str, Any],
        session_id: str = "",
        user_id: str = "system",
        reasoning: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> ActionExecutionResponse:
        """Execute registered action handler with verified transaction receipts."""
        url = f"{self._base_url}/execute"
        resp = await internal_request(
            "POST",
            url,
            json_payload={
                "action_name": action_name,
                "payload": payload,
                "session_id": session_id,
                "user_id": user_id,
                "reasoning": reasoning,
            },
            headers=service_headers(trace_id=session_id),
            client=client,
        )
        data = resp.json()
        result_inner = data.get("result") or {} if isinstance(data.get("result"), dict) else {}
        action_val = data.get("action") or result_inner.get("action") or action_name
        is_success = data.get("status") == "success" or data.get("success") is True or result_inner.get("success") is True
        return ActionExecutionResponse(
            success=is_success,
            action=action_val,
            result=data.get("result"),
            receipt=data.get("receipt") or result_inner.get("receipt"),
            verification_status=data.get("verification_status") or result_inner.get("verification_status"),
            error=data.get("error"),
        )


class KnowledgeServiceClient:
    """Typed client for the Semantic Knowledge Base & RAG Service."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or get_settings().knowledge_url).rstrip("/")

    async def query_knowledge(
        self,
        query: str,
        sources: list[str] | None = None,
        top_k: int = 5,
        session_id: str = "",
        user_role: str = "end_user",
        client: httpx.AsyncClient | None = None,
    ) -> KnowledgeQueryResponse:
        """Query semantic knowledge chunks with least-privilege role masking."""
        url = f"{self._base_url}/query"
        resp = await internal_request(
            "POST",
            url,
            json_payload={
                "query": query,
                "sources": sources or ["faq", "tickets", "sla"],
                "top_k": top_k,
                "session_id": session_id,
                "user_role": user_role,
            },
            headers=service_headers(trace_id=session_id),
            client=client,
        )
        data = resp.json()
        return KnowledgeQueryResponse(
            query=data.get("query", query),
            chunks=data.get("chunks", []),
            total=len(data.get("chunks", [])),
        )


# ── Unified Top-Level KRAKEN SDK ──────────────────────────────────────────────
class KrakenClient:
    """Unified Enterprise SDK client entry point."""

    def __init__(self) -> None:
        self.approval = ApprovalServiceClient()
        self.action = ActionServiceClient()
        self.knowledge = KnowledgeServiceClient()


# Singleton SDK instance
kraken_sdk = KrakenClient()

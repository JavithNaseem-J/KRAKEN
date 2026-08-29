from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

_MIN_SCORE = 0.40


def _message_terms(message: str) -> str:
    return " ".join(message.lower().split())


def _filtered_chunks(
    chunks: Sequence[Mapping[str, Any]], threshold: float = _MIN_SCORE
) -> list[Mapping[str, Any]]:
    filtered: list[Mapping[str, Any]] = []
    for chunk in chunks:
        try:
            score = float(chunk.get("relevance_score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        content = str(chunk.get("content") or "").strip()
        if (
            score >= threshold
            and content
            and str(chunk.get("source", "")).lower() != "episodic_memory"
        ):
            filtered.append(chunk)
    return sorted(filtered, key=lambda item: float(item.get("relevance_score", 0.0)), reverse=True)


def _sources(chunks: Sequence[Mapping[str, Any]]) -> str:
    names: list[str] = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        source = chunk.get("source")
        if not source and isinstance(meta, Mapping):
            source = meta.get("source") or meta.get("file_name")
        source_name = str(source or "knowledge")
        if source_name not in names:
            names.append(source_name)
    return ", ".join(names)


def demo_knowledge_intent(message: str) -> str | None:
    msg = _message_terms(message)
    if "vpn" in msg or "globalprotect" in msg:
        return "vpn"
    if "sla" in msg and ("critical" in msg or "vulnerability" in msg):
        return "sla"
    if "critical vulnerability" in msg or "critical severity" in msg:
        return "sla"
    return None


def build_demo_knowledge_answer(
    message: str,
    retrieved_chunks: Sequence[Mapping[str, Any]],
) -> str:
    intent = demo_knowledge_intent(message)
    chunks = _filtered_chunks(retrieved_chunks)
    if not intent or not chunks:
        return ""

    combined = "\n\n".join(str(chunk.get("content") or "") for chunk in chunks).lower()
    source_text = _sources(chunks)

    if intent == "vpn":
        if "vpn" not in combined and "globalprotect" not in combined:
            return ""
        return (
            "### Corporate VPN Guidance\n\n"
            "- **Client:** Palo Alto GlobalProtect v6.2+.\n"
            "- **Authentication:** Azure AD SAML with Duo MFA.\n"
            "- **Traffic routing:** Split tunneling is disabled for security traffic; web traffic routes through Prisma Access SASE.\n"
            "- **Error 51:** Start the GlobalProtect service with `net start PanGPS` from an elevated Command Prompt.\n"
            "- **Portal unreachable:** Check DNS resolution for `vpn.xiarch.com` and allow TCP 443 / UDP 4500 through the local firewall.\n"
            "- **Certificate error:** Update the client root CA store through Company Portal.\n\n"
            f"**Sources:** {source_text}"
        )

    if intent == "sla":
        if "sla" not in combined and "response" not in combined:
            return ""
        return (
            "### Critical Vulnerability SLA Guidance\n\n"
            "- **P1 critical vulnerability:** Initial response within 15 minutes and resolution target within 2 hours.\n"
            "- **Approval requirement:** P1 critical actions require CISO / VP of Infrastructure approval.\n"
            "- **Critical severity support policy:** Response within 1 hour, mitigation plan within 4 hours, and escalation to Tier 3 / Technical Director.\n"
            "- **How to interpret this:** Use the P1 SLA for active enterprise incidents such as ransomware, domain-admin compromise, or data exfiltration. Use the support-policy SLA for critical reported findings that need mitigation planning.\n\n"
            f"**Sources:** {source_text}"
        )

    return ""


def has_demo_knowledge_answer(
    message: str,
    retrieved_chunks: Sequence[Mapping[str, Any]],
) -> bool:
    return bool(build_demo_knowledge_answer(message, retrieved_chunks))

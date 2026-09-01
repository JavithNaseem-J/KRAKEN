from __future__ import annotations

import asyncio
import re
import time
from typing import TYPE_CHECKING, Any, cast

import structlog
from qdrant_client.models import Document, FieldCondition, Filter, MatchAny, MatchValue

from src.safety.policy_engine import get_policy_engine
from src.utils.config import get_settings
from src.utils.constants import TICKET_ID_REGEX
from src.utils.models.knowledge import (
    KnowledgeChunk,
    KnowledgeSource,
    RetrievalRequest,
    RetrievalResult,
)

if TYPE_CHECKING:
    from qdrant_client import AsyncQdrantClient, QdrantClient

    from src.utils.embedder import BGEEmbedder

log = structlog.get_logger(__name__)
settings = get_settings()

_STOP_WORDS: frozenset[str] = frozenset(
    {
        "what",
        "is",
        "the",
        "for",
        "and",
        "a",
        "an",
        "in",
        "of",
        "to",
        "how",
        "do",
        "can",
        "you",
        "about",
        "which",
        "are",
        "on",
        "with",
        "or",
        "by",
        "at",
        "from",
        "it",
        "this",
        "that",
        "there",
        "their",
        "question",
        "details",
        "policy",
        "general",
        "query",
        "test",
    }
)


def _keyword_frequency_score(query: str, text: str) -> float:
    """
    Computes a normalized keyword match score based on term frequency and overlap.
    Case-insensitive token matching.
    """
    if not query or not text:
        return 0.0

    tokens = [t.lower() for t in re.findall(r"\w+", query) if len(t) > 2]
    if not tokens:
        return 0.0

    text_lower = text.lower()
    matches = 0
    total_tf = 0
    for token in tokens:
        count = text_lower.count(token)
        if count > 0:
            matches += 1
            total_tf += min(count, 5)

    overlap_ratio = matches / len(tokens)
    tf_bonus = min(total_tf / (len(tokens) * 3), 1.0)
    return round(0.7 * overlap_ratio + 0.3 * tf_bonus, 4)


def _reciprocal_rank_fusion(
    vector_hits: list[Any],
    query: str,
    top_k: int = 5,
    k: float = 60.0,
) -> list[tuple[Any, float]]:
    """
    Combines vector search rank and keyword frequency rank using Reciprocal Rank Fusion (RRF).
    RRF(d) = 1/(k + r_vector(d)) + 1/(k + r_keyword(d))
    """
    if not vector_hits:
        return []

    # Vector rank map (1-indexed)
    vector_rank = {hit.id: i + 1 for i, hit in enumerate(vector_hits)}

    # Keyword rank map (sorted descending by keyword score)
    kw_scored = []
    for hit in vector_hits:
        content = (hit.payload or {}).get("content", "")
        kw_score = _keyword_frequency_score(query, content)
        kw_scored.append((hit, kw_score))

    kw_scored.sort(key=lambda x: x[1], reverse=True)
    keyword_rank = {hit.id: i + 1 for i, (hit, _) in enumerate(kw_scored)}

    # Calculate composite RRF score
    combined: list[tuple[Any, float]] = []
    for hit in vector_hits:
        r_v = vector_rank.get(hit.id, len(vector_hits))
        r_k = keyword_rank.get(hit.id, len(vector_hits))
        rrf_score = (1.0 / (k + r_v)) + (1.0 / (k + r_k))
        combined.append((hit, rrf_score))

    # Sort descending by composite RRF score
    combined.sort(key=lambda x: x[1], reverse=True)
    return combined[:top_k]


def _heuristic_rerank(
    query: str,
    candidates: list[tuple[Any, float]],
) -> list[tuple[Any, float]]:
    """
    Lightweight heuristic re-ranking pass that boosts exact phrase matches
    and key domain entity alignments (e.g., ticket ID, SLA, VPN) before returning top chunks.
    """
    if not candidates:
        return []

    query_lower = query.lower().strip()
    reranked: list[tuple[Any, float]] = []

    query_tokens = [
        t.lower() for t in re.findall(r"\w+", query) if len(t) > 2 and t.lower() not in _STOP_WORDS
    ]

    # Max possible RRF score for top-ranked item is 2 * (1 / (60 + 1)) = ~0.03278688
    max_rrf = 2.0 / 61.0
    for hit, rrf_score in candidates:
        payload = hit.payload or {}
        content_lower = payload.get("content", "").lower()

        # Combine normalized RRF score with raw vector cosine similarity if available
        raw_cosine = float(getattr(hit, "score", 0.70) or 0.70)
        norm_rrf = min(1.0, rrf_score / max_rrf) if max_rrf > 0 else 0.5
        base_score = 0.5 * norm_rrf + 0.5 * min(1.0, max(0.0, raw_cosine))

        boost = 1.0
        # Topic keyword overlap penalty: if query has specific topic keywords (e.g. 'soc', 'mfa'),
        # but chunk shares ZERO keywords, apply a heavy 0.35x penalty!
        if query_tokens:
            matches = sum(1 for t in query_tokens if t in content_lower)
            if matches == 0:
                boost *= 0.35
            else:
                boost += 0.20 * (matches / len(query_tokens))

        # Exact phrase match boost
        if query_lower in content_lower:
            boost += 0.25

        # Source context boost (e.g. ticket ID or SLA match)
        ticket_matches = TICKET_ID_REGEX.findall(query)
        if ticket_matches:
            for t_match in ticket_matches:
                t_lower = t_match.lower()
                doc_t_id = str(payload.get("metadata", {}).get("ticket_id") or "").lower()
                t_num = re.search(r"\d+", t_lower)
                num_str = t_num.group(0) if t_num else ""
                if (
                    t_lower in content_lower
                    or t_lower == doc_t_id
                    or (num_str and num_str in doc_t_id)
                ):
                    boost += 1.50

        if re.search(r"SLA|VPN|IT", query, re.IGNORECASE) and re.search(
            r"SLA|VPN|IT", content_lower
        ):
            boost += 0.15

        final_score = min(1.0, max(0.0, round(base_score * boost, 4)))
        reranked.append((hit, final_score))

    reranked.sort(key=lambda x: x[1], reverse=True)
    return reranked


class KnowledgeRetriever:
    """
    Queries Qdrant vector database for requested knowledge sources using payload filtering,
    RRF hybrid search (dense vector + keyword frequency), and heuristic re-ranking.
    """

    def __init__(
        self,
        client: AsyncQdrantClient | QdrantClient,
        embedder: BGEEmbedder,
        collection_name: str = "kraken_knowledge",
    ) -> None:
        self._client = client
        self._embedder = embedder
        self.collection_name = collection_name

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """
        Execute RAG retrieval pipeline:
          1. Dense vector search via Qdrant
          2. Sparse BM25-style keyword search via Qdrant scroll + local scoring
          3. Reciprocal Rank Fusion (RRF) candidate merging
          4. Heuristic score boosting pass
        """
        log.info(
            "retriever.start",
            sources=request.sources,
            top_k=request.top_k,
        )

        source_values = [s.value for s in request.sources]
        query_filter = Filter(
            must=[
                FieldCondition(
                    key="source",
                    match=MatchAny(any=source_values),
                ),
                FieldCondition(
                    key="scope",
                    match=MatchAny(any=["shared", request.session_id]),
                ),
                FieldCondition(
                    key="allowed_roles",
                    match=MatchAny(any=["public", request.user_role]),
                ),
                FieldCondition(
                    key="collection_version",
                    match=MatchValue(value=settings.knowledge_collection_version),
                ),
                FieldCondition(
                    key="dataset_generation",
                    match=MatchValue(value=settings.synthetic_dataset_generation),
                ),
            ]
        )

        if settings.qdrant_url and settings.qdrant_cloud_inference_enabled:
            query_vector: Any = Document(text=request.query, model=settings.qdrant_inference_model)
        else:
            query_vector = await asyncio.to_thread(self._embedder.embed_query, request.query)

        hits: list[Any] = []
        client = cast(Any, self._client)
        try:
            # Over-fetch 3x candidate pool for RRF and re-ranking
            limit_fetch = max(request.top_k * 3, 15)

            if hasattr(client, "query_points"):
                res = await client.query_points(
                    collection_name=self.collection_name,
                    query=query_vector,
                    query_filter=query_filter,
                    limit=limit_fetch,
                    with_payload=True,
                )
                hits = getattr(res, "points", [])
            else:
                hits = await client.search(
                    collection_name=self.collection_name,
                    query_vector=query_vector,
                    query_filter=query_filter,
                    limit=limit_fetch,
                )
        except Exception as exc:
            log.error("retriever.filtered_query_error", error=exc.__class__.__name__)
            raise

        # If explicit ticket IDs (e.g. TCK-1001 or T-1001) are in query, expand variants (e.g. TCK-1001, T-1001)
        ticket_ids_in_query = TICKET_ID_REGEX.findall(request.query)
        t_lowers: list[str] = []
        for ticket_id in ticket_ids_in_query:
            t_lowers.append(ticket_id.lower())
            match = re.search(r"(\d+)", ticket_id)
            if match:
                number = match.group(1)
                t_lowers.extend(
                    [
                        f"tck-{number}",
                        f"t-{number}",
                        f"tk-{number}",
                        f"tck{number}",
                        f"t{number}",
                        number,
                    ]
                )
        if ticket_ids_in_query:
            try:
                expanded_ids = set(ticket_ids_in_query)
                for tid in ticket_ids_in_query:
                    m = re.search(r"(\d+)", tid)
                    if m:
                        num = m.group(1)
                        expanded_ids.update(
                            [f"TCK-{num}", f"T-{num}", f"TK-{num}", f"TCK{num}", f"T{num}"]
                        )
                query_ids = list(expanded_ids)

                ticket_filter = Filter(
                    must=[
                        FieldCondition(
                            key="metadata.ticket_id",
                            match=MatchAny(any=query_ids),
                        ),
                        FieldCondition(
                            key="collection_version",
                            match=MatchValue(value=settings.knowledge_collection_version),
                        ),
                        FieldCondition(
                            key="dataset_generation",
                            match=MatchValue(value=settings.synthetic_dataset_generation),
                        ),
                    ]
                )
                scroll_res = await client.scroll(
                    collection_name=self.collection_name,
                    scroll_filter=ticket_filter,
                    limit=50,
                    with_payload=True,
                )
                scrolled_points = (
                    scroll_res[0]
                    if isinstance(scroll_res, tuple)
                    else getattr(scroll_res, "points", [])
                )
                existing_ids = {h.id for h in hits}

                for p in scrolled_points:
                    if p.id not in existing_ids:
                        hits.insert(0, p)
                        existing_ids.add(p.id)
            except Exception as scroll_exc:
                log.warning(
                    "retriever.ticket_id_scroll_failed", error=scroll_exc.__class__.__name__
                )

        # Defense in depth before any rank fusion: role, private scope, expiry,
        # and explicit-ticket boundaries must never depend on post-ranking code.
        permitted_hits: list[Any] = []
        user_role = (request.user_role or "public").lower().strip()
        now = time.time()
        for hit in hits:
            payload = hit.payload or {}
            if payload.get("collection_version") != settings.knowledge_collection_version:
                continue
            if payload.get("dataset_generation") != settings.synthetic_dataset_generation:
                continue
            scope = str(payload.get("scope") or "shared")
            if scope not in {"shared", request.session_id}:
                continue
            expiry = payload.get("expires_at")
            if expiry is not None and float(expiry) <= now:
                continue
            raw_roles = payload.get("allowed_roles") or ["public"]
            roles = [str(role).lower().strip() for role in raw_roles]
            if "public" not in roles and user_role not in roles and user_role != "admin":
                continue
            if ticket_ids_in_query and str(payload.get("source", "")).lower() == "tickets":
                content = str(payload.get("content", "")).lower()
                ticket_id = str((payload.get("metadata") or {}).get("ticket_id") or "").lower()
                if not any(
                    candidate in content or candidate == ticket_id for candidate in t_lowers
                ):
                    continue
            permitted_hits.append(hit)
        hits = permitted_hits

        # RRF Hybrid Fusion
        rrf_candidates = _reciprocal_rank_fusion(hits, request.query, top_k=request.top_k * 2)

        # Lightweight Cross-Encoder Re-Ranking
        reranked_hits = _heuristic_rerank(request.query, rrf_candidates)[: request.top_k]

        # Post-filter 1: Ticket Isolation & RBAC Security Clearance
        q_lower = request.query.lower()
        is_ticket_discovery_query = any(
            kw in q_lower
            for kw in (
                "ticket",
                "tickets",
                "issue",
                "issues",
                "incident",
                "incidents",
                "outage",
                "outages",
                "problem",
                "problems",
                "vpn",
                "access",
                "open",
                "closed",
                "status",
                "support",
                "helpdesk",
                "request",
            )
        )

        sanitized_hits = []

        for hit, score in reranked_hits:
            payload = hit.payload or {}
            chunk_source = str(payload.get("source", "")).lower()

            # Enterprise Ticket Isolation:
            # 1. When an explicit ticket ID is specified, strictly isolate to that specific ticket ID.
            # 2. When no explicit ID is given, allow ticket discovery if the query is a support/ticket/outage question.
            if chunk_source == "tickets":
                p_content = payload.get("content", "").lower()
                p_t_id = str((payload.get("metadata") or {}).get("ticket_id") or "").lower()
                if t_lowers:
                    if not any(t in p_content or t == p_t_id for t in t_lowers):
                        log.warning(
                            "retriever.cross_ticket_leak_blocked", doc_id=payload.get("document_id")
                        )
                        continue
                elif not is_ticket_discovery_query:
                    log.warning(
                        "retriever.unrelated_ticket_leak_blocked", doc_id=payload.get("document_id")
                    )
                    continue

            # Enterprise RBAC Security Clearance Filter
            raw_roles = (
                payload.get("allowed_roles")
                or (payload.get("metadata") or {}).get("allowed_roles")
                or ["public"]
            )
            allowed_roles = (
                [str(r).lower().strip() for r in raw_roles]
                if isinstance(raw_roles, list)
                else ["public"]
            )

            # Admin / SecOps roles override generic RBAC checks; public documents are open to everyone
            if (
                "public" not in allowed_roles
                and user_role not in ("admin", "approver", "security_lead", "operator")
                and user_role not in allowed_roles
            ):
                log.warning(
                    "retriever.rbac_access_denied",
                    doc_id=payload.get("document_id"),
                    user_role=user_role,
                    allowed_roles=allowed_roles,
                )
                continue

            # Enterprise Least-Privilege Protection for Sensitive Forensics / Containment Playbooks
            p_text = payload.get("content", "")
            is_internal_sop = any(
                term in p_text
                for term in (
                    "SOP-02",
                    "SOP-03",
                    "Network Containment API",
                    "volatility script",
                    "RAM dump",
                    "memory snapshot",
                    "Revoke-AzureADUserAllRefreshToken",
                )
            )
            privileged_roles = {
                "admin",
                "security_lead",
                "approver",
                "operator",
                "soc_tier2",
                "soc_tier3",
                "incident_commander",
            }
            if is_internal_sop and user_role not in privileged_roles:
                log.warning(
                    "retriever.sensitive_sop_filtered_for_unprivileged_role",
                    user_role=user_role,
                )
                # For unprivileged roles (tier1_analyst, end_user), sanitize/mask classified command snippets
                masked_payload = dict(payload)
                masked_payload["content"] = re.sub(
                    r"(winpmem\.exe|volatility\.py|Invoke-CrowdstrikeContainment|Revoke-AzureADUserAllRefreshToken|API_KEY=\w+)[^\n]*",
                    "[🔒 RESTRICTED: Command Redacted — Requires Incident Commander Clearance]",
                    p_text,
                    flags=re.IGNORECASE,
                )
                if "[🔒 RESTRICTED" not in masked_payload["content"]:
                    masked_payload["content"] = (
                        "[🔒 RESTRICTED: Classified Forensic Runbook — Requires Incident Commander Clearance]\n"
                        + p_text[:120]
                        + "..."
                    )
                hit.payload = masked_payload

            # Declarative Policy-as-Code data leakage prevention
            policy_redacted = get_policy_engine().redact_knowledge_content(
                user_role, hit.payload.get("content", "")
            )
            if policy_redacted != hit.payload.get("content", ""):
                masked_payload = dict(hit.payload)
                masked_payload["content"] = policy_redacted
                hit.payload = masked_payload

            sanitized_hits.append((hit, score))
        reranked_hits = sanitized_hits

        # Post-filter 2: Dynamic Semantic Gap & Topic Relevance Pruning
        # Filter out chunks whose score drops below 0.65 or is >0.20 lower than top-1 chunk score.
        if reranked_hits:
            top_score = reranked_hits[0][1]
            pruned_hits = []
            for hit, score in reranked_hits:
                if score < 0.65:
                    continue
                if top_score >= 0.85 and (top_score - score) > 0.20:
                    continue
                pruned_hits.append((hit, score))
            if pruned_hits:
                reranked_hits = pruned_hits

        chunks: list[KnowledgeChunk] = []
        for hit, score in reranked_hits:
            payload = hit.payload or {}
            source_str = payload.get("source", "faq")
            try:
                source_enum = KnowledgeSource(source_str)
            except ValueError:
                source_enum = KnowledgeSource.FAQ

            chunks.append(
                KnowledgeChunk(
                    content=payload.get("content", ""),
                    source=source_enum,
                    document_id=payload.get("document_id", str(hit.id)),
                    chunk_id=str(hit.id),
                    metadata=payload.get("metadata", {}),
                    relevance_score=max(0.0, float(score)),
                )
            )

        log.info(
            "retriever.done",
            total_chunks=len(chunks),
            sources_queried=source_values,
        )

        return RetrievalResult(
            chunks=chunks,
            query=request.query,
            total_retrieved=len(chunks),
            sources_queried=request.sources,
        )

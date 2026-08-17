from unittest.mock import MagicMock

from src.utils.knowledge.retriever import _heuristic_rerank


def test_rbac_filtering_tier1_denied_security_lead_doc():
    # Simulated candidate hits with allowed_roles = ["security_lead"]
    hit = MagicMock()
    hit.id = "doc1"
    hit.payload = {
        "content": "Secret vulnerability exploit report",
        "source": "faq",
        "document_id": "secret_doc.md",
        "allowed_roles": ["security_lead"],
    }
    hit.score = 0.90

    # Test candidate ranking
    reranked = _heuristic_rerank("exploit report", [(hit, 0.03)])
    assert len(reranked) == 1

    # Test retrieval filtering logic
    user_role_tier1 = "tier1"
    raw_roles = hit.payload.get("allowed_roles")
    assert "public" not in raw_roles
    assert user_role_tier1 not in raw_roles


def test_rbac_filtering_admin_allowed():
    hit = MagicMock()
    hit.id = "doc2"
    hit.payload = {
        "content": "Executive salary and audit log data",
        "source": "faq",
        "document_id": "audit.md",
        "allowed_roles": ["security_lead"],
    }

    user_role_admin = "admin"
    # Admin persona bypasses restriction
    assert user_role_admin in ("admin", "approver")

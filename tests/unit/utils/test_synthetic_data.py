from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.utils.registry import REGISTRY
from src.utils.synthetic_data import (
    GenerationConfig,
    SyntheticCorpus,
    build_corpus,
    checksum,
    scan_for_unsafe_values,
    validate_corpus,
    write_corpus,
)


def test_same_seed_produces_identical_manifest_and_stable_order() -> None:
    first = build_corpus()
    second = build_corpus()

    assert first.manifest == second.manifest
    assert [ticket.ticket_id for ticket in first.tickets] == [
        ticket.ticket_id for ticket in second.tickets
    ]
    assert first.manifest is not None
    assert first.manifest.counts == {
        "tickets": 500,
        "documents": 30,
        "scenarios": 75,
        "sla_levels": 4,
    }


def test_changed_generation_changes_records_and_manifest() -> None:
    first = build_corpus()
    second = build_corpus(GenerationConfig(generation="northstar-v2"))

    assert first.manifest != second.manifest
    assert first.tickets[0].dataset_generation == "northstar-v1"
    assert second.tickets[0].dataset_generation == "northstar-v2"


def test_invalid_reference_and_non_reserved_values_are_rejected() -> None:
    corpus = build_corpus()
    corpus.tickets[0].policy_id = "DOC-999"
    with pytest.raises(ValueError, match="unknown policy IDs"):
        validate_corpus(corpus)

    with pytest.raises(ValueError, match="non-reserved email domain"):
        scan_for_unsafe_values({"email": "person@example.com"})
    with pytest.raises(ValueError, match="non-documentation IP"):
        scan_for_unsafe_values({"address": "8.8.8.8"})


def test_role_retrieval_cases_only_expect_accessible_documents() -> None:
    corpus = build_corpus()
    role_case = next(case for case in corpus.scenarios if case.scenario_id == "SCN-014")
    role_case.required_role = "end_user"
    with pytest.raises(ValueError, match="role retrieval source unavailable"):
        validate_corpus(corpus)


def test_written_corpus_matches_manifest_checksums(tmp_path: Path) -> None:
    corpus = build_corpus()
    paths = write_corpus(corpus, data_root=tmp_path)

    assert len(paths) == 34
    tickets = json.loads((tmp_path / "knowledge/tickets/synthetic_tickets.json").read_text())
    scenarios = json.loads((tmp_path / "synthetic/capability_scenarios.json").read_text())
    manifest = json.loads((tmp_path / "synthetic/manifest.json").read_text())
    assert checksum(tickets) == manifest["checksums"]["tickets"]
    assert checksum(scenarios) == manifest["checksums"]["scenarios"]
    assert len(list((tmp_path / "knowledge/faq").glob("*.md"))) == 30


def test_every_capability_has_five_curated_cases() -> None:
    corpus: SyntheticCorpus = build_corpus()
    coverage = corpus.manifest.capability_coverage if corpus.manifest else {}
    assert len(coverage) == 15
    assert set(coverage.values()) == {5}


def test_generated_action_risks_match_runtime_registry() -> None:
    corpus = build_corpus()
    assert corpus.sla["action_risk_mapping"] == {
        name: REGISTRY[name].risk_level.value for name in sorted(REGISTRY)
    }


def test_superseded_certificate_policy_matches_current_policy() -> None:
    corpus = build_corpus()
    legacy = next(doc for doc in corpus.documents if doc.document_id == "DOC-012")
    current = next(doc for doc in corpus.documents if doc.document_id == "DOC-029")
    assert legacy.superseded_by == current.document_id
    assert "certificate" in legacy.title.lower() and "certificate" in current.title.lower()
    conflict_cases = [case for case in corpus.scenarios if case.capability == "conflict_resolution"]
    assert all("certificate" in case.query.lower() for case in conflict_cases)

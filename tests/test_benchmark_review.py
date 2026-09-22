from __future__ import annotations

import copy

import pytest

from evaluation.benchmark import CRITICAL_FIELDS
from evaluation.benchmark_review import ReviewImportError, apply_review_payload, merge_review_payloads


DOCUMENT_ID = "a" * 64


def _benchmark():
    empty_reference = {
        "value": None,
        "normalized_value": None,
        "page": None,
        "evidence_text": None,
        "validated_by_human": False,
        "validated_by": None,
        "validated_at": None,
    }
    return {
        "benchmark_version": "1.0",
        "documents": [
            {
                "document_id": DOCUMENT_ID,
                "filename": "edital.pdf",
                "split": "development",
                "orgao": None,
                "uf": None,
                "modalidade": None,
                "metadata_status": "pending_review",
                "annotation_status": "pending_review",
                "references": {field: copy.deepcopy(empty_reference) for field in CRITICAL_FIELDS},
            }
        ],
    }


def _payload(evidence="Trecho literal da página"):
    return {
        "reviewer": "revisor_teste",
        "sources": ["review.json"],
        "documents": [
            {
                "document_id": DOCUMENT_ID,
                "filename": "edital.pdf",
                "metadata": {"orgao": "Órgão X", "uf": "CE", "modalidade": "Pregão"},
                "references": {
                    field: {"value": f"valor-{field}", "page": 2, "evidence_text": evidence}
                    for field in CRITICAL_FIELDS
                },
            }
        ],
    }


def test_apply_review_payload_validates_all_fields_and_metadata():
    updated, report = apply_review_payload(
        _benchmark(),
        _payload(),
        page_loader=lambda _document_id, _page: ("Antes. Trecho literal da página. Depois.", 4),
    )

    document = updated["documents"][0]
    assert report["validated_documents"] == 1
    assert report["validated_fields"] == 3
    assert document["annotation_status"] == "validated"
    assert document["metadata_status"] == "validated"
    assert all(document["references"][field]["validated_by_human"] for field in CRITICAL_FIELDS)
    assert document["references"]["valor_estimado"]["import_sources"] == ["review.json"]


def test_apply_review_payload_rejects_nonliteral_evidence_without_mutating_input():
    original = _benchmark()
    snapshot = copy.deepcopy(original)

    with pytest.raises(ReviewImportError, match="nenhuma alteração foi gravada"):
        apply_review_payload(
            original,
            _payload(evidence="Trecho inexistente"),
            page_loader=lambda _document_id, _page: ("Conteúdo real da página", 4),
        )

    assert original == snapshot


def test_merge_review_payloads_overrides_only_supplied_sections():
    first = _payload()
    second = {
        "reviewer": "revisor_teste",
        "documents": [
            {
                "document_id": DOCUMENT_ID,
                "metadata": {"uf": "PE"},
                "references": {
                    "valor_estimado": {"value": "R$ 1,00", "page": 1, "evidence_text": "R$ 1,00"}
                },
            }
        ],
    }

    merged, overridden = merge_review_payloads([first, second])
    document = merged["documents"][0]
    assert overridden == [DOCUMENT_ID]
    assert document["metadata"]["orgao"] == "Órgão X"
    assert document["metadata"]["uf"] == "PE"
    assert document["references"]["modalidade"]["value"] == "valor-modalidade"
    assert document["references"]["valor_estimado"]["value"] == "R$ 1,00"

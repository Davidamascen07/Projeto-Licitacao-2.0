from __future__ import annotations

import json

from evaluation import benchmark
from evaluation.metrics import (
    aggregate_rows,
    hallucination_rate,
    row_has_reference_mismatch,
    row_is_hallucinated,
)


def _documents(count=10):
    return [
        {"document_id": f"{number:064x}", "filename": f"{number}.pdf", "sha256": f"{number:064x}", "status": "indexed"}
        for number in range(1, count + 1)
    ]


def test_benchmark_serialization_and_deterministic_split(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark, "load_manifest", lambda: {"documents": _documents()})
    first = benchmark.create_benchmark(tmp_path / "a.json", seed=42)
    second = benchmark.create_benchmark(tmp_path / "b.json", seed=42)
    assert [(d["document_id"], d["split"]) for d in first["documents"]] == [(d["document_id"], d["split"]) for d in second["documents"]]
    assert sum(d["split"] == "development" for d in first["documents"]) == 7
    assert sum(d["split"] == "test" for d in first["documents"]) == 3
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))["benchmark_version"] == "1.0"


def test_hallucination_rate_formula():
    rows = [
        {"answered": True, "value": "A", "evidence": {"evidence_valid": True}, "reference": {"validated_by_human": True, "value": "A"}},
        {"answered": True, "value": "B", "evidence": {"evidence_valid": False}, "reference": {}},
        {"answered": False, "evidence": {"evidence_valid": False}},
    ]
    result = hallucination_rate(rows)
    assert result["answered_fields"] == 2
    assert result["hallucinated_fields"] == 1
    assert result["hallucination_rate"] == 0.5
    assert result["unsupported_claim_rate"] == 0.5
    assert result["reference_mismatch_rate"] == 0.0


def test_reference_wording_difference_is_not_factual_hallucination():
    row = {
        "answered": True,
        "value": "Procedimento: Credenciamento.",
        "faithfulness": 1.0,
        "evidence": {"evidence_valid": True},
        "reference": {"validated_by_human": True, "value": "credenciamento"},
    }
    result = hallucination_rate([row])
    assert row_has_reference_mismatch(row) is True
    assert row_is_hallucinated(row) is False
    assert result["reference_mismatch_rate"] == 1.0
    assert result["unsupported_claim_rate"] == 0.0
    assert result["hallucination_rate"] == 0.0


def test_partial_faithfulness_is_unsupported_even_with_valid_evidence_anchor():
    row = {
        "answered": True,
        "value": "Afirmação parcialmente sustentada",
        "faithfulness": 0.5,
        "evidence": {"evidence_valid": True},
        "reference": {},
    }
    assert hallucination_rate([row])["unsupported_claim_rate"] == 0.5


def test_aggregation_of_latency_tokens_and_cost():
    rows = [
        {"approach": "rag", "config_id": "c", "metrics": {"total_ms": 10}, "usage": {"prompt_tokens": 4, "completion_tokens": 2, "estimated_cost": 0.1}, "answered": True, "evidence": {"evidence_valid": True}, "reference": {}},
        {"approach": "rag", "config_id": "c", "metrics": {"total_ms": 30}, "usage": {"prompt_tokens": 6, "completion_tokens": 4, "estimated_cost": 0.3}, "answered": True, "evidence": {"evidence_valid": True}, "reference": {}},
    ]
    summary = aggregate_rows(rows, ("approach", "config_id"))[0]
    assert summary["total_ms"]["mean"] == 20
    assert summary["prompt_tokens"]["mean"] == 5
    assert summary["estimated_cost"]["mean"] == 0.2

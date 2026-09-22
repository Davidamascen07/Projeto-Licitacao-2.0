from __future__ import annotations

import json

import pytest

from evaluation.generate_reports import _assert_split, hypothesis_report
from evaluation.ragas_metrics import (
    MAX_EVALUATION_CONTEXT_CHARS,
    _evaluation_contexts,
    _install_ragas_langchain_compatibility_shim,
)
from evaluation.run_experiments import (
    choose_configuration,
    default_output_dir,
    normalize_approaches,
    run,
)


def _metric_row(config_id, correctness, faithfulness, *, split="development"):
    return {
        "split": split,
        "approach": "rag",
        "config_id": config_id,
        "answer_correctness": correctness,
        "faithfulness": faithfulness,
        "answered": True,
        "evidence": {"evidence_valid": True},
        "reference": {"validated_by_human": True, "value": "x"},
        "value": "x",
        "usage": {"estimated_cost": 0.01},
        "metrics": {"total_ms": 10},
    }


def test_default_result_directories_are_isolated():
    assert default_output_dir("development") != default_output_dir("test")
    assert default_output_dir("development").name == "development"
    assert default_output_dir("test").name == "test"


def test_approach_selection_is_explicit_deduplicated_and_validated():
    assert normalize_approaches(["rag", "rag"]) == ("rag",)
    assert normalize_approaches(None) == ("regex", "llm_no_retrieval", "rag")
    with pytest.raises(ValueError, match="desconhecidas"):
        normalize_approaches(["unknown"])


def test_configuration_selection_ignores_test_rows():
    rows = [
        _metric_row("c1", 0.5, 0.5),
        _metric_row("c2", 0.8, 0.8),
        _metric_row("c1", 1.0, 1.0, split="test"),
    ]
    assert choose_configuration(rows)["selected_config_id"] == "c2"


def test_test_execution_requires_development_selection(tmp_path):
    benchmark = {
        "documents": [
            {
                "document_id": "a" * 64,
                "filename": "x.pdf",
                "split": "test",
                "references": {field: {} for field in ("valor_estimado", "modalidade", "prazo_entrega_proposta")},
            }
        ]
    }
    benchmark_path = tmp_path / "benchmark.json"
    benchmark_path.write_text(json.dumps(benchmark), encoding="utf-8")
    selected_path = tmp_path / "selected.json"
    selected_path.write_text(
        json.dumps({"selected_config_id": "chunk300_overlap50_topk3", "source_split": "test"}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exclusivamente no desenvolvimento"):
        run(
            benchmark_path,
            split="test",
            output_dir=tmp_path / "test-results",
            selected_config_path=selected_path,
        )


def test_hypothesis_uses_only_selected_rag_test_rows():
    rows = [
        _metric_row("selected", 0.9, 0.9, split="test"),
        _metric_row("other", 0.0, 0.0, split="test"),
        _metric_row("selected", 0.0, 0.0, split="development"),
    ]
    report = hypothesis_report(rows, "selected")
    assert report["sample_rows"] == 1
    assert report["observed"]["answer_correctness"]["mean"] == 0.9
    assert report["conclusion"] == "confirmada"


def test_report_rejects_mixed_splits():
    with pytest.raises(ValueError, match="misturam splits"):
        _assert_split([{"split": "development"}, {"split": "test"}], "development")


def test_ragas_compatibility_shim_is_reentrant():
    _install_ragas_langchain_compatibility_shim()
    _install_ragas_langchain_compatibility_shim()


def test_ragas_context_limit_prioritizes_literal_evidence_chunk():
    evidence_text = "evidencia-" * 400
    row = {
        "evidence": {"chunk_id": "evidence"},
        "sources": [
            {"chunk_id": "high-score", "text": "outro-" * 3000, "retrieval_score": 0.99},
            {"chunk_id": "evidence", "text": evidence_text, "retrieval_score": 0.10},
        ],
    }
    contexts = _evaluation_contexts(row)
    assert contexts[0] == evidence_text
    assert sum(map(len, contexts)) <= MAX_EVALUATION_CONTEXT_CHARS

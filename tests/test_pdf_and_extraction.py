from __future__ import annotations

import json

import pytest

from services.config import estimate_cost
from services.extraction_service import (
    NOT_FOUND_MSG,
    _build_field_prompt,
    extract_fields_from_sources,
    extract_single_field,
)
from services.pdf_service import validate_pdf_file
from services.llm_utils import complete_with_metrics
from tests.conftest import FakeLLM


def test_invalid_or_corrupted_pdf_is_rejected(tmp_path):
    path = tmp_path / "bad.pdf"
    path.write_bytes(b"not-a-pdf")
    with pytest.raises(ValueError):
        validate_pdf_file(path)


def test_minimal_evaluation_with_mocked_llm_and_retrieval(monkeypatch, tmp_path):
    source = {
        "chunk_id": "chunk-1", "document_id": "doc-1", "filename": "edital.pdf",
        "page_start": 1, "page_end": 1, "text": "A modalidade é Pregão Eletrônico.", "retrieval_score": 0.95,
    }
    (tmp_path / "edital.pdf").write_bytes(b"%PDF-")
    monkeypatch.setattr("services.evidence.PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("services.evidence.load_manifest", lambda: {"documents": [{"document_id": "doc-1", "relative_path": "edital.pdf", "page_count": 1}]})
    search_fn = lambda *_args, **_kwargs: [source]
    preamble_fn = lambda **_kwargs: [source]
    llm = FakeLLM('{"value":"Pregão Eletrônico","source_chunk_id":"chunk-1","evidence_text":"modalidade é Pregão Eletrônico"}')
    result = extract_single_field(
        "modalidade", "Qual a modalidade?", "doc-1", llm_client=llm,
        search_fn=search_fn, preamble_fn=preamble_fn,
    )
    assert result["value"] == "Pregão Eletrônico"
    assert result["evidence"]["evidence_valid"] is True
    assert result["usage"]["total_tokens"] == 14


def test_multifield_extraction_uses_one_call_and_does_not_double_count_usage():
    fields = {"valor_estimado": "valor?", "modalidade": "modalidade?", "prazo_entrega_proposta": "prazo?"}
    payload = json.dumps(
        {
            field: {"value": NOT_FOUND_MSG, "source_chunk_id": "", "evidence_text": ""}
            for field in fields
        },
        ensure_ascii=False,
    )
    results = extract_fields_from_sources(fields, "doc-1", [], llm_client=FakeLLM(payload))
    assert set(results) == set(fields)
    assert sum(result["usage"]["total_tokens"] for result in results.values()) == 14
    assert sum(result["usage"]["estimated_cost"] for result in results.values()) == pytest.approx(
        estimate_cost(10, 4)["estimated_cost"]
    )
    assert all(result["usage"]["shared_call_fields"] == 3 for result in results.values())


def test_daily_groq_limit_stops_without_repeating_calls():
    class DailyLimitClient:
        calls = 0

        def complete(self, _prompt):
            self.calls += 1
            raise RuntimeError("Rate limit on tokens per day (TPD)")

    client = DailyLimitClient()
    with pytest.raises(RuntimeError, match="Cota diária"):
        complete_with_metrics("teste", llm_client=client, max_retries=8, retry_wait_seconds=0)
    assert client.calls == 1


def test_field_prompt_keeps_late_exact_value_from_preamble():
    source = {
        "chunk_id": "cover",
        "text": ("introdução " * 300) + "VALOR ESTIMADO: SIGILOSO " + ("fim " * 300),
    }
    prompt = _build_field_prompt("Qual é o valor estimado?", [source])
    assert "VALOR ESTIMADO: SIGILOSO" in prompt

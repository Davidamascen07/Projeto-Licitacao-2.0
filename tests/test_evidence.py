from __future__ import annotations

from services.evidence import literal_is_present, normalization_is_valid, validate_evidence


def _source():
    return {
        "chunk_id": "chunk-1",
        "document_id": "doc-1",
        "filename": "edital.pdf",
        "page_start": 2,
        "page_end": 2,
        "text": "Valor   estimado:\nR$ 1.000,00.",
        "retrieval_score": 0.9,
    }


def _manifest(page_count=3):
    return {"documents": [{"document_id": "doc-1", "relative_path": "edital.pdf", "page_count": page_count}]}


def test_literal_validation_normalizes_whitespace_and_unicode(tmp_path, monkeypatch):
    (tmp_path / "edital.pdf").write_bytes(b"%PDF-")
    monkeypatch.setattr("services.evidence.PROJECT_ROOT", tmp_path)
    assert literal_is_present("Valor estimado: R$ 1.000,00.", _source()["text"])
    result = validate_evidence(
        evidence_text="Valor estimado: R$ 1.000,00.", source_chunk_id="chunk-1",
        retrieved_sources=[_source()], selected_document_id="doc-1", value="R$ 1.000,00",
        field_name="valor_estimado", manifest=_manifest(),
    )
    assert result["evidence_valid"] is True


def test_rejects_nonexistent_file(tmp_path, monkeypatch):
    monkeypatch.setattr("services.evidence.PROJECT_ROOT", tmp_path)
    result = validate_evidence(
        evidence_text="Valor estimado", source_chunk_id="chunk-1", retrieved_sources=[_source()],
        selected_document_id="doc-1", manifest=_manifest(),
    )
    assert result["validation_error"] == "source_file_not_found"


def test_rejects_invalid_page(tmp_path, monkeypatch):
    (tmp_path / "edital.pdf").write_bytes(b"%PDF-")
    monkeypatch.setattr("services.evidence.PROJECT_ROOT", tmp_path)
    result = validate_evidence(
        evidence_text="Valor estimado", source_chunk_id="chunk-1", retrieved_sources=[_source()],
        selected_document_id="doc-1", manifest=_manifest(page_count=1),
    )
    assert result["validation_error"] == "page_out_of_document_range"


def test_rejects_other_document_context(tmp_path):
    source = _source()
    source["document_id"] = "other"
    result = validate_evidence(
        evidence_text="Valor estimado", source_chunk_id="chunk-1", retrieved_sources=[source],
        selected_document_id="doc-1", manifest=_manifest(),
    )
    assert result["validation_error"] == "retrieved_context_contains_other_document"


def test_confidential_value_is_a_valid_normalized_value():
    assert normalization_is_valid("valor_estimado", "Valor estimado: sigiloso.")
    assert normalization_is_valid("valor_estimado", "Orçamento não divulgado.")

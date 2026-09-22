from __future__ import annotations

import io
from types import SimpleNamespace

import pytest

import app as app_module
from services import agent_service
from services.llm_utils import complete_with_metrics
from services.retrieval import detect_query_intent


def _source(chunk_id: str, text: str, *, page: int = 1, part: str = "edital_principal") -> dict:
    return {
        "chunk_id": chunk_id,
        "document_id": "doc-1",
        "filename": "edital.pdf",
        "chunk_index": page,
        "page_start": page,
        "page_end": page,
        "text": text,
        "document_part": part,
    }


def _valid_evidence(**kwargs):
    source = next(
        item
        for item in kwargs["retrieved_sources"]
        if item["chunk_id"] == kwargs["source_chunk_id"]
    )
    return {
        "evidence_valid": True,
        "chunk_id": source["chunk_id"],
        "filename": source["filename"],
        "pages": str(source["page_start"]),
        "text": kwargs["evidence_text"],
    }


def test_specific_receipt_and_validity_deadlines_are_found(monkeypatch):
    sources = [
        _source(
            "receipt",
            "O recebimento definitivo ocorrerá no prazo de até 10 (dez) dias úteis, "
            "contados do recebimento provisório",
            page=61,
            part="termo_referencia",
        ),
        _source(
            "validity",
            "O prazo inicial de vigência da Ata de Registro de Preços e/ou contrato, "
            "conforme for o caso, será de 12 (doze) meses contados da assinatura.",
            page=35,
        ),
    ]
    monkeypatch.setattr(agent_service, "validate_evidence", _valid_evidence)

    receipt_response, receipt_items, _ = agent_service._deadline_items_from_sources(
        sources,
        "doc-1",
        "prazo_recebimento_definitivo",
    )
    validity_response, validity_items, _ = agent_service._deadline_items_from_sources(
        sources,
        "doc-1",
        "prazo_vigencia",
    )

    assert {item["deadline_type"] for item in receipt_items} == {
        "prazo_recebimento_definitivo"
    }
    assert agent_service._deadline_status(
        "prazo_recebimento_definitivo",
        receipt_items,
    ) == "FOUND"
    assert "10 dias úteis" in receipt_response
    assert {item["deadline_type"] for item in validity_items} == {"prazo_vigencia"}
    assert agent_service._deadline_status("prazo_vigencia", validity_items) == "FOUND"
    assert "12 meses" in validity_response


def test_technical_documents_query_uses_habilitation_scope(monkeypatch):
    assert (
        detect_query_intent("Quais documentos técnicos a empresa deve apresentar?")
        == "documentos_tecnicos"
    )
    source = _source(
        "technical",
        "CAPACIDADE TÉCNICO-OPERACIONAL. CAPACIDADE TÉCNICO-PROFISSIONAL.",
        page=22,
    )
    monkeypatch.setattr(agent_service, "validate_evidence", _valid_evidence)

    response, items, _ = agent_service._validated_habilitation_items(
        {},
        [source],
        "doc-1",
        {"tecnico_operacional", "tecnico_profissional"},
    )

    assert response.startswith("Documentos técnicos exigidos:")
    assert {item["category"] for item in items} == {
        "tecnico_operacional",
        "tecnico_profissional",
    }


def test_truncated_habilitation_json_uses_local_fallback_with_one_call(monkeypatch):
    source = _source(
        "habilitation",
        "HABILITAÇÃO JURÍDICA. REGULARIDADE FISCAL E TRABALHISTA. "
        "QUALIFICAÇÃO ECONÔMICA-FINANCEIRA. CAPACIDADE TÉCNICO-OPERACIONAL. "
        "CAPACIDADE TÉCNICO-PROFISSIONAL. PROCURAÇÃO/DECLARAÇÕES.",
        page=19,
    )
    calls = 0

    class TruncatedLLM:
        def complete(self, _prompt):
            nonlocal calls
            calls += 1
            return SimpleNamespace(
                text='{"status":"FOUND","items":[',
                raw={"usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}},
            )

    def fake_search(_query, *, top_k, document_id, timing):
        assert top_k == 3
        assert document_id == "doc-1"
        timing["query_intent"] = "requisitos_habilitacao"
        return [source]

    monkeypatch.setattr(agent_service, "search", fake_search)
    monkeypatch.setattr(
        agent_service,
        "expand_evidence_bundle",
        lambda **_kwargs: (
            [source],
            {
                "section_expansion_ms": 0.0,
                "adjacent_chunks_considered": 1,
                "evidence_bundle_chunks": 1,
            },
        ),
    )
    monkeypatch.setattr(agent_service, "validate_evidence", _valid_evidence)

    result = agent_service.process_query_with_agent(
        "Requisitos de habilitação?",
        "doc-1",
        llm_client=TruncatedLLM(),
    )

    assert calls == 1
    assert result["status"] == "FOUND"
    assert {item["category"] for item in result["habilitation_items"]} == {
        "juridica",
        "fiscal_trabalhista",
        "economica",
        "tecnico_operacional",
        "tecnico_profissional",
        "declaracoes",
    }


def test_generic_labor_declaration_is_not_fiscal_regularness(monkeypatch):
    source = _source(
        "declaration",
        "Declaração de regularidade perante o Ministério do Trabalho.",
    )
    monkeypatch.setattr(agent_service, "validate_evidence", _valid_evidence)

    _response, items, rejected = agent_service._validated_habilitation_items(
        {
            "items": [
                {
                    "category": "fiscal_trabalhista",
                    "summary": "Apresentar declaração trabalhista.",
                    "source_chunk_id": "declaration",
                    "evidence_text": source["text"],
                }
            ]
        },
        [source],
        "doc-1",
    )

    assert items == []
    assert rejected == 1


def test_rate_limit_error_never_retries_generation():
    calls = 0

    class RateLimitedClient:
        def complete(self, _prompt):
            nonlocal calls
            calls += 1
            raise RuntimeError("rate limit")

    with pytest.raises(RuntimeError, match="rate limit"):
        complete_with_metrics(
            "teste",
            llm_client=RateLimitedClient(),
            max_retries=8,
            retry_wait_seconds=0,
        )

    assert calls == 1


def test_commented_groq_keys_are_loaded_without_duplicates(monkeypatch, tmp_path):
    from services import config

    primary = "gsk_" + "a" * 32
    secondary = "gsk_" + "b" * 32
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"GROQCLOUD_API_KEY={primary}\n# {secondary}\n# texto comum\n# {primary}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GROQCLOUD_API_KEY", primary)
    monkeypatch.delenv("GROQCLOUD_API_KEYS", raising=False)

    assert config._load_groq_api_keys(env_file) == [primary, secondary]


def test_groq_client_rotates_only_after_rotatable_error():
    from services import config

    class CompletionEndpoint:
        def __init__(self, outcome):
            self.outcome = outcome
            self.calls = 0

        def create(self, **_kwargs):
            self.calls += 1
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

    class Client:
        def __init__(self, outcome):
            self.endpoint = CompletionEndpoint(outcome)
            self.chat = type("Chat", (), {"completions": self.endpoint})()

    class RateLimitError(RuntimeError):
        status_code = 429

    response = type(
        "Response",
        (),
        {
            "choices": [type("Choice", (), {"message": type("Message", (), {"content": "ok"})()})()],
            "usage": None,
        },
    )()
    first = Client(RateLimitError("rate limit"))
    second = Client(response)
    rotating = config._RotatingGroqCompletionClient([first, second])

    assert rotating.complete("teste").text == "ok"
    assert first.endpoint.calls == 1
    assert second.endpoint.calls == 1


def test_extract_fields_endpoint_uses_one_shared_extraction(client, monkeypatch):
    captured = {}
    monkeypatch.setattr(app_module, "get_chunks", lambda _document_id=None: [{"document_id": "doc-1"}])
    monkeypatch.setattr(app_module, "require_embedding_ready", lambda: None)

    def fake_extract(field_questions, document_id):
        captured["field_questions"] = field_questions
        captured["document_id"] = document_id
        return {"objeto": {"value": "Objeto validado"}}

    monkeypatch.setattr(app_module, "extract_multiple_fields", fake_extract)
    response = client.post("/extract_fields", json={"document_id": "doc-1"})

    assert response.status_code == 200
    assert captured["document_id"] == "doc-1"
    assert captured["field_questions"] is app_module.FIELD_QUESTIONS


@pytest.fixture
def client():
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_duplicate_upload_does_not_write_second_pdf(client, monkeypatch, tmp_path):
    monkeypatch.setattr(app_module, "UPLOAD_FOLDER", tmp_path)
    monkeypatch.setattr(app_module, "validate_pdf_file", lambda _path: 1)
    monkeypatch.setattr(app_module, "calculate_sha256", lambda _path: "a" * 64)
    monkeypatch.setattr(app_module, "document_id_from_sha256", lambda _sha: "doc-1")
    monkeypatch.setattr(app_module, "_indexed_document_ids", lambda: ["doc-1"])
    monkeypatch.setattr(
        app_module,
        "get_chunks",
        lambda document_id=None: (
            [
                {
                    "document_id": "doc-1",
                    "filename": "canonical.pdf",
                    "chunk_id": "chunk-1",
                }
            ]
            if document_id == "doc-1"
            else [{"document_id": "doc-1"}]
        ),
    )

    response = client.post(
        "/upload_pdf",
        data={"file": (io.BytesIO(b"%PDF-1.4 controlled"), "other-name.pdf")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["chunks_added"] == 0
    assert response.get_json()["filename"] == "canonical.pdf"
    assert list(tmp_path.iterdir()) == []


def test_interface_uses_unified_busy_state_and_clears_document_outputs():
    template = (
        app_module.Path(app_module.app.root_path) / "templates" / "index.html"
    ).read_text(encoding="utf-8")

    assert "let uploadInFlight = false;" in template
    assert "const operationBusy = uploadInFlight || queryInFlight || extractionInFlight;" in template
    assert "documentSelect.disabled = operationBusy;" in template
    assert "clearDocumentOutputs();" in template
    assert "Evidências validadas" in template
    assert "Expansão de seção:" in template

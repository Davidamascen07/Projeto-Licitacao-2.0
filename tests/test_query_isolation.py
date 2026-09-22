from __future__ import annotations

import pytest

import app as app_module
from services import agent_service
from tests.conftest import FakeLLM


@pytest.fixture
def client():
    app_module.app.config.update(TESTING=True)
    return app_module.app.test_client()


def test_query_requires_document_id(client, monkeypatch):
    called = False

    def fake_process(*_args, **_kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(app_module, "process_query_with_agent", fake_process)
    response = client.post("/query", json={"query": "Qual é o objeto?"})

    assert response.status_code == 400
    assert "Selecione ou envie" in response.get_json()["error"]
    assert called is False


def test_query_rejects_unknown_or_empty_document(client, monkeypatch):
    monkeypatch.setattr(app_module, "_indexed_document_ids", lambda: ["doc-1"])
    monkeypatch.setattr(app_module, "get_chunks", lambda document_id=None: [])

    response = client.post(
        "/query",
        json={"query": "Qual é o objeto?", "document_id": "doc-inexistente"},
    )

    assert response.status_code == 404
    assert "Documento não encontrado" in response.get_json()["error"]


def test_query_with_many_documents_uses_only_selected_document(client, monkeypatch):
    selected = "doc-11"
    document_ids = [f"doc-{number}" for number in range(18)]
    captured = {}

    monkeypatch.setattr(app_module, "_indexed_document_ids", lambda: document_ids)
    monkeypatch.setattr(app_module, "require_embedding_ready", lambda: None)
    monkeypatch.setattr(
        app_module,
        "get_chunks",
        lambda document_id=None: [{"document_id": selected}] if document_id == selected else [],
    )

    def fake_process(query_text, *, document_id):
        captured.update({"query": query_text, "document_id": document_id})
        return {
            "response": "Objeto encontrado.",
            "document_id": document_id,
            "sources": [
                {
                    "document_id": document_id,
                    "filename": "selecionado.pdf",
                    "page_start": 1,
                    "page_end": 1,
                    "text": "Objeto encontrado.",
                }
            ],
        }

    monkeypatch.setattr(app_module, "process_query_with_agent", fake_process)
    response = client.post(
        "/query",
        json={"query": "Qual é o objeto?", "document_id": selected},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert captured == {"query": "Qual é o objeto?", "document_id": selected}
    assert {source["document_id"] for source in payload["sources"]} == {selected}


def test_query_rejects_cross_document_sources(client, monkeypatch):
    monkeypatch.setattr(app_module, "_indexed_document_ids", lambda: ["doc-1"])
    monkeypatch.setattr(app_module, "require_embedding_ready", lambda: None)
    monkeypatch.setattr(app_module, "get_chunks", lambda _document_id=None: [{"document_id": "doc-1"}])
    monkeypatch.setattr(
        app_module,
        "process_query_with_agent",
        lambda *_args, **_kwargs: {
            "response": "resposta",
            "sources": [{"document_id": "doc-2"}],
        },
    )

    response = client.post(
        "/query",
        json={"query": "Prazo?", "document_id": "doc-1"},
    )

    assert response.status_code == 500


@pytest.mark.parametrize("state", ["loading", "ready", "error"])
def test_status_exposes_embedding_state(client, monkeypatch, state):
    monkeypatch.setattr(
        app_module,
        "get_embedding_model_status",
        lambda: {
            "embedding_model_status": state,
            "embedding_model_load_ms": 42.0 if state == "ready" else None,
            "embedding_model_error": "Falha ao preparar o modelo de busca." if state == "error" else None,
        },
    )
    monkeypatch.setattr(app_module, "get_index", lambda: None)
    monkeypatch.setattr(app_module, "get_chunks", lambda _document_id=None: [])
    monkeypatch.setattr(app_module, "get_document_summaries", lambda: [])
    monkeypatch.setattr(app_module, "get_index_info", lambda: {})
    monkeypatch.setattr(app_module, "is_storage_consistent", lambda: True)

    response = client.get("/status")

    assert response.status_code == 200
    assert response.get_json()["embedding_model_status"] == state


def test_agent_query_caps_top_k_and_keeps_timing(monkeypatch):
    captured = {}

    def fake_search(query, *, top_k, document_id, timing):
        captured.update({"query": query, "top_k": top_k, "document_id": document_id})
        timing.update({"embedding_ms": 12.5, "vector_search_ms": 0.8})
        return [
            {
                "chunk_id": f"chunk-{number}",
                "document_id": document_id,
                "filename": "selecionado.pdf",
                "page_start": number,
                "page_end": number,
                "text": f"trecho {number}",
            }
            for number in range(1, 4)
        ]

    monkeypatch.setattr(agent_service, "search", fake_search)
    result = agent_service.process_query_with_agent(
        "Qual é o objeto?",
        "doc-1",
        top_k=99,
        llm_client=FakeLLM("Resposta objetiva."),
    )

    assert captured["top_k"] == 3
    assert captured["document_id"] == "doc-1"
    assert len(result["sources"]) == 3
    assert result["metrics"]["embedding_ms"] == 12.5
    assert result["metrics"]["vector_search_ms"] == 0.8


def test_agent_query_rejects_cross_document_result_before_llm(monkeypatch):
    monkeypatch.setattr(
        agent_service,
        "search",
        lambda *_args, **_kwargs: [
            {
                "chunk_id": "wrong",
                "document_id": "doc-2",
                "filename": "outro.pdf",
                "page_start": 1,
                "page_end": 1,
                "text": "trecho",
            }
        ],
    )

    with pytest.raises(RuntimeError, match="outro edital"):
        agent_service.process_query_with_agent(
            "Prazo?",
            "doc-1",
            llm_client=FakeLLM("não deve ser chamado"),
        )


def test_interface_preserves_busy_state_during_status_poll():
    template = (app_module.Path(app_module.app.root_path) / "templates" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "let uploadInFlight = false;" in template
    assert "let queryInFlight = false;" in template
    assert "let extractionInFlight = false;" in template
    assert "const operationBusy = uploadInFlight || queryInFlight || extractionInFlight;" in template
    assert "queryBtn.disabled = !hasDocument || !modelReady || operationBusy;" in template
    assert "chip.disabled = !hasDocument || !modelReady || operationBusy;" in template
    assert "extractFieldsBtn.disabled = !hasDocument || !modelReady || operationBusy;" in template
    assert "await fetchStatus(data.document_id);" in template
    assert "const selectedBefore = preferredDocumentId || documentSelect.value;" in template


def test_upload_failure_does_not_expose_sync_exception():
    source = (app_module.Path(app_module.app.root_path) / "app.py").read_text(encoding="utf-8")

    assert '"sync": report' not in source
    assert "Não foi possível indexar o edital." in source


@pytest.mark.parametrize(
    ("exception", "code"),
    [
        (
            app_module.EmbeddingModelLoadingError("detalhe interno"),
            "EMBEDDING_MODEL_LOADING",
        ),
        (
            app_module.EmbeddingModelUnavailableError("detalhe interno"),
            "EMBEDDING_MODEL_UNAVAILABLE",
        ),
    ],
)
def test_query_returns_safe_503_when_embedding_is_not_ready(
    client,
    monkeypatch,
    exception,
    code,
):
    process_called = False

    monkeypatch.setattr(app_module, "_indexed_document_ids", lambda: ["doc-1"])
    monkeypatch.setattr(app_module, "get_chunks", lambda _document_id=None: [{"document_id": "doc-1"}])
    monkeypatch.setattr(
        app_module,
        "require_embedding_ready",
        lambda: (_ for _ in ()).throw(exception),
    )

    def fake_process(*_args, **_kwargs):
        nonlocal process_called
        process_called = True

    monkeypatch.setattr(app_module, "process_query_with_agent", fake_process)
    response = client.post("/query", json={"query": "Objeto?", "document_id": "doc-1"})

    assert response.status_code == 503
    assert response.get_json()["code"] == code
    assert "detalhe interno" not in response.get_data(as_text=True)
    assert process_called is False


def test_unexpected_query_error_is_never_exposed(client, monkeypatch):
    monkeypatch.setattr(app_module, "_indexed_document_ids", lambda: ["doc-1"])
    monkeypatch.setattr(app_module, "get_chunks", lambda _document_id=None: [{"document_id": "doc-1"}])
    monkeypatch.setattr(app_module, "require_embedding_ready", lambda: None)
    monkeypatch.setattr(
        app_module,
        "process_query_with_agent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("SEGREDO_INTERNO")),
    )

    response = client.post("/query", json={"query": "Objeto?", "document_id": "doc-1"})

    assert response.status_code == 500
    assert response.get_json()["code"] == "INTERNAL_ERROR"
    assert "SEGREDO_INTERNO" not in response.get_data(as_text=True)


def test_interface_renders_http_failures_as_system_errors():
    template = (app_module.Path(app_module.app.root_path) / "templates" / "index.html").read_text(
        encoding="utf-8"
    )

    assert "appendSystemError(" in template
    assert "label.textContent = 'Erro do sistema';" in template
    assert "appendAgentMessage({response: err.message" not in template

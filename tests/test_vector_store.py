from __future__ import annotations

import hashlib

from services import vector_store
from tests.conftest import FakeEmbeddingModel


def _item(name: str, payload: str) -> dict:
    sha = hashlib.sha256(payload.encode()).hexdigest()
    return {
        "document_id": sha,
        "sha256": sha,
        "filename": name,
        "relative_path": f"uploads/{name}",
        "size_bytes": len(payload),
        "path": None,
    }


def test_removed_pdf_is_marked_missing(monkeypatch):
    old = _item("old.pdf", "old")
    monkeypatch.setattr(vector_store, "load_manifest", lambda: {"documents": [{**old, "status": "indexed"}]})
    monkeypatch.setattr(vector_store, "discover_pdfs", lambda: [])
    monkeypatch.setattr(vector_store, "_chunks", [{"document_id": old["document_id"], "filename": "old.pdf"}])
    plan = vector_store.plan_synchronization()
    assert old["document_id"] in plan["missing"]
    assert plan["manifest"]["documents"][0]["status"] == "file_missing"


def test_changed_pdf_creates_new_id_and_retires_old(monkeypatch):
    old = _item("same.pdf", "old")
    new = _item("same.pdf", "new")
    monkeypatch.setattr(vector_store, "load_manifest", lambda: {"documents": [{**old, "status": "indexed"}]})
    monkeypatch.setattr(vector_store, "discover_pdfs", lambda: [new])
    monkeypatch.setattr(vector_store, "_chunks", [{"document_id": old["document_id"], "filename": "same.pdf"}])
    plan = vector_store.plan_synchronization()
    assert new["document_id"] in plan["added"]
    assert old["document_id"] in plan["missing"]
    assert new["document_id"] in plan["to_index"]


def test_search_is_filtered_by_document(monkeypatch):
    chunks = [
        {"chunk_id": "a", "document_id": "doc-a", "filename": "a.pdf", "chunk_index": 0, "page_start": 1, "page_end": 1, "text": "valor estimado 10"},
        {"chunk_id": "b", "document_id": "doc-b", "filename": "b.pdf", "chunk_index": 0, "page_start": 1, "page_end": 1, "text": "valor estimado 20"},
    ]
    vector_store.rebuild_vector_index(chunks, embedding_model=FakeEmbeddingModel(), persist=False)
    monkeypatch.setattr(vector_store, "_index_info", {"metric": vector_store.INDEX_METRIC})
    result = vector_store.search("valor", document_id="doc-a", embedding_model=FakeEmbeddingModel())
    assert result
    assert {item["document_id"] for item in result} == {"doc-a"}


def test_add_chunks_prevents_duplicate_index_entry(monkeypatch):
    monkeypatch.setattr(vector_store, "_chunks", [])
    chunk = {"document_id": "doc", "chunk_index": 0, "filename": "x.pdf", "text": "x", "page_start": 1, "page_end": 1}
    assert len(vector_store.add_chunks([chunk])) == 1
    assert vector_store.add_chunks([chunk]) == []


def test_incremental_append_encodes_only_new_chunks(monkeypatch):
    old_chunk = {
        "chunk_id": "old",
        "document_id": "doc-old",
        "filename": "old.pdf",
        "chunk_index": 0,
        "page_start": 1,
        "page_end": 1,
        "text": "conteúdo antigo",
    }
    new_chunk = {
        "chunk_id": "new",
        "document_id": "doc-new",
        "filename": "new.pdf",
        "chunk_index": 0,
        "page_start": 1,
        "page_end": 1,
        "text": "conteúdo novo",
    }
    monkeypatch.setattr(vector_store, "_chunks", [])
    monkeypatch.setattr(vector_store, "_faiss_index", None)
    monkeypatch.setattr(vector_store, "_index_info", {})
    vector_store.rebuild_vector_index(
        [old_chunk],
        embedding_model=FakeEmbeddingModel(),
        persist=False,
    )

    calls = []

    class RecordingModel(FakeEmbeddingModel):
        def encode(self, texts, normalize_embeddings=False):
            calls.append(list(texts))
            return super().encode(texts, normalize_embeddings=normalize_embeddings)

    vector_store.append_chunks_to_vector_index(
        [new_chunk],
        embedding_model=RecordingModel(),
        persist=False,
    )

    assert calls == [["conteúdo novo"]]
    assert vector_store.get_index().ntotal == 2
    assert [chunk["chunk_id"] for chunk in vector_store.get_chunks()] == ["old", "new"]


def test_incremental_embedding_failure_preserves_loaded_index(monkeypatch):
    old_chunk = {
        "chunk_id": "old",
        "document_id": "doc-old",
        "filename": "old.pdf",
        "chunk_index": 0,
        "page_start": 1,
        "page_end": 1,
        "text": "conteúdo antigo",
    }
    new_chunk = {
        "chunk_id": "new",
        "document_id": "doc-new",
        "filename": "new.pdf",
        "chunk_index": 0,
        "page_start": 1,
        "page_end": 1,
        "text": "conteúdo novo",
    }
    monkeypatch.setattr(vector_store, "_chunks", [])
    monkeypatch.setattr(vector_store, "_faiss_index", None)
    monkeypatch.setattr(vector_store, "_index_info", {})
    vector_store.rebuild_vector_index(
        [old_chunk],
        embedding_model=FakeEmbeddingModel(),
        persist=False,
    )

    class FailingModel:
        def encode(self, *_args, **_kwargs):
            raise RuntimeError("falha simulada")

    before_chunks = vector_store.get_chunks()
    before_vectors = vector_store.get_index().ntotal

    import pytest

    with pytest.raises(RuntimeError, match="falha simulada"):
        vector_store.append_chunks_to_vector_index(
            [new_chunk],
            embedding_model=FailingModel(),
            persist=False,
        )

    assert vector_store.get_chunks() == before_chunks
    assert vector_store.get_index().ntotal == before_vectors

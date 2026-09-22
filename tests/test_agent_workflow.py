from __future__ import annotations

import pytest

from services.agent_workflow import search_document_chunks


def test_agent_search_requires_document_id():
    with pytest.raises(ValueError, match="document_id"):
        search_document_chunks("valor", "", search_fn=lambda *_args, **_kwargs: [])


def test_agent_search_forwards_scope_and_limits_top_k():
    captured = {}

    def fake_search(query, *, top_k, document_id):
        captured.update({"query": query, "top_k": top_k, "document_id": document_id})
        return [{"document_id": document_id, "text": "evidência"}]

    rows = search_document_chunks("valor", "doc-1", 99, search_fn=fake_search)
    assert captured == {"query": "valor", "top_k": 10, "document_id": "doc-1"}
    assert rows[0]["document_id"] == "doc-1"


def test_agent_search_rejects_cross_document_result():
    with pytest.raises(RuntimeError, match="outro documento"):
        search_document_chunks(
            "prazo",
            "doc-1",
            search_fn=lambda *_args, **_kwargs: [{"document_id": "doc-2"}],
        )

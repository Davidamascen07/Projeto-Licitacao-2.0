"""Núcleo único de recuperação usado por consulta e extração em lote."""

from __future__ import annotations

from typing import Any, Callable

from .evidence_bundle import expand_evidence_bundle
from .retrieval import detect_deadline_subtype, detect_query_intent, hybrid_search
from .vector_store import get_chunks


def retrieve_evidence(
    query: str,
    document_id: str,
    *,
    top_k: int = 3,
    search_fn: Callable[..., list[dict[str, Any]]] = hybrid_search,
    chunks_fn: Callable[[str | None], list[dict[str, Any]]] = get_chunks,
    expansion_fn: Callable[..., tuple[list[dict[str, Any]], dict[str, Any]]] = expand_evidence_bundle,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Executa busca, reranking e expansão de seção com isolamento obrigatório."""
    document_id = str(document_id or "").strip()
    if not document_id:
        raise ValueError("document_id é obrigatório para recuperar evidências.")
    timing: dict[str, Any] = {}
    try:
        sources = search_fn(query, top_k=top_k, document_id=document_id, timing=timing)
    except TypeError as exc:
        if "timing" not in str(exc):
            raise
        sources = search_fn(query, top_k=top_k, document_id=document_id)
    if any(source.get("document_id") != document_id for source in sources):
        raise RuntimeError("Falha de isolamento: a busca retornou outro edital.")
    intent = str(timing.get("query_intent") or detect_query_intent(query))
    deadline_subtype = detect_deadline_subtype(query) if intent == "prazo" else None
    sources, expansion = expansion_fn(
        intent=intent,
        document_id=document_id,
        base_sources=sources,
        deadline_subtype=deadline_subtype,
        chunks_fn=chunks_fn,
    )
    if any(source.get("document_id") != document_id for source in sources):
        raise RuntimeError("Falha de isolamento: o pacote contém outro edital.")
    return sources, {
        **timing,
        **expansion,
        "query_intent": intent,
        "deadline_subtype": deadline_subtype,
    }

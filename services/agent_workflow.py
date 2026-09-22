from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

from .config import get_llm
from .retrieval import hybrid_search as search


def search_document_chunks(
    query: str,
    document_id: str,
    top_k: int = 3,
    *,
    search_fn: Callable[..., list[dict[str, Any]]] = search,
) -> list[dict[str, Any]]:
    """Ferramenta tipada que impede busca sem escopo e mistura entre documentos."""
    if not str(document_id or "").strip():
        raise ValueError("document_id é obrigatório para a ferramenta de busca.")
    rows = search_fn(query, top_k=max(1, min(int(top_k), 10)), document_id=document_id)
    if any(row.get("document_id") != document_id for row in rows):
        raise RuntimeError("A busca retornou conteúdo de outro documento.")
    return rows


def build_function_agent(
    document_id: str,
    *,
    llm: Any | None = None,
    search_fn: Callable[..., list[dict[str, Any]]] = search,
) -> Any:
    """Cria o FunctionAgent real declarado na metodologia, isolado por edital."""
    if not str(document_id or "").strip():
        raise ValueError("document_id é obrigatório para criar o agente.")
    from llama_index.core.agent.workflow import FunctionAgent

    def buscar_trechos(query: str, top_k: int = 3) -> str:
        """Busca trechos no edital selecionado e devolve páginas e evidências literais."""
        rows = search_document_chunks(query, document_id, top_k, search_fn=search_fn)
        payload = [
            {
                "chunk_id": row.get("chunk_id"),
                "document_id": row.get("document_id"),
                "filename": row.get("filename"),
                "page_start": row.get("page_start"),
                "page_end": row.get("page_end"),
                "text": str(row.get("text") or "")[:1800],
                "retrieval_score": row.get("retrieval_score"),
            }
            for row in rows
        ]
        return json.dumps(payload, ensure_ascii=False)

    return FunctionAgent(
        name="analista_edital",
        description="Analisa exclusivamente o edital selecionado usando busca semântica com evidências.",
        llm=llm or get_llm(),
        tools=[buscar_trechos],
        system_prompt=(
            "Você analisa um único edital. Sempre use buscar_trechos antes de responder. "
            "Não use conhecimento externo, não invente dados e cite arquivo, página e trecho literal. "
            "Se não houver evidência suficiente, declare que a informação não foi encontrada."
        ),
    )


async def arun_function_agent_query(
    query: str,
    document_id: str,
    *,
    llm: Any | None = None,
    search_fn: Callable[..., list[dict[str, Any]]] = search,
) -> str:
    agent = build_function_agent(document_id, llm=llm, search_fn=search_fn)
    result = await agent.run(user_msg=query)
    return str(result)


def run_function_agent_query(
    query: str,
    document_id: str,
    *,
    llm: Any | None = None,
    search_fn: Callable[..., list[dict[str, Any]]] = search,
) -> str:
    return asyncio.run(arun_function_agent_query(query, document_id, llm=llm, search_fn=search_fn))

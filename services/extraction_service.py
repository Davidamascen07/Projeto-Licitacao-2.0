from __future__ import annotations

import concurrent.futures
import json
import re
import time
from typing import Any, Callable

from .agent_service import (
    _confidential_value_from_sources,
    _deadline_items_from_sources,
    _deterministic_habilitation_items,
    _estimated_value_from_sources,
    _modality_summary_from_sources,
    _object_summary_from_sources,
    _relevant_excerpt,
    _scoped_estimated_value_from_sources,
)
from .evidence import validate_evidence
from .deadline_ontology import proposal_validity_from_sources
from .field_parsers import (
    criterion_from_sources,
    generic_habilitation_from_sources,
    organization_from_sources,
    uf_from_sources,
)
from .llm_utils import complete_with_metrics
from .retrieval import CADASTRAL_INTENTS, detect_query_intent, hybrid_search as search
from .retrieval_pipeline import retrieve_evidence
from .rag_diagnostics import diagnostic_summary
from .decision_taxonomy import FIELD_CONFIDENTIAL, FIELD_VARIABLE_BY_ITEM, FOUND
from .execution_ontology import execution_answer, execution_candidate
from .value_ontology import (
    CONFIDENTIAL_VALUE,
    VARIABLE_VALUE,
    estimated_value_candidate,
    value_answer,
)
from .vector_store import get_chunks, get_preamble_chunks

NOT_FOUND_MSG = "Informação não encontrada nos trechos disponíveis."
MAX_SOURCE_CHARS = 1200
DEFAULT_TOP_K = 3
MAX_WORKERS = 6
MAX_SOURCES_PER_FIELD = 5
BATCH_CONTEXT_SOURCES_PER_FIELD = 3
BATCH_EXCERPT_CHARS = 520

FIELD_QUESTIONS = {
    "objeto": "Qual é o objeto da licitação?",
    "modalidade": "Qual é a modalidade da licitação?",
    "valor_estimado": "Qual é o valor estimado ou valor máximo aceitável da licitação?",
    "prazo_entrega_proposta": "Qual é o prazo de validade da proposta?",
    "orgao_responsavel": "Qual é o órgão ou entidade responsável pela licitação?",
    "uf": "Em qual UF está localizado o órgão ou será executado o objeto?",
    "criterio_julgamento": "Qual é o critério de julgamento das propostas?",
    "prazo_execucao": "Qual é o prazo de execução do contrato ou objeto?",
    "requisitos_habilitacao": "Quais são os principais requisitos de habilitação?",
}


def _truncate(text: str, question: str = "", max_chars: int = MAX_SOURCE_CHARS) -> str:
    from .retrieval import detect_query_intent

    return _relevant_excerpt(text, detect_query_intent(question), max_chars)


def _build_field_prompt(question: str, sources: list[dict[str, Any]]) -> str:
    context = "\n\n".join(
        f"[chunk_id={source['chunk_id']}]\n{_truncate(source['text'], question)}" for source in sources
    ) or "(nenhum trecho recuperado)"
    return f"""Responda somente com base no contexto abaixo.

Contexto:
{context}

Pergunta: {question}

Retorne exclusivamente JSON válido:
{{"value": "resposta objetiva ou {NOT_FOUND_MSG}", "source_chunk_id": "id do chunk ou vazio", "evidence_text": "trecho literal curto ou vazio"}}

Não informe arquivo, página ou confiança. Esses dados são validados pelo sistema. Não invente valores.
"""


def _parse_field_response(raw_text: str) -> dict[str, str]:
    fallback = {"value": NOT_FOUND_MSG, "source_chunk_id": "", "evidence_text": ""}
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if not match:
        return fallback
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return fallback
    return {
        "value": str(data.get("value") or NOT_FOUND_MSG),
        "source_chunk_id": str(data.get("source_chunk_id") or ""),
        "evidence_text": str(data.get("evidence_text") or ""),
    }


def _sources_for_document(
    question: str,
    document_id: str,
    top_k: int,
    search_fn: Callable[..., list[dict[str, Any]]] = search,
    preamble_fn: Callable[..., list[dict[str, Any]]] = get_preamble_chunks,
) -> list[dict[str, Any]]:
    sources, _metrics = _sources_and_metrics_for_document(
        question,
        document_id,
        top_k,
        search_fn,
        preamble_fn,
    )
    return sources


def _sources_and_metrics_for_document(
    question: str,
    document_id: str,
    top_k: int,
    search_fn: Callable[..., list[dict[str, Any]]] = search,
    preamble_fn: Callable[..., list[dict[str, Any]]] = get_preamble_chunks,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    semantic, metrics = retrieve_evidence(
        question,
        document_id,
        top_k=top_k,
        search_fn=search_fn,
        chunks_fn=get_chunks,
    )
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    intent = detect_query_intent(question)
    preamble = (
        preamble_fn(document_id=document_id)
        if intent in CADASTRAL_INTENTS
        else []
    )
    for source in preamble + semantic:
        if source.get("document_id") != document_id:
            raise RuntimeError("Falha de isolamento na extração estruturada.")
        if source["chunk_id"] not in seen:
            combined.append(source)
            seen.add(source["chunk_id"])
    selected = combined[:MAX_SOURCES_PER_FIELD]
    return selected, {
        **metrics,
        "preamble_chunks": len(preamble),
        "semantic_chunks": len(semantic),
        "selected_chunks": len(selected),
    }


def extract_single_field(
    field_name: str,
    question: str,
    document_id: str,
    top_k: int = DEFAULT_TOP_K,
    llm_client: Any | None = None,
    search_fn: Callable[..., list[dict[str, Any]]] = search,
    preamble_fn: Callable[..., list[dict[str, Any]]] = get_preamble_chunks,
) -> dict[str, Any]:
    started = time.perf_counter()
    retrieval_started = time.perf_counter()
    sources = _sources_for_document(question, document_id, top_k, search_fn, preamble_fn)
    retrieval_ms = round((time.perf_counter() - retrieval_started) * 1000, 1)
    completion = complete_with_metrics(_build_field_prompt(question, sources), llm_client=llm_client)
    parsed = _parse_field_response(completion["text"])
    evidence = validate_evidence(
        evidence_text=parsed["evidence_text"],
        source_chunk_id=parsed["source_chunk_id"] or None,
        retrieved_sources=sources,
        selected_document_id=document_id,
        value=parsed["value"],
        field_name=field_name,
    )
    answered = parsed["value"] != NOT_FOUND_MSG
    return {
        "field": field_name,
        "value": parsed["value"],
        "answered": answered,
        "evidence": evidence,
        "sources": sources,
        "metrics": {
            "retrieval_ms": retrieval_ms,
            "llm_ms": completion["llm_ms"],
            "total_ms": round((time.perf_counter() - started) * 1000, 1),
        },
        "usage": completion["usage"],
    }


def extract_all_fields(
    document_id: str,
    top_k: int = DEFAULT_TOP_K,
    llm_client: Any | None = None,
    search_fn: Callable[..., list[dict[str, Any]]] = search,
    preamble_fn: Callable[..., list[dict[str, Any]]] = get_preamble_chunks,
) -> dict[str, dict[str, Any]]:
    if not document_id:
        raise ValueError("document_id é obrigatório para extração estruturada.")
    results: dict[str, dict[str, Any]] = {}
    workers = 1 if llm_client is not None else min(MAX_WORKERS, len(FIELD_QUESTIONS))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                extract_single_field,
                field,
                question,
                document_id,
                top_k,
                llm_client,
                search_fn,
                preamble_fn,
            ): field
            for field, question in FIELD_QUESTIONS.items()
        }
        for future in concurrent.futures.as_completed(futures):
            field = futures[future]
            try:
                results[field] = future.result()
            except Exception as exc:
                results[field] = {"field": field, "value": NOT_FOUND_MSG, "answered": False, "error": str(exc)}
    return results


def _allocate_usage(usage: dict[str, Any], count: int, position: int) -> dict[str, Any]:
    allocated = dict(usage)
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            allocated[key] = value // count + (1 if position < value % count else 0)
    cost = usage.get("estimated_cost")
    if isinstance(cost, (int, float)):
        allocated["estimated_cost"] = round(float(cost) / count, 8)
    allocated["shared_call_fields"] = count
    return allocated


def _deterministic_field_candidate(
    field: str,
    sources: list[dict[str, Any]],
    document_id: str,
) -> dict[str, str]:
    def match_candidate(pattern: str, value: str | Callable[[re.Match[str]], str]):
        compiled = re.compile(pattern, re.IGNORECASE)
        for source in sources:
            match = compiled.search(str(source.get("text") or ""))
            if not match:
                continue
            literal = " ".join(match.group(1).split()).strip()
            resolved = value(match) if callable(value) else value
            return {
                "value": resolved,
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": literal,
            }
        return None

    if field == "objeto":
        object_summary = _object_summary_from_sources(sources)
        if object_summary:
            source, answer, literal = object_summary
            return {
                "value": answer,
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": literal,
            }
        candidate = match_candidate(
            r"(Constitui\s+objeto\s+da\s+presente\s+licita[çc][ãa]o[^.]{40,900}\.)",
            lambda match: " ".join(match.group(1).split()).strip(),
        )
        if candidate:
            return candidate
    elif field == "modalidade":
        modality = _modality_summary_from_sources(sources)
        if modality:
            source, answer, literal = modality
            return {
                "value": answer,
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": literal,
            }
    elif field == "valor_estimado":
        confidential = _confidential_value_from_sources(sources)
        if confidential:
            source, literal = confidential
            return {
                "value": "SIGILOSO",
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": literal,
            }
        scoped = _scoped_estimated_value_from_sources(sources)
        if scoped:
            source, answer, literal = scoped
            return {
                "value": answer,
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": literal,
            }
        typed_value = estimated_value_candidate(sources)
        if typed_value:
            internal_status = (
                FIELD_CONFIDENTIAL
                if typed_value["value_type"] == CONFIDENTIAL_VALUE
                else FIELD_VARIABLE_BY_ITEM
                if typed_value["value_type"] == VARIABLE_VALUE
                else FOUND
            )
            return {
                "value": value_answer(typed_value),
                "source_chunk_id": typed_value["source_chunk_id"],
                "evidence_text": typed_value["evidence_text"],
                "internal_status": internal_status,
                "final_status": "CONTEXT_DEPENDENT" if internal_status == FIELD_VARIABLE_BY_ITEM else "FOUND",
                "value_type": typed_value["value_type"],
            }
        estimated = _estimated_value_from_sources(sources)
        if estimated:
            source, answer, literal = estimated
            return {
                "value": answer,
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": literal,
            }
    elif field == "prazo_entrega_proposta":
        proposal_validity = proposal_validity_from_sources(sources)
        if proposal_validity:
            source, deadline = proposal_validity
            return {
                "value": f"{deadline['duration']} {deadline['unit']}",
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": deadline["evidence_text"],
                "normalized": deadline,
            }
    elif field == "orgao_responsavel":
        organization = organization_from_sources(sources)
        if organization:
            source, answer, literal = organization
            return {
                "value": answer,
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": literal,
            }
    elif field == "uf":
        uf = uf_from_sources(sources)
        if uf:
            source, answer, literal = uf
            return {
                "value": answer,
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": literal,
            }
    elif field == "criterio_julgamento":
        criterion = criterion_from_sources(sources)
        if criterion:
            source, answer, literal = criterion
            return {
                "value": answer,
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": literal,
            }
    elif field == "prazo_execucao":
        typed_execution = execution_candidate(sources, include_delivery=False)
        if typed_execution:
            return {
                "value": execution_answer(typed_execution),
                "source_chunk_id": typed_execution["source_chunk_id"],
                "evidence_text": typed_execution["evidence_text"],
                "internal_status": FOUND,
                "final_status": "FOUND",
                "execution_type": typed_execution["execution_type"],
                "deadline_type": typed_execution["deadline_type"],
            }
        _response, items, _rejected = _deadline_items_from_sources(
            sources,
            document_id,
            "prazo_execucao",
        )
        if items:
            item = items[0]
            return {
                "value": item["summary"],
                "source_chunk_id": str(item["source_chunk_id"]),
                "evidence_text": item["evidence_text"],
            }
    elif field == "requisitos_habilitacao":
        items = _deterministic_habilitation_items(sources, document_id)
        if items:
            item = items[0]
            return {
                "value": item["summary"],
                "source_chunk_id": str(item["source_chunk_id"]),
                "evidence_text": item["evidence_text"],
            }
        generic = generic_habilitation_from_sources(sources)
        if generic:
            source, answer, literal = generic
            return {
                "value": answer,
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": literal,
            }
    return {
        "value": NOT_FOUND_MSG,
        "source_chunk_id": "",
        "evidence_text": "",
    }


def extract_fields_from_sources(
    field_questions: dict[str, str],
    document_id: str,
    sources: list[dict[str, Any]],
    *,
    llm_client: Any | None = None,
    sources_by_field: dict[str, list[dict[str, Any]]] | None = None,
    retrieval_by_field: dict[str, dict[str, Any]] | None = None,
    include_diagnostics: bool = False,
) -> dict[str, dict[str, Any]]:
    """Extrai vários campos em uma chamada e distribui tokens/custo sem contagem dupla."""
    started = time.perf_counter()
    sources_by_field = sources_by_field or {
        field: sources for field in field_questions
    }
    retrieval_by_field = retrieval_by_field or {}
    context_blocks: list[str] = []
    excerpts_by_field: dict[str, list[dict[str, Any]]] = {}
    for field, question in field_questions.items():
        field_sources = sources_by_field.get(field, [])[:BATCH_CONTEXT_SOURCES_PER_FIELD]
        excerpt_items = [
            {
                "chunk_id": str(source.get("chunk_id") or ""),
                "pages": [source.get("page_start"), source.get("page_end")],
                "text": _truncate(str(source.get("text") or ""), question, BATCH_EXCERPT_CHARS),
            }
            for source in field_sources
        ]
        excerpts_by_field[field] = excerpt_items
        excerpts = "\n\n".join(
            f"[chunk_id={item['chunk_id']}]\n{item['text']}" for item in excerpt_items
        ) or "(nenhum trecho recuperado)"
        context_blocks.append(f"[CAMPO {field}]\n{excerpts}")
    context = "\n\n".join(context_blocks)
    schema = {
        field: {
            "value": f"resposta objetiva ou {NOT_FOUND_MSG}",
            "source_chunk_id": "id do chunk ou vazio",
            "evidence_text": "trecho literal curto ou vazio",
        }
        for field in field_questions
    }
    questions = "\n".join(f"- {field}: {question}" for field, question in field_questions.items())
    prompt = f"""Responda somente com base no contexto abaixo.

Contexto:
{context}

Campos:
{questions}

Retorne exclusivamente um objeto JSON válido com este formato:
{json.dumps(schema, ensure_ascii=False)}

Não informe arquivo, página ou confiança. Não invente valores. Cada evidence_text deve ser um trecho literal do contexto.
"""
    completion = complete_with_metrics(prompt, llm_client=llm_client)
    match = re.search(r"\{.*\}", completion["text"], re.DOTALL)
    parsed: dict[str, Any] = {}
    if match:
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            parsed = {}
    output: dict[str, dict[str, Any]] = {}
    fields = list(field_questions)
    for position, field in enumerate(fields):
        field_sources = sources_by_field.get(field, [])
        item = parsed.get(field) if isinstance(parsed.get(field), dict) else {}
        llm_candidate_extracted = bool(item and item.get("evidence_text"))
        deterministic_fallback_used = False
        if not item or not item.get("evidence_text"):
            item = _deterministic_field_candidate(field, field_sources, document_id)
            deterministic_fallback_used = bool(item.get("evidence_text"))
        value = str(item.get("value") or NOT_FOUND_MSG)
        evidence = validate_evidence(
            evidence_text=str(item.get("evidence_text") or ""),
            source_chunk_id=str(item.get("source_chunk_id") or "") or None,
            retrieved_sources=field_sources,
            selected_document_id=document_id,
            value=value,
            field_name=field,
        )
        if not evidence["evidence_valid"]:
            fallback = _deterministic_field_candidate(field, field_sources, document_id)
            deterministic_fallback_used = bool(fallback.get("evidence_text"))
            item = fallback
            value = str(fallback.get("value") or NOT_FOUND_MSG)
            evidence = validate_evidence(
                evidence_text=str(fallback.get("evidence_text") or ""),
                source_chunk_id=str(fallback.get("source_chunk_id") or "") or None,
                retrieved_sources=field_sources,
                selected_document_id=document_id,
                value=value,
                field_name=field,
            )
        answered = value != NOT_FOUND_MSG and evidence["evidence_valid"]
        if not answered:
            value = NOT_FOUND_MSG
        internal_status = str(item.get("internal_status") or (FOUND if answered else "UNRESOLVED"))
        final_status = str(item.get("final_status") or ("FOUND" if answered else "NOT_FOUND"))
        output[field] = {
            "field": field,
            "value": value,
            "answered": answered,
            "final_status": final_status,
            "internal_status": internal_status,
            "evidence": evidence,
            "sources": field_sources,
            "metrics": {
                "retrieval_ms": 0.0,
                "llm_ms": completion["llm_ms"],
                "total_ms": round((time.perf_counter() - started) * 1000, 1),
                "shared_call_fields": len(fields),
            },
            "usage": _allocate_usage(completion["usage"], len(fields), position),
        }
        if include_diagnostics:
            output[field]["diagnostics"] = diagnostic_summary(
                sources=field_sources,
                retrieval=retrieval_by_field.get(field, {}),
                context_excerpts=excerpts_by_field.get(field, []),
                llm_candidate_extracted=llm_candidate_extracted,
                deterministic_fallback_used=deterministic_fallback_used,
                evidence=evidence,
                answered=answered,
            )
    return output


def extract_multiple_fields(
    field_questions: dict[str, str],
    document_id: str,
    *,
    top_k: int = DEFAULT_TOP_K,
    llm_client: Any | None = None,
    search_fn: Callable[..., list[dict[str, Any]]] = search,
    preamble_fn: Callable[..., list[dict[str, Any]]] = get_preamble_chunks,
    include_diagnostics: bool = False,
) -> dict[str, dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    sources_by_field: dict[str, list[dict[str, Any]]] = {}
    retrieval_by_field: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for field, question in field_questions.items():
        field_sources, retrieval_metrics = _sources_and_metrics_for_document(
            question, document_id, top_k, search_fn, preamble_fn
        )
        sources_by_field[field] = field_sources
        retrieval_by_field[field] = retrieval_metrics
        for source in field_sources:
            if source["chunk_id"] not in seen:
                sources.append(source)
                seen.add(source["chunk_id"])
    return extract_fields_from_sources(
        field_questions,
        document_id,
        sources,
        llm_client=llm_client,
        sources_by_field=sources_by_field,
        retrieval_by_field=retrieval_by_field,
        include_diagnostics=include_diagnostics,
    )

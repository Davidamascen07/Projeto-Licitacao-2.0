from __future__ import annotations

import json
import re
import time
from typing import Any

from services.config import PROJECT_ROOT
from services.document_manifest import get_manifest_document, load_manifest
from services.evidence import validate_evidence
from services.extraction_service import FIELD_QUESTIONS, NOT_FOUND_MSG, extract_fields_from_sources
from services.llm_utils import complete_with_metrics


def load_document_pages(document_id: str) -> list[dict[str, Any]]:
    import fitz

    record = get_manifest_document(document_id)
    if record is None:
        raise KeyError(f"Documento ausente no manifesto: {document_id}")
    path = PROJECT_ROOT / record["relative_path"]
    with fitz.open(path) as pdf:
        return [{"page": number + 1, "text": page.get_text("text")} for number, page in enumerate(pdf)]


REGEX_PATTERNS = {
    "modalidade": re.compile(r"\b(pregão(?: eletrônico)?|concorrência|dispensa|inexigibilidade|credenciamento|leilão)\b", re.I),
    "valor_estimado": re.compile(
        r"(?:valor\s+(?:total\s+)?estimado|valor\s+máximo\s+aceitável|orçamento\s+estimado)[^\n]{0,160}?(R\$\s*[\d.]+,\d{2})",
        re.I,
    ),
    "prazo_entrega_proposta": re.compile(
        r"(?:entrega|recebimento|envio)[^\n]{0,180}?(?:propostas?)[^\n]{0,120}?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}(?:\s+(?:às?|até)\s+\d{1,2}:\d{2})?)",
        re.I,
    ),
}


def _regex_field(document_id: str, field_name: str, pages: list[dict[str, Any]]) -> dict[str, Any]:
    started = time.perf_counter()
    pattern = REGEX_PATTERNS[field_name]
    for page in pages:
        match = pattern.search(page["text"])
        if not match:
            continue
        value = match.group(1) if match.lastindex else match.group(0)
        evidence_text = match.group(0)
        chunk = {
            "chunk_id": f"regex-page-{page['page']}",
            "document_id": document_id,
            "filename": get_manifest_document(document_id)["filename"],
            "page_start": page["page"],
            "page_end": page["page"],
            "text": page["text"],
            "retrieval_score": None,
        }
        evidence = validate_evidence(
            evidence_text=evidence_text,
            source_chunk_id=chunk["chunk_id"],
            retrieved_sources=[chunk],
            selected_document_id=document_id,
            value=value,
            field_name=field_name,
        )
        return {
            "field": field_name,
            "value": value,
            "answered": True,
            "evidence": evidence,
            "sources": [chunk],
            "metrics": {"retrieval_ms": 0.0, "llm_ms": 0.0, "total_ms": round((time.perf_counter() - started) * 1000, 1)},
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost": 0.0, "currency": "USD", "pricing_source": "no_llm"},
        }
    return {
        "field": field_name,
        "value": NOT_FOUND_MSG,
        "answered": False,
        "evidence": {"evidence_valid": False, "validation_error": "regex_no_match"},
        "sources": [],
        "metrics": {"retrieval_ms": 0.0, "llm_ms": 0.0, "total_ms": round((time.perf_counter() - started) * 1000, 1)},
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "estimated_cost": 0.0, "currency": "USD", "pricing_source": "no_llm"},
    }


def run_regex_baseline(document_id: str) -> dict[str, dict[str, Any]]:
    pages = load_document_pages(document_id)
    return {field: _regex_field(document_id, field, pages) for field in REGEX_PATTERNS}


def _controlled_context(document_id: str, pages: list[dict[str, Any]], max_chars: int = 12000) -> list[dict[str, Any]]:
    record = get_manifest_document(document_id)
    selected: list[dict[str, Any]] = []
    used = 0
    for page in pages:
        if used >= max_chars:
            break
        text = page["text"][: max_chars - used]
        used += len(text)
        selected.append(
            {
                "chunk_id": f"no-rag-page-{page['page']}",
                "document_id": document_id,
                "filename": record["filename"],
                "page_start": page["page"],
                "page_end": page["page"],
                "text": text,
                "retrieval_score": None,
            }
        )
    return selected


def run_llm_no_retrieval(document_id: str, llm_client: Any | None = None) -> dict[str, dict[str, Any]]:
    pages = load_document_pages(document_id)
    sources = _controlled_context(document_id, pages)
    context = "\n\n".join(f"[chunk_id={source['chunk_id']}]\n{source['text']}" for source in sources)
    results: dict[str, dict[str, Any]] = {}
    for field, question in {key: FIELD_QUESTIONS[key] for key in REGEX_PATTERNS}.items():
        started = time.perf_counter()
        prompt = f"""Use somente o contexto controlado abaixo. Responda exclusivamente em JSON.
{{"value":"valor ou {NOT_FOUND_MSG}","source_chunk_id":"id","evidence_text":"trecho literal"}}

Pergunta: {question}

Contexto:
{context}
"""
        completion = complete_with_metrics(prompt, llm_client=llm_client)
        match = re.search(r"\{.*\}", completion["text"], re.DOTALL)
        data: dict[str, Any] = {}
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = {}
        value = str(data.get("value") or NOT_FOUND_MSG)
        evidence = validate_evidence(
            evidence_text=str(data.get("evidence_text") or ""),
            source_chunk_id=data.get("source_chunk_id"),
            retrieved_sources=sources,
            selected_document_id=document_id,
            value=value,
            field_name=field,
        )
        results[field] = {
            "field": field,
            "value": value,
            "answered": value != NOT_FOUND_MSG,
            "evidence": evidence,
            "sources": sources,
            "metrics": {"retrieval_ms": 0.0, "llm_ms": completion["llm_ms"], "total_ms": round((time.perf_counter() - started) * 1000, 1)},
            "usage": completion["usage"],
            "context_policy": "pages from start of document, truncated at 12000 characters",
        }
    return results


def run_llm_no_retrieval_batched(document_id: str, llm_client: Any | None = None) -> dict[str, dict[str, Any]]:
    pages = load_document_pages(document_id)
    sources = _controlled_context(document_id, pages, max_chars=6000)
    results = extract_fields_from_sources(
        {key: FIELD_QUESTIONS[key] for key in REGEX_PATTERNS},
        document_id,
        sources,
        llm_client=llm_client,
    )
    for result in results.values():
        result["context_policy"] = "pages from start of document, truncated at 6000 characters; one shared call"
    return results

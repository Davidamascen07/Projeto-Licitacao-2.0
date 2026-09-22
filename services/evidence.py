"""Validação determinística das evidências retornadas pelo modelo."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .document_manifest import get_manifest_document, load_manifest
from .scope_validation import missing_critical_qualifiers


def normalize_literal(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def literal_is_present(needle: str, haystack: str) -> bool:
    normalized_needle = normalize_literal(needle)
    return bool(normalized_needle) and normalized_needle in normalize_literal(haystack)


def normalization_is_valid(field_name: str, value: str | None) -> bool:
    if not value:
        return False
    normalized = normalize_literal(value)
    if field_name == "valor_estimado":
        return bool(
            re.search(r"(?:r\$\s*)?\d[\d.]*,\d{2}", normalized)
            or any(marker in normalized for marker in ("sigiloso", "não divulgado", "nao divulgado"))
        )
    if field_name == "modalidade":
        return any(
            modality in normalized
            for modality in ("pregão", "concorrência", "dispensa", "inexigibilidade", "credenciamento", "leilão")
        )
    if field_name == "prazo_entrega_proposta":
        return bool(
            re.search(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", normalized)
            or re.search(r"\b\d{1,2}\s+(?:dia|dias|hora|horas)\b", normalized)
        )
    return True


def validate_evidence(
    *,
    evidence_text: str,
    source_chunk_id: str | None,
    retrieved_sources: list[dict[str, Any]],
    selected_document_id: str,
    value: str | None = None,
    field_name: str = "",
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = {
        "document_id": selected_document_id,
        "chunk_id": source_chunk_id,
        "filename": None,
        "pages": None,
        "text": evidence_text or "",
        "retrieval_score": None,
        "evidence_valid": False,
        "validation_error": None,
        "exact_value_found": False,
        "normalization_valid": normalization_is_valid(field_name, value),
    }
    candidates = [source for source in retrieved_sources if source.get("document_id") == selected_document_id]
    if len(candidates) != len(retrieved_sources):
        result["validation_error"] = "retrieved_context_contains_other_document"
        return result
    source = next((item for item in candidates if item.get("chunk_id") == source_chunk_id), None)
    if source is None and evidence_text:
        matching = [item for item in candidates if literal_is_present(evidence_text, item.get("text", ""))]
        if len(matching) == 1:
            source = matching[0]
            result["chunk_id"] = source.get("chunk_id")
    if source is None:
        result["validation_error"] = "chunk_not_in_retrieved_context"
        return result

    current_manifest = manifest or load_manifest()
    document = get_manifest_document(selected_document_id, current_manifest)
    if document is None:
        result["validation_error"] = "document_not_in_manifest"
        return result
    path = PROJECT_ROOT / document.get("relative_path", "")
    if not path.is_file():
        result["validation_error"] = "source_file_not_found"
        return result
    page_start = int(source.get("page_start", 0))
    page_end = int(source.get("page_end", 0))
    page_count = int(document.get("page_count") or 0)
    if page_start < 1 or page_end < page_start or (page_count and page_end > page_count):
        result["validation_error"] = "page_out_of_document_range"
        return result
    if not literal_is_present(evidence_text, source.get("text", "")):
        result["validation_error"] = "evidence_not_found_in_retrieved_context"
        return result
    missing_qualifiers = missing_critical_qualifiers(evidence_text, value or "")
    if missing_qualifiers:
        result["validation_error"] = "critical_scope_qualifier_missing"
        result["missing_qualifiers"] = missing_qualifiers
        return result

    result.update(
        {
            "filename": source.get("filename"),
            "pages": str(page_start) if page_start == page_end else f"{page_start}-{page_end}",
            "retrieval_score": source.get("retrieval_score"),
            "evidence_valid": True,
            "validation_error": None,
            "exact_value_found": literal_is_present(value or "", source.get("text", "")),
        }
    )
    return result

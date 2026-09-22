"""Vocabulário e helpers de diagnóstico por etapa do RAG."""

from __future__ import annotations

from typing import Any

RETRIEVAL_FAILURE = "RETRIEVAL_FAILURE"
RANKING_FAILURE = "RANKING_FAILURE"
SECTION_EXPANSION_FAILURE = "SECTION_EXPANSION_FAILURE"
CONTEXT_TRUNCATION = "CONTEXT_TRUNCATION"
LLM_EXTRACTION_FAILURE = "LLM_EXTRACTION_FAILURE"
EVIDENCE_VALIDATION_FAILURE = "EVIDENCE_VALIDATION_FAILURE"
FIELD_NORMALIZATION_FAILURE = "FIELD_NORMALIZATION_FAILURE"
ACTUALLY_NOT_PRESENT = "ACTUALLY_NOT_PRESENT"

FAILURE_STAGES = {
    RETRIEVAL_FAILURE,
    RANKING_FAILURE,
    SECTION_EXPANSION_FAILURE,
    CONTEXT_TRUNCATION,
    LLM_EXTRACTION_FAILURE,
    EVIDENCE_VALIDATION_FAILURE,
    FIELD_NORMALIZATION_FAILURE,
    ACTUALLY_NOT_PRESENT,
}


def classify_extraction_failure(
    *,
    sources: list[dict[str, Any]],
    llm_candidate_extracted: bool,
    evidence: dict[str, Any],
    answered: bool,
) -> tuple[str | None, str | None]:
    """Classificação conservadora; golden audit can refine ranking/truncation."""
    if answered:
        return None, None
    if not sources:
        return RETRIEVAL_FAILURE, "RETRIEVAL_MISS"
    if llm_candidate_extracted and not evidence.get("normalization_valid", True):
        return FIELD_NORMALIZATION_FAILURE, "CANDIDATE_REJECTED"
    if llm_candidate_extracted and not evidence.get("evidence_valid"):
        return EVIDENCE_VALIDATION_FAILURE, "VALIDATION_FAILED"
    return LLM_EXTRACTION_FAILURE, "CANDIDATE_REJECTED"


def diagnostic_summary(
    *,
    sources: list[dict[str, Any]],
    retrieval: dict[str, Any],
    context_excerpts: list[dict[str, Any]],
    llm_candidate_extracted: bool,
    deterministic_fallback_used: bool,
    evidence: dict[str, Any],
    answered: bool,
) -> dict[str, Any]:
    failure_stage, not_found_reason = classify_extraction_failure(
        sources=sources,
        llm_candidate_extracted=llm_candidate_extracted,
        evidence=evidence,
        answered=answered,
    )
    return {
        "retrieval": {
            **retrieval,
            "retrieved_chunk_ids": [str(source.get("chunk_id") or "") for source in sources],
            "retrieved_pages": [
                [source.get("page_start"), source.get("page_end")] for source in sources
            ],
        },
        "section_expansion": {
            "expanded": bool(retrieval.get("section_expansion_ms")),
            "evidence_bundle_chunks": retrieval.get("evidence_bundle_chunks", len(sources)),
            "adjacent_chunks_considered": retrieval.get("adjacent_chunks_considered", 0),
        },
        "context": {
            "source_limit": 3,
            "chars_per_source": 520,
            "excerpts": context_excerpts,
        },
        "llm": {"candidate_extracted": llm_candidate_extracted},
        "fallback": {"deterministic_used": deterministic_fallback_used},
        "validation": {
            "validated": bool(evidence.get("evidence_valid")),
            "validation_reason": evidence.get("validation_error"),
            "normalization_valid": evidence.get("normalization_valid"),
        },
        "failure_stage": failure_stage,
        "not_found_reason": not_found_reason,
    }

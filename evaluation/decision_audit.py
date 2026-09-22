"""Auditoria determinística das 171 decisões cadastrais do corpus."""

from __future__ import annotations

import argparse
import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from evaluation.golden_regression import aggregate_recall, evaluate_retriever_entry, load_golden
from services.decision_taxonomy import (
    ACTUALLY_ABSENT,
    DOCUMENT_TEXT_INSUFFICIENT,
    FIELD_CONFIDENTIAL,
    FIELD_PRESENT_CONTEXT_TRUNCATION,
    FIELD_PRESENT_IN_ANNEX,
    FIELD_PRESENT_IN_TABLE,
    FIELD_PRESENT_PARSER_MISS,
    FIELD_PRESENT_RANKING_MISS,
    FIELD_PRESENT_RETRIEVAL_MISS,
    FIELD_PRESENT_SECTION_EXPANSION_MISS,
    FIELD_VARIABLE_BY_ITEM,
    FOUND,
    NOT_APPLICABLE,
    UNRESOLVED,
    decision_payload,
)
from services.document_manifest import load_manifest
from services.document_profile import classify_document_profile
from services.evidence import validate_evidence
from services.execution_ontology import delivery_candidate, execution_answer, execution_candidate
from services.extraction_service import (
    BATCH_EXCERPT_CHARS,
    FIELD_QUESTIONS,
    _deterministic_field_candidate,
    _sources_and_metrics_for_document,
    _truncate,
)
from services.pdf_quality import audit_pdf_text
from services.retrieval import annotate_document_structure, hybrid_search, normalize_text
from services.value_ontology import (
    CONFIDENTIAL_VALUE,
    VARIABLE_VALUE,
    estimated_value_candidate,
    value_answer,
)
from services.vector_store import get_chunks, init_vector_store

ROOT = Path(__file__).resolve().parents[1]
VALIDATED_CURRENT_PATH = Path(__file__).with_name("validated_current.json")
DEFAULT_JSON = ROOT / "output" / "decision_audit_2026-08-07.json"
DEFAULT_CSV = ROOT / "output" / "decision_audit_2026-08-07.csv"

_FIELD_MARKERS = {
    "objeto": ("do objeto", "tem por objeto", "constitui objeto", "finalidade"),
    "modalidade": ("pregao", "concorrencia", "credenciamento", "leilao", "dispensa", "inexigibilidade"),
    "valor_estimado": ("valor estimado", "valor total", "valor global", "valor de referencia", "orcamento", "lance minimo", "avaliacao"),
    "prazo_entrega_proposta": ("validade da proposta", "validade das propostas", "proposta valida por"),
    "orgao_responsavel": ("orgao responsavel", "contratante", "credenciante", "prefeitura", "ministerio"),
    "uf": ("estado do", "estado de", "municipio/uf"),
    "criterio_julgamento": ("criterio de julgamento", "menor preco", "maior lance", "maior oferta"),
    "prazo_execucao": ("prazo de execucao", "periodo de execucao", "ordem de servico", "sob demanda", "prazo de entrega"),
    "requisitos_habilitacao": ("da habilitacao", "documentos de habilitacao", "habilitacao juridica", "regularidade fiscal"),
}


def load_validated_current(path: Path = VALIDATED_CURRENT_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    count = sum(len(row.get("found_fields", [])) for row in payload.get("documents", []))
    if count != payload.get("consolidated_found"):
        raise ValueError("validated_current diverge da contagem consolidada.")
    return payload


def _validated_pairs(payload: dict[str, Any], manifest: dict[str, Any]) -> set[tuple[str, str]]:
    ids = {row["filename"]: row["document_id"] for row in manifest["documents"]}
    return {
        (ids[row["document"]], field)
        for row in payload["documents"]
        for field in row["found_fields"]
    }


def _candidate_for_field(field: str, sources: list[dict[str, Any]], document_id: str) -> dict[str, Any] | None:
    if field == "valor_estimado":
        candidate = estimated_value_candidate(sources)
        if candidate:
            return {
                "value": value_answer(candidate),
                "source_chunk_id": candidate["source_chunk_id"],
                "evidence_text": candidate["evidence_text"],
                "value_type": candidate["value_type"],
            }
    if field == "prazo_execucao":
        candidate = execution_candidate(sources, include_delivery=False)
        if candidate:
            return {
                "value": execution_answer(candidate),
                "source_chunk_id": candidate["source_chunk_id"],
                "evidence_text": candidate["evidence_text"],
                "execution_type": candidate["execution_type"],
                "deadline_type": candidate["deadline_type"],
            }
    candidate = _deterministic_field_candidate(field, sources, document_id)
    return candidate if candidate.get("evidence_text") else None


def _formal_heading(field: str, chunks: list[dict[str, Any]]) -> str | None:
    expected = {
        "objeto": {"objeto"},
        "valor_estimado": {"recursos_financeiros", "preco"},
        "criterio_julgamento": {"criterio_julgamento"},
        "prazo_execucao": {"execucao", "regime_execucao", "prazo_entrega"},
        "requisitos_habilitacao": {"habilitacao"},
    }.get(field, set())
    for chunk in chunks:
        for heading in chunk.get("section_headings", []):
            if heading.get("section_type") in expected and not heading.get("is_toc"):
                return str(heading.get("section_title") or "") or None
    return None


def _stage_for_candidate(
    candidate: dict[str, Any],
    ranked: list[dict[str, Any]],
    production_sources: list[dict[str, Any]],
    question: str,
) -> str:
    chunk_id = str(candidate.get("source_chunk_id") or "")
    ranked_ids = [str(row.get("chunk_id") or "") for row in ranked]
    production_ids = [str(row.get("chunk_id") or "") for row in production_sources]
    if chunk_id not in ranked_ids:
        return FIELD_PRESENT_RETRIEVAL_MISS
    if ranked_ids.index(chunk_id) >= 3:
        return FIELD_PRESENT_RANKING_MISS
    if chunk_id not in production_ids:
        return FIELD_PRESENT_SECTION_EXPANSION_MISS
    source = next(row for row in production_sources if str(row.get("chunk_id") or "") == chunk_id)
    excerpt = _truncate(str(source.get("text") or ""), question, BATCH_EXCERPT_CHARS)
    if normalize_text(candidate.get("evidence_text", "")) not in normalize_text(excerpt):
        return FIELD_PRESENT_CONTEXT_TRUNCATION
    return FIELD_PRESENT_PARSER_MISS


def _absence_decision(
    field: str,
    chunks: list[dict[str, Any]],
    profile: dict[str, Any],
    quality: dict[str, Any],
) -> tuple[str, str]:
    if quality.get("ocr_required") or not quality.get("text_layer_present"):
        return DOCUMENT_TEXT_INSUFFICIENT, "A camada textual não permite auditoria estrutural segura."
    if field == "prazo_execucao" and profile["document_type"] == "edital_leilao":
        return NOT_APPLICABLE, "Leilão de alienação não possui execução contratual do objeto a contratar."
    if field == "prazo_execucao" and profile["document_type"] == "edital_credenciamento":
        return NOT_APPLICABLE, "O credenciamento não estabelece prazo único de execução após a varredura integral."
    if field == "criterio_julgamento" and profile["document_type"] == "edital_credenciamento":
        return NOT_APPLICABLE, "Credenciamento sem competição não possui critério de julgamento de propostas aplicável."
    if field == "prazo_entrega_proposta" and profile["document_type"] == "edital_leilao":
        return NOT_APPLICABLE, "O documento disciplina lances de leilão, não validade de proposta comercial."
    text = normalize_text(" ".join(str(chunk.get("text") or "") for chunk in chunks))
    marker_found = any(marker in text for marker in _FIELD_MARKERS[field])
    if field == "valor_estimado" and profile.get("table_heavy"):
        return FIELD_PRESENT_IN_TABLE, "Há valores em tabela/quadro, mas nenhum valor global seguro foi tipado."
    if marker_found and profile.get("has_annex") and field in {"valor_estimado", "prazo_execucao"}:
        return FIELD_PRESENT_IN_ANNEX, "Há referência ao campo em anexo, sem evidência suficiente no recorte principal."
    if marker_found:
        return UNRESOLVED, "Há vocabulário relacionado, mas não há candidato seguro com sujeito, valor e escopo completos."
    return ACTUALLY_ABSENT, "Nenhuma disposição do campo foi encontrada após varredura integral da camada textual."


def run_audit(*, include_pdf_quality: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    init_vector_store(sync_uploads=False)
    manifest = load_manifest()
    current = load_validated_current()
    consolidated = _validated_pairs(current, manifest)
    golden = load_golden()
    golden_pairs = {(row["document_id"], row["field"]) for row in golden["entries"]}
    decisions: list[dict[str, Any]] = []
    local_retrieval_ms = 0.0

    for document in manifest["documents"]:
        if document.get("excluded") or document.get("status") != "indexed":
            continue
        document_id = document["document_id"]
        chunks = annotate_document_structure(get_chunks(document_id))
        profile = classify_document_profile(chunks)
        quality = (
            audit_pdf_text(ROOT / document["relative_path"])
            if include_pdf_quality
            else {"classification": "NOT_RUN", "text_layer_present": True, "ocr_required": False}
        )
        for field, question in FIELD_QUESTIONS.items():
            base = {
                "document": document["filename"],
                "document_id": document_id,
                "field": field,
                "intent": field,
                "baseline_origin": "GOLDEN" if (document_id, field) in golden_pairs else "CONSOLIDATED",
                "document_profile": profile,
                "document_quality": quality["classification"],
            }
            if (document_id, field) in consolidated:
                semantic_details: dict[str, Any] = {}
                if field == "prazo_execucao":
                    typed_deadline = execution_candidate(chunks, include_delivery=False)
                    if typed_deadline is None:
                        typed_deadline = delivery_candidate(chunks)
                    if typed_deadline:
                        semantic_details = {
                            "deadline_type": typed_deadline["deadline_type"],
                            "execution_type": typed_deadline["execution_type"],
                            "semantic_field": (
                                "prazo_entrega"
                                if typed_deadline["deadline_type"] == "DELIVERY"
                                else "prazo_execucao"
                            ),
                            "legacy_field_alias": typed_deadline["deadline_type"] == "DELIVERY",
                        }
                decisions.append({
                    **base,
                    **decision_payload(
                        field=field,
                        internal_status=FOUND,
                        reason="Decisão preservada na baseline validated_current.",
                        baseline_state="CONSOLIDATED",
                        **semantic_details,
                    ),
                })
                continue

            retrieval_started = time.perf_counter()
            ranked = hybrid_search(
                question,
                top_k=10,
                document_id=document_id,
                diagnostic_top_k=True,
            )
            production_sources, retrieval_metrics = _sources_and_metrics_for_document(
                question, document_id, 3
            )
            local_retrieval_ms += (time.perf_counter() - retrieval_started) * 1000
            production_candidate = _candidate_for_field(
                field, production_sources, document_id
            )
            candidate = _candidate_for_field(field, chunks, document_id)
            heading = _formal_heading(field, chunks)
            diagnostic = {
                "baseline_state": "NOT_FOUND",
                "top_10": [
                    {
                        "rank": rank,
                        "chunk_id": row.get("chunk_id"),
                        "pages": [row.get("page_start"), row.get("page_end")],
                        "score": row.get("retrieval_score"),
                    }
                    for rank, row in enumerate(ranked, start=1)
                ],
                "most_relevant_section": production_sources[0].get("section_title") if production_sources else None,
                "formal_heading": heading,
                "parser": "deterministic_full_document",
                "fallback_used": bool(candidate),
                "retrieval_metrics": retrieval_metrics,
            }
            if production_candidate:
                production_evidence = validate_evidence(
                    evidence_text=str(production_candidate.get("evidence_text") or ""),
                    source_chunk_id=str(production_candidate.get("source_chunk_id") or "") or None,
                    retrieved_sources=production_sources,
                    selected_document_id=document_id,
                    value=str(production_candidate.get("value") or ""),
                    field_name=field,
                )
                if production_evidence["evidence_valid"]:
                    if production_candidate.get("value_type") == CONFIDENTIAL_VALUE:
                        production_status = FIELD_CONFIDENTIAL
                    elif production_candidate.get("value_type") == VARIABLE_VALUE:
                        production_status = FIELD_VARIABLE_BY_ITEM
                    else:
                        production_status = FOUND
                    decisions.append({
                        **base,
                        **decision_payload(
                            field=field,
                            internal_status=production_status,
                            reason="Novo candidato local validado nas três fontes de produção.",
                            value=str(production_candidate.get("value") or ""),
                            evidence=production_evidence,
                            candidate={key: value for key, value in production_candidate.items() if key != "source"},
                            candidate_origin="CANDIDATE",
                            deadline_type=production_candidate.get("deadline_type"),
                            execution_type=production_candidate.get("execution_type"),
                            semantic_field=(
                                "prazo_execucao"
                                if field == "prazo_execucao"
                                else field
                            ),
                            **diagnostic,
                        ),
                    })
                    continue
            if candidate:
                evidence = validate_evidence(
                    evidence_text=str(candidate.get("evidence_text") or ""),
                    source_chunk_id=str(candidate.get("source_chunk_id") or "") or None,
                    retrieved_sources=chunks,
                    selected_document_id=document_id,
                    value=str(candidate.get("value") or ""),
                    field_name=field,
                )
                if candidate.get("value_type") == CONFIDENTIAL_VALUE and evidence["evidence_valid"]:
                    status = FIELD_CONFIDENTIAL
                    reason = "O documento declara literalmente que o valor estimado é sigiloso."
                elif candidate.get("value_type") == VARIABLE_VALUE:
                    status = FIELD_VARIABLE_BY_ITEM
                    reason = "Os valores estão distribuídos por item, lote ou tabela; não foi calculado total artificial."
                elif evidence["evidence_valid"]:
                    status = _stage_for_candidate(candidate, ranked, production_sources, question)
                    reason = "O campo existe no documento; a etapa indicada impediu sua consolidação anterior."
                else:
                    status = UNRESOLVED
                    reason = f"Candidato localizado, mas a validação literal rejeitou: {evidence.get('validation_error')}."
                decisions.append({
                    **base,
                    **decision_payload(
                        field=field,
                        internal_status=status,
                        reason=reason,
                        value=str(candidate.get("value") or ""),
                        evidence=evidence,
                        candidate={key: value for key, value in candidate.items() if key != "source"},
                        deadline_type=candidate.get("deadline_type"),
                        execution_type=candidate.get("execution_type"),
                        semantic_field=(
                            "prazo_execucao"
                            if field == "prazo_execucao"
                            else field
                        ),
                        **diagnostic,
                    ),
                })
                continue

            if field == "prazo_execucao" and profile.get("object_nature") == "bens":
                related_delivery = delivery_candidate(chunks)
                if related_delivery:
                    evidence = validate_evidence(
                        evidence_text=str(related_delivery.get("evidence_text") or ""),
                        source_chunk_id=str(related_delivery.get("source_chunk_id") or "") or None,
                        retrieved_sources=chunks,
                        selected_document_id=document_id,
                        value=execution_answer(related_delivery),
                        field_name=field,
                    )
                    if evidence["evidence_valid"]:
                        decisions.append({
                            **base,
                            **decision_payload(
                                field=field,
                                internal_status=NOT_APPLICABLE,
                                reason=(
                                    "A aquisição possui prazo de entrega física, não prazo de execução; "
                                    "os conceitos foram mantidos separados."
                                ),
                                value=(
                                    "O documento não estabelece prazo de execução. Como prazo distinto, "
                                    f"{execution_answer(related_delivery).lower()}"
                                ),
                                evidence=evidence,
                                semantic_field="prazo_entrega",
                                deadline_type=related_delivery["deadline_type"],
                                related_candidate={
                                    key: value
                                    for key, value in related_delivery.items()
                                    if key != "source"
                                },
                                **diagnostic,
                            ),
                        })
                        continue

            status, reason = _absence_decision(field, chunks, profile, quality)
            decisions.append({
                **base,
                **decision_payload(
                    field=field,
                    internal_status=status,
                    reason=reason,
                    **diagnostic,
                ),
            })

    recall_rows = [evaluate_retriever_entry(entry) for entry in golden["entries"]]
    status_counts = Counter(row["internal_status"] for row in decisions)
    field_matrix: dict[str, Counter[str]] = defaultdict(Counter)
    document_matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for row in decisions:
        field_matrix[row["field"]][row["internal_status"]] += 1
        document_matrix[row["document"]][row["internal_status"]] += 1
    correct = sum(
        status_counts[key]
        for key in (FOUND, FIELD_CONFIDENTIAL, NOT_APPLICABLE, ACTUALLY_ABSENT)
    )
    return {
        "schema_version": "1.0",
        "baseline": {"golden": 46, "consolidated_found": 105, "total": len(decisions)},
        "metrics": {
            "found": status_counts[FOUND] + status_counts[FIELD_CONFIDENTIAL],
            "found_coverage": round((status_counts[FOUND] + status_counts[FIELD_CONFIDENTIAL]) / max(len(decisions), 1), 4),
            "correct_decisions": correct,
            "correct_decision_rate": round(correct / max(len(decisions), 1), 4),
            "status_counts": dict(sorted(status_counts.items())),
            "recall": aggregate_recall(recall_rows),
            "local_processing_time_ms": round((time.perf_counter() - started) * 1000, 1),
            "local_retrieval_time_ms": round(local_retrieval_ms, 1),
            "external_api_wait_time_ms": 0.0,
            "groq_calls": 0,
        },
        "field_matrix": {field: dict(counts) for field, counts in field_matrix.items()},
        "document_matrix": {document: dict(counts) for document, counts in document_matrix.items()},
        "decisions": decisions,
    }


def write_outputs(payload: dict[str, Any], json_path: Path, csv_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "document", "document_id", "field", "final_status", "internal_status",
                "failure_stage", "reason", "value", "baseline_state", "formal_heading",
            ],
        )
        writer.writeheader()
        for row in payload["decisions"]:
            writer.writerow({key: row.get(key) for key in writer.fieldnames})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--skip-pdf-quality", action="store_true")
    args = parser.parse_args()
    payload = run_audit(include_pdf_quality=not args.skip_pdf_quality)
    write_outputs(payload, args.json, args.csv)
    print(json.dumps(payload["metrics"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

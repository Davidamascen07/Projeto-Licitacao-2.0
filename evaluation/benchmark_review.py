from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from services.config import PROJECT_ROOT
from services.document_manifest import load_manifest
from services.evidence import literal_is_present, normalize_literal
from services.storage_utils import utc_now

from .benchmark import CRITICAL_FIELDS, validate_benchmark


class ReviewImportError(ValueError):
    """Indica que o arquivo de revisão não pode ser aplicado com segurança."""


def load_review_payload(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReviewImportError(f"Não foi possível ler {source}: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("documents"), list):
        raise ReviewImportError(f"{source} deve conter um objeto com a lista 'documents'.")
    reviewer = str(payload.get("reviewer") or "").strip()
    if not reviewer:
        raise ReviewImportError(f"{source} não informa o identificador do revisor.")
    payload["_source_path"] = str(source.resolve())
    return payload


def merge_review_payloads(payloads: list[dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    if not payloads:
        raise ReviewImportError("Informe ao menos um arquivo de revisão.")
    reviewers = {str(payload.get("reviewer") or "").strip() for payload in payloads}
    if len(reviewers) != 1:
        raise ReviewImportError("Todos os arquivos importados devem ter o mesmo revisor.")
    merged_by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    overridden: list[str] = []
    declared_missing: list[dict[str, Any]] = []
    sources: list[str] = []
    for payload in payloads:
        sources.append(payload.get("_source_path", ""))
        if isinstance(payload.get("missing_document"), dict):
            declared_missing.append(payload["missing_document"])
        for incoming in payload["documents"]:
            document_id = str(incoming.get("document_id") or "").strip()
            if not document_id:
                raise ReviewImportError("Documento de revisão sem document_id.")
            if document_id not in merged_by_id:
                merged_by_id[document_id] = copy.deepcopy(incoming)
                order.append(document_id)
                continue
            overridden.append(document_id)
            current = merged_by_id[document_id]
            current.update({key: copy.deepcopy(value) for key, value in incoming.items() if key not in {"metadata", "references"}})
            current.setdefault("metadata", {}).update(copy.deepcopy(incoming.get("metadata", {})))
            current.setdefault("references", {}).update(copy.deepcopy(incoming.get("references", {})))
    return (
        {
            "reviewer": reviewers.pop(),
            "documents": [merged_by_id[document_id] for document_id in order],
            "sources": sources,
            "declared_missing": declared_missing,
        },
        sorted(set(overridden)),
    )


def extract_page_text(document_id: str, page_number: int, manifest: dict[str, Any] | None = None) -> tuple[str, int]:
    import fitz

    current_manifest = manifest or load_manifest()
    record = next((doc for doc in current_manifest["documents"] if doc.get("document_id") == document_id), None)
    if record is None:
        raise ReviewImportError(f"Documento fora do manifesto: {document_id}")
    path = PROJECT_ROOT / record["relative_path"]
    if not path.is_file():
        raise ReviewImportError(f"PDF ausente: {path}")
    with fitz.open(path) as pdf:
        if page_number < 1 or page_number > pdf.page_count:
            raise ReviewImportError(
                f"Página {page_number} fora do intervalo 1-{pdf.page_count} de {record['filename']}."
            )
        return pdf[page_number - 1].get_text("text"), pdf.page_count


def apply_review_payload(
    benchmark: dict[str, Any],
    payload: dict[str, Any],
    *,
    page_loader: Callable[[str, int], tuple[str, int]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    schema_errors = validate_benchmark(benchmark)
    if schema_errors:
        raise ReviewImportError("Benchmark atual inválido: " + "; ".join(schema_errors))
    reviewer = str(payload.get("reviewer") or "").strip()
    if not reviewer:
        raise ReviewImportError("Identificador do revisor ausente.")
    loader = page_loader or extract_page_text
    updated = copy.deepcopy(benchmark)
    benchmark_by_id = {doc["document_id"]: doc for doc in updated["documents"]}
    errors: list[str] = []
    validated_fields = 0
    validated_documents: list[str] = []

    for incoming in payload.get("documents", []):
        document_id = str(incoming.get("document_id") or "").strip()
        target = benchmark_by_id.get(document_id)
        if target is None:
            errors.append(f"document_id não pertence ao benchmark: {document_id}")
            continue
        incoming_filename = str(incoming.get("filename") or "").strip()
        if incoming_filename and incoming_filename != target.get("filename"):
            errors.append(
                f"filename divergente em {document_id}: esperado {target.get('filename')}, recebido {incoming_filename}"
            )
        metadata = incoming.get("metadata") or {}
        for key in ("orgao", "uf", "modalidade"):
            value = metadata.get(key)
            if value is not None:
                target[key] = value
        if metadata:
            target["metadata_status"] = "validated"
            target["metadata_validated_by"] = reviewer
            target["metadata_validated_at"] = utc_now()

        references = incoming.get("references") or {}
        for field in CRITICAL_FIELDS:
            if field not in references:
                continue
            reference = references[field]
            page = reference.get("page")
            evidence = str(reference.get("evidence_text") or "").strip()
            if not isinstance(page, int):
                errors.append(f"{document_id}/{field}: página deve ser um inteiro 1-based")
                continue
            if not evidence:
                errors.append(f"{document_id}/{field}: evidence_text ausente")
                continue
            try:
                page_text, page_count = loader(document_id, page)
            except Exception as exc:
                errors.append(f"{document_id}/{field}: {exc}")
                continue
            if not literal_is_present(evidence, page_text):
                errors.append(
                    f"{document_id}/{field}: trecho não encontrado literalmente na página {page}/{page_count}"
                )
                continue
            value = reference.get("value")
            target["references"][field] = {
                "value": value,
                "normalized_value": None if value is None else normalize_literal(str(value)),
                "page": page,
                "evidence_text": evidence,
                "validated_by_human": True,
                "validated_by": reviewer,
                "validated_at": utc_now(),
                "note": reference.get("note"),
                "import_sources": payload.get("sources", []),
            }
            validated_fields += 1
        if all(target["references"].get(field, {}).get("validated_by_human") for field in CRITICAL_FIELDS):
            target["annotation_status"] = "validated"
            validated_documents.append(document_id)
        else:
            target["annotation_status"] = "pending_review"

    if errors:
        raise ReviewImportError("Importação cancelada; nenhuma alteração foi gravada:\n- " + "\n- ".join(errors))
    updated["updated_at"] = utc_now()
    report = {
        "reviewer": reviewer,
        "submitted_documents": len(payload.get("documents", [])),
        "validated_documents": len(set(validated_documents)),
        "validated_fields": validated_fields,
        "declared_missing": payload.get("declared_missing", []),
    }
    return updated, report

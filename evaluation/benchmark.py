from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from services.config import BENCHMARK_SEED
from services.document_manifest import load_manifest
from services.storage_utils import atomic_write_json, load_json, utc_now

BENCHMARK_PATH = Path(__file__).with_name("benchmark.json")
CRITICAL_FIELDS = ("valor_estimado", "modalidade", "prazo_entrega_proposta")


def _empty_reference() -> dict[str, Any]:
    return {
        "value": None,
        "normalized_value": None,
        "page": None,
        "evidence_text": None,
        "validated_by_human": False,
        "validated_by": None,
        "validated_at": None,
    }


def create_benchmark(
    output_path: str | Path = BENCHMARK_PATH,
    *,
    max_documents: int = 10,
    seed: int = BENCHMARK_SEED,
) -> dict[str, Any]:
    if max_documents < 1 or max_documents > 10:
        raise ValueError("O benchmark inicial deve conter entre 1 e 10 documentos.")
    manifest = load_manifest()
    eligible = [
        doc for doc in manifest["documents"]
        if doc.get("status") in {"indexed", "pending_index"} and not doc.get("excluded")
    ]
    eligible.sort(key=lambda doc: doc["document_id"])
    random.Random(seed).shuffle(eligible)
    selected = eligible[:max_documents]
    existing = load_json(output_path, {"documents": []})
    existing_by_id = {doc.get("document_id"): doc for doc in existing.get("documents", [])}

    development_count = min(7, max(1, round(len(selected) * 0.7))) if selected else 0
    documents: list[dict[str, Any]] = []
    for position, source in enumerate(selected):
        previous = existing_by_id.get(source["document_id"], {})
        references = previous.get("references") or {field: _empty_reference() for field in CRITICAL_FIELDS}
        for field in CRITICAL_FIELDS:
            references.setdefault(field, _empty_reference())
        documents.append(
            {
                "document_id": source["document_id"],
                "filename": source["filename"],
                "sha256": source["sha256"],
                "source": source.get("source"),
                "source_url": source.get("source_url"),
                "collection_date": source.get("collection_date"),
                "orgao": previous.get("orgao"),
                "uf": previous.get("uf"),
                "modalidade": previous.get("modalidade"),
                "metadata_status": previous.get("metadata_status", "pending_review"),
                "split": "development" if position < development_count else "test",
                "annotation_status": previous.get("annotation_status", "pending_review"),
                "references": references,
            }
        )
    benchmark = {
        "benchmark_version": "1.0",
        "created_at": existing.get("created_at") or utc_now(),
        "updated_at": utc_now(),
        "seed": seed,
        "selection_method": "deterministic_sha256_shuffle; metadata diversity pending human review",
        "documents": documents,
    }
    atomic_write_json(output_path, benchmark)
    return benchmark


def validate_benchmark(benchmark: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for doc in benchmark.get("documents", []):
        document_id = doc.get("document_id")
        if not document_id or document_id in seen:
            errors.append(f"document_id ausente ou duplicado: {document_id}")
        seen.add(document_id)
        if doc.get("split") not in {"development", "test"}:
            errors.append(f"split inválido em {document_id}")
        for field in CRITICAL_FIELDS:
            reference = doc.get("references", {}).get(field)
            if not isinstance(reference, dict):
                errors.append(f"referência ausente: {document_id}/{field}")
    return errors


def pending_review_report(benchmark: dict[str, Any]) -> list[dict[str, Any]]:
    report: list[dict[str, Any]] = []
    for doc in benchmark.get("documents", []):
        pending_fields = [
            field for field in CRITICAL_FIELDS
            if not doc.get("references", {}).get(field, {}).get("validated_by_human")
        ]
        missing_metadata = [name for name in ("orgao", "uf", "modalidade") if not doc.get(name)]
        if pending_fields or missing_metadata:
            report.append(
                {
                    "document_id": doc["document_id"],
                    "filename": doc["filename"],
                    "pending_reference_fields": pending_fields,
                    "pending_metadata": missing_metadata,
                }
            )
    return report

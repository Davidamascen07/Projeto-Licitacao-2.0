"""Avaliação permanente de regressão, Recall@K e paridade individual/lote."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from services.extraction_service import FIELD_QUESTIONS
from services.retrieval import hybrid_search, normalize_text
from services.vector_store import get_chunks

GOLDEN_PATH = Path(__file__).with_name("golden_baseline.json")
RECALL_KS = (1, 3, 5, 10)


def load_golden(path: Path = GOLDEN_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("baseline_found_count") != len(payload.get("entries", [])):
        raise ValueError("baseline_found_count diverge da quantidade de casos golden.")
    return payload


def relevant_chunks(entry: dict[str, Any], chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected_terms = [normalize_text(term) for term in entry.get("expected_terms", [])]
    expected_pages = {int(page) for page in entry.get("expected_pages", [])}
    output = []
    for chunk in chunks:
        if chunk.get("document_id") != entry.get("document_id"):
            continue
        text = normalize_text(chunk.get("text", ""))
        term_match = not expected_terms or any(term in text for term in expected_terms)
        pages = set(range(int(chunk.get("page_start") or 0), int(chunk.get("page_end") or 0) + 1))
        page_match = not expected_pages or bool(pages & expected_pages)
        if term_match and page_match:
            output.append(chunk)
    return output


def recall_at_k(ranked: list[dict[str, Any]], relevant_ids: set[str]) -> dict[str, float]:
    """Recall binário: ao menos um chunk correto apareceu até K."""
    return {
        f"recall@{k}": float(
            any(str(item.get("chunk_id")) in relevant_ids for item in ranked[:k])
        )
        for k in RECALL_KS
    }


def evaluate_retriever_entry(
    entry: dict[str, Any],
    *,
    dense_search_fn: Callable[..., list[dict[str, Any]]] | None = None,
    chunks_fn: Callable[[str | None], list[dict[str, Any]]] = get_chunks,
) -> dict[str, Any]:
    chunks = chunks_fn(entry["document_id"])
    targets = relevant_chunks(entry, chunks)
    kwargs: dict[str, Any] = {
        "top_k": 10,
        "document_id": entry["document_id"],
        "diagnostic_top_k": True,
        "chunks_fn": chunks_fn,
    }
    if dense_search_fn is not None:
        kwargs["dense_search_fn"] = dense_search_fn
    ranked = hybrid_search(FIELD_QUESTIONS[entry["field"]], **kwargs)
    target_ids = {str(item.get("chunk_id")) for item in targets}
    first_rank = next(
        (
            rank
            for rank, item in enumerate(ranked, start=1)
            if str(item.get("chunk_id")) in target_ids
        ),
        None,
    )
    return {
        "document": entry["document"],
        "document_id": entry["document_id"],
        "field": entry["field"],
        "target_chunk_ids": sorted(target_ids),
        "target_candidate_found": first_rank is not None,
        "target_rank": first_rank,
        **recall_at_k(ranked, target_ids),
        "ranked_chunk_ids": [str(item.get("chunk_id")) for item in ranked],
    }


def aggregate_recall(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {f"recall@{k}": 0.0 for k in RECALL_KS}
    return {
        f"recall@{k}": round(sum(float(row[f"recall@{k}"]) for row in rows) / len(rows), 4)
        for k in RECALL_KS
    }


def compare_golden_results(
    results: dict[tuple[str, str], dict[str, Any]],
    golden: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    golden = golden or load_golden()
    rows = []
    for entry in golden["entries"]:
        result = results.get((entry["document_id"], entry["field"]), {})
        actual_status = "FOUND" if result.get("answered") else "NOT_FOUND"
        expected_status = entry["expected_status"]
        rows.append(
            {
                "document": entry["document"],
                "field": entry["field"],
                "expected_status": expected_status,
                "actual_status": actual_status,
                "outcome": "REGRESSION" if expected_status == "FOUND" and actual_status != "FOUND" else "PASS",
            }
        )
    return rows


def compare_batch_individual(
    batch: dict[str, dict[str, Any]],
    individual: dict[str, dict[str, Any]],
) -> list[dict[str, str]]:
    divergences = []

    def status(item: dict[str, Any]) -> str:
        return str(
            item.get("final_status")
            or ("FOUND" if item.get("answered") else "NOT_FOUND")
        )

    def evidence_id(item: dict[str, Any]) -> str:
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        return str(evidence.get("chunk_id") or item.get("source_chunk_id") or "")

    for field in sorted(set(batch) | set(individual)):
        batch_item = batch.get(field, {})
        individual_item = individual.get(field, {})
        batch_status = status(batch_item)
        individual_status = status(individual_item)
        mismatch = batch_status != individual_status
        comparable_details = any(
            key in batch_item or key in individual_item
            for key in ("internal_status", "document_id", "evidence", "source_chunk_id")
        )
        if comparable_details and not mismatch:
            mismatch = any(
                str(batch_item.get(key) or "") != str(individual_item.get(key) or "")
                for key in ("internal_status", "document_id", "field")
            ) or evidence_id(batch_item) != evidence_id(individual_item)
        if mismatch:
            divergences.append({
                "field": field,
                "code": "BATCH_INDIVIDUAL_DIVERGENCE",
                "individual_status": individual_status,
                "batch_status": batch_status,
            })
    return divergences

"""Congela uma baseline forte somente após todos os invariantes da auditoria."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT = ROOT / "output" / "decision_audit_2026-08-07.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "strong_baseline_2026-08-07.json"

BLOCKING_STATUSES = {
    "FIELD_PRESENT_RETRIEVAL_MISS",
    "FIELD_PRESENT_RANKING_MISS",
    "FIELD_PRESENT_SECTION_EXPANSION_MISS",
    "FIELD_PRESENT_CONTEXT_TRUNCATION",
    "FIELD_PRESENT_PARSER_MISS",
    "FIELD_PRESENT_VALIDATION_MISS",
    "FIELD_PRESENT_IN_TABLE",
    "FIELD_PRESENT_IN_ANNEX",
    "DOCUMENT_TEXT_INSUFFICIENT",
    "UNRESOLVED",
}

SURGICAL_REVIEW = {
    ("01.Edital_credenciamento_01_2024.pdf", "prazo_entrega_proposta"),
    ("1123420260129-Termo_1.pdf", "orgao_responsavel"),
    ("Edital+Credenciamento_OCS-PSA+01-2024.pdf", "prazo_entrega_proposta"),
    ("edital609.pdf", "requisitos_habilitacao"),
    ("edital610.pdf", "requisitos_habilitacao"),
    ("EDITAL_CC006.pdf", "valor_estimado"),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _origin(row: dict[str, Any]) -> str:
    if (row["document"], row["field"]) in SURGICAL_REVIEW:
        return "SURGICAL_REVIEW"
    if row.get("baseline_origin") == "GOLDEN":
        return "GOLDEN"
    if row.get("baseline_state") == "CONSOLIDATED":
        return "CONSOLIDATED"
    return "CANDIDATE_VALIDATED"


def freeze(payload: dict[str, Any]) -> dict[str, Any]:
    decisions = payload["decisions"]
    if len(decisions) != 171:
        raise ValueError(f"A baseline exige 171 decisões; recebido: {len(decisions)}")
    blockers = [row for row in decisions if row["internal_status"] in BLOCKING_STATUSES]
    if blockers:
        raise ValueError(f"Existem {len(blockers)} decisões bloqueantes; baseline não congelada.")
    golden = [row for row in decisions if row.get("baseline_origin") == "GOLDEN"]
    if len(golden) != 46 or any(row["final_status"] != "FOUND" for row in golden):
        raise ValueError("Os 46 casos GOLDEN não foram integralmente preservados.")
    cross_document = [
        row for row in decisions
        if (row.get("evidence") or {}).get("document_id")
        and row["evidence"]["document_id"] != row["document_id"]
    ]
    if cross_document:
        raise ValueError("Há evidência associada a outro document_id.")
    incoherent_profiles = [
        row for row in decisions
        if not row["document_profile"].get("profile_consistent")
        or not row["document_profile"].get("justification_consistent")
    ]
    if incoherent_profiles:
        raise ValueError("Há perfil ou justificativa documental incoerente.")

    counts = Counter(row["internal_status"] for row in decisions)
    frozen_decisions = []
    for row in decisions:
        evidence = row.get("evidence") or {}
        frozen_decisions.append(
            {
                "document": row["document"],
                "document_id": row["document_id"],
                "field": row["field"],
                "origin": _origin(row),
                "final_status": row["final_status"],
                "internal_status": row["internal_status"],
                "value": row.get("value") or "",
                "semantic_field": row.get("semantic_field") or row["field"],
                "deadline_type": row.get("deadline_type"),
                "execution_type": row.get("execution_type"),
                "legacy_field_alias": bool(row.get("legacy_field_alias")),
                "document_profile": row["document_profile"],
                "evidence": {
                    "document_id": evidence.get("document_id"),
                    "chunk_id": evidence.get("chunk_id"),
                    "filename": evidence.get("filename"),
                    "pages": evidence.get("pages"),
                    "text": evidence.get("text") or "",
                    "evidence_valid": evidence.get("evidence_valid"),
                },
                "reason": row.get("reason") or "",
            }
        )
    return {
        "schema_version": "1.0",
        "baseline_id": "strong-2026-08-07-surgical",
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "source_audit": str(DEFAULT_AUDIT.relative_to(ROOT)).replace("\\", "/"),
        "policy": {
            "golden_promoted_automatically": False,
            "delivery_is_execution": False,
            "variable_values_are_summed": False,
            "cross_document_evidence_allowed": False,
        },
        "counts": {
            "total": len(decisions),
            "golden": len(golden),
            "surgical_review": len(SURGICAL_REVIEW),
            "by_internal_status": dict(sorted(counts.items())),
            "correct_decisions_strict": payload["metrics"]["correct_decisions"],
            "correct_decision_rate_strict": payload["metrics"]["correct_decision_rate"],
            "context_dependent_variable_values": counts["FIELD_VARIABLE_BY_ITEM"],
        },
        "index_integrity": {
            "vector_index_sha256": _sha256(ROOT / "vector_index.faiss"),
            "chunks_metadata_sha256": _sha256(ROOT / "chunks_metadata.json"),
            "reindexed": False,
        },
        "decisions": frozen_decisions,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    payload = json.loads(args.audit.read_text(encoding="utf-8"))
    frozen = freeze(payload)
    args.output.write_text(json.dumps(frozen, ensure_ascii=False, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

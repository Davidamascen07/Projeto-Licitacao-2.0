from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Any, Iterable

from services.evidence import normalize_literal


def values_equivalent(actual: Any, reference: Any) -> bool:
    if actual is None or reference is None:
        return False
    return normalize_literal(str(actual)) == normalize_literal(str(reference))


def row_has_reference_mismatch(row: dict[str, Any]) -> bool:
    if not row.get("answered"):
        return False
    reference = row.get("reference") or {}
    return bool(
        reference.get("validated_by_human")
        and not values_equivalent(row.get("value"), reference.get("value"))
    )


def row_unsupported_claim_score(row: dict[str, Any]) -> float:
    """Retorna a fração sem suporte factual, sem comparar texto com o gabarito."""
    if not row.get("answered"):
        return 0.0
    evidence = row.get("evidence") or {}
    if not evidence.get("evidence_valid"):
        return 1.0
    faithfulness = row.get("faithfulness")
    if faithfulness is None:
        return 0.0
    try:
        supported = min(1.0, max(0.0, float(faithfulness)))
        return 1.0 - supported
    except (TypeError, ValueError):
        return 1.0


def row_is_unsupported_claim(row: dict[str, Any]) -> bool:
    return row_unsupported_claim_score(row) > 1e-9


def row_is_hallucinated(row: dict[str, Any]) -> bool:
    """Alias compatível: alucinação agora significa afirmação sem suporte factual."""
    return row_is_unsupported_claim(row)


def hallucination_rate(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    answered = [row for row in rows if row.get("answered")]
    unsupported_scores = [row_unsupported_claim_score(row) for row in answered]
    unsupported = [row for row in answered if row_is_unsupported_claim(row)]
    comparable = [
        row
        for row in answered
        if (row.get("reference") or {}).get("validated_by_human")
    ]
    mismatches = [row for row in comparable if row_has_reference_mismatch(row)]
    unsupported_rate = statistics.fmean(unsupported_scores) if answered else None
    return {
        "answered_fields": len(answered),
        "unsupported_fields": len(unsupported),
        "unsupported_claim_rate": unsupported_rate,
        "reference_compared_fields": len(comparable),
        "reference_mismatch_fields": len(mismatches),
        "reference_mismatch_rate": len(mismatches) / len(comparable) if comparable else None,
        # Chaves legadas preservadas para relatórios e critérios existentes.
        "hallucinated_fields": len(unsupported),
        "hallucination_rate": unsupported_rate,
        "definition": "mean unsupported fraction per answered field: 1 for invalid evidence, otherwise 1 - Faithfulness",
        "reference_mismatch_definition": "answers not literally equivalent to a human-validated reference / comparable answered fields",
    }


def numeric_summary(values: Iterable[Any]) -> dict[str, Any]:
    valid = [float(value) for value in values if value is not None and not math.isnan(float(value))]
    if not valid:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None, "stddev": None}
    return {
        "count": len(valid),
        "mean": statistics.fmean(valid),
        "median": statistics.median(valid),
        "min": min(valid),
        "max": max(valid),
        "stddev": statistics.pstdev(valid),
    }


def aggregate_rows(rows: list[dict[str, Any]], group_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row.get(field) for field in group_fields)].append(row)
    output: list[dict[str, Any]] = []
    for key, group in sorted(groups.items(), key=lambda item: str(item[0])):
        item = dict(zip(group_fields, key))
        item.update(
            {
                "samples": len(group),
                "faithfulness": numeric_summary(row.get("faithfulness") for row in group),
                "answer_correctness": numeric_summary(row.get("answer_correctness") for row in group),
                "total_ms": numeric_summary((row.get("metrics") or {}).get("total_ms") for row in group),
                "prompt_tokens": numeric_summary((row.get("usage") or {}).get("prompt_tokens") for row in group),
                "completion_tokens": numeric_summary((row.get("usage") or {}).get("completion_tokens") for row in group),
                "estimated_cost": numeric_summary((row.get("usage") or {}).get("estimated_cost") for row in group),
                **hallucination_rate(group),
                "ignored_answer_correctness": sum(
                    1 for row in group if not (row.get("reference") or {}).get("validated_by_human")
                ),
            }
        )
        output.append(item)
    return output

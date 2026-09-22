"""Extração tipada do modelo/prazo de execução, sem confundir vigência."""

from __future__ import annotations

import re
from typing import Any

from .deadline_ontology import DELIVERY, EXECUTION

ON_DEMAND = "ON_DEMAND"
NUMERIC_EXECUTION = "NUMERIC_EXECUTION"
EXECUTION_EQUALS_CONTRACT_TERM = "EXECUTION_EQUALS_CONTRACT_TERM"
DURING_CONTRACT_TERM = "DURING_CONTRACT_TERM"
DELIVERY_DEADLINE = "DELIVERY_DEADLINE"
EXECUTION_SCHEDULE = "EXECUTION_SCHEDULE"

_DURATION = r"\d{1,4}\s*(?:\([^)]{1,40}\)\s*)?(?:dias?\s+[úu]teis|dias?|meses?|anos?|horas?)"

_NUMERIC_PATTERNS = (
    re.compile(
        rf"((?:prazo|per[íi]odo|tempo)\s+(?:para\s+|de\s+)?execu[çc][ãa]o[^.;]{{0,220}}?({_DURATION})[^.;]*[.;]?)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"((?:servi[çc]os?|objeto)\s+(?:ser[ãa]o\s+)?(?:executados?|prestados?)[^.;]{{0,180}}?"
        rf"(?:durante|pelo\s+per[íi]odo\s+de|em)\s+({_DURATION})[^.;]*[.;]?)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"((?:presta[çc][ãa]o|execu[çc][ãa]o|contrata[çc][ãa]o\s+de\s+servi[çc]o)[^.;]{{0,220}}?"
        rf"(?:no|pelo)\s+per[íi]odo\s+de\s+({_DURATION})[^.;]*[.;]?)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"((?:a\s+contar|contados?|ap[óo]s|a\s+partir)\s+(?:da\s+)?(?:emiss[ãa]o|recebimento)?"
        rf"[^.;]{{0,80}}?ordem\s+de\s+servi[çc]o[^.;]{{0,100}}?({_DURATION})[^.;]*[.;]?)",
        re.IGNORECASE,
    ),
)

_DELIVERY_PATTERNS = (
    re.compile(
        rf"((?:prazo\s+(?:para|de)\s+entrega(?:\s+dos?\s+bens?)?[^.;]{{0,160}}?"
        rf"(?:ser[áa]\s+de|[ée]\s+de|em|:)\s*(?:at[ée]\s+)?({_DURATION})|"
        rf"proceder\s+[àa]\s+entrega\s+do\s+bem[^.;]{{0,100}}?(?:no\s+m[áa]ximo\s+em|em)\s+({_DURATION}))[^.;]*[.;]?)",
        re.IGNORECASE,
    ),
)

_SCHEDULE = re.compile(
    rf"((?:prazo\s+m[áa]ximo\s+para\s+a\s+execu[çc][ãa]o|do\s+prazo\s+e\s+da\s+vig[êe]ncia)"
    rf"[\s\S]{{0,500}}?in[íi]cio\s*:\s*({_DURATION})\s*;?\s*"
    rf"conclus[ãa]o\s*:\s*({_DURATION}))",
    re.IGNORECASE,
)

_ON_DEMAND = re.compile(
    r"((?:execu[çc][ãa]o|presta[çc][ãa]o|servi[çc]os?)[^.;]{0,220}?sob\s+demanda"
    r"[^.;]{0,220}?(?:ordem\s+de\s+servi[çc]o|vig[êe]ncia|necessidade)[^.;]*[.;]?|"
    r"sob\s+demanda[^.;]{0,180}?(?:ordem\s+de\s+servi[çc]o|execu[çc][ãa]o)[^.;]*[.;]?|"
    r"in[íi]cio\s+da\s+presta[çc][ãa]o\s+dos?\s+servi[çc]os?\s+ocorrer[áa]"
    r"[^.;]{0,100}?de\s+acordo\s+com\s+as\s+demandas[^.;]*[.;]?)",
    re.IGNORECASE,
)

_COINCIDENT = re.compile(
    rf"((?:prazo|per[íi]odo)\s+de\s+execu[çc][ãa]o[^.;]{{0,180}}?({_DURATION})"
    r"[^.;]{0,180}?(?:coincidente|igual|correspondente|atrelado)"
    r"[^.;]{0,120}?vig[êe]ncia[^.;]*[.;]?)",
    re.IGNORECASE,
)

_TERM_LINKED = re.compile(
    rf"((?:contrato[^.;]{{0,180}}?per[íi]odo\s+inicial\s+de\s+({_DURATION})[^.;]*[.;])"
    rf"[\s\S]{{0,1500}}?(?:prazo\s+para\s+execu[çc][ãa]o|prazo\s+de\s+execu[çc][ãa]o)"
    r"[^.;]{0,160}?(?:atrelado|coincidente|igual|correspondente)[^.;]{0,100}?vig[êe]ncia[^.;]*[.;]?)",
    re.IGNORECASE,
)

_DURING_TERM = re.compile(
    r"((?:execu[çc][ãa]o|presta[çc][ãa]o)\s+dos?\s+servi[çc]os?[^.;]{0,180}?"
    r"(?:ao\s+longo|durante)\s+da\s+vig[êe]ncia(?:\s+contratual)?[^.;]*[.;]?)",
    re.IGNORECASE,
)


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def delivery_candidate(sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Extrai somente entrega física, sem promovê-la a execução."""
    for source in sources:
        text = str(source.get("text") or "")
        for pattern in _DELIVERY_PATTERNS:
            match = pattern.search(text)
            if match:
                duration = next((group for group in match.groups()[1:] if group), "")
                return {
                    "execution_type": DELIVERY_DEADLINE,
                    "deadline_type": DELIVERY,
                    "value": _compact(duration),
                    "source_chunk_id": str(source.get("chunk_id") or ""),
                    "evidence_text": _compact(match.group(1)),
                    "source": source,
                }
    return None


def execution_candidate(
    sources: list[dict[str, Any]], *, include_delivery: bool = True
) -> dict[str, Any] | None:
    """Extrai execução; entrega só é aceita quando o chamador pede o fallback relacionado."""
    for source in sources:
        text = str(source.get("text") or "")
        match = _SCHEDULE.search(text)
        if match:
            return {
                "execution_type": EXECUTION_SCHEDULE,
                "deadline_type": EXECUTION,
                "value": f"início em {_compact(match.group(2))}; conclusão em {_compact(match.group(3))}",
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": _compact(match.group(1)),
                "source": source,
            }
    for source in sources:
        text = str(source.get("text") or "")
        match = _TERM_LINKED.search(text)
        if match:
            return {
                "execution_type": EXECUTION_EQUALS_CONTRACT_TERM,
                "deadline_type": EXECUTION,
                "value": _compact(match.group(2)),
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": _compact(match.group(1)),
                "source": source,
            }
    for source in sources:
        text = str(source.get("text") or "")
        match = _COINCIDENT.search(text)
        if match:
            return {
                "execution_type": EXECUTION_EQUALS_CONTRACT_TERM,
                "deadline_type": EXECUTION,
                "value": _compact(match.group(2)),
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": _compact(match.group(1)),
                "source": source,
            }
    for source in sources:
        text = str(source.get("text") or "")
        for pattern in _NUMERIC_PATTERNS:
            match = pattern.search(text)
            if match:
                return {
                    "execution_type": NUMERIC_EXECUTION,
                    "deadline_type": EXECUTION,
                    "value": _compact(match.group(2)),
                    "source_chunk_id": str(source.get("chunk_id") or ""),
                    "evidence_text": _compact(match.group(1)),
                    "source": source,
                }
    for source in sources:
        match = _ON_DEMAND.search(str(source.get("text") or ""))
        if match:
            return {
                "execution_type": ON_DEMAND,
                "deadline_type": EXECUTION,
                "value": "sob demanda",
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": _compact(match.group(1)),
                "source": source,
            }
    for source in sources:
        text = str(source.get("text") or "")
        match = _DURING_TERM.search(text)
        if match:
            return {
                "execution_type": DURING_CONTRACT_TERM,
                "deadline_type": EXECUTION,
                "value": "durante a vigência contratual",
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": _compact(match.group(1)),
                "source": source,
            }
    return delivery_candidate(sources) if include_delivery else None


def execution_answer(candidate: dict[str, Any]) -> str:
    if candidate["execution_type"] == ON_DEMAND:
        return "A execução ocorre sob demanda, conforme a necessidade e a Ordem de Serviço; não há prazo numérico único."
    if candidate["execution_type"] == EXECUTION_EQUALS_CONTRACT_TERM:
        return f"Prazo de execução: {candidate['value']}, expressamente vinculado à vigência contratual."
    if candidate["execution_type"] == DURING_CONTRACT_TERM:
        return "A execução ocorre ao longo da vigência contratual; o trecho não fixa prazo numérico independente."
    if candidate["execution_type"] == DELIVERY_DEADLINE:
        return f"Prazo de entrega do objeto: {candidate['value']}."
    if candidate["execution_type"] == EXECUTION_SCHEDULE:
        return f"Cronograma de execução: {candidate['value']}."
    return f"Prazo de execução: {candidate['value']}."

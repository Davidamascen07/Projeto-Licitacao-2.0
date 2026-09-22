"""Tipagem e extração conservadora de valores de editais."""

from __future__ import annotations

import re
from typing import Any

GLOBAL_ESTIMATED_VALUE = "GLOBAL_ESTIMATED_VALUE"
MAXIMUM_VALUE = "MAXIMUM_VALUE"
REFERENCE_VALUE = "REFERENCE_VALUE"
BUDGET_VALUE = "BUDGET_VALUE"
LOT_VALUE = "LOT_VALUE"
ITEM_VALUE = "ITEM_VALUE"
ESTIMATIVE_COMMITMENT = "ESTIMATIVE_COMMITMENT"
CONFIDENTIAL_VALUE = "CONFIDENTIAL_VALUE"
VARIABLE_VALUE = "VARIABLE_VALUE"
NO_GLOBAL_VALUE = "NO_GLOBAL_VALUE"

VALUE_TYPES = {
    GLOBAL_ESTIMATED_VALUE,
    MAXIMUM_VALUE,
    REFERENCE_VALUE,
    BUDGET_VALUE,
    LOT_VALUE,
    ITEM_VALUE,
    ESTIMATIVE_COMMITMENT,
    CONFIDENTIAL_VALUE,
    VARIABLE_VALUE,
    NO_GLOBAL_VALUE,
}

MONEY = r"R\$\s*[\d.]+,\d{2,3}"

_CONFIDENTIAL = re.compile(
    r"((?:(?:valor|or[çc]amento|pre[çc]o)(?:\s+(?:total|global|m[áa]ximo))?\s+"
    r"(?:estimado|da\s+contrata[çc][ãa]o)|estimativa\s+da\s+contrata[çc][ãa]o)"
    r"[^.;]{0,240}?(?:sigiloso|car[áa]ter\s+sigiloso|n[ãa]o\s+divulgado))",
    re.IGNORECASE,
)

_TYPED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        GLOBAL_ESTIMATED_VALUE,
        re.compile(
            rf"((?:valor\s+(?:total\s+)?estimado|valor\s+global\s+estimado|"
            rf"valor\s+estimado(?:\s+da\s+(?:licita[çc][ãa]o|contrata[çc][ãa]o))?|"
            rf"valor\s+total\s+da\s+contrata[çc][ãa]o|estimativa\s+do\s+valor\s+da\s+contrata[çc][ãa]o)"
            rf"[^.;]{{0,240}}?({MONEY}))",
            re.IGNORECASE,
        ),
    ),
    (
        MAXIMUM_VALUE,
        re.compile(
            rf"((?:valor|pre[çc]o)\s+m[áa]ximo(?:\s+aceit[áa]vel)?[^.;]{{0,180}}?({MONEY}))",
            re.IGNORECASE,
        ),
    ),
    (
        REFERENCE_VALUE,
        re.compile(
            rf"((?:valor|pre[çc]o)\s+(?:de\s+)?refer[êe]ncia\s*:?[\s\S]{{0,120}}?({MONEY}))",
            re.IGNORECASE,
        ),
    ),
    (
        BUDGET_VALUE,
        re.compile(
            rf"((?:or[çc]amento\s+estimado|dota[çc][ãa]o\s+estimada|recursos\s+financeiros)"
            rf"[^.;]{{0,220}}?({MONEY}))",
            re.IGNORECASE,
        ),
    ),
    (
        BUDGET_VALUE,
        re.compile(
            rf"((?:valor\s+total|total\s+geral)\s*[:|\]\-]*\s*({MONEY}))",
            re.IGNORECASE,
        ),
    ),
    (
        ESTIMATIVE_COMMITMENT,
        re.compile(
            rf"((?:empenho\s+estimativo[^.;]{{0,220}}?({MONEY})|({MONEY})[^.;]{{0,160}}?empenho\s+estimativo))",
            re.IGNORECASE,
        ),
    ),
    (
        REFERENCE_VALUE,
        re.compile(
            rf"((?:valor\s+total\s+de\s+avalia[çc][ãa]o\s+dos\s+bens|valor\s+total\s+dos?\s+itens?)"
            rf"[^.;]{{0,160}}?({MONEY}))",
            re.IGNORECASE,
        ),
    ),
    (
        REFERENCE_VALUE,
        re.compile(
            rf"((?:valor\s+total\s+dos?\s+item|lance\s+m[íi]nimo)\s*:?"
            rf"[^.;]{{0,100}}?({MONEY}))",
            re.IGNORECASE,
        ),
    ),
)

_VARIABLE_ANCHOR = re.compile(
    r"(?:valores?|pre[çc]os?|lances?)\s+(?:por|dos?|constantes?\s+(?:da|nas?))\s+"
    r"(?:itens?|lotes?|tabelas?|listas?\s+referenciais?)|"
    r"rela[çc][ãa]o\s+dos?\s+lotes?|quadro\s+de\s+itens?|tabela\s+de\s+(?:pre[çc]os?|exames?)"
    r"|valor\s+unit[áa]rio\s+estimado\s+subtotal",
    re.IGNORECASE,
)

_LOT_OR_ITEM_VALUE = re.compile(
    rf"((?:^|\n)\s*(?:lote|item)\s*(?:n[ºo°.]*)?\s*\d+[^\n.;]{{0,180}}?({MONEY}))",
    re.IGNORECASE | re.MULTILINE,
)


def _compact(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _money_for_display(value: str) -> str:
    """Corrige somente o zero excedente comum da extração PDF brasileira."""
    compact = _compact(value)
    return re.sub(r"(,\d{2})0\b", r"\1", compact)


def _candidate(
    source: dict[str, Any], value_type: str, match: re.Match[str], amount: str = ""
) -> dict[str, Any]:
    literal = _compact(match.group(1))
    return {
        "value_type": value_type,
        "value": _compact(amount),
        "source_chunk_id": str(source.get("chunk_id") or ""),
        "evidence_text": literal,
        "source": source,
    }


def estimated_value_candidate(
    sources: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Extrai valor sem somar itens/lotes e sem remover qualificadores."""
    for source in sources:
        match = _CONFIDENTIAL.search(str(source.get("text") or ""))
        if match:
            return _candidate(source, CONFIDENTIAL_VALUE, match, "SIGILOSO")

    for value_type, pattern in _TYPED_PATTERNS:
        for source in sources:
            match = pattern.search(str(source.get("text") or ""))
            if not match:
                continue
            groups = [group for group in match.groups()[1:] if group and re.search(r"\d", group)]
            amount = groups[-1] if groups else ""
            return _candidate(source, value_type, match, amount)

    lot_candidates: list[dict[str, Any]] = []
    for source in sources:
        for match in _LOT_OR_ITEM_VALUE.finditer(str(source.get("text") or "")):
            value_type = LOT_VALUE if match.group(1).casefold().startswith("lote") else ITEM_VALUE
            lot_candidates.append(_candidate(source, value_type, match, match.group(2)))
    if len(lot_candidates) == 1:
        return lot_candidates[0]
    if len(lot_candidates) > 1:
        first = lot_candidates[0]
        return {
            **first,
            "value_type": VARIABLE_VALUE,
            "value": "",
            "item_count": len(lot_candidates),
        }

    for source in sources:
        text = str(source.get("text") or "")
        match = _VARIABLE_ANCHOR.search(text)
        if match:
            return {
                "value_type": VARIABLE_VALUE,
                "value": "",
                "source_chunk_id": str(source.get("chunk_id") or ""),
                "evidence_text": _compact(match.group(0)),
                "source": source,
            }
    return None


def value_answer(candidate: dict[str, Any]) -> str:
    value_type = candidate["value_type"]
    if value_type == CONFIDENTIAL_VALUE:
        return "Valor estimado sigiloso."
    if value_type == VARIABLE_VALUE:
        return "O documento não apresenta um único valor global; os valores variam por item, lote ou tabela."
    labels = {
        GLOBAL_ESTIMATED_VALUE: "Valor global estimado",
        MAXIMUM_VALUE: "Valor máximo aceitável",
        REFERENCE_VALUE: "Valor de referência",
        BUDGET_VALUE: "Orçamento estimado",
        ESTIMATIVE_COMMITMENT: "Empenho estimativo",
        LOT_VALUE: "Valor do lote",
        ITEM_VALUE: "Valor do item",
    }
    return f"{labels.get(value_type, 'Valor')}: {_money_for_display(candidate.get('value', ''))}."

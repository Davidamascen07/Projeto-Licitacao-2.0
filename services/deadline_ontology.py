"""Classifica prazos de editais antes de associá-los a um campo.

As regras são deliberadamente locais e conservadoras: um número só vira prazo
quando a própria frase contém sujeito e evento suficientes para definir o tipo.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

PROPOSAL_VALIDITY = "PROPOSAL_VALIDITY"
DELIVERY = "DELIVERY"
EXECUTION = "EXECUTION"
CONTRACT_TERM = "CONTRACT_TERM"
SIGNATURE = "SIGNATURE"
PAYMENT = "PAYMENT"
APPEAL = "APPEAL"
IMPUGNATION = "IMPUGNATION"
CREDENTIALING = "CREDENTIALING"
EMERGENCY_NOTIFICATION = "EMERGENCY_NOTIFICATION"
OTHER = "OTHER"

DEADLINE_TYPES = {
    PROPOSAL_VALIDITY,
    DELIVERY,
    EXECUTION,
    CONTRACT_TERM,
    SIGNATURE,
    PAYMENT,
    APPEAL,
    IMPUGNATION,
    CREDENTIALING,
    EMERGENCY_NOTIFICATION,
    OTHER,
}

_TYPE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (PROPOSAL_VALIDITY, (
        r"validade\s+(?:da|das)\s+propostas?",
        r"propostas?\s+v[aá]lidas?\s+por",
        r"(?:carta\s+)?propostas?[^.;]{0,100}?ter[aã]o\s+validade",
        r"manuten[cç][aã]o\s+da\s+proposta",
    )),
    (SIGNATURE, (r"assinatura\s+(?:da|do|das|dos)", r"assinar(?:em)?[^.;]{0,80}\b(?:contratos?|atas?)\b")),
    (PAYMENT, (r"pagamento", r"nota\s+fiscal")),
    (APPEAL, (r"recurso", r"contrarraz[oõ]es")),
    (IMPUGNATION, (r"impugna[cç][aã]o",)),
    (CREDENTIALING, (r"credenciamento", r"inscri[cç][oõ]es")),
    (EMERGENCY_NOTIFICATION, (r"emerg[eê]ncia", r"notifica[cç][aã]o")),
    (CONTRACT_TERM, (r"vig[eê]ncia", r"prazo\s+contratual")),
    (DELIVERY, (r"entrega\s+(?:do\s+objeto|dos?\s+bens?|dos?\s+produtos?)", r"recebimento\s+da\s+ordem\s+de\s+compra")),
    (EXECUTION, (r"execu[cç][aã]o", r"presta[cç][aã]o\s+dos?\s+servi[cç]os", r"ordem\s+de\s+servi[cç]o")),
)

_DURATION_RE = re.compile(
    r"(?P<duration>\d{1,4})\s*(?:\([^)]{1,40}\)\s*)?"
    r"(?P<unit>dias?\s+[uú]teis|dias?|horas?|meses?|anos?)",
    re.IGNORECASE,
)


def _normalized(text: str) -> str:
    value = unicodedata.normalize("NFKC", str(text or ""))
    return re.sub(r"\s+", " ", value).strip()


def classify_deadline(text: str) -> dict[str, Any] | None:
    """Retorna tipo, duração e unidade quando a frase contém um prazo literal."""
    literal = _normalized(text)
    duration = _DURATION_RE.search(literal)
    if not duration:
        return None
    deadline_type = OTHER
    for candidate_type, patterns in _TYPE_PATTERNS:
        if any(re.search(pattern, literal, re.IGNORECASE) for pattern in patterns):
            deadline_type = candidate_type
            break
    return {
        "duration": int(duration.group("duration")),
        "unit": duration.group("unit").casefold(),
        "type": deadline_type,
        "evidence_text": literal,
    }


def proposal_validity_from_sources(
    sources: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Localiza validade da proposta sem aceitar entrega, assinatura ou vigência."""
    patterns = (
        re.compile(
            r"((?:a\s+)?validade\s+(?:da|das)\s+propostas?\s+(?:ser[áa]|ser[ãa]o|[ée])\s+(?:de\s+)?"
            r"[A-Za-zÀ-ÿ-]+\s*\((\d{1,4})\)\s*(dias?\s+[úu]teis|dias?|meses?)[^.;]{0,120}[.;])",
            re.IGNORECASE,
        ),
        re.compile(
            r"((?:o\s+)?prazo\s+(?:de\s+)?validade\s+(?:da|das)\s+propostas?"
            r"[^.;]{0,180}?\b\d{1,4}\s*(?:\([^)]{1,40}\)\s*)?(?:dias?\s+[uú]teis|dias?|meses?)[^.;]{0,120}[.;])",
            re.IGNORECASE,
        ),
        re.compile(
            r"((?:a\s+)?validade\s+(?:da|das)\s+propostas?\s+(?:ser[aá]|ser[aã]o|é)\s+(?:de\s+)?"
            r"[^.;]{0,100}?\b\d{1,4}\s*(?:\([^)]{1,40}\)\s*)?(?:dias?\s+[uú]teis|dias?|meses?)[^.;]{0,120}[.;])",
            re.IGNORECASE,
        ),
        re.compile(
            r"(propostas?\s+v[aá]lidas?\s+por\s+[^.;]{0,80}?\b\d{1,4}\s*"
            r"(?:\([^)]{1,40}\)\s*)?(?:dias?\s+[uú]teis|dias?|meses?)[^.;]{0,120}[.;])",
            re.IGNORECASE,
        ),
        re.compile(
            r"((?:[“\"]?(?:carta\s+)?proposta[”\"]?[^.;]{0,100}?)"
            r"ter[aã]o\s+validade\s+de\s+\d{1,4}\s*"
            r"(?:\([^)]{1,40}\)\s*)?(?:dias?\s+[uú]teis|dias?|meses?)[^.;]{0,120}[.;])",
            re.IGNORECASE,
        ),
    )
    for source in sources:
        text = _normalized(str(source.get("text") or ""))
        for pattern in patterns:
            match = pattern.search(text)
            if not match:
                continue
            literal = match.group(1).strip()
            if pattern is patterns[0]:
                return source, {
                    "duration": int(match.group(2)),
                    "unit": match.group(3).casefold(),
                    "type": PROPOSAL_VALIDITY,
                    "evidence_text": literal,
                }
            classified = classify_deadline(literal)
            if classified and classified["type"] == PROPOSAL_VALIDITY:
                return source, classified
    return None

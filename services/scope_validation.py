"""Preserva qualificadores críticos de sujeito e exceção em respostas resumidas."""

from __future__ import annotations

import re
import unicodedata

_QUALIFIER_PATTERNS = (
    re.compile(r"\b(No\s+caso\s+de\s+[^,.;:]{3,100})", re.IGNORECASE),
    re.compile(
        r"\b(Para\s+(?:as?\s+|os\s+)?(?:Microempresas?|ME(?:/|\s+e\s+)EPP|"
        r"Empresas?\s+de\s+Pequeno\s+Porte|OCS|PSA|Sociedades?\s+Limitadas?|"
        r"Organiza[cç][oõ]es\s+Civis\s+de\s+Sa[uú]de|Profissionais?\s+de\s+Sa[uú]de\s+Aut[oô]nomos?)"
        r"[^,.;:]{0,80})[,;:]",
        re.IGNORECASE,
    ),
    re.compile(r"\b(Somente\s+para\s+[^,.;:]{3,100})", re.IGNORECASE),
    re.compile(r"\b(Exceto\s+[^,.;:]{3,100})", re.IGNORECASE),
)


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", value).strip().casefold()


def critical_qualifiers(text: str) -> list[str]:
    qualifiers = []
    for pattern in _QUALIFIER_PATTERNS:
        qualifiers.extend(match.group(1).strip() for match in pattern.finditer(str(text or "")))
    return qualifiers


def missing_critical_qualifiers(evidence_text: str, value: str) -> list[str]:
    normalized_value = _normalize(value)
    missing = []
    for qualifier in critical_qualifiers(evidence_text):
        # Remove conectivos, mas exige que o sujeito/escopo substantivo sobreviva.
        subject = re.sub(
            r"^(?:no\s+caso\s+de|para|somente\s+para|exceto)\s+",
            "",
            _normalize(qualifier),
        ).strip()
        if subject and subject not in normalized_value:
            missing.append(qualifier)
    return missing

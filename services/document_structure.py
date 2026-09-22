"""Reconhecimento estrutural local de seções de editais.

O módulo trabalha tanto durante o chunking quanto sobre metadados antigos em
memória. Assim, os ganhos de ranking não exigem reconstruir o índice FAISS.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def normalize_structure_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", value).strip().casefold()


SECTION_TITLES: tuple[tuple[str, str], ...] = (
    ("prazo_entrega", "do prazo e do local de entrega do objeto"),
    ("prazo_entrega", "do prazo de entrega"),
    ("objeto", "objeto da contratacao"),
    ("objeto", "do objeto"),
    ("objeto", "da contratacao"),
    ("habilitacao", "da habilitacao e do criterio de julgamento"),
    ("habilitacao", "dos documentos de habilitacao"),
    ("habilitacao", "da habilitacao"),
    ("recursos_financeiros", "dos recursos financeiros"),
    ("recursos_financeiros", "estimativa do valor da contratacao"),
    ("criterio_julgamento", "do criterio de julgamento"),
    ("regime_execucao", "do regime de execucao"),
    ("execucao", "da execucao"),
    ("contrato", "do contrato e suas alteracoes"),
    ("contrato", "do contrato"),
    ("participacao", "da participacao no credenciamento"),
    ("participacao", "da participacao"),
    ("preco", "do preco e condicoes de pagamento"),
    ("preco", "do preco"),
    ("pagamento", "do pagamento"),
    ("reajuste", "do reajuste"),
    ("vigencia", "da vigencia"),
    ("prazos", "dos prazos"),
    ("abertura", "da abertura"),
    ("entrega", "da entrega"),
    ("obrigacoes", "das obrigacoes"),
    ("sancoes", "das sancoes"),
    ("impugnacao", "da impugnacao"),
    ("recursos", "dos recursos"),
)

_TITLE_TO_TYPE = {title: section_type for section_type, title in SECTION_TITLES}
_TITLE_ALTERNATION = "|".join(
    re.escape(title) for _section_type, title in sorted(SECTION_TITLES, key=lambda item: len(item[1]), reverse=True)
)
_NUMBERED_HEADING_RE = re.compile(
    rf"(?<![a-z0-9])(?:(?P<number>\d{{1,2}}(?:\.\d+)*)\s*[.)-]?\s+)?"
    rf"(?P<title>{_TITLE_ALTERNATION})(?=\s*[.:;-]|\s+\d{{1,2}}(?:\.\d+)+\s*[.)-]?|$)",
    re.IGNORECASE,
)
_BARE_HEADING_RE = re.compile(
    r"(?<![a-z0-9])(?P<title>objeto|valor estimado|criterio de julgamento)\s*:",
    re.IGNORECASE,
)


def _toc_positions(headings: list[dict[str, Any]]) -> set[int]:
    """Marca sequências densas de títulos, normalmente pertencentes ao índice."""
    positions: set[int] = set()
    for index, heading in enumerate(headings):
        neighbours = sum(
            1
            for other in headings
            if abs(int(other["heading_start"]) - int(heading["heading_start"])) <= 700
        )
        if neighbours >= 4:
            positions.add(index)
    return positions


def extract_section_headings(text: str) -> list[dict[str, Any]]:
    normalized = normalize_structure_text(text)
    headings: list[dict[str, Any]] = []
    for match in _NUMBERED_HEADING_RE.finditer(normalized):
        title = match.group("title").strip()
        number = (match.group("number") or "").strip() or None
        headings.append(
            {
                "section_number": number.split(".", 1)[0] if number else None,
                "subsection_number": number if number and "." in number else None,
                "section_title": title.upper(),
                "section_type": _TITLE_TO_TYPE[title.casefold()],
                "heading_start": match.start(),
                "heading_end": match.end(),
                "is_toc": False,
            }
        )
    for match in _BARE_HEADING_RE.finditer(normalized):
        if any(abs(match.start() - int(item["heading_start"])) < 8 for item in headings):
            continue
        title = match.group("title").strip()
        section_type = {
            "objeto": "objeto",
            "valor estimado": "recursos_financeiros",
            "criterio de julgamento": "criterio_julgamento",
        }[title.casefold()]
        headings.append(
            {
                "section_number": None,
                "subsection_number": None,
                "section_title": title.upper(),
                "section_type": section_type,
                "heading_start": match.start(),
                "heading_end": match.end(),
                "is_toc": False,
            }
        )
    headings.sort(key=lambda item: int(item["heading_start"]))
    for index in _toc_positions(headings):
        headings[index]["is_toc"] = True
    return headings


def enrich_chunks_with_sections(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(chunks, key=lambda item: int(item.get("chunk_index") or 0))
    current: dict[str, Any] | None = None
    output: list[dict[str, Any]] = []
    for chunk in ordered:
        headings = extract_section_headings(str(chunk.get("text") or ""))
        substantive = [heading for heading in headings if not heading["is_toc"]]
        if substantive:
            current = substantive[-1]
        inherited = current if not substantive else None
        primary = substantive[-1] if substantive else inherited
        output.append(
            {
                **chunk,
                "section_headings": headings,
                "section_number": primary.get("section_number") if primary else chunk.get("section_number"),
                "subsection_number": primary.get("subsection_number") if primary else chunk.get("subsection_number"),
                "section_title": primary.get("section_title") if primary else chunk.get("section_title"),
                "section_type": primary.get("section_type") if primary else chunk.get("section_type"),
                "section_inherited": bool(inherited),
            }
        )
    return output

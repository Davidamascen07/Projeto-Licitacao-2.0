"""Perfil documental usado como contexto, nunca como hardcode de ausência."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKD", str(text or ""))
    value = "".join(character for character in value if not unicodedata.combining(character))
    return re.sub(r"\s+", " ", value).strip().casefold()


_FORMAL_MODALITIES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    (
        "edital_pregao",
        "pregao_eletronico",
        (
            r"\bmodalidade\s*:\s*pregao(?:\s+eletronico)?\b",
            r"\bedital\s+(?:n[ºo°.]?\s*\d+[^\n]{0,50})?[-–]?\s*pregao\s+eletronico\b",
            r"\bpregao\s+eletronico\s+(?:n[ºo°.]?\s*)?\d+\b",
            r"\bedital\b.{0,100}\bpregao\s+eletronico\b",
            r"\bpregao\s+eletronico\b.{0,80}\bedital\b",
        ),
    ),
    (
        "edital_concorrencia",
        "concorrencia_eletronica",
        (
            r"\bmodalidade\s*:\s*concorrencia(?:\s+eletronica)?\b",
            r"\bconcorrencia\s+eletronica\s+(?:n[ºo°.]?\s*)?\d+\b",
        ),
    ),
    (
        "edital_credenciamento",
        "credenciamento",
        (
            r"\bedital\s+de\s+credenciamento\b",
            r"\bcredenciamento(?:\s+de[^.;]{0,100})?\s+(?:n[ºo°.]?\s*)?\d+[/.-]\d+\b",
        ),
    ),
    (
        "edital_leilao",
        "leilao_eletronico",
        (
            r"\bedital\s+(?:de\s+)?leilao\b",
            r"\bleilao\s+(?:na\s+modalidade\s+)?eletronico\b",
        ),
    ),
    (
        "aviso_dispensa",
        "dispensa_licitacao",
        (r"\bdispensa\s+de\s+licitacao\b",),
    ),
)


def _formal_modality(head: str) -> tuple[str, str, str] | None:
    matches: list[tuple[int, str, str, str]] = []
    for document_type, modality, patterns in _FORMAL_MODALITIES:
        for pattern in patterns:
            match = re.search(pattern, head)
            if match:
                matches.append((match.start(), document_type, modality, match.group(0)))
    if not matches:
        return None
    _position, document_type, modality, evidence = min(matches, key=lambda item: item[0])
    return document_type, modality, evidence


def _nature(text: str) -> str:
    if re.search(r"\b(?:pavimentacao|construcao|reforma)\b", text):
        return "obra_engenharia"
    patterns = {
        "alienacao": r"\b(?:alienacao|leilao|arrematacao)\b",
        "obra_engenharia": r"\bobra\b",
        "bens": (
            r"\baquisicao(?:\s+e\s+instalacao)?\s+de\b|"
            r"\bfornecimento\s+de\b|\bmaterial\s+de\s+consumo\b"
        ),
        "servicos": (
            r"\b(?:prestacao|contratacao)\s+de\s+servicos?\b|"
            r"\bexecucao(?:\s+e\s+manutencao)?\s+de\s+servicos?\b|"
            r"\bservicos?\s+continuados?\b"
        ),
    }
    matches = [
        (match.start(), nature)
        for nature, pattern in patterns.items()
        if (match := re.search(pattern, text))
    ]
    return min(matches, default=(0, "indeterminada"), key=lambda item: item[0])[1]


def _object_context(head: str) -> str:
    patterns = (
        (0, r"\b(?:\d+(?:\.\d+)*\.?\s*)?do\s+objeto\s*:\s*(?:\d+(?:\.\d+)*\.?\s*)?(.{0,1800})"),
        (0, r"\bobjeto\s*:\s*(.{0,1800})"),
        (1, r"\b(?:tem\s+por\s+objeto|constitui\s+objeto(?:\s+da\s+presente\s+licitacao)?)\s*:?[ ]*(.{0,1800})"),
        (2, r"\b(?:1(?:\.0)?\.?\s*)?do\s+objeto\b(.{0,1800})"),
    )
    candidates = []
    for priority, pattern in patterns:
        for match in list(re.finditer(pattern, head))[:8]:
            candidates.append((priority, match.start(), match.group(1)))
    for _priority, _position, candidate in sorted(candidates, key=lambda item: (item[0], item[1])):
        if _nature(candidate) != "indeterminada":
            return candidate
    return head[:30000]


def classify_document_profile(chunks: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(chunks, key=lambda chunk: (int(chunk.get("page_start") or 999999), int(chunk.get("chunk_index") or 0)))
    preamble_chunks = [chunk for chunk in ordered if int(chunk.get("page_start") or 999999) <= 4][:4]
    preamble = " ".join(str(chunk.get("text") or "") for chunk in (preamble_chunks or ordered[:3]))
    full_text = " ".join(str(chunk.get("text") or "") for chunk in chunks)
    head = _normalize(preamble[:30000])
    body = _normalize(full_text)
    formal = _formal_modality(head)
    title_is_reference = bool(re.search(r"\btermo\s+de\s+referencia\b", head[:2500]))
    contains_edital = bool(re.search(r"\bedital\b", head[:5000]))
    if title_is_reference and not contains_edital:
        document_type = "termo_referencia"
        classification_reason = "Título formal TERMO DE REFERÊNCIA no preâmbulo."
    elif formal:
        document_type = formal[0]
        classification_reason = f"Modalidade formal identificada no preâmbulo: {formal[2]}."
    else:
        document_type = "documento_contratacao"
        classification_reason = "Nenhum título/modalidade formal suficientemente específico no preâmbulo."

    object_nature = _nature(_object_context(head))
    justification_match = re.search(r"\bjustific(?:ativa|a-se)\b(.{0,3500})", body)
    justification_nature = _nature(justification_match.group(1)) if justification_match else "indeterminada"
    justification_consistent = (
        justification_nature == "indeterminada"
        or object_nature == "indeterminada"
        or justification_nature == object_nature
    )
    formal_modality = formal[1] if formal else ("dispensa_licitacao" if "dispensa de licitacao" in head else None)

    table_heavy = bool(
        re.search(r"(?:tabela|planilha|quadro\s+de\s+itens|relacao\s+dos?\s+lotes?)", body)
        and len(re.findall(r"r\$\s*[\d.]+,\d{2}", body)) >= 3
    )
    return {
        "document_type": document_type,
        "formal_modality": formal_modality,
        "classification_reason": classification_reason,
        "object_nature": object_nature,
        "justification_nature": justification_nature,
        "justification_consistent": justification_consistent,
        "profile_consistent": bool(document_type == "termo_referencia" or formal or document_type == "documento_contratacao"),
        "table_heavy": table_heavy,
        "has_annex": bool(re.search(r"\banexo\b", body)),
        "execution_on_demand": bool(re.search(r"sob\s+demanda|ordem\s+de\s+servico", body)),
    }

from __future__ import annotations

import hashlib
import re
import unicodedata
from typing import Any

from .config import CHUNK_OVERLAP_WORDS, CHUNK_SIZE_WORDS
from .document_structure import extract_section_headings


def _normalize_structure_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", text)
    return "".join(character for character in value if not unicodedata.combining(character)).casefold()


def _structure_metadata(text: str, chunk_index: int, page_start: int, current_part: str) -> dict[str, Any]:
    document_part = "edital_principal" if page_start <= 5 else current_part
    headings = list(re.finditer(r"\bANEXO\s+[IVXLCDM]+\s*(?:[-–—]\s*)?(.{0,140})", text))
    if page_start > 5 and headings:
        title = _normalize_structure_text(headings[-1].group(1))
        if "termo de referencia" in title:
            document_part = "termo_referencia"
        elif "minuta" in title and "ata de registro de precos" in title:
            document_part = "ata_registro_precos"
        elif "minuta" in title and "contrato" in title:
            document_part = "minuta_contrato"
        elif "modelo" in title or "declarac" in title:
            document_part = "modelo_declaracao"
    heading_match = re.search(
        r"(OBJETO|VALOR ESTIMADO|CRIT[ÉE]RIO DE JULGAMENTO|TERMO DE REFER[ÊE]NCIA|"
        r"ANEXO\s+[IVXLCDM]+|MINUTA[^.;]{0,80})\s*:?",
        text[:1200],
        re.IGNORECASE,
    )
    section_headings = extract_section_headings(text)
    substantive = [item for item in section_headings if not item["is_toc"]]
    primary = substantive[-1] if substantive else None
    return {
        "document_part": document_part,
        "section": "dados_do_edital" if page_start <= 2 else document_part,
        "heading": heading_match.group(1).strip() if heading_match else None,
        "section_headings": section_headings,
        "section_number": primary.get("section_number") if primary else None,
        "subsection_number": primary.get("subsection_number") if primary else None,
        "section_title": primary.get("section_title") if primary else None,
        "section_type": primary.get("section_type") if primary else None,
        "section_inherited": False,
        "is_preamble": chunk_index == 0,
    }


def chunk_pages(
    pages: list[dict[str, Any]],
    filename: str,
    document_id: str | None = None,
    chunk_size_words: int = CHUNK_SIZE_WORDS,
    overlap_words: int = CHUNK_OVERLAP_WORDS,
) -> list[dict[str, Any]]:
    if chunk_size_words < 1 or overlap_words < 0 or overlap_words >= chunk_size_words:
        raise ValueError("Configuração de chunk inválida.")
    word_page_pairs = [
        (word, page["page"])
        for page in pages
        for word in str(page.get("text", "")).split()
    ]
    if not word_page_pairs:
        return []
    chunks: list[dict[str, Any]] = []
    step = chunk_size_words - overlap_words
    current_part = "edital_principal"
    for start in range(0, len(word_page_pairs), step):
        window = word_page_pairs[start : start + chunk_size_words]
        words = [word for word, _page in window]
        page_numbers = [page for _word, page in window]
        chunk_index = len(chunks)
        identity = f"{document_id or filename}:{chunk_index}:{' '.join(words)[:200]}"
        text = " ".join(words)
        structure = _structure_metadata(text, chunk_index, min(page_numbers), current_part)
        current_part = structure["document_part"]
        chunks.append(
            {
                "chunk_id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                "document_id": document_id,
                "filename": filename,
                "chunk_index": chunk_index,
                "text": text,
                "page_start": min(page_numbers),
                "page_end": max(page_numbers),
                **structure,
            }
        )
        if start + chunk_size_words >= len(word_page_pairs):
            break
    return chunks

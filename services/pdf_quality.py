"""Auditoria local de qualidade textual de PDFs, sem executar OCR."""

from __future__ import annotations

import re
import statistics
from pathlib import Path
from typing import Any

import fitz


FIELD_MARKERS = {
    "objeto": ("objeto", "tem por objeto", "finalidade"),
    "modalidade": ("pregão", "concorrência", "leilão", "credenciamento", "dispensa de licitação"),
    "valor_estimado": ("valor estimado", "valor mínimo", "avaliação", "preço mínimo"),
    "prazo_entrega_proposta": ("validade da proposta", "validade das propostas"),
    "orgao_responsavel": ("contratante", "prefeitura", "secretaria", "ministério", "fundo municipal"),
    "uf": ("estado do", "estado de", "/rs", "/mg", "/ba", "/sp", "/go"),
    "criterio_julgamento": ("critério de julgamento", "maior lance", "menor preço", "maior oferta"),
    "prazo_execucao": ("prazo de execução", "prazo de entrega", "ordem de serviço"),
    "requisitos_habilitacao": ("habilitação", "documentos exigidos"),
}


def _heading_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip()
        and (
            re.match(r"^(?:\d+(?:\.\d+)*\.?\s+)?(?:DO|DA|DOS|DAS|OBJETO|EDITAL|TERMO|ANEXO)\b", line, re.IGNORECASE)
            or (len(line) <= 120 and sum(ch.isupper() for ch in line) >= max(8, int(sum(ch.isalpha() for ch in line) * 0.75)))
        )
    ]


def audit_pdf_text(path: str | Path) -> dict[str, Any]:
    """Mede a camada textual. Não renderiza página e nunca chama Tesseract."""
    pdf_path = Path(path)
    page_rows = []
    headings: list[dict[str, Any]] = []
    all_text: list[str] = []
    image_pages = 0
    with fitz.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            text = page.get_text("text") or ""
            all_text.append(text)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            characters = len(text)
            words = len(re.findall(r"\w+", text, re.UNICODE))
            alphabetic = sum(ch.isalpha() for ch in text)
            replacements = text.count("\ufffd")
            has_images = bool(page.get_images(full=True))
            image_pages += int(has_images)
            page_rows.append(
                {
                    "page": page_number,
                    "characters": characters,
                    "words": words,
                    "alphabetic_ratio": alphabetic / max(characters, 1),
                    "replacement_character_ratio": replacements / max(characters, 1),
                    "average_line_length": sum(map(len, lines)) / max(len(lines), 1),
                    "has_images": has_images,
                }
            )
            headings.extend({"page": page_number, "text": line} for line in _heading_lines(text)[:8])
    combined = "\n".join(all_text).casefold()
    pages = len(page_rows)
    chars_per_page = statistics.mean(row["characters"] for row in page_rows) if page_rows else 0.0
    words_per_page = statistics.mean(row["words"] for row in page_rows) if page_rows else 0.0
    empty_page_ratio = sum(row["characters"] < 20 for row in page_rows) / max(pages, 1)
    possible_scanned = pages >= 3 and (chars_per_page < 100 or empty_page_ratio > 0.7)
    apparent_fields = [
        field
        for field, markers in FIELD_MARKERS.items()
        if any(marker.casefold() in combined for marker in markers)
    ]
    if possible_scanned and image_pages / max(pages, 1) > 0.7:
        classification = "SCANNED_NO_OCR"
    elif statistics.mean(row["replacement_character_ratio"] for row in page_rows) > 0.01:
        classification = "OCR_LOW_QUALITY"
    elif chars_per_page < 250 and not possible_scanned:
        classification = "TEXT_FRAGMENTED"
    elif not apparent_fields:
        classification = "FIELDS_ACTUALLY_ABSENT"
    else:
        classification = "TEXT_OK"
    return {
        "file": pdf_path.name,
        "classification": classification,
        "pages": pages,
        "characters": sum(row["characters"] for row in page_rows),
        "chars_per_page": round(chars_per_page, 2),
        "words_per_page": round(words_per_page, 2),
        "alphabetic_ratio": round(statistics.mean(row["alphabetic_ratio"] for row in page_rows), 4),
        "replacement_character_ratio": round(statistics.mean(row["replacement_character_ratio"] for row in page_rows), 6),
        "average_line_length": round(statistics.mean(row["average_line_length"] for row in page_rows), 2),
        "empty_page_ratio": round(empty_page_ratio, 4),
        "possible_scanned_document": possible_scanned,
        "text_layer_present": chars_per_page >= 100,
        "ocr_required": possible_scanned,
        "pages_with_images": image_pages,
        "headings": headings,
        "apparent_fields": apparent_fields,
    }

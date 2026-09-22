import os
from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

from .chunking import chunk_pages
from .config import ALLOWED_EXTENSIONS


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def has_pdf_signature(path):
    """Valida a assinatura, sem confiar somente na extensão."""
    try:
        with Path(path).open("rb") as handle:
            return handle.read(5) == b"%PDF-"
    except OSError:
        return False


def validate_pdf_file(path):
    if not has_pdf_signature(path):
        raise ValueError("O arquivo não possui uma assinatura PDF válida.")
    try:
        with fitz.open(path) as document:
            if document.page_count < 1:
                raise ValueError("O PDF não contém páginas.")
            return document.page_count
    except (fitz.FileDataError, RuntimeError) as exc:
        raise ValueError("PDF inválido, corrompido ou protegido de forma incompatível.") from exc


def ocr_extract_text_from_page(page):
    pix = page.get_pixmap()
    mode = "RGBA" if pix.alpha else "RGB"
    img = Image.frombytes(mode, [pix.width, pix.height], pix.samples)

    try:
        return pytesseract.image_to_string(img, lang="por+eng")
    except pytesseract.TesseractNotFoundError as e:
        raise RuntimeError(
            "Tesseract OCR não está instalado ou não está no PATH. Instale o Tesseract e tente novamente."
        ) from e


def extract_pages_from_pdf(pdf_path):
    """Extrai o texto do PDF preservando a numeração de página.

    Retorna uma lista de dicts: [{"page": 1, "text": "..."}, ...]
    Faz fallback para OCR em páginas sem texto pesquisável.
    """
    validate_pdf_file(pdf_path)
    filename = os.path.basename(pdf_path)
    pages = []
    with fitz.open(pdf_path) as doc:
        for page_number, page in enumerate(doc, start=1):
            page_text = page.get_text("text")
            if not page_text.strip():
                print(f"[INFO] Página {page_number} de {filename} não tem texto pesquisável; aplicando OCR de fallback.")
                page_text = ocr_extract_text_from_page(page)
                if not page_text.strip():
                    print(f"[WARN] OCR não retornou texto para a página {page_number} de {filename}.")
            pages.append({"page": page_number, "text": page_text})

    if not any(p["text"].strip() for p in pages):
        print(f"[WARN] O PDF '{filename}' não retornou texto pesquisável nem OCR. Verifique o arquivo.")

    return pages


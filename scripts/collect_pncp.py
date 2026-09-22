from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.pncp_service import DEFAULT_DOWNLOAD_DIR, PNCPClient  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Consulta e coleta reproduzível de documentos no PNCP.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    search = subparsers.add_parser("search", help="Consulta contratações por publicação.")
    search.add_argument("--start", required=True, help="Data inicial AAAAMMDD.")
    search.add_argument("--end", required=True, help="Data final AAAAMMDD.")
    search.add_argument("--modality", required=True, type=int, help="Código PNCP da modalidade.")
    search.add_argument("--page", type=int, default=1)
    search.add_argument("--uf")
    search.add_argument("--output", type=Path)

    download = subparsers.add_parser("download", help="Baixa PDFs de uma contratação identificada.")
    download.add_argument("--cnpj", required=True)
    download.add_argument("--year", required=True, type=int)
    download.add_argument("--sequence", required=True, type=int)
    download.add_argument("--output-dir", type=Path, default=DEFAULT_DOWNLOAD_DIR)
    download.add_argument("--limit", type=int)

    args = parser.parse_args()
    client = PNCPClient()
    if args.command == "search":
        result = client.search_publications(
            start_date=args.start,
            end_date=args.end,
            modality_code=args.modality,
            page=args.page,
            uf=args.uf,
        )
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        else:
            print(rendered, end="")
        return 0

    documents = client.list_documents(cnpj=args.cnpj, year=args.year, sequence=args.sequence)
    pdf_documents = [
        document
        for document in documents
        if "pdf" in str(document.get("url") or "").lower()
        or "edital" in str(document.get("titulo") or "").lower()
        or "pdf" in str(document.get("tipoDocumentoNome") or "").lower()
    ]
    selected = pdf_documents[: args.limit] if args.limit else pdf_documents
    entries = [
        client.download_document(
            cnpj=args.cnpj,
            year=args.year,
            sequence=args.sequence,
            document=document,
            output_dir=args.output_dir,
        )
        for document in selected
    ]
    print(json.dumps({"available": len(documents), "downloaded": entries}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


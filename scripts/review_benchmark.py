from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.benchmark import BENCHMARK_PATH, CRITICAL_FIELDS, pending_review_report, validate_benchmark  # noqa: E402
from evaluation.benchmark_review import (  # noqa: E402
    ReviewImportError,
    apply_review_payload,
    load_review_payload,
    merge_review_payloads,
)
from services.config import PROJECT_ROOT  # noqa: E402
from services.document_manifest import load_manifest  # noqa: E402
from services.evidence import literal_is_present, normalize_literal  # noqa: E402
from services.storage_utils import atomic_write_json, backup_files, load_json, utc_now  # noqa: E402


def _page_text(document_id: str, page_number: int) -> str:
    import fitz

    manifest = load_manifest()
    record = next(doc for doc in manifest["documents"] if doc.get("document_id") == document_id)
    path = PROJECT_ROOT / record["relative_path"]
    with fitz.open(path) as pdf:
        if page_number < 1 or page_number > pdf.page_count:
            raise ValueError("Página fora do intervalo do PDF.")
        return pdf[page_number - 1].get_text("text")


def interactive_review(path: Path) -> None:
    benchmark = load_json(path, {})
    pending = pending_review_report(benchmark)
    if not pending:
        print("Nenhuma anotação pendente.")
        return
    for item in pending:
        print(f"\n{item['filename']}\nID: {item['document_id']}")
        document = next(doc for doc in benchmark["documents"] if doc["document_id"] == item["document_id"])
        for field in item["pending_reference_fields"]:
            if input(f"Revisar {field}? [s/N] ").strip().casefold() != "s":
                continue
            value = input("Valor confirmado: ").strip()
            page = int(input("Página (1-based): ").strip())
            evidence = input("Trecho literal da página: ").strip()
            page_text = _page_text(item["document_id"], page)
            if not literal_is_present(evidence, page_text):
                print("Trecho não encontrado literalmente; anotação não foi validada.")
                continue
            reviewer = input("Identificador do revisor humano: ").strip()
            if not reviewer:
                print("Revisor obrigatório; anotação não foi salva.")
                continue
            document["references"][field] = {
                "value": value,
                "normalized_value": normalize_literal(value),
                "page": page,
                "evidence_text": evidence,
                "validated_by_human": True,
                "validated_by": reviewer,
                "validated_at": utc_now(),
            }
        if all(document["references"][field].get("validated_by_human") for field in CRITICAL_FIELDS):
            document["annotation_status"] = "validated"
    benchmark["updated_at"] = utc_now()
    atomic_write_json(path, benchmark)


def main() -> int:
    parser = argparse.ArgumentParser(description="Revisa referências com validação literal por página.")
    parser.add_argument("--benchmark", default=str(BENCHMARK_PATH))
    parser.add_argument("--report", action="store_true")
    parser.add_argument(
        "--import-json",
        action="append",
        default=[],
        metavar="ARQUIVO",
        help="Importa uma ou mais revisões JSON e valida os trechos nos PDFs.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Valida a importação sem alterar o benchmark.")
    args = parser.parse_args()
    path = Path(args.benchmark)
    benchmark = load_json(path, {})
    errors = validate_benchmark(benchmark)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    if args.import_json:
        try:
            payloads = [load_review_payload(source) for source in args.import_json]
            merged, overridden = merge_review_payloads(payloads)
            updated, import_report = apply_review_payload(benchmark, merged)
            import_report["overridden_documents"] = overridden
            import_report["dry_run"] = args.dry_run
            if not args.dry_run:
                backup = backup_files([path], "benchmark-review-import")
                atomic_write_json(path, updated)
                import_report["backup_path"] = str(backup) if backup else None
            print(json.dumps(import_report, ensure_ascii=False, indent=2))
        except ReviewImportError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    elif args.report:
        print(json.dumps(pending_review_report(benchmark), ensure_ascii=False, indent=2))
    else:
        interactive_review(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

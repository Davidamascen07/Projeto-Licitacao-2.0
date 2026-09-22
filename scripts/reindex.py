from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.vector_store import init_vector_store, inventory_documents, synchronize_documents  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza PDFs, manifesto, chunks e FAISS.")
    parser.add_argument("--document-id")
    parser.add_argument("--rebuild-all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--inventory-only", action="store_true", help="Atualiza somente o manifesto, sem embeddings.")
    args = parser.parse_args()
    init_vector_store()
    if args.inventory_only:
        report = inventory_documents(dry_run=args.dry_run)
    else:
        report = synchronize_documents(
            document_id=args.document_id,
            rebuild_all=args.rebuild_all,
            dry_run=args.dry_run,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report.get("failed") else 0


if __name__ == "__main__":
    raise SystemExit(main())

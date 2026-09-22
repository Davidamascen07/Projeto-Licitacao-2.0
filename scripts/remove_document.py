from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.vector_store import init_vector_store, remove_document  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Remove um documento do índice, preservando o PDF e criando backup.")
    parser.add_argument("document_id")
    args = parser.parse_args()
    init_vector_store()
    print(json.dumps(remove_document(args.document_id), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

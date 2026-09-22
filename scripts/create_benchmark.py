from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.benchmark import BENCHMARK_PATH, create_benchmark, pending_review_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Cria benchmark determinístico sem fabricar referências.")
    parser.add_argument("--max-documents", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=str(BENCHMARK_PATH))
    args = parser.parse_args()
    benchmark = create_benchmark(args.output, max_documents=args.max_documents, seed=args.seed)
    print(json.dumps({"documents": len(benchmark["documents"]), "pending_review": pending_review_report(benchmark)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None


def _repo_id(model_name: str) -> str:
    return model_name if "/" in model_name else f"sentence-transformers/{model_name}"


def prepare_model(*, offline_check: bool = False) -> dict[str, object]:
    if load_dotenv is not None:
        load_dotenv(ROOT / ".env")
    model_name = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")

    if offline_check:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
    else:
        os.environ.pop("HF_HUB_OFFLINE", None)
        os.environ.pop("TRANSFORMERS_OFFLINE", None)

    from huggingface_hub import snapshot_download
    from sentence_transformers import SentenceTransformer

    snapshot = Path(
        snapshot_download(
            _repo_id(model_name),
            local_files_only=offline_check,
        )
    ).resolve()
    model = SentenceTransformer(str(snapshot), local_files_only=True)
    dimension = int(model.get_sentence_embedding_dimension())
    if dimension != 384:
        raise RuntimeError(f"Dimensão inesperada do modelo: {dimension}.")
    return {
        "model": model_name,
        "snapshot": snapshot.name,
        "dimension": dimension,
        "mode": "offline_check" if offline_check else "download_or_refresh",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara o modelo local de embeddings.")
    parser.add_argument(
        "--offline-check",
        action="store_true",
        help="Valida somente o cache existente, sem qualquer acesso à rede.",
    )
    args = parser.parse_args()
    try:
        result = prepare_model(offline_check=args.offline_check)
    except Exception as exc:
        print(f"ERRO: modelo de embeddings indisponível ({type(exc).__name__}).")
        return 1
    print(
        "OK: "
        f"modelo={result['model']} "
        f"snapshot={result['snapshot']} "
        f"dimensão={result['dimension']} "
        f"modo={result['mode']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

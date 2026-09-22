from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.metadata
import itertools
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluation.baselines import run_llm_no_retrieval_batched, run_regex_baseline  # noqa: E402
from evaluation.benchmark import BENCHMARK_PATH, CRITICAL_FIELDS, validate_benchmark  # noqa: E402
from evaluation.experiment_store import ExperimentalIndex  # noqa: E402
from evaluation.metrics import aggregate_rows  # noqa: E402
from evaluation.ragas_metrics import score_ragas_rows  # noqa: E402
from evaluation.reporting import RESULTS_DIR, write_result_artifacts  # noqa: E402
from services.config import GROQ_MODEL_NAME  # noqa: E402
from services.extraction_service import FIELD_QUESTIONS, extract_multiple_fields  # noqa: E402
from services.storage_utils import atomic_write_json, load_json, utc_now  # noqa: E402

EXPERIMENT_CONFIG_PATH = Path(__file__).with_name("experiments.json")
SELECTED_CONFIG_PATH = RESULTS_DIR / "selected_config.json"
SELECTION_PRIORITY = (
    "answer_correctness_desc",
    "faithfulness_desc",
    "hallucination_rate_asc",
    "estimated_cost_asc",
    "total_ms_asc",
)
VALID_APPROACHES = ("regex", "llm_no_retrieval", "rag")


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def default_output_dir(split: str) -> Path:
    return RESULTS_DIR / split


def normalize_approaches(approaches: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    selected = tuple(dict.fromkeys(approaches or VALID_APPROACHES))
    invalid = [approach for approach in selected if approach not in VALID_APPROACHES]
    if invalid:
        raise ValueError(f"Abordagens desconhecidas: {', '.join(invalid)}")
    if not selected:
        raise ValueError("Ao menos uma abordagem deve ser selecionada.")
    return selected


def result_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return tuple(
        str(row.get(key) or "")
        for key in ("split", "approach", "config_id", "document_id", "field")
    )


def configurations(config_path: str | Path = EXPERIMENT_CONFIG_PATH) -> list[dict[str, int | str]]:
    settings = load_json(config_path, {})
    output = []
    for chunk_size, overlap, top_k in itertools.product(
        settings["chunk_sizes"], settings["overlaps"], settings["top_ks"]
    ):
        output.append(
            {
                "config_id": f"chunk{chunk_size}_overlap{overlap}_topk{top_k}",
                "chunk_size": int(chunk_size),
                "overlap": int(overlap),
                "top_k": int(top_k),
            }
        )
    return output


def _base_row(
    result: dict[str, Any],
    *,
    document: dict[str, Any],
    field: str,
    approach: str,
    config_id: str,
    split: str,
) -> dict[str, Any]:
    return {
        **result,
        "document_id": document["document_id"],
        "filename": document["filename"],
        "field": field,
        "question": FIELD_QUESTIONS[field],
        "reference": document["references"][field],
        "approach": approach,
        "config_id": config_id,
        "split": split,
        "evaluated_at": utc_now(),
    }


def _score(row: dict[str, Any], skip_ragas: bool) -> dict[str, Any]:
    if skip_ragas or not row.get("answered"):
        row.update({"faithfulness": None, "answer_correctness": None, "ragas_error": "skipped"})
    else:
        row.update({"faithfulness": None, "answer_correctness": None, "ragas_error": "pending"})
    return row


def choose_configuration(rows: list[dict[str, Any]]) -> dict[str, Any]:
    rag_rows = [row for row in rows if row.get("approach") == "rag" and row.get("split") == "development"]
    summaries = aggregate_rows(rag_rows, ("config_id",))
    usable = [item for item in summaries if item["answer_correctness"]["count"] > 0]
    if not usable:
        return {
            "status": "insufficient_validated_references",
            "selected_config_id": None,
            "selection_priority": list(SELECTION_PRIORITY),
            "reason": "Nenhuma configuração possui Answer Correctness calculada com referência humana validada.",
        }

    def ranking(item: dict[str, Any]) -> tuple[float, float, float, float, float]:
        return (
            -(item["answer_correctness"]["mean"] or 0),
            -(item["faithfulness"]["mean"] or 0),
            item["hallucination_rate"] if item["hallucination_rate"] is not None else 1.0,
            item["estimated_cost"]["mean"] if item["estimated_cost"]["mean"] is not None else float("inf"),
            item["total_ms"]["mean"] if item["total_ms"]["mean"] is not None else float("inf"),
        )

    selected = min(usable, key=ranking)
    return {
        "status": "selected_on_development",
        "selected_config_id": selected["config_id"],
        "selection_priority": list(SELECTION_PRIORITY),
        "summary": selected,
    }


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in ("ragas", "llama-index", "llama-index-llms-groq", "sentence-transformers", "faiss-cpu"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def run(
    benchmark_path: str | Path,
    *,
    split: str,
    output_dir: str | Path | None = None,
    skip_ragas: bool = False,
    selected_config_path: str | Path = SELECTED_CONFIG_PATH,
    approaches: tuple[str, ...] | list[str] | None = None,
    llm_client: Any | None = None,
    embedding_model: Any | None = None,
) -> list[dict[str, Any]]:
    started = time.perf_counter()
    destination = Path(output_dir) if output_dir is not None else default_output_dir(split)
    active_approaches = normalize_approaches(approaches)
    destination.mkdir(parents=True, exist_ok=True)
    checkpoint_path = destination / "checkpoint_results.json"
    benchmark = load_json(benchmark_path, {})
    errors = validate_benchmark(benchmark)
    if errors:
        raise ValueError("Benchmark inválido: " + "; ".join(errors))
    documents = [doc for doc in benchmark["documents"] if doc.get("split") == split]
    if not documents:
        raise ValueError(f"Nenhum documento no split {split}.")
    configs = configurations()
    selection_path = Path(selected_config_path)
    if split == "test":
        selected = load_json(selection_path, {})
        selected_id = selected.get("selected_config_id")
        if not selected_id or selected.get("source_split") != "development":
            raise ValueError("Configuração final não selecionada exclusivamente no desenvolvimento.")
        configs = [config for config in configs if config["config_id"] == selected_id]
        if len(configs) != 1:
            raise ValueError(f"Configuração selecionada desconhecida: {selected_id}")
        selection_hash_before = sha256_file(selection_path)
    else:
        selection_hash_before = None

    rows = load_json(checkpoint_path, [])
    if not isinstance(rows, list) or any(row.get("split") != split for row in rows):
        raise ValueError(f"Checkpoint incompatível com o split {split}: {checkpoint_path}")
    completed = {result_key(row) for row in rows}
    if len(completed) != len(rows):
        raise ValueError(f"Checkpoint contém resultados duplicados: {checkpoint_path}")

    def save_row(row: dict[str, Any]) -> None:
        key = result_key(row)
        if key in completed:
            return
        rows.append(row)
        completed.add(key)
        atomic_write_json(checkpoint_path, rows)

    if "regex" in active_approaches:
        for document in documents:
            regex_missing = [
                field
                for field in CRITICAL_FIELDS
                if (split, "regex", "baseline_regex", document["document_id"], field) not in completed
            ]
            if regex_missing:
                for field, result in run_regex_baseline(document["document_id"]).items():
                    if field in regex_missing:
                        save_row(
                            _score(
                                _base_row(
                                    result,
                                    document=document,
                                    field=field,
                                    approach="regex",
                                    config_id="baseline_regex",
                                    split=split,
                                ),
                                skip_ragas,
                            )
                        )

    if "llm_no_retrieval" in active_approaches:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            baseline_futures = {}
            for document in documents:
                missing_fields = [
                    field
                    for field in CRITICAL_FIELDS
                    if (split, "llm_no_retrieval", "baseline_llm", document["document_id"], field) not in completed
                ]
                if missing_fields:
                    future = executor.submit(run_llm_no_retrieval_batched, document["document_id"], llm_client)
                    baseline_futures[future] = (document, missing_fields)
            for future in concurrent.futures.as_completed(baseline_futures):
                document, missing_fields = baseline_futures[future]
                for field, result in future.result().items():
                    if field in missing_fields:
                        save_row(
                            _score(
                                _base_row(
                                    result,
                                    document=document,
                                    field=field,
                                    approach="llm_no_retrieval",
                                    config_id="baseline_llm",
                                    split=split,
                                ),
                                skip_ragas,
                            )
                        )

    pages_cache: dict[str, list[dict[str, Any]]] = {}
    document_ids = [doc["document_id"] for doc in documents]
    for config in configs if "rag" in active_approaches else []:
        missing = {
            (document["document_id"], field)
            for document in documents
            for field in CRITICAL_FIELDS
            if (split, "rag", str(config["config_id"]), document["document_id"], field) not in completed
        }
        if not missing:
            continue
        store = ExperimentalIndex(
            document_ids,
            chunk_size=int(config["chunk_size"]),
            overlap=int(config["overlap"]),
            embedding_model=embedding_model,
            pages_cache=pages_cache,
        )
        def extract_document(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
            return extract_multiple_fields(
                {field: FIELD_QUESTIONS[field] for field in CRITICAL_FIELDS},
                document["document_id"],
                top_k=int(config["top_k"]),
                llm_client=llm_client,
                search_fn=store.search,
                preamble_fn=store.preambles,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            rag_futures = {
                executor.submit(extract_document, document): (
                    document,
                    [field for field in CRITICAL_FIELDS if (document["document_id"], field) in missing],
                )
                for document in documents
                if any((document["document_id"], field) in missing for field in CRITICAL_FIELDS)
            }
            for future in concurrent.futures.as_completed(rag_futures):
                document, missing_fields = rag_futures[future]
                for field, result in future.result().items():
                    if field not in missing_fields:
                        continue
                    row = _base_row(
                        result,
                        document=document,
                        field=field,
                        approach="rag",
                        config_id=str(config["config_id"]),
                        split=split,
                    )
                    row["configuration"] = config
                    save_row(_score(row, skip_ragas))

    approach_multiplier = int("regex" in active_approaches) + int("llm_no_retrieval" in active_approaches)
    approach_multiplier += len(configs) if "rag" in active_approaches else 0
    expected_rows = len(documents) * len(CRITICAL_FIELDS) * approach_multiplier
    if len(rows) != expected_rows:
        raise RuntimeError(f"Execução incompleta: {len(rows)}/{expected_rows} resultados no split {split}.")
    if not skip_ragas:
        for expects_reference in (True, False):
            pending = [
                row
                for row in rows
                if row.get("answered")
                and row.get("ragas_error") not in {None, "skipped"}
                and (
                    bool((row.get("reference") or {}).get("validated_by_human"))
                    and (row.get("reference") or {}).get("value") is not None
                )
                == expects_reference
            ]
            # Uma amostra por checkpoint: no plano gratuito, limites de TPM/TPD
            # podem interromper o avaliador a qualquer momento.
            for start in range(0, len(pending), 1):
                batch = pending[start : start + 1]
                for row, metrics in zip(batch, score_ragas_rows(batch)):
                    row.update(metrics)
                atomic_write_json(checkpoint_path, rows)
                if batch[0].get("ragas_error") is not None:
                    raise RuntimeError(
                        "RAGAS interrompido; checkpoint preservado. "
                        f"Erro: {batch[0]['ragas_error']}"
                    )
        failures = [
            row
            for row in rows
            if row.get("answered")
            and (
                row.get("faithfulness") is None
                or (
                    (row.get("reference") or {}).get("validated_by_human")
                    and (row.get("reference") or {}).get("value") is not None
                    and row.get("answer_correctness") is None
                )
            )
        ]
        if failures:
            raise RuntimeError(
                f"RAGAS não produziu todas as métricas obrigatórias: {len(failures)} falhas; "
                f"primeiro erro={failures[0].get('ragas_error')}"
            )
    write_result_artifacts(rows, destination)

    if split == "development":
        selection = choose_configuration(rows)
        selection.update(
            {
                "created_at": utc_now(),
                "source_split": "development",
                "benchmark_sha256": sha256_file(benchmark_path),
                "experiments_sha256": sha256_file(EXPERIMENT_CONFIG_PATH),
            }
        )
        atomic_write_json(selection_path, selection)
        selection_hash_after = sha256_file(selection_path)
        Path(str(selection_path) + ".sha256").write_text(selection_hash_after + "\n", encoding="ascii")
    else:
        selection_hash_after = sha256_file(selection_path)
        if selection_hash_after != selection_hash_before:
            raise RuntimeError("selected_config.json mudou durante a execução do teste.")

    atomic_write_json(
        destination / "run_metadata.json",
        {
            "split": split,
            "completed_at": utc_now(),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "python": platform.python_version(),
            "packages": _package_versions(),
            "model": GROQ_MODEL_NAME,
            "benchmark_sha256": sha256_file(benchmark_path),
            "experiments_sha256": sha256_file(EXPERIMENT_CONFIG_PATH),
            "selected_config_sha256": selection_hash_after,
            "rows": len(rows),
            "skip_ragas": skip_ragas,
            "approaches": list(active_approaches),
        },
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Executa baselines e as 12 configurações RAG.")
    parser.add_argument("--benchmark", default=str(BENCHMARK_PATH))
    parser.add_argument("--split", choices=("development", "test"), default="development")
    parser.add_argument("--output-dir", default=None, help="Padrão: evaluation/results/<split>.")
    parser.add_argument("--skip-ragas", action="store_true", help="Somente diagnóstico; não produz métricas acadêmicas.")
    parser.add_argument("--selected-config", default=str(SELECTED_CONFIG_PATH))
    parser.add_argument(
        "--approach",
        action="append",
        choices=VALID_APPROACHES,
        dest="approaches",
        help="Limita a execução; pode ser repetido. O padrão executa todas as abordagens.",
    )
    args = parser.parse_args()
    rows = run(
        args.benchmark,
        split=args.split,
        output_dir=args.output_dir,
        skip_ragas=args.skip_ragas,
        selected_config_path=args.selected_config,
        approaches=args.approaches,
    )
    print(
        json.dumps(
            {"rows": len(rows), "output_dir": str(args.output_dir or default_output_dir(args.split))},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

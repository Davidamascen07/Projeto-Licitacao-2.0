from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from services.storage_utils import atomic_write_json, utc_now

from .metrics import aggregate_rows

RESULTS_DIR = Path(__file__).with_name("results")


def _flatten_summary(summary: dict[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in summary.items():
        if isinstance(value, dict):
            for subkey, subvalue in value.items():
                flat[f"{key}_{subkey}"] = subvalue
        else:
            flat[key] = value
    return flat


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flattened = [_flatten_summary(row) for row in rows]
    fields = sorted({field for row in flattened for field in row})
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(flattened)


def write_result_artifacts(rows: list[dict[str, Any]], output_dir: str | Path = RESULTS_DIR) -> dict[str, str]:
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    by_field = aggregate_rows(rows, ("approach", "config_id", "field"))
    by_document = aggregate_rows(rows, ("approach", "config_id", "document_id"))
    global_summary = {
        "generated_at": utc_now(),
        "rows": len(rows),
        "summary": aggregate_rows(rows, ("approach", "config_id")),
    }
    atomic_write_json(destination / "raw_results.json", rows)
    atomic_write_json(destination / "global_summary.json", global_summary)
    _write_csv(destination / "results_by_field.csv", by_field)
    _write_csv(destination / "results_by_document.csv", by_document)
    return {
        "raw_results": str(destination / "raw_results.json"),
        "by_field": str(destination / "results_by_field.csv"),
        "by_document": str(destination / "results_by_document.csv"),
        "global_summary": str(destination / "global_summary.json"),
    }

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from evaluation import benchmark
from evaluation.metrics import aggregate_rows, hallucination_rate
from evaluation.run_experiments import configurations
from services.chunking import chunk_pages
from services.document_manifest import calculate_sha256, document_id_from_sha256, group_duplicates
from services.evidence import literal_is_present


class SmokeWithoutOptionalDependencies(unittest.TestCase):
    def test_hash_and_document_id_are_stable(self):
        path = Path(__file__)
        digest = calculate_sha256(path)
        self.assertEqual(digest, calculate_sha256(path))
        self.assertEqual(digest, document_id_from_sha256(digest))

    def test_duplicate_content(self):
        grouped = group_duplicates([
            {"sha256": "a" * 64, "relative_path": "uploads/a.pdf"},
            {"sha256": "a" * 64, "relative_path": "uploads/b.pdf"},
        ])
        self.assertEqual(1, len(grouped))
        self.assertEqual(2, len(next(iter(grouped.values()))))

    def test_chunk_metadata_and_stability(self):
        pages = [{"page": 1, "text": "um dois três quatro cinco"}]
        first = chunk_pages(pages, "x.pdf", "doc", chunk_size_words=3, overlap_words=1)
        second = chunk_pages(pages, "x.pdf", "doc", chunk_size_words=3, overlap_words=1)
        self.assertEqual(first, second)
        self.assertTrue(all(chunk["document_id"] == "doc" for chunk in first))
        self.assertEqual([0, 1], [chunk["chunk_index"] for chunk in first])

    def test_literal_normalization(self):
        self.assertTrue(literal_is_present("Valor estimado: R$ 10,00", "Valor   estimado:\nR$ 10,00"))

    def test_benchmark_split_is_deterministic(self):
        docs = [
            {"document_id": f"{number:064x}", "filename": f"{number}.pdf", "sha256": f"{number:064x}", "status": "indexed"}
            for number in range(10)
        ]
        written = {}
        with patch.object(benchmark, "load_manifest", return_value={"documents": docs}), patch.object(
            benchmark, "atomic_write_json", side_effect=lambda _path, payload: written.update(payload)
        ):
            result = benchmark.create_benchmark("unused.json", seed=42)
            self.assertEqual(7, sum(doc["split"] == "development" for doc in result["documents"]))
            self.assertEqual(3, sum(doc["split"] == "test" for doc in result["documents"]))
            self.assertEqual("1.0", written["benchmark_version"])

    def test_hallucination_and_aggregation(self):
        rows = [
            {"approach": "rag", "config_id": "c", "answered": True, "evidence": {"evidence_valid": True}, "reference": {}, "metrics": {"total_ms": 10}, "usage": {"prompt_tokens": 2}},
            {"approach": "rag", "config_id": "c", "answered": True, "evidence": {"evidence_valid": False}, "reference": {}, "metrics": {"total_ms": 30}, "usage": {"prompt_tokens": 4}},
        ]
        self.assertEqual(0.5, hallucination_rate(rows)["hallucination_rate"])
        summary = aggregate_rows(rows, ("approach", "config_id"))[0]
        self.assertEqual(20, summary["total_ms"]["mean"])
        self.assertEqual(3, summary["prompt_tokens"]["mean"])

    def test_exactly_twelve_rag_configurations(self):
        self.assertEqual(12, len(configurations()))


if __name__ == "__main__":
    unittest.main()

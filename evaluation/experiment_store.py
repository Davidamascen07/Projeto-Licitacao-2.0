from __future__ import annotations

from typing import Any

import numpy as np

try:
    import faiss
except ModuleNotFoundError:
    faiss = None

from services.config import get_embedding_model
from services.document_manifest import get_manifest_document
from services.chunking import chunk_pages

from .baselines import load_document_pages


class ExperimentalIndex:
    """Índice FAISS em memória para não sobrescrever o índice operacional."""

    def __init__(
        self,
        document_ids: list[str],
        *,
        chunk_size: int,
        overlap: int,
        embedding_model: Any | None = None,
        pages_cache: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        if faiss is None:
            raise RuntimeError("faiss-cpu não instalado; não é possível executar experimentos vetoriais.")
        self.model = embedding_model or get_embedding_model()
        self.chunks: list[dict[str, Any]] = []
        self.pages_cache = pages_cache if pages_cache is not None else {}
        for document_id in document_ids:
            pages = self.pages_cache.setdefault(document_id, load_document_pages(document_id))
            record = get_manifest_document(document_id)
            self.chunks.extend(
                chunk_pages(
                    pages,
                    record["filename"],
                    document_id=document_id,
                    chunk_size_words=chunk_size,
                    overlap_words=overlap,
                )
            )
        encoded = self.model.encode([chunk["text"] for chunk in self.chunks], normalize_embeddings=True)
        self.embeddings = np.asarray(encoded, dtype="float32")
        self.index = faiss.IndexFlatIP(self.embeddings.shape[1])
        self.index.add(self.embeddings)

    def search(self, query: str, top_k: int = 5, document_id: str | None = None, **_kwargs: Any) -> list[dict[str, Any]]:
        query_embedding = np.asarray(self.model.encode([query], normalize_embeddings=True), dtype="float32")
        scores, indices = self.index.search(query_embedding, self.index.ntotal)
        output: list[dict[str, Any]] = []
        for score, position in zip(scores[0], indices[0]):
            chunk = self.chunks[int(position)]
            if document_id is not None and chunk.get("document_id") != document_id:
                continue
            output.append({**chunk, "raw_score": float(score), "retrieval_score": round((float(score) + 1) / 2, 6)})
            if len(output) >= top_k:
                break
        return output

    def preambles(self, document_id: str | None = None) -> list[dict[str, Any]]:
        seen: set[str] = set()
        output: list[dict[str, Any]] = []
        for chunk in self.chunks:
            current = chunk["document_id"]
            if document_id is not None and current != document_id:
                continue
            if current not in seen:
                output.append(chunk)
                seen.add(current)
        return output

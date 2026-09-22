"""Persistência consistente de documentos, chunks e índice vetorial."""

from __future__ import annotations

import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np

try:
    import faiss
except ModuleNotFoundError:  # inventário e dry-run continuam disponíveis sem dependências completas
    faiss = None

from .config import (
    AUTO_SYNC_UPLOADS,
    CHUNK_OVERLAP_WORDS,
    CHUNK_SIZE_WORDS,
    INDEX_INFO_PATH,
    INDEX_PATH,
    MANIFEST_PATH,
    METADATA_PATH,
    UPLOAD_FOLDER,
    get_embedding_model,
)
from .document_manifest import discover_pdfs, group_duplicates, load_manifest, save_manifest
from .storage_utils import atomic_write_json, backup_files, load_json, storage_lock, utc_now

LOGGER = logging.getLogger(__name__)
INDEX_SCHEMA_VERSION = "2.0"
INDEX_METRIC = "cosine_ip_normalized"

_chunks: list[dict[str, Any]] = []
_faiss_index: Any | None = None
_index_info: dict[str, Any] = {}


def _encode(texts: list[str], embedding_model: Any | None = None) -> np.ndarray:
    model = embedding_model or get_embedding_model()
    try:
        encoded = model.encode(texts, normalize_embeddings=True)
    except TypeError:
        encoded = model.encode(texts)
        encoded = np.asarray(encoded, dtype="float32")
        norms = np.linalg.norm(encoded, axis=1, keepdims=True)
        encoded = encoded / np.maximum(norms, 1e-12)
    array = np.asarray(encoded, dtype="float32")
    if array.ndim != 2:
        raise ValueError("O modelo de embeddings retornou dimensões inválidas.")
    return array


def load_chunks_metadata() -> list[dict[str, Any]]:
    global _chunks
    loaded = load_json(METADATA_PATH, [])
    if not isinstance(loaded, list):
        raise ValueError("chunks_metadata.json deve conter uma lista.")
    _chunks = loaded
    return _chunks


def save_chunks_metadata(chunks: list[dict[str, Any]] | None = None) -> None:
    atomic_write_json(METADATA_PATH, chunks if chunks is not None else _chunks)


def get_chunks(document_id: str | None = None) -> list[dict[str, Any]]:
    if document_id is None:
        return list(_chunks)
    return [chunk for chunk in _chunks if chunk.get("document_id") == document_id]


def get_documents() -> list[str]:
    return list(dict.fromkeys(chunk["filename"] for chunk in _chunks))


def get_document_summaries() -> list[dict[str, Any]]:
    manifest = load_manifest()
    return [
        {
            "document_id": doc.get("document_id"),
            "filename": doc.get("filename"),
            "status": doc.get("status"),
            "page_count": doc.get("page_count"),
            "duplicate_paths": doc.get("duplicate_paths", []),
        }
        for doc in manifest["documents"]
    ]


def get_index() -> Any | None:
    return _faiss_index


def get_index_info() -> dict[str, Any]:
    return dict(_index_info)


def is_storage_consistent() -> bool:
    return bool(
        _faiss_index is not None
        and _faiss_index.ntotal == len(_chunks)
        and _index_info.get("metric") == INDEX_METRIC
        and all(chunk.get("document_id") for chunk in _chunks)
    )


def get_preamble_chunks(document_id: str | None = None) -> list[dict[str, Any]]:
    seen: set[str] = set()
    preamble: list[dict[str, Any]] = []
    for chunk in sorted(_chunks, key=lambda item: (item.get("document_id") or "", item.get("chunk_index", 0))):
        chunk_document_id = chunk.get("document_id")
        if document_id is not None and chunk_document_id != document_id:
            continue
        if not chunk_document_id or chunk_document_id in seen:
            continue
        seen.add(chunk_document_id)
        preamble.append(chunk)
    return preamble


def add_chunks(new_chunk_dicts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = {(item.get("document_id"), item.get("chunk_index")) for item in _chunks}
    added: list[dict[str, Any]] = []
    now = utc_now()
    for source in new_chunk_dicts:
        key = (source.get("document_id"), source.get("chunk_index"))
        if key in existing:
            continue
        chunk = dict(source)
        chunk.setdefault("chunk_id", uuid.uuid4().hex)
        chunk.setdefault("created_at", now)
        _chunks.append(chunk)
        added.append(chunk)
        existing.add(key)
    return added


def _require_faiss() -> Any:
    if faiss is None:
        raise RuntimeError("faiss-cpu não instalado. Instale requirements.txt para criar ou consultar o índice.")
    return faiss


def _write_faiss_atomic(index: Any) -> None:
    faiss_module = _require_faiss()
    temporary = INDEX_PATH.with_name(f".{INDEX_PATH.name}.{uuid.uuid4().hex}.tmp")
    try:
        faiss_module.write_index(index, str(temporary))
        os.replace(temporary, INDEX_PATH)
    finally:
        temporary.unlink(missing_ok=True)


def rebuild_vector_index(
    chunks: list[dict[str, Any]] | None = None,
    embedding_model: Any | None = None,
    persist: bool = True,
) -> Any:
    global _faiss_index, _index_info, _chunks
    source_chunks = list(_chunks if chunks is None else chunks)
    faiss_module = _require_faiss()
    if source_chunks:
        embeddings = _encode([chunk["text"] for chunk in source_chunks], embedding_model)
        index = faiss_module.IndexFlatIP(embeddings.shape[1])
        index.add(embeddings)
        dimension = embeddings.shape[1]
    else:
        dimension = 384
        index = faiss_module.IndexFlatIP(dimension)

    info = {
        "schema_version": INDEX_SCHEMA_VERSION,
        "metric": INDEX_METRIC,
        "dimension": dimension,
        "vector_count": len(source_chunks),
        "updated_at": utc_now(),
    }
    if persist:
        _write_faiss_atomic(index)
        save_chunks_metadata(source_chunks)
        atomic_write_json(INDEX_INFO_PATH, info)
    _chunks = source_chunks
    _faiss_index = index
    _index_info = info
    return index


def append_chunks_to_vector_index(
    new_chunks: list[dict[str, Any]],
    embedding_model: Any | None = None,
    persist: bool = True,
) -> Any:
    """Adiciona somente chunks novos a um índice consistente."""
    global _faiss_index, _index_info, _chunks
    if not new_chunks:
        return _faiss_index
    if not is_storage_consistent():
        raise RuntimeError("Índice incompatível; não é possível realizar inclusão incremental.")

    embeddings = _encode([chunk["text"] for chunk in new_chunks], embedding_model)
    if embeddings.shape[1] != int(_index_info.get("dimension") or 0):
        raise RuntimeError("Dimensão dos embeddings novos é incompatível com o índice.")

    faiss_module = _require_faiss()
    candidate_index = faiss_module.clone_index(_faiss_index)
    candidate_index.add(embeddings)
    candidate_chunks = list(_chunks) + list(new_chunks)
    candidate_info = {
        **_index_info,
        "vector_count": len(candidate_chunks),
        "updated_at": utc_now(),
    }

    if persist:
        _write_faiss_atomic(candidate_index)
        save_chunks_metadata(candidate_chunks)
        atomic_write_json(INDEX_INFO_PATH, candidate_info)
    _faiss_index = candidate_index
    _chunks = candidate_chunks
    _index_info = candidate_info
    return candidate_index


def _active_manifest_record(item: dict[str, Any], aliases: list[dict[str, Any]], previous: dict[str, Any] | None) -> dict[str, Any]:
    now = utc_now()
    record = dict(previous or {})
    record.update(
        {
            "document_id": item["document_id"],
            "sha256": item["sha256"],
            "filename": item["filename"],
            "relative_path": item["relative_path"],
            "size_bytes": item["size_bytes"],
            "updated_at": now,
            "status": record.get("status", "pending_index"),
            "duplicate_paths": [alias["relative_path"] for alias in aliases[1:]],
            "source": record.get("source"),
            "source_url": record.get("source_url"),
            "collection_date": record.get("collection_date"),
            "evaluation_set": record.get("evaluation_set"),
            "excluded": bool(record.get("excluded", False)),
        }
    )
    if record.get("page_count") is None:
        record["page_count"] = 0
    record.setdefault("indexed_at", None)
    return record


def plan_synchronization(document_id: str | None = None, rebuild_all: bool = False) -> dict[str, Any]:
    manifest = load_manifest()
    discovered = discover_pdfs()
    grouped = group_duplicates(discovered)
    old_by_id = {doc.get("document_id"): doc for doc in manifest["documents"] if doc.get("document_id")}
    chunks_by_id: dict[str, int] = {}
    for chunk in _chunks:
        if chunk.get("document_id"):
            chunks_by_id[chunk["document_id"]] = chunks_by_id.get(chunk["document_id"], 0) + 1

    active_records: list[dict[str, Any]] = []
    added: list[str] = []
    to_index: list[str] = []
    duplicates: list[dict[str, Any]] = []
    for sha256, aliases in grouped.items():
        aliases.sort(key=lambda item: item["relative_path"].casefold())
        item = aliases[0]
        previous = old_by_id.get(item["document_id"])
        record = _active_manifest_record(item, aliases, previous)
        active_records.append(record)
        if len(aliases) > 1:
            duplicates.append({"document_id": item["document_id"], "paths": [a["relative_path"] for a in aliases]})
        if previous is None:
            added.append(item["document_id"])
        needs_index = rebuild_all or not chunks_by_id.get(item["document_id"]) or record.get("status") != "indexed"
        if document_id is not None:
            needs_index = item["document_id"] == document_id
        if needs_index and not record.get("excluded"):
            to_index.append(item["document_id"])

    active_ids = {record["document_id"] for record in active_records}
    missing: list[str] = []
    retained_missing: list[dict[str, Any]] = []
    for old_id, old in old_by_id.items():
        if old_id in active_ids:
            continue
        stale = dict(old)
        stale["status"] = "file_missing"
        stale["updated_at"] = utc_now()
        retained_missing.append(stale)
        missing.append(old_id)

    legacy_filenames = sorted({chunk.get("filename") for chunk in _chunks if not chunk.get("document_id")})
    return {
        "manifest": {"manifest_version": "1.0", "documents": active_records + retained_missing},
        "discovered": discovered,
        "added": added,
        "to_index": to_index,
        "missing": missing,
        "duplicates": duplicates,
        "legacy_chunk_filenames": legacy_filenames,
        "index_incompatible": (
            _faiss_index is None
            or _faiss_index.ntotal != len(_chunks)
            or _index_info.get("metric") != INDEX_METRIC
        ),
    }


def synchronize_documents(
    document_id: str | None = None,
    rebuild_all: bool = False,
    dry_run: bool = False,
    embedding_model: Any | None = None,
) -> dict[str, Any]:
    """Sincroniza PDFs, manifesto, chunks e FAISS com backup antes da mutação."""
    global _chunks
    with storage_lock():
        load_chunks_metadata()
        plan = plan_synchronization(document_id=document_id, rebuild_all=rebuild_all)
        report: dict[str, Any] = {
            "dry_run": dry_run,
            "added": plan["added"],
            "updated": [],
            "removed_or_missing": plan["missing"],
            "duplicates": plan["duplicates"],
            "ignored": [],
            "failed": [],
            "legacy_chunks_removed_from_active_index": plan["legacy_chunk_filenames"],
            "backup_path": None,
        }
        if dry_run:
            report["would_index"] = plan["to_index"]
            return report

        backup = backup_files([INDEX_PATH, METADATA_PATH, INDEX_INFO_PATH, MANIFEST_PATH], "reindex")
        report["backup_path"] = str(backup) if backup else None

        discovered_by_id = {item["document_id"]: item for item in plan["discovered"]}
        manifest_by_id = {doc["document_id"]: doc for doc in plan["manifest"]["documents"] if doc.get("document_id")}
        replacements: dict[str, list[dict[str, Any]]] = {}
        from .chunking import chunk_pages
        from .pdf_service import extract_pages_from_pdf

        for target_id in plan["to_index"]:
            item = discovered_by_id[target_id]
            started = time.perf_counter()
            try:
                pages = extract_pages_from_pdf(item["path"])
                generated = chunk_pages(
                    pages,
                    item["filename"],
                    document_id=target_id,
                    chunk_size_words=CHUNK_SIZE_WORDS,
                    overlap_words=CHUNK_OVERLAP_WORDS,
                )
                if not generated:
                    raise ValueError("Nenhum texto foi extraído do PDF.")
                replacements[target_id] = generated
                record = manifest_by_id[target_id]
                record.update(
                    {
                        "page_count": len(pages),
                        "indexed_at": utc_now(),
                        "updated_at": utc_now(),
                        "status": "indexed",
                        "index_config": {
                            "chunk_size_words": CHUNK_SIZE_WORDS,
                            "overlap_words": CHUNK_OVERLAP_WORDS,
                        },
                        "extraction_seconds": round(time.perf_counter() - started, 4),
                    }
                )
                report["updated"].append(target_id)
            except Exception as exc:
                manifest_by_id[target_id]["status"] = "index_error"
                manifest_by_id[target_id]["last_error"] = str(exc)
                report["failed"].append({"document_id": target_id, "error": str(exc)})
                LOGGER.exception("Falha ao indexar %s", item["filename"])

        active_ids = {
            doc["document_id"]
            for doc in plan["manifest"]["documents"]
            if doc.get("status") not in {"file_missing", "removed"} and not doc.get("excluded")
        }
        final_chunks: list[dict[str, Any]] = []
        for chunk in _chunks:
            chunk_id = chunk.get("document_id")
            if not chunk_id or chunk_id not in active_ids or chunk_id in replacements:
                continue
            final_chunks.append(chunk)
        for replacement in replacements.values():
            final_chunks.extend(replacement)
        final_chunks.sort(key=lambda chunk: (chunk.get("document_id", ""), chunk.get("chunk_index", 0)))

        index_changed = bool(replacements or plan["missing"] or plan["legacy_chunk_filenames"] or plan["index_incompatible"])
        existing_document_ids = {chunk.get("document_id") for chunk in _chunks}
        incremental_document_id = document_id if document_id in replacements else None
        can_append_incrementally = bool(
            incremental_document_id
            and incremental_document_id not in existing_document_ids
            and set(replacements) == {incremental_document_id}
            and not plan["missing"]
            and not plan["legacy_chunk_filenames"]
            and not plan["index_incompatible"]
            and not rebuild_all
            and is_storage_consistent()
        )
        report["incremental"] = can_append_incrementally
        try:
            if can_append_incrementally:
                rebuild_started = time.perf_counter()
                append_chunks_to_vector_index(
                    replacements[incremental_document_id],
                    embedding_model=embedding_model,
                    persist=True,
                )
                report["embedding_and_index_seconds"] = round(
                    time.perf_counter() - rebuild_started,
                    4,
                )
            elif index_changed:
                rebuild_started = time.perf_counter()
                rebuild_vector_index(final_chunks, embedding_model=embedding_model, persist=True)
                report["embedding_and_index_seconds"] = round(time.perf_counter() - rebuild_started, 4)
            else:
                report["embedding_and_index_seconds"] = 0.0
                save_chunks_metadata(final_chunks)
        except Exception as exc:
            for failed_id in replacements:
                record = manifest_by_id[failed_id]
                record["status"] = "index_error"
                record["last_error"] = str(exc)
                if failed_id in report["updated"]:
                    report["updated"].remove(failed_id)
                report["failed"].append({"document_id": failed_id, "error": str(exc)})
            save_manifest(plan["manifest"])
            report.update(
                {
                    "embedding_and_index_seconds": 0.0,
                    "pdf_files": len(plan["discovered"]),
                    "unique_documents": len(group_duplicates(plan["discovered"])),
                    "chunks": len(_chunks),
                    "vectors": _faiss_index.ntotal if _faiss_index is not None else 0,
                }
            )
            LOGGER.exception("Falha ao persistir atualização vetorial")
            return report
        save_manifest(plan["manifest"])
        persisted_chunks = get_chunks()
        report.update(
            {
                "pdf_files": len(plan["discovered"]),
                "unique_documents": len(group_duplicates(plan["discovered"])),
                "chunks": len(persisted_chunks),
                "vectors": _faiss_index.ntotal if _faiss_index is not None else 0,
            }
        )
        return report


def inventory_documents(dry_run: bool = False) -> dict[str, Any]:
    """Atualiza somente o manifesto; útil antes da instalação das dependências vetoriais."""
    with storage_lock():
        load_chunks_metadata()
        plan = plan_synchronization()
        report = {
            "dry_run": dry_run,
            "pdf_files": len(plan["discovered"]),
            "unique_documents": len(group_duplicates(plan["discovered"])),
            "added": plan["added"],
            "missing": plan["missing"],
            "duplicates": plan["duplicates"],
            "pending_index": plan["to_index"],
            "backup_path": None,
        }
        if not dry_run:
            backup = backup_files([MANIFEST_PATH], "manifest-inventory")
            save_manifest(plan["manifest"])
            report["backup_path"] = str(backup) if backup else None
        return report


def remove_document(document_id: str, embedding_model: Any | None = None) -> dict[str, Any]:
    global _chunks
    with storage_lock():
        manifest = load_manifest()
        record = next((doc for doc in manifest["documents"] if doc.get("document_id") == document_id), None)
        if record is None:
            raise KeyError("Documento não encontrado no manifesto.")
        backup = backup_files([INDEX_PATH, METADATA_PATH, INDEX_INFO_PATH, MANIFEST_PATH], "remove-document")
        record["status"] = "removed"
        record["excluded"] = True
        record["updated_at"] = utc_now()
        remaining = [chunk for chunk in _chunks if chunk.get("document_id") != document_id]
        rebuild_vector_index(remaining, embedding_model=embedding_model, persist=True)
        save_manifest(manifest)
        return {"document_id": document_id, "status": "removed", "backup_path": str(backup) if backup else None}


def init_vector_store(sync_uploads: bool | None = None) -> Any | None:
    global _faiss_index, _index_info
    load_chunks_metadata()
    _index_info = load_json(INDEX_INFO_PATH, {})
    if INDEX_PATH.exists() and faiss is not None:
        try:
            _faiss_index = faiss.read_index(str(INDEX_PATH))
        except Exception as exc:
            LOGGER.warning("Índice FAISS ilegível: %s", exc)
            _faiss_index = None
    if _faiss_index is not None and _faiss_index.ntotal != len(_chunks):
        LOGGER.warning("Índice incompatível com metadados; execute scripts/reindex.py --rebuild-all.")
    if sync_uploads if sync_uploads is not None else AUTO_SYNC_UPLOADS:
        synchronize_documents()
    return _faiss_index


DOMAIN_KEYWORDS = [
    "objeto", "valor", "modalidade", "prazo", "orgao", "órgão", "julgamento",
    "habilitacao", "habilitação", "execucao", "execução", "uf",
]


def _keyword_boost(query: str, text: str) -> int:
    query_lower = query.casefold()
    text_lower = text.casefold()
    return sum(1 for term in DOMAIN_KEYWORDS if term in query_lower and term in text_lower)


def search(
    query: str,
    top_k: int = 5,
    document_id: str | None = None,
    *,
    k: int | None = None,
    embedding_model: Any | None = None,
    timing: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Busca semântica com filtro obrigatório quando ``document_id`` é fornecido."""
    if k is not None:
        top_k = k
    if top_k < 1:
        raise ValueError("top_k deve ser maior que zero.")
    if _chunks and not is_storage_consistent():
        raise RuntimeError("Índice legado ou inconsistente. Execute scripts/reindex.py --rebuild-all.")
    if _faiss_index is None or _faiss_index.ntotal == 0 or not _chunks:
        return []
    embedding_started = time.perf_counter()
    query_embedding = _encode([query], embedding_model)
    embedding_ms = round((time.perf_counter() - embedding_started) * 1000, 1)
    vector_started = time.perf_counter()
    fetch_k = _faiss_index.ntotal if document_id else min(max(top_k * 3, top_k), _faiss_index.ntotal)
    scores, indices = _faiss_index.search(query_embedding, fetch_k)
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    cosine_metric = _index_info.get("metric") == INDEX_METRIC
    for raw_score, index_position in zip(scores[0], indices[0]):
        if index_position < 0 or index_position >= len(_chunks):
            continue
        chunk = _chunks[int(index_position)]
        if document_id is not None and chunk.get("document_id") != document_id:
            continue
        if chunk.get("chunk_id") in seen:
            continue
        seen.add(chunk.get("chunk_id"))
        retrieval_score = (float(raw_score) + 1.0) / 2.0 if cosine_metric else 1.0 / (1.0 + max(float(raw_score), 0.0))
        candidates.append({**chunk, "raw_score": float(raw_score), "retrieval_score": round(retrieval_score, 6)})
    candidates.sort(key=lambda item: (-_keyword_boost(query, item["text"]), -item["retrieval_score"]))
    result = candidates[:top_k]
    if timing is not None:
        timing.update(
            {
                "embedding_ms": embedding_ms,
                "vector_search_ms": round((time.perf_counter() - vector_started) * 1000, 1),
            }
        )
    if document_id is not None and any(item.get("document_id") != document_id for item in result):
        raise RuntimeError("Falha de isolamento: busca retornou chunk de outro documento.")
    return result

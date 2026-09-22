"""Identidade por conteúdo e manifesto central dos PDFs."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Iterable

from .config import MANIFEST_PATH, PROJECT_ROOT, UPLOAD_FOLDER
from .storage_utils import atomic_write_json, load_json, utc_now

MANIFEST_VERSION = "1.0"


def calculate_sha256(path: str | Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def document_id_from_sha256(sha256: str) -> str:
    if len(sha256) != 64 or any(char not in "0123456789abcdef" for char in sha256.lower()):
        raise ValueError("SHA-256 inválido")
    return sha256.lower()


def load_manifest(path: str | Path = MANIFEST_PATH) -> dict[str, Any]:
    default = {"manifest_version": MANIFEST_VERSION, "updated_at": None, "documents": []}
    manifest = load_json(path, default)
    manifest.setdefault("manifest_version", MANIFEST_VERSION)
    manifest.setdefault("documents", [])
    return manifest


def save_manifest(manifest: dict[str, Any], path: str | Path = MANIFEST_PATH) -> None:
    manifest["manifest_version"] = MANIFEST_VERSION
    manifest["updated_at"] = utc_now()
    atomic_write_json(path, manifest)


def relative_project_path(path: str | Path) -> str:
    return Path(path).resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()


def discover_pdfs(folder: str | Path = UPLOAD_FOLDER) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    for path in sorted(Path(folder).glob("*"), key=lambda item: item.name.casefold()):
        if not path.is_file() or path.suffix.lower() != ".pdf":
            continue
        sha256 = calculate_sha256(path)
        discovered.append(
            {
                "document_id": document_id_from_sha256(sha256),
                "sha256": sha256,
                "filename": path.name,
                "relative_path": relative_project_path(path),
                "size_bytes": path.stat().st_size,
                "path": path,
            }
        )
    return discovered


def group_duplicates(discovered: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in discovered:
        grouped.setdefault(item["sha256"], []).append(item)
    return grouped


def get_manifest_document(document_id: str, manifest: dict[str, Any] | None = None) -> dict[str, Any] | None:
    current = manifest or load_manifest()
    return next((doc for doc in current["documents"] if doc.get("document_id") == document_id), None)

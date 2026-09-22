from __future__ import annotations

from pathlib import Path

from services.document_manifest import calculate_sha256, discover_pdfs, document_id_from_sha256, group_duplicates


def _pdf(path: Path, payload: bytes = b"%PDF-1.4\ncontent") -> Path:
    path.write_bytes(payload)
    return path


def test_sha256_and_document_id_are_stable(tmp_path):
    source = _pdf(tmp_path / "a.pdf")
    first = calculate_sha256(source)
    second = calculate_sha256(source)
    assert first == second
    assert document_id_from_sha256(first) == first
    assert len(first) == 64


def test_duplicate_content_is_grouped_by_hash(tmp_path, monkeypatch):
    _pdf(tmp_path / "a.pdf")
    _pdf(tmp_path / "renamed.pdf")
    monkeypatch.setattr("services.document_manifest.PROJECT_ROOT", tmp_path)
    found = discover_pdfs(tmp_path)
    grouped = group_duplicates(found)
    assert len(grouped) == 1
    assert len(next(iter(grouped.values()))) == 2


def test_new_pdf_is_discovered(tmp_path, monkeypatch):
    _pdf(tmp_path / "novo.pdf", b"%PDF-1.7\nnew")
    monkeypatch.setattr("services.document_manifest.PROJECT_ROOT", tmp_path)
    found = discover_pdfs(tmp_path)
    assert [item["filename"] for item in found] == ["novo.pdf"]

from __future__ import annotations

import json

import pytest

from services.pncp_service import MAX_PDF_BYTES, PNCPClient


class FakeResponse:
    def __init__(self, *, json_value=None, content=b"", status=200):
        self._json_value = json_value
        self.content = content
        self.status = status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(self.status)

    def json(self):
        return self._json_value


class FakeSession:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.headers = {}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return next(self.responses)


def test_search_publications_uses_official_query_contract():
    session = FakeSession([FakeResponse(json_value={"data": []})])
    result = PNCPClient(session=session).search_publications(
        start_date="20260701", end_date="20260702", modality_code=6, uf="ce"
    )
    assert result == {"data": []}
    url, kwargs = session.calls[0]
    assert url.endswith("/contratacoes/publicacao")
    assert kwargs["params"]["codigoModalidadeContratacao"] == 6
    assert kwargs["params"]["uf"] == "CE"


def test_download_validates_pdf_and_records_provenance(tmp_path):
    session = FakeSession([FakeResponse(content=b"%PDF-1.7\nexample")])
    manifest = tmp_path / "manifest.json"
    entry = PNCPClient(session=session).download_document(
        cnpj="12345678000199",
        year=2026,
        sequence=7,
        document={"sequencialDocumento": 2, "titulo": "Edital teste", "dataPublicacaoPncp": "2026-07-01"},
        output_dir=tmp_path / "pdfs",
        manifest_path=manifest,
    )
    assert entry["source"] == "PNCP"
    assert entry["source_url"].endswith("/arquivos/2")
    assert (tmp_path / "pdfs" / entry["filename"]).read_bytes().startswith(b"%PDF-")
    assert json.loads(manifest.read_text(encoding="utf-8"))[0]["sha256"] == entry["sha256"]


def test_download_rejects_non_pdf(tmp_path):
    session = FakeSession([FakeResponse(content=b"<html>erro</html>")])
    with pytest.raises(ValueError, match="assinatura PDF"):
        PNCPClient(session=session).download_document(
            cnpj="12345678000199",
            year=2026,
            sequence=7,
            document={"sequencialDocumento": 2},
            output_dir=tmp_path,
            manifest_path=tmp_path / "manifest.json",
        )

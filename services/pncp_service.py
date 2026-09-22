"""Cliente de leitura para as APIs públicas oficiais do PNCP."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CONSULTA_BASE_URL = "https://pncp.gov.br/api/consulta/v1"
PNCP_BASE_URL = "https://pncp.gov.br/api/pncp/v1"
DEFAULT_DOWNLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "pncp_downloads"
DEFAULT_MANIFEST_PATH = Path(__file__).resolve().parent.parent / "data" / "pncp_collection_manifest.json"
MAX_PDF_BYTES = 50 * 1024 * 1024


def _safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._")
    return value[:120] or "documento"


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


class PNCPClient:
    """Consulta e baixa documentos sem autenticação, conforme API pública do PNCP."""

    def __init__(self, *, timeout: float = 30.0, session: requests.Session | None = None) -> None:
        self.timeout = timeout
        self.session = session or requests.Session()
        if session is None:
            retry = Retry(
                total=3,
                backoff_factor=1.0,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=("GET",),
            )
            self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update(
            {"Accept": "application/json", "User-Agent": "Projeto-Licitacao-Academico/2.0"}
        )

    def search_publications(
        self,
        *,
        start_date: str,
        end_date: str,
        modality_code: int,
        page: int = 1,
        uf: str | None = None,
    ) -> dict[str, Any]:
        if not re.fullmatch(r"\d{8}", start_date) or not re.fullmatch(r"\d{8}", end_date):
            raise ValueError("Datas devem usar o formato AAAAMMDD.")
        if page < 1 or modality_code < 1:
            raise ValueError("Página e código de modalidade devem ser positivos.")
        params: dict[str, Any] = {
            "dataInicial": start_date,
            "dataFinal": end_date,
            "codigoModalidadeContratacao": modality_code,
            "pagina": page,
        }
        if uf:
            params["uf"] = uf.upper()
        response = self.session.get(
            f"{CONSULTA_BASE_URL}/contratacoes/publicacao",
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict):
            raise ValueError("Resposta inesperada da consulta PNCP.")
        return result

    def list_documents(self, *, cnpj: str, year: int, sequence: int) -> list[dict[str, Any]]:
        if not re.fullmatch(r"\d{14}", cnpj):
            raise ValueError("CNPJ deve conter 14 dígitos.")
        if year < 2021 or sequence < 1:
            raise ValueError("Ano ou sequencial PNCP inválido.")
        url = f"{PNCP_BASE_URL}/orgaos/{cnpj}/compras/{year}/{sequence}/arquivos"
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, list):
            raise ValueError("Resposta inesperada da lista de documentos PNCP.")
        return [item for item in result if isinstance(item, dict)]

    def download_document(
        self,
        *,
        cnpj: str,
        year: int,
        sequence: int,
        document: dict[str, Any],
        output_dir: Path = DEFAULT_DOWNLOAD_DIR,
        manifest_path: Path = DEFAULT_MANIFEST_PATH,
    ) -> dict[str, Any]:
        document_sequence = int(document["sequencialDocumento"])
        source_url = (
            f"{PNCP_BASE_URL}/orgaos/{cnpj}/compras/{year}/{sequence}"
            f"/arquivos/{document_sequence}"
        )
        response = self.session.get(source_url, timeout=self.timeout, headers={"Accept": "application/pdf"})
        response.raise_for_status()
        content = response.content
        if len(content) > MAX_PDF_BYTES:
            raise ValueError("Documento PNCP excede o limite de 50 MB.")
        if not content.startswith(b"%PDF-"):
            raise ValueError("O documento retornado pelo PNCP não possui assinatura PDF.")
        digest = hashlib.sha256(content).hexdigest()
        title = str(document.get("titulo") or f"documento-{document_sequence}")
        filename = _safe_name(f"pncp-{cnpj}-{year}-{sequence}-{document_sequence}-{title}") + ".pdf"
        output_dir.mkdir(parents=True, exist_ok=True)
        destination = output_dir / filename
        destination.write_bytes(content)
        entry = {
            "sha256": digest,
            "filename": filename,
            "path": str(destination.resolve()),
            "source": "PNCP",
            "source_url": source_url,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "cnpj": cnpj,
            "year": year,
            "sequence": sequence,
            "document_sequence": document_sequence,
            "title": title,
            "document_type_id": document.get("tipoDocumentoId"),
            "document_type_name": document.get("tipoDocumentoNome"),
            "published_at_pncp": document.get("dataPublicacaoPncp"),
            "bytes": len(content),
        }
        manifest = []
        if manifest_path.exists():
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest = loaded if isinstance(loaded, list) else []
        manifest = [item for item in manifest if item.get("sha256") != digest]
        manifest.append(entry)
        _atomic_json(manifest_path, manifest)
        return entry


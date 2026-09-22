from __future__ import annotations

import atexit
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename

from services.agent_service import process_query_with_agent
from services.config import (
    EMBEDDING_MODEL_NAME,
    FLASK_DEBUG,
    FLASK_HOST,
    FLASK_PORT,
    INDEX_PATH,
    MAX_CONTENT_LENGTH,
    UPLOAD_FOLDER,
    EmbeddingModelLoadingError,
    EmbeddingModelUnavailableError,
    get_embedding_model_status,
    require_embedding_ready,
    warm_embedding_model_async,
)
from services.document_manifest import calculate_sha256, document_id_from_sha256, load_manifest
from services.extraction_service import FIELD_QUESTIONS, extract_multiple_fields
from services.pdf_service import allowed_file, validate_pdf_file
from services.vector_store import (
    get_chunks,
    get_document_summaries,
    get_index,
    get_index_info,
    init_vector_store,
    inventory_documents,
    is_storage_consistent,
    remove_document,
    synchronize_documents,
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
LOGGER = logging.getLogger(__name__)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
init_vector_store()
SERVER_INSTANCE_ID = uuid.uuid4().hex
SERVER_STARTED_AT = datetime.now(timezone.utc).isoformat()
_INSTANCE_LOCK_HANDLE = None


def acquire_instance_lock(lock_path: Path | None = None) -> None:
    """Impede duas instâncias oficiais deste projeto no mesmo host/porta."""
    global _INSTANCE_LOCK_HANDLE
    lock_path = lock_path or (
        Path(__file__).resolve().parent / "data" / f".app-{FLASK_HOST}-{FLASK_PORT}.lock"
    )
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = lock_path.open("a+b")
        if lock_path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, PermissionError) as exc:
        if "handle" in locals():
            handle.close()
        raise RuntimeError(
            f"Já existe uma instância desta aplicação para {FLASK_HOST}:{FLASK_PORT}."
        ) from exc
    handle.seek(0)
    handle.write(str(os.getpid()).encode("ascii"))
    handle.truncate()
    handle.flush()
    _INSTANCE_LOCK_HANDLE = handle


def release_instance_lock() -> None:
    global _INSTANCE_LOCK_HANDLE
    if _INSTANCE_LOCK_HANDLE is None:
        return
    try:
        if os.name == "nt":
            import msvcrt

            _INSTANCE_LOCK_HANDLE.seek(0)
            msvcrt.locking(_INSTANCE_LOCK_HANDLE.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(_INSTANCE_LOCK_HANDLE.fileno(), fcntl.LOCK_UN)
    finally:
        _INSTANCE_LOCK_HANDLE.close()
        _INSTANCE_LOCK_HANDLE = None


atexit.register(release_instance_lock)


def _indexed_document_ids() -> list[str]:
    return [
        doc["document_id"]
        for doc in load_manifest()["documents"]
        if doc.get("status") == "indexed" and not doc.get("excluded")
    ]


def _selected_document_id(payload: dict | None) -> str | None:
    requested = (payload or {}).get("document_id")
    if requested:
        return str(requested)
    indexed = _indexed_document_ids()
    return indexed[0] if len(indexed) == 1 else None


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return jsonify(
        {
            "error": f"Arquivo excede o limite de {MAX_CONTENT_LENGTH} bytes.",
            "code": "UPLOAD_TOO_LARGE",
            "request_id": getattr(g, "request_id", None),
        }
    ), 413


@app.before_request
def assign_request_id():
    g.request_id = uuid.uuid4().hex


@app.after_request
def attach_request_id(response):
    response.headers["X-Request-ID"] = getattr(g, "request_id", "")
    return response


@app.errorhandler(EmbeddingModelLoadingError)
def embedding_loading(_error):
    return jsonify(
        {
            "error": "O modelo de busca ainda está sendo preparado. Aguarde e tente novamente.",
            "code": "EMBEDDING_MODEL_LOADING",
            "request_id": g.request_id,
        }
    ), 503


@app.errorhandler(EmbeddingModelUnavailableError)
def embedding_unavailable(_error):
    return jsonify(
        {
            "error": (
                "Modelo de busca indisponível. Reinicie a aplicação ou prepare o cache local."
            ),
            "code": "EMBEDDING_MODEL_UNAVAILABLE",
            "request_id": g.request_id,
        }
    ), 503


@app.errorhandler(Exception)
def unexpected_error(error):
    request_id = getattr(g, "request_id", uuid.uuid4().hex)
    LOGGER.exception("Erro não tratado na requisição request_id=%s", request_id)
    error_name = type(error).__name__
    error_module = type(error).__module__
    if error_name in {"APIConnectionError", "APITimeoutError"} or error_module.startswith("groq"):
        return jsonify(
            {
                "error": "Não foi possível conectar à Groq. Verifique rede e configuração.",
                "code": "GROQ_CONNECTION_ERROR",
                "request_id": request_id,
            }
        ), 502
    if "Cota diária da Groq" in str(error):
        return jsonify(
            {
                "error": "A cota diária da Groq foi atingida. Tente novamente mais tarde.",
                "code": "GROQ_QUOTA_EXCEEDED",
                "request_id": request_id,
            }
        ), 429
    return jsonify(
        {
            "error": "Erro interno ao processar a solicitação.",
            "code": "INTERNAL_ERROR",
            "request_id": request_id,
        }
    ), 500


@app.post("/upload_pdf")
def upload_pdf():
    if "file" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado."}), 400
    uploaded = request.files["file"]
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "Arquivo inválido."}), 400
    if not allowed_file(uploaded.filename):
        return jsonify({"error": "Apenas arquivos PDF são aceitos."}), 400

    safe_name = secure_filename(uploaded.filename) or f"documento-{uuid.uuid4().hex[:8]}.pdf"
    temporary = UPLOAD_FOLDER / f".upload-{uuid.uuid4().hex}.tmp"
    destination: Path | None = None
    try:
        uploaded.save(temporary)
        validate_pdf_file(temporary)
        sha256 = calculate_sha256(temporary)
        document_id = document_id_from_sha256(sha256)
        existing_chunks = get_chunks(document_id)
        if document_id in _indexed_document_ids() and existing_chunks:
            temporary.unlink(missing_ok=True)
            canonical_filename = str(existing_chunks[0].get("filename") or safe_name)
            return jsonify(
                {
                    "message": "Edital já estava indexado e foi selecionado.",
                    "status": "indexed",
                    "filename": canonical_filename,
                    "document_id": document_id,
                    "duplicate_content": True,
                    "chunks_added": 0,
                    "total_chunks": len(get_chunks()),
                }
            )

        destination = UPLOAD_FOLDER / safe_name
        if destination.exists():
            if calculate_sha256(destination) == sha256:
                temporary.unlink(missing_ok=True)
            else:
                destination = UPLOAD_FOLDER / f"{destination.stem}-{sha256[:8]}.pdf"
                os.replace(temporary, destination)
        else:
            os.replace(temporary, destination)

        embedding_status = get_embedding_model_status()["embedding_model_status"]
        if embedding_status != "ready":
            inventory_documents(dry_run=False)
            return jsonify(
                {
                    "message": (
                        "Edital salvo e aguardando a preparação do modelo de busca. "
                        "A indexação pode ser retomada sem reenviar o arquivo."
                    ),
                    "status": "pending_index",
                    "filename": destination.name,
                    "document_id": document_id,
                    "chunks_added": 0,
                    "total_chunks": len(get_chunks()),
                }
            ), 202

        require_embedding_ready()
        report = synchronize_documents(document_id=document_id)
        failed = next((item for item in report["failed"] if item["document_id"] == document_id), None)
        if failed:
            LOGGER.error("Falha ao indexar upload %s: %s", document_id, failed["error"])
            return (
                jsonify(
                    {
                        "error": (
                            "Não foi possível indexar o edital. Reinicie a aplicação e aguarde "
                            "o modelo de busca ficar pronto antes de tentar novamente."
                        ),
                        "document_id": document_id,
                    }
                ),
                422,
            )
        chunks = get_chunks(document_id)
        chunks_added = len(chunks) if document_id in report["updated"] else 0
        return jsonify(
            {
                "message": "Edital reconhecido e índice sincronizado.",
                "filename": destination.name,
                "document_id": document_id,
                "duplicate_content": bool(report["duplicates"]),
                "chunks_added": chunks_added,
                "total_chunks": len(get_chunks()),
            }
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    finally:
        temporary.unlink(missing_ok=True)


@app.post("/query")
def query():
    data = request.get_json(silent=True) or {}
    query_text = str(data.get("query") or "").strip()
    if not query_text:
        return jsonify({"error": "Consulta não fornecida."}), 400
    document_id = str(data.get("document_id") or "").strip()
    if not document_id:
        return jsonify({"error": "Selecione ou envie um edital antes de perguntar."}), 400
    if document_id not in _indexed_document_ids() or not get_chunks(document_id):
        return jsonify({"error": "Documento não encontrado, não indexado ou sem trechos."}), 404
    require_embedding_ready()
    result = process_query_with_agent(query_text, document_id=document_id)
    if any(source.get("document_id") != document_id for source in result.get("sources", [])):
        raise RuntimeError("Falha de isolamento: resposta contém fonte de outro edital.")
    return jsonify(result)


@app.post("/extract_fields")
def extract_fields():
    data = request.get_json(silent=True) or {}
    document_id = _selected_document_id(data)
    if not document_id:
        return jsonify({"error": "Selecione um document_id para impedir mistura entre editais."}), 400
    if not get_chunks(document_id):
        return jsonify({"error": "Documento não indexado ou sem chunks."}), 404
    require_embedding_ready()
    fields = extract_multiple_fields(FIELD_QUESTIONS, document_id)
    return jsonify({"document_id": document_id, "fields": fields})


@app.get("/chunks")
def list_chunks():
    document_id = request.args.get("document_id")
    preview = [
        {
            "chunk_id": chunk["chunk_id"],
            "document_id": chunk.get("document_id"),
            "filename": chunk["filename"],
            "chunk_index": chunk.get("chunk_index"),
            "page_start": chunk["page_start"],
            "page_end": chunk["page_end"],
            "preview": chunk["text"][:300],
        }
        for chunk in get_chunks(document_id)
    ]
    return jsonify({"chunks": preview})


@app.get("/documents")
def documents():
    return jsonify({"documents": get_document_summaries()})


@app.post("/reindex")
def reindex():
    require_embedding_ready()
    data = request.get_json(silent=True) or {}
    report = synchronize_documents(
        document_id=data.get("document_id"),
        rebuild_all=bool(data.get("rebuild_all", False)),
        dry_run=bool(data.get("dry_run", False)),
    )
    return jsonify(report)


@app.post("/documents/<document_id>/index")
def index_pending_document(document_id: str):
    require_embedding_ready()
    report = synchronize_documents(document_id=document_id)
    failed = next((item for item in report["failed"] if item["document_id"] == document_id), None)
    if failed:
        LOGGER.error("Falha ao retomar indexação %s: %s", document_id, failed["error"])
        return jsonify(
            {
                "error": "Não foi possível indexar o edital salvo.",
                "code": "DOCUMENT_INDEX_FAILED",
                "document_id": document_id,
                "request_id": g.request_id,
            }
        ), 422
    chunks = get_chunks(document_id)
    return jsonify(
        {
            "message": "Edital indexado com sucesso.",
            "document_id": document_id,
            "chunks_added": len(chunks),
            "total_chunks": len(get_chunks()),
        }
    )


@app.delete("/documents/<document_id>")
def delete_document(document_id: str):
    """Remove do índice e preserva o PDF; a operação cria backup."""
    try:
        return jsonify(remove_document(document_id))
    except KeyError as exc:
        return jsonify({"error": str(exc)}), 404


@app.get("/status")
def status():
    index = get_index()
    embedding_status = get_embedding_model_status()
    return jsonify(
        {
            "chunks": len(get_chunks()),
            "vetores_no_indice": index.ntotal if index is not None else 0,
            "index_existe": INDEX_PATH.exists(),
            "documentos": get_document_summaries(),
            "modelo_embedding": EMBEDDING_MODEL_NAME,
            "index_info": get_index_info(),
            "storage_consistent": is_storage_consistent(),
            "server_instance_id": SERVER_INSTANCE_ID,
            "process_id": os.getpid(),
            "started_at": SERVER_STARTED_AT,
            "debug": bool(app.debug),
            **embedding_status,
        }
    )


@app.get("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    try:
        acquire_instance_lock()
    except RuntimeError as exc:
        LOGGER.error("%s", exc)
        raise SystemExit(1)
    warm_embedding_model_async()
    LOGGER.info(
        "Iniciando aplicação pid=%s instance=%s em http://%s:%s debug=%s",
        os.getpid(),
        SERVER_INSTANCE_ID,
        FLASK_HOST,
        FLASK_PORT,
        FLASK_DEBUG,
    )
    app.run(
        host=FLASK_HOST,
        port=FLASK_PORT,
        debug=FLASK_DEBUG,
        use_reloader=False,
    )

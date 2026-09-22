"""Configuração central, sem efeitos pesados durante o import."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
from types import SimpleNamespace
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


EMBEDDING_OFFLINE = _env_bool("EMBEDDING_OFFLINE", True)
GROQ_TRUST_ENV = _env_bool("GROQ_TRUST_ENV", False)
FLASK_DEBUG = _env_bool("FLASK_DEBUG", False)
FLASK_HOST = os.getenv("FLASK_HOST", "127.0.0.1")
FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))

# Deve ser definido antes de qualquer import de Hugging Face/transformers.
if EMBEDDING_OFFLINE:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

UPLOAD_FOLDER = PROJECT_ROOT / "uploads"
DATA_DIR = PROJECT_ROOT / "data"
CONFIG_DIR = PROJECT_ROOT / "config"
BACKUP_DIR = PROJECT_ROOT / "backups"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {"pdf"}
INDEX_PATH = PROJECT_ROOT / "vector_index.faiss"
METADATA_PATH = PROJECT_ROOT / "chunks_metadata.json"
INDEX_INFO_PATH = DATA_DIR / "vector_index_info.json"
MANIFEST_PATH = DATA_DIR / "documents_manifest.json"
STORAGE_LOCK_PATH = DATA_DIR / ".storage.lock"

CHUNK_SIZE_WORDS = int(os.getenv("CHUNK_SIZE_WORDS", "500"))
CHUNK_OVERLAP_WORDS = int(os.getenv("CHUNK_OVERLAP_WORDS", "80"))
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(50 * 1024 * 1024)))
MAX_CONTENT_LENGTH = MAX_UPLOAD_BYTES

EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "all-MiniLM-L6-v2")
GROQ_MODEL_NAME = os.getenv("GROQ_MODEL_NAME", "openai/gpt-oss-120b")
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0"))
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "800"))
BENCHMARK_SEED = int(os.getenv("BENCHMARK_SEED", "42"))
AUTO_SYNC_UPLOADS = os.getenv("AUTO_SYNC_UPLOADS", "false").lower() in {"1", "true", "yes"}

_embedding_model: Any | None = None
_llm: Any | None = None
_generation_llm: Any | None = None
_model_lock = threading.RLock()
_embedding_state_lock = threading.RLock()
_embedding_model_status = "not_started"
_embedding_model_load_ms: float | None = None
_embedding_model_error: str | None = None
_embedding_load_started: float | None = None
_embedding_warmup_thread: threading.Thread | None = None
_embedding_model_source: str | None = None
_embedding_model_snapshot: str | None = None
LOGGER = logging.getLogger(__name__)

_GROQ_KEY_PATTERN = re.compile(r"^gsk_[A-Za-z0-9_-]{20,}$")
_GROQ_ROTATABLE_STATUS_CODES = {401, 403, 429}


def _load_groq_api_keys(env_file: Path | None = None) -> list[str]:
    """Carrega chaves Groq sem expor valores e preservando a ordem configurada.

    A chave ativa continua sendo a principal. Também são aceitas chaves em
    ``GROQCLOUD_API_KEYS`` (separadas por vírgula/ponto e vírgula), variáveis
    numeradas como ``GROQCLOUD_API_KEY_2`` e, por compatibilidade com o arquivo
    atual do projeto, comentários formados exclusivamente por ``# gsk_...``.
    """

    candidates: list[str] = []

    def add(value: str | None) -> None:
        normalized = (value or "").strip()
        if _GROQ_KEY_PATTERN.fullmatch(normalized) and normalized not in candidates:
            candidates.append(normalized)

    add(os.getenv("GROQCLOUD_API_KEY"))
    for value in re.split(r"[,;\s]+", os.getenv("GROQCLOUD_API_KEYS", "")):
        add(value)
    for name, value in sorted(os.environ.items()):
        if re.fullmatch(r"GROQCLOUD_API_KEY_\d+", name):
            add(value)

    path = env_file or (PROJECT_ROOT / ".env")
    if path.is_file():
        for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = re.fullmatch(r"\s*#\s*(gsk_[A-Za-z0-9_-]{20,})\s*", raw_line)
            if match:
                add(match.group(1))
    return candidates


def _is_rotatable_groq_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in _GROQ_ROTATABLE_STATUS_CODES:
        return True
    response = getattr(exc, "response", None)
    if getattr(response, "status_code", None) in _GROQ_ROTATABLE_STATUS_CODES:
        return True
    message = str(exc).casefold()
    return any(
        marker in message
        for marker in (
            "rate limit",
            "quota",
            "tokens per day",
            "invalid api key",
            "authentication",
        )
    )


class _RotatingGroqCompletionClient:
    """Alterna chaves somente após falhas que não geram uma conclusão."""

    def __init__(self, clients: list[Any]):
        if not clients:
            raise ValueError("Ao menos um cliente Groq é obrigatório.")
        self._clients = clients
        self._active_index = 0
        self._lock = threading.Lock()

    @property
    def key_count(self) -> int:
        return len(self._clients)

    def complete(self, prompt: str) -> Any:
        last_error: Exception | None = None
        for _attempt in range(len(self._clients)):
            with self._lock:
                index = self._active_index
                client = self._clients[index]
            try:
                response = client.chat.completions.create(
                    model=GROQ_MODEL_NAME,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=GROQ_TEMPERATURE,
                    max_tokens=GROQ_MAX_TOKENS,
                    reasoning_effort=GROQ_REASONING_EFFORT,
                )
                return SimpleNamespace(
                    text=response.choices[0].message.content or "",
                    raw={"usage": response.usage},
                )
            except Exception as exc:
                last_error = exc
                if not _is_rotatable_groq_error(exc):
                    raise
                with self._lock:
                    if self._active_index == index:
                        self._active_index = (index + 1) % len(self._clients)
        assert last_error is not None
        raise last_error


class EmbeddingModelError(RuntimeError):
    """Erro base seguro do modelo local."""


class EmbeddingModelLoadingError(EmbeddingModelError):
    """Modelo ainda está sendo preparado."""


class EmbeddingModelUnavailableError(EmbeddingModelError):
    """Modelo local não pode ser utilizado."""


def _embedding_repo_id() -> str:
    if "/" in EMBEDDING_MODEL_NAME:
        return EMBEDDING_MODEL_NAME
    return f"sentence-transformers/{EMBEDDING_MODEL_NAME}"


def _load_embedding_model() -> tuple[Any, str, str | None]:
    from sentence_transformers import SentenceTransformer

    if not EMBEDDING_OFFLINE:
        return SentenceTransformer(EMBEDDING_MODEL_NAME), "online_or_cache", None

    try:
        from huggingface_hub import snapshot_download
        from huggingface_hub.errors import LocalEntryNotFoundError
    except ImportError as exc:
        raise EmbeddingModelUnavailableError(
            "A dependência huggingface_hub não está disponível."
        ) from exc
    try:
        cached_model_path = Path(
            snapshot_download(
                _embedding_repo_id(),
                local_files_only=True,
            )
        ).resolve()
    except (LocalEntryNotFoundError, FileNotFoundError, OSError) as exc:
        raise EmbeddingModelUnavailableError(
            "O modelo de busca não está disponível no cache local."
        ) from exc

    if not cached_model_path.is_dir():
        raise EmbeddingModelUnavailableError(
            "O snapshot local do modelo de busca não é um diretório válido."
        )

    model = SentenceTransformer(str(cached_model_path), local_files_only=True)
    return model, "local_cache", cached_model_path.name


def _setup_tesseract() -> str | None:
    tesseract_cmd = os.getenv("TESSERACT_CMD") or shutil.which("tesseract")
    if not tesseract_cmd:
        for candidate in (
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ):
            if Path(candidate).exists():
                tesseract_cmd = candidate
                break
    if tesseract_cmd:
        try:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        except ModuleNotFoundError:
            pass
    return tesseract_cmd


TESSERACT_CMD = _setup_tesseract()


def get_embedding_model() -> Any:
    """Carrega e reutiliza o modelo, publicando estado seguro para a interface."""
    global _embedding_model, _embedding_model_status, _embedding_model_load_ms
    global _embedding_model_error, _embedding_load_started
    global _embedding_model_source, _embedding_model_snapshot
    with _model_lock:
        if _embedding_model is not None:
            with _embedding_state_lock:
                _embedding_model_status = "ready"
                _embedding_model_error = None
            return _embedding_model
        with _embedding_state_lock:
            if _embedding_model_status != "loading":
                _embedding_model_status = "loading"
                _embedding_model_error = None
                _embedding_load_started = time.perf_counter()
            started = _embedding_load_started or time.perf_counter()
        try:
            _embedding_model, _embedding_model_source, _embedding_model_snapshot = (
                _load_embedding_model()
            )
        except Exception as exc:
            elapsed = round((time.perf_counter() - started) * 1000, 1)
            with _embedding_state_lock:
                _embedding_model_status = "error"
                _embedding_model_load_ms = elapsed
                _embedding_model_error = "Falha ao preparar o modelo de busca."
                _embedding_model_source = None
                _embedding_model_snapshot = None
            if isinstance(exc, EmbeddingModelError):
                raise
            raise EmbeddingModelUnavailableError(
                "Falha ao carregar o modelo de busca do cache local."
            ) from exc
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        with _embedding_state_lock:
            _embedding_model_status = "ready"
            _embedding_model_load_ms = elapsed
            _embedding_model_error = None
    return _embedding_model


def get_embedding_model_status() -> dict[str, Any]:
    """Retorna somente informações operacionais seguras para exposição no `/status`."""
    with _embedding_state_lock:
        return {
            "embedding_model_status": _embedding_model_status,
            "embedding_model_load_ms": _embedding_model_load_ms,
            "embedding_model_error": _embedding_model_error,
            "embedding_model_source": _embedding_model_source,
            "embedding_model_snapshot": _embedding_model_snapshot,
        }


def require_embedding_ready() -> None:
    status = get_embedding_model_status()["embedding_model_status"]
    if status in {"not_started", "loading"}:
        raise EmbeddingModelLoadingError("O modelo de busca ainda está sendo preparado.")
    if status != "ready" or _embedding_model is None:
        raise EmbeddingModelUnavailableError("O modelo de busca está indisponível.")


def warm_embedding_model_async() -> bool:
    """Inicia um único aquecimento em daemon; não é chamado durante imports."""
    global _embedding_warmup_thread, _embedding_model_status
    global _embedding_model_error, _embedding_load_started
    with _embedding_state_lock:
        if _embedding_model is not None or _embedding_model_status == "ready":
            return False
        if _embedding_warmup_thread is not None and _embedding_warmup_thread.is_alive():
            return False
        _embedding_model_status = "loading"
        _embedding_model_error = None
        _embedding_load_started = time.perf_counter()

        def _warm() -> None:
            LOGGER.info("Preparando modelo de embeddings %s em segundo plano.", EMBEDDING_MODEL_NAME)
            started = time.perf_counter()
            try:
                get_embedding_model()
            except Exception:
                LOGGER.exception("Falha ao preparar o modelo de embeddings.")
                return
            LOGGER.info(
                "Modelo de embeddings pronto em %.1f ms.",
                (time.perf_counter() - started) * 1000,
            )

        _embedding_warmup_thread = threading.Thread(
            target=_warm,
            name="embedding-model-warmup",
            daemon=True,
        )
        _embedding_warmup_thread.start()
        return True


def get_llm() -> Any:
    """Cria o cliente Groq sob demanda, permitindo testes sem chave real."""
    global _llm
    with _model_lock:
        if _llm is None:
            api_key = os.getenv("GROQCLOUD_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "GROQCLOUD_API_KEY não definida. Configure-a no .env antes de chamar o LLM."
                )
            from llama_index.llms.groq import Groq

            _llm = Groq(
                model=GROQ_MODEL_NAME,
                api_key=api_key,
                temperature=GROQ_TEMPERATURE,
                reasoning_effort=GROQ_REASONING_EFFORT,
                max_tokens=GROQ_MAX_TOKENS,
                timeout=60.0,
                max_retries=3,
                context_window=131072,
            )
    return _llm


def get_generation_llm() -> Any:
    """Cliente Groq direto para evitar camadas duplicadas de retry nos experimentos."""
    global _generation_llm
    with _model_lock:
        if _generation_llm is None:
            api_keys = _load_groq_api_keys()
            if not api_keys:
                raise RuntimeError("GROQCLOUD_API_KEY não definida. Configure-a no .env antes de chamar o LLM.")
            from groq import Groq as GroqClient
            import httpx

            sdk_clients = []
            for api_key in api_keys:
                http_client = httpx.Client(
                    trust_env=GROQ_TRUST_ENV,
                    timeout=httpx.Timeout(60.0),
                )
                sdk_clients.append(
                    GroqClient(
                        api_key=api_key,
                        timeout=60.0,
                        max_retries=0,
                        http_client=http_client,
                    )
                )
            _generation_llm = _RotatingGroqCompletionClient(sdk_clients)
    return _generation_llm


def load_model_pricing() -> dict[str, Any]:
    path = CONFIG_DIR / "model_pricing.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def estimate_cost(prompt_tokens: int | None, completion_tokens: int | None) -> dict[str, Any]:
    pricing = load_model_pricing().get(GROQ_MODEL_NAME, {})
    if prompt_tokens is None or completion_tokens is None or not pricing:
        return {
            "estimated_cost": None,
            "currency": pricing.get("currency", "USD"),
            "pricing_source": pricing.get("pricing_source", "configuration_unavailable"),
        }
    input_rate = pricing.get("input_per_million_tokens")
    output_rate = pricing.get("output_per_million_tokens")
    if input_rate is None or output_rate is None:
        return {"estimated_cost": None, "currency": "USD", "pricing_source": "configuration_unavailable"}
    cost = (prompt_tokens * input_rate + completion_tokens * output_rate) / 1_000_000
    return {
        "estimated_cost": round(cost, 8),
        "currency": pricing.get("currency", "USD"),
        "pricing_source": pricing.get("pricing_source", "configuration"),
    }

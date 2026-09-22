from __future__ import annotations

import importlib.util
import math
import os
import re
import sys
import time
import types
from typing import Any, Generator

from pydantic import PrivateAttr

from services.config import (
    EMBEDDING_MODEL_NAME,
    GROQ_MAX_TOKENS,
    GROQ_MODEL_NAME,
    GROQ_REASONING_EFFORT,
    GROQ_TEMPERATURE,
)

_cached_evaluator_llm: Any | None = None
_cached_evaluator_embeddings: Any | None = None
MAX_EVALUATION_CONTEXT_CHARS = 12_000


def _evaluation_contexts(row: dict[str, Any]) -> list[str]:
    """Limita o contexto do juiz, priorizando o chunk da evidência literal."""
    sources = [source for source in row.get("sources", []) if source.get("text")]
    evidence_chunk_id = (row.get("evidence") or {}).get("chunk_id")
    ordered = sorted(
        sources,
        key=lambda source: (
            source.get("chunk_id") != evidence_chunk_id,
            -float(source.get("retrieval_score") or 0.0),
        ),
    )
    contexts: list[str] = []
    remaining = MAX_EVALUATION_CONTEXT_CHARS
    seen: set[str] = set()
    for source in ordered:
        text = str(source.get("text") or "").strip()
        fingerprint = str(source.get("chunk_id") or text)
        if not text or fingerprint in seen or remaining <= 0:
            continue
        seen.add(fingerprint)
        excerpt = text[:remaining]
        contexts.append(excerpt)
        remaining -= len(excerpt)
    return contexts


def _tpm_retry_seconds(message: str) -> float | None:
    """Extrai o Retry-After apenas de limites por minuto da Groq."""
    if "tokens per minute (TPM)" not in message:
        return None
    match = re.search(r"try again in (?:(\d+)m)?([0-9.]+)s", message, re.IGNORECASE)
    if not match:
        return 15.0
    return int(match.group(1) or 0) * 60 + float(match.group(2)) + 1.0


def _build_evaluator_llm() -> Any:
    """Cliente que respeita Retry-After de TPM sem ocultar esgotamento diário."""
    api_key = os.getenv("GROQCLOUD_API_KEY")
    if not api_key:
        raise RuntimeError("GROQCLOUD_API_KEY não definida.")
    from groq import Groq as GroqClient
    from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata
    from llama_index.core.llms.callbacks import llm_completion_callback

    class FreeTierGroqEvaluator(CustomLLM):
        model_name: str = GROQ_MODEL_NAME
        max_tokens: int = GROQ_MAX_TOKENS
        _client: Any = PrivateAttr()

        def __init__(self) -> None:
            super().__init__(model_name=GROQ_MODEL_NAME, max_tokens=GROQ_MAX_TOKENS)
            self._client = GroqClient(api_key=api_key, timeout=60.0, max_retries=0)

        @property
        def metadata(self) -> Any:
            return LLMMetadata(
                context_window=131072,
                num_output=self.max_tokens,
                is_chat_model=False,
                model_name=self.model_name,
            )

        @llm_completion_callback()
        def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> Any:
            for attempt in range(8):
                try:
                    response = self._client.chat.completions.create(
                        model=self.model_name,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=GROQ_TEMPERATURE,
                        max_tokens=self.max_tokens,
                        reasoning_effort=GROQ_REASONING_EFFORT,
                    )
                    return CompletionResponse(
                        text=response.choices[0].message.content or "",
                        raw=response,
                    )
                except Exception as exc:
                    wait_seconds = _tpm_retry_seconds(str(exc))
                    if wait_seconds is None or attempt == 7:
                        raise
                    time.sleep(min(wait_seconds, 75.0))
            raise RuntimeError("Retentativas TPM esgotadas.")

        @llm_completion_callback()
        def stream_complete(
            self, prompt: str, formatted: bool = False, **kwargs: Any
        ) -> Generator[Any, None, None]:
            response = self.complete(prompt, formatted=formatted, **kwargs)
            yield CompletionResponse(text=response.text, delta=response.text)

    return FreeTierGroqEvaluator()


def _result_value(result: Any, name: str) -> float | None:
    try:
        frame = result.to_pandas()
        value = frame.iloc[0].get(name)
        return None if value is None else float(value)
    except Exception:
        try:
            value = result[name]
            return None if value is None else float(value)
        except Exception:
            return None


def _install_ragas_langchain_compatibility_shim() -> None:
    """Contorna import removido do LangChain que o RAGAS 0.4.3 ainda referencia."""
    module_name = "langchain_community.chat_models.vertexai"
    if module_name in sys.modules:
        return
    if importlib.util.find_spec(module_name) is not None:
        return
    module = types.ModuleType(module_name)

    class ChatVertexAI:  # pragma: no cover - usado somente em isinstance interno
        pass

    module.ChatVertexAI = ChatVertexAI
    sys.modules[module_name] = module


def score_ragas_row(
    row: dict[str, Any],
    *,
    evaluator_llm: Any | None = None,
    evaluator_embeddings: Any | None = None,
) -> dict[str, Any]:
    """Calcula RAGAS real; Answer Correctness exige referência humana validada."""
    try:
        _install_ragas_langchain_compatibility_shim()
        from ragas import EvaluationDataset, evaluate
        from ragas.embeddings import HuggingFaceEmbeddings
        from ragas.llms import LlamaIndexLLMWrapper
        from ragas.metrics import AnswerCorrectness, Faithfulness
        from ragas.run_config import RunConfig

        global _cached_evaluator_llm, _cached_evaluator_embeddings
        if evaluator_llm is None and _cached_evaluator_llm is None:
            _cached_evaluator_llm = LlamaIndexLLMWrapper(_build_evaluator_llm())
        if evaluator_embeddings is None and _cached_evaluator_embeddings is None:
            _cached_evaluator_embeddings = HuggingFaceEmbeddings(
                model=f"sentence-transformers/{EMBEDDING_MODEL_NAME}"
            )
        llm = evaluator_llm or _cached_evaluator_llm
        embeddings = evaluator_embeddings or _cached_evaluator_embeddings
        sample = {
            "user_input": row["question"],
            "response": row.get("value") or "",
            "retrieved_contexts": _evaluation_contexts(row),
        }
        metrics: list[Any] = [Faithfulness()]
        reference = row.get("reference") or {}
        if reference.get("validated_by_human") and reference.get("value") is not None:
            sample["reference"] = str(reference["value"])
            metrics.append(AnswerCorrectness())
        dataset = EvaluationDataset.from_list([sample])
        result = evaluate(
            dataset=dataset,
            metrics=metrics,
            llm=llm,
            embeddings=embeddings,
            run_config=RunConfig(
                timeout=60,
                max_workers=1,
                max_retries=1,
                max_wait=15,
                seed=42,
            ),
            raise_exceptions=True,
            show_progress=False,
        )
        return {
            "faithfulness": _result_value(result, "faithfulness"),
            "answer_correctness": _result_value(result, "answer_correctness"),
            "ragas_error": None,
        }
    except Exception as exc:
        detail = str(exc).strip()
        error = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
        return {"faithfulness": None, "answer_correctness": None, "ragas_error": error}


def score_ragas_rows(
    rows: list[dict[str, Any]],
    *,
    evaluator_llm: Any | None = None,
    evaluator_embeddings: Any | None = None,
) -> list[dict[str, Any]]:
    """Avalia um lote homogêneo; todas as linhas devem ter ou não ter referência."""
    if not rows:
        return []
    has_reference = [
        bool((row.get("reference") or {}).get("validated_by_human"))
        and (row.get("reference") or {}).get("value") is not None
        for row in rows
    ]
    if len(set(has_reference)) != 1:
        raise ValueError("O lote RAGAS deve ser homogêneo quanto à presença de referência.")
    try:
        _install_ragas_langchain_compatibility_shim()
        from ragas import EvaluationDataset, evaluate
        from ragas.embeddings import HuggingFaceEmbeddings
        from ragas.llms import LlamaIndexLLMWrapper
        from ragas.metrics import AnswerCorrectness, Faithfulness
        from ragas.run_config import RunConfig

        global _cached_evaluator_llm, _cached_evaluator_embeddings
        if evaluator_llm is None and _cached_evaluator_llm is None:
            _cached_evaluator_llm = LlamaIndexLLMWrapper(_build_evaluator_llm())
        if evaluator_embeddings is None and _cached_evaluator_embeddings is None:
            _cached_evaluator_embeddings = HuggingFaceEmbeddings(
                model=f"sentence-transformers/{EMBEDDING_MODEL_NAME}"
            )
        llm = evaluator_llm or _cached_evaluator_llm
        embeddings = evaluator_embeddings or _cached_evaluator_embeddings
        samples = []
        for row in rows:
            sample = {
                "user_input": row["question"],
                "response": row.get("value") or "",
                "retrieved_contexts": _evaluation_contexts(row),
            }
            if has_reference[0]:
                sample["reference"] = str((row.get("reference") or {})["value"])
            samples.append(sample)
        metrics: list[Any] = [Faithfulness()]
        if has_reference[0]:
            metrics.append(AnswerCorrectness())
        result = evaluate(
            dataset=EvaluationDataset.from_list(samples),
            metrics=metrics,
            llm=llm,
            embeddings=embeddings,
            run_config=RunConfig(
                timeout=60,
                max_workers=1,
                max_retries=1,
                max_wait=15,
                seed=42,
            ),
            raise_exceptions=True,
            show_progress=False,
            batch_size=1,
        )
        frame = result.to_pandas()
        output = []
        for _, record in frame.iterrows():
            faithfulness = record.get("faithfulness")
            correctness = record.get("answer_correctness") if has_reference[0] else None
            faithfulness = None if faithfulness is None or (isinstance(faithfulness, float) and math.isnan(faithfulness)) else float(faithfulness)
            correctness = None if correctness is None or (isinstance(correctness, float) and math.isnan(correctness)) else float(correctness)
            required_missing = faithfulness is None or (has_reference[0] and correctness is None)
            output.append(
                {
                    "faithfulness": faithfulness,
                    "answer_correctness": correctness,
                    "ragas_error": "metric_unavailable" if required_missing else None,
                }
            )
        if len(output) != len(rows):
            raise RuntimeError(f"RAGAS retornou {len(output)} resultados para {len(rows)} amostras.")
        return output
    except Exception as exc:
        detail = str(exc).strip()
        error = f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__
        return [
            {"faithfulness": None, "answer_correctness": None, "ragas_error": error}
            for _ in rows
        ]

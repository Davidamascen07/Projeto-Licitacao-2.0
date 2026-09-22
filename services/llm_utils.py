"""Chamadas ao LLM com métricas de uso sem acoplamento à Groq nos testes."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from .config import GROQ_MAX_TOKENS, estimate_cost, get_generation_llm

_RATE_LOCK = threading.Lock()
_NEXT_ALLOWED_CALL = 0.0
_TPM_LIMIT = int(os.getenv("GROQ_TPM_LIMIT", "8000"))
_TPM_SAFETY_FACTOR = float(os.getenv("GROQ_TPM_SAFETY_FACTOR", "0.85"))


def _lookup_usage(response: Any) -> tuple[int | None, int | None, int | None]:
    candidates = [
        getattr(response, "raw", None),
        getattr(response, "additional_kwargs", None),
        response,
    ]
    usage: Any = None
    for candidate in candidates:
        if candidate is None:
            continue
        if isinstance(candidate, dict):
            usage = candidate.get("usage") or candidate.get("usage_metadata")
        else:
            usage = getattr(candidate, "usage", None) or getattr(candidate, "usage_metadata", None)
        if usage:
            break
    if usage is None:
        return None, None, None

    def value(*names: str) -> int | None:
        for name in names:
            result = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
            if result is not None:
                return int(result)
        return None

    prompt = value("prompt_tokens", "input_tokens")
    completion = value("completion_tokens", "output_tokens")
    total = value("total_tokens")
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    return prompt, completion, total


def complete_with_metrics(
    prompt: str,
    *,
    llm_client: Any | None = None,
    max_retries: int = 1,
    retry_wait_seconds: float = 60.0,
) -> dict[str, Any]:
    """Executa exatamente uma chamada remota.

    ``max_retries`` e ``retry_wait_seconds`` permanecem na assinatura por
    compatibilidade, mas não provocam uma segunda geração. Um retry após o
    servidor aceitar a requisição pode duplicar respostas e uso de tokens.
    """
    global _NEXT_ALLOWED_CALL
    del max_retries, retry_wait_seconds
    enforce_rate_limit = llm_client is None
    client = llm_client or get_generation_llm()
    rate_limit_wait_ms = 0.0
    if enforce_rate_limit:
        with _RATE_LOCK:
            delay = _NEXT_ALLOWED_CALL - time.monotonic()
            if delay > 0:
                wait_started = time.perf_counter()
                time.sleep(delay)
                rate_limit_wait_ms += (time.perf_counter() - wait_started) * 1000
            call_started = time.monotonic()
            if _TPM_LIMIT > 0:
                safe_tpm = max(1.0, _TPM_LIMIT * _TPM_SAFETY_FACTOR)
                reserved_tokens = max(1, len(prompt) // 4) + GROQ_MAX_TOKENS
                _NEXT_ALLOWED_CALL = call_started + (reserved_tokens / safe_tpm) * 60.0
    started = time.perf_counter()
    try:
        response = client.complete(prompt)
    except Exception as exc:
        error_text = str(exc).casefold()
        if "tokens per day" in error_text or "(tpd)" in error_text:
            raise RuntimeError(
                "Cota diária da Groq esgotada; checkpoint preservado. "
                "Retome após a renovação da janela TPD."
            ) from exc
        raise
    text = response.text if hasattr(response, "text") else str(response)
    prompt_tokens, completion_tokens, total_tokens = _lookup_usage(response)
    usage = {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "usage_available": total_tokens is not None,
    }
    usage.update(estimate_cost(prompt_tokens, completion_tokens))
    return {
        "text": text,
        "llm_ms": round((time.perf_counter() - started) * 1000, 1),
        "rate_limit_wait_ms": round(rate_limit_wait_ms, 1),
        "usage": usage,
    }

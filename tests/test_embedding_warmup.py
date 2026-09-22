from __future__ import annotations

import threading
import sys
from types import SimpleNamespace

import pytest

from services import config


def test_warmup_starts_once_and_does_not_duplicate_model_load(monkeypatch):
    release = threading.Event()
    entered = threading.Event()
    calls = 0

    def fake_get_embedding_model():
        nonlocal calls
        calls += 1
        entered.set()
        release.wait(timeout=2)
        return object()

    monkeypatch.setattr(config, "_embedding_model", None)
    monkeypatch.setattr(config, "_embedding_model_status", "not_started")
    monkeypatch.setattr(config, "_embedding_model_error", None)
    monkeypatch.setattr(config, "_embedding_warmup_thread", None)
    monkeypatch.setattr(config, "get_embedding_model", fake_get_embedding_model)

    assert config.warm_embedding_model_async() is True
    assert entered.wait(timeout=1)
    assert config.warm_embedding_model_async() is False

    release.set()
    config._embedding_warmup_thread.join(timeout=2)

    assert calls == 1
    assert not config._embedding_warmup_thread.is_alive()


def test_warmup_reports_error_without_exposing_exception(monkeypatch):
    def failing_model():
        with config._embedding_state_lock:
            config._embedding_model_status = "error"
            config._embedding_model_error = "Falha ao preparar o modelo de busca."
        raise RuntimeError("segredo técnico")

    monkeypatch.setattr(config, "_embedding_model", None)
    monkeypatch.setattr(config, "_embedding_model_status", "not_started")
    monkeypatch.setattr(config, "_embedding_model_error", None)
    monkeypatch.setattr(config, "_embedding_warmup_thread", None)
    monkeypatch.setattr(config, "get_embedding_model", failing_model)

    assert config.warm_embedding_model_async() is True
    config._embedding_warmup_thread.join(timeout=2)
    status = config.get_embedding_model_status()

    assert status["embedding_model_status"] == "error"
    assert status["embedding_model_error"] == "Falha ao preparar o modelo de busca."


def test_embedding_model_prefers_local_cache(monkeypatch, tmp_path):
    calls = []
    model = object()
    cached_path = str(tmp_path)

    def fake_sentence_transformer(name, **kwargs):
        calls.append((name, kwargs))
        return model

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=fake_sentence_transformer),
    )
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=lambda *_args, **_kwargs: cached_path),
    )
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub.errors",
        SimpleNamespace(LocalEntryNotFoundError=OSError),
    )
    monkeypatch.setattr(config, "_embedding_model", None)
    monkeypatch.setattr(config, "_embedding_model_status", "not_started")
    monkeypatch.setattr(config, "_embedding_model_load_ms", None)
    monkeypatch.setattr(config, "_embedding_model_error", None)
    monkeypatch.setattr(config, "_embedding_load_started", None)

    assert config.get_embedding_model() is model
    assert calls == [(str(tmp_path.resolve()), {"local_files_only": True})]
    assert config.get_embedding_model_status()["embedding_model_status"] == "ready"


def test_embedding_model_does_not_fall_back_online_when_cache_is_missing(monkeypatch):
    calls = []
    model = object()

    def fake_sentence_transformer(name, **kwargs):
        calls.append((name, kwargs))
        return model

    def missing_snapshot(*_args, **_kwargs):
        raise OSError("cache ausente")

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=fake_sentence_transformer),
    )
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=missing_snapshot),
    )
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub.errors",
        SimpleNamespace(LocalEntryNotFoundError=OSError),
    )
    monkeypatch.setattr(config, "_embedding_model", None)
    monkeypatch.setattr(config, "_embedding_model_status", "not_started")
    monkeypatch.setattr(config, "_embedding_model_load_ms", None)
    monkeypatch.setattr(config, "_embedding_model_error", None)
    monkeypatch.setattr(config, "_embedding_load_started", None)

    with pytest.raises(config.EmbeddingModelUnavailableError):
        config.get_embedding_model()
    assert calls == []

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import app as app_module
from scripts import prepare_embedding_model


def test_second_instance_lock_is_refused(tmp_path):
    lock_path = tmp_path / "app.lock"
    try:
        app_module.acquire_instance_lock(lock_path)
        with pytest.raises(RuntimeError, match="Já existe uma instância"):
            app_module.acquire_instance_lock(lock_path)
    finally:
        app_module.release_instance_lock()


def test_offline_prepare_uses_local_snapshot_without_adapter_or_network(monkeypatch, tmp_path):
    calls = []

    def fake_snapshot_download(repo_id, *, local_files_only):
        calls.append((repo_id, local_files_only))
        return str(tmp_path)

    class FakeModel:
        def __init__(self, path, *, local_files_only):
            assert path == str(tmp_path.resolve())
            assert local_files_only is True

        def get_sentence_embedding_dimension(self):
            return 384

    monkeypatch.setattr(prepare_embedding_model, "load_dotenv", lambda *_args, **_kwargs: True)
    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=fake_snapshot_download),
    )
    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeModel),
    )

    result = prepare_embedding_model.prepare_model(offline_check=True)

    assert calls == [("sentence-transformers/all-MiniLM-L6-v2", True)]
    assert result["dimension"] == 384
    assert not (tmp_path / "adapter_config.json").exists()

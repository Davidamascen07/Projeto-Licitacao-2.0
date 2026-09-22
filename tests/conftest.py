from __future__ import annotations

import hashlib
from types import SimpleNamespace

import numpy as np


class FakeEmbeddingModel:
    def encode(self, texts, normalize_embeddings=False):
        rows = []
        for text in texts:
            digest = hashlib.sha256(str(text).encode("utf-8")).digest()
            vector = np.array([byte + 1 for byte in digest[:8]], dtype="float32")
            if normalize_embeddings:
                vector /= np.linalg.norm(vector)
            rows.append(vector)
        return np.vstack(rows)


class FakeLLM:
    def __init__(self, payload):
        self.payload = payload

    def complete(self, _prompt):
        return SimpleNamespace(
            text=self.payload,
            raw={"usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}},
        )

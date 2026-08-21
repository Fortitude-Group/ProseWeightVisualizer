"""Embedding-distance signal (research.md R4).

Default embedder: BAAI/bge-small-en-v1.5 pinned to an exact HF revision SHA.
Distance = 1 - cosine similarity of L2-normalised outputs (symmetric same-domain
comparison, so no query/passage prefixes). The embedder is deterministic given
its input; sentence-transformers is imported lazily.
"""

from __future__ import annotations

from typing import Protocol

DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


class Embedder(Protocol):
    def distance(self, a: str, b: str) -> float: ...


class BgeEmbedder:
    def __init__(self, model_id: str = DEFAULT_EMBED_MODEL, revision: str = "unpinned"):
        self.model_id = model_id
        self.revision = revision
        self._model = None

    def _load(self):  # pragma: no cover - needs model weights
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            raise RuntimeError(
                "BgeEmbedder needs the runtime extra: pip install 'proseweight[runtime]'"
            ) from e
        self._model = SentenceTransformer(self.model_id, revision=self.revision)

    def distance(self, a: str, b: str) -> float:  # pragma: no cover - needs weights
        import numpy as np

        if self._model is None:
            self._load()
        emb = self._model.encode([a, b], normalize_embeddings=True)
        return float(min(max(1.0 - np.dot(emb[0], emb[1]), 0.0), 1.0))

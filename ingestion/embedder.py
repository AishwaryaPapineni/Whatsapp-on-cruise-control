"""Embedding model + Chroma connection, loaded ONCE and shared (Session 2.2 Part 4).

EMBEDDER (env):
  st    (default) sentence-transformers "paraphrase-multilingual-mpnet-base-v2" -- the
        course's multilingual model, so Hinglish / Hindi / English land near each other.
  hash  deterministic character-n-gram vectors, NO download. Only for tests, CI and
        offline demos; it matches spelling, not meaning. Never use it live.
CHROMA_MODE (env):
  http       (default) chromadb.HttpClient(localhost:8000) -- the `chroma run` server
  persistent embedded folder (./chroma_data), handy when the server isn't running
  memory     in-process, for tests
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from functools import lru_cache

MODEL_NAME = os.getenv("EMBED_MODEL", "paraphrase-multilingual-mpnet-base-v2")
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))


class HashEmbedder:
    name = "hash-512 (offline test embedder)"
    dim = 512

    def encode(self, texts, show_progress_bar=False):
        single = isinstance(texts, str)
        out = [self._one(t) for t in ([texts] if single else texts)]
        return out[0] if single else out

    def _one(self, text: str) -> list[float]:
        v = [0.0] * self.dim
        t = f"  {re.sub(r'\s+', ' ', text.lower().strip())}  "
        grams = [t[i:i + n] for n in (2, 3, 4) for i in range(len(t) - n + 1)] + re.findall(r"\w+", t)
        for g in grams:
            h = int(hashlib.md5(g.encode()).hexdigest(), 16)
            v[h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]


class STEmbedder:
    def __init__(self, model_name: str = MODEL_NAME):
        from sentence_transformers import SentenceTransformer

        print(f"Loading multilingual embedding model {model_name} (first run downloads ~1GB)...")
        self.model = SentenceTransformer(model_name)
        self.name = model_name

    def encode(self, texts, show_progress_bar=False):
        vecs = self.model.encode(texts, show_progress_bar=show_progress_bar, normalize_embeddings=True)
        return vecs.tolist()


@lru_cache(maxsize=1)
def get_embedder():
    return HashEmbedder() if os.getenv("EMBEDDER", "st").lower() == "hash" else STEmbedder()


_CLIENT = None


def get_client():
    global _CLIENT
    if _CLIENT is None:
        import chromadb

        mode = os.getenv("CHROMA_MODE", "http").lower()
        if mode == "memory":
            _CLIENT = chromadb.EphemeralClient()
        elif mode == "persistent":
            _CLIENT = chromadb.PersistentClient(path=os.getenv("CHROMA_PATH", "chroma_data"))
        else:
            _CLIENT = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    return _CLIENT


def set_client(client) -> None:
    """Tests inject a client here."""
    global _CLIENT
    _CLIENT = client


def collection(relationship: str, create: bool = True):
    name = f"history_{relationship}"
    client = get_client()
    if create:
        # cosine space -> distance 0 = same meaning, ~1 = unrelated; makes thresholds readable
        return client.get_or_create_collection(name, metadata={"hnsw:space": "cosine", "embedder": get_embedder().name})
    return client.get_collection(name)

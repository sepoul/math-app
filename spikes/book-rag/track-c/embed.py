"""Track C — embeddings (OpenAI text-embedding-3-small, 1536-d).

One signal, not the system (spec §5/§13). Batched calls; key from BOOK_RAG_ENV
via _shared.db.load_env(). Returns numpy float32 arrays so they round-trip into
the pgvector `vector` columns (pgvector.psycopg is registered on connect()).
"""
from __future__ import annotations

import sys
import time
import pathlib

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _shared.db import load_env  # noqa: E402

MODEL = "text-embedding-3-small"
DIM = 1536
# text-embedding-3-small hard-caps at 8192 tokens/input. Big section nodes (a
# 16-page §) blow past that. Truncate by chars at a conservative ~3.2 chars/token
# budget (≈7000 tokens) — only section nodes hit this; leaves stay whole. A real
# build would embed a section *summary* (spec §12), not the raw concatenation.
MAX_CHARS = 22000
_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=load_env()["OPENAI_API_KEY"])
    return _client


def embed_texts(texts: list[str], batch: int = 128) -> tuple[list[np.ndarray], dict]:
    """Embed a list of strings. Returns (vectors, stats). stats has wall time +
    an approximate token count (sum of usage.total_tokens across batches)."""
    client = _get_client()
    out: list[np.ndarray] = []
    total_tokens = 0
    t0 = time.time()
    for i in range(0, len(texts), batch):
        chunk = [(t if t.strip() else " ")[:MAX_CHARS] for t in texts[i:i + batch]]
        resp = client.embeddings.create(model=MODEL, input=chunk)
        for d in resp.data:
            out.append(np.asarray(d.embedding, dtype=np.float32))
        total_tokens += getattr(resp.usage, "total_tokens", 0) or 0
    dt = time.time() - t0
    return out, {"seconds": dt, "tokens": total_tokens, "n": len(texts), "model": MODEL}


def embed_one(text: str) -> np.ndarray:
    vecs, _ = embed_texts([text])
    return vecs[0]

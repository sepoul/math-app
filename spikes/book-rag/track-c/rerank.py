"""Track C — LLM reranker (spec §13 reranker stage).

Retrieve broadly (hybrid top-20), then rerank with a tightly-constrained Claude
scorer that ranks the candidates — it does NOT invent passages (spec §13). We
use `claude-haiku-4-5` (cheapest/fastest current model) for a bulk relevance-
scoring task: one call ranks all candidates, returns an ordered index list as
JSON. Key from BOOK_RAG_ENV via _shared.db.load_env().

Cost is reported (input/output tokens per call) so the speed/cost ledger is honest.
"""
from __future__ import annotations

import sys
import json
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _shared.db import load_env  # noqa: E402

MODEL = "claude-haiku-4-5"  # cheapest/fastest current model for bulk scoring
_client = None


def _get_client():
    global _client
    if _client is None:
        import anthropic
        # per-request timeout + 1 retry so a single slow call can't wedge the eval
        _client = anthropic.Anthropic(api_key=load_env()["ANTHROPIC_API_KEY"],
                                      timeout=30.0, max_retries=1)
    return _client


SYSTEM = (
    "You are a retrieval reranker for a mathematics textbook (Tu, An Introduction "
    "to Manifolds). Given a query and a numbered list of candidate passages, rank "
    "them by how well each ANSWERS the query. Consider the passage's type "
    "(definition/theorem/proof/example/exercise/section), its label, and its text. "
    "You only RANK the given candidates; never invent passages or text. "
    "Respond with ONLY a JSON array of candidate numbers, best first, e.g. [3,1,2]. "
    "Include every candidate number exactly once."
)


def claude_rerank(query: str, cands: list) -> tuple[list[int], dict]:
    """Return (order, cost). `order` is a permutation of indices into `cands`
    (best first). `cands` are Cand objects with .kind/.label/.text. Degrades to
    identity order on any parse failure (rerank must never drop candidates)."""
    if not cands:
        return [], {}
    lines = []
    for i, c in enumerate(cands):
        kind = getattr(c, "kind", None) or "?"
        label = getattr(c, "label", None) or ""
        text = " ".join((getattr(c, "text", "") or "").split())[:300]
        lines.append(f"[{i}] ({kind} {label}) {text}")
    user = f"Query: {query}\n\nCandidates:\n" + "\n".join(lines) + \
           "\n\nReturn the JSON array of candidate numbers, best first."

    try:
        client = _get_client()
        resp = client.messages.create(
            model=MODEL, max_tokens=512,
            system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        cost = {"in": resp.usage.input_tokens, "out": resp.usage.output_tokens}
        text = next((b.text for b in resp.content if b.type == "text"), "")
        return _parse_order(text, len(cands)), cost
    except Exception:
        # never let a rerank failure drop candidates or wedge the eval
        return list(range(len(cands))), {"in": 0, "out": 0}


def _parse_order(text: str, n: int) -> list[int]:
    import re
    m = re.search(r"\[[\d,\s]*\]", text)
    if not m:
        return list(range(n))
    try:
        arr = json.loads(m.group(0))
    except Exception:
        return list(range(n))
    seen, order = set(), []
    for x in arr:
        if isinstance(x, int) and 0 <= x < n and x not in seen:
            order.append(x)
            seen.add(x)
    for i in range(n):  # append any the model dropped, preserving completeness
        if i not in seen:
            order.append(i)
    return order

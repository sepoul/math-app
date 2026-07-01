#!/usr/bin/env python3
"""math_book deploy-smoke + eval — score the DEPLOYED book_retrieve vs the spike.

End-to-end against the LIVE platform (no in-process job logic):

  1. POST the Tu PDF to /media  -> storage_ref
  2. submit `book_index` (book_id, page_range = the shared slice) -> wait for
     the BookStructureArtifact + BookIndexArtifact + `math_book_chunks` rows
  3. submit `book_retrieve` for every query in queries/queries.json (k=10),
     collect the ranked, source-traceable hits from the job result
  4. score the run through the PORTED harness (eval/metrics.py, verbatim from
     `spike/eval-efficiency:track-d/metrics.py`) against eval/queries/gold.json,
     reporting recall@k / MRR / nDCG / exact-label-hit / source-traceability,
     PAGE-AWARE (right place) + STRICT (right unit), plus a label-less naive
     baseline (page-mode) — the same two-column figure the spike is cited by.

The retriever contract the harness expects (track-d/harness.py) is fed straight
from the deployed `BookRetrievalHit`s: {node_id, chunk_id, score, label,
page_pdf_start, heading_path}.

Run (host):  python packages/math-book/eval/run_eval.py
Env: API_URL (default http://localhost:8000), TU_PDF (default the repo copy),
     BOOK_ID (default tu_manifolds), SLICE_START/SLICE_END (default 22..101),
     SKIP_INDEX=1 to reuse an already-indexed book.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from metrics import GoldItem, RetrievedItem, score_run  # noqa: E402

API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")
BOOK_ID = os.environ.get("BOOK_ID", "tu_manifolds")
SLICE_START = int(os.environ.get("SLICE_START", "22"))
SLICE_END = int(os.environ.get("SLICE_END", "101"))
K = int(os.environ.get("K", "10"))
DEFAULT_PDF = pathlib.Path(__file__).resolve().parents[3] / "Tu_AnIntroductionToManifolds copy.pdf"
TU_PDF = pathlib.Path(os.environ.get("TU_PDF", str(DEFAULT_PDF)))
QUERIES = HERE / "queries" / "queries.json"
GOLD = HERE / "queries" / "gold.json"


# --------------------------------------------------------------------------- #
# tiny HTTP helpers (stdlib only — no domain / SDK dep in the harness)
# --------------------------------------------------------------------------- #
def _get(path: str) -> dict:
    with urllib.request.urlopen(f"{API_URL}{path}", timeout=60) as r:
        return json.loads(r.read())


def _post_json(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{API_URL}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"POST {path} -> {e.code}: {e.read().decode()[:800]}") from e


def _upload_media(pdf: pathlib.Path) -> str:
    """multipart/form-data POST /media -> storage_ref."""
    boundary = "----mathbookeval8f3c2a"
    body = bytearray()
    body += f"--{boundary}\r\n".encode()
    body += (f'Content-Disposition: form-data; name="file"; '
             f'filename="{pdf.name}"\r\n').encode()
    body += b"Content-Type: application/pdf\r\n\r\n"
    body += pdf.read_bytes()
    body += f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{API_URL}/media", data=bytes(body), method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        out = json.loads(r.read())
    ref = out.get("storage_ref") or out.get("ref") or out.get("id")
    if not ref:
        raise RuntimeError(f"/media returned no storage_ref: {out}")
    return ref


def _submit(payload: dict) -> str:
    out = _post_json("/jobs/runs/submit", payload)
    job_id = out.get("job_id") or out.get("id")
    if not job_id:
        raise RuntimeError(f"submit returned no job_id: {out}")
    return job_id


def _wait(job_id: str, *, timeout_s: int = 900, poll_s: float = 3.0) -> dict:
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout_s:
        st = _get(f"/jobs/{job_id}")
        status = (st.get("status") or st.get("state") or "").lower()
        if status != last:
            print(f"    job {job_id[:8]} status={status} (+{time.time()-t0:.0f}s)")
            last = status
        if status in ("completed", "succeeded", "success", "done"):
            return _get(f"/jobs/{job_id}/result")
        if status in ("failed", "error", "cancelled", "canceled"):
            raise RuntimeError(f"job {job_id} ended status={status}: {json.dumps(st)[:800]}")
        time.sleep(poll_s)
    raise RuntimeError(f"job {job_id} timed out after {timeout_s}s (last status={last})")


# --------------------------------------------------------------------------- #
# gold / query loaders (mirror track-d/harness.py)
# --------------------------------------------------------------------------- #
def load_queries() -> dict[str, dict]:
    data = json.loads(QUERIES.read_text())
    return {q["query_id"]: {"category": q["category"], "query_text": q["query_text"],
                            "intent": q.get("intent", "")} for q in data["queries"]}


def load_gold() -> dict[str, list[GoldItem]]:
    data = json.loads(GOLD.read_text())
    out: dict[str, list[GoldItem]] = {}
    for qid, items in data["gold"].items():
        out[qid] = [GoldItem(query_id=qid, gold_label=it.get("gold_label"),
                             gold_node_id=it.get("gold_node_id"),
                             relevance=int(it.get("relevance", 1)),
                             rationale=it.get("rationale", ""),
                             page_pdf=it.get("page_pdf")) for it in items]
    return out


def _result_body(res: dict) -> dict:
    """The /jobs/{id}/result envelope wraps the typed result in a few possible
    shapes across platform versions — unwrap to the job result dict."""
    for key in ("result", "job_result", "data"):
        if isinstance(res.get(key), dict):
            return res[key]
    return res


# --------------------------------------------------------------------------- #
# The retrieve fn: one deployed book_retrieve job per query
# --------------------------------------------------------------------------- #
def make_retrieve_fn(book_id: str):
    def retrieve(query_text: str, k: int) -> list[dict]:
        job_id = _submit({
            "job_type": "book_retrieve",
            "book_id": book_id,
            "query": query_text,
            "k": k,
        })
        res = _result_body(_wait(job_id, timeout_s=300))
        hits = res.get("hits") or []
        cands = []
        for h in hits:
            cands.append({
                "node_id": h.get("node_id"),
                "chunk_id": h.get("chunk_id"),
                "score": h.get("score"),
                "label": h.get("label"),
                "page_pdf_start": h.get("page"),
                "heading_path": h.get("heading_path") or [],
            })
        return cands
    return retrieve


# --------------------------------------------------------------------------- #
# report printing
# --------------------------------------------------------------------------- #
def _fmt_macro(label: str, macro: dict) -> str:
    keys = ["recall@1", "recall@3", "recall@5", "recall@10", "mrr",
            "ndcg@5", "ndcg@10", "exact_label_hit_rate", "traceability"]
    lines = [f"  [{label}]"]
    for k in keys:
        v = macro.get(k)
        if v is not None:
            lines.append(f"    {k:<22}{v:>8.3f}")
    return "\n".join(lines)


def main() -> None:
    print(f"== math_book deploy-smoke + eval ==")
    print(f"  API_URL={API_URL}  book_id={BOOK_ID}  slice=pdf[{SLICE_START}..{SLICE_END}]  k={K}")

    if not os.environ.get("SKIP_INDEX"):
        if not TU_PDF.is_file():
            raise SystemExit(f"Tu PDF not found: {TU_PDF} (set TU_PDF=...)")
        print(f"  [1/4] uploading {TU_PDF.name} ({TU_PDF.stat().st_size} bytes) -> /media")
        ref = _upload_media(TU_PDF)
        print(f"        storage_ref = {ref}")

        print(f"  [2/4] submitting book_index (pages {SLICE_START}..{SLICE_END}) ...")
        idx_job = _submit({
            "job_type": "book_index",
            "pdf_ref": ref,
            "book_id": BOOK_ID,
            "page_range": {"start": SLICE_START, "end": SLICE_END},
        })
        idx_res = _result_body(_wait(idx_job, timeout_s=1200))
        print(f"        book_index done: node_count={idx_res.get('node_count')} "
              f"edge_count={idx_res.get('edge_count')} chunk_count={idx_res.get('chunk_count')}")
        if not idx_res.get("chunk_count"):
            print("  !! chunk_count=0 — embed/vector-store step produced nothing; "
                  "retrieval will be empty. Check worker EmbeddingsInterpreter + DB.")
    else:
        print("  [1-2/4] SKIP_INDEX=1 — reusing already-indexed book")

    print(f"  [3/4] running {len(load_queries())} book_retrieve queries (k={K}) ...")
    queries = load_queries()
    gold = load_gold()
    catmap = {qid: q["category"] for qid, q in queries.items()}
    retrieve = make_retrieve_fn(BOOK_ID)

    results_by_query: dict[str, list[RetrievedItem]] = {}
    latency_ms: dict[str, float] = {}
    raw: dict[str, list[dict]] = {}
    for i, (qid, q) in enumerate(queries.items(), 1):
        t0 = time.perf_counter()
        cands = retrieve(q["query_text"], K) or []
        latency_ms[qid] = (time.perf_counter() - t0) * 1000.0
        raw[qid] = cands
        results_by_query[qid] = [
            RetrievedItem(query_id=qid, rank=r + 1,
                          retrieved_node_id=c.get("node_id"),
                          retrieved_chunk_id=c.get("chunk_id"),
                          score=c.get("score"), label=c.get("label"),
                          page_pdf_start=c.get("page_pdf_start"),
                          heading_path=c.get("heading_path"))
            for r, c in enumerate(cands[:K])
        ]
        top = cands[0] if cands else {}
        print(f"    {i:>2}/{len(queries)} {qid} '{q['query_text'][:42]}' "
              f"-> {len(cands)} hits, top='{top.get('label')}' p{top.get('page_pdf_start')} "
              f"({latency_ms[qid]:.0f}ms)")

    print(f"  [4/4] scoring vs gold ...")
    page_report = score_run("deployed_book_retrieve__page", results_by_query,
                            gold, catmap, match_mode="page")
    strict_report = score_run("deployed_book_retrieve__strict", results_by_query,
                              gold, catmap, match_mode="strict")

    # "naive VIEW": the SAME deployed hits, but with label/node_id/heading_path
    # STRIPPED, scored page-mode. This is NOT an independent retriever (the
    # spike's naive_baseline was a separate label-less lexical retriever in the
    # lab DB, which isn't packaged as a job). It isolates the ONE thing structure
    # buys that no page-only retriever can: on the identical page-recall, the
    # label-hit and source-traceability rates COLLAPSE TO 0 — the spike's
    # naive=0-on-label/trace headline, reproduced on the deployed hits.
    naive_by_query: dict[str, list[RetrievedItem]] = {}
    for qid, items in results_by_query.items():
        naive_by_query[qid] = [
            RetrievedItem(query_id=qid, rank=it.rank,
                          retrieved_chunk_id=it.retrieved_chunk_id,
                          score=it.score, page_pdf_start=it.page_pdf_start)
            for it in items
        ]
    naive_report = score_run("naive_view__page", naive_by_query, gold, catmap,
                             match_mode="page")

    print("\n================ RESULTS (deployed book_retrieve, C_full) ================")
    print(_fmt_macro("PAGE-AWARE (right place)", page_report.macro))
    print(_fmt_macro("STRICT (right unit)", strict_report.macro))
    print(_fmt_macro("naive VIEW (same hits; label/heading STRIPPED)", naive_report.macro))
    lat = sorted(latency_ms.values())
    if lat:
        p50 = lat[len(lat) // 2]
        p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
        print(f"\n  latency per book_retrieve job: p50={p50:.0f}ms p95={p95:.0f}ms "
              f"(includes submit+poll round-trip)")

    # machine-readable dump for RESULTS.md / re-inspection
    out = {
        "config": {"api_url": API_URL, "book_id": BOOK_ID,
                   "slice_pdf": [SLICE_START, SLICE_END], "k": K},
        "page_aware": page_report.macro,
        "strict": strict_report.macro,
        "naive_view": naive_report.macro,
        "by_category_page": page_report.by_category,
        "latency_ms": latency_ms,
        "raw_hits": raw,
    }
    (HERE / "last_run.json").write_text(json.dumps(out, indent=2))
    print(f"\n  wrote {HERE / 'last_run.json'}")


if __name__ == "__main__":
    main()

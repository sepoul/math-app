"""Track C — R1 sanity bake-off: structured-hybrid vs naive, on 5 ad-hoc probes.

Eyeball-level only. Real scoring against Track D's gold lands in R2. Each probe
reports the top-3 of: structured-hybrid (c_chunks), naive-vector (baseline),
naive-lexical (baseline). Latency per query is recorded.
"""
from __future__ import annotations

import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from retrieve import search  # noqa: E402

PROBES = [
    "definition of quotient topology",
    "theorem about the quotient construction",
    "Problem 7.11",
    "smooth versus analytic functions",
    "regular value",   # control: NOT in slice — expect weak/own-section drift
]


def short(h, n=70):
    head = (h.label or (h.kind or "")) if h.kind else "(window)"
    loc = f"p{h.page}" if h.page else "?"
    body = " ".join(h.text.split())[:n]
    return f"[{head} {loc}] {body}"


def run():
    lat = {"structured_hybrid": [], "naive_vector": [], "naive_lexical": []}
    for q in PROBES:
        print("\n" + "=" * 78)
        print("QUERY:", q)
        sh, t1 = search(q, "hybrid", "c_chunks", k=3)
        nv, t2 = search(q, "vector", "c_baseline_chunks", k=3)
        nl, t3 = search(q, "lexical", "c_baseline_chunks", k=3)
        lat["structured_hybrid"].append(t1)
        lat["naive_vector"].append(t2)
        lat["naive_lexical"].append(t3)
        print(f"\n-- STRUCTURED-HYBRID (c_chunks)  {t1*1000:.0f} ms --")
        for i, h in enumerate(sh, 1):
            print(f"  {i}. score={h.score:.3f} {h.signals}  {short(h)}")
        print(f"\n-- NAIVE VECTOR (baseline)  {t2*1000:.0f} ms --")
        for i, h in enumerate(nv, 1):
            print(f"  {i}. sim={h.score:.3f}  {short(h)}")
        print(f"\n-- NAIVE LEXICAL (baseline)  {t3*1000:.0f} ms --")
        for i, h in enumerate(nl, 1):
            print(f"  {i}. r={h.score:.4f}  {short(h)}")

    print("\n" + "#" * 78)
    print("LATENCY (mean ms over %d probes, incl. 1 embed call/query):" % len(PROBES))
    for k, v in lat.items():
        print(f"  {k:20} mean={1000*sum(v)/len(v):.0f}ms  min={1000*min(v):.0f}ms  max={1000*max(v):.0f}ms")


if __name__ == "__main__":
    run()

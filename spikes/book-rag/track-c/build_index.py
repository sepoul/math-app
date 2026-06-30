"""Track C — build the two index tables: c_chunks (structured) + c_baseline_chunks (naive).

Round 1: stand up the retrieval substrate. Sources, in preference order:
  1. Track A's `a_nodes` (preferred) — when populated.
  2. seed fixture `_shared/seed/seed_nodes.json` — when present.
  3. direct fitz extract of the slice (extract_slice.py) — the R1 fallback.
We print which source we used.

For structured units we build the §12 *contextualized embed_input*:

    Book: An Introduction to Manifolds
    Chapter 1: Euclidean Spaces
    Section §7: Quotients
    Type: Theorem
    Label: Theorem 7.7

    <text>

`tsv` = to_tsvector('english', heading_path || label || text) so labels and the
heading path are lexically searchable too. `embedding` = text-embedding-3-small.

Usage (CWD = spikes/book-rag):
    .venv/bin/python track-c/build_index.py [--source a_nodes|seed|fitz] [--no-embed]
"""
from __future__ import annotations

import sys
import json
import time
import pathlib
import argparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _shared.db import connect, SCHEMA, SLICE  # noqa: E402
from extract_slice import extract_slice  # noqa: E402
from baseline import build_baseline_chunks  # noqa: E402

BOOK_TITLE = "An Introduction to Manifolds"


# ---- source resolution ----------------------------------------------------
def _from_a_nodes() -> list[dict] | None:
    """Read structured nodes from Track A if present and non-empty."""
    with connect() as conn, conn.cursor() as cur:
        cur.execute(f"select count(*) from {SCHEMA}.a_nodes;")
        if cur.fetchone()[0] == 0:
            return None
        cur.execute(f"""
            select node_id, parent_id, kind, label, title, heading_path,
                   page_pdf_start, page_pdf_end, page_printed_start, page_printed_end,
                   text_raw, proves, confidence
            from {SCHEMA}.a_nodes
            where kind in ('section','subsection','definition','theorem','proposition',
                           'lemma','corollary','proof','example','remark','exercise')
        """)
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _from_seed() -> list[dict] | None:
    p = pathlib.Path(__file__).resolve().parents[1] / "_shared" / "seed" / "seed_nodes.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def resolve_source(pref: str) -> tuple[str, list[dict], list[dict]]:
    """Return (source_name, section_nodes, leaf_nodes)."""
    if pref in ("a_nodes", "auto"):
        a = _from_a_nodes()
        if a:
            secs = [n for n in a if n["kind"] in ("section", "subsection")]
            leaves = [n for n in a if n["kind"] not in ("section", "subsection", "chapter", "book")]
            return "a_nodes", secs, leaves
        if pref == "a_nodes":
            raise SystemExit("a_nodes is empty; pass --source fitz to fall back.")
    if pref in ("seed", "auto"):
        s = _from_seed()
        if s:
            secs = [n for n in s if n["kind"] in ("section", "subsection")]
            leaves = [n for n in s if n["kind"] not in ("section", "subsection", "chapter", "book")]
            return "seed", secs, leaves
        if pref == "seed":
            raise SystemExit("seed fixture not found; pass --source fitz.")
    # fallback: direct fitz extract
    secs, leaves = extract_slice()
    return "fitz_extract", secs, leaves


# ---- §12 contextualized embed_input --------------------------------------
def make_embed_input(node: dict, level: str) -> str:
    hp = node.get("heading_path") or []
    lines = [f"Book: {hp[0] if hp else BOOK_TITLE}"]
    if len(hp) >= 2:
        lines.append(hp[1])               # "Chapter 1: Euclidean Spaces"
    if len(hp) >= 3:
        lines.append(f"Section: {hp[2]}")  # "§7 Quotients"
    lines.append(f"Type: {node['kind'].capitalize()}")
    if node.get("label"):
        lines.append(f"Label: {node['label']}")
    if node.get("title"):
        lines.append(f"Title: {node['title']}")
    body = (node.get("text_raw") or "").strip()
    return "\n".join(lines) + "\n\n" + body


def _tsv_source(node: dict) -> str:
    hp = " ".join(node.get("heading_path") or [])
    return " ".join(filter(None, [hp, node.get("label") or "", node.get("title") or "",
                                   node.get("text_raw") or ""]))


# ---- write tables ---------------------------------------------------------
def build(pref: str, do_embed: bool) -> dict:
    source, secs, leaves = resolve_source(pref)
    rows: list[dict] = []
    for n in secs:
        rows.append({"level": "section", **n})
    for n in leaves:
        rows.append({"level": "leaf", **n})

    # structured embed inputs
    for r in rows:
        r["embed_input"] = make_embed_input(r, r["level"])

    base = build_baseline_chunks()

    stats = {"source": source, "slice": SLICE,
             "n_section": len(secs), "n_leaf": len(leaves),
             "n_struct": len(rows), "n_baseline": len(base)}

    # embeddings
    struct_vecs = base_vecs = None
    if do_embed:
        from embed import embed_texts, DIM
        sv, s_stat = embed_texts([r["embed_input"] for r in rows])
        bv, b_stat = embed_texts([c["embed_input"] for c in base])
        struct_vecs, base_vecs = sv, bv
        stats["embed_dim"] = DIM
        stats["embed_struct"] = s_stat
        stats["embed_baseline"] = b_stat

    with connect() as conn, conn.cursor() as cur:
        # idempotent: clear our two tables, then insert
        cur.execute(f"truncate {SCHEMA}.c_chunks;")
        cur.execute(f"truncate {SCHEMA}.c_baseline_chunks;")
        for i, r in enumerate(rows):
            chunk_id = f"c.struct.{r['node_id']}"
            emb = struct_vecs[i] if struct_vecs is not None else None
            cur.execute(
                f"""insert into {SCHEMA}.c_chunks
                    (chunk_id, level, node_id, kind, heading_path, label,
                     page_pdf_start, page_printed_start, text, embed_input, tsv, embedding, meta)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                            to_tsvector('english', %s), %s, %s)""",
                (chunk_id, r["level"], r["node_id"], r["kind"],
                 r.get("heading_path") or [], r.get("label"),
                 r.get("page_pdf_start"), str(r.get("page_printed_start") or ""),
                 (r.get("text_raw") or ""), r["embed_input"], _tsv_source(r),
                 emb, json.dumps({"title": r.get("title"), "proves": r.get("proves"),
                                  "confidence": r.get("confidence")})),
            )
        for i, c in enumerate(base):
            emb = base_vecs[i] if base_vecs is not None else None
            cur.execute(
                f"""insert into {SCHEMA}.c_baseline_chunks
                    (chunk_id, page_pdf_start, text, tsv, embedding, meta)
                    values (%s,%s,%s, to_tsvector('english', %s), %s, %s)""",
                (c["chunk_id"], c.get("page_pdf_start"), c["text"], c["text"],
                 emb, json.dumps({})),
            )
        conn.commit()
        cur.execute(f"select count(*) from {SCHEMA}.c_chunks;")
        stats["c_chunks_rows"] = cur.fetchone()[0]
        cur.execute(f"select count(*) from {SCHEMA}.c_chunks where embedding is not null;")
        stats["c_chunks_embedded"] = cur.fetchone()[0]
        cur.execute(f"select count(*) from {SCHEMA}.c_baseline_chunks;")
        stats["c_baseline_rows"] = cur.fetchone()[0]
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="auto", choices=["auto", "a_nodes", "seed", "fitz"])
    ap.add_argument("--no-embed", action="store_true")
    args = ap.parse_args()
    pref = "fitz" if args.source == "fitz" else args.source
    if pref == "fitz":
        # force the fallback by skipping a_nodes/seed
        import builtins  # noqa
        # simplest: monkeypatch resolvers off
        globals()["_from_a_nodes"] = lambda: None
        globals()["_from_seed"] = lambda: None
        pref = "auto"
    t0 = time.time()
    st = build(pref, not args.no_embed)
    st["build_seconds"] = round(time.time() - t0, 2)
    print(json.dumps(st, indent=2, default=str))

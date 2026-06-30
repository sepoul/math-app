"""Track C — build the two index tables: c_chunks (structured) + c_baseline_chunks (naive).

Sources, in preference order (printed as `source`):
  1. Track A's `a_nodes` (PREFERRED, R2) — the canonical skeleton.
  2. seed fixture `_shared/seed/seed_nodes.json` — if present.
  3. direct fitz extract of the slice (extract_slice.py) — the R1 fallback.

R2 changes vs R1
----------------
- Adopt A's canonical node_ids + heading_path (`book.sub7.5.theorem117`, §7 under
  Chapter 2). Carry `node_id` on every chunk so the harness can match on id.
- **Gold-matching labels.** The eval matches on normalized `label`. A labels
  subsections "7.1" and proofs "Proof"; D's gold uses "subsection 7.1 The
  Quotient Topology" and "Proof of Theorem 7.7". We mint a `match_label` per
  chunk that follows D's convention (and fix the "C∞Versus"→"C∞ Versus" spacing).
- **Section/subsection summaries.** A's section/subsection nodes have empty
  text_raw; we synthesize a deterministic summary (heading path + the labels/
  titles of contained leaves). Fixes the R1 8192-token cap with no LLM call.

`tsv = to_tsvector('english', heading_path ‖ match_label ‖ title ‖ text)`.
`embedding = text-embedding-3-small` (1536-d), same for both tables.

Usage (CWD = spikes/book-rag):
    .venv/bin/python track-c/build_index.py [--source a_nodes|seed|fitz] [--no-embed]
"""
from __future__ import annotations

import re
import sys
import json
import time
import pathlib
import argparse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _shared.db import connect, SCHEMA, SLICE  # noqa: E402
from extract_slice import extract_slice, clean_text  # noqa: E402
from baseline import build_baseline_chunks  # noqa: E402
from labels import match_label_for  # noqa: E402

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
        nodes = [dict(zip(cols, r)) for r in cur.fetchall()]
    return nodes


def _from_seed() -> list[dict] | None:
    p = pathlib.Path(__file__).resolve().parents[1] / "_shared" / "seed" / "seed_nodes.json"
    if not p.is_file():
        return None
    return json.loads(p.read_text())


def resolve_source(pref: str) -> tuple[str, list[dict]]:
    """Return (source_name, all_nodes) — sections+subsections+leaves in one list."""
    if pref in ("a_nodes", "auto"):
        a = _from_a_nodes()
        if a:
            return "a_nodes", a
        if pref == "a_nodes":
            raise SystemExit("a_nodes is empty; pass --source fitz to fall back.")
    if pref in ("seed", "auto"):
        s = _from_seed()
        if s:
            return "seed", s
        if pref == "seed":
            raise SystemExit("seed fixture not found; pass --source fitz.")
    secs, leaves = extract_slice()
    return "fitz_extract", secs + leaves


# ---- §12 section/subsection deterministic summary -------------------------
SECTION_KINDS = {"section", "subsection"}
LEAF_KINDS = {"definition", "theorem", "proposition", "lemma", "corollary",
              "proof", "example", "remark", "exercise"}


def synthesize_container_text(node: dict, children: list[dict]) -> str:
    """A cheap, deterministic 'what's in this section' summary (spec §12): the
    heading path + an enumerated list of the contained units' labels/titles."""
    hp = node.get("heading_path") or []
    head = hp[-1] if hp else (node.get("title") or node.get("label") or node["node_id"])
    lines = [f"{head}.", "Contains:"]
    for ch in children:
        if ch["kind"] in ("section", "subsection"):
            continue
        bit = ch.get("label") or ch["kind"]
        if ch.get("title"):
            bit += f" ({ch['title']})"
        lines.append(f"- {bit}")
    return "\n".join(lines)


# ---- §12 contextualized embed_input --------------------------------------
def make_embed_input(node: dict, level: str, body: str) -> str:
    hp = node.get("heading_path") or []
    lines = [f"Book: {BOOK_TITLE}"]
    for h in hp:
        lines.append(h)
    lines.append(f"Type: {node['kind'].capitalize()}")
    if node.get("match_label"):
        lines.append(f"Label: {node['match_label']}")
    if node.get("title"):
        lines.append(f"Title: {node['title']}")
    return "\n".join(lines) + "\n\n" + (body or "").strip()


def _tsv_source(node: dict, body: str) -> str:
    hp = " ".join(node.get("heading_path") or [])
    return " ".join(filter(None, [hp, node.get("match_label") or "",
                                   node.get("title") or "", body or ""]))


# ---- build ----------------------------------------------------------------
def build(pref: str, do_embed: bool) -> dict:
    source, nodes = resolve_source(pref)

    by_id = {n["node_id"]: n for n in nodes}
    # mint gold-matching labels for every node (resolves Proof->proven label)
    for n in nodes:
        n["match_label"] = match_label_for(n, by_id)

    # group leaves under their container (parent_id) for section summaries
    children: dict[str, list[dict]] = {}
    for n in nodes:
        if n.get("parent_id"):
            children.setdefault(n["parent_id"], []).append(n)

    rows: list[dict] = []
    for n in nodes:
        level = "section" if n["kind"] in SECTION_KINDS else "leaf"
        body = clean_text(n.get("text_raw") or "")
        if level == "section" and not body.strip():
            body = synthesize_container_text(n, children.get(n["node_id"], []))
        n["_body"] = body
        n["_level"] = level
        n["embed_input"] = make_embed_input(n, level, body)
        rows.append(n)

    base = build_baseline_chunks()

    stats = {"source": source, "slice": SLICE,
             "n_section": sum(1 for r in rows if r["_level"] == "section"),
             "n_leaf": sum(1 for r in rows if r["_level"] == "leaf"),
             "n_struct": len(rows), "n_baseline": len(base)}

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
                (chunk_id, r["_level"], r["node_id"], r["kind"],
                 r.get("heading_path") or [], r["match_label"],
                 r.get("page_pdf_start"), str(r.get("page_printed_start") or ""),
                 r["_body"], r["embed_input"], _tsv_source(r, r["_body"]),
                 emb, json.dumps({"title": r.get("title"), "proves": r.get("proves"),
                                  "parent_id": r.get("parent_id"),
                                  "raw_label": r.get("label"),
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
    pref = args.source
    if pref == "fitz":
        globals()["_from_a_nodes"] = lambda: None
        globals()["_from_seed"] = lambda: None
        pref = "auto"
    t0 = time.time()
    st = build(pref, not args.no_embed)
    st["build_seconds"] = round(time.time() - t0, 2)
    print(json.dumps(st, indent=2, default=str))

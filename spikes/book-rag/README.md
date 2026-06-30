# book-rag spike — LAB

Feasibility/quality/speed lab for **structured RAG retrieval on Tu** (*An
Introduction to Manifolds*, 2nd ed.). Base issue: **#57**. Spec:
[`../../book_only_structured_math_retrieval.md`](../../book_only_structured_math_retrieval.md).
Book (in repo root): `Tu_AnIntroductionToManifolds copy.pdf`.

> **This is a LAB, not a feature.** Findings are the artifact (`FINDINGS.md` per
> track); code is the means. Keep the framework (pydantic schemas, typed
> functions) so learnings transfer, but scrappy is fine. No platform/wheel/SDK
> wiring. Work the one shared slice. Decision first, build later.

## The isolated zones (already provisioned)

Everything lives in **one new Supabase schema** + **one new private bucket**,
walled off from `public` / `test` / `app-data*` (which hold real data — do not
touch them).

- **Schema:** `book_rag_spike` — 16 tables, **one common schema, isolated
  per-track tables** (prefix = track letter). pgvector is enabled (in the
  `extensions` schema; the bare `vector` type resolves on our search_path).
- **Bucket:** `book-rag-spike` (private). Per-track folders are implicit key
  prefixes: `track-a/ track-b/ track-c/ track-d/ book/ _shared/` (created on
  first upload). Use it for equation crops / rendered page images / review
  artifacts.

| Track | Tables (your zone) | Bucket prefix |
|---|---|---|
| **A** extraction & skeleton | `a_parse_runs a_pages a_spans a_blocks a_toc_entries a_nodes a_equations` | `track-a/` |
| **B** graph, refs, validation | `b_node_edges b_references b_validation_issues` | `track-b/` |
| **C** indexing & retrieval | `c_chunks c_baseline_chunks` *(embedding dim left to you)* | `track-c/` |
| **D** eval harness | `d_queries d_gold d_results d_speed_cost` | `track-d/` |

**Rules of the road:** write only to your own prefix/tables; read anyone's.
`d_queries`/`d_gold` are owned by D and consumed by C (the one cross-track
seam — C builds the retriever, D owns the metrics). Don't `DROP`/`ALTER`
another track's tables.

## Connecting (no secrets in this repo)

Credentials come from `ai-platform/.env` (resolved by walking up parents —
works from the main checkout and from a `.claude/worktrees/issue-N` worktree;
override with `BOOK_RAG_ENV=/abs/path/.env`). The password is opaque (not
URL-decoded). Just use the helper:

```python
from _shared.db import connect, SCHEMA, BUCKET, SLICE, storage_base
with connect() as conn, conn.cursor() as cur:        # search_path already = book_rag_spike, extensions, public
    cur.execute("select count(*) from a_nodes;")
```

Smoke test: `python spikes/book-rag/_shared/db.py`.

## The venv

Shared venv built by `bootstrap.sh` at `spikes/book-rag/.venv` (gitignored).
A venv can't be copied into a worktree, so reference it by **absolute path**:

```
/Users/charbelelhachem/projects/public/math-app/spikes/book-rag/.venv/bin/python
```

…or run `bash bootstrap.sh` from inside your worktree for a local one. Deps in
`requirements.txt` (PyMuPDF/pdfplumber/pypdf, rapidfuzz, psycopg+pgvector,
openai+anthropic). Embeddings: OpenAI `text-embedding-3-*`; LLM rerank/judge:
Claude — both keys are in `ai-platform/.env`.

## The shared slice

All four tracks work the **same** slice so numbers compare:
**Tu — Ch 1 §1–§3 (early definitional) + Ch 7 §7 *Quotients* (theorem/proof
dense)**. Don't process all 430 pages.

## What we already know about Tu (the §1 inspection)

430-page native PDF, selectable text; **269-entry embedded outline**
(Chapter→§Section→Subsection — a free anchor); heading typography separable
(`§7 Quotients` = Times-Bold 12pt over Times-Roman 10pt body); **math is the
hard part** (display/inline math is glyph-soup in CM/Symbol/xypic fonts; no
images — text-as-glyphs); **Tu labels sections `§N` and subsections `N.M`** so
the spec's generic `^(\d+)\.(\d+)` section regex MIS-fires here; printed-page
offset is ~21 and not constant.

## Layout

```
spikes/book-rag/
  README.md            ← you are here
  SYNTHESIS.md         ← control plane fills in: go/no-go + recommendation
  requirements.txt  bootstrap.sh
  _shared/   db.py  schema.py   (the node/edge contract — Track A owns)
  seed/      hand-built fixture (~1 section) so B/C/D start before A lands
  queries/   Track D's shared query set + gold (files mirror d_queries/d_gold)
  track-a/ track-b/ track-c/ track-d/   each: FINDINGS.md + scratch code
```

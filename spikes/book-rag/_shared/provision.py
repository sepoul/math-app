"""Provision (idempotent) the isolated lab zones on the shared Supabase:
the `book_rag_spike` schema + per-track tables + pgvector, and the private
`book-rag-spike` bucket.

Additive ONLY — CREATE … IF NOT EXISTS / INSERT-if-absent. Never touches
`public` / `test` / `app-data*`. Safe to re-run. Run with the lab venv:

    spikes/book-rag/.venv/bin/python spikes/book-rag/_shared/provision.py
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _shared.db import connect, SCHEMA, BUCKET  # noqa: E402

DDL = f"""
create schema if not exists {SCHEMA};

-- Track A — extraction & skeleton (owns the node/edge contract)
create table if not exists {SCHEMA}.a_parse_runs (
  run_id text primary key, book text default 'tu_manifolds', slice text,
  tool text, created_at timestamptz default now(), notes jsonb default '{{}}'::jsonb);
create table if not exists {SCHEMA}.a_pages (
  id bigserial primary key, run_id text, pdf_page int not null, printed_page text,
  has_header boolean, has_footer boolean, meta jsonb default '{{}}'::jsonb);
create table if not exists {SCHEMA}.a_spans (
  id bigserial primary key, run_id text, pdf_page int not null, bbox double precision[],
  text text, font text, font_size double precision, bold boolean, italic boolean,
  reading_order int, source text default 'native_pdf', confidence double precision,
  meta jsonb default '{{}}'::jsonb);
create table if not exists {SCHEMA}.a_blocks (
  block_id text primary key, run_id text, pdf_page int not null, bbox double precision[],
  kind text default 'unknown', text_raw text, span_ids text[], reading_order int,
  confidence double precision, meta jsonb default '{{}}'::jsonb);
create table if not exists {SCHEMA}.a_toc_entries (
  id bigserial primary key, run_id text, level int, raw_label text, chapter_number int,
  section_number text, title text, pdf_page int, printed_page text);
create table if not exists {SCHEMA}.a_nodes (
  node_id text primary key, run_id text, parent_id text, kind text not null,
  label text, title text, heading_path text[], page_pdf_start int, page_pdf_end int,
  page_printed_start text, page_printed_end text, text_raw text, text_normalized text,
  proves text, math_region_ids text[], confidence double precision,
  evidence jsonb default '[]'::jsonb, created_at timestamptz default now());
create table if not exists {SCHEMA}.a_equations (
  eq_id text primary key, run_id text, pdf_page int, bbox double precision[],
  raw_text text, latex text, latex_confidence double precision,
  image_crop_key text, parent_node_id text, block_id text);
-- ADDED R2 (Track A): regrouped, ordered display-equation regions (raw
-- fragments in a_equations are kept untouched); + aliases column on a_nodes.
create table if not exists {SCHEMA}.a_eq_regions (
  region_id text primary key, run_id text, pdf_page int, bbox double precision[],
  member_eq_ids text[], ordered_text text, latex text, latex_confidence double precision,
  image_crop_key text, parent_node_id text, n_fragments int);
alter table {SCHEMA}.a_nodes add column if not exists aliases text[];

-- Track B — graph, references, validation
create table if not exists {SCHEMA}.b_node_edges (
  id bigserial primary key, from_node_id text not null, to_node_id text not null,
  edge_type text not null, confidence double precision, evidence jsonb default '[]'::jsonb);
create table if not exists {SCHEMA}.b_references (
  id bigserial primary key, src_node_id text, raw_mention text, resolved_label text,
  resolved_node_id text, method text, confidence double precision, correct boolean);
create table if not exists {SCHEMA}.b_validation_issues (
  id bigserial primary key, node_id text, invariant text, severity text, detail text,
  created_at timestamptz default now());

-- Track C — indexing & hybrid retrieval (embedding dim left to C; bare vector)
create table if not exists {SCHEMA}.c_chunks (
  chunk_id text primary key, level text, node_id text, kind text, heading_path text[],
  label text, page_pdf_start int, page_printed_start text, text text, embed_input text,
  tsv tsvector, embedding vector, meta jsonb default '{{}}'::jsonb);
create table if not exists {SCHEMA}.c_baseline_chunks (
  chunk_id text primary key, page_pdf_start int, text text, tsv tsvector,
  embedding vector, meta jsonb default '{{}}'::jsonb);

-- Track D — eval harness
create table if not exists {SCHEMA}.d_queries (
  query_id text primary key, category text, query_text text not null, intent text,
  notes jsonb default '{{}}'::jsonb);
create table if not exists {SCHEMA}.d_gold (
  id bigserial primary key, query_id text not null, gold_node_id text, gold_label text,
  relevance int default 1, rationale text);
create table if not exists {SCHEMA}.d_results (
  id bigserial primary key, run_label text not null, query_id text not null, rank int,
  retrieved_node_id text, retrieved_chunk_id text, score double precision,
  signals jsonb default '{{}}'::jsonb, created_at timestamptz default now());
create table if not exists {SCHEMA}.d_speed_cost (
  id bigserial primary key, stage text, run_label text, metric text,
  value double precision, detail jsonb default '{{}}'::jsonb, created_at timestamptz default now());

-- indexes
create index if not exists c_chunks_tsv_gin on {SCHEMA}.c_chunks using gin(tsv);
create index if not exists c_baseline_tsv_gin on {SCHEMA}.c_baseline_chunks using gin(tsv);
create index if not exists a_nodes_kind on {SCHEMA}.a_nodes(kind);
create index if not exists a_nodes_label on {SCHEMA}.a_nodes(label);
create index if not exists b_edges_from on {SCHEMA}.b_node_edges(from_node_id);
create index if not exists b_edges_to on {SCHEMA}.b_node_edges(to_node_id);
create index if not exists d_results_lbl on {SCHEMA}.d_results(run_label, query_id);
"""


def main() -> None:
    with connect(autocommit=True) as conn, conn.cursor() as cur:
        # pgvector (usually pre-installed on Supabase, in the extensions schema)
        cur.execute("select 1 from pg_extension where extname='vector';")
        if not cur.fetchone():
            try:
                cur.execute("create extension if not exists vector with schema extensions;")
            except Exception:
                cur.execute("create extension if not exists vector;")
        cur.execute(DDL)
        # private bucket (storage.buckets row == what the storage API creates)
        cur.execute("select 1 from storage.buckets where id=%s;", (BUCKET,))
        if not cur.fetchone():
            cur.execute("insert into storage.buckets (id, name, public) values (%s,%s,false);",
                        (BUCKET, BUCKET))
        cur.execute("select count(*) from information_schema.tables where table_schema=%s;", (SCHEMA,))
        ntab = cur.fetchone()[0]
        cur.execute("select public from storage.buckets where id=%s;", (BUCKET,))
        print(f"provisioned: schema '{SCHEMA}' ({ntab} tables), bucket '{BUCKET}' (public={cur.fetchone()[0]})")


if __name__ == "__main__":
    main()

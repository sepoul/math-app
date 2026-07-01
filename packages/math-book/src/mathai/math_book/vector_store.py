"""math_book domain vector store — pgvector helper over `math_book_chunks`.

The domain OWNS its vector store in the tenant storage plane — the platform does
NOT provide a `VectorRepository` (that would violate the §13 boundary; the
math-notes PR-3 doc explicitly forbids a platform-owned vector store). So this
domain stands up its own pgvector table (`math_book_chunks`, namespaced by
`book_id`) and exposes `upsert` / `knn_query` over it.

Connection (lean v1, #63): the worker process already carries the platform's
Supabase credentials in its environment (`SUPABASE_CONNECTION_STRING` +
`SUPABASE_SCHEMA` — the same vars `ai_platform` reads to open its own pool). We
connect to that SAME tenant Postgres, with the opaque-password hand-parse the
platform itself uses (`ai_platform...structured.supabase.parse_connection_string`
/ the spike's `_shared/db.py`: Supabase passwords contain `%`/`?` that libpq's
URI parser chokes on). For host dev where the var isn't exported, we fall back to
reading `../ai-platform/.env` the spike way. `pgvector.psycopg.register_vector`
is called after connect so vectors round-trip. The table + its ivfflat index are
created on first use (idempotent).

`psycopg` + `pgvector` are execution-only deps, imported lazily inside methods so
this module imports without them present (matches how math_notes defers media
deps). Deferred to #62: the deploy-smoke that runs this end-to-end against the
live tenant DB.
"""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass
from typing import Any, Optional, Sequence

# The domain-owned table. Namespaced by `book_id` so many books coexist; one
# embedding row per (book_id, chunk_id). Lives in the platform's schema
# (SUPABASE_SCHEMA, default `public`) alongside the platform's own tables — a
# domain-owned table in the tenant DB, not a platform primitive.
CHUNK_TABLE = "math_book_chunks"


@dataclass
class ChunkRecord:
    """One row to upsert into `math_book_chunks`.

    `embedding` is the dense vector; `node_id` ties the chunk to its structural
    skeleton node for source-traceable retrieval; `source` is the human-readable
    citation (heading path / label).
    """

    chunk_id: str
    text: str
    embedding: Sequence[float]
    node_id: Optional[str] = None
    source: Optional[str] = None
    kind: Optional[str] = None
    token_count: Optional[int] = None
    embedding_model: Optional[str] = None


@dataclass
class KnnHit:
    """One retrieved chunk row — from `knn_query` (vector) or `lexical_query`
    (FTS). `score` is the leg's raw score (cosine similarity or ts_rank)."""

    chunk_id: str
    text: str
    node_id: Optional[str]
    source: Optional[str]
    score: float
    kind: Optional[str] = None


def _vec_literal(vec: Sequence[float]) -> str:
    """Format a float sequence as a pgvector text literal (`[0.1,0.2,…]`), bound
    with an explicit `::vector` cast in the SQL. A plain Python `list` otherwise
    adapts to `double precision[]`, which has no `<=>` operator — this sidesteps
    the numpy/`register_vector` dependence entirely (works for lists)."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


def _parse_connection_string(url: str) -> dict[str, Any]:
    """Hand-parse a libpq URL, treating the password as OPAQUE (no URL-decode) —
    identical to `ai_platform` and the spike `_shared/db.py`."""
    rest = url.split("://", 1)[1]
    userinfo, _, hostpart = rest.rpartition("@")
    user, _, password = userinfo.partition(":")
    hostport, _, dbname = hostpart.partition("/")
    dbname = dbname.split("?", 1)[0]
    host, _, port = hostport.partition(":")
    return {
        "host": host,
        "port": int(port) if port else 5432,
        "user": user,
        "password": password,
        "dbname": dbname or "postgres",
    }


def _find_platform_env() -> Optional[pathlib.Path]:
    """Host-dev fallback: locate `ai-platform/.env` by walking up parents (works
    from the main checkout and a `.claude/worktrees/…` worktree). The spike's
    `find_platform_env` pattern, sans the hard error — returns None if absent."""
    override = os.environ.get("BOOK_RAG_ENV")
    if override and pathlib.Path(override).is_file():
        return pathlib.Path(override)
    here = pathlib.Path(__file__).resolve()
    for anc in here.parents:
        cand = anc / "ai-platform" / ".env"
        if cand.is_file():
            return cand
        # also try a sibling checkout `../ai-platform/.env`
        cand2 = anc.parent / "ai-platform" / ".env" if anc.parent else None
        if cand2 and cand2.is_file():
            return cand2
    return None


def _env_from_file(path: pathlib.Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.split("   ")[0].strip()  # drop wide-gap inline comments
    return env


def _resolve_conn_config() -> tuple[str, str]:
    """Return `(connection_string, schema)` for the tenant DB.

    Prefers the process environment (the worker exports the platform's
    `SUPABASE_CONNECTION_STRING` / `SUPABASE_SCHEMA`); falls back to
    `ai-platform/.env` for host dev. Raises if neither carries a connection
    string."""
    dsn = os.environ.get("SUPABASE_CONNECTION_STRING")
    schema = os.environ.get("SUPABASE_SCHEMA")
    if not dsn:
        env_file = _find_platform_env()
        if env_file is not None:
            fenv = _env_from_file(env_file)
            dsn = dsn or fenv.get("SUPABASE_CONNECTION_STRING")
            schema = schema or fenv.get("SUPABASE_SCHEMA")
    if not dsn:
        raise RuntimeError(
            "math_book vector store needs SUPABASE_CONNECTION_STRING (set in the "
            "worker env, or ai-platform/.env for host dev)."
        )
    return dsn, (schema or "public")


class VectorStore:
    """Domain-owned pgvector store over `math_book_chunks` in the tenant DB.

    Constructed per worker (like math-notes' interpreters). Holds a lazily-opened
    psycopg connection; `upsert`/`knn_query` are the only surface the job nodes
    use. Everything is namespaced by `book_id` so a re-index of one book never
    touches another's rows. Lean v1: a single connection (no pool), created on
    first use; the deploy-smoke (#62) exercises it live.
    """

    def __init__(self, *, dsn: Optional[str] = None, schema: Optional[str] = None) -> None:
        self._dsn = dsn
        self._schema = schema
        self._conn: Any = None
        self._ready = False

    # -- connection ---------------------------------------------------------
    def _connect(self) -> Any:
        if self._conn is not None:
            return self._conn
        import psycopg  # execution-only dep

        dsn, schema = (self._dsn, self._schema)
        if not dsn or not schema:
            rdsn, rschema = _resolve_conn_config()
            dsn = dsn or rdsn
            schema = schema or rschema
        self._schema = schema
        params = _parse_connection_string(dsn)
        conn = psycopg.connect(
            **params, connect_timeout=15, autocommit=True,
            keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
        )
        with conn.cursor() as cur:
            cur.execute(f"set search_path to {schema}, extensions, public;")
        try:  # numpy/list <-> vector round-tripping
            from pgvector.psycopg import register_vector
            register_vector(conn)
        except Exception:
            pass
        self._conn = conn
        return conn

    def _ensure_table(self, dim: int) -> None:
        """Create `math_book_chunks` (+ its ANN index) if missing. Idempotent.

        The embedding column is `vector(<dim>)` (dim from the first upsert —
        1536 for text-embedding-3-small). Cosine ops (`<=>`) match the spike."""
        if self._ready:
            return
        conn = self._connect()
        schema = self._schema
        with conn.cursor() as cur:
            try:
                cur.execute("create extension if not exists vector with schema extensions;")
            except Exception:
                pass  # usually pre-installed on Supabase
            cur.execute(f"""
                create table if not exists {schema}.{CHUNK_TABLE} (
                    book_id text not null,
                    chunk_id text not null,
                    node_id text,
                    kind text,
                    source text,
                    text text,
                    embedding vector({dim}),
                    embedding_model text,
                    token_count int,
                    tsv tsvector,
                    updated_at timestamptz default now(),
                    primary key (book_id, chunk_id)
                );
            """)
            cur.execute(
                f"create index if not exists {CHUNK_TABLE}_book_idx "
                f"on {schema}.{CHUNK_TABLE}(book_id);")
            cur.execute(
                f"create index if not exists {CHUNK_TABLE}_tsv_gin "
                f"on {schema}.{CHUNK_TABLE} using gin(tsv);")
        self._ready = True

    # -- write --------------------------------------------------------------
    def upsert(self, book_id: str, chunk: ChunkRecord) -> None:
        """Upsert one chunk (text + embedding + trace fields) for `book_id`.

        `INSERT ... ON CONFLICT (book_id, chunk_id) DO UPDATE`, writing the
        vector into the pgvector column and a `tsvector` over source+text for the
        lexical leg #64 will add. Shape ported from
        `spike/hybrid-retrieval:track-c/build_index.py`."""
        vec = list(chunk.embedding)
        self._ensure_table(len(vec))
        conn = self._connect()
        schema = self._schema
        tsv_source = " ".join(filter(None, [chunk.source or "", chunk.text or ""]))
        with conn.cursor() as cur:
            cur.execute(
                f"""insert into {schema}.{CHUNK_TABLE}
                    (book_id, chunk_id, node_id, kind, source, text, embedding,
                     embedding_model, token_count, tsv, updated_at)
                    values (%s,%s,%s,%s,%s,%s,%s::vector,%s,%s,
                            to_tsvector('english', %s), now())
                    on conflict (book_id, chunk_id) do update set
                        node_id=excluded.node_id, kind=excluded.kind,
                        source=excluded.source, text=excluded.text,
                        embedding=excluded.embedding,
                        embedding_model=excluded.embedding_model,
                        token_count=excluded.token_count, tsv=excluded.tsv,
                        updated_at=now();""",
                (book_id, chunk.chunk_id, chunk.node_id, chunk.kind, chunk.source,
                 chunk.text, _vec_literal(vec), chunk.embedding_model,
                 chunk.token_count, tsv_source),
            )

    # -- read (#64 retrieval) ----------------------------------------------
    def knn_query(self, book_id: str, vec: Sequence[float], k: int) -> list[KnnHit]:
        """Return the `k` nearest chunks to `vec` within `book_id` (best first).

        Cosine distance via pgvector's `<=>`; `score = 1 - distance` so higher is
        better. The vector leg of the hybrid
        (`spike/hybrid-retrieval:track-c/retrieve_r2.py:Retriever.vector`)."""
        conn = self._connect()
        schema = self._schema
        query_vec = _vec_literal(vec)
        with conn.cursor() as cur:
            cur.execute(
                f"""select chunk_id, text, node_id, source, kind,
                           1 - (embedding <=> %s::vector) as score
                    from {schema}.{CHUNK_TABLE}
                    where book_id = %s and embedding is not null
                    order by embedding <=> %s::vector
                    limit %s;""",
                (query_vec, book_id, query_vec, k),
            )
            return [KnnHit(chunk_id=r[0], text=r[1], node_id=r[2], source=r[3],
                           kind=r[4], score=float(r[5])) for r in cur.fetchall()]

    def lexical_query(self, book_id: str, query: str, k: int) -> list[KnnHit]:
        """The lexical leg of the hybrid — full-text search over the `tsv` column
        (`ts_rank` on `plainto_tsquery`), scoped to `book_id`. Ported from
        `retrieve_r2.py:Retriever.lexical`. Falls back to a substring `ILIKE`
        scan when the FTS query matches nothing (short/symbolic queries that
        `plainto_tsquery` reduces to empty), so a lexical signal is always
        available."""
        conn = self._connect()
        schema = self._schema
        with conn.cursor() as cur:
            cur.execute(
                f"""select chunk_id, text, node_id, source, kind,
                           ts_rank(tsv, plainto_tsquery('english', %s)) as r
                    from {schema}.{CHUNK_TABLE}
                    where book_id = %s
                      and tsv @@ plainto_tsquery('english', %s)
                    order by r desc limit %s;""",
                (query, book_id, query, k),
            )
            rows = cur.fetchall()
            if not rows:  # ILIKE fallback for FTS-empty queries
                cur.execute(
                    f"""select chunk_id, text, node_id, source, kind
                        from {schema}.{CHUNK_TABLE}
                        where book_id = %s
                          and (text ilike %s or source ilike %s)
                        limit %s;""",
                    (book_id, f"%{query}%", f"%{query}%", k),
                )
                return [KnnHit(chunk_id=r[0], text=r[1], node_id=r[2], source=r[3],
                               kind=r[4], score=1.0) for r in cur.fetchall()]
            return [KnnHit(chunk_id=r[0], text=r[1], node_id=r[2], source=r[3],
                           kind=r[4], score=float(r[5])) for r in rows]

    def get_chunks_by_node(self, book_id: str, node_ids: Sequence[str]) -> list[KnnHit]:
        """Fetch chunks for the given node_ids (for graph-expansion neighbours —
        `retrieve_r2.py:Retriever.expand` reads chunk rows for the reached
        nodes). Returns them without a score (the caller assigns the graph
        score)."""
        if not node_ids:
            return []
        conn = self._connect()
        schema = self._schema
        with conn.cursor() as cur:
            cur.execute(
                f"""select chunk_id, text, node_id, source, kind
                    from {schema}.{CHUNK_TABLE}
                    where book_id = %s and node_id = any(%s);""",
                (book_id, list(node_ids)),
            )
            return [KnnHit(chunk_id=r[0], text=r[1], node_id=r[2], source=r[3],
                           kind=r[4], score=0.0) for r in cur.fetchall()]

    def delete_book(self, book_id: str) -> int:
        """Drop all chunks for `book_id` (a re-index supersedes the prior one).
        No-op (returns 0) when the table doesn't exist yet — the table is created
        with the correct embedding dim on the first `upsert`, not here."""
        conn = self._connect()
        schema = self._schema
        with conn.cursor() as cur:
            cur.execute("select to_regclass(%s);", (f"{schema}.{CHUNK_TABLE}",))
            if cur.fetchone()[0] is None:
                return 0
            cur.execute(f"delete from {schema}.{CHUNK_TABLE} where book_id=%s;", (book_id,))
            return cur.rowcount

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            finally:
                self._conn = None
                self._ready = False

"""math_book domain vector store — pgvector helper over `math_book_chunks` (STUB).

The domain OWNS its vector store in the tenant storage plane — the platform
does NOT provide a `VectorRepository` (that would violate the §13 boundary;
the math-notes PR-3 doc explicitly forbids a platform-owned vector store). So
this domain stands up its own pgvector table (`math_book_chunks`, namespaced by
`book_id`) and exposes `upsert` / `knn_query` over it.

Connection pattern is modeled on the spike's `_shared/db.py`
(`git show origin/spike/hybrid-retrieval:spikes/book-rag/_shared/db.py`):
libpq-hostile Supabase passwords are treated as OPAQUE (parse the connection
string by hand, no URL-decode), and `pgvector.psycopg.register_vector` is called
after connecting so numpy vectors round-trip. The ONE deliberate difference: the
spike connected to an isolated lab schema from `ai-platform/.env`; the domain
must connect to the **tenant DB** the worker already has credentials for.

SCAFFOLD (#60): the shapes + the connection pattern are fixed; the exact
connection-acquisition (which env var / worker-provided handle exposes the
tenant DSN) is left as a documented TODO for the index job (#63), and the method
bodies are stubs. Heavy deps (`psycopg`, `pgvector`) are imported lazily inside
methods so this module imports without them present.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

# The domain-owned table + its columns. Namespaced by `book_id` so many books
# coexist; one embedding row per chunk. (DDL creation is #63.)
CHUNK_TABLE = "math_book_chunks"


@dataclass
class ChunkRecord:
    """One row to upsert into `math_book_chunks`.

    `embedding` is the dense vector (a `list[float]` / numpy array registered
    via pgvector). `node_id` ties the chunk to its structural skeleton node for
    source-traceable retrieval; `source` is the human-readable citation.
    """

    chunk_id: str
    text: str
    embedding: Sequence[float]
    node_id: Optional[str] = None
    source: Optional[str] = None
    token_count: Optional[int] = None
    embedding_model: Optional[str] = None


@dataclass
class KnnHit:
    """One nearest-neighbour row from `knn_query` — chunk + its distance/score."""

    chunk_id: str
    text: str
    node_id: Optional[str]
    source: Optional[str]
    score: float


def _parse_connection_string(url: str) -> dict[str, Any]:
    """Hand-parse a libpq connection URL, treating the password as OPAQUE.

    Ported from the spike's `_shared/db.py`: Supabase passwords contain `%`/`?`
    that libpq's URI parser chokes on, so we split by hand and never URL-decode.
    """
    rest = url.split("://", 1)[1]
    userinfo, _, hostpart = rest.rpartition("@")
    user, _, password = userinfo.partition(":")  # opaque, no URL-decode
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


class VectorStore:
    """Domain-owned pgvector store over `math_book_chunks` in the tenant DB.

    Constructed per worker (like math-notes' interpreters). Holds a lazily-opened
    psycopg connection; `upsert`/`knn_query` are the only surface the job nodes
    use. Everything is namespaced by `book_id` so a re-index of one book never
    touches another's rows.
    """

    def __init__(self, *, dsn: Optional[str] = None) -> None:
        # `dsn` is the tenant Postgres connection string. See `_connect` for the
        # acquisition TODO (#63).
        self._dsn = dsn
        self._conn: Any = None

    def _connect(self) -> Any:
        """Open (once) a psycopg connection to the TENANT DB, pgvector registered.

        TODO(#63): resolve the tenant DSN. Unlike the spike — which read an
        isolated lab schema from `ai-platform/.env` via `find_platform_env()` —
        the domain must connect to the tenant database the worker already has
        credentials for. Decide the acquisition:
          * a `DATABASE_URL` / tenant-DSN env var the worker sets, OR
          * a connection/handle exposed on the worker's `PlatformClient`
            (passed into `VectorStore(...)` from `execution.build_*`).
        Then, mirroring `spikes/book-rag/_shared/db.py:connect`:
            params = _parse_connection_string(dsn)   # opaque password
            conn = psycopg.connect(**params, connect_timeout=15, ...keepalives...)
            # set search_path so the pgvector `extensions` schema resolves
            from pgvector.psycopg import register_vector; register_vector(conn)
        Ensure the `math_book_chunks` table + its ivfflat/hnsw index exist (DDL
        also #63). Cache the connection on self._conn.
        """
        raise NotImplementedError("VectorStore._connect is wired in #63")

    def upsert(self, book_id: str, chunk: ChunkRecord) -> None:
        """Upsert one chunk (text + embedding + trace fields) for `book_id`.

        TODO(#63): `INSERT ... ON CONFLICT (book_id, chunk_id) DO UPDATE` into
        `math_book_chunks`, writing `chunk.embedding` into the pgvector column.
        Port the shape from `spikes/book-rag/track-c/build_index.py`.
        """
        raise NotImplementedError("VectorStore.upsert is wired in #63")

    def knn_query(
        self, book_id: str, vec: Sequence[float], k: int
    ) -> list[KnnHit]:
        """Return the `k` nearest chunks to `vec` within `book_id` (best first).

        TODO(#63/#64): `SELECT ... ORDER BY embedding <=> %s LIMIT %s WHERE
        book_id = %s` (cosine distance via pgvector's `<=>`), mapping rows to
        `KnnHit`. Port from `spikes/book-rag/track-c/retrieve.py`. #64 layers the
        lexical + type/label + graph-expansion hybrid on top of this vector leg.
        """
        raise NotImplementedError("VectorStore.knn_query is wired in #63/#64")

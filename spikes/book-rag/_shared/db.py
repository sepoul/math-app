"""Shared lab connection helper for the book-rag spike.

No secrets live in this repo. Credentials are read from the platform's
`ai-platform/.env`, located by walking up parent directories (works from the
main checkout *and* from a `.claude/worktrees/issue-N` worktree) or via the
`BOOK_RAG_ENV` override. The Supabase password is treated as OPAQUE (no
URL-decoding) — Supabase passwords contain `%`/`?` that libpq's URI parser
chokes on; we parse the connection string by hand, same as the platform.

Everything in this lab is isolated to the `book_rag_spike` schema + the
`book-rag-spike` private bucket. Never touch `public` / `test` / `app-data*`.
"""
from __future__ import annotations

import os
import pathlib
from typing import Any

import psycopg

# ---- the lab's isolated zones --------------------------------------------
SCHEMA = "book_rag_spike"
BUCKET = "book-rag-spike"
# the shared representative slice every track works (so numbers are comparable)
SLICE = "Tu: Ch1 §1–§3 + Ch7 §7 (Quotients)"
PDF_NAME = "Tu_AnIntroductionToManifolds copy.pdf"

# per-track table prefixes (one common schema, isolated tables per track)
TRACK_TABLES = {
    "a": ["a_parse_runs", "a_pages", "a_spans", "a_blocks", "a_toc_entries",
          "a_nodes", "a_equations"],
    "b": ["b_node_edges", "b_references", "b_validation_issues"],
    "c": ["c_chunks", "c_baseline_chunks"],
    "d": ["d_queries", "d_gold", "d_results", "d_speed_cost"],
}


def find_platform_env() -> pathlib.Path:
    """Locate ai-platform/.env from main checkout or a worktree."""
    override = os.environ.get("BOOK_RAG_ENV")
    if override:
        p = pathlib.Path(override)
        if p.is_file():
            return p
        raise FileNotFoundError(f"BOOK_RAG_ENV={override} not found")
    here = pathlib.Path(__file__).resolve()
    for anc in here.parents:
        cand = anc / "ai-platform" / ".env"
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        "Could not locate ai-platform/.env; set BOOK_RAG_ENV to its path.")


def load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in find_platform_env().read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.split("   ")[0].strip()  # drop wide-gap inline comments
    return env


def parse_connection_string(url: str) -> dict[str, Any]:
    rest = url.split("://", 1)[1]
    userinfo, _, hostpart = rest.rpartition("@")
    user, _, password = userinfo.partition(":")          # opaque, no URL-decode
    hostport, _, dbname = hostpart.partition("/")
    dbname = dbname.split("?", 1)[0]
    host, _, port = hostport.partition(":")
    return {"host": host, "port": int(port) if port else 5432, "user": user,
            "password": password, "dbname": dbname or "postgres"}


def connect(*, autocommit: bool = False, search_path_first: str | None = SCHEMA):
    """Open a psycopg connection scoped to the lab schema, pgvector registered."""
    env = load_env()
    params = parse_connection_string(env["SUPABASE_CONNECTION_STRING"])
    conn = psycopg.connect(
        **params, connect_timeout=15, autocommit=autocommit,
        keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5,
    )
    sp = f"{search_path_first}, extensions, public" if search_path_first else "extensions, public"
    with conn.cursor() as cur:
        cur.execute(f"set search_path to {sp};")
    if not autocommit:
        conn.commit()
    try:  # numpy <-> vector round-tripping for Track C
        from pgvector.psycopg import register_vector
        register_vector(conn)
    except Exception:
        pass
    return conn


# ---- storage (REST, stdlib only) -----------------------------------------
# The copyrighted book is NOT committed (sepoul/math-app is PUBLIC). It lives in
# the private bucket; workers fetch it via ensure_book().
BOOK_KEY = "book/Tu_AnIntroductionToManifolds.pdf"


def storage_base() -> tuple[str, dict[str, str]]:
    env = load_env()
    base = env["SUPABASE_URL"].rstrip("/") + "/storage/v1"
    key = env["SUPABASE_SECRET_KEY"]
    return base, {"Authorization": f"Bearer {key}", "apikey": key}


def storage_upload(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    import urllib.request
    base, headers = storage_base()
    req = urllib.request.Request(
        f"{base}/object/{BUCKET}/{key}", data=data, method="POST",
        headers={**headers, "Content-Type": content_type, "x-upsert": "true"})
    urllib.request.urlopen(req, timeout=120).read()


def storage_download(key: str) -> bytes:
    import urllib.request
    base, headers = storage_base()
    req = urllib.request.Request(f"{base}/object/{BUCKET}/{key}", headers=headers)
    return urllib.request.urlopen(req, timeout=120).read()


def ensure_book(cache_dir: str | None = None) -> pathlib.Path:
    """Return a local path to the Tu PDF. Uses the repo-root copy if present
    (main checkout), else downloads it from the private bucket into a cache
    (worktree workers). Never relies on the PDF being committed."""
    for anc in pathlib.Path(__file__).resolve().parents:
        local = anc / "Tu_AnIntroductionToManifolds copy.pdf"
        if local.is_file():
            return local
    cache = pathlib.Path(cache_dir or (pathlib.Path(__file__).resolve().parents[1] / ".cache"))
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / "Tu_AnIntroductionToManifolds.pdf"
    if not dest.is_file():
        dest.write_bytes(storage_download(BOOK_KEY))
    return dest


if __name__ == "__main__":  # quick smoke: python _shared/db.py
    with connect() as c, c.cursor() as cur:
        cur.execute("select count(*) from information_schema.tables where table_schema=%s;", (SCHEMA,))
        print(f"connected — {SCHEMA} has {cur.fetchone()[0]} tables; slice = {SLICE}")

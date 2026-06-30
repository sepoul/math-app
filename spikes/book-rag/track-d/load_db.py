"""Track D — load the file-mirror query set + gold into the shared tables.

Reads queries/queries.json + queries/gold.json and upserts them into
book_rag_spike.d_queries / d_gold. Idempotent: truncates the two D-owned tables
(only those) and reloads. Run with the lab venv, CWD at spikes/book-rag:

    export BOOK_RAG_ENV=/Users/.../ai-platform/.env
    cd spikes/book-rag
    /abs/path/.venv/bin/python track-d/load_db.py
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from _shared.db import connect, SCHEMA  # noqa: E402

QDIR = pathlib.Path(__file__).resolve().parents[1] / "queries"


def main() -> None:
    queries = json.loads((QDIR / "queries.json").read_text())["queries"]
    gold = json.loads((QDIR / "gold.json").read_text())["gold"]

    with connect() as conn, conn.cursor() as cur:
        # D owns these two tables only — safe truncate-and-reload.
        cur.execute(f"truncate {SCHEMA}.d_gold;")
        cur.execute(f"delete from {SCHEMA}.d_queries;")
        for q in queries:
            cur.execute(
                f"""insert into {SCHEMA}.d_queries (query_id, category, query_text, intent, notes)
                    values (%s,%s,%s,%s,%s)""",
                (q["query_id"], q["category"], q["query_text"], q.get("intent"),
                 json.dumps(q.get("notes", {}))))
        n_gold = 0
        # page_pdf / page_printed are real d_gold columns (promoted R3) for clean
        # page-aware scoring; additive, so older rows/loaders still work.
        cur.execute(f"alter table {SCHEMA}.d_gold add column if not exists page_pdf int;")
        cur.execute(f"alter table {SCHEMA}.d_gold add column if not exists page_printed text;")
        for qid, items in gold.items():
            for it in items:
                cur.execute(
                    f"""insert into {SCHEMA}.d_gold
                        (query_id, gold_node_id, gold_label, relevance, rationale,
                         page_pdf, page_printed)
                        values (%s,%s,%s,%s,%s,%s,%s)""",
                    (qid, it.get("gold_node_id"), it.get("gold_label"),
                     int(it.get("relevance", 1)), it.get("rationale"),
                     it.get("page_pdf"), it.get("page_printed")))
                n_gold += 1
        conn.commit()

        cur.execute(f"select count(*) from {SCHEMA}.d_queries;")
        nq = cur.fetchone()[0]
        cur.execute(f"select category, count(*) from {SCHEMA}.d_queries group by category order by category;")
        by_cat = cur.fetchall()
    print(f"loaded {nq} queries, {n_gold} gold rows")
    print("by category:", dict(by_cat))


if __name__ == "__main__":
    main()

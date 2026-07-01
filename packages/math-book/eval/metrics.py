"""Track D — the measuring stick.

Runnable, importable retrieval metrics for the book-rag spike. Track C imports
`score_run` (and the individual metric fns) to score a retriever against
Track D's gold without inventing its own metrics (the one seam to police —
issue #57). Pure-python, no DB dependency, so it's trivially unit-testable.

Vocabulary
----------
A *result* is one retrieved item at a rank for a query. We grade results by
matching them to gold via either a real `node_id` (once Track A populates
`a_nodes`) or a stable `label` (this round, before A lands). The gold itself is
graded relevance: 2 = primary/exact answer, 1 = relevant/supporting, 0 = not.

Metrics (spec §17 success criteria)
-----------------------------------
- recall@k                 — fraction of gold-relevant items retrieved in top-k.
- mrr                      — mean reciprocal rank of the first relevant hit.
- ndcg@k                   — graded-relevance ranking quality (rewards getting
                             the primary answer ABOVE merely-relevant ones).
- exact_label_hit_rate     — for label-anchored queries: did rank-1 carry the
                             exact PRIMARY gold label? (the "find Theorem 7.7"
                             capability).
- source_traceability_rate — does each returned result carry page + heading_path
                             back to source (spec §17: "return a traceable path
                             back to the source page")? A retriever can be
                             accurate yet untraceable; we score that explicitly.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional


# --------------------------------------------------------------------------- #
# Data shapes (mirror d_results / d_gold; intentionally light, no pydantic dep
# so C can `from metrics import ...` in the lab venv without extra installs).
# --------------------------------------------------------------------------- #
@dataclass
class GoldItem:
    """One gold-relevant node for a query (mirrors a d_gold row)."""
    query_id: str
    gold_label: Optional[str] = None     # stable label, e.g. "Theorem 7.7"
    gold_node_id: Optional[str] = None   # real a_nodes.node_id once A lands
    relevance: int = 1                   # 2=primary, 1=relevant, 0=not
    rationale: str = ""
    page_pdf: Optional[int] = None       # source page (for page-overlap matching)

    def key(self) -> str:
        """Match key: prefer node_id, fall back to label (round-1 reality)."""
        return self.gold_node_id or self.gold_label or ""


@dataclass
class RetrievedItem:
    """One retrieved result at a rank (mirrors a d_results row)."""
    query_id: str
    rank: int
    retrieved_node_id: Optional[str] = None
    retrieved_chunk_id: Optional[str] = None
    score: Optional[float] = None
    label: Optional[str] = None          # the retriever's label for the item
    page_pdf_start: Optional[int] = None
    heading_path: Optional[list[str]] = None
    signals: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        return self.retrieved_node_id or self.label or self.retrieved_chunk_id or ""

    def is_traceable(self) -> bool:
        """Spec §17: a result must trace back to a source page. We require a
        page AND a non-empty heading_path (hierarchy → 'where in the book')."""
        return self.page_pdf_start is not None and bool(self.heading_path)


# --------------------------------------------------------------------------- #
# Matching: a retrieved item "hits" a gold item if their keys match. We compare
# on whatever both sides carry — node_id when present on both, else label.
# Label comparison is normalized (case/space-insensitive) to survive cosmetic
# drift between A's labels and D's gold ("Theorem 7.7" vs "theorem 7.7").
# --------------------------------------------------------------------------- #
def _norm(s: Optional[str]) -> str:
    return " ".join((s or "").lower().split())


def _matches(item: RetrievedItem, gold: GoldItem, match_mode: str = "auto") -> bool:
    """match_mode:
       'auto'  — node_id when both sides have it, else label, else page (fallback).
       'strict'— node_id-or-label only (no page credit).
       'page'  — credit when item.page == gold.page_pdf (for label-less baselines;
                 gold leaf nodes are mostly single-page so page identity is a fair
                 'same source unit' proxy).
    """
    if match_mode != "page":
        if item.retrieved_node_id and gold.gold_node_id:
            if item.retrieved_node_id == gold.gold_node_id:
                return True
        if _norm(item.label) and _norm(item.label) == _norm(gold.gold_label):
            return True
        if match_mode == "strict":
            return False
    # page fallback ('auto' last resort, or explicit 'page')
    if item.page_pdf_start is not None and gold.page_pdf is not None:
        return item.page_pdf_start == gold.page_pdf
    return False


def _ranked(items: Iterable[RetrievedItem]) -> list[RetrievedItem]:
    return sorted(items, key=lambda r: r.rank)


# --------------------------------------------------------------------------- #
# Per-query metrics
# --------------------------------------------------------------------------- #
def recall_at_k(results: list[RetrievedItem], gold: list[GoldItem], k: int,
                match_mode: str = "auto") -> float:
    rel = [g for g in gold if g.relevance > 0]
    if not rel:
        return float("nan")
    topk = _ranked(results)[:k]
    found = sum(1 for g in rel if any(_matches(r, g, match_mode) for r in topk))
    return found / len(rel)


def reciprocal_rank(results: list[RetrievedItem], gold: list[GoldItem],
                    match_mode: str = "auto") -> float:
    rel = [g for g in gold if g.relevance > 0]
    for r in _ranked(results):
        if any(_matches(r, g, match_mode) for g in rel):
            return 1.0 / r.rank
    return 0.0


def ndcg_at_k(results: list[RetrievedItem], gold: list[GoldItem], k: int,
              match_mode: str = "auto") -> float:
    rel = [g for g in gold if g.relevance > 0]
    if not rel:
        return float("nan")

    # Each gold item may be credited AT MOST ONCE, to its earliest-ranked match
    # (otherwise page-overlap matching, where one chunk matches several gold and
    # several chunks match one gold, can push DCG above iDCG -> nDCG > 1).
    topk = _ranked(results)[:k]
    claimed: set[int] = set()
    dcg = 0.0
    for i, r in enumerate(topk):
        best_g, best_rel = None, 0
        for gi, g in enumerate(rel):
            if gi in claimed:
                continue
            if _matches(r, g, match_mode) and g.relevance > best_rel:
                best_g, best_rel = gi, g.relevance
        if best_g is not None:
            claimed.add(best_g)
            dcg += (2 ** best_rel - 1) / math.log2(i + 2)
    ideal = sorted((g.relevance for g in rel), reverse=True)[:k]
    idcg = sum((2 ** rel_g - 1) / math.log2(i + 2) for i, rel_g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def exact_label_hit(results: list[RetrievedItem], gold: list[GoldItem]) -> Optional[bool]:
    """For label-anchored queries: did rank-1 carry the exact PRIMARY gold label?
    Returns None when the query has no primary (relevance==2) gold label."""
    primary = [g for g in gold if g.relevance == 2 and g.gold_label]
    if not primary:
        return None
    ranked = _ranked(results)
    if not ranked:
        return False
    top = ranked[0]
    return any(_norm(top.label) == _norm(g.gold_label) for g in primary)


def source_traceability(results: list[RetrievedItem], k: int) -> float:
    topk = _ranked(results)[:k]
    if not topk:
        return float("nan")
    return sum(1 for r in topk if r.is_traceable()) / len(topk)


# --------------------------------------------------------------------------- #
# Aggregate scoring over a full run
# --------------------------------------------------------------------------- #
@dataclass
class QueryScore:
    query_id: str
    category: str
    recall_at: dict[int, float]
    mrr: float
    ndcg_at: dict[int, float]
    exact_label_hit: Optional[bool]
    traceability_at_k: float
    n_gold: int
    n_retrieved: int


@dataclass
class RunReport:
    run_label: str
    per_query: list[QueryScore]
    macro: dict[str, float]                      # mean over all queries
    by_category: dict[str, dict[str, float]]     # mean per category

    def summary_table(self) -> str:
        lines = [f"run: {self.run_label}", ""]
        lines.append(f"{'metric':<22}{'overall':>10}")
        for m, v in self.macro.items():
            lines.append(f"{m:<22}{v:>10.3f}")
        lines.append("")
        lines.append(f"{'category':<16}{'recall@5':>10}{'mrr':>8}{'ndcg@5':>8}{'n':>5}")
        for cat, d in sorted(self.by_category.items()):
            lines.append(f"{cat:<16}{d.get('recall@5', float('nan')):>10.3f}"
                         f"{d.get('mrr', float('nan')):>8.3f}"
                         f"{d.get('ndcg@5', float('nan')):>8.3f}{int(d.get('n', 0)):>5}")
        return "\n".join(lines)


def _mean(xs: list[float]) -> float:
    xs = [x for x in xs if x == x]  # drop NaN
    return sum(xs) / len(xs) if xs else float("nan")


def score_run(
    run_label: str,
    results_by_query: dict[str, list[RetrievedItem]],
    gold_by_query: dict[str, list[GoldItem]],
    category_by_query: dict[str, str],
    ks: tuple[int, ...] = (1, 3, 5, 10),
    match_mode: str = "auto",
) -> RunReport:
    """Score a full retrieval run. `results_by_query` maps query_id -> the
    retriever's ranked results; `gold_by_query` maps query_id -> gold items.
    Category drives the per-category breakdown and which metrics are headline
    (exact_label_hit is meaningful for `direct`/`structural`).
    match_mode='page' fairly scores label-less retrievers (naive baseline) by
    page-overlap against the gold page anchors."""
    per_query: list[QueryScore] = []
    for qid, gold in gold_by_query.items():
        res = results_by_query.get(qid, [])
        per_query.append(QueryScore(
            query_id=qid,
            category=category_by_query.get(qid, "?"),
            recall_at={k: recall_at_k(res, gold, k, match_mode) for k in ks},
            mrr=reciprocal_rank(res, gold, match_mode),
            ndcg_at={k: ndcg_at_k(res, gold, k, match_mode) for k in ks},
            exact_label_hit=exact_label_hit(res, gold),
            traceability_at_k=source_traceability(res, max(ks)),
            n_gold=len([g for g in gold if g.relevance > 0]),
            n_retrieved=len(res),
        ))

    macro: dict[str, float] = {}
    for k in ks:
        macro[f"recall@{k}"] = _mean([q.recall_at[k] for q in per_query])
        macro[f"ndcg@{k}"] = _mean([q.ndcg_at[k] for q in per_query])
    macro["mrr"] = _mean([q.mrr for q in per_query])
    macro["traceability"] = _mean([q.traceability_at_k for q in per_query])
    label_hits = [q.exact_label_hit for q in per_query if q.exact_label_hit is not None]
    macro["exact_label_hit_rate"] = (
        sum(1 for h in label_hits if h) / len(label_hits) if label_hits else float("nan"))

    by_cat: dict[str, dict[str, float]] = {}
    cats = {q.category for q in per_query}
    for cat in cats:
        grp = [q for q in per_query if q.category == cat]
        d: dict[str, float] = {"n": float(len(grp))}
        for k in ks:
            d[f"recall@{k}"] = _mean([q.recall_at[k] for q in grp])
            d[f"ndcg@{k}"] = _mean([q.ndcg_at[k] for q in grp])
        d["mrr"] = _mean([q.mrr for q in grp])
        d["traceability"] = _mean([q.traceability_at_k for q in grp])
        clh = [q.exact_label_hit for q in grp if q.exact_label_hit is not None]
        d["exact_label_hit_rate"] = (
            sum(1 for h in clh if h) / len(clh) if clh else float("nan"))
        by_cat[cat] = d

    return RunReport(run_label=run_label, per_query=per_query, macro=macro, by_category=by_cat)


__all__ = [
    "GoldItem", "RetrievedItem", "QueryScore", "RunReport",
    "recall_at_k", "reciprocal_rank", "ndcg_at_k", "exact_label_hit",
    "source_traceability", "score_run",
]

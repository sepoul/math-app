"""Track A — fidelity verification / scorecard helper.

Builds an *eyeballed ground-truth* count of formal environments directly from
the raw PDF typography (the same signals a human uses scanning the page: bold
label, italic label, exercise numbering), independently of the extractor's node
logic, then diffs against what landed in `a_nodes`. This is the honest
"recovered & located vs. truth" measure for FINDINGS.md.

Run:
    cd spikes/book-rag
    BOOK_RAG_ENV=.../.env /path/.venv/bin/python track-a/verify.py
"""
from __future__ import annotations

import re
import sys
import pathlib
import collections

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import fitz  # noqa: E402
from _shared.db import connect, ensure_book  # noqa: E402
import tu_config as cfg  # noqa: E402
from extract import SLICE_PAGES, header_line, footer_line, RUN_ID  # noqa: E402


def gt_labels(doc):
    """Independent ground truth: scan slice pages with a PRECISE y-sort (not the
    y/3 bucketing the extractor uses, so interleaving can't hide a label), emit
    one (page, kind, label_key) per formal-environment label line by font/size
    signature. Deduped by (kind, label_key) — a label that wraps across a page
    break is one item. Unnumbered example/remark keyed by page so distinct ones
    aren't collapsed. This is the 'truth' the scorecard scores against."""
    out = []
    seen = set()
    in_problems = False
    ctr = collections.Counter()
    for p in SLICE_PAGES:
        pg = doc[p - 1]
        h = pg.rect.height
        d = pg.get_text("dict")
        raw = [l for b in d["blocks"] if b.get("type") == 0 for l in b["lines"] if l["spans"]]
        raw.sort(key=lambda l: (round(l["bbox"][1], 1), l["bbox"][0]))
        for l in raw:
            sp = l["spans"]
            s0 = sp[0]
            y0 = l["bbox"][1]
            sz = round(s0["size"], 1)
            # drop ONLY the tight running-header band + small font (same two-part
            # test as the extractor) — a y<60 filter alone eats body labels @ y~47
            if (y0 < cfg.HEADER_BAND_Y and sz < 9.5) or y0 > h - cfg.HEADER_FOOTER_Y_BOT_MARGIN:
                continue
            txt = cfg.normalize_text("".join(s["text"] for s in sp)).strip()
            bold = bool(s0["flags"] & 16)
            ital = bool(s0["flags"] & 2)
            if cfg.SECTION_RE.match(txt) and (bold or sz >= cfg.SECTION_SIZE_MIN):
                in_problems = False
            if cfg.PROBLEMS_RE.match(txt) and bold and abs(sz - cfg.SUBSECTION_SIZE) < 0.6:
                in_problems = True
                continue

            def add(kind, num):
                # numbered items dedup by (kind,num) so a page-break wrap counts
                # once; UNNUMBERED items (proof / unnumbered example) are each
                # distinct -> key by a per-(kind,page) running index. EXERCISES
                # are keyed by (kind,num,page): Tu reuses a number for two
                # distinct exercises (e.g. Exercise 3.6 inline @p40 AND in the
                # Problems block @p52), and an exercise label never wraps pages.
                if kind == "exercise" and num:
                    key = (kind, num, p)
                elif num:
                    key = (kind, num)
                else:
                    ctr[(kind, p)] += 1
                    key = (kind, f"unnum@p{p}#{ctr[(kind, p)]}")
                if key not in seen:
                    seen.add(key)
                    out.append((p, kind, num))

            if bold and abs(sz - cfg.ENV_SIZE) < 0.7:
                for kind, rx in cfg.ENV_BOLD_10.items():
                    if re.match(rx, txt):
                        m = cfg.LABEL_RE.match(txt)
                        add(kind, m.group("num") if m else None)
            if ital and abs(sz - cfg.ENV_SIZE) < 0.7:
                for kind, rx in cfg.ENV_ITALIC_10.items():
                    if re.match(rx, txt):
                        m = cfg.LABEL_RE.match(txt)
                        # proofs have no number -> key by page so each is distinct
                        add(kind, (m.group("num") if (m and m.group("num")) else None)
                            if kind != "proof" else None)
            if bold and abs(sz - cfg.EXERCISE_SIZE) < 0.6:
                # inline "Exercise N.M ..." anywhere in the body
                mi = cfg.INLINE_EXERCISE_RE.match(txt)
                if mi:
                    add("exercise", mi.group("num"))
                # in-Problems bare "N.M. ..." (exclude figures)
                elif in_problems and not cfg.FIGURE_RE.match(txt):
                    m = cfg.EXERCISE_RE.match(txt)
                    if m:
                        add("exercise", m.group("num"))
    return out


def main():
    doc = fitz.open(ensure_book())
    gt = gt_labels(doc)
    gt_by_kind = collections.Counter(k for _, k, _ in gt)

    with connect() as c, c.cursor() as cur:
        # scope to LABELED formal environments only — exclude structure and the
        # R2 inline-definition nodes (those have no typographic label and are
        # measured separately in FINDINGS, not against the labeled-env GT).
        cur.execute(
            "select kind, page_pdf_start, label from a_nodes "
            "where run_id=%s and kind not in ('chapter','section','subsection') "
            "and node_id not like 'book.inlinedef.%%';",
            (RUN_ID,))
        rows = cur.fetchall()
    ex_by_kind = collections.Counter(k for k, _, _ in rows)

    # located = same (kind, page) appears in both gt and extracted
    gt_keys = collections.Counter((p, k) for p, k, _ in gt)
    ex_keys = collections.Counter((p, k) for k, p, _ in rows)
    located = collections.Counter()
    for key, n in gt_keys.items():
        located[key[1]] += min(n, ex_keys.get(key, 0))

    print("=== FIDELITY SCORECARD (slice) ===")
    print(f"{'kind':12} {'truth':>6} {'recov':>6} {'located':>8}")
    kinds = ["definition", "theorem", "proposition", "lemma", "corollary",
             "proof", "example", "remark", "exercise"]
    tt = tr = tl = 0
    for k in kinds:
        t, r, lo = gt_by_kind.get(k, 0), ex_by_kind.get(k, 0), located.get(k, 0)
        tt += t; tr += r; tl += lo
        print(f"{k:12} {t:6d} {r:6d} {lo:8d}")
    print(f"{'TOTAL':12} {tt:6d} {tr:6d} {tl:8d}   "
          f"recall(located/truth)={tl/tt:.1%} precision(located/recov)={tl/max(tr,1):.1%}")

    # proof linkage + confidence distribution
    with connect() as c, c.cursor() as cur:
        cur.execute("select count(*) from a_nodes where run_id=%s and kind='proof';", (RUN_ID,))
        np_ = cur.fetchone()[0]
        cur.execute("select count(*) from a_nodes where run_id=%s and kind='proof' and proves is not null;", (RUN_ID,))
        npl = cur.fetchone()[0]
        cur.execute("select width_bucket(confidence,0,1,10)*0.1 b, count(*) from a_nodes where run_id=%s group by b order by b;", (RUN_ID,))
        conf = cur.fetchall()
        cur.execute("select count(*), count(*) filter (where latex is not null) from a_equations where run_id=%s;", (RUN_ID,))
        neq, nlx = cur.fetchone()
    print(f"\nproofs linked (proves set): {npl}/{np_}")
    print(f"node confidence histogram (bucket->count): {conf}")
    print(f"equations: {neq} (latex set: {nlx}; raw-only otherwise)")


if __name__ == "__main__":
    main()

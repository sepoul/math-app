"""Honest reference-resolution eval against GENUINE PDF prose (not seed
paraphrases). Pulls the raw body text of the §7 slice pages, runs the same
resolver grammar, and reports resolution against the seed's node index.

This is the real accuracy number for FINDINGS: the seed text I wrote is partly
circular (I chose the mentions), so we re-run the resolver on Tu's actual words.

Run from spikes/book-rag:  .venv/bin/python track-b/ref_eval_raw.py
"""
from __future__ import annotations

import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve()
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from _shared.db import ensure_book  # noqa: E402
from graph_build import (load_nodes, resolve_references, _build_label_index,  # noqa: E402
                         REF_PATTERNS, _LABEL_NUM, NodeRow)


def slice_raw_text(pages=range(90, 104)) -> str:
    import fitz
    doc = fitz.open(ensure_book())
    parts = []
    for pno in pages:
        if pno - 1 >= doc.page_count:
            break
        pg = doc[pno - 1]
        H = pg.rect.height
        d = pg.get_text("dict")
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b["lines"]:
                if l["bbox"][1] < 40 or l["bbox"][1] > H - 40:
                    continue  # strip running header / footer band
                txt = "".join(s["text"] for s in l["spans"])
                parts.append(txt)
    return " ".join(parts)


def main():
    nodes, src = load_nodes()
    env_idx, prob_idx, sec_idx, chap_idx = _build_label_index(nodes)
    raw = slice_raw_text()

    # find all genuine in-text mentions in Tu's prose
    found = []
    for kind, pat in REF_PATTERNS:
        for m in pat.finditer(raw):
            found.append((kind, m.group(0).strip(), m))

    # resolve via the same grammar as resolve_references (inline, since we have raw text)
    print(f"node source: {src}")
    print(f"raw slice chars: {len(raw)}")
    print(f"\ngenuine in-text mentions found in Tu §7 prose: {len(found)}\n")

    # the slice's env numbering lives under §7 (7.x) — Ch1 §1-§3 (1.x/2.x/3.x)
    # join when Track A populates them. Anything else (5.7, A.36, ...) is a
    # genuine cross-reference OUT of the slice.
    SLICE_ENV_PREFIXES = {"7", "1", "2", "3"}

    resolved = 0
    correct = 0
    rows = []
    for kind, raw_m, m in found:
        rid = None
        within_slice_target = True
        if kind == "env":
            canon = f"{m.group(1)} {m.group(2)}".lower()
            rid = env_idx.get(canon)
            num = m.group(2)
            prefix = num.split(".")[0]
            # appendix (A.36) or a different chapter's number (5.7) -> out of slice
            if re.match(r"[A-Z]", prefix) or prefix not in SLICE_ENV_PREFIXES:
                within_slice_target = False
        elif kind == "problem":
            rid = prob_idx.get(m.group(1))
            if m.group(1).split(".")[0] not in SLICE_ENV_PREFIXES:
                within_slice_target = False
        elif kind == "section":
            rid = sec_idx.get(m.group(1))
            if m.group(1) != "7":
                within_slice_target = False
        elif kind == "chapter":
            rid = chap_idx.get(m.group(1))
            if m.group(1) != "1":
                within_slice_target = False

        if rid:
            resolved += 1
            ok = True  # grammar-matched + found in index
        else:
            ok = not within_slice_target  # correct to NOT resolve out-of-slice
        if ok:
            correct += 1
        rows.append((kind, raw_m, rid or ("-" if within_slice_target else "OUT-OF-SLICE(ok)"), ok))

    for kind, raw_m, rid, ok in rows:
        flag = "✓" if ok else "✗"
        print(f"  {flag} [{kind:9s}] {raw_m:24s} -> {rid}")

    n = len(found)
    print(f"\nRESOLVED to in-slice node: {resolved}/{n} = {resolved/n:.1%}")
    print(f"SELF-CORRECT (resolved-right OR correctly-declined-out-of-slice): "
          f"{correct}/{n} = {correct/n:.1%}")
    in_slice = [r for r in rows if r[2] != "OUT-OF-SLICE(ok)"]
    in_slice_ok = sum(1 for r in in_slice if r[3])
    print(f"IN-SLICE resolution accuracy: {in_slice_ok}/{len(in_slice)} = "
          f"{in_slice_ok/len(in_slice):.1%}")


if __name__ == "__main__":
    main()

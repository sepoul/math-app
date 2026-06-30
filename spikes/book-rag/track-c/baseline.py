"""Track C — the NAIVE BASELINE: fixed-window chunks, NO structure.

The control comparison for the headline question. We take the *same* slice text
(same pages as the structured corpus), concatenate it in reading order, and cut
it into fixed ~450-token windows with a small overlap — exactly the "bag of
token windows" the spec (§12) warns against. No labels, no heading path, no
type, no proof linkage. Embedded the same way as the structured units so the
only difference under test is *structure*, not the embedder.

Token counting is approximate (whitespace words ≈ tokens at the slice scale);
the point is comparable window sizes, not exact BPE counts.
"""
from __future__ import annotations

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _shared.db import ensure_book  # noqa: E402
from extract_slice import clean_text  # noqa: E402

import fitz  # PyMuPDF

# same pages as extract_slice.SLICE_SECTIONS (pdf_start, pdf_end inclusive)
SLICE_PAGE_RANGES = [(22, 28), (29, 36), (37, 52), (90, 104)]

WINDOW_WORDS = 450      # ~= 450-512 tokens for this prose+math mix
OVERLAP_WORDS = 60      # modest overlap so a unit isn't split mid-statement everywhere


def _slice_word_stream() -> list[tuple[int, str]]:
    """(pdf_page, word) in reading order over the slice. We attribute each word to
    the page it came from so a chunk can report a representative start page."""
    doc = fitz.open(ensure_book())
    stream: list[tuple[int, str]] = []
    for p0, p1 in SLICE_PAGE_RANGES:
        for pidx in range(p0 - 1, p1):
            txt = clean_text(doc[pidx].get_text("text"))
            for w in txt.split():
                stream.append((pidx + 1, w))
    return stream


def build_baseline_chunks() -> list[dict]:
    """Fixed-window chunks over the slice. Returns chunk dicts for c_baseline_chunks."""
    stream = _slice_word_stream()
    chunks: list[dict] = []
    i = 0
    n = len(stream)
    step = WINDOW_WORDS - OVERLAP_WORDS
    idx = 0
    while i < n:
        window = stream[i:i + WINDOW_WORDS]
        if not window:
            break
        start_page = window[0][0]
        text = " ".join(w for _, w in window)
        chunks.append(dict(
            chunk_id=f"c.base.{idx:03d}",
            page_pdf_start=start_page,
            text=text,
            embed_input=text,  # baseline: no contextualization, raw window only
        ))
        idx += 1
        i += step
    return chunks


if __name__ == "__main__":
    chunks = build_baseline_chunks()
    words = sum(len(c["text"].split()) for c in chunks)
    print(f"baseline chunks: {len(chunks)}  (~{WINDOW_WORDS} words/window, "
          f"{OVERLAP_WORDS} overlap)  total words≈{words}")
    print("sample:", chunks[0]["text"][:120])

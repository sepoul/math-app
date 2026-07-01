"""Chunk assembly — contextualized embed input, spike Track C.

Provenance: adapted from
  `origin/spike/hybrid-retrieval:spikes/book-rag/track-c/build_index.py`
  (`synthesize_container_text`, `make_embed_input`, the section/leaf split).

One chunk per leaf node (definition/theorem/proof/example/…) and one per
container node (section/subsection). The container body is a cheap deterministic
"what's in this section" summary (spec §12 — heading path + the labels/titles of
its contained leaves), so we never blow the embedding token cap on a raw
multi-page section concatenation and need no LLM call.

`embed_input` is the *contextualized* text handed to the embedder: the book
title + heading breadcrumb + type/label/title + the body. That context was the
spike's headline win (retrieval lands on the right node, not a bare text match).
The embedder is the platform `EmbeddingsInterpreter` (called by the workflow);
this module is pure string work, no I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from mathai.math_book._extraction import ParsedNode

SECTION_KINDS = {"section", "subsection"}
# text-embedding-3-small hard-caps at 8192 tokens; truncate section bodies at a
# conservative ~3.2 chars/token budget (spike embed.py MAX_CHARS). Leaves stay
# whole.
MAX_CHARS = 22000


@dataclass
class Chunk:
    """One unit to embed + persist. `embed_input` is the contextualized text
    fed to the embedder; `text` is the raw body kept for display/traceability."""

    chunk_id: str
    node_id: str
    kind: str
    level: str  # "section" | "leaf"
    heading_path: list[str]
    label: Optional[str]
    title: Optional[str]
    page: Optional[int]
    text: str
    embed_input: str
    token_count: Optional[int] = None
    embedding_model: Optional[str] = None
    vector: list[float] = field(default_factory=list)


def _synthesize_container_text(node: ParsedNode, children: list[ParsedNode]) -> str:
    """Deterministic 'what's in this section' summary (spike §12)."""
    hp = node.heading_path or []
    head = hp[-1] if hp else (node.title or node.label or node.node_id)
    lines = [f"{head}.", "Contains:"]
    for ch in children:
        if ch.kind in SECTION_KINDS:
            continue
        bit = ch.label or ch.kind
        if ch.title:
            bit += f" ({ch.title})"
        lines.append(f"- {bit}")
    return "\n".join(lines)


def _make_embed_input(book_title: str, node: ParsedNode, body: str) -> str:
    """Contextualized embed input (spike track-c/build_index.py:make_embed_input)."""
    lines = [f"Book: {book_title}"] if book_title else []
    lines += list(node.heading_path or [])
    lines.append(f"Type: {node.kind.capitalize()}")
    if node.label:
        lines.append(f"Label: {node.label}")
    if node.title:
        lines.append(f"Title: {node.title}")
    return "\n".join(lines) + "\n\n" + (body or "").strip()


def build_chunks(
    nodes: list[ParsedNode], *, book_id: str, book_title: str = ""
) -> list[Chunk]:
    """One chunk per leaf + one per container, with contextualized `embed_input`.
    `chunk_id` is namespaced by `book_id` so many books coexist in one table."""
    children: dict[str, list[ParsedNode]] = {}
    for n in nodes:
        if n.parent_id:
            children.setdefault(n.parent_id, []).append(n)

    chunks: list[Chunk] = []
    for n in nodes:
        # skip the synthetic book/chapter containers — they carry no retrievable
        # body and their children are already chunked.
        if n.kind in ("book", "chapter"):
            continue
        level = "section" if n.kind in SECTION_KINDS else "leaf"
        body = (n.text_normalized or n.text_raw or "").strip()
        if level == "section" and not body:
            body = _synthesize_container_text(n, children.get(n.node_id, []))
        embed_input = _make_embed_input(book_title, n, body)[:MAX_CHARS]
        chunks.append(Chunk(
            chunk_id=f"{book_id}:{n.node_id}",
            node_id=n.node_id, kind=n.kind, level=level,
            heading_path=list(n.heading_path or []),
            label=n.label, title=n.title, page=n.page_pdf_start,
            text=body, embed_input=embed_input))
    return chunks

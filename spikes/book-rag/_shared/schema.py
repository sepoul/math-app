"""The node/edge contract for the book-rag spike — the shared shape every
track codes against. Mirrors the `book_rag_spike` tables.

**Track A owns this file.** It is stubbed here so Tracks B/C/D can build against
a stable shape from minute one (against the seed fixture) before A's real
extractor lands. Track A may refine fields; keep changes additive and announce
them on issue #57 so downstream tracks aren't broken silently.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

NodeKind = Literal[
    "book", "chapter", "section", "subsection", "exposition",
    "definition", "theorem", "proposition", "lemma", "corollary",
    "proof", "example", "remark", "exercise",
]

EdgeType = Literal[
    "contains", "parent_of", "next", "previous", "proven_by",
    "references", "referenced_by", "has_equation",
    # optional later semantic edges:
    "uses", "depends_on", "explains", "example_of", "generalizes", "special_case_of",
]


class Span(BaseModel):
    pdf_page: int
    bbox: list[float]
    text: str
    font: Optional[str] = None
    font_size: Optional[float] = None
    bold: bool = False
    italic: bool = False
    reading_order: Optional[int] = None
    source: str = "native_pdf"
    confidence: Optional[float] = None


class Block(BaseModel):
    block_id: str
    pdf_page: int
    bbox: list[float]
    kind: str = "unknown"
    text_raw: str = ""
    span_ids: list[str] = Field(default_factory=list)
    reading_order: Optional[int] = None
    confidence: Optional[float] = None


class TocEntry(BaseModel):
    level: int
    raw_label: str
    chapter_number: Optional[int] = None
    section_number: Optional[str] = None
    title: Optional[str] = None
    pdf_page: Optional[int] = None
    printed_page: Optional[str] = None


class Equation(BaseModel):
    eq_id: str
    pdf_page: Optional[int] = None
    bbox: Optional[list[float]] = None
    raw_text: str = ""
    latex: Optional[str] = None
    latex_confidence: Optional[float] = None
    image_crop_key: Optional[str] = None  # object key in the book-rag-spike bucket
    parent_node_id: Optional[str] = None
    block_id: Optional[str] = None


class Node(BaseModel):
    node_id: str
    parent_id: Optional[str] = None
    kind: NodeKind
    label: Optional[str] = None            # "Theorem 4.7"
    title: Optional[str] = None            # "Chain Rule"
    heading_path: list[str] = Field(default_factory=list)
    page_pdf_start: Optional[int] = None
    page_pdf_end: Optional[int] = None
    page_printed_start: Optional[str] = None
    page_printed_end: Optional[str] = None
    text_raw: Optional[str] = None
    text_normalized: Optional[str] = None
    proves: Optional[str] = None           # proof -> proven node_id
    math_region_ids: list[str] = Field(default_factory=list)
    confidence: Optional[float] = None
    evidence: list[Any] = Field(default_factory=list)
    # ADDED R2 (Track A, #57): textual aliases for B's reference resolver + D's
    # gold — e.g. a proof node carries ["Proof", "Proof of Theorem 7.7",
    # "proof of 7.7"]; an exercise carries ["Exercise 7.1","7.1","Problem 7.1"].
    aliases: list[str] = Field(default_factory=list)


class EqRegion(BaseModel):
    """ADDED R2 (Track A, #57). A regrouped, ORDERED display-equation region —
    the deterministic clustering of several `Equation` fragments (which extract
    out of order, one per glyph-run). `member_eq_ids` points back to the raw
    `Equation` rows (never overwritten); `ordered_text` is the fragments joined
    in reading order; `latex`/`latex_confidence` are filled by a vision pass.
    Mirrors `book_rag_spike.a_eq_regions`."""
    region_id: str
    pdf_page: Optional[int] = None
    bbox: Optional[list[float]] = None
    member_eq_ids: list[str] = Field(default_factory=list)
    ordered_text: str = ""
    latex: Optional[str] = None
    latex_confidence: Optional[float] = None
    image_crop_key: Optional[str] = None
    parent_node_id: Optional[str] = None
    n_fragments: int = 0


class Edge(BaseModel):
    from_node_id: str
    to_node_id: str
    edge_type: EdgeType
    confidence: Optional[float] = None
    evidence: list[Any] = Field(default_factory=list)

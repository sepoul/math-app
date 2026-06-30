# Structured Extraction and Retrieval for a Mathematical Textbook

## Purpose

Build a trustworthy, structured representation of a mathematical textbook from its PDF.

The system should recover and preserve:

- book, chapter, section, and subsection hierarchy;
- definitions, theorems, propositions, lemmas, corollaries, proofs, examples, remarks, and exercises;
- PDF page and printed-page numbering;
- display-math regions and associated source evidence;
- explicit references between book elements;
- a graph and hybrid search index over the book itself.

This document deliberately concerns **only the book-side system**. It makes no assumptions about any external notes, agents, user data, or application workflow.

---

## Core Principle

A mathematical textbook is not a bag of text chunks.

It is already a partially explicit knowledge structure:

```text
Book
└── Chapter
    └── Section
        ├── exposition
        ├── definition
        ├── example
        ├── lemma
        ├── proposition
        ├── theorem
        ├── proof
        ├── corollary
        ├── remark
        └── exercise
```

The extraction system should preserve this organization rather than flatten the PDF into arbitrary token windows.

Embeddings are useful later, but only as one retrieval signal. The primary asset is the extracted structure.

---

## Scope

### In scope

- Native, selectable-text PDFs with good typography.
- Chapter, section, and subsection extraction.
- Formal mathematical environment extraction.
- PDF-page and printed-page mapping.
- Layout-aware source preservation.
- Structured JSON and document graph generation.
- Hybrid book retrieval using structure, lexical search, and embeddings.
- Validation and a review queue for uncertain parses.

### Not required for an MVP

- Perfect mathematical OCR.
- Perfect LaTeX reconstruction for every equation.
- A parser that works equally well on every publisher.
- A fully automatic semantic dependency graph.
- A distributed vector database.
- An LLM deciding the book’s global outline from a text blob.

A book-specific parser configuration is usually the correct engineering choice.

---

## High-Level Architecture

```text
Native PDF
  ↓
layout-aware span extraction
  ↓
page blocks + header/footer detection
  ↓
TOC/bookmark parsing
  ↓
heading hierarchy parser
  ↓
theorem/proof/example/definition parser
  ↓
validation + confidence + review queue
  ↓
structured document graph
  ↓
section and leaf-node indexing
  ↓
hybrid retrieval: lexical + embeddings + metadata + reranker
```

---

## 1. Inspect the PDF Before Building Anything

First determine whether the document is truly native and structurally usable.

Check:

- text selection quality;
- whether copy/paste preserves reading order;
- whether formulas are selectable or represented as drawing/image content;
- whether PDF bookmarks / an outline exist;
- whether a table of contents exists;
- page-number style and front matter;
- one- versus two-column layout;
- typography used for chapter, section, theorem, and proof labels.

For a clean native math PDF, the first version can be pleasantly boring:

```text
PDF
  → spans with text + font + size + bbox
  → TOC / bookmark extraction
  → heading parser
  → theorem-environment parser
  → structured JSON / graph
  → hybrid index
```

The clean PDF is the source of truth. Do not introduce OCR unless a concrete region is missing or malformed.

---

## 2. Extract Layout-Aware Text, Not Plain Text

Extract text as spans with typography and geometry.

A useful primitive is:

```json
{
  "page_pdf": 83,
  "bbox": [72.1, 194.8, 523.9, 217.0],
  "text": "4.2 The Differential",
  "font": "Times-Bold",
  "font_size": 15.8,
  "font_flags": {
    "bold": true,
    "italic": false
  },
  "reading_order": 12,
  "source": "native_pdf",
  "confidence": 0.99
}
```

Preserve:

- text;
- physical PDF page;
- bounding box;
- font family;
- font size;
- bold/italic flags;
- line and block ordering;
- image / equation regions;
- PDF links and bookmarks, when present.

Do not discard coordinates. Coordinates distinguish body text from headings, running headers, footnotes, captions, page numbers, and display equations.

### Practical stack

```text
PyMuPDF / fitz      layout-aware native PDF extraction
pdfplumber          alternate layout inspection
pypdf               PDF outline and metadata
SQLite              initial persistent storage
SQLite FTS5         lexical search
FAISS or LanceDB    local vector search
```

The exact libraries are replaceable. The key capability is span-level extraction with layout metadata.

---

## 3. Build a Page Layout Model

Before semantic classification, reconstruct each page into layout regions.

```text
Page
├── header
├── footer
├── body column(s)
│   ├── heading
│   ├── prose paragraph
│   ├── theorem-like block
│   ├── proof block
│   ├── display equation
│   ├── figure / caption
│   └── footnote
└── page number
```

### Block record

```json
{
  "block_id": "book-p087-b012",
  "page_pdf": 87,
  "bbox": [72, 196, 524, 417],
  "kind": "unknown",
  "text_raw": "Theorem 4.7 ...",
  "span_ids": ["book-p087-s041", "book-p087-s042"],
  "reading_order": 12,
  "confidence": 0.88
}
```

The early pass should be geometric and conservative:

- group words into lines;
- group lines into blocks;
- infer columns;
- preserve original and corrected reading order;
- flag display-math regions;
- identify repeated top/bottom regions across pages.

---

## 4. Parse the Table of Contents and PDF Outline

The table of contents and PDF bookmarks are high-value structural anchors.

Normalize TOC entries:

```json
{
  "raw_label": "4.2 The Differential",
  "chapter_number": 4,
  "section_number": "4.2",
  "title": "The Differential",
  "printed_page": 72
}
```

Use them to:

- seed expected chapter and section labels;
- validate in-body heading extraction;
- align printed-page numbers to PDF pages;
- repair weak title extraction;
- detect missing sections.

Store two separate page fields:

```text
pdf_page       physical index in the PDF
printed_page   page number displayed in the book
```

Do not assume their offset is globally constant. Front matter, title pages, Roman numerals, appendices, and edition quirks can all break a simplistic mapping.

---

## 5. Detect Heading Candidates

Heading detection should combine several signals. Do not rely on a regex alone.

Example score features:

```text
numbering pattern               +4
font larger than local median   +3
bold / semibold                 +2
extra whitespace above          +2
near page top                   +1
title-like capitalization       +1
matches TOC entry               +4
ends with ordinary prose        -2
very long line                  -2
inside body prose block         -3
matches running header          -8
```

Typical patterns:

```text
Chapter 4
4.2 The Differential
4.2.1 Coordinate Descriptions
Appendix A
```

Emit a structured heading candidate:

```json
{
  "text": "4.2 The Differential",
  "classification": "section_heading",
  "section_number": "4.2",
  "confidence": 0.98,
  "evidence": [
    "matched numbering pattern",
    "font larger than local body median",
    "matched TOC entry"
  ]
}
```

---

## 6. Construct the Heading Hierarchy

Once headings are classified, hierarchy construction is largely deterministic.

```text
Chapter 4
  Section 4.1
  Section 4.2
    Subsection 4.2.1
    Subsection 4.2.2
  Section 4.3
Chapter 5
```

Use a stack plus numbering rules:

```text
4.2.3 belongs under 4.2
4.2 belongs under 4
4 belongs under Chapter 4
```

Where numbering is absent or inconsistent, fall back to:

- heading typography;
- indentation;
- local whitespace;
- table-of-contents alignment;
- nearby numbering continuity.

---

## 7. Detect and Remove Running Headers and Footers

Repeated top- or bottom-margin text should not become semantic content.

Examples:

```text
Introduction to Manifolds
Chapter 4: Smooth Maps
87
```

A simple detector:

```text
same or near-identical text
+ repeated across many pages
+ stable y-coordinate
= likely running header/footer
```

Retain it as layout metadata if useful, but do not index it as ordinary text.

---

## 8. Parse Formal Mathematical Environments

Math books are unusually cooperative because they explicitly label important blocks.

### Common labels

```text
Definition 4.3
Theorem 5.7
Proposition 6.2
Lemma 6.4
Corollary 6.5
Example 3.8
Remark 4.10
Proof.
Exercise 7.3
```

Use regex plus typography and local geometry.

### Book-specific configuration

```yaml
book: introduction_to_manifolds

heading_patterns:
  chapter:
    regex: '^Chapter\s+(\d+)\b'
  section:
    regex: '^(\d+)\.(\d+)\s+.+'
  subsection:
    regex: '^(\d+)\.(\d+)\.(\d+)\s+.+'

environment_patterns:
  definition: '^(Definition)\s+(\d+(?:\.\d+)*)'
  theorem: '^(Theorem|Proposition|Lemma|Corollary)\s+(\d+(?:\.\d+)*)'
  proof: '^Proof\.?$'
  example: '^(Example|Remark|Exercise)\s+(\d+(?:\.\d+)*)?'
```

### Block boundaries

A theorem-like item consists of:

```text
label line
+ following prose
+ display equations
+ continuation paragraphs
until:
  - the next labeled environment;
  - the next equal-or-higher-level heading;
  - document end.
```

The parser should create typed nodes rather than generic chunks.

```json
{
  "id": "book.ch4.sec2.theorem7",
  "kind": "theorem",
  "label": "Theorem 4.7",
  "title": "Chain Rule",
  "path": [
    "Chapter 4: Smooth Maps",
    "4.2 The Differential"
  ],
  "page_pdf_start": 86,
  "page_pdf_end": 87,
  "page_printed_start": 72,
  "page_printed_end": 73,
  "statement_text": "...",
  "math_region_ids": ["book-p087-eq004"],
  "parent_id": "book.ch4.sec2",
  "confidence": 0.98
}
```

### Theorem-proof linkage

Keep proofs as separate nodes and connect them.

```json
{
  "id": "book.ch4.sec2.proof7",
  "kind": "proof",
  "proves": "book.ch4.sec2.theorem7",
  "page_pdf_start": 87,
  "page_pdf_end": 88,
  "text": "Proof. ..."
}
```

This preserves useful distinctions:

- theorem statement;
- proof of theorem;
- theorem plus proof;
- examples near theorem;
- later references to theorem.

---

## 9. Preserve Equations as First-Class Regions

Do not block structural extraction on perfect LaTeX recovery.

Represent display equations separately:

```json
{
  "id": "book-p087-eq004",
  "kind": "display_math",
  "page_pdf": 87,
  "bbox": [95, 310, 480, 345],
  "raw_text": "d(f o g)p = dfg(p) o dgp",
  "image_crop_id": "book-page87-eq4",
  "latex": null,
  "latex_confidence": 0.42
}
```

If a later process produces corrected LaTeX, retain both the raw evidence and the corrected representation:

```json
{
  "latex": "d(f \\circ g)_p = df_{g(p)} \\circ dg_p",
  "latex_confidence": 0.96,
  "source": "postprocess"
}
```

Never silently replace source evidence with inferred notation.

For book retrieval, an equation should be linked to:

- its surrounding block;
- its parent theorem/definition/proof;
- its page;
- its visual crop;
- any corrected textual representation.

---

## 10. Validation and Confidence

A parser that outputs JSON is not necessarily correct. Validate aggressively.

### Structural invariants

```text
Section numbering should progress sensibly:
4.1 → 4.2 → 4.3

A theorem should not begin inside a proof.

A proof should normally attach to a preceding theorem-like item.

Each TOC section should have a matching in-body heading.

No paragraph should belong to two sibling sections.

A child cannot begin before its parent begins.

Printed page numbers should be monotone.

A repeated top-margin line is not a sequence of headings.
```

### Confidence records

Every structural decision should carry a score and evidence:

```json
{
  "node": "section 4.2",
  "confidence": 0.94,
  "evidence": [
    "matched TOC entry",
    "numbering pattern",
    "bold heading typography",
    "consistent local whitespace"
  ]
}
```

Low-confidence items should enter a review queue.

Typical review candidates:

- split headings;
- malformed reading order;
- unexpected environment labels;
- column interleaving;
- equation interruptions;
- ambiguous proof attachment;
- pages with unusual publisher layout.

---

## 11. Build a Document Graph

The target is a graph, not merely a folder of chunks.

```text
Book
└── Chapter 4: Smooth Maps
    └── §4.2 The Differential
        ├── Definition 4.1
        ├── Example 4.3
        ├── Theorem 4.7: Chain Rule
        │   └── Proof of Theorem 4.7
        ├── Remark 4.8
        └── Exercise 4.9
```

Start with explicit graph edges that are easy to recover:

```text
contains
parent_of
next
previous
proven_by
references
referenced_by
has_equation
appears_on_page
```

Example:

```text
Theorem 4.7
  ├── contained_in → §4.2
  ├── proven_by → Proof of Theorem 4.7
  ├── has_equation → Equation 4
  ├── previous → Example 4.3
  ├── next → Remark 4.8
  └── references → Theorem 3.8
```

Later, optionally add higher-level semantic edges:

```text
uses
depends_on
explains
example_of
generalizes
special_case_of
```

These should be confidence-scored and evidence-backed.

---

## 12. Chunking Strategy

Do not make arbitrary fixed token windows the primary index units.

Use two levels.

### Leaf nodes

Leaf nodes are direct retrieval units:

- definition;
- theorem statement;
- proof;
- example;
- remark;
- exercise;
- short exposition passage.

Preserve the whole semantic unit even if it is shorter or longer than a preferred token range.

### Section nodes

Create one broad representation for each section:

- heading path;
- section text or concise generated summary;
- contained definitions/theorems;
- page range;
- links to leaf nodes.

This enables coarse-to-fine search:

```text
query
  ↓
retrieve relevant sections
  ↓
retrieve exact leaves inside those sections
  ↓
return source-linked results
```

### Contextualized embedding input

When generating embeddings, include hierarchy and type:

```text
Book: Introduction to Manifolds
Chapter 4: Smooth Maps
Section 4.2: The Differential
Type: Theorem
Label: Theorem 4.7

[the theorem statement]
```

This is more informative than embedding an isolated sentence stripped of context.

---

## 13. Hybrid Retrieval Over the Book

Embeddings should not be the only retrieval mechanism for mathematics.

Use a combined score:

```text
final_score =
  semantic_vector_score
+ lexical_score
+ metadata_score
+ type_match_score
+ reranker_score
```

### Semantic vector retrieval

Useful for conceptual paraphrases and broad topic queries.

### Lexical retrieval

Essential for:

- theorem labels;
- exact symbols;
- named constructions;
- precise terminology;
- direct phrases from the book.

A basic lexical index such as SQLite FTS5 is enough to begin.

### Metadata and type boosts

Boost results according to their structural role.

Examples:

```text
"what is X?"
  → definitions

"state/prove theorem"
  → theorem/proposition/corollary and proof

"why is this true?"
  → proof, lemmas, adjacent exposition

"give intuition/example"
  → examples, remarks, exposition

"Theorem 4.7"
  → exact label match dominates
```

### Reranking

Retrieve broadly, then rerank a smaller set.

```text
query
  ↓
top 20–50 candidates from lexical + vector search
  ↓
metadata and type boosts
  ↓
rerank top 10–30 candidates
  ↓
group by section / theorem / page range
```

The reranker may be a cross-encoder or a tightly constrained model-based scorer. It should rank candidates; it should not invent source passages.

---

## 14. Book-Side Retrieval Capabilities

With the graph and index in place, the book can support:

### Direct lookup

```text
Find the definition of a regular value.
Find Theorem 4.7.
Show the proof attached to Proposition 6.2.
```

### Conceptual lookup

```text
Find passages about tangent maps.
Find examples involving local coordinates.
Find results related to submersions.
```

### Structural lookup

```text
What comes immediately before and after this theorem?
What definitions occur in this section?
Which proofs reference this lemma?
Which examples are near this concept?
```

### Bounded graph expansion

```text
Start from a theorem
  → its proof
  → explicit references
  → enclosing section
  → selected nearby definitions/examples
```

Bound expansion by graph depth and confidence. “Related” should not devolve into every mathematically adjacent topic in the book.

---

## 15. Suggested Storage Model

Use relational storage for structure and a vector index for embeddings.

### Core tables

```text
books
pages
spans
blocks
nodes
node_edges
equations
toc_entries
embeddings
parse_runs
validation_issues
```

### Node fields

```text
node_id
book_id
parent_id
kind
label
title
heading_path
page_pdf_start
page_pdf_end
page_printed_start
page_printed_end
text_raw
text_normalized
embedding_id
confidence
created_at
```

### Edge fields

```text
from_node_id
to_node_id
edge_type
confidence
evidence
```

Useful `edge_type` values:

```text
contains
parent_of
next
previous
proven_by
references
referenced_by
has_equation
uses
depends_on
explains
example_of
```

---

## 16. MVP Plan

Start with one book and one or two representative chapters.

### Phase 1: Structural extraction

1. Inspect PDF characteristics.
2. Extract spans with page, bbox, font, and style.
3. Parse TOC and bookmarks.
4. Detect chapters, sections, and subsections.
5. Detect theorem-like environments.
6. Attach all nodes to PDF and printed pages.
7. Export JSON.
8. Manually inspect a chapter and tune the parser configuration.

### Phase 2: Build the document graph

1. Add parent/child hierarchy edges.
2. Link theorem-like items to proofs.
3. Add previous/next sibling edges.
4. Extract explicit references such as “Theorem 4.7.”
5. Add equation-to-block links.
6. Validate graph invariants.

### Phase 3: Add retrieval

1. Build a lexical index over sections and leaves.
2. Build embeddings for section and leaf nodes.
3. Implement hybrid ranking.
4. Add metadata/type boosts.
5. Add reranking.
6. Return source-linked pages, hierarchy, node type, and excerpts.

### Phase 4: Improve semantic links

1. Extract explicit concept mentions.
2. Add confidence-scored concept-to-node mappings.
3. Add selected prerequisite/explanation edges.
4. Build bounded “related material” navigation.

---

## 17. First Vertical Slice: Success Criteria

A first version is useful if it can reliably:

- recover the correct chapter and section hierarchy;
- identify most definitions, theorems, and proofs;
- preserve correct PDF and printed-page locations;
- link a proof to the right theorem;
- locate an exact theorem/definition by label;
- retrieve conceptually relevant sections and leaves;
- return a traceable path back to the source page.

The first debugging question should be:

```text
When retrieval is wrong, is the failure caused by:
  - heading segmentation;
  - PDF reading order;
  - theorem/proof boundary detection;
  - page mapping;
  - weak lexical retrieval;
  - semantic vector retrieval;
  - metadata scoring;
  - reranking;
  - graph expansion?
```

For mathematical textbooks, segmentation and structural accuracy usually matter more than swapping embedding models.

---

## Design Rules

1. Preserve source evidence.
2. Keep PDF and printed-page numbers separate.
3. Store layout metadata; do not flatten early.
4. Treat theorem, proof, definition, example, remark, and exercise as first-class node types.
5. Use embeddings as one signal, not the whole system.
6. Use hybrid lexical plus semantic retrieval.
7. Prefer deterministic parsing before probabilistic interpretation.
8. Use model assistance only for uncertain local regions.
9. Validate against TOC, numbering, typography, and graph invariants.
10. Keep retrieval outputs source-linked and auditable.
11. Start book-specific; generalize only after several real books reveal stable common patterns.
12. Keep graph expansion bounded and explainable.

---

## Bottom Line

For a clean native mathematical textbook PDF, this is highly feasible.

The real task is not “PDF embedding.” It is extracting the book’s existing hierarchy and formal mathematical grammar into a document graph, then indexing that graph with lexical and semantic retrieval.

A strong book-side system can locate material by chapter, section, theorem label, concept, proof relationship, page, local neighborhood, and explicit reference—without collapsing the text into undifferentiated PDF soup.

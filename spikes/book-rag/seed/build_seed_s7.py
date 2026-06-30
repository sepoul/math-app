"""Hand-built SEED fixture for the §7 Quotients slice (Track B, round 1).

Track A had not written `a_nodes` for the slice yet, so this seed lets Track B
(graph + references + validation) build immediately and never block. It mirrors
`_shared/schema.py` (Node) and is validated against it before writing JSON.

Provenance: hand-extracted from Tu, *An Introduction to Manifolds* (2nd ed.),
§7 "Quotients" — PDF pages 90-103 (printed pages 71-84). Page offset is
**printed = pdf_page - 19** in this region (verified: pdf 90 top-margin shows
"71"; pdf 22 shows "3").

This is a SEED, not Track A's authoritative output. When `a_nodes` is populated,
Track B swaps to it behind the same `node_id`/schema. Node IDs use a stable
`book.ch1.s7.*` grammar so edges/refs survive the swap if A adopts the same ids.

Run from `spikes/book-rag`:  .venv/bin/python seed/build_seed_s7.py
"""
from __future__ import annotations

import json
import pathlib
import sys

# resolve _shared from spikes/book-rag (CWD) or from this file's parents
HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))  # spikes/book-rag
from _shared.schema import Node, Equation  # noqa: E402

OFFSET = 19  # printed = pdf - OFFSET in this region
SEED_RUN = "seed-track-b-r1"

HEAD = ["Chapter 1: Euclidean Spaces", "§7 Quotients"]  # heading_path prefix


def pp(pdf: int) -> str:
    return str(pdf - OFFSET)


def node(node_id, parent_id, kind, *, label=None, title=None, sub=None,
         pdf_start=None, pdf_end=None, proves=None, text="", conf=0.95,
         math_region_ids=None, evidence=None) -> Node:
    hp = list(HEAD) + ([sub] if sub else [])
    return Node(
        node_id=node_id, parent_id=parent_id, kind=kind, label=label,
        title=title, heading_path=hp,
        page_pdf_start=pdf_start, page_pdf_end=pdf_end,
        page_printed_start=pp(pdf_start) if pdf_start else None,
        page_printed_end=pp(pdf_end) if pdf_end else None,
        text_raw=text, text_normalized=text, proves=proves,
        math_region_ids=math_region_ids or [],
        confidence=conf, evidence=evidence or ["hand-seed §7"],
    )


# --- the section + 7 subsections -------------------------------------------
SEC = "book.ch1.s7"
nodes: list[Node] = [
    node(SEC, "book.ch1", "section", label="§7", title="Quotients",
         pdf_start=90, pdf_end=103,
         text="Gluing the edges of a malleable square is one way to create new "
              "surfaces. ... This gluing process is called an identification or a "
              "quotient construction. The main results of this section give "
              "conditions under which a quotient space remains second countable "
              "and Hausdorff.",
         conf=0.99, evidence=["matched TOC §7", "Times-Bold 14pt heading"]),
    node(f"{SEC}.7_1", SEC, "subsection", label="7.1",
         title="The Quotient Topology", sub="7.1 The Quotient Topology",
         pdf_start=90, pdf_end=91, conf=0.98,
         text="Recall that an equivalence relation on a set S is reflexive, "
              "symmetric, transitive ... the quotient topology on S/~ ...",
         evidence=["matched TOC 7.1", "bold 12pt"]),
    node(f"{SEC}.7_2", SEC, "subsection", label="7.2",
         title="Continuity of a Map on a Quotient",
         sub="7.2 Continuity of a Map on a Quotient",
         pdf_start=91, pdf_end=92, conf=0.98,
         text="Let ~ be an equivalence relation on the topological space S ... it "
              "induces a map f-bar : S/~ -> Y ...",
         evidence=["matched TOC 7.2", "bold 12pt"]),
    node(f"{SEC}.7_3", SEC, "subsection", label="7.3",
         title="Identification of a Subset to a Point",
         sub="7.3 Identification of a Subset to a Point",
         pdf_start=92, pdf_end=92, conf=0.98,
         text="If A is a subspace of a topological space S ... identifying A to a "
              "point.",
         evidence=["matched TOC 7.3", "bold 12pt"]),
    node(f"{SEC}.7_4", SEC, "subsection", label="7.4",
         title="A Necessary Condition for a Hausdorff Quotient",
         sub="7.4 A Necessary Condition for a Hausdorff Quotient",
         pdf_start=92, pdf_end=93, conf=0.98,
         text="The quotient construction does not in general preserve the "
              "Hausdorff property or second countability.",
         evidence=["matched TOC 7.4", "bold 12pt"]),
    node(f"{SEC}.7_5", SEC, "subsection", label="7.5",
         title="Open Equivalence Relations",
         sub="7.5 Open Equivalence Relations",
         pdf_start=93, pdf_end=95, conf=0.98,
         text="In this section we follow the treatment of Boothby and derive "
              "conditions under which a quotient space is Hausdorff or second "
              "countable.",
         evidence=["matched TOC 7.5", "bold 12pt"]),
    node(f"{SEC}.7_6", SEC, "subsection", label="7.6",
         title="Real Projective Space", sub="7.6 Real Projective Space",
         pdf_start=95, pdf_end=98, conf=0.98,
         text="Define an equivalence relation on R^{n+1}-{0} ... The real "
              "projective space RP^n is the quotient space ...",
         evidence=["matched TOC 7.6", "bold 12pt"]),
    node(f"{SEC}.7_7", SEC, "subsection", label="7.7",
         title="The Standard C-infinity Atlas on a Real Projective Space",
         sub="7.7 The Standard C-infinity Atlas on a Real Projective Space",
         pdf_start=98, pdf_end=99, conf=0.98,
         text="The standard atlas on RP^n ...",
         evidence=["matched TOC 7.7", "bold 12pt"]),
]

# --- formal environments (theorem-like / def / example / exercise) ----------
# (parent subsection, node_id, kind, label, title, pdf_start, pdf_end, text)
ENV = [
    (f"{SEC}.7_2", f"{SEC}.prop7_1", "proposition", "Proposition 7.1", None, 91, 91,
     "The induced map f-bar : S/~ -> Y is continuous if and only if the map "
     "f : S -> Y is continuous."),
    (f"{SEC}.7_3", f"{SEC}.ex7_2", "example", "Example 7.2", None, 92, 92,
     "Let I be the unit interval [0,1] and I/~ the quotient obtained from I by "
     "identifying {0,1} to a point ... induces f-bar : I/~ -> S^1."),
    (f"{SEC}.7_3", f"{SEC}.prop7_3", "proposition", "Proposition 7.3", None, 92, 92,
     "The function f-bar : I/~ -> S^1 is a homeomorphism."),
    (f"{SEC}.7_4", f"{SEC}.prop7_4", "proposition", "Proposition 7.4", None, 92, 93,
     "If the quotient space S/~ is Hausdorff, then the equivalence class [p] of "
     "any point p in S is closed in S."),
    # unnumbered Example on printed p74 (pdf 93) — Tu uses a bare "Example."
    (f"{SEC}.7_4", f"{SEC}.ex_p74", "example", "Example", None, 93, 93,
     "Define an equivalence relation ~ on R by identifying the open interval "
     "]0,inf[ to a point. Then R/~ is not Hausdorff ..."),
    (f"{SEC}.7_5", f"{SEC}.def7_5", "definition", "Definition 7.5", None, 93, 93,
     "An equivalence relation ~ on a topological space S is said to be open if "
     "the projection map pi : S -> S/~ is open."),
    (f"{SEC}.7_5", f"{SEC}.ex7_6", "example", "Example 7.6", None, 93, 93,
     "The projection map to a quotient space is in general not open. For "
     "example, identify 1 and -1 on R ..."),
    (f"{SEC}.7_5", f"{SEC}.thm7_7", "theorem", "Theorem 7.7", None, 94, 94,
     "Suppose ~ is an open equivalence relation on a topological space S. Then "
     "S/~ is Hausdorff if and only if the graph R of ~ is closed in S x S."),
    (f"{SEC}.7_5", f"{SEC}.cor7_8", "corollary", "Corollary 7.8", None, 94, 94,
     "A topological space S is Hausdorff if and only if the diagonal Delta in "
     "S x S is closed. (Found in round-1 ref-eval: cited 3x in §7 prose but "
     "missing from the first hand-seed; added.)"),
    (f"{SEC}.7_5", f"{SEC}.thm7_9", "theorem", "Theorem 7.9", None, 95, 95,
     "Let ~ be an open equivalence relation on a topological space S with "
     "projection pi. If B={B_a} is a basis for S, then {pi(B_a)} is a basis for "
     "S/~."),
    (f"{SEC}.7_5", f"{SEC}.cor7_10", "corollary", "Corollary 7.10", None, 95, 95,
     "If ~ is an open equivalence relation on a second-countable space S, then "
     "S/~ is second countable."),
    (f"{SEC}.7_6", f"{SEC}.exr7_11", "exercise", "Exercise 7.11", "Real projective space as a quotient of a sphere", 96, 96,
     "For x=(x1,...,xn) in R^n ... real projective space as a quotient of a "
     "sphere."),
    (f"{SEC}.7_6", f"{SEC}.ex7_12", "example", "Example 7.12", "The real projective line RP1", 96, 96,
     "The real projective line RP^1 ..."),
    (f"{SEC}.7_6", f"{SEC}.ex7_13", "example", "Example 7.13", "The real projective plane RP2", 96, 97,
     "By Exercise 7.11, there is a homeomorphism ... real projective plane RP^2 "
     "(see Problem 7.2)."),
    (f"{SEC}.7_6", f"{SEC}.prop7_14", "proposition", "Proposition 7.14", None, 98, 98,
     "The equivalence relation ~ on R^{n+1}-{0} in the definition of RP^n is "
     "open."),
    (f"{SEC}.7_6", f"{SEC}.cor7_15", "corollary", "Corollary 7.15", None, 98, 98,
     "The real projective space RP^n is second countable."),
    (f"{SEC}.7_6", f"{SEC}.prop7_16", "proposition", "Proposition 7.16", None, 98, 98,
     "The real projective space RP^n is Hausdorff."),
]
for parent, nid, kind, label, title, ps, pe, text in ENV:
    sub_title = next((n.heading_path[-1] for n in nodes if n.node_id == parent), None)
    nodes.append(node(nid, parent, kind, label=label, title=title, sub=sub_title,
                      pdf_start=ps, pdf_end=pe, text=text, conf=0.96,
                      evidence=[f"bold label '{label}'"]))

# --- proofs (separate nodes, linked via proves) -----------------------------
PROOFS = [
    (f"{SEC}.prop7_1", f"{SEC}.prf7_1", 91, 91,
     "Proof. (=>) If f-bar is continuous ... (<=) Suppose f is continuous ..."),
    (f"{SEC}.prop7_3", f"{SEC}.prf7_3", 92, 92,
     "Proof. Since f is continuous, f-bar is continuous by Proposition 7.1 ... "
     "By Corollary A.36, f-bar is a homeomorphism."),
    (f"{SEC}.thm7_7", f"{SEC}.prf7_7", 94, 94,
     "Proof. There is a sequence of equivalent statements ... see Problem 7.1 ..."),
    (f"{SEC}.thm7_9", f"{SEC}.prf7_9", 95, 95,
     "Proof. Since pi is an open map, {pi(B_a)} is a collection of open sets ..."),
    (f"{SEC}.prop7_14", f"{SEC}.prf7_14", 98, 98,
     "Proof. For an open set U in R^{n+1}-{0}, the image pi(U) is open in RP^n "
     "if and only if ..."),
    (f"{SEC}.cor7_15", f"{SEC}.prf7_15", 98, 98,
     "Proof. Apply Corollary 7.10."),
    (f"{SEC}.prop7_16", f"{SEC}.prf7_16", 98, 98,
     "Proof. Let S = R^{n+1}-{0} and consider the set ..."),
]
for proven, pid, ps, pe, text in PROOFS:
    sub_title = next((n.heading_path[-1] for n in nodes if n.node_id == proven), None)
    nodes.append(node(pid, proven, "proof", label="Proof", sub=sub_title,
                      pdf_start=ps, pdf_end=pe, proves=proven, text=text,
                      conf=0.9, evidence=[f"'Proof.' attaches to {proven}"]))

# --- the Problems block (exercises 7.1-7.9) ---------------------------------
PROBLEMS = [
    ("7.1", "Image of the inverse image of a map", 100),
    ("7.2", "Real projective plane", 100),
    ("7.3", "Closedness of the diagonal of a Hausdorff space", 100),
    ("7.4", "Quotient of a sphere with antipodal points identified", 100),
    ("7.5", "Orbit space of a continuous group action", 100),
    ("7.6", "Quotient of R by 2*pi*Z", 100),
    ("7.7", "The circle as a quotient space", 101),
    ("7.8", "The Grassmannian G(k,n)", 101),
    ("7.9", "Compactness of real projective space", 102),
]
nodes.append(node(f"{SEC}.problems", SEC, "exposition", label="Problems",
                  title="Problems", sub="Problems", pdf_start=100, pdf_end=103,
                  text="Problems block for §7.", conf=0.97,
                  evidence=["bold 'Problems' 12pt heading"]))
for num, title, pdf in PROBLEMS:
    nodes.append(node(f"{SEC}.prob{num.replace('.', '_')}", f"{SEC}.problems",
                      "exercise", label=f"Problem {num}", title=title, sub="Problems",
                      pdf_start=pdf, pdf_end=pdf,
                      text=f"Problem {num}. {title}.", conf=0.94,
                      evidence=[f"bold '{num}' in Problems block"]))

# parent stub so parent_id refs resolve (chapter is Track A's; we stub it)
chapter = Node(node_id="book.ch1", parent_id="book", kind="chapter",
               label="Chapter 1", title="Euclidean Spaces",
               heading_path=["Chapter 1: Euclidean Spaces"],
               page_pdf_start=22, page_printed_start="1", confidence=0.99,
               evidence=["TOC L1"])
book = Node(node_id="book", kind="book", title="An Introduction to Manifolds",
            heading_path=[], confidence=1.0, evidence=["root"])

# --- a couple of first-class display equations ------------------------------
equations = [
    Equation(eq_id=f"{SEC}.eq_proj", pdf_page=90, raw_text="pi : S -> S/~",
             parent_node_id=f"{SEC}.7_1", latex_confidence=0.5),
    Equation(eq_id=f"{SEC}.eq_graphR", pdf_page=93,
             raw_text="R = {(x,y) in SxS | x ~ y}",
             parent_node_id=f"{SEC}.7_5", latex_confidence=0.5),
    Equation(eq_id=f"{SEC}.eq_rpn", pdf_page=95,
             raw_text="x ~ y  <=>  y = t x for some nonzero real t",
             parent_node_id=f"{SEC}.7_6", latex_confidence=0.5),
]
# attach equations to their parents' math_region_ids
by_id = {n.node_id: n for n in nodes}
for eq in equations:
    if eq.parent_node_id in by_id:
        by_id[eq.parent_node_id].math_region_ids.append(eq.eq_id)

ALL = [book, chapter] + nodes

if __name__ == "__main__":
    out = {
        "provenance": "Tu §7 Quotients, pdf 90-103 / printed 71-84, offset 19; hand-seed Track B r1",
        "run_id": SEED_RUN,
        "nodes": [n.model_dump() for n in ALL],
        "equations": [e.model_dump() for e in equations],
    }
    dest = HERE.parent / "seed_s7_quotients.json"
    dest.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    kinds: dict[str, int] = {}
    for n in ALL:
        kinds[n.kind] = kinds.get(n.kind, 0) + 1
    print(f"wrote {dest} : {len(ALL)} nodes, {len(equations)} equations")
    print("by kind:", dict(sorted(kinds.items())))

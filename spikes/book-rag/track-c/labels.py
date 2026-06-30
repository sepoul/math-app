"""Track C — the A↔D label seam.

The eval harness (`metrics._matches`) matches a retrieved item to gold on a
normalized `label` string (gold node_ids are null this round). Track A and Track
D use *different* label conventions for containers and proofs:

  node kind     A's `label`     D's gold label
  ----------    -----------     ----------------------------------
  theorem/...   "Theorem 7.7"   "Theorem 7.7"                       (match as-is)
  subsection    "7.1"           "subsection 7.1 The Quotient Topology"
  proof         "Proof"         "Proof of Theorem 7.7"

So Track C mints a `match_label` per node that follows D's convention. Pure
string work, no DB — unit-testable. Also fixes a real spacing drift: A emits
"C∞Versus Analytic Functions" (glued), D's gold has "C∞ Versus ...". We insert a
space after ∞ / a digit when glued to a capital so normalized compare lands.
"""
from __future__ import annotations

import re

# environment kinds whose A label already matches gold
_ENV_KINDS = {"definition", "theorem", "proposition", "lemma",
              "corollary", "example", "remark", "exercise"}

# insert a space where A glued a sub/superscript or digit onto the next word:
#   "C∞Versus" -> "C∞ Versus" ; also handles a lowercase/digit glued to a capital
_GLUE = re.compile(r"(?<=[∞0-9a-z])(?=[A-Z])")


def _despace(title: str) -> str:
    return _GLUE.sub(" ", title or "").strip()


def match_label_for(node: dict, by_id: dict[str, dict]) -> str | None:
    """Return the gold-convention label for a node (or None)."""
    kind = node.get("kind")
    label = node.get("label")
    title = node.get("title")

    if kind == "subsection":
        # gold: "subsection <num> <Title>" ; A: label=num, title=Title
        num = label or ""
        return f"subsection {num} {_despace(title or '')}".strip()

    if kind == "section":
        # gold never anchors on a bare section; keep "§N Title" for traceability
        return f"§{label} {_despace(title or '')}".strip() if label else None

    if kind == "proof":
        # gold: "Proof of <proven label>"; resolve the proves link to its label
        proven = node.get("proves")
        if proven and proven in by_id:
            pl = by_id[proven].get("label")
            if pl:
                return f"Proof of {pl}"
        return "Proof"

    if kind in _ENV_KINDS:
        return label  # already in gold convention

    return label

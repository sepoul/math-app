r"""Deterministic text normalization for the synthesis path.

The synthesis renderer (`math-ui/components/library/markdown-math.tsx`) runs the
note's Markdown through **remark-math**, which lexes ONLY `$...$` (inline) and
`$$...$$` (display) math. KaTeX-style `\(...\)` / `\[...\]` delimiters are NOT
remark-math delimiters, so any the model emits render as **raw literal text**
(and the document-mode `validate_latex` is blind to them — issue #33).

`convert_delimiters` is the deterministic guard against that drift: it rewrites
the four legacy delimiters to their canonical `$`/`$$` equivalents so no
synthesis ever persists `\(`/`\)`/`\[`/`\]`. It is the SAME conversion the
in-place repair migration (`scripts/migrate_synthesis_delimiters.py`) applies to
existing notes — factored here so the live synthesis path and the migration
share one proven implementation (and one place to reason about it).

Pure and idempotent: the spec is literal (`\(`→`$`, `\)`→`$`, `\[`→`$$`,
`\]`→`$$`), the four search strings are disjoint so replacement order is
irrelevant, and the output contains none of them — re-applying it is a no-op,
and content already in `$` form is returned unchanged.
"""
from __future__ import annotations

# The four legacy delimiters → their dollar equivalents. Each is replaced
# independently; the search strings are disjoint so replacement order is
# irrelevant. This is the canonical, prod-proven mapping (PR #10).
_DELIMITERS: tuple[tuple[str, str], ...] = (
    (r"\(", "$"),
    (r"\)", "$"),
    (r"\[", "$$"),
    (r"\]", "$$"),
)


def convert_delimiters(markdown: str) -> str:
    r"""Rewrite legacy LaTeX delimiters to canonical `$`/`$$` math.

    Pure and idempotent: the output contains no `\(`/`\)`/`\[`/`\]`, so
    re-applying it is a no-op (and content already in `$` form is unchanged).
    Falsy input (``""``/``None``-ish empty) is returned unchanged.
    """
    if not markdown:
        return markdown
    out = markdown
    for old, new in _DELIMITERS:
        out = out.replace(old, new)
    return out

r"""Deterministic text normalization for the synthesis path.

The synthesis renderer (`math-ui/components/library/markdown-math.tsx`) runs the
note's Markdown through **remark-math**, which lexes ONLY `$...$` (inline) and
`$$...$$` (display) math. Two drift modes break rendering (issue #33), both
silent under the old document-mode validator:

1. **Legacy delimiters.** KaTeX-style `\(...\)` / `\[...\]` are NOT remark-math
   delimiters, so any the model emits render as **raw literal text**.
2. **Glued multi-line display math.** A `$$` that is glued to its first content
   line and then spans a newline — e.g. ``$$a, \qquad\nb.$$`` — is lexed by
   micromark as single-line **text** math; the internal newline breaks it and
   desyncs the rest of the block, again rendering raw. (Single-line `$$…$$`
   happens to render fine, which is why only some notes broke.)

This module's normalizers are the deterministic guard against both:

* `convert_delimiters` — (1) only: rewrites the four legacy delimiters to their
  `$`/`$$` equivalents. The SAME conversion the in-place repair migration
  (`scripts/migrate_synthesis_delimiters.py`) applies to existing notes, so the
  migration and synthesis share one proven implementation.
* `flow_fence_display` — (2) only: promotes every `$$…$$` to a standalone block
  with the delimiters on their own lines (``$$\n…\n$$``, blank-line separated)
  so it parses as multi-line *display* math.
* `normalize_synthesis_markdown` — both, in order — what the live synthesis path
  applies so nothing it persists carries `\(`/`\)`/`\[`/`\]` or a glued `$$`.

All three are pure and idempotent: re-applying any is a no-op (legacy delimiters
are gone after the first pass; an already-fenced `$$` block re-fences to itself,
and 3+ newlines collapse to 2 so blank lines never accrete).
"""
from __future__ import annotations

import re

# The four legacy delimiters → their dollar equivalents. Each is replaced
# independently; the search strings are disjoint so replacement order is
# irrelevant. This is the canonical, prod-proven mapping (PR #10).
_DELIMITERS: tuple[tuple[str, str], ...] = (
    (r"\(", "$"),
    (r"\)", "$"),
    (r"\[", "$$"),
    (r"\]", "$$"),
)

# A `$$…$$` display span — non-greedy, DOTALL so it spans the glued multi-line
# case. Requires non-empty content; inline `$…$` (single `$`) is never matched.
_DISPLAY_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
# 3+ newlines → exactly one blank line (keeps fencing idempotent).
_BLANK_RUN_RE = re.compile(r"\n{3,}")


def convert_delimiters(markdown: str) -> str:
    r"""Rewrite legacy LaTeX delimiters to canonical `$`/`$$` math.

    Pure and idempotent: the output contains no `\(`/`\)`/`\[`/`\]`, so
    re-applying it is a no-op (and content already in `$` form is unchanged).
    Falsy input (``""``/``None``-ish empty) is returned unchanged. Does NOT
    touch `$$` placement — see `flow_fence_display` for that.
    """
    if not markdown:
        return markdown
    out = markdown
    for old, new in _DELIMITERS:
        out = out.replace(old, new)
    return out


def flow_fence_display(markdown: str) -> str:
    r"""Put every `$$…$$` display block on its own lines (blank-line separated).

    ``$$a, \qquad\nb.$$`` → ``\n\n$$\na, \qquad\nb.\n$$\n\n`` — so micromark
    parses it as a multi-line display block instead of broken text math. Pure;
    idempotent (an already-fenced block re-fences to itself, and 3+ newlines
    collapse to 2 so re-running never adds blank lines). Does NOT strip the
    document (the caller decides) so it composes cleanly; inline `$…$` is
    untouched.
    """
    if not markdown:
        return markdown

    def _fence(match: "re.Match[str]") -> str:
        content = match.group(1).strip()
        return f"\n\n$$\n{content}\n$$\n\n"

    fenced = _DISPLAY_RE.sub(_fence, markdown)
    return _BLANK_RUN_RE.sub("\n\n", fenced)


def normalize_synthesis_markdown(markdown: str) -> str:
    r"""Full synthesis-markdown normalization: legacy delimiters → `$`/`$$`, then
    flow-fence every `$$` block, then trim outer whitespace.

    The single entry point the live synthesis path applies to every persisted
    markdown (each segment, every section, the flat field, the stitched doc) so
    no synthesis ever stores a `\(`/`\)`/`\[`/`\]` or a glued multi-line `$$`.
    Pure and idempotent. The migration uses the narrower `convert_delimiters`
    (it only repairs the legacy-delimiter drift in stored notes; the renderer
    repairs `$$` placement for those at read time).
    """
    if not markdown:
        return markdown
    return flow_fence_display(convert_delimiters(markdown)).strip()

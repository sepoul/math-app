r"""Tests for the deterministic markdown normalizer in the synthesis path (#33).

Two drift modes, two helpers, plus the synthesis path applying them:

* `convert_delimiters` — legacy `\(…\)`/`\[…\]` → `$`/`$$` (delimiter-only).
* `flow_fence_display` / `normalize_synthesis_markdown` — also flow-fence every
  `$$…$$` onto its own lines so a glued multi-line `$$` (which micromark mis-lexes
  as text math and renders raw) parses as a display block. Pure + idempotent.
* `synthesize_note` applying `normalize_synthesis_markdown` — even when the
  (stubbed) model emits `\[…\]` / `\(…\)` or a glued `$$`, NO persisted markdown
  (flat, per-section, or stitched) carries a legacy delimiter or an unfenced
  display block.

Model calls are stubbed (mirrors `test_segmented_synthesis.py`), so nothing here
touches the network, an API key, or the math-ui validator.

Run from the repo root in the default-runtime venv::

    PYTHONPATH="packages/math-notes/src:../ai-platform/packages/core/src:../ai-platform/packages/worker/src" \
      ../ai-platform/.venv/bin/python -m pytest \
      packages/math-notes/tests/test_synthesis_delimiter_normalizer.py
"""
from __future__ import annotations

import asyncio

from mathai.math_notes import workflow
from mathai.math_notes.artifacts import NotePage, PlanTopic, SynthesisPlan
from mathai.math_notes.text import (
    convert_delimiters,
    flow_fence_display,
    normalize_synthesis_markdown,
)
from mathai.math_notes.workflow import _ReduceOutput, _SynthesisOutput, synthesize_note


# ---- convert_delimiters (delimiter-only) ---------------------------------

def test_convert_inline_and_display_delimiters():
    src = r"Let \(x\) be real. \[ x^2 \ge 0 \]"
    assert convert_delimiters(src) == "Let $x$ be real. $$ x^2 \\ge 0 $$"


def test_convert_is_idempotent():
    src = r"## H\nLet \(G\) be a group. \[ gH = Hg \]"
    once = convert_delimiters(src)
    assert convert_delimiters(once) == once
    assert "\\(" not in once and "\\[" not in once and "\\)" not in once and "\\]" not in once


def test_convert_does_not_touch_dollar_placement():
    # convert_delimiters is delimiter-only — it leaves a glued `$$` alone.
    src = "$$x$$"
    assert convert_delimiters(src) == "$$x$$"


def test_convert_handles_empty_and_none():
    assert convert_delimiters("") == ""
    assert convert_delimiters(None) is None  # type: ignore[arg-type]


# ---- flow_fence_display + normalize_synthesis_markdown -------------------

def test_normalize_fences_single_line_display():
    assert normalize_synthesis_markdown("$$x^2$$") == "$$\nx^2\n$$"


def test_normalize_fences_glued_multiline_display():
    # The confirmed prod trigger: `$$` glued to the first line, content spanning
    # a newline (note 5cb619ca). Must become a fenced multi-line display block.
    src = (
        "$$i_{\\alpha\\beta}^{\\alpha} \\colon \\pi_1(U) \\to \\pi_1(A_\\alpha), \\qquad\n"
        "i_{\\alpha\\beta}^{\\beta} \\colon \\pi_1(U) \\to \\pi_1(A_\\beta).$$"
    )
    out = normalize_synthesis_markdown(src)
    assert out.startswith("$$\n")
    assert out.endswith("\n$$")
    assert "$$i_" not in out  # opening no longer glued to content
    assert ".$$" not in out  # closing no longer glued to content
    assert "\\qquad\ni_{\\alpha\\beta}^{\\beta}" in out  # internal newline kept


def test_normalize_converts_then_fences():
    out = normalize_synthesis_markdown(r"text \[ x^2 \] more")
    assert "$$\nx^2\n$$" in out
    for bad in (r"\[", r"\]", r"\(", r"\)"):
        assert bad not in out


def test_normalize_leaves_inline_math_untouched():
    assert normalize_synthesis_markdown("a $x+y$ b") == "a $x+y$ b"


def test_normalize_fences_each_of_multiple_blocks():
    out = normalize_synthesis_markdown("$$a$$ and $$b$$")
    assert "$$\na\n$$" in out
    assert "$$\nb\n$$" in out


def test_normalize_is_idempotent():
    for src in (
        "$$x$$",
        "text \\[ y \\] and \\(z\\)",
        "$$a, \\qquad\nb.$$",
        "## H\n\n$$\nE = mc^2\n$$\n\nprose $inline$ here",
        "no math at all\n\n\n\nlots of blanks",
    ):
        once = normalize_synthesis_markdown(src)
        assert normalize_synthesis_markdown(once) == once


def test_flow_fence_collapses_blank_runs():
    # 3+ newlines collapse to 2 (the idempotency guard for blank-line separation).
    assert "\n\n\n" not in flow_fence_display("$$x$$\n\n\n\nmore")


# ---- single-pass synthesis normalizes the model's output -----------------

_TRANSCRIPT = "Did one exercise on the divergence theorem."
_PAGES = [NotePage(page_index=0, image_ref="media/0/p.jpg", raw_text="div F = ...")]


def test_single_pass_normalizes_slipped_delimiters(monkeypatch):
    # The model defies the prompt and emits display math as `\[…\]` plus an
    # inline `\(…\)`. Synthesis must persist fenced `$$` / inline `$` regardless.
    async def fake_synth(source: str, instructions):
        return _SynthesisOutput(
            markdown=r"The flux is \[ \iint_S F\cdot n\,dS \] for a region \(R\).",
            concepts=["divergence theorem"],
            summary="flux via the divergence theorem",
            validation_attempts=1,
        )

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)

    syn = asyncio.run(synthesize_note(_TRANSCRIPT, _PAGES, "SYS", plan=None))
    assert syn is not None
    assert syn.markdown is not None
    for bad in (r"\[", r"\]", r"\(", r"\)"):
        assert bad not in syn.markdown
    assert "$$\n\\iint_S F\\cdot n\\,dS\n$$" in syn.markdown
    assert "$R$" in syn.markdown


def test_single_pass_normalizes_glued_display(monkeypatch):
    async def fake_synth(source: str, instructions):
        return _SynthesisOutput(
            markdown="$$a = b, \\qquad\nc = d.$$",
            validation_attempts=1,
        )

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)

    syn = asyncio.run(synthesize_note(_TRANSCRIPT, _PAGES, "SYS", plan=None))
    assert syn is not None
    assert syn.markdown == "$$\na = b, \\qquad\nc = d.\n$$"


def test_single_pass_normalizes_section_markdown(monkeypatch):
    async def fake_synth(source: str, instructions):
        from mathai.math_notes.artifacts import NoteSection

        return _SynthesisOutput(
            markdown="$inline$",
            sections=[
                NoteSection(
                    heading="Stokes",
                    markdown=r"\[ \oint_C F\cdot dr \]",
                    concepts=["stokes"],
                )
            ],
            validation_attempts=1,
        )

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)

    syn = asyncio.run(synthesize_note(_TRANSCRIPT, _PAGES, "SYS", plan=None))
    assert syn is not None
    assert len(syn.sections) == 1
    assert syn.sections[0].markdown == "$$\n\\oint_C F\\cdot dr\n$$"


# ---- segmented synthesis normalizes every section + the stitched doc ------

def _two_topic_plan() -> SynthesisPlan:
    return SynthesisPlan(
        topics=[
            PlanTopic(title="Greens theorem", kind="concept"),
            PlanTopic(title="Line integrals", kind="exercise"),
        ],
        depth_tier="deep",
        suggested_sections=2,
    )


def test_segmented_normalizes_sections_and_stitched_markdown(monkeypatch):
    # One segment slips into `\[…\]`, another into a glued multi-line `$$`; both
    # the stored sections AND the deterministically-stitched flat markdown must
    # end up clean (no legacy delimiters, every `$$` fenced).
    async def fake_synth(source: str, instructions):
        if "Greens theorem" in source:
            return _SynthesisOutput(
                markdown=r"\[ \oint_C P\,dx + Q\,dy = \iint_D (Q_x - P_y) \]",
                concepts=["greens theorem"],
                validation_attempts=1,
            )
        return _SynthesisOutput(
            markdown="$$\\int_C F\\cdot dr = 0, \\qquad\nC \\text{ closed}.$$",
            concepts=["line integrals"],
            validation_attempts=1,
        )

    async def fake_reduce(prompt, instructions):
        return _ReduceOutput(ordered_indices=[0, 1], summary="two topics", concepts=["a", "b"])

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)
    monkeypatch.setattr(workflow, "_run_reduce_agent", fake_reduce)

    syn = asyncio.run(
        synthesize_note(_TRANSCRIPT, _PAGES, "SYS", plan=_two_topic_plan())
    )
    assert syn is not None
    assert len(syn.sections) == 2
    # Every section is clean (no legacy delimiters, no glued `$$`)...
    for sec in syn.sections:
        for bad in (r"\[", r"\]", r"\(", r"\)"):
            assert bad not in sec.markdown
        assert "$$i" not in sec.markdown.replace("$$\n", "")  # no glued opener
    assert syn.sections[0].markdown == "$$\n\\oint_C P\\,dx + Q\\,dy = \\iint_D (Q_x - P_y)\n$$"
    assert syn.sections[1].markdown == "$$\n\\int_C F\\cdot dr = 0, \\qquad\nC \\text{ closed}.\n$$"
    # ...and so is the stitched flat document.
    assert syn.markdown is not None
    for bad in (r"\[", r"\]", r"\(", r"\)"):
        assert bad not in syn.markdown
    assert "## Greens theorem" in syn.markdown
    assert "$$\n\\oint_C P\\,dx + Q\\,dy = \\iint_D (Q_x - P_y)\n$$" in syn.markdown
    assert "$$\n\\int_C F\\cdot dr = 0, \\qquad\nC \\text{ closed}.\n$$" in syn.markdown

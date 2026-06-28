r"""Tests for the deterministic delimiter normalizer in the synthesis path (#33).

Two layers:

* The pure helper `mathai.math_notes.text.convert_delimiters` — converts the
  four legacy KaTeX-style delimiters to canonical `$`/`$$` and is idempotent.
* The synthesis path (`synthesize_note`) applying it — even when the (stubbed)
  model emits `\[…\]` / `\(…\)` despite the prompt, NO persisted markdown (flat,
  per-section, or stitched) carries a legacy delimiter. This is the durable
  guard: the renderer (remark-math) only handles `$`/`$$`, so a slipped `\[…\]`
  would otherwise render raw and still pass the old document-mode validator.

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
from mathai.math_notes.text import convert_delimiters
from mathai.math_notes.workflow import _ReduceOutput, _SynthesisOutput, synthesize_note


# ---- pure helper ---------------------------------------------------------

def test_convert_inline_and_display_delimiters():
    src = r"Let \(x\) be real. \[ x^2 \ge 0 \]"
    assert convert_delimiters(src) == "Let $x$ be real. $$ x^2 \\ge 0 $$"


def test_convert_is_idempotent():
    src = r"## H\nLet \(G\) be a group. \[ gH = Hg \]"
    once = convert_delimiters(src)
    assert convert_delimiters(once) == once
    assert "\\(" not in once and "\\[" not in once and "\\)" not in once and "\\]" not in once


def test_already_dollar_form_is_noop():
    src = "Inline $a+b$ and display\n$$\nc=d\n$$"
    assert convert_delimiters(src) == src


def test_convert_handles_empty_and_none():
    assert convert_delimiters("") == ""
    assert convert_delimiters(None) is None  # type: ignore[arg-type]


# ---- single-pass synthesis normalizes the model's output -----------------

_TRANSCRIPT = "Did one exercise on the divergence theorem."
_PAGES = [NotePage(page_index=0, image_ref="media/0/p.jpg", raw_text="div F = ...")]


def test_single_pass_normalizes_slipped_delimiters(monkeypatch):
    # The model defies the prompt and emits display math as `\[…\]` plus an
    # inline `\(…\)`. Synthesis must persist canonical `$`/`$$` regardless.
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
    # No legacy delimiter survives; the math is now `$`/`$$`.
    for bad in (r"\[", r"\]", r"\(", r"\)"):
        assert bad not in syn.markdown
    assert "$$ \\iint_S F\\cdot n\\,dS $$" in syn.markdown
    assert "for a region $R$." in syn.markdown


def test_single_pass_normalizes_section_markdown(monkeypatch):
    # A moderately multi-topic single pass can return `sections`; those are
    # normalized too (via `_normalize_sections`).
    async def fake_synth(source: str, instructions):
        from mathai.math_notes.artifacts import NoteSection

        return _SynthesisOutput(
            markdown="$ok$",
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
    assert r"\[" not in syn.sections[0].markdown
    assert "$$ \\oint_C F\\cdot dr $$" == syn.sections[0].markdown


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
    # One segment slips into `\[…\]`; both the stored section AND the
    # deterministically-stitched flat markdown must end up clean.
    async def fake_synth(source: str, instructions):
        if "Greens theorem" in source:
            return _SynthesisOutput(
                markdown=r"By the theorem, \[ \oint_C P\,dx + Q\,dy = \iint_D (Q_x - P_y) \].",
                concepts=["greens theorem"],
                validation_attempts=1,
            )
        return _SynthesisOutput(
            markdown=r"A line integral \( \int_C F\cdot dr \).",
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
    # Every section is clean...
    for sec in syn.sections:
        for bad in (r"\[", r"\]", r"\(", r"\)"):
            assert bad not in sec.markdown
    # ...and so is the stitched flat document.
    assert syn.markdown is not None
    for bad in (r"\[", r"\]", r"\(", r"\)"):
        assert bad not in syn.markdown
    assert "$$ \\oint_C P\\,dx + Q\\,dy = \\iint_D (Q_x - P_y) $$" in syn.markdown
    assert "$ \\int_C F\\cdot dr $" in syn.markdown

"""Scaling eval — prove synthesis output magnitude tracks input magnitude (#21).

Epic #14's whole claim is that the synthesizer stops "reacting constantly": a
light single-topic note and a dense multi-topic one should produce *differently
sized* output. This is the repeatable, offline check of that claim and a
regression guard on the **measurement** that proves it.

It builds three representative `DailyNoteArtifact`s — a light/brief note, a
typical/standard note, and a dense/deep multi-topic note — each carrying the
synthesis a scaling synthesizer would have produced, and asserts:

  * input magnitude rises light → standard → dense (the `NoteMagnitude` tier
    ladder), and
  * output magnitude rises with it — strictly **more** markdown chars, **more**
    sections, **more** distinct concepts — i.e. the dense note yields
    proportionally more, and
  * the reporter's corpus-level `scaling_verdict` reads the whole set as
    ``scales`` (monotonic up the tier ladder, non-negative input/output rank
    correlation).

The fixtures stand in for real pipeline output (running the live Opus pass needs
an Anthropic key + the math-ui validator, out of scope for a unit test), so this
guards the metric extraction + scaling check. The companion
`scripts/report_magnitude_scaling.py` runs the *same* pure functions over a real
corpus to prove it on production data.

Run from the repo root in the default-runtime venv::

    PYTHONPATH="../ai-platform/packages/core/src:packages/math-notes/src" \
      ../ai-platform/.venv/bin/python -m pytest \
      packages/math-notes/tests/test_magnitude_scaling_eval.py
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

from mathai.math_notes.artifacts import (
    DailyNoteArtifact,
    NoteMagnitude,
    NotePage,
    NoteSection,
    NoteSynthesis,
)

# The reporter lives in scripts/ (not an importable package) — load it by path,
# the same way test_note_magnitude.py loads its migration. The test exercises
# the EXACT pure functions the operator-facing reporter uses.
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "report_magnitude_scaling.py"
_spec = importlib.util.spec_from_file_location("report_magnitude_scaling", _SCRIPT)
assert _spec and _spec.loader
report = importlib.util.module_from_spec(_spec)
# Register before exec so the module's @dataclass can resolve its own (PEP 563,
# stringized) annotations via sys.modules during class processing.
sys.modules[_spec.name] = report
_spec.loader.exec_module(report)


# --- fixtures: three notes spanning the magnitude ladder ----------------------


def _page(i: int, chars: int) -> NotePage:
    return NotePage(page_index=i, image_ref=f"media/{i}/p.jpg", raw_text="p" * chars)


def _light_note() -> DailyNoteArtifact:
    """A terse single-exercise note: short transcript, no photos, flat synthesis."""
    transcript = "Quick note: practised one limit, " + "x" * 1500
    mag = NoteMagnitude.from_signals(transcript=transcript, pages=[])
    synthesis = NoteSynthesis(
        markdown="Worked a single limit: $\\lim_{x\\to 0}\\frac{\\sin x}{x}=1$.",
        concepts=["limits"],
        summary="One limit.",
        depth_tier=mag.density_tier,
        magnitude=mag,
        model_used="claude-opus-4-8",
        validation_attempts=1,
    )
    return DailyNoteArtifact(
        note_date=date(2026, 6, 1),
        transcript=transcript,
        magnitude=mag,
        synthesis=synthesis,
        schema_version=3,
    )


def _standard_note() -> DailyNoteArtifact:
    """A typical session: ~1 page, a couple of topics, a modest write-up."""
    transcript = "Studied derivatives today. " + "y" * 4000
    pages = [_page(0, 1500)]
    mag = NoteMagnitude.from_signals(transcript=transcript, pages=pages)
    synthesis = NoteSynthesis(
        markdown=(
            "## Derivatives\n\nReviewed the power rule and the chain rule. "
            + "The derivative of $x^n$ is $n x^{n-1}$. " * 8
        ),
        concepts=["derivatives", "power rule", "chain rule"],
        summary="A standard derivatives session.",
        sections=[
            NoteSection(
                heading="Power rule",
                markdown="$\\frac{d}{dx}x^n = n x^{n-1}$. " * 6,
                concepts=["power rule"],
            ),
            NoteSection(
                heading="Chain rule",
                markdown="$(f\\circ g)'(x) = f'(g(x))g'(x)$. " * 6,
                concepts=["chain rule"],
            ),
        ],
        depth_tier=mag.density_tier,
        magnitude=mag,
        model_used="claude-opus-4-8",
        validation_attempts=2,
    )
    return DailyNoteArtifact(
        note_date=date(2026, 6, 2),
        transcript=transcript,
        pages=pages,
        image_refs=["media/0/p.jpg"],
        magnitude=mag,
        synthesis=synthesis,
        schema_version=3,
    )


def _dense_note() -> DailyNoteArtifact:
    """A dense, multi-topic, multi-page session — the synthesizer should go big."""
    transcript = "Long day, covered a lot. " + "z" * 7000
    pages = [_page(i, 3000) for i in range(4)]
    mag = NoteMagnitude.from_signals(transcript=transcript, pages=pages)
    sections = [
        NoteSection(
            heading=f"Topic {i}",
            markdown=f"Detailed treatment of topic {i}. " * 30 + f"$T_{i} = \\int_0^1 f_{i}$. ",
            concepts=[f"concept-{i}-a", f"concept-{i}-b"],
        )
        for i in range(5)
    ]
    synthesis = NoteSynthesis(
        markdown="# Full session\n\n" + "Comprehensive multi-topic write-up. " * 40,
        concepts=["measure theory", "integration", "topology", "compactness"],
        summary="A dense, multi-topic study session spanning several hours.",
        sections=sections,
        depth_tier=mag.density_tier,
        magnitude=mag,
        model_used="claude-opus-4-8",
        validation_attempts=3,
    )
    return DailyNoteArtifact(
        note_date=date(2026, 6, 3),
        transcript=transcript,
        pages=pages,
        image_refs=[f"media/{i}/p.jpg" for i in range(4)],
        magnitude=mag,
        synthesis=synthesis,
        schema_version=3,
    )


@pytest.fixture
def light():
    return _light_note()


@pytest.fixture
def standard():
    return _standard_note()


@pytest.fixture
def dense():
    return _dense_note()


# --- input magnitude actually differs ----------------------------------------


def test_fixtures_span_the_density_ladder(light, standard, dense):
    # The premise of the eval: the three notes really do sit on different rungs.
    assert light.magnitude.density_tier == "brief"
    assert standard.magnitude.density_tier == "standard"
    assert dense.magnitude.density_tier == "deep"


def test_input_score_is_strictly_increasing(light, standard, dense):
    scores = [report.note_metrics(n).input_score for n in (light, standard, dense)]
    assert scores[0] < scores[1] < scores[2]


# --- the headline claim: output magnitude tracks input -----------------------


def test_dense_note_yields_proportionally_more(light, dense):
    lo = report.note_metrics(light)
    hi = report.note_metrics(dense)

    # More sections, more total written chars, more distinct concepts.
    assert hi.out_section_count > lo.out_section_count
    assert hi.out_total_chars > lo.out_total_chars
    assert hi.out_concept_count > lo.out_concept_count

    # "Proportionally" more — not a marginal bump. The dense note should produce
    # several times the output volume of the light one.
    assert hi.out_total_chars >= 3 * max(lo.out_total_chars, 1)
    assert hi.out_concept_count >= 3 * max(lo.out_concept_count, 1)


def test_output_magnitude_is_monotonic_across_all_three(light, standard, dense):
    ms = [report.note_metrics(n) for n in (light, standard, dense)]
    chars = [m.out_total_chars for m in ms]
    sections = [m.out_section_count for m in ms]
    concepts = [m.out_concept_count for m in ms]
    # Strictly increasing on every output dimension as input magnitude rises.
    assert chars[0] < chars[1] < chars[2]
    assert sections[0] < sections[1] < sections[2]
    assert concepts[0] < concepts[1] < concepts[2]


# --- effort metrics are captured ---------------------------------------------


def test_effort_metrics_are_visible(light, dense):
    lo = report.note_metrics(light)
    hi = report.note_metrics(dense)
    # validation_attempts surfaced straight off the synthesis.
    assert lo.validation_attempts == 1
    assert hi.validation_attempts == 3
    # section count is a proxy for model calls (base pass + one per section);
    # a denser note implies more effort.
    assert hi.effort_calls_proxy > lo.effort_calls_proxy
    assert hi.effort_calls_proxy == 1 + hi.out_section_count
    # model + depth tier are recorded for the report.
    assert hi.model_used == "claude-opus-4-8"
    assert hi.depth_tier == "deep"


def test_total_chars_counts_flat_markdown_plus_sections(standard):
    m = report.note_metrics(standard)
    syn = standard.synthesis
    expected_flat = len(syn.markdown or "")
    expected_sections = sum(len(s.markdown) for s in syn.sections)
    assert m.out_markdown_chars == expected_flat
    assert m.out_section_chars == expected_sections
    assert m.out_total_chars == expected_flat + expected_sections


def test_distinct_concepts_dedupes_note_and_section_concepts():
    # Note-level and section-level concept lists overlap; the count is distinct.
    mag = NoteMagnitude.from_signals(transcript="x" * 100)
    syn = NoteSynthesis(
        markdown="m",
        concepts=["Limits", "derivatives"],
        sections=[
            NoteSection(heading="A", markdown="x", concepts=["limits"]),  # dup (case)
            NoteSection(heading="B", markdown="y", concepts=["integration"]),  # new
        ],
        magnitude=mag,
    )
    note = DailyNoteArtifact(note_date=date(2026, 6, 4), synthesis=syn, schema_version=3)
    # {limits, derivatives, integration} = 3 distinct.
    assert report.note_metrics(note).out_concept_count == 3


# --- corpus-level verdict reads "scales" -------------------------------------


def test_scaling_verdict_reports_scales(light, standard, dense):
    metrics = [report.note_metrics(n) for n in (light, standard, dense)]
    verdict = report.scaling_verdict(metrics)

    assert verdict["verdict"] == "scales"
    assert verdict["tiers_present"] == ["brief", "standard", "deep"]
    # Output is monotonic non-decreasing up the tier ladder on every dimension.
    mono = verdict["monotonic_non_decreasing"]
    assert mono["total_chars"] and mono["sections"] and mono["concepts"]
    # Input score and output chars are perfectly rank-correlated here.
    assert verdict["spearman_input_vs_output_chars"] == 1.0
    assert verdict["n_synthesized"] == 3
    assert verdict["n_without_synthesis"] == 0


def test_constant_output_is_caught_as_regression():
    # The guard has teeth: a synthesizer that emits the SAME output regardless of
    # input (the bug epic #14 fixes) must NOT read as "scales". Here a brief and a
    # deep note carry identical output → the rank correlation collapses.
    light_mag = NoteMagnitude.from_signals(transcript="x" * 1000, pages=[])
    deep_mag = NoteMagnitude.from_signals(
        transcript="z" * 7000, pages=[_page(i, 3000) for i in range(4)]
    )
    assert light_mag.density_tier == "brief"
    assert deep_mag.density_tier == "deep"

    flat = NoteSynthesis(
        markdown="identical blob " * 20,
        concepts=["a", "b"],
        sections=[NoteSection(heading="X", markdown="same", concepts=["a"])],
        validation_attempts=1,
    )
    notes = [
        DailyNoteArtifact(note_date=date(2026, 6, 5), magnitude=light_mag,
                          synthesis=flat.model_copy(deep=True), schema_version=3),
        DailyNoteArtifact(note_date=date(2026, 6, 6), magnitude=deep_mag,
                          synthesis=flat.model_copy(deep=True), schema_version=3),
    ]
    verdict = report.scaling_verdict([report.note_metrics(n) for n in notes])
    # Two tiers present, identical output → flat means, undefined correlation:
    # the verdict must not falsely claim it scales.
    assert verdict["verdict"] != "scales"


def test_verdict_inconclusive_with_too_little_data(light):
    # A single note can't prove scaling — the verdict is honest about that.
    verdict = report.scaling_verdict([report.note_metrics(light)])
    assert verdict["verdict"] == "inconclusive"


# --- notes without synthesis don't pollute the verdict -----------------------


def test_unsynthesized_notes_are_excluded_from_aggregates(light, standard, dense):
    # A note whose synthesis failed (None) has zero output — it isn't evidence
    # about scaling and must be reported separately, not aggregated.
    failed = DailyNoteArtifact(
        note_date=date(2026, 6, 7),
        transcript="z" * 7000,
        pages=[_page(i, 3000) for i in range(4)],
        magnitude=_dense_note().magnitude,
        synthesis=None,
        schema_version=3,
    )
    metrics = [report.note_metrics(n) for n in (light, standard, dense, failed)]
    verdict = report.scaling_verdict(metrics)
    assert verdict["n_synthesized"] == 3
    assert verdict["n_without_synthesis"] == 1
    # The failed note's tier (deep) aggregate still reflects only the real one.
    assert verdict["by_tier"]["deep"]["count"] == 1
    assert verdict["verdict"] == "scales"


# --- old rows (no stored magnitude) still measure ----------------------------


def test_metrics_recompute_magnitude_for_legacy_rows():
    # A pre-S1 row carries no `magnitude`; the reporter re-derives it from the
    # stored transcript/pages so legacy notes still appear in the report.
    note = DailyNoteArtifact(
        note_date=date(2026, 1, 1),
        transcript="legacy " * 1000,
        pages=[_page(0, 2000), _page(1, 2000)],
        synthesis=NoteSynthesis(markdown="recovered", concepts=["x"]),
        schema_version=2,  # pre-magnitude
    )
    assert note.magnitude is None
    m = report.note_metrics(note)
    assert m.in_transcript_chars == len(note.transcript)
    assert m.in_page_count == 2
    assert m.in_density_tier in ("brief", "standard", "deep")

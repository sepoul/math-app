#!/usr/bin/env python
"""Report input-vs-output magnitude across recent `daily_note` artifacts (#21).

Epic #14 makes synthesis *scale* with how much a note contains. This reporter
makes that claim **measurable instead of vibes**: for each note it derives, from
data already on the row, three things and lines them up —

  * **input magnitude**  — the note's `NoteMagnitude` (transcript chars, page
    count, page chars, `density_tier`, audio duration). Recomputed from the
    stored `transcript`/`pages` for rows written before S1 (no model call).
  * **output magnitude** — what synthesis *produced*: total written chars (flat
    `markdown` + every `NoteSection.markdown`), section count, and distinct
    concept count (note-level ∪ per-section).
  * **effort**           — `validation_attempts`, the synthesis `depth_tier` and
    `model_used`, and the section count as a coarse proxy for model calls (a
    map-reduce synthesis writes roughly one pass + one per section).

It then asks the headline question — *does output track input?* — by bucketing
notes into their input `density_tier` (brief|standard|deep) and checking whether
mean output magnitude is **monotonic non-decreasing** up that ladder, plus a
Spearman rank correlation between the fused input score and total output chars.
The verdict (`scales` / `regresses` / `inconclusive`) is the repeatable proof
the synthesizer "reacts" rather than emitting a constant-shape blob.

**Purely read-only and additive** — it never mutates an artifact (no `--apply`
needed) and edits no existing source; it derives everything post-hoc from the
produced `DailyNoteArtifact` / `NoteSynthesis` / `NoteMagnitude`. It is pure
(no Anthropic key, no math-ui validator) and idempotent (a re-run on the same
store yields the same report). The pure metric functions are imported by
`tests/test_magnitude_scaling_eval.py`, which proves the *measurement* on
constructed fixtures; this script proves it on a *real* corpus.

It mirrors the sibling `scripts/migrate_note_magnitude.py`: `ArtifactService`
over `make_backend()`, env-selected backend, `--limit`, and an optional JSON
report. Run it in the **default-runtime** venv with the platform + package on
PYTHONPATH, pointed at the target backend. Example::

    BACKEND=supabase SUPABASE_URL=... SUPABASE_SECRET_KEY=... \
    SUPABASE_CONNECTION_STRING=... \
    PYTHONPATH="../ai-platform/packages/core/src:packages/math-notes/src" \
      ../ai-platform/.venv/bin/python \
      packages/math-notes/scripts/report_magnitude_scaling.py            # stdout
    # ... optionally also dump the full JSON:
      ... report_magnitude_scaling.py --report magnitude-scaling-report.json

`make_backend()` resolves `BACKEND`; the supabase backend reads `SUPABASE_URL`
/ `SUPABASE_SECRET_KEY` / `SUPABASE_CONNECTION_STRING` and `SUPABASE_SCHEMA`
(unset = `public`/prod).
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from mathai.math_notes.artifacts import (
    DailyNoteArtifact,
    DensityTier,
    NoteMagnitude,
)

# --- fused magnitude scores (transparent, observability-only) ----------------
#
# These weights are *not* the `density_tier` thresholds (those live in
# artifacts.py); they are a single scalar per axis so the report can correlate
# input against output. `page_count` is weighted heavily on the input side
# because it is the strongest study-scope proxy (epic #14) — one page stands in
# for ~this many "content chars" of scope.
_INPUT_PAGE_CHAR_EQUIV = 3500.0

# Tier ordering, brief < standard < deep, for monotonicity checks.
_TIER_ORDER: tuple[DensityTier, ...] = ("brief", "standard", "deep")


def tier_rank(tier: Optional[str]) -> int:
    """Ordinal rank of a density/depth tier (brief=0, standard=1, deep=2).

    Unknown / None sorts before `brief` (-1) so it never masquerades as data."""
    try:
        return _TIER_ORDER.index(tier)  # type: ignore[arg-type]
    except ValueError:
        return -1


def input_magnitude_score(mag: NoteMagnitude) -> float:
    """A single fused input-magnitude scalar (page_count-weighted)."""
    return (
        float(mag.transcript_chars)
        + float(mag.page_chars)
        + float(mag.page_count) * _INPUT_PAGE_CHAR_EQUIV
    )


def _note_magnitude(note: DailyNoteArtifact) -> NoteMagnitude:
    """The note's stored magnitude, or one recomputed from its raw material.

    New ingests stamp `magnitude` (schema_version 3); older rows don't. For those
    we re-derive it from the stored `transcript` + `pages` with the same pure
    fusion the live node uses — no model call, no duration (not recoverable)."""
    if note.magnitude is not None:
        return note.magnitude
    return NoteMagnitude.from_signals(
        transcript=note.transcript,
        pages=note.pages,
        image_ref_count=len(note.image_refs),
    )


def _distinct_concepts(note: DailyNoteArtifact) -> int:
    """Count distinct concepts across note-level + per-section lists (case-insensitive)."""
    syn = note.synthesis
    if syn is None:
        return 0
    seen: set[str] = set()
    for concept in syn.concepts:
        key = str(concept).strip().lower()
        if key:
            seen.add(key)
    for section in syn.sections:
        for concept in section.concepts:
            key = str(concept).strip().lower()
            if key:
                seen.add(key)
    return len(seen)


@dataclass
class NoteMetrics:
    """Per-note input/output/effort metrics derived post-hoc from the artifact."""

    artifact_id: str
    note_date: str
    # --- input magnitude (what the note contained) ---
    in_transcript_chars: int
    in_page_count: int
    in_page_chars: int
    in_density_tier: str
    in_duration_seconds: Optional[float]
    input_score: float
    # --- output magnitude (what synthesis produced) ---
    has_synthesis: bool
    out_markdown_chars: int
    out_section_chars: int
    out_total_chars: int
    out_section_count: int
    out_concept_count: int
    # --- effort ---
    validation_attempts: int
    effort_calls_proxy: int  # ~ one synthesis pass + one per section (map-reduce)
    depth_tier: Optional[str]
    model_used: Optional[str]


def note_metrics(note: DailyNoteArtifact) -> NoteMetrics:
    """Derive the magnitude/effort metrics record for one note (pure, read-only)."""
    mag = _note_magnitude(note)
    syn = note.synthesis

    markdown_chars = len(syn.markdown or "") if syn else 0
    section_chars = sum(len(s.markdown or "") for s in syn.sections) if syn else 0
    section_count = len(syn.sections) if syn else 0

    return NoteMetrics(
        artifact_id=str(note.artifact_id),
        note_date=str(note.note_date),
        in_transcript_chars=mag.transcript_chars,
        in_page_count=mag.page_count,
        in_page_chars=mag.page_chars,
        in_density_tier=mag.density_tier,
        in_duration_seconds=mag.duration_seconds,
        input_score=input_magnitude_score(mag),
        has_synthesis=syn is not None,
        out_markdown_chars=markdown_chars,
        out_section_chars=section_chars,
        out_total_chars=markdown_chars + section_chars,
        out_section_count=section_count,
        out_concept_count=_distinct_concepts(note),
        validation_attempts=(syn.validation_attempts if syn else 0),
        effort_calls_proxy=1 + section_count,
        depth_tier=(syn.depth_tier if syn else None),
        model_used=(syn.model_used if syn else None),
    )


# --- corpus-level scaling check ----------------------------------------------


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _is_monotonic_non_decreasing(values: list[float]) -> bool:
    """True if the sequence never decreases (a flat sequence still counts)."""
    return all(b >= a for a, b in zip(values, values[1:]))


def spearman(xs: list[float], ys: list[float]) -> Optional[float]:
    """Spearman rank correlation of two equal-length sequences (pure Python).

    Returns `None` when it is undefined — fewer than two points, or either
    sequence constant (zero rank variance). Ties get average ranks."""
    n = len(xs)
    if n < 2 or len(ys) != n:
        return None

    def _ranks(values: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: values[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and values[order[j + 1]] == values[order[i]]:
                j += 1
            avg = (i + j) / 2.0  # average rank for the tie group
            for k in range(i, j + 1):
                ranks[order[k]] = avg
            i = j + 1
        return ranks

    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = _mean(rx), _mean(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den_x = sum((a - mx) ** 2 for a in rx)
    den_y = sum((b - my) ** 2 for b in ry)
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y) ** 0.5


def aggregate_by_tier(metrics: list[NoteMetrics]) -> dict[str, dict]:
    """Mean output magnitude / effort per *input* density tier (synthesized notes).

    Only notes that actually produced a synthesis are aggregated — a failed/empty
    synthesis isn't evidence about scaling. Keyed by input `density_tier`."""
    buckets: dict[str, list[NoteMetrics]] = {}
    for m in metrics:
        if not m.has_synthesis:
            continue
        buckets.setdefault(m.in_density_tier, []).append(m)

    out: dict[str, dict] = {}
    for tier, ms in buckets.items():
        out[tier] = {
            "count": len(ms),
            "mean_input_score": round(_mean([m.input_score for m in ms]), 1),
            "mean_total_chars": round(_mean([m.out_total_chars for m in ms]), 1),
            "mean_sections": round(_mean([m.out_section_count for m in ms]), 2),
            "mean_concepts": round(_mean([m.out_concept_count for m in ms]), 2),
            "mean_validation_attempts": round(
                _mean([m.validation_attempts for m in ms]), 2
            ),
        }
    return out


def scaling_verdict(metrics: list[NoteMetrics]) -> dict:
    """Does output magnitude track input magnitude across the corpus?

    Headline check: bucket synthesized notes by input `density_tier` and verify
    mean total output chars / sections / concepts are monotonic non-decreasing
    up the brief→standard→deep ladder. Plus a Spearman rank correlation between
    each note's fused input score and its total output chars.

    `verdict`:
      * ``inconclusive`` — fewer than 2 synthesized notes, or fewer than 2 input
        tiers represented (can't compare across magnitudes).
      * ``scales``       — output **grows** up the tier ladder (mean total chars
        monotonic non-decreasing AND the top tier strictly exceeds the bottom)
        AND the input/output correlation is non-negative.
      * ``regresses``    — there is data to compare, but output does NOT grow
        with input (e.g. a constant-shape "reacts uniformly" synthesizer).
    """
    synth = [m for m in metrics if m.has_synthesis]
    by_tier = aggregate_by_tier(metrics)
    present = [t for t in _TIER_ORDER if t in by_tier]

    rho = spearman(
        [m.input_score for m in synth], [float(m.out_total_chars) for m in synth]
    )

    ordered = [by_tier[t] for t in present]
    chars_means = [b["mean_total_chars"] for b in ordered]
    monotonic = {
        "total_chars": _is_monotonic_non_decreasing(chars_means),
        "sections": _is_monotonic_non_decreasing([b["mean_sections"] for b in ordered]),
        "concepts": _is_monotonic_non_decreasing([b["mean_concepts"] for b in ordered]),
    }
    # Output must actually *grow*, not merely never-decrease — a flat curve is
    # exactly the constant-output bug we're guarding against.
    grows = bool(chars_means) and chars_means[-1] > chars_means[0]

    if len(synth) < 2 or len(present) < 2:
        verdict = "inconclusive"
    elif monotonic["total_chars"] and grows and (rho is None or rho >= 0):
        verdict = "scales"
    else:
        verdict = "regresses"

    return {
        "n_synthesized": len(synth),
        "n_without_synthesis": len(metrics) - len(synth),
        "tiers_present": present,
        "by_tier": by_tier,
        "monotonic_non_decreasing": monotonic,
        "output_grows_across_tiers": grows,
        "spearman_input_vs_output_chars": (round(rho, 3) if rho is not None else None),
        "verdict": verdict,
    }


# --- CLI ---------------------------------------------------------------------


def _build_service():
    """ArtifactService over the env-selected backend, with the math_notes registry."""
    from ai_platform.jobs.artifact_service import ArtifactService
    from ai_platform.workspace.storage.backends import make_backend
    from mathai.math_notes.artifacts import MATH_NOTES_ARTIFACTS

    backend = make_backend()
    return ArtifactService(backend.artifact_repo, registry=MATH_NOTES_ARTIFACTS)


def _fmt_dur(seconds: Optional[float]) -> str:
    return f"{seconds:.0f}s" if seconds else "-"


def _print_table(metrics: list[NoteMetrics]) -> None:
    header = (
        f"{'date':<12} {'tier':<9} {'t.chars':>8} {'pg':>3} {'pg.chars':>8} "
        f"{'out.chars':>9} {'sec':>4} {'conc':>5} {'val':>4} {'depth':<9} model"
    )
    print(header)
    print("-" * len(header))
    for m in metrics:
        depth = m.depth_tier or "-"
        model = (m.model_used or "-").split("/")[-1]
        out = m.out_total_chars if m.has_synthesis else 0
        marker = "" if m.has_synthesis else "  (no synthesis)"
        print(
            f"{m.note_date:<12} {m.in_density_tier:<9} {m.in_transcript_chars:>8} "
            f"{m.in_page_count:>3} {m.in_page_chars:>8} {out:>9} "
            f"{m.out_section_count:>4} {m.out_concept_count:>5} "
            f"{m.validation_attempts:>4} {depth:<9} {model}{marker}"
        )


def _print_verdict(verdict: dict) -> None:
    print("\n=== scaling check: does output track input? ===")
    print(
        f"synthesized notes: {verdict['n_synthesized']} "
        f"(+{verdict['n_without_synthesis']} without synthesis); "
        f"input tiers present: {verdict['tiers_present'] or '(none)'}"
    )
    for tier in verdict["tiers_present"]:
        b = verdict["by_tier"][tier]
        print(
            f"  {tier:<9} n={b['count']:<3} "
            f"mean_out_chars={b['mean_total_chars']:<8} "
            f"mean_sections={b['mean_sections']:<5} "
            f"mean_concepts={b['mean_concepts']:<5} "
            f"mean_val={b['mean_validation_attempts']}"
        )
    mono = verdict["monotonic_non_decreasing"]
    print(
        "  monotonic up brief→standard→deep: "
        f"chars={mono['total_chars']}, sections={mono['sections']}, concepts={mono['concepts']}"
    )
    rho = verdict["spearman_input_vs_output_chars"]
    print(f"  spearman(input_score, output_chars) = {rho if rho is not None else 'n/a'}")
    print(f"  VERDICT: {verdict['verdict'].upper()}")


def _main(args: argparse.Namespace) -> int:
    service = _build_service()

    notes = [
        n for n in service.list_by_type("daily_note") if isinstance(n, DailyNoteArtifact)
    ]
    notes.sort(key=lambda n: n.note_date)
    if args.limit is not None:
        notes = notes[-args.limit :]  # the most recent N

    print(f"scanned {len(notes)} daily_note artifact(s)\n")
    metrics = [note_metrics(n) for n in notes]
    if metrics:
        _print_table(metrics)

    verdict = scaling_verdict(metrics)
    _print_verdict(verdict)

    if args.report:
        report = {
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "backend": os.environ.get("BACKEND"),
            "scanned": len(notes),
            "notes": [asdict(m) for m in metrics],
            "scaling": verdict,
        }
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nreport → {args.report}")

    # Non-zero exit when the corpus has enough data and does NOT scale, so an
    # operator / CI can gate on the proof. `inconclusive` (too little data) and
    # `scales` both pass.
    return 1 if verdict["verdict"] == "regresses" else 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--limit", type=int, default=None, help="Only the most recent N notes.")
    p.add_argument(
        "--report",
        default=None,
        help="Optional path to also dump the full JSON report (stdout is always printed).",
    )
    return _main(p.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())

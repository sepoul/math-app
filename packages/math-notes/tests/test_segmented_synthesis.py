"""Tests for the adaptive / segmented synthesis pass (issue #18 / epic #14, S4).

Covers the plan-driven map-reduce path and its single-pass fallback:

* `_should_segment` — when the S3 plan warrants fanning out vs. one pass.
* `_note_context_line` — the `NOTE CONTEXT` calibration line wired into the prompt.
* `_compose_synthesis_prompt` — directives / context / focus ordering.
* The segmented path — multiple topics → multiple validated sections, stitched
  into one document with a note-level summary, deduped concepts, embedded
  magnitude, and summed validation attempts.
* Best-effort degrade — a light note keeps the single pass; a map-phase failure
  that leaves < 2 sections falls back to a single pass; a reduce failure degrades
  to a deterministic stitch without discarding the validated map work.
* The `SynthesizeNoteStep` node threads `state.plan` into synthesis.

The model calls (`_run_synthesis_agent` / `_run_reduce_agent`) are stubbed, so
nothing here touches the network, an API key, or the math-ui validator.

Run from the repo root in the default-runtime venv::

    PYTHONPATH="packages/math-notes/src:../ai-platform/packages/core/src:../ai-platform/packages/worker/src" \
      ../ai-platform/.venv/bin/python -m pytest \
      packages/math-notes/tests/test_segmented_synthesis.py
"""
from __future__ import annotations

import asyncio

from pydantic_graph import End, GraphRunContext

from mathai.math_notes import workflow
from mathai.math_notes.artifacts import (
    NoteMagnitude,
    NotePage,
    PlanTopic,
    SynthesisPlan,
)
from mathai.math_notes.state import MathNotesState
from mathai.math_notes.workflow import (
    SYNTHESIS_MODEL,
    MathNotesWorkflowDependencies,
    SynthesizeNoteStep,
    _compose_synthesis_prompt,
    _note_context_line,
    _should_segment,
    _SynthesisOutput,
    _ReduceOutput,
    synthesize_note,
)


class _FakeLog:
    """Captures log lines, with a `for_stage` shim (mirrors test_synthesis_plan)."""

    def __init__(self) -> None:
        self.infos: list[str] = []
        self.warnings: list[str] = []

    def for_stage(self, _name: str) -> "_FakeLog":
        return self

    async def info(self, msg: str) -> None:
        self.infos.append(msg)

    async def warning(self, msg: str) -> None:
        self.warnings.append(msg)


def _page(i: int, text: str) -> NotePage:
    return NotePage(page_index=i, image_ref=f"media/{i}/p.jpg", raw_text=text)


def _two_topic_plan() -> SynthesisPlan:
    return SynthesisPlan(
        topics=[
            PlanTopic(title="Integration by parts", kind="exercise", span_hint="opening"),
            PlanTopic(title="Series convergence", kind="concept", span_hint="pages 1-2"),
        ],
        depth_tier="deep",
        suggested_sections=2,
        segment_boundaries=["moves on to convergence"],
        study_scope_hint="spent the afternoon, ~4 hours",
        rationale="Two distinct threads.",
        model_used="claude-haiku-4-5",
    )


# A multi-topic transcript + a page — enough source for synthesis.
_TRANSCRIPT = (
    "Worked an integration by parts exercise, then series convergence all afternoon."
)
_PAGES = [_page(0, "u dv = uv - v du")]


# ---- _should_segment -----------------------------------------------------

def test_should_segment_for_deep_multi_topic_plan():
    assert _should_segment(_two_topic_plan()) is True


def test_should_segment_false_without_plan():
    assert _should_segment(None) is False


def test_should_segment_false_for_single_topic():
    plan = SynthesisPlan(
        topics=[PlanTopic(title="Just one exercise", kind="exercise")],
        depth_tier="deep",
        suggested_sections=3,  # even if the model over-counts sections
    )
    assert _should_segment(plan) is False


def test_should_segment_false_for_light_multi_topic_note():
    # Two topics but the assessor judged it brief / single-section → single pass.
    plan = SynthesisPlan(
        topics=[PlanTopic(title="A"), PlanTopic(title="B")],
        depth_tier="brief",
        suggested_sections=1,
    )
    assert _should_segment(plan) is False


def test_should_segment_true_for_standard_multi_section_note():
    plan = SynthesisPlan(
        topics=[PlanTopic(title="A"), PlanTopic(title="B")],
        depth_tier="standard",
        suggested_sections=2,
    )
    assert _should_segment(plan) is True


def test_should_segment_ignores_blank_titled_topics():
    plan = SynthesisPlan(
        topics=[PlanTopic(title="A"), PlanTopic(title="   ")],
        depth_tier="deep",
        suggested_sections=2,
    )
    # Only one real topic survives → not enough to segment.
    assert _should_segment(plan) is False


# ---- _note_context_line --------------------------------------------------

def test_note_context_line_none_without_signals():
    assert _note_context_line(None, None) is None


def test_note_context_line_fuses_magnitude_and_plan():
    mag = NoteMagnitude.from_signals(
        transcript="t" * 6000,
        pages=[_page(0, "p" * 4000)],
        duration_seconds=210.0,
    )
    line = _note_context_line(mag, _two_topic_plan())
    assert line is not None
    assert line.startswith("NOTE CONTEXT:")
    # plan depth wins the density label; magnitude supplies the counts.
    assert "density: deep" in line
    assert "1 notebook page(s)" in line
    assert "6000 transcript chars" in line
    assert "210s of audio" in line
    assert "2 distinct topic(s) assessed" in line
    assert "spent the afternoon, ~4 hours" in line


def test_note_context_line_from_magnitude_only():
    mag = NoteMagnitude.from_signals(transcript="x" * 100)
    line = _note_context_line(mag, None)
    assert line is not None
    assert "density: brief" in line  # falls back to the measured tier


# ---- _compose_synthesis_prompt ordering ----------------------------------

def test_compose_prompt_orders_directives_context_focus_then_source():
    prompt = _compose_synthesis_prompt(
        "the transcript",
        _PAGES,
        flair_directives=["Do not spoil the exercise."],
        note_context="NOTE CONTEXT: density: deep.",
        focus="FOCUS: only topic X.",
    )
    assert prompt is not None
    di = prompt.index("LEARNER DIRECTIVES")
    ci = prompt.index("NOTE CONTEXT:")
    fi = prompt.index("FOCUS:")
    si = prompt.index("the transcript")
    assert di < ci < fi < si


def test_compose_prompt_none_without_source():
    # Flairs / context alone never trigger a synthesis.
    assert _compose_synthesis_prompt(None, [], flair_directives=["x"]) is None


# ---- segmented (map-reduce) path -----------------------------------------

def test_segmented_synthesis_produces_multiple_stitched_sections(monkeypatch):
    sources: list[str] = []

    async def fake_synth(source: str, instructions):
        sources.append(source)
        if "Integration by parts" in source:
            return _SynthesisOutput(
                markdown="$\\int u\\,dv = uv - \\int v\\,du$",
                concepts=["integration by parts"],
                validation_attempts=2,
            )
        if "Series convergence" in source:
            return _SynthesisOutput(
                markdown="$\\sum 1/n^2 = \\pi^2/6$",
                concepts=["series convergence", "integration by parts"],  # a dup
                validation_attempts=1,
            )
        raise AssertionError("unexpected single-pass call on the segmented path")

    async def fake_reduce(prompt: str, instructions):
        # Reorder (convergence first), no drops, note-level summary + concepts.
        return _ReduceOutput(
            ordered_indices=[1, 0],
            drop_indices=[],
            summary="A two-topic session on parts and convergence.",
            concepts=["series convergence", "integration by parts"],
        )

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)
    monkeypatch.setattr(workflow, "_run_reduce_agent", fake_reduce)

    mag = NoteMagnitude.from_signals(transcript=_TRANSCRIPT, pages=_PAGES)
    log = _FakeLog()
    syn = asyncio.run(
        synthesize_note(
            _TRANSCRIPT,
            _PAGES,
            "SYS",
            log,
            magnitude=mag,
            plan=_two_topic_plan(),
        )
    )

    assert syn is not None
    # Two map calls happened — one per topic — and each carried the NOTE CONTEXT.
    assert len(sources) == 2
    assert all("NOTE CONTEXT:" in s for s in sources)
    assert all("FOCUS:" in s for s in sources)

    # Sections reordered per the reduce pass; headings come from the plan topics.
    assert [s.heading for s in syn.sections] == ["Series convergence", "Integration by parts"]
    # Flat markdown is the deterministic stitch of the validated sections.
    assert "## Series convergence" in syn.markdown
    assert "## Integration by parts" in syn.markdown
    assert "\\pi^2/6" in syn.markdown
    # Reduce-supplied summary + deduped concepts.
    assert syn.summary == "A two-topic session on parts and convergence."
    assert syn.concepts == ["series convergence", "integration by parts"]
    # Depth from the plan; magnitude embedded; validation attempts summed (2 + 1).
    assert syn.depth_tier == "deep"
    assert syn.magnitude == mag
    assert syn.validation_attempts == 3
    assert syn.model_used == SYNTHESIS_MODEL


def test_segmented_preserves_learner_directives_on_every_segment(monkeypatch):
    sources: list[str] = []

    async def fake_synth(source: str, instructions):
        sources.append(source)
        title = "Integration by parts" if "Integration by parts" in source else "Series convergence"
        return _SynthesisOutput(markdown=f"$x$ for {title}", concepts=[], validation_attempts=1)

    async def fake_reduce(prompt, instructions):
        return _ReduceOutput(ordered_indices=[0, 1], summary="s", concepts=[])

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)
    monkeypatch.setattr(workflow, "_run_reduce_agent", fake_reduce)

    syn = asyncio.run(
        synthesize_note(
            _TRANSCRIPT,
            _PAGES,
            "SYS",
            flair_directives=["Do NOT reveal the solution to any unfinished exercise."],
            plan=_two_topic_plan(),
        )
    )
    assert syn is not None
    # The flair override rides on EVERY per-topic segment, not just one pass.
    assert len(sources) == 2
    assert all("LEARNER DIRECTIVES" in s and "Do NOT reveal" in s for s in sources)


def test_segmented_reduce_failure_degrades_to_deterministic_stitch(monkeypatch):
    async def fake_synth(source: str, instructions):
        if "Integration by parts" in source:
            return _SynthesisOutput(markdown="$A$", concepts=["a"], validation_attempts=1)
        return _SynthesisOutput(markdown="$B$", concepts=["b"], validation_attempts=1)

    async def boom_reduce(prompt, instructions):
        raise RuntimeError("reduce model down")

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)
    monkeypatch.setattr(workflow, "_run_reduce_agent", boom_reduce)

    log = _FakeLog()
    syn = asyncio.run(
        synthesize_note(_TRANSCRIPT, _PAGES, "SYS", log, plan=_two_topic_plan())
    )
    assert syn is not None
    # The validated map work is kept: sections in original topic order, union of
    # concepts, no summary, and a stitched document — never discarded.
    assert [s.heading for s in syn.sections] == ["Integration by parts", "Series convergence"]
    assert syn.concepts == ["a", "b"]
    assert syn.summary is None
    assert "## Integration by parts" in syn.markdown and "## Series convergence" in syn.markdown
    assert any("reduce/stitch unavailable" in w for w in log.warnings)


def test_segmented_partial_map_failure_stitches_the_rest(monkeypatch):
    plan = SynthesisPlan(
        topics=[PlanTopic(title="A"), PlanTopic(title="B"), PlanTopic(title="C")],
        depth_tier="deep",
        suggested_sections=3,
    )

    async def fake_synth(source: str, instructions):
        if "FOCUS:" in source and '"B"' in source:
            raise RuntimeError("one segment blew up")
        title = "A" if '"A"' in source else "C"
        return _SynthesisOutput(markdown=f"$x$ {title}", concepts=[title], validation_attempts=1)

    async def fake_reduce(prompt, instructions):
        return _ReduceOutput(ordered_indices=[0, 1], summary="ok", concepts=["A", "C"])

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)
    monkeypatch.setattr(workflow, "_run_reduce_agent", fake_reduce)

    log = _FakeLog()
    syn = asyncio.run(synthesize_note(_TRANSCRIPT, _PAGES, "SYS", log, plan=plan))
    assert syn is not None
    # Two of three survived — still >= 2, so it stitches what it has.
    assert [s.heading for s in syn.sections] == ["A", "C"]
    assert any("segment call(s) failed" in w for w in log.warnings)


# ---- single-pass fallback ------------------------------------------------

def test_light_note_uses_single_pass_and_skips_reduce(monkeypatch):
    calls: list[str] = []

    async def fake_synth(source: str, instructions):
        calls.append(source)
        return _SynthesisOutput(
            markdown="$a + b$", concepts=["addition"], summary="adds.", validation_attempts=1
        )

    async def reduce_must_not_run(prompt, instructions):
        raise AssertionError("reduce ran for a single-topic note")

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)
    monkeypatch.setattr(workflow, "_run_reduce_agent", reduce_must_not_run)

    # No plan → single pass; one synthesis call, no reduce, no FOCUS.
    syn = asyncio.run(synthesize_note(_TRANSCRIPT, _PAGES, "SYS", plan=None))
    assert syn is not None
    assert syn.markdown == "$a + b$"
    assert syn.sections == []
    assert len(calls) == 1
    assert "FOCUS:" not in calls[0]
    assert "NOTE CONTEXT:" not in calls[0]  # no magnitude/plan supplied here


def test_single_pass_carries_note_context_when_magnitude_present(monkeypatch):
    calls: list[str] = []

    async def fake_synth(source: str, instructions):
        calls.append(source)
        return _SynthesisOutput(markdown="$x$", concepts=[], validation_attempts=1)

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)
    mag = NoteMagnitude.from_signals(transcript=_TRANSCRIPT, pages=_PAGES)
    syn = asyncio.run(synthesize_note(_TRANSCRIPT, _PAGES, "SYS", magnitude=mag, plan=None))
    assert syn is not None
    assert "NOTE CONTEXT:" in calls[0]
    # depth falls back to the measured density when the model didn't pick one.
    assert syn.depth_tier == mag.density_tier


def test_segmented_under_two_sections_falls_back_to_single_pass(monkeypatch):
    async def fake_synth(source: str, instructions):
        if "FOCUS:" in source:
            # Map phase: first topic empty, second raises → 0 sections survive.
            if '"Series convergence"' in source:
                raise RuntimeError("segment down")
            return _SynthesisOutput(markdown="", concepts=[], validation_attempts=1)
        # Single-pass fallback call.
        return _SynthesisOutput(
            markdown="# whole note", concepts=["c"], summary="all of it", validation_attempts=1
        )

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)
    monkeypatch.setattr(
        workflow,
        "_run_reduce_agent",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("reduce should not run")),
    )

    log = _FakeLog()
    syn = asyncio.run(
        synthesize_note(_TRANSCRIPT, _PAGES, "SYS", log, plan=_two_topic_plan())
    )
    assert syn is not None
    # Degraded to the holistic single pass (which still saw the whole note).
    assert syn.markdown == "# whole note"
    assert syn.sections == []
    assert any("< 2 sections" in i for i in log.infos)


def test_no_source_returns_none(monkeypatch):
    monkeypatch.setattr(
        workflow,
        "_run_synthesis_agent",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("agent should not run")),
    )
    assert asyncio.run(synthesize_note(None, [], "SYS", plan=_two_topic_plan())) is None


# ---- SynthesizeNoteStep threads the plan ---------------------------------

def test_node_runs_segmented_synthesis_from_state_plan(monkeypatch):
    async def fake_synth(source: str, instructions):
        title = "Integration by parts" if "Integration by parts" in source else "Series convergence"
        return _SynthesisOutput(markdown=f"$x$ {title}", concepts=[title], validation_attempts=1)

    async def fake_reduce(prompt, instructions):
        return _ReduceOutput(ordered_indices=[0, 1], summary="two topics", concepts=["a", "b"])

    monkeypatch.setattr(workflow, "_run_synthesis_agent", fake_synth)
    monkeypatch.setattr(workflow, "_run_reduce_agent", fake_reduce)

    state = MathNotesState(
        transcript=_TRANSCRIPT,
        pages=_PAGES,
        magnitude=NoteMagnitude.from_signals(transcript=_TRANSCRIPT, pages=_PAGES),
        plan=_two_topic_plan(),
    )
    log = _FakeLog()
    ctx = GraphRunContext(
        state=state,
        deps=MathNotesWorkflowDependencies(synthesis_instructions="SYS", logger=log),
    )

    result = asyncio.run(SynthesizeNoteStep().run(ctx))

    assert isinstance(result, End)
    assert state.synthesis is not None
    # The node drove the plan into the segmented pass → two stitched sections.
    assert len(state.synthesis.sections) == 2
    assert "## Integration by parts" in state.synthesis.markdown

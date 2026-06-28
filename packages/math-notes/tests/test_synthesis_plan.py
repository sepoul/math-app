"""Tests for the assess/triage pass and the `SynthesisPlan` contract (issue #17).

Covers the pure pieces (schema + the agent-output → plan normalization), the
best-effort `assess_note` degrade behaviour (no source → None; any failure →
None, never raises), and the `AssessNoteStep` graph node threading the plan onto
state. The model call (`_run_assess_agent`) is stubbed so nothing here touches
the network or needs an API key.

Run from the repo root in the default-runtime venv::

    PYTHONPATH="packages/math-notes/src:../ai-platform/packages/core/src:../ai-platform/packages/worker/src" \
      ../ai-platform/.venv/bin/python -m pytest \
      packages/math-notes/tests/test_synthesis_plan.py
"""
from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError
from pydantic_graph import GraphRunContext

from mathai.math_notes import workflow
from mathai.math_notes.artifacts import PlanTopic, SynthesisPlan
from mathai.math_notes.state import MathNotesState
from mathai.math_notes.workflow import (
    ASSESS_INSTRUCTIONS,
    ASSESS_MODEL,
    AssessNoteStep,
    MathNotesWorkflowDependencies,
    NotePage,
    SynthesizeNoteStep,
    _AssessOutput,
    _AssessTopic,
    _plan_from_output,
    assess_note,
)


class _FakeLog:
    """Captures the log lines a node/helper emits, with a `for_stage` shim."""

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


# ---- schema --------------------------------------------------------------

def test_plan_defaults_are_sane():
    plan = SynthesisPlan()
    assert plan.topics == []
    assert plan.depth_tier == "standard"
    assert plan.suggested_sections == 1
    assert plan.segment_boundaries == []
    assert plan.study_scope_hint is None
    assert plan.rationale is None
    assert plan.model_used is None


def test_plan_round_trips():
    plan = SynthesisPlan(
        topics=[PlanTopic(title="Integration by parts", kind="exercise", span_hint="pages 1-2")],
        depth_tier="deep",
        suggested_sections=3,
        segment_boundaries=["switches to series convergence"],
        study_scope_hint="~4 hours",
        rationale="Multi-topic, dense session.",
        model_used=ASSESS_MODEL,
    )
    again = SynthesisPlan.model_validate(plan.model_dump())
    assert again == plan
    assert again.topics[0].kind == "exercise"


def test_plan_rejects_unknown_fields():
    # `extra="forbid"` keeps the contract tight.
    with pytest.raises(ValidationError):
        SynthesisPlan.model_validate({"topics": [], "bogus": 1})


def test_topic_requires_a_title():
    with pytest.raises(ValidationError):
        PlanTopic(kind="concept")


def test_suggested_sections_floor_is_enforced_by_schema():
    with pytest.raises(ValidationError):
        SynthesisPlan(suggested_sections=0)


# ---- normalization (agent output -> plan) --------------------------------

def test_plan_from_output_normalizes_tiers_and_kinds():
    out = _AssessOutput(
        topics=[
            _AssessTopic(title="Integration by parts", kind="EXERCISE", span_hint=" pages 1-2 "),
            _AssessTopic(title="Taylor series", kind="not_a_real_kind"),
        ],
        depth_tier="DEEP",
        suggested_sections=2,
        segment_boundaries=["a", "", "  b  "],
        study_scope_hint="  ~4 hours  ",
        rationale="  dense  ",
    )
    plan = _plan_from_output(out, "claude-haiku-4-5")

    assert [t.title for t in plan.topics] == ["Integration by parts", "Taylor series"]
    # kind is lowercased; an unknown kind falls back to "other".
    assert plan.topics[0].kind == "exercise"
    assert plan.topics[1].kind == "other"
    # span_hint is trimmed.
    assert plan.topics[0].span_hint == "pages 1-2"
    # depth_tier is lowercased + validated.
    assert plan.depth_tier == "deep"
    # blank boundaries dropped, surviving ones trimmed.
    assert plan.segment_boundaries == ["a", "b"]
    assert plan.study_scope_hint == "~4 hours"
    assert plan.rationale == "dense"
    assert plan.model_used == "claude-haiku-4-5"


def test_plan_from_output_clamps_bad_values():
    out = _AssessOutput(
        topics=[_AssessTopic(title="   ", kind="exercise")],  # blank title -> dropped
        depth_tier="ludicrous",  # unknown -> standard
        suggested_sections=0,  # < 1 -> 1
        study_scope_hint="   ",  # blank -> None
        rationale="",  # blank -> None
    )
    plan = _plan_from_output(out, ASSESS_MODEL)
    assert plan.topics == []
    assert plan.depth_tier == "standard"
    assert plan.suggested_sections == 1
    assert plan.study_scope_hint is None
    assert plan.rationale is None


# ---- assess_note: best-effort behaviour ----------------------------------

def test_assess_note_returns_none_with_no_source():
    # No transcript, no page text -> nothing to assess, no model call.
    assert asyncio.run(assess_note(None, [])) is None
    assert asyncio.run(assess_note("   ", [_page(0, "  ")])) is None


def test_assess_note_enumerates_topics_for_multi_topic_note(monkeypatch):
    # Acceptance: a multi-topic transcript yields a plan enumerating the
    # distinct topics with a sensible depth_tier. The model call is stubbed.
    captured: dict = {}

    async def fake_run(source: str, instructions, model: str) -> _AssessOutput:
        captured["source"] = source
        captured["instructions"] = instructions
        captured["model"] = model
        return _AssessOutput(
            topics=[
                _AssessTopic(title="Integration by parts", kind="exercise", span_hint="opening"),
                _AssessTopic(title="Series convergence", kind="concept", span_hint="pages 1-2"),
            ],
            depth_tier="deep",
            suggested_sections=2,
            segment_boundaries=["moves on to convergence"],
            study_scope_hint="spent the afternoon, ~4 hours",
            rationale="Two distinct threads over a long session.",
        )

    monkeypatch.setattr(workflow, "_run_assess_agent", fake_run)

    transcript = (
        "Today I worked through an integration by parts exercise, then moved on "
        "to series convergence for the rest of the afternoon, about 4 hours total."
    )
    plan = asyncio.run(assess_note(transcript, [_page(0, "u dv = uv - v du")]))

    assert plan is not None
    assert [t.title for t in plan.topics] == ["Integration by parts", "Series convergence"]
    assert plan.depth_tier == "deep"
    assert plan.suggested_sections == 2
    assert plan.study_scope_hint == "spent the afternoon, ~4 hours"
    assert plan.model_used == ASSESS_MODEL
    # The raw material reached the model and the default instructions were used.
    assert "integration by parts" in captured["source"].lower()
    assert "u dv = uv - v du" in captured["source"]
    assert captured["instructions"] == ASSESS_INSTRUCTIONS
    assert captured["model"] == ASSESS_MODEL


def test_assess_note_uses_instruction_override(monkeypatch):
    async def fake_run(source, instructions, model) -> _AssessOutput:
        assert instructions == "CUSTOM TRIAGE PROMPT"
        return _AssessOutput(topics=[_AssessTopic(title="x")])

    monkeypatch.setattr(workflow, "_run_assess_agent", fake_run)
    plan = asyncio.run(assess_note("some math", [], instructions="CUSTOM TRIAGE PROMPT"))
    assert plan is not None
    assert plan.topics[0].title == "x"


def test_assess_note_degrades_to_none_on_failure(monkeypatch):
    # Any failure in the model call must yield None (never raise) and log a
    # warning — the ingest must not fail because triage was unavailable.
    async def boom(*_a, **_k) -> _AssessOutput:
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(workflow, "_run_assess_agent", boom)
    log = _FakeLog()
    plan = asyncio.run(assess_note("studied calculus", [], log=log))

    assert plan is None
    assert any("assessment unavailable" in w for w in log.warnings)


# ---- AssessNoteStep node -------------------------------------------------

def _ctx(state: MathNotesState, log: _FakeLog) -> GraphRunContext:
    return GraphRunContext(state=state, deps=MathNotesWorkflowDependencies(logger=log))


def test_node_threads_plan_onto_state_and_advances(monkeypatch):
    plan = SynthesisPlan(
        topics=[PlanTopic(title="Limits", kind="concept")],
        depth_tier="standard",
        suggested_sections=1,
        study_scope_hint="~1 hour",
        model_used=ASSESS_MODEL,
    )

    async def fake_assess(transcript, pages, instructions, log):
        return plan

    monkeypatch.setattr(workflow, "assess_note", fake_assess)
    state = MathNotesState(transcript="limits today")
    log = _FakeLog()

    result = asyncio.run(AssessNoteStep().run(_ctx(state, log)))

    assert isinstance(result, SynthesizeNoteStep)
    assert state.plan is plan
    assert any("synthesis plan" in line for line in log.infos)


def test_node_handles_missing_plan(monkeypatch):
    async def fake_assess(*_a, **_k):
        return None

    monkeypatch.setattr(workflow, "assess_note", fake_assess)
    state = MathNotesState(transcript="x")
    log = _FakeLog()

    result = asyncio.run(AssessNoteStep().run(_ctx(state, log)))

    assert isinstance(result, SynthesizeNoteStep)
    assert state.plan is None
    assert any("no synthesis plan produced" in line for line in log.infos)


def test_node_is_registered_in_the_graph():
    assert workflow.math_notes_node_registry["AssessNoteStep"] is AssessNoteStep
    # Ordered between extraction and synthesis.
    keys = list(workflow.math_notes_node_registry)
    assert keys.index("ExtractPagesStep") < keys.index("AssessNoteStep") < keys.index(
        "SynthesizeNoteStep"
    )

"""Tests for the GroundedAnchor resolver (issue #68).

Every test drives `resolve_anchor` through an **in-memory fake port** — no live
platform, no network, no DB. The fake records the `BookRetrieveInput`s it
receives so we can assert the seam is used correctly (book-scoped, coordinate
grammar, intent passthrough, exactly one call).

Run (from the repo root, in a 3.13 venv with mathai-math-mentor + mathai-math-book
+ aiplatform-core + pydantic + pytest installed)::

    python -m pytest packages/math-mentor/tests -q

Acceptance criteria covered (see the issue), one or more tests each:
  1. Coordinate-first grounded (Problem 2.16 / Problem 21.4 / §21.4).
  2. Right book / right grammar (book_id + query on the input; wrong-book label
     not accepted as grounded).
  3. No false precision (coordinate=None → at most section-grounded, label None).
  4. Never fabricates (empty hits → ungrounded; unmatched coord + below floor →
     ungrounded).
  5. Only-one-retrieval-path (exactly one port call; no platform IO imported).
  6. intent passthrough (forwarded into BookRetrieveInput.intent).
  7. score_floor (below floor → ungrounded; above floor → section-grounded).
"""
from __future__ import annotations

import sys

import pytest

from mathai.math_book.models import (
    BookRetrievalHit,
    BookRetrievalResult,
    BookRetrieveInput,
)
from mathai.math_mentor.adapter import PlatformBookRetrieve
from mathai.math_mentor.anchor import (
    DEFAULT_K,
    DEFAULT_SCORE_FLOOR,
    GroundedAnchor,
    normalize_coordinate,
    resolve_anchor,
)
from mathai.math_mentor.port import BookRetrieveFn


# --- fixtures / helpers -------------------------------------------------------


class FakeBookRetrieve:
    """An in-memory `BookRetrieveFn`. Returns a canned result and records every
    request it is called with, so tests can assert on the seam."""

    def __init__(self, result: BookRetrievalResult) -> None:
        self._result = result
        self.calls: list[BookRetrieveInput] = []

    def __call__(self, req: BookRetrieveInput) -> BookRetrievalResult:
        self.calls.append(req)
        return self._result


def hit(
    chunk_id: str = "c1",
    *,
    label: str | None = None,
    node_id: str | None = None,
    page: int | None = None,
    heading_path: list[str] | None = None,
    source: str | None = None,
    score: float = 0.9,
    text: str = "chunk body",
) -> BookRetrievalHit:
    return BookRetrievalHit(
        chunk_id=chunk_id,
        node_id=node_id,
        text=text,
        score=score,
        label=label,
        page=page,
        heading_path=heading_path or [],
        source=source,
    )


def result(*hits: BookRetrievalHit, book_id: str | None = None, query: str | None = None) -> BookRetrievalResult:
    return BookRetrievalResult(book_id=book_id, query=query, hits=list(hits))


# --- AC1: coordinate-first grounded ------------------------------------------


@pytest.mark.parametrize(
    "coordinate, hit_label",
    [
        ("Problem 2.16", "Problem 2.16"),
        ("Problem 21.4", "Problem 21.4"),
        ("§21.4", "Section 21.4"),  # cross-variant: § coord matches 'Section' label
    ],
)
def test_coordinate_first_grounded_copies_fields(coordinate: str, hit_label: str) -> None:
    matching = hit(
        "c-match",
        label=hit_label,
        node_id="node-42",
        page=137,
        heading_path=["Chapter 2", "§2.3"],
        source=f"Chapter 2 › §2.3 › {hit_label} (p.137)",
        score=0.62,
    )
    # A higher-scoring distractor proves grounding is by LABEL match, not top score.
    distractor = hit("c-other", label="Theorem 9.9", node_id="node-9", page=200, score=0.99)
    fake = FakeBookRetrieve(result(distractor, matching, book_id="Tu", query=coordinate))

    anchor = resolve_anchor(fake, book_id="Tu", coordinate=coordinate, topic="ignored", intent=None)

    assert anchor.trust_level == "grounded"
    assert anchor.matched is True
    assert anchor.node_id == "node-42"
    assert anchor.label == hit_label
    assert anchor.page == 137
    assert anchor.heading_path == ["Chapter 2", "§2.3"]
    assert anchor.source == f"Chapter 2 › §2.3 › {hit_label} (p.137)"
    assert anchor.score == 0.62
    assert anchor.book_id == "Tu"
    assert anchor.query == coordinate


def test_coordinate_grounded_cross_variant_exercise() -> None:
    matching = hit(label="Exercise 1.2.4", node_id="n-ex", page=12, heading_path=["Chapter 1"], score=0.5)
    fake = FakeBookRetrieve(result(matching))

    anchor = resolve_anchor(fake, book_id="Tu", coordinate="Ex 1.2.4", topic="t", intent=None)

    assert anchor.trust_level == "grounded"
    assert anchor.label == "Exercise 1.2.4"
    assert anchor.node_id == "n-ex"
    assert anchor.page == 12


def test_grounded_picks_highest_scoring_label_match() -> None:
    lo = hit("lo", label="Problem 2.16", node_id="lo-node", page=10, score=0.40)
    hi = hit("hi", label="problem  2.16", node_id="hi-node", page=11, score=0.55)  # same coord, variant spelling
    fake = FakeBookRetrieve(result(lo, hi))

    anchor = resolve_anchor(fake, book_id="Tu", coordinate="Problem 2.16", topic="t", intent=None)

    assert anchor.trust_level == "grounded"
    assert anchor.node_id == "hi-node"
    assert anchor.score == 0.55


def test_grounded_even_when_below_score_floor() -> None:
    """An exact coordinate-label match grounds regardless of score (label match is
    the strongest signal; the floor only gates the topical section fallback)."""
    low = hit(label="Problem 2.16", node_id="n", page=5, heading_path=["Ch2"], score=DEFAULT_SCORE_FLOOR - 0.3)
    fake = FakeBookRetrieve(result(low))

    anchor = resolve_anchor(fake, book_id="Tu", coordinate="Problem 2.16", topic="t", intent=None)

    assert anchor.trust_level == "grounded"
    assert anchor.score == pytest.approx(DEFAULT_SCORE_FLOOR - 0.3)
    assert anchor.node_id == "n"


# --- AC2: right book / right grammar (namespacing at the call site) ----------


def test_port_receives_book_scoped_coordinate_query() -> None:
    fake = FakeBookRetrieve(result())
    resolve_anchor(fake, book_id="Tu", coordinate="Problem 2.16", topic="covering spaces", intent=None)

    assert len(fake.calls) == 1
    req = fake.calls[0]
    assert isinstance(req, BookRetrieveInput)
    assert req.book_id == "Tu"           # book-scoped: retrieval can't leave Tu
    assert req.query == "Problem 2.16"   # coordinate-first grammar
    assert req.job_type == "book_retrieve"


def test_wrong_book_style_label_not_accepted_as_grounded() -> None:
    """A Hatcher-style label surfacing for a Tu 'Problem N.M' query must NOT be
    accepted as a grounded coordinate match (it's a different coordinate)."""
    hatcher = hit(
        "hatcher",
        label="Proposition 1.20",  # Hatcher grammar, not a Tu 'Problem 2.16'
        node_id="h-1",
        page=30,
        heading_path=["Hatcher Ch1"],
        source="Hatcher › Ch1",
        score=0.95,
    )
    fake = FakeBookRetrieve(result(hatcher))

    anchor = resolve_anchor(fake, book_id="Tu", coordinate="Problem 2.16", topic="covering spaces", intent=None)

    assert anchor.trust_level != "grounded"
    assert anchor.label is None   # never a confident wrong label
    assert anchor.node_id is None


# --- AC3: no false precision -------------------------------------------------


def test_no_coordinate_yields_at_most_section_grounded() -> None:
    """coordinate=None with topical hits present → section-grounded with label
    and node_id None (even though the hit carries a label, we only trust a label
    that matches a *requested* coordinate)."""
    topical = hit(
        label="van Kampen theorem",  # present, but NOT a requested coordinate
        node_id="vk-node",
        page=44,
        heading_path=["Chapter 1", "§1.2 Van Kampen"],
        source="Chapter 1 › §1.2 Van Kampen (p.44)",
        score=0.8,
    )
    fake = FakeBookRetrieve(result(topical))

    anchor = resolve_anchor(fake, book_id="Hatcher", coordinate=None, topic="van Kampen theorem", intent="theorem")

    assert anchor.trust_level == "section-grounded"
    assert anchor.matched is True
    assert anchor.label is None      # no false precision
    assert anchor.node_id is None    # no false precision
    assert anchor.heading_path == ["Chapter 1", "§1.2 Van Kampen"]  # section copied
    assert anchor.page == 44
    assert anchor.source == "Chapter 1 › §1.2 Van Kampen (p.44)"
    assert anchor.score == 0.8
    assert anchor.query == "van Kampen theorem"  # query falls back to topic


def test_coordinate_unmatched_but_topical_hit_is_section_grounded_not_wrong_label() -> None:
    """A coordinate with no matching label but a strong topical hit → at most
    section-grounded (label None), never a confident wrong label."""
    topical = hit(label="Theorem 3.1", node_id="t31", page=60, heading_path=["Ch3"], score=0.7)
    fake = FakeBookRetrieve(result(topical))

    anchor = resolve_anchor(fake, book_id="Tu", coordinate="Problem 2.16", topic="Stokes", intent=None)

    assert anchor.trust_level == "section-grounded"
    assert anchor.label is None
    assert anchor.node_id is None
    assert anchor.heading_path == ["Ch3"]


# --- AC4: never fabricates ---------------------------------------------------


def test_empty_hits_yields_ungrounded() -> None:
    fake = FakeBookRetrieve(result())

    anchor = resolve_anchor(fake, book_id="Tu", coordinate="Problem 2.16", topic="t", intent=None)

    assert anchor.trust_level == "ungrounded"
    assert anchor.matched is False
    assert anchor.label is None
    assert anchor.node_id is None
    assert anchor.page is None
    assert anchor.source is None
    assert anchor.score is None
    assert anchor.heading_path == []
    assert anchor.book_id == "Tu"


def test_coordinate_unmatched_and_below_floor_yields_ungrounded() -> None:
    weak = hit(label="Theorem 9.9", node_id="n9", page=99, heading_path=["Ch9"], score=0.10)
    fake = FakeBookRetrieve(result(weak))

    anchor = resolve_anchor(fake, book_id="Tu", coordinate="Problem 2.16", topic="t", intent=None)

    assert anchor.trust_level == "ungrounded"
    assert anchor.matched is False
    assert anchor.label is None
    assert anchor.node_id is None


# --- AC5: only-one-retrieval-path --------------------------------------------


@pytest.mark.parametrize(
    "coordinate, hits, expected_level",
    [
        ("Problem 2.16", [hit(label="Problem 2.16", node_id="n", page=1, score=0.9)], "grounded"),
        (None, [hit(label="topic", heading_path=["Ch"], page=2, score=0.9)], "section-grounded"),
        ("Problem 2.16", [], "ungrounded"),
    ],
)
def test_exactly_one_port_call_per_resolve(coordinate, hits, expected_level) -> None:
    fake = FakeBookRetrieve(result(*hits))
    anchor = resolve_anchor(fake, book_id="Tu", coordinate=coordinate, topic="topic", intent=None)
    assert anchor.trust_level == expected_level
    assert len(fake.calls) == 1  # the port is the sole data source, called once


def test_resolver_path_imports_no_platform_io() -> None:
    """The resolver never touches the platform session layer. `ai_platform` is
    only pulled in for the *contract types* (math_book.models); the session /
    network layer (`ai_platform.session`) is imported lazily by
    `PlatformBookRetrieve` at call time — and no test ever calls it."""
    assert "ai_platform.session" not in sys.modules
    assert "ai_platform.session.session" not in sys.modules


# --- AC6: intent passthrough -------------------------------------------------


@pytest.mark.parametrize("intent", ["definition", "theorem", "proof", "example", "general", None])
def test_intent_forwarded_into_input(intent) -> None:
    fake = FakeBookRetrieve(result())
    resolve_anchor(fake, book_id="Tu", coordinate=None, topic="compactness", intent=intent)
    assert fake.calls[0].intent == intent


# --- AC7: score_floor --------------------------------------------------------


def test_topical_hit_just_below_floor_is_ungrounded() -> None:
    below = hit(label="van Kampen", node_id="vk", page=44, heading_path=["Ch1"], score=DEFAULT_SCORE_FLOOR - 0.01)
    fake = FakeBookRetrieve(result(below))

    anchor = resolve_anchor(fake, book_id="Hatcher", coordinate=None, topic="van Kampen theorem", intent=None)

    assert anchor.trust_level == "ungrounded"
    assert anchor.matched is False


def test_topical_hit_just_above_floor_is_section_grounded() -> None:
    above = hit(label="van Kampen", node_id="vk", page=44, heading_path=["Ch1"], score=DEFAULT_SCORE_FLOOR + 0.01)
    fake = FakeBookRetrieve(result(above))

    anchor = resolve_anchor(fake, book_id="Hatcher", coordinate=None, topic="van Kampen theorem", intent=None)

    assert anchor.trust_level == "section-grounded"
    assert anchor.matched is True


def test_custom_score_floor_param_is_respected() -> None:
    h = hit(label="x", node_id="n", page=1, heading_path=["Ch"], score=0.5)

    # A floor above the hit's score demotes it to ungrounded...
    strict = FakeBookRetrieve(result(h))
    a_strict = resolve_anchor(strict, book_id="Tu", coordinate=None, topic="t", intent=None, score_floor=0.9)
    assert a_strict.trust_level == "ungrounded"

    # ...a floor below it keeps it section-grounded.
    loose = FakeBookRetrieve(result(h))
    a_loose = resolve_anchor(loose, book_id="Tu", coordinate=None, topic="t", intent=None, score_floor=0.1)
    assert a_loose.trust_level == "section-grounded"


# --- contract / invariants ---------------------------------------------------


def test_matched_invariant_holds_across_all_trust_levels() -> None:
    grounded = resolve_anchor(
        FakeBookRetrieve(result(hit(label="Problem 2.16", node_id="n", page=1, score=0.9))),
        book_id="Tu", coordinate="Problem 2.16", topic="t", intent=None,
    )
    section = resolve_anchor(
        FakeBookRetrieve(result(hit(label="topic", heading_path=["Ch"], page=2, score=0.9))),
        book_id="Tu", coordinate=None, topic="t", intent=None,
    )
    ungrounded = resolve_anchor(
        FakeBookRetrieve(result()),
        book_id="Tu", coordinate="Problem 2.16", topic="t", intent=None,
    )
    assert grounded.trust_level == "grounded"
    assert section.trust_level == "section-grounded"
    assert ungrounded.trust_level == "ungrounded"
    for anchor in (grounded, section, ungrounded):
        assert anchor.matched == (anchor.trust_level != "ungrounded")


def test_default_k_forwarded_into_input() -> None:
    fake = FakeBookRetrieve(result())
    resolve_anchor(fake, book_id="Tu", coordinate="Problem 2.16", topic="t", intent=None)
    assert fake.calls[0].k == DEFAULT_K


def test_query_falls_back_to_topic_when_no_coordinate() -> None:
    fake = FakeBookRetrieve(result())
    anchor = resolve_anchor(fake, book_id="Tu", coordinate=None, topic="Stokes theorem", intent=None)
    assert fake.calls[0].query == "Stokes theorem"
    assert anchor.query == "Stokes theorem"


def test_fake_satisfies_port_protocol() -> None:
    assert isinstance(FakeBookRetrieve(result()), BookRetrieveFn)


def test_grounded_anchor_is_the_frozen_contract_shape() -> None:
    """GroundedAnchor exposes EXACTLY the #68 field set — no more, no less."""
    assert set(GroundedAnchor.model_fields) == {
        "book_id", "node_id", "label", "page", "heading_path",
        "source", "score", "query", "trust_level", "matched",
    }


# --- coordinate normalization (the matching primitive) -----------------------


@pytest.mark.parametrize(
    "a, b",
    [
        ("§21.4", "Section 21.4"),
        ("§ 21.4", "section 21.4"),
        ("Ex 1.2.4", "Exercise 1.2.4"),
        ("Problem 2.16", "  problem   2.16 "),
        ("§21.4", "§21-4"),                # hyphen vs dot
        ("Thm 7.7", "Theorem 7.7"),
        ("Prop 3.1", "Proposition 3.1"),
    ],
)
def test_normalize_coordinate_treats_variants_as_equal(a: str, b: str) -> None:
    na, nb = normalize_coordinate(a), normalize_coordinate(b)
    assert na is not None
    assert na == nb


@pytest.mark.parametrize(
    "a, b",
    [
        ("Problem 7.1", "Theorem 7.1"),   # different KIND must not collapse
        ("Problem 2.16", "Problem 2.17"),  # different NUMBER must not collapse
        ("§21.4", "Problem 21.4"),         # section vs problem
    ],
)
def test_normalize_coordinate_keeps_distinct_coordinates_distinct(a: str, b: str) -> None:
    assert normalize_coordinate(a) != normalize_coordinate(b)


def test_normalize_coordinate_none_and_empty() -> None:
    assert normalize_coordinate(None) is None
    assert normalize_coordinate("") is None
    assert normalize_coordinate("   ") is None


# --- adapter result-envelope parsing (no network) ----------------------------


def test_platform_adapter_unwraps_result_envelope() -> None:
    """PlatformBookRetrieve._parse_result understands the API envelope shape
    ({"job_id","result":{...}}) as well as a bare result body — verified without
    touching the network."""
    body = {
        "job_type": "book_retrieve",
        "book_id": "Tu",
        "query": "Problem 2.16",
        "hits": [
            {"chunk_id": "c1", "text": "x", "score": 0.9, "label": "Problem 2.16", "page": 5},
        ],
    }
    enveloped = PlatformBookRetrieve._parse_result({"job_id": "j1", "result": body})
    bare = PlatformBookRetrieve._parse_result(body)
    for parsed in (enveloped, bare):
        assert isinstance(parsed, BookRetrievalResult)
        assert parsed.book_id == "Tu"
        assert len(parsed.hits) == 1
        assert parsed.hits[0].label == "Problem 2.16"

    empty = PlatformBookRetrieve._parse_result({"job_id": "j1", "result": None})
    assert isinstance(empty, BookRetrievalResult)
    assert empty.hits == []

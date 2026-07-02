# math-mentor

The tutoring layer over the book-RAG corpus. This package currently ships three
issues of pure logic:

- **#68 — the `GroundedAnchor` resolver**: the single seam onto the
  already-shipped `book_retrieve` RAG job.
- **#69 — the detection pass**: a trailing-window read-model over daily notes
  that extracts *grounded candidate signals*.
- **#70 — restraint & arbitration**: the deterministic **fire/silence** decision
  over #69's candidates → a `MentorDecision`.

> **Deploy wiring is deferred.** These issues are *logic contracts* only. There
> is intentionally **no** `bundle.toml`, `control.py`, or `execution.py` here
> yet — turning `math_mentor` into a deployable platform job is future work
> (#71).

## What #68 is

`resolve_anchor(retrieve, book_id, coordinate, topic, intent)` takes a request to
locate a spot in a book and returns a `GroundedAnchor` — a source-traceable
citation with an **honest trust level**:

| trust level        | meaning                                                            | `matched` |
|--------------------|--------------------------------------------------------------------|-----------|
| `grounded`         | a returned hit's label matches the requested coordinate exactly    | `True`    |
| `section-grounded` | no coordinate match, but a topical hit clears the score floor      | `True`    |
| `ungrounded`       | no usable hit (empty, or nothing above the floor)                  | `False`   |

`matched == (trust_level != "ungrounded")`.

The resolver **never fabricates** a `label`/`node_id`: those are only ever copied
from a hit the retriever returned. A coordinate with no matching label yields at
most `section-grounded` (with `label=None`, `node_id=None`) — never a confident
wrong label.

## The one seam: `book_retrieve`

The resolver's *only* source of retrieval data is a **`BookRetrieveFn` port** — a
`typing.Protocol` of `(BookRetrieveInput) -> BookRetrievalResult`. No SQL, no
OCR, no regex over book text, no vector store, no filesystem/DB access — every
byte of book knowledge flows through that one port call, made exactly once per
`resolve_anchor`.

- The contract types (`BookRetrieveInput`, `BookRetrievalResult`,
  `BookRetrievalHit`, `RetrievalIntent`) are imported from
  `mathai.math_book.models` — the single source of truth. We never redefine them.
- `PlatformBookRetrieve` is a thin production adapter implementing the port via
  `ai_platform.session.PlatformSession` (submit `book_retrieve` → wait → parse).
  It imports `ai_platform` **lazily**, so unit tests never need the platform.

## What #69 is — the detection pass

`detect_candidates(notes, retrieve, extractor, *, book_id, window=None)` reads a
**trailing window** of daily notes and emits the *set* of grounded
`CandidateSignal`s. It is **pure extraction** — it makes **no** fire/silence
decision (that is #70) and calls **no** model.

- **The read-model.** `NoteView` is a minimal typed view holding exactly the
  fields detection reads — `transcript` (the primary surface), `concepts` (the
  cross-track trail), `density_tier`, `dont_spoil`, `markdown`. It mirrors the
  real `math_notes` types; `from_daily_note(artifact, *, flairs=…)` adapts a live
  `DailyNoteArtifact` (+ its flairs, which live on the *job input*) into one. The
  core logic runs on `NoteView`s, so tests need no platform.
- **All grounding rides through #68.** Every candidate resolves its anchor via
  `resolve_anchor(book_id, written_coordinate, topic, intent)`. A candidate whose
  anchor is `ungrounded` is **dropped** — no nameable anchor → not a candidate.
  There is no direct book access anywhere in the pass.
- **The one LLM-shaped seam.** Pulling a *verbatim* hedge quote and judging a
  struggle's **resolution clause** (abandoned vs. resolved vs. in-progress) is
  model work; it lives behind the injectable `SignalExtractor` Protocol (like
  `BookRetrieveFn`). The detection *policy* around it is deterministic.

`CandidateSignal = { kind, verbatim_quote, topic, written_coordinate?,
source_note_date, grounded_anchor }`, `kind ∈ {abandoned_crux, unverified_proof,
ripe_bridge}`. A surviving candidate always carries a non-empty verbatim quote
and a grounded/section-grounded anchor.

**Bridge canonicalization rides on retrieval, not strings.** Two *distinct*
`concepts`-trail strings form a `ripe_bridge` iff their `resolve_anchor` hits
land on **related/adjacent skeleton nodes** — a shared `heading_path` prefix (≥
`BRIDGE_MIN_SHARED_DEPTH` levels) or the same `node_id`. The determinant surfaces
as five word-disjoint strings (`determinant` / `kernel` / `SL(m)` / `regular
level set` / `submersion`) that a literal match could never unite; they bridge
because their anchors share the `§9 The Regular Level Set Theorem` region.

**Intent mapping (open seam).** `unverified_proof → proof`, `abandoned_crux →
theorem`, `ripe_bridge → general`.

## What #70 is — restraint & arbitration

`arbitrate(candidates, *, note, retrieve, history, cues)` takes the candidate set
that surfaced on one night and returns a **`MentorDecision`** — *does a card fire
tonight, and which one?* The governing principle is asymmetric: **a wrong card is
strictly worse than a missed one** (a miss costs one opportunity; a wrong card
costs the instrument), so **the default is silence** and every gate is a reason to
*stay* silent. Like #68/#69 it is engine-free, deterministic, pydantic-only —
**no model call**.

```
MentorDecision = { fire: bool,
                   kind: "repair" | "bridge" | "none",
                   winning_signal: CandidateSignal | None,
                   grounded_anchor: GroundedAnchor | None,
                   quote: str | None,
                   suppressed: [CandidateSignal],   # losers preserved, never discarded
                   reason: str }
```

`kind` maps from the winner: `abandoned_crux`/`unverified_proof` → `"repair"`,
`ripe_bridge` → `"bridge"`, nothing → `"none"`. The decision is handed to #71 (the
repair card) / the bridge card **only when `fire=True`**.

**The gate order** (each a reason to stay silent):

1. **`dont_spoil` flair** → respect the learner's deliberate in-progress work.
2. **Distracted verbal cue** → a light/low-signal night, read from the
   **transcript cue, not `density_tier`** (a brief night with a real hedge still
   fires; a distracted night does not).
3. **Staleness** → drop a candidate whose topic was *self-closed the same day*
   (a prerequisite already shored up is not a live crux).
4. **Confidence bar** → `candidate_confidence` (anchor **trust** × `density_tier`)
   must clear `confidence_bar(streak)`. A `section-grounded` anchor is weaker than
   a `grounded` one; a weak anchor on a light or repeatedly-ignored night falls
   below the bar.
5. **One-card-max arbitration** → among survivors, **live repair > ripe bridge**
   (ties broken by confidence, then date/topic). At most one card per night.
6. **Adversarial self-check** → re-resolve the winner's anchor through #68's
   `resolve_anchor`; if it comes back `ungrounded`, it **cannot fire**. This is the
   *only* extra book access — no independent retrieval path.
7. **Corpus-cap backstop** → at most `MAX_CORPUS_CARDS` (= 2) across the window.

**Grounding still rides only through #68.** Arbitration does no retrieval of its
own; the self-check calls `resolve_anchor(retrieve, …)` with the injected
`BookRetrieveFn`. `grounded_anchor.trust_level ∈ {grounded, section-grounded,
ungrounded}` gates the fire — an `ungrounded` re-resolve can never fire.

**Verbal cues are an injected seam, not a model call.** Reading "kind of
distracted" or "raised *and* self-closed within one note" is model work; it lives
behind the `NightCueReader` Protocol (`read(note) -> NightCue`), exactly like
`SignalExtractor`. Tests inject an in-memory fake (`corpus.build_cues`).

**Corpus-level restraint** is the driver `drive_corpus(notes, retrieve, extractor,
*, book_id, cues, ignored_dates, window)`: it produces the candidate set once via
`detect_candidates`, buckets it by `source_note_date`, then walks the notes in
date order threading a **`MentorState`** (`cards_fired`, `consecutive_ignores`).
**Repeated ignores** are modeled as `ignored_dates` — the set of note-dates whose
*fired* card the learner later ignored (an inspectable, order-free representation;
only meaningful for dates a card fired on). Each consecutive ignore raises the bar
(**backs off**); a card that lands resets the streak; the bar never falls (**never
escalates**). Silence never counts as an ignore.

**Confidence-bar mapping (open seam, #55 calibration).** `trust →` {`grounded`:
1.0, `section-grounded`: 0.6}; `density_tier →` {`brief`: −0.15, `standard`: 0,
`deep`: +0.05}; `BASE_BAR` = 0.55; each ignore adds `IGNORE_STEP` = 0.15. The
numbers are provisional — what matters is the ordering they induce and that the
bar is monotone non-decreasing in the ignore streak.

## Layout

```
src/mathai/math_mentor/
  port.py         BookRetrieveFn (the retrieval Protocol / port)
  anchor.py       GroundedAnchor model + resolve_anchor + coordinate normalization
  adapter.py      PlatformBookRetrieve — the concrete platform-backed port
  signals.py      CandidateSignal + SignalExtractor port + kind→intent mapping (#69)
  detection.py    NoteView read-model + from_daily_note adapter + detect_candidates (#69)
  arbitration.py  MentorDecision + NightCue(Reader) + arbitrate + drive_corpus (#70)
tests/
  test_resolve_anchor.py   #68 AC coverage with an in-memory fake port
  corpus.py                the shared 10-note fixture (notes + fake port + fake
                           extractor + fake verbal-cue reader)
  test_detection.py        #69 AC coverage, driven off the corpus
  test_arbitration.py      #70 AC coverage, driven off the corpus
```

The `corpus` module is a **reusable** fixture (#70/#71 import it), not inline in
one test file — the canonical 2025-06-19..06-28 note window that realizes every
detection scenario. #70 extended it **additively** with `build_cues()` (the seeded
`NightCueReader`); the #69 builders are untouched.

## Tests

The resolver is tested entirely against an in-memory fake port (no live
platform):

```bash
uv venv --python 3.13 /tmp/mentor-venv
uv pip install --python /tmp/mentor-venv/bin/python pydantic pytest
uv pip install --python /tmp/mentor-venv/bin/python --no-deps \
  -e /ABS/PATH/ai-platform/packages/core \
  -e packages/math-book \
  -e packages/math-mentor
/tmp/mentor-venv/bin/python -m pytest packages/math-mentor/tests -q
```

## Open seams / judgment calls (settle with #55 calibration)

- `DEFAULT_SCORE_FLOOR = 0.35` — provisional; #55 calibrates real numbers.
- `section-grounded` sets `node_id=None` (no false precision — we only trust a
  node_id when it comes with an exact coordinate-label match).
- "Topically relevant" is operationalized as *clears the score floor*: the port
  is the sole data source and it already scoped by `book_id` + the query, so any
  hit above the floor is by construction a relevant hit for this query.

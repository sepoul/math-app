# 05 — Book skeleton & grounding

*The substrate every card leans on. This facet does not decide whether to speak,
or what to say — it answers one question for the facets that do: **"where in
which book is he, exactly, and how sure are we?"***

> One of six facets of the Mentor Loop (see #43). The loop's promise is
> "point at the **math**, never the app." That promise is only as good as the
> coordinate it points at. A directive that says *"redo the 3×3 grid (Hatcher
> §1.2)"* is trustworthy; the same directive pointing at the wrong section is
> worse than saying nothing. This facet owns the map that makes the pointing
> real — and owns the discipline of returning **nothing** when the map is unsure.

---

## The story

> **As the learner, I want the mentor's directives to land on the exact place in
> my book — the coordinates I already write down myself ("Problem 2.16", "§21.4",
> "Hatcher §1.2") — so that when it says *go back and redo this*, I trust it
> instantly and can flip to the page in seconds, instead of being sent on a
> wild-goose chase that makes me ignore the card forever.**

### The job & the moment

He studies from books, self-directed, no exams, no teacher. Every note he records
is *about a specific spot in a specific book* — and he tells us where, in his own
words, every time. The job of this facet is to be the **shared coordinate system**
the whole loop speaks in: take tonight's note, and resolve it to a precise,
trusted location in his actual library.

The moment is invisible to him. He never sees the skeleton; he never "opens" it.
It runs once, silently, the instant a note finishes synthesizing — *before* any
card is even considered. It produces the anchor that the repair card (#2), the
bridge card (#3), and the detector (#1) all read. When it gets the anchor right,
the loop feels like *"the app flipped back through my notebook and knows exactly
which page I'm on."* When it gets it wrong, the whole product dies — once.

---

## What a "book skeleton" concretely is

A **book skeleton** is a hand-curated, structured map of one book: its table of
contents as an ordered hierarchy, with the book's *numbered anchors* hanging off
it. Nothing more — **structure and labels, not the book's content.** No theorem
text, no proofs, no exercise statements (that would be a spoiler store, and it
isn't ours to hold). Just the scaffolding a tutor carries in their head:

- **The TOC hierarchy** — part → chapter → section, in reading order, each with
  its canonical number and short title. This is what lets us say "he's near the
  end" or "§21 comes after §19" without reading a single page.
- **Numbered anchors** under each section — the things he cites by number:
  theorems, propositions, definitions, and especially **exercises / problems**.
  Each anchor carries the *canonical coordinate string the book itself prints*
  ("Problem 21.4", "Exercise 1.2.4", "Theorem 1.20 (van Kampen)") and a short
  human label. That canonical string is the join key between his notes and the
  book.

Think of it as the index card a tutor would build before tutoring a student out
of a book they both own: *"chapter 21 is orientations; problem 21.4 is the
diffeo-pullback one; §1.2 of Hatcher is van Kampen, exercises 1.2.1–1.2.8."* Not
the math — the **addresses**.

### Grounded in his real corpus

He already writes these coordinates, unprompted, in the two places that matter
most — the **clean transcript** and **his own page headings** — and they survive
even when the surrounding OCR is garbage:

| Date | Where he wrote it | The coordinate (verbatim) | Note: OCR around it |
|---|---|---|---|
| 06-26 | page heading | **"Problem 2.16 — Orientationbility of a regular level set in ℝ^{m+1}"** | clean coordinate; prose elsewhere has noise like "216" |
| 06-25 | page text + spoken | **"Continuation of Problem 21.4"** / *"Problem 21.4… I don't wanna be spoiled"* | clean coordinate inside a rambly transcript |
| 06-27 | transcript | *"orientation on manifolds… §1"* (Tu) | section-level |
| 06-20 (math day) | transcript + pages | *"van Kampen's theorem… Massey"* / *"Hatcher"* | named book, theorem-by-name, no number |
| 06-28 (Sunday) | transcript | *"continuing the proof… of Van Kampen"* | the crux note; **no coordinate at all** — pure prose |

The pattern that defines this facet: **the coordinate he writes is the cleanest,
most reliable signal in the whole note.** "Problem 2.16" and "Problem 21.4" come
through perfectly even when the same pages OCR "Van Kampen" as *"V. european
hypothesis"* and degrade math into noise. So our grounding strategy is not "read
the page and figure out where he is" — it is **"find the address he already wrote,
and trust it over everything else."**

---

## How a note maps to a book location

A small, ordered resolution, **coordinate-first**, producing one of three trust
levels. (This facet defines the levels and resolves them; #1 decides what to do
with each — but the design only works if "grounded" genuinely means grounded.)

1. **Explicit coordinate → `grounded`.** He wrote a canonical address (in the
   transcript or as a page heading) that matches an anchor in a skeleton. *This
   is the high-trust path and the common case.* 06-25 → Tu Problem 21.4. 06-26 →
   Tu Problem 2.16. The coordinate **he** authored beats any inference.
2. **Book + section, no item number → `section-grounded`.** He named the book and
   a section/chapter but no specific anchor (06-27 "§1", or a theorem named not
   numbered). We resolve to the section node; usable for "you're in chapter 21"
   but not for "redo Problem 21.4."
3. **No usable coordinate → `ungrounded`.** Prose only (06-28: "continuing the
   van Kampen proof" — no number anywhere). We may *guess* a section from title /
   concepts / recent trail, but we **flag it low-confidence and hand back
   essentially "no anchor."**

**Which book** is resolved alongside the coordinate, by two cheap, reinforcing
signals: (a) the **track / topic** (manifolds-orientation-Lie-groups → Tu;
algebraic-topology / van Kampen → the AT book), and (b) the **coordinate grammar**
itself — `Problem N.M` / `§N` is Tu's house style; `§1.2` + `Exercise 1.2.4` is
Hatcher's. When grammar and topic agree, book is `grounded`; when they disagree
(see edge cases), we degrade rather than guess.

The output of this facet, per note, is a compact **location handle**: *which book,
which anchor (or section), and the trust level* — plus, for #6's benefit, *how far
through the book that anchor sits.* That handle is the entire contract; everything
downstream reads it and nothing else from here.

---

## Semi-manual, once-off ingestion (confirmed acceptable)

The skeleton is **built by hand, once per book, and curated to be right** — not
auto-extracted from a scanned book at runtime. The user explicitly blessed this:
*"get it right once with semi-manual processing."* That trade is the right one:

- A book's TOC and anchor numbering are **stable, finite, and authored once** —
  they don't change between sessions. The cost is paid a single time and amortizes
  over months of daily notes.
- A skeleton built from the **published front-matter TOC** (plus a pass to list
  the numbered exercises/problems per section) is *clean by construction* — no OCR
  noise, no hallucinated theorems. This is exactly the reliability the "wrong
  anchor is worse than none" rule demands; auto-OCR of the book body would
  reintroduce the very noise we're trying to escape.
- "Semi-manual" = a human (or an assisted pass he reviews) produces the structured
  map and **signs off on it**. Getting Problem 21.4 to actually be Problem 21.4 is
  a one-time verification, not a per-note risk.

**The library it must cover, concretely:**

- **Tu — *An Introduction to Manifolds*** (his daily book): sections §1…§N grouped
  into chapters; problems as "Problem ⟨section⟩.⟨n⟩". His live region is the
  orientations neighborhood (§21-ish) and regular level sets (Problem 2.16 area).
- **Hatcher — *Algebraic Topology*** (his Sunday book): chapters → §1.2-style
  sections; exercises as "1.2.4"; major theorems named (van Kampen).
- **A future next book** — the model must accommodate adding the book he moves to
  after Tu *by repeating the same once-off curation*, with no change to how notes
  resolve against it. (The *timing/trigger* of that switch is #6's call; this
  facet just guarantees "adding book N+1 is the same cheap, manual step.")

---

## Acceptance criteria — "done *and good*"

Behavioral, from the loop's point of view:

1. **The coordinate he wrote wins.** Given a note where he writes an explicit
   address (06-25 "Problem 21.4", 06-26 "Problem 2.16"), the resolved location is
   that exact anchor, `grounded` — even when surrounding OCR is garbled. We never
   override his clean coordinate with an inferred one.
2. **No false precision.** Given a prose-only note (06-28 van Kampen, no number),
   the facet returns at most a low-confidence section guess explicitly marked
   *not* `grounded` — never a confident wrong anchor. Downstream, this reads as
   "no anchor," which lets #1 stay silent.
3. **A `grounded` anchor is verifiably real.** Every coordinate we emit as
   `grounded` resolves to an actual node in a curated skeleton; we never surface a
   coordinate that exists in his note but not in the book (he may misremember a
   number — see edge cases).
4. **Right book, right grammar.** Tu notes resolve against Tu, Hatcher notes
   against Hatcher; "Problem 21.4" is never matched into Hatcher and "Exercise
   1.2.4" never into Tu.
5. **Position is available.** For any resolved location, the facet can report
   *roughly how deep in the book it is* (so #6 can sense "near the end of Tu")
   without that being this facet's decision to act on.
6. **Adding a book is cheap and isolated.** Onboarding the next book is the
   once-off manual curation and nothing else — no per-note logic changes, no
   re-tuning of how existing books resolve.
7. **The skeleton holds no spoilers.** It stores addresses and short labels, not
   theorem/exercise *content* — so the loop's no-spoiler guarantee can't be
   breached *through the grounding layer*.

---

## Design decisions & open questions

**Decided (within this facet's lane):**

- **Coordinate-first, his-words-first.** The join key is the canonical coordinate
  string he authors, read from the **clean transcript and his own page headings**,
  not reconstructed from OCR'd body prose. This is the single most important call
  and the real-data evidence is overwhelming.
- **Three trust levels** (`grounded` / `section-grounded` / `ungrounded`) as the
  shared vocabulary, so "we're not sure" is a first-class, *expressible* answer
  rather than a silent bad guess.
- **Hand-curated, signed-off skeletons**, one per book, content-free (addresses +
  labels), versioned so a correction or a newly added book is a deliberate edit.

**Open questions (flagged, not resolved here):**

- **Granularity of anchors.** Do we enumerate *every* numbered exercise/problem,
  or only sections + the theorems/exercises he's likely to cite? (Leaning: full
  exercise list for his two live books, since exercises are exactly what his
  directives point at — but it's a curation-cost call.)
- **How "depth / position" is expressed** — page numbers vs. ordinal section index
  vs. percent-through. Needs to be cheap and stable; #6 is the consumer, so the
  exact shape should be agreed with #6.
- **Cross-book theorem identity.** Van Kampen lives in *both* Hatcher and Massey
  (and his corpus shows him reading Massey for it on math-day, Hatcher on
  Sundays). Should the skeleton model "the same theorem in two books," or keep
  books strictly separate and resolve per-note by which book he names? (Leaning:
  strictly separate skeletons; resolve the book per note. But the loop should not
  send a Massey-night directive into Hatcher's numbering.)
- **Trust threshold for `grounded`** — exact string match only, or normalized
  (e.g. "Prob 21.4" ≈ "Problem 21.4", "section 21.4" ≈ "§21.4")? Normalization
  helps recall but must never promote a *wrong* match to `grounded`.

---

## Edge cases / failure modes

| Case (grounded in his corpus) | What goes wrong | How this facet handles it |
|---|---|---|
| **Prose-only note** (06-28: "continuing the van Kampen proof," no number) | We invent a section to look smart → confident wrong anchor → trust dies | Return `ungrounded` (low-confidence section guess at most); never `grounded`. Silence is correct here. |
| **Garbled OCR around a clean coordinate** (06-26: "216", "V. european") | Matcher latches onto noise instead of the real address | Read the coordinate from the **clean** channels (transcript, page *headings*) first; treat body OCR as last resort. |
| **He misremembers / mis-numbers** (cites "Problem 21.5" that isn't in Tu) | We emit a coordinate the book doesn't have → broken pointer | Only `grounded` if it resolves to a real skeleton node; otherwise degrade to `section-grounded` on the nearby section. |
| **Same theorem, two books** (van Kampen: Massey on math-day, Hatcher on Sunday) | Directive points at Hatcher §1.2 on a night he was in Massey | Disambiguate book by named book + coordinate grammar; if ambiguous, degrade — don't cross numbering systems. |
| **Topic not in any skeleton** (a side-reading, or a book we haven't ingested) | We force-fit into Tu/Hatcher | Return `ungrounded` with "book unknown"; the loop simply has nothing to ground on that night. |
| **Near the end of Tu** (~80pp left per the winner basis) | Stale skeleton; next book not yet ingested | Position is reportable (#6's signal); "no next book yet" is a known, explicit state, not a crash. |
| **Multi-topic note** (the synthesis can carry several sections) | Which single location? | Resolve **per topic/section** and expose the set; let #1 pick which (if any) to act on — we don't collapse to one prematurely. |

The throughline: **every failure mode degrades toward `ungrounded`, never toward a
confident wrong anchor.** That asymmetry — "a wrong anchor is worse than none" — is
the design center of gravity for this facet.

---

## Seams to adjacent facets (named, not designed)

- **→ #1 Detection & restraint.** I *hand off* the location handle (book, anchor
  or section, trust level, rough position). #1 *decides* whether to fire and uses
  my trust level as an input to its restraint ("`ungrounded` ⇒ lean silent"). I do
  **not** decide whether a card fires.
- **→ #2 The repair card / #3 The bridge card.** They *receive* the canonical
  coordinate string to render ("redo the 3×3 grid, Hatcher §1.2"; "prove SL(m) is
  a regular level set"). How the card *phrases* or *uses* the anchor — the
  directive, the tone, the bridge logic over the concepts trail — is theirs. I
  guarantee the coordinate is real and correctly attributed; I don't author copy.
- **← Existing ingest / synthesis.** I *receive* the note: transcript, page
  text/headings, the synthesis concepts trail, and magnitude. I read these to
  resolve location; I don't change how they're produced. (The concepts trail is
  #3's raw material for bridges; I only use it as a weak book-disambiguation hint.)
- **→ #6 Cadence & the finish-Tu pivot.** I *provide* the skeleton and a sense of
  "where in the book / near the end," and I guarantee "adding the next book is a
  cheap once-off." #6 *owns* the closed-book transition, the Tu→next-book timing,
  and where the Recall complement enters. I supply the substrate it reads; I don't
  trigger the pivot.
- **Platform boundary (§13).** The skeleton is **domain-owned data** (it lives
  with math_notes' interpretation layer, not the platform). Matching is
  coordinate-string + light normalization, **not** embeddings — there is no
  platform vector store today, and grounding deliberately doesn't need one. If a
  future facet wants fuzzy semantic matching, that's a new capability, out of this
  facet's once-off, content-free scope.

---

## In one line

This facet makes "go back to the book" **trustworthy** by building a clean,
hand-verified address book for Tu and Hatcher (and the next book), then resolving
each note to the coordinate **he already wrote** — and, crucially, saying *"I don't
know where this is"* out loud whenever it can't, so the loop stays silent instead
of pointing at the wrong page.

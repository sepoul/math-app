# 07 — The Skeptic / Pre-mortem

*Lens: a skeptical principal PM running a pre-mortem. The other six docs are
advocacy. This one is the counter-narrative — not to kill the idea, but to
protect the decision before anyone spends weeks building "the map."*

---

## The bet I'm challenging

> *"Book-grounded notes": ingest the book, anchor his sparse breadcrumbs to its
> dense structure, and close a reinforcing loop that redirects him back into the
> book."*

I went and read his actual notes first. **The premise doesn't survive contact
with the data.** His notes are not sparse breadcrumbs that need anchoring, the
"where am I" problem he supposedly has doesn't appear, and — twice, in his own
voice — he explicitly asks the app *not* to do the one thing the mentor-loop
half of the bet wants to do. We are at risk of building a heavyweight product to
solve problems this learner does not have, paid for out of the one budget he
*can't* spare: the daily hour and the two-week-old logging habit.

---

## The job & the moment — interrogated

The bet assumes two jobs. Walk each against the corpus (10 notes, 2026-06-19 →
06-28).

**Job A — "give me visibility / a map so I know where I am."** He already knows
exactly where he is. He's ~80 pages from the end of Tu, working linearly through
the *Orientation* chapter. His own notes are *titled by the book's own
coordinates*: "Problem 2.16," "21.4," "Example 21.6," "§81.5," "2.14 Orientation
preserving diffeomorphisms." **He logs the page/section himself, as an existing
habit, on nearly every page.** A solo hobbyist reading one book front-to-back
does not get lost — and this one is meticulously self-located. The map mostly
re-derives coordinates he already writes down.

**Job B — "detect when something's off and redirect me to re-study."** This is
the half the data actively contradicts. On 06-25: *"this is a message for you,
synthesists… don't spoil the last exercise. I'm working on it, please."* On
06-24: *"don't spoil… I wanna take my time trying to figure it out alone if
possible."* He treasures *productive struggle*. A mentor that says "go redo
§9.3" risks spoiling the exact thing he values. **The most active version of the
bet is the one his own words veto.**

So *when* does he reach for this? The honest answer from the data: **never,
unprompted.** He reaches for his phone to *record* (voice + photos) — that ritual
is real and daily. He reads notes back only "now and then" (his words; a
two-week-old habit). There is no observed moment of "I'm stuck, let me consult
the map." We'd be manufacturing the moment, then hoping he shows up for it.

---

## The experience / the aha — does it actually land?

The advocacy docs promise an aha: the lit-up territory, the trail across the
book. Two reasons to doubt it lands for *this* person:

**1. The app's current output is already excellent — the marginal aha is
small.** Look at what synthesis does *today* with his garbled OCR. His page reads
*"Our V. european hypothesis tell us…"*; the synthesis silently corrects it to
*"the van Kampen hypothesis,"* reconstructs the Lebesgue-number argument, splits
it into seven titled sections, and extracts 25 precise concepts (06-28). That is
the magic moment, and **it already exists.** "Anchoring to the book" is a thinner
delta on top of a product that is already doing the hard, valuable thing.

**2. A wrong anchor is worse than no anchor.** The whole bet rests on
note→section mapping, and the substrate is *that same garbled OCR*: "216" for
"2.16," "81.5," "V. european," "Von Kamps Theorem." Auto-mapping onto a book's
structure from text this noisy will misfile pages. For a precise mathematician,
a map that confidently puts his Van Kampen work under the wrong section isn't
neutral — it's an irritant that erodes trust in the whole surface.

---

## The leanest test (instead of an MVP)

**The core assumption to test, before building anything: does anchoring notes to
the book actually change his behavior?** Specifically Job A — because Job B is
already contradicted, and if the *cheap* visibility nudge doesn't move him, the
*expensive* mentor loop is dead on arrival.

**Test: a Wizard-of-Oz weekly digest. Zero new build.** Once a week, assemble —
by hand or a one-shot LLM call over the artifacts the app *already* produces — a
short email:

> **This week in Tu — *Orientation*.** 4 sessions. Open thread you left
> unfinished Thu: the non-vanishing top form on a regular level set (§2.16).
> ~80pp to the end of the book. Sunday side-track: Van Kampen, surjectivity case
> done.

No book ingestion, no map UI, no graph, no prescriptions. It reuses the existing
`concepts`, `sections`, and the page numbers *he* writes. Run it for **4 weeks,
n=1**, and read three signals:

1. **Does he open it / read to the end?** (Appetite for backward-looking,
   book-anchored visibility at all.)
2. **Does it change next-week behavior?** More sessions; does he ever *revisit* a
   flagged open thread? That's the reinforcing loop — observed or not.
3. **Does he ask for *more* anchoring, or ignore it?** Pull, not push.

If all three are flat after a month, we've spent ~zero engineering to learn the
big map wouldn't have paid off. If even one fires, *now* we know which half of
the bet to build, and we've de-risked the most expensive decision in the slate.

A leaner variant if even the email is too much: add a single derived line —
**"Tu · Orientation · ~80pp left"** — to the existing note view, computed only
from page numbers he already logs, and watch whether he ever mentions it.

---

## Why running the pre-mortem first wins

It doesn't win a product — it protects the other six. The skeptic's value is
*sequencing*: a one-week, build-nothing test sits in front of a multi-week map /
mentor / graph build and tells us whether the foundational assumption is even
true for the only user we have. **The cheapest thing the learner explicitly
asked for is "vanity visibility over my progress" — that's a digest line, not a
cartographic substrate.** Build the cheap thing he named, measure, and let the
data — not seven enthusiastic docs — license the expensive thing.

---

## Risks / why this skeptical view might itself be wrong

Steelmanning the bet, fairly:

- **Latent needs don't show up in two weeks of logs.** Strava wasn't a felt need
  before it existed either. Visibility may *compound* over months in a way a
  10-note corpus can't reveal; absence of a "stuck" moment isn't proof one won't
  emerge.
- **The cross-book dot-connecting is real and latent.** His practice *is* Tu ↔
  Hatcher in parallel (manifolds weekdays, algebraic topology Sundays), and he
  says he likes "connecting dots." A concept/book substrate is plausibly the
  only thing that surfaces *that* — and a backward-looking digest won't.
- **The "don't spoil" plea cuts both ways.** It vetoes a prescriptive tutor, but
  it's also proof he *engages emotionally* with the app as an interlocutor. A
  loop that nudges *backward* ("you left this open") rather than *forward*
  ("do this next") might thread the needle the digest only gestures at.

The honest position isn't "don't build it." It's **"don't build the big version
on faith; run the one-week test that tells us which version, if any, he'll
actually pull on."**

---

## Napkin sketch (the *test*, not a product)

```
  EXISTING ARTIFACTS                 WIZARD-OF-OZ (manual, weekly)
  ┌────────────────────┐             ┌──────────────────────────────┐
  │ daily_note ×N      │             │  ✉  "This week in Tu"        │
  │  • sections        │  ── 1 LLM ─▶│  • 4 sessions · §2.16        │
  │  • concepts        │    call or  │  • open thread: non-vanishing │
  │  • page #s (his)   │    by hand  │    form (you left it Thu)    │
  └────────────────────┘             │  • ~80pp to end of book      │
                                     └──────────────────────────────┘
        MEASURE  ── opens it? ── revisits a thread? ── asks for more? ──▶ decide
                     │                │                    │
                  all flat  →  the big map wouldn't have paid. Stop.
                  any fires →  build *that* half. Now licensed.
```

No map. No graph. No "go do exercise 9.3." One email, four weeks, then a
data-backed go/no-go.

---

## Fit to his practice

- **The daily ritual is the asset — don't tax it.** His one constrained resource
  is the hour. Every new surface that must be *tended* (a map, a graph, a streak,
  a chat) competes with study time *and* with a logging habit only two weeks old.
  The corpus already shows the ritual is brittle: on 06-20 he dropped photos
  mid-session — *"not adding a photo this time. The photos are huge and they're
  bugging the application."* He sheds parts of the ritual the instant friction
  appears. A digest is the only candidate that adds **zero** daily surface — it's
  pull, asynchronous, and skippable.

- **Even the habit we're betting on already skipped.** In its first two weeks the
  logging shows a 3-day gap (06-21 → 06-23). We're proposing to build a product
  *on top of* a behavior that isn't yet reliable. Stabilize and reward the
  logging before we couple a map to it.

- **The transition is the worst possible moment to ship a single-book map.**
  He's ~80pp from finishing Tu and about to pick a new topic. A map keyed to
  Tu's structure resets to empty exactly when he's most in flux — and his real
  pattern is *hopping and connecting across* books (Tu, Hatcher, an abandoned
  Lean detour), not dwelling inside one. A single-book atlas fights his actual
  behavior; a digest survives the topic change untouched.

- **n=1, ~10 notes, ~10 days.** We are one user and two weeks of data away from
  committing weeks of build. The skeptic's whole job is to insist the next
  decision cost *less* than the data we have can justify — and then go get more
  data, cheaply, before the big bet.

---

*Bottom line: the existing synthesis is already the magic. Ship the cheapest
thing he literally asked for — a book-anchored weekly digest — measure whether
anchoring changes his behavior at all, and let that one-week result license (or
retire) the map, the mentor, and the graph the other six want to build.*

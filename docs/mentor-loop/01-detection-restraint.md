# 01 — Detection & restraint

*Facet 1 of the Mentor Loop (see #43). The brain that decides **whether** to
surface a card at all, and **which kind**. This story owns the IF and the WHICH —
not the card's wording.*

> Where this sits in the loop: **Detect → one move → carry → close.** This facet
> is the first verb. Everything downstream (the repair card #2, the bridge card
> #3, the carry/close mechanic #4) only runs if detection decides to speak —
> which, on most nights, it doesn't.

---

## The story

> **As the learner**, when my voice note synthesizes at the end of a session, I
> want the mentor to stay **silent unless it has caught something that genuinely
> matters** — a hard step I quietly abandoned, a proof I admitted I'm unsure of,
> or two threads that have secretly grown into one — **so that** the one night it
> does speak, I trust it completely and act, instead of learning to swipe past a
> nightly nag.

**The job:** protect the value of the card by spending it rarely. A solo learner
with no exam and no teacher has no external signal for *which* gaps matter; the
mentor's entire credibility rests on the gap it points at being real. The job of
detection is to be the gatekeeper that makes "the mentor spoke" mean something.

**The moment:** invisible to him by design. He taps record, talks, and the
synthesis runs. Detection happens inside that existing pass. The *only* moment he
experiences is the rare one where a card has earned its place at the bottom of
tonight's note — and the much more common one where there's nothing extra, just
his synthesized note as always. The restraint *is* the feature: he never sees the
nights we decided to stay quiet, and that's exactly why he believes the nights we
don't.

---

## The default is silence

The single most important behavior in this facet: **most nights, nothing fires.**

Across his real 10-note corpus (06-19 → 06-28), detection should surface **at
most two cards total** — not two per week, two across the whole window. If a
naive version fires on five or six of these notes, it is broken, no matter how
"reasonable" each individual card looks. Silence is the correct output for the
large majority of sessions, including good, dense, productive ones.

This inverts the usual product instinct (more engagement = more surfaces). Here,
**a wrong card is strictly worse than no card**, because of an asymmetry in cost:

- A **missed** card costs *one* re-engagement opportunity. It's recoverable — the
  gap is still there tomorrow, and the same or a louder signal can catch it next
  session.
- A **wrong** card costs *the instrument*. The first time he reads "redo the 3×3
  grid" about a step he actually nailed, or gets assigned homework on a 15-minute
  distracted day, he reclassifies the mentor as noise and swipes past every card
  forever. The loop dies on a single false positive.

So the operating rule is **precision over recall, and when in doubt, silence.**
Detection is tuned so that a fired card is almost always right, accepting that it
will miss real gaps it wasn't confident enough about. The bar is not "is there
plausibly something here?" — it's "would I bet the mentor's credibility on this?"

---

## What earns consideration: the signal taxonomy

Detection recognizes a small, sharp set of signals. Each is **anchored in his
actual transcripts** (clean ASR of his own voice — see "Why this is detectable"),
not inferred from page OCR. Two of the three are *repair-eligible* (a gap to
catch); one is *bridge-eligible* (a connection to offer).

### 1. Abandoned crux — *repair-eligible, highest confidence*
An explicit verbal surrender at a load-bearing step: he names the hard part and
then says he's going to move on without securing it.
- **Real fire — 06-28:** *"this is a bit harder… I think next time I will just
  keep moving and assume I got it."* He himself frames it as *"the hardest part
  of the proof"* (the well-definedness step of van Kampen — the crux, not a
  detail). Deep note, 4 pages, real work done, *then* the hedge. This is the
  flagship repair trigger.
- Confidence is highest here because the signal is **his own words, explicit, and
  about a step he himself flagged as hard.** Little room to misread intent.

### 2. Unverified proof — *repair-eligible, high but not highest*
Explicit doubt about the correctness of his *own* argument.
- **Real fire — 06-27:** *"Honestly, not really sure about the correctness"* —
  about proving Lie groups are parallelizable / orientable via a left-invariant
  frame.
- Confidence is a notch lower than the abandoned crux, because doubt is not
  abandonment: he may well verify it himself next session. This raises the bar
  (see "the trailing window") — detection should prefer to wait one note to see
  if he self-resolves before spending a card.

### 3. Ripe cross-track bridge — *bridge-eligible, lowest urgency*
A concept that has recurred across **both** of his tracks (manifolds / Tu and
algebraic topology / Hatcher–Massey) with enough independent touches over enough
span that the connection is genuinely "ready to be named."
- **Real fire — the determinant chain:** `determinant` and its avatars thread the
  whole corpus across both tracks —
  - 06-19: *change-of-basis determinant* (defines pointwise orientation),
    *transition-map Jacobian*;
  - 06-24 / 06-25: *Jacobian determinant*, *multiplicativity of the determinant*,
    orientation-preserving via positive Jacobian;
  - 06-20 (algebra track): *determinant homomorphism*, *SL(m) = ker(det)*, GL(m)/SL(m)
    via the first isomorphism theorem;
  - 06-26 / 06-27: regular level sets and Lie-group frames.

  Four-plus independent touches, both tracks, ~10 days. The latent connection
  (e.g. *SL(m) is itself a regular level set of det*) bridges the algebra
  quotient/kernel work to the manifolds regular-level-set work. **This is real
  in his concept trail**, which is what makes a bridge trustworthy.
- A bridge is never urgent — it's durable and can wait indefinitely for a quiet
  night. It therefore loses every arbitration to a live repair (see below).

> **Lane note:** the *traversal that finds* a bridge candidate from the `concepts`
> trail belongs to facet #3. This facet owns only the **restraint over** bridge
> candidates: the ripeness bar a candidate must clear to interrupt silence, and
> whether it wins tonight's single slot. See seams.

---

## What looks like a signal but must stay silent

Equally part of this facet: the **anti-patterns** that a careless detector would
fire on and shouldn't. Each is grounded in a real note.

| Real note | What it looks like | Why it stays **silent** |
|---|---|---|
| **06-24** — *"distracted… 15 minutes from the session"*, *"I have not finished the proof yet, so don't spoil"* | a real in-progress, unfinished proof | Short, distracted, low-effort day **and** in-progress by intent. "Not finished yet" is honest work he'll continue, **not** abandonment. Homework here is pure tax. Canonical restraint case. |
| **06-26** — *"I had to look at some examples on a sphere… but I kind of figured it out"* | a struggle, a backtrack | **Resolved** struggle. He backtracked *and closed it* (*"this allowed me to prove that the form is well defined"*). That's a success, not a gap. Don't reward effort with homework. |
| **06-25** — *"I wanna take my time trying to figure it out alone if possible"*, `dont_spoil` | an open, unsolved exercise | **Deliberately** in progress. He explicitly asked for room. Firing would violate his stated wish *and* the no-spoiler rule. |
| **06-20 (math-day opener)** — *"I didn't read it well in the theorem itself"* | a skipped prerequisite | Real at that instant — but **he self-corrected within the same day** (a later 06-20 session: *"I read the van Kampen theorem announcement"*). A same-day fire would be stale on arrival. |
| **06-19**, steady-progress notes | dense, lots of concepts | Productive learning with no hedge and no doubt. **Density is not a gap.** Don't fire just because a lot happened. |

The throughline: detection reads the **resolution clause**, not the
effort-language. "This is a bit harder… *I'll just assume I got it*" (06-28) is
abandonment. "It's a bit harder… *but I kind of figured it out*" (06-26) is
victory. The hard-sounding phrase is identical; the clause after it is the entire
decision.

---

## Why this is detectable (the precision bet)

The bet that precision-over-recall is *achievable*, not just desirable, rests on
one structural fact: **his triggers live in the transcript, not the page OCR.**

- His hedges are **spoken, explicit, and quotable**: *"assume I got it,"* *"not
  sure about the correctness,"* *"didn't read the statement itself."* These come
  from clean ASR of his own voice — the least-noisy signal in the corpus.
- The mentor-loop's failure-prone cousins (anything that map-matches noisy page
  text like `216` or `V. european`) are *not* this facet's inputs. Detection
  keys off what he **said**, and anchors off the coordinates he **writes/says**
  ("chapter Orientation," "the last exercise"), never garbled OCR.

This is why a high-confidence-only policy can still catch the cases that matter:
the cases that matter announce themselves in plain words.

---

## Decision flow (the IF and the WHICH)

For each synthesized note, in order:

1. **Scan** tonight's note for repair-eligible signals (abandoned crux,
   unverified proof) and consume any bridge candidate offered by #3.
2. **Suppress the anti-patterns** — resolved struggle, deliberate in-progress
   work, `dont_spoil`-protected exercises (for *that* exercise), low-magnitude /
   distracted days.
3. **Trailing-window check** — would this fire target something he already closed
   himself in a recent note? If so, drop it (stale).
4. **Threshold** — does the surviving signal clear its (per-category) confidence
   bar *and* the "worth interrupting silence" bar? If not → **silence.**
5. **Arbitrate to one** — if more than one signal survives, choose exactly one
   (next section). The losers are **preserved, not discarded** (a ripe bridge
   stays ripe).
6. **Require an anchor for a repair** — if the gap can't be tied to a nameable
   coordinate (from #5), a repair doesn't fire (a bridge still can — it points at
   concepts, not a single exercise).
7. **Hand off** the single chosen signal (with its evidence quote, category,
   anchor, magnitude/context, confidence) to the matching card facet — or emit
   nothing.

### One-card-max arbitration
When several signals fire the same night (realistic — on 06-28 the abandoned crux
*and* the now-ripe determinant bridge both qualify), exactly one card surfaces.
Priority:

1. **Live repair — abandoned crux** (a gap he's about to walk away from *tonight*;
   most perishable).
2. **Live repair — unverified proof.**
3. **Ripe bridge** (durable; can always wait).

Tie-break within a tier by **recency** then **crux-severity** (is the step
load-bearing?). The principle: **catch the perishable thing now; the durable
thing keeps.** On 06-28, the repair wins and the determinant bridge is held for a
quieter night.

---

## Acceptance criteria (done *and good*)

Behavioral, checkable against the real corpus:

- **Fires on 06-28:** exactly one repair-eligible signal (abandoned crux), at high
  confidence, carrying the quoted hedge and a nameable coordinate.
- **Silent on 06-24** (distracted, 15 min, in-progress, `dont_spoil`).
- **Silent on 06-26** (resolved struggle).
- **Silent on 06-25** (deliberate in-progress, `dont_spoil`).
- **Not stale on 06-20** — does not fire a "read the statement" repair that he
  already self-closed later the same day.
- **Corpus-level restraint:** across the 10 notes, **≤ 2 cards total**, and
  **never two on one night.**
- **Arbitration works:** when a live repair and a ripe bridge coincide (06-28),
  exactly one card (the repair) surfaces and the bridge is preserved, not dropped.
- **No hallucinated gaps:** detection never fires on a hedge that isn't actually
  in the transcript; every fired signal carries the verbatim evidence line.
- **Threshold, not weak cards:** a below-bar signal yields *no signal*, never a
  hedged/low-confidence card pushed downstream.
- **Self-regulation:** if he ignores cards repeatedly, detection backs *off*
  (raises the bar / goes quieter), never escalates.

---

## Design decisions & open questions

**Decided (proposed):**
- **Silence is the default**, and the cost asymmetry (wrong ≫ missed) is the
  governing principle. Tie → silence.
- **Per-category confidence bars**, not one global bar: abandoned-crux lowest
  (explicit + verbal), unverified-proof higher (doubt ≠ abandonment), bridge
  gated on a ripeness measure (touch-count × track-spread × span).
- **`dont_spoil` is a detection input, not only a synthesis guard:** on a note
  carrying it, repair targeting *that* exercise is suppressed (he asked for room);
  an unrelated bridge is unaffected.
- **Magnitude modulates the bar, doesn't veto:** a `brief`/distracted day raises
  the bar (06-24 stays silent); a `deep` day where real work preceded the hedge
  is the sweet spot (06-28 fires). But tier alone never decides — a short
  transcript can still be a dense breakthrough (06-20's 1-page, 2325-char note is
  `brief` by page-count yet substantive), so magnitude is a dial, not a gate.

**Open questions (flagged for the build epic):**
- **Trailing-window size:** how many notes back does detection look to decide a
  signal is "already self-closed" before firing a repair? (1–2 notes proposed.)
- **Adversarial self-check:** should detection run a second "try to refute this
  gap — is it really abandonment, or productive struggle?" pass before
  committing, given precision-over-recall? (Leaning yes.)
- **Cooldown ownership:** after a card fires, how many nights of enforced silence
  protect the "most nights nothing" feel even if new signals qualify? This is
  partly cadence's (#6) — seam below.
- **Unverified-proof timing:** fire same-night, or always wait one note for
  self-verification? (Leaning: wait one note unless the doubt is paired with an
  abandonment cue.)
- **Calibration over time:** as the corpus grows past 2 weeks, do the bars need to
  drift, or is the ≤~1-card-per-several-sessions rate stable?

---

## Edge cases / failure modes

- **Multiple signals, one night** → one-card arbitration (above); losers
  preserved.
- **Rhetorical ease-language misread** ("easy to believe") → read the resolution
  clause, not the adjective; 06-26 (resolved) vs 06-28 (abandoned) is the test.
- **Stale signal** (already self-closed, e.g. 06-20 prerequisite) → trailing-window
  suppression.
- **No resolvable anchor** → repair doesn't fire (can't say "redo X" without
  naming X); bridge may still fire.
- **Repeated ignores** → back off / raise the bar; never escalate or stack cards.
- **Over-firing on a great night** → density ≠ gap; a rich `deep` note with no
  hedge stays silent.
- **Magnitude false-low** → don't let a low tier alone veto a substantive note.
- **Hallucinated hedge** → require a verbatim transcript quote as the fire's
  evidence; no quote, no fire.
- **Cold start** → with only ~10 notes, bridges need accumulation; expect
  repair-only early. Detection must be alive and *correct* (mostly silent) from
  note one, not wait for mass.

---

## Seams (what I hand off / receive — named, not designed)

- **→ #2 (Repair card):** I hand off a **repair-eligible signal** — category
  (abandoned-crux | unverified-proof), the verbatim evidence quote, the
  resolved anchor, magnitude/context, and a confidence. #2 owns the card's
  anatomy, the firm-but-on-his-side tone, the no-spoiler phrasing, and the "I'll
  ask Sunday" close. *I decide there's a gap worth a directive; #2 writes the
  directive.*
- **↔ #3 (Bridge card):** #3 **proposes** bridge candidates from the `concepts`
  trail (the determinant chain) with a ripeness measure and wording; I **gate**
  them — the bar a candidate must clear to interrupt silence, and whether it wins
  the single slot vs. a live repair. *#3 finds and words the connection; I decide
  if/when it's allowed to speak.*
- **↔ #4 (Loop close):** I produce the **initial fire**; #4 owns the carry-forward
  banner, the one-tap states, and inferring closure of an **already-surfaced**
  card. There's a feedback edge: #4's closure/ignore signal feeds back into
  detection as cooldown / back-off / "don't re-fire a closed loop." Note the
  distinction — my *trailing-window self-close* (he closed it before any card
  existed) is upstream of #4's *close an open card*; both reduce noise, at
  different points.
- **← #5 (Book skeleton & grounding):** I **consume** anchor resolution — the map
  from "van Kampen well-definedness" to a nameable coordinate ("§1.2 / Ex 1.2.4").
  I require an anchor as a *precondition* for a repair fire; I don't build the TOC.
- **↔ #6 (Cadence, fit & restraint):** I gate on **signal merit** (is this gap
  real and worth a card?); #6 gates on **rhythm** (does the daily/Sunday/math-day
  cadence allow a card now, and is the anti-nag cooldown satisfied?). Either can
  veto. Cooldown specifically straddles us — I own "did I just fire," #6 owns the
  rhythm shape.

---

*Out of my lane (named, not designed): the repair card's anatomy and tone (#2),
the bridge card's wording and concept-graph traversal (#3), the carry/close
mechanic and closure inference (#4), the book-anchor substrate (#5), the cadence
fit (#6). This story decides only **whether** the mentor speaks tonight and
**which** kind of signal earned it.*

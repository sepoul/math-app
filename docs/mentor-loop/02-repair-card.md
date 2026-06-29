# 02 — The repair card

*Facet 2 of the Mentor Loop (#43). The directive that catches an abandoned or
hedged hard step and turns it into one move back into the book.*

> Sibling facets, named here only as seams (not designed here): **#1** decides
> *whether* a card fires tonight and hands me the signal; **#3** is the other
> flavor of card (the cross-track bridge); **#4** owns the carry-forward banner
> and closure. This doc owns one thing: **what a great repair card looks and
> feels like.**

---

## The story

> **As the learner**, when I quietly bail on the crux of a proof — *"I'll just
> keep moving and assume I got it"* — **I want** the bottom of tonight's note to
> catch it by name and hand me **one** concrete move back into the book, **so
> that** the hard step gets finished instead of calcifying into a gap I never
> revisit.

**The job.** A solo, exam-free learner has no one to say *"not so fast."* The
failure mode of that life isn't forgetting — it's **skipping the hard part and
believing he didn't.** The repair card is the voice that holds him to the book at
the exact moment he decides to walk past the crux.

**The moment.** He finishes a session and taps record. The synthesis runs (the
existing magic). Tonight, because he hedged, the note ends not with a tidy
summary that lets him off the hook but with a short, firm card that names the
bluff and gives him the next move. He doesn't go looking for it — it lands where
he already reads.

This facet is **not** the decision to speak (that's #1) and **not** the loop
mechanics (that's #4). It is the **content, shape, and tone of the directive
itself**: given that a repair *should* fire, what does it say, and why is it good?

---

## Anatomy of a repair card — four beats + a clause

A repair card is short enough to read in ~10 seconds and is built from four beats
in order, with one tone-carrying clause woven through. The flagship, grounded in
the real **06-28 van Kampen** note:

> **⟳ Not yet.** You said you'd *"just keep moving and assume I got it"* on the
> well-definedness step. **That step *is* van Kampen** — the rest is bookkeeping.
> → Redo the 3×3 homotopy grid by hand (Hatcher §1.2), then **Exercise 1.2.4**.
> You already nailed the triple-intersection trick; close this and the proof is
> yours. *I'll ask Sunday.*

| Beat | Job | In the flagship |
|---|---|---|
| **1. The catch** | Name the abandoned/hedged step back to him — ideally **in his own words** — so he feels *read*, not lectured. Anchor to the *specific step*, never the whole topic. | *"You said you'd 'just keep moving and assume I got it' on the well-definedness step."* |
| **2. The why-it-matters** | One sentence of stakes that a mathematician would agree with — distinguishes **crux from detail**, so the catch reads as a tutor who knows the terrain, not a nag. | *"That step **is** van Kampen — the rest is bookkeeping."* |
| **3. The one move** | **Exactly one** concrete, book-rooted action, doable in a single sitting: reread §X / redo the figure / do exercise Y / verify against the statement. A pointer, **never** a worked step. | *"Redo the 3×3 homotopy grid (Hatcher §1.2), then Ex 1.2.4."* |
| **4. The close** | A forward commitment with a **when** — turns a tip into an appointment. (The card emits the *line*; #4 owns the mechanism.) | *"I'll ask Sunday."* |
| **+ the on-his-side clause** | Cite **one specific real thing he got right** (from the same note) — proves the read was deep and reframes the catch as *finishing what he started*, not a grade. | *"You already nailed the triple-intersection trick; close this and the proof is yours."* |

The clause is the whole personality: **it caught him, but it's on his side.** Drop
it and the card grades him; keep it and the card finishes him.

### The two real flavors (same shape, different catch + move)

The repair card catches two distinct signals in his actual corpus. The four-beat
shape is identical; beats 1 and 3 change.

- **Abandonment** — he *explicitly says he'll skip*. Grounded: **06-28**, *"I'll
  just keep moving and assume I got it."* Catch quotes the bail; move is a
  **redo/do** ("redo the grid, then Ex 1.2.4").
- **Unverified / hedged proof** — he *finished but doubts it's right*. Grounded:
  **06-27**, *"honestly, not really sure about the correctness"* (Lie groups
  parallelizable via a left-invariant frame). Catch quotes the doubt; move is a
  **verification** move — *"Check your left-invariant-frame argument against Tu's
  statement of parallelizability; if the global frame holds, orientability is the
  one-line corollary."* Still no answer — it points at the statement to check
  against, not the proof.

---

## How it stays a *move*, never an *answer*

The platform already ships a `dont_spoil` learner-directive flair
(`packages/math-notes/src/mathai/math_notes/models.py:35`; wording lives in the
prompt registry as `math_notes.flair.dont_spoil`) that steers synthesis away from
finishing or revealing an unfinished exercise. **The repair card inherits that
guarantee structurally — I lean on it, I don't re-litigate it.**

The consequence is liberating, not constraining: because the answer is *already
off the table*, the directive is free to be **maximally directive** — point hard
at the book — with **zero risk of over-telling.** Every move the card can emit is
one of a small, safe vocabulary:

- *reread* a section / *redo* a figure by hand,
- *do* a named exercise,
- *verify* a finished proof against a book statement,
- *read the statement first* when he jumped into a proof without it (grounded
  pattern: **06-20**, deep in a proof he hadn't read the statement of).

None of these is a step of the solution. The card never contains a line of the
proof or the exercise's answer. (See **Open questions** for whether a repair on a
*live, unfinished* thread should assume `dont_spoil` semantics even when the
learner didn't attach the flair.)

---

## Acceptance criteria — "done *and good*"

A repair card is good when, behaviorally:

1. **It names the specific step**, not the topic. On 06-28 it says
   *"well-definedness step,"* not *"van Kampen."* If there is no nameable step to
   point at, there is no card.
2. **It quotes him.** The catch reuses his actual phrase (*"assume I got it,"*
   *"not sure about the correctness"*) so the recognition lands. No quotable
   signal → no honest catch → no card (handed back to #1, see seams).
3. **It states why the step matters** in one line a mathematician would sign off
   on (crux vs. bookkeeping).
4. **It prescribes exactly one move** — doable in a single session, anchored to a
   book coordinate (figure / section / exercise), **never the answer.** No second
   "while you're at it" move.
5. **It celebrates one specific real thing** from the same note (the
   triple-intersection trick on 06-28), never generic praise.
6. **It closes with a concrete when** ("I'll ask Sunday"), not a vague "later."
7. **It contains no spoiler** — verified by leaning on `dont_spoil`; the move is a
   pointer, the card holds no solution step.
8. **It's short** — one catch, one why, one move, one close, one clause; readable
   at the bottom of the note in ~10 seconds (≈4 lines). No bulleted homework list.
9. **It passes the human-tutor gate**: would a good human tutor who'd read his
   notebook say *exactly* this? If it reads as a grade, a generic "good job," or
   an "if you'd like…," it fails.
10. **On the hedged flavor (06-27)** the move is a *verification-against-statement*
    move, and it still passes 4 and 7.

---

## Design decisions & open questions

**Decisions (taken in this facet):**

- **Quote-first.** The catch *must* be built on a phrase the learner actually
  said. The recognition ("the app flipped back through my notebook and knows
  which page I'm bluffing on") is the product; a generic catch destroys it. This
  also makes the card **self-policing**: no quotable bail/doubt → no card.
- **The on-his-side clause is mandatory, and specific.** A repair card without a
  grounded celebration is a downgrade, not a card — it's the difference between a
  tutor and a scold. Generic praise ("great work!") fails; it must cite a real
  thing from tonight's note.
- **One move, sized to the day.** Exactly one move (hard rule: one card max, and
  within the card, one move). On a light/distracted day the move shrinks (reread
  one page, not "do the exercise") — magnitude is on the artifact
  (`density_tier`), grounded by **06-24** (*"distracted… 15 minutes"*). Whether
  the card fires *at all* on such a day is #1's call; *sizing the move* is mine.
- **Two flavors, one shape.** Abandonment and unverified-proof share the four-beat
  anatomy; only the catch line and the move-verb differ. This keeps the card
  recognizable as "the mentor's voice" regardless of trigger.
- **Voice register.** The card speaks in **first person** ("I'll ask Sunday") and
  sits *below* the synthesis's neutral silent-corrector prose — it is the one
  place the mentor steps forward and addresses him directly.

**Open questions (flagged, not resolved here):**

- **Implicit `dont_spoil` on live threads?** When the note is an in-progress
  proof but the learner *didn't* attach the flair, should the repair card still
  render under no-spoiler semantics? *Lean yes* — move-not-answer is intrinsic to
  a repair card. Needs a ruling shared with #1 (it owns flair/signal intake).
- **Which crux when there are two?** If a note abandons two steps, the card names
  the **most load-bearing** one (the crux that calcifies), not the one he'll hit
  first. Open: is "load-bearing" inferable reliably, or does it need #5's book
  structure to rank? (Seam to #5.)
- **How firm is too firm?** "Not yet" / "don't move on" is the intended register.
  Does any phrasing ever tip into bossy for *this* learner (a hobbyist doing this
  for love)? A tone dial may belong upstream; the card ships one calibrated voice
  and we watch the one number that matters — **did he act on it.**
- **Stale-by-read-time.** He may have done more in the same session before the
  synthesis runs. Phrasing the move as *"before [next checkpoint]"* makes it
  robust to partial completion; open whether the card should ever soften to
  *"if you haven't already…"* (risks diluting the firmness).

---

## Edge cases & failure modes

| Case (grounded) | Risk | How the card handles it (my lane) |
|---|---|---|
| **He resolved it himself** — 06-26, *"I had to look at the sphere examples… but I kind of figured it out."* | A card scolding a *solved* problem is corrosive; one wrong card burns trust permanently. | The catch needs an **explicit** bail/doubt phrase to quote. 06-26 has none (it's a *success* narration) — so there's nothing honest to catch, and the card **declines to render rather than invent a catch.** (Firing is #1's; my contribution is *refusing to fabricate.*) |
| **Short / distracted day** — 06-24, 15 active minutes. | Assigning an exercise on a 15-minute day is tone-deaf and feels like a tax on a hobby. | If a card fires at all, the **move shrinks to the day** (reread one page, not "do Ex X"). Magnitude/`density_tier` is on the artifact. |
| **No clean book anchor** — he names a step but the exact exercise/figure number isn't resolvable from #5's skeleton. | A fabricated *"Exercise 1.2.4"* that doesn't exist is worse than vagueness. | The move **degrades gracefully**: `Exercise 1.2.4` → *"the well-definedness step in Hatcher §1.2"* → at worst *"redo the homotopy-square figure by hand."* **Never emit a fake number.** |
| **Garbled OCR coordinate** — page text shows `216`, `V. european`. | Anchoring the move to noisy OCR sends him to the wrong place. | Anchor only to coordinates he **spoke/wrote** ("Problem 2.16," "Orientation of Manifolds," 06-25) or to #5's skeleton — **never** to raw OCR. (Hard rule; the repair card is the *least* OCR-exposed surface — its trigger lives in the clean transcript.) |
| **Vague hedge, no nameable step** — *"lots of interesting stuff."* | A card with no specific step is generic nagging. | Requires **both** a quotable signal **and** a nameable step. Missing either → no card. |
| **Two abandonments in one note.** | Two moves = homework pile = the nag that kills the hobby. | One card, **one move**: name the single load-bearing crux; mention nothing else. |
| **Tone overreach** — catch shames (*"you gave up"*) or praise is generic. | Reads as a grade; he ignores the card forever. | Catch frames the bail as **unfinished**, never **failure**; the clause cites a **specific real** win. Fails the human-tutor gate otherwise. |

The throughline of every failure mode: **a wrong or tone-deaf repair card is worse
than no card.** When the card can't be honest, specific, and on-his-side, it
declines — silence over a bad directive.

---

## Seams — what I hand off / receive (named, not designed)

- **← From #1 (Detection & restraint).** I *receive*: the decision that a repair
  card should fire, the **flavor** (abandonment vs. unverified-proof), the
  **confidence**, the **quotable phrase**, and the **nameable step**. I do **not**
  decide whether to speak. I *hand back* one constraint: the card can render an
  honest catch **only if** a quotable signal + nameable step exist — so "I can't
  write a truthful catch" is itself a signal to #1 to stay silent.
- **← From #5 (Book skeleton & grounding).** I *receive* the **book coordinate(s)**
  — the section / figure / exercise anchor the move points at. I render around
  whatever precision #5 can give and degrade gracefully; I don't build or own the
  skeleton, and I never anchor to OCR.
- **→ To #4 (The loop close).** I *emit* the **close line** ("I'll ask Sunday")
  and a **handle on the move** (what was prescribed). #4 owns the carry-forward
  banner on the record page, the one-tap done/not-yet/in-the-note states, and the
  next-synthesis closure inference. The card produces text + a move handle; the
  loop machinery is #4's.
- **∥ vs. #3 (The bridge card).** Different flavor, same one-card budget: the
  bridge is **desire-pull / delight** ("your two tracks secretly meet"); the
  repair is **firm finish-the-crux.** #1 arbitrates which flavor fires on a given
  night; I don't design the bridge.
- **Delivery surface.** The card lands at the **bottom of tonight's synthesized
  note** — the existing surface, no new screen. (The record-page banner that
  greets him next time is #4's.)

---

## Grounded examples (from his real notes)

**Flagship — abandonment (06-28, van Kampen, deep/2h).** Transcript: *"this is a
bit harder, it's easy to believe, harder to explicitly show with figures, but
this is okay. I think next time I will just keep moving and assume I got it."* The
synthesis itself flags well-definedness as *"the harder half of the argument."* He
*did* work out the triple-intersection / successive-vertices construction (both in
the transcript and the synthesis) — so the celebration is real, not flattery.

> **⟳ Not yet.** You said you'd *"keep moving and assume I got it"* on the
> well-definedness step. That step *is* van Kampen — the rest is bookkeeping. →
> Redo the 3×3 homotopy grid by hand (Hatcher §1.2), then **Exercise 1.2.4.** You
> already nailed the triple-intersection trick; close this and the proof is yours.
> *I'll ask Sunday.*

**Unverified-proof flavor (06-27, orientation/Lie groups, standard).** Transcript:
*"honestly, not really sure about the correctness… proving that Lie groups are
parallelizable… based my intuition on left-invariant vector fields… construct a
top non-vanishing form."*

> **⟳ Worth a second look.** You finished the Lie-groups-are-parallelizable
> argument but flagged it yourself — *"not sure about the correctness."* The whole
> proof rests on the **global left-invariant frame.** → Re-read Tu's statement of
> parallelizability and check your frame against it; if it holds, the orientability
> corollary is one line. Nice instinct carrying it over to left-invariant *forms.*
> *I'll check it with you next session.*

**A note where the card correctly stays silent (06-26).** Transcript: *"I had to
look at some of the examples on a sphere… but I kind of figured it out."* This is a
*resolved* struggle with no bail and no doubt to quote — there is no honest catch
to write, so **no repair card renders.** (Whether to fire is #1's; the card's part
is declining to fabricate a catch.)

---

*Note on the flagship anchor: `Hatcher §1.2 / Exercise 1.2.4 / 3×3 grid` is the
agreed example from the convergent design (#43). Resolving the **exact** anchor —
which figure, which exercise number — is #5's contract; this facet specifies that
the card renders around whatever anchor precision it's given and **degrades rather
than invents** when precision is missing.*

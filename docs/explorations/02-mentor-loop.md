# 02 — The Mentor Loop

*Lens: a private tutor / coach who has read your book **and** your notebook.*

> One of seven divergent bottles (see #35). The other six describe a thing you
> *look at* (Atlas), a thing that *keeps you logging* (Streak), a thing that
> *reorganizes ideas* (Concept-Web), a thing that *re-quizzes you* (Recall-Engine),
> a thing you *talk to* (Companion), or a thing that *argues against the bet*
> (Skeptic). This one is the only product that **tells you what to do next.**

## The bet

This product **is the closed loop he asked for**: every study session ends with
**one prescribed move, rooted in the book** — *"redo the 3×3 grid before you move
on,"* *"go read the Van Kampen statement first,"* *"check your Lie-group proof
against Tu's Prop X."* The app stops being a diary and becomes the voice that
holds a solo learner to the book when no teacher, exam, or deadline does. It is
the most literal reading of his own words:

> "redirect me back in the book to previous sections if a note reveals something
> off; act as a mentor whose tools translate into *go study that section, go do
> that exercise*."

## The job & the moment

The job: **external direction for a learner who has none.** He studies from
books, self-directed, no exams. The failure mode of that life isn't forgetting
(Recall-Engine) or losing motivation (Streak) — it's **quietly skipping the hard
part**. We have him doing exactly that, on tape:

> *"this is a bit harder, it's easy to believe, harder to explicitly show with
> figures, but this is okay. I think next time I will just keep moving and assume
> I got it."* — 06-28, the well-definedness step of Van Kampen (the crux, not a
> detail)

A tutor reading that notebook says **"not so fast."** That's the moment: the
**end of the session**, when he taps record — the mentor reads tonight's note and
hands back tomorrow's instruction. And the **start of the next** session, where
an open loop greets him before he begins. It works daily, but it earns its keep
on the two cadences where threads go stale: **Sunday** (Hatcher, 2h) and the
**monthly math day** (4–5h), where the mentor pre-loads the accumulated dangling
threads instead of letting him cold-start.

## The experience / the aha

Tonight's synthesis of the 06-28 note ends not with a tidy summary that lets him
off the hook, but with a **Mentor card**:

> **⟳ Mentor — don't move on yet.** You hedged on Van Kampen's well-definedness —
> *"I'll just assume I got it."* That step *is* the theorem; the rest is
> bookkeeping. **Before Sunday:** redo the 3×3 grid case by hand (Hatcher §1.2,
> the homotopy-square figure), then attempt **Exercise 1.2.4**. I'll check next
> week. *(You're close — you already nailed the triple-intersection trick.)*

That last clause is the whole personality: **it caught him, but it's on his
side.** The magic is the recognition — *the app flipped back through my notebook
and knows which page I'm bluffing on.*

The **prescriptions** come in a small, sharp taxonomy — each triggered by a real
signal already in his corpus:

| Signal (from his actual notes) | Real example | Prescription (a *move*, never the answer) |
|---|---|---|
| **Hedged confidence / "I'll move on"** | 06-28 *"I'll just keep moving and assume I got it"* | "Redo the 3×3 grid (Hatcher §1.2) + Ex. 1.2.4 before you advance." |
| **Unsure his own proof is right** | 06-27 *"not really sure about the correctness"* (Lie groups parallelizable) | "Your proof rests on a global left-invariant frame — check your statement against Tu's Prop on parallelizability, then the orientability corollary is yours." |
| **Had to backtrack to unblock** | 06-26 *"I had to look at some of the examples on a sphere"* | mentor prescribes it *proactively*: "Stuck fabricating the form? Tu's sphere example is the template — read it, then return to Problem 2.16." |
| **Skipped a prerequisite** | 06-20 (math day) *"I didn't read it well in the theorem itself"* | "You're deep in the proof but skipped the statement — read Hatcher's Van Kampen statement (one page) before next session." |
| **Open / unresolved thread** | 06-20 *"Still figuring it out."* / 06-24 unfinished proof | next session resumes the dangling thread instead of a cold start. |

**The hard rule — no spoilers.** He stated it twice, unprompted: *"don't spoil
the last exercise, I'm working on it, please"* (06-25), *"I have not finished the
proof yet, so don't spoil"* (06-24). So the mentor **never gives the answer** — it
gives *direction*: a section to reread, an exercise to do, a prerequisite to
revisit. This is what separates it from the Companion (which would just answer)
and is the single non-negotiable design constraint.

## MVP

The smallest slice that delivers the aha:

1. **Ingest one book's skeleton** — Tu's TOC + numbered theorems/exercises (he's
   daily there). Just structure + anchors, not full text.
2. **One extra "mentor" pass at synthesis time** over each note: classify the
   confidence signal, map the note to a book location, emit **exactly one**
   book-rooted prescription.
3. **Surface it** as the Mentor card at the end of the synthesized note, plus an
   **open-loop banner** on next open: *"Last time I asked you to redo the 3×3
   grid. Did you?"* → one tap done / not yet / in the voice note.
4. **Close the loop** by inferring from the next note (did the hedge disappear?
   did the concept return resolved?) or the one-tap.

No graph, no spaced-rep scheduler, no chat. **Detect → prescribe → carry forward
→ check.** Crucially this works from a corpus *one note deep* — it only needs the
last note + the book — so it's alive on day one, unlike products that need mass.

## Why this angle wins

It's the **only proactive, directive** bottle. Atlas and Streak are passive — they
show you where you are and keep you coming back, but a hobbyist drifting past the
hard step (*"I'll just assume I got it"*) doesn't need a prettier map, he needs
someone to say **go back.** Concept-Web and Recall-Engine act on knowledge he's
*already secured*; the Mentor acts on the knowledge he's **about to skip.** The
Companion waits to be asked — but he won't ask about the step he thinks he
understood. Only the mentor *initiates*, *assigns a book action*, and *closes the
loop*. And it's the literal product he described. For a learner with no external
accountability, the missing ingredient is exactly that — and the book is the
authority that makes the directive trustworthy rather than bossy.

## Risks / why it might fail

- **Nagging kills the joy.** This is a *hobby*, done for love, with a 2-week-old
  fragile logging habit. A bossy app that grades him could end both. → **One**
  prescription per session, celebratory tone, opt-in, the no-spoiler rule, and
  *silence when unsure* (under-prescribe).
- **A wrong prescription burns trust permanently.** Misreading a rambly voice
  note — taking *"easy to believe"* for mastery, or mapping to the wrong § — and
  he ignores the card forever. Detecting intent from transcripts is the real
  technical bet. → Fire **only on high-confidence signals** (explicit hedges,
  explicit "didn't read the statement"); stay quiet otherwise.
- **The grounding book is about to retire.** The MVP anchors in Tu — and he's
  **~80 pages from finishing it.** → Turn that into the flagship moment (below),
  not a bug.
- **The loop can't see paper.** He may do the exercise and never report it. →
  Infer from the next note + one-tap; treat "can't tell" as silence, not nagging.

## Napkin sketch

```
┌─ Session · Sun 06-28 · Van Kampen (Hatcher, 2h) ─ [deep] ─┐
│  ## Van Kampen — well-definedness via homotopy             │
│  …synthesized markdown, concepts, figures…                 │
│                                                            │
│  ⟳ MENTOR — don't move on yet                              │
│  You hedged on the well-definedness step ("I'll just       │
│  assume I got it"). That step *is* the theorem.            │
│  → Redo the 3×3 grid by hand (Hatcher §1.2 figure)         │
│  → Then Exercise 1.2.4                                     │
│  You already nailed the triple-intersection trick. Close   │
│  this and the proof is yours.       [ Got it ] [ Snooze ]  │
└────────────────────────────────────────────────────────────┘

  next time he opens to record ↓
┌─ Open loops (2) ───────────────────────────────────────────┐
│ ⟳ 3×3 grid + Ex 1.2.4 (Van Kampen)    [done] [not yet] [▾] │
│ ⟳ verify Lie-group proof vs Tu Prop   [done] [not yet] [▾] │
└────────────────────────────────────────────────────────────┘
```

## Fit to his practice

- **Daily Tu (1h, orientation chapter).** Keeps the thread tight — catches the
  06-28 "I'll just move on" and the 06-27 "not sure it's correct" before they
  calcify. Light days get light nudges: 06-24 was *"distracted… 15 minutes"* —
  the mentor reads magnitude and doesn't assign homework on a short day.
- **Sunday Hatcher (2h).** Cross-book prerequisites — the mentor noticed he was
  proving Van Kampen having *"not read the statement itself"* and prescribes the
  one-page read first.
- **Monthly math day (4–5h; 06-20 was one — four sessions in a day).** The mentor
  **pre-loads** it with the accumulated open loops: *"math day is when you close
  your 4 dangling threads."*
- **The finishing-Tu transition.** The single highest-value thing a tutor can do
  at a book-switch: audit the dangling threads (the unverified Lie-group proof,
  the bluffed Van Kampen step) and say **close these before you start the next
  book.** The mentor curates the handoff instead of letting him walk away from
  open loops.
- **2-week corpus.** No disadvantage — the mentor needs only the **last note +
  the book** to prescribe the **next move**, so it delivers value from note one.

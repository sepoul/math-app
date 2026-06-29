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

## Round 2 — defense & why mine wins

### Rebutting the Skeptic (07)

The Skeptic's whole case against my half (Job B) rests on one reading of *"don't
spoil — I'm working on it"* (06-24/06-25) as a **veto on a prescriptive tutor.**
Read the full sentence and it's the opposite — it's my **founding spec**: *"I
don't wanna be spoiled and I wanna take my time trying to figure it out alone if
possible."* He is not refusing direction; he is refusing **the answer**. A
prescription — *"reread Tu's sphere example, then return to 2.16"* — is the exact
inverse of a spoiler: it points at the next move and withholds the solution. The
Skeptic conflates *"prescribe an action"* with *"give the answer."* The art of a
tutor is precisely that distinction, and his plea draws the line for me. I built
Round 1 on it ("the single non-negotiable constraint").

And the Skeptic *ignores the louder signal in the same corpus*: 06-28, *"I'll
just keep moving and assume I got it."* That is not productive struggle — it's
**productive struggle abandoned** at the crux of Van Kampen. The thing the
Skeptic rightly says he treasures (figuring it out himself) is the very thing
he's about to give up on. A mentor that says *"not so fast"* **protects** that
struggle; the Skeptic's own value argues *for* me, not against.

On its strongest structural point — *"there's no moment he consults this; he
reaches for his phone to record, not to look."* **True, and it's my edge, not my
wound.** I am not a destination he must visit (that critique lands on Atlas/Web).
I attach to the **one reliable ritual — recording** — firing the card at its tail
and greeting the next record with the open loop. I never manufacture a new trip.

On *"wrong anchor from garbled OCR"* (`216`, `V. european`): that risk belongs to
the **map-matching** bottles (Atlas, Web, Streak) whose signal lives in noisy
page text. **My triggers live in the clean transcript** — explicit verbal hedges
(*"assume I got it," "not sure about the correctness," "didn't read the statement
itself"*). I am the **least** OCR-exposed direction in the slate.

Where the Skeptic is simply right: **test before a big build, n=1.** I concede
the discipline and absorb it — my MVP *is* that test. One extra LLM pass at
synthesis emitting **one** prescription is nearly as cheap as its weekly digest,
and unlike the digest it tests the thing he called *the goal* ("re-engage my
practice via a reinforcing loop"), not the thing he called *vanity* (backward
visibility). Run it Wizard-of-Oz for two weeks; measure one number: **did he act
on the prescription.** That is the cheapest possible test of the actual bet.

### Defending against the five advocates

- **Atlas (01)** concedes me in its own words: *"if looking doesn't pull him back
  into the book, the Mentor-Loop's 'go do exercise 9.3' wins."* It builds the
  *"vanity visibility"* he called **step one**; I build the loop he called **the
  goal.** I steal its best asset, though: at the Tu→next-book switch my
  transition prescription should borrow the map's adjacency (*"closes naturally
  into X"*) — but the directive stays mine.
- **Streak (03)** lands the sharpest punch: it's *upstream of all six* and over-
  justification is real. I concede it's my dependency (no log → nothing to
  prescribe). But he's logged **10 months with no app and no reward** — showing
  up isn't the gap; *what he does once here* is. And the Streak rewards the
  **log**, which is exactly the over-justification trap it fears; a prescription
  rewards the **math** (do the exercise) — pointing at the book is the mitigation
  Streak says it needs, and I do it natively.
- **Concept-Web (04)** also concedes the behavior axis (*"doesn't itself say go
  do exercise 9.3 — that's the Mentor's job"*). Its determinant-bridge insight is
  genuinely real in his corpus; I absorb it as an **action** — *"you've hit the
  determinant from four sides; prove SL(m) is a regular level set to nail it."*
- **Recall-Engine (05)** is my dangerous twin — same 06-28 seed. But it waits
  ~10 days and asks *"can you still say why?"* (retention); I fire **that night**:
  *"don't move on — do it now"* (progress). The 06-28 case isn't decay, it's
  **abandonment** — spacing it 10 days out lets him leave the crux first.
- **Companion (06)** is a lovely surface but it's **pull** — and names its own
  killer flaw: *"he may never form the question."* By definition of *"I'll assume
  I got it,"* he will never open a chat about the step he thinks he closed. Only a
  product that **initiates on the bluff** catches it. The box is delivery; the
  initiative is mine.

### My wedge (the one thing only I do)

**I intervene on the gap he has decided to abandon.** Every rival either honors
the bluff (Atlas lights it as *walked*, Streak rewards the *log*, Web *links* it,
Companion waits to be *asked*) or checks it ten days too late (Recall). Only the
Mentor turns 06-28's *"I'll just assume I got it"* into *"not yet — redo the 3×3
grid, then Ex 1.2.4,"* in the moment, answer withheld as he demanded. That is
verbatim what he asked for: *"redirect me back in the book… go study that section,
go do that exercise."*

### Honest concession

**Recall-Engine beats me the day he closes Tu.** Once the book is shut, ten
months of manifolds decays whether or not he ever bluffed — that's pure
forgetting, and there's no *"next action in the book"* to prescribe for a closed
book. A spaced keep-alive is the right instrument there; a prescription isn't. I
own *"don't let the live chapter close with its crux unproven."* Recall owns
*"don't let the closed book evaporate."* If the bet is durability of work already
done, build Recall. If it's the reinforcing loop he actually asked for, build me.

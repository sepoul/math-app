# 04 — The Loop Close

*Facet 4 of the Mentor Loop (see #43). The brain that decides **whether** to
speak is #1; what the card **says** is #2 (repair) / #3 (bridge). This doc owns
the part that turns a one-off tip into a **loop**: carry it forward, let him
close it with one tap or none, and infer closure from the next note on its own.*

> **Detect → one move → carry → close.** Facets 1–3 do *detect* and *one move*.
> This facet does **carry** and **close** — the back half that makes the mentor a
> loop instead of a fortune cookie. If a card fires tonight and nothing ever
> picks it back up, it was advice. If it greets him next session and quietly
> resolves itself off his real notes, it was a loop.

---

## The story

> **As the learner**, when the mentor catches a step I abandoned and tells me to
> go back to the book, **I want** that open thread to still be there waiting the
> next time I sit down to study — and to close on its own when I actually do the
> work, without me filing a report — **so that** the mentor feels like a tutor
> who *remembers what he asked me*, not an app that fires a tip into the void and
> forgets it.

**The job.** I study alone, from books, on paper, with no exam and no teacher to
hold the thread. The failure mode isn't forgetting — it's that *the hard step I
waved off on Sunday is simply gone by Wednesday*, and nothing in my life brings
it back. The loop close is the thing that brings it back: it carries the open
thread across the gap between sessions and lets it resolve quietly when I've done
the work.

**The moment.** Two moments, both anchored to the one ritual I already keep —
**recording**:

1. **Next time I tap record**, before I say a word, the open loop greets me at
   the top of the record page: *"Last Sunday: redo the 3×3 grid + Ex 1.2.4. Did
   you?"* — three taps, no typing.
2. **When tonight's note synthesizes**, the existing magic pass also reads the
   open loops and, on its own, decides whether any of them just closed — because
   the hedge disappeared, the exercise got mentioned, or the concept came back
   *resolved*. Most of the time I never touch a button; the loop closes itself
   off what I actually wrote.

This facet introduces **zero new surface**: no push notification, no new screen,
no badge, no typing. The carry lives on the record page I already open; the close
lives inside the synthesis I already get.

---

## What "done *and good*" looks like (acceptance criteria)

1. **It carries.** After a card fires, the very next time he opens the record
   page, the open loop is waiting at the top — anchored to the coordinate *he*
   wrote ("Problem 2.16," "Ex 1.2.4"), never to OCR garble or app-speak.
2. **It closes with zero interaction.** If the next note's synthesis infers
   closure (hedge gone / exercise named / concept returned resolved), the loop
   closes itself and is acknowledged in **one line** — never re-fired as a fresh
   card, never demanding confirmation.
3. **One tap, three states, no typing.** `did it` / `not yet` / `it's in today's
   note` — and tapping is always *optional*; the loop can live its whole life and
   close without a single tap.
4. **"It's in today's note" is believed-and-verified.** That tap doesn't blindly
   mark done, and doesn't ignore his paper work — it tells the next synthesis
   *where to look* and raises its confidence that today's note closes the loop.
5. **"Can't tell" is silence, not a poke.** A loop the system can't read closure
   on is met with **silence** — never "did you finally do X?", never a second
   prompt. He studies on paper and may never report; absence of evidence is never
   treated as failure.
6. **Ignored loops decay gracefully.** An un-acted loop softens, then disappears
   within a bounded number of cadence cycles — no failure message, no "you still
   haven't…". A good tutor stops bringing up the exercise you clearly walked away
   from.
7. **It self-limits.** At most a small handful (~3) of open loops are ever
   visible; beyond that the system folds the older ones and back-pressures new
   detection. More than a few open loops *is* nagging, and nagging kills a hobby.
8. **It respects the day.** On a light/distracted day the banner doesn't arrive
   as homework; on math day / at the book switch the accumulated loops pre-load as
   the agenda instead of a cold start.

The single behavioral proof that this is a loop and not a tip: **show it closing
itself off his real corpus with no tap** — the 06-25 → 06-26 arc below does
exactly that.

---

## The design, at a balanced altitude

### A. The carry — the open-loop banner on the record page

When a card fires, it becomes an **open loop**: a small carried thread holding the
book anchor, the move, an optional promised check-time (*"I'll ask Sunday"*), a
status, and a pointer back to the note that opened it. (The *anchor* comes from
#5, the *move* and *promise* from #2/#3 — I receive them; I don't author them.)

Next time he opens to record, the open loop(s) greet him at the top as one
compact line each:

```
┌─ Open loops (2) ───────────────────────────────────────────┐
│ ⟳ 3×3 grid + Ex 1.2.4 (Van Kampen)    [did it] [not yet] [▾]│
│ ⟳ verify Lie-group proof vs Tu        [did it] [not yet] [▾]│
└─────────────────────────────────────────────────────────────┘
            ↓ he can ignore all of this and just record
```

It **greets, it never blocks**. It is not a notification — there is no push, no
badge, no trip he has to make. It is simply *there* on the page he was going to
open anyway. The whole accountability is "the app remembers," delivered with no
friction.

### B. The close — one tap, three states

Three taps, no typing, all optional:

- **`did it`** → the loop closes. The next synthesis may acknowledge it in a
  single warm line (*"nice — you closed the van Kampen step"*), never a new card.
- **`not yet`** → the loop stays open and *acknowledged*. It does **not** spawn a
  fresh card (that's #1's call); it just persists, and its decay clock advances.
- **`it's in today's note`** → the loop is flagged *claimed-closed, verify from
  note* and handed to the closure-inference pass, which looks in today's note for
  the evidence and confirms. This is the seam between self-report and inference:
  he tells it *where to look* without having to prove anything.

Why the third state matters most: he works on **paper**. He does the exercise,
then records a note *about* it. That tap is how a paper learner says "I did the
work, it's in here somewhere" without typing a word — and it turns inference from
a guess into a targeted check.

### C. Closure by inference — the heart of the loop

The existing synthesis pass already produces, per note, a `summary`, a recurring
`concepts` trail, and a `markdown` body. The closure-inference step rides on that
output: it gets the open loops as context and reads the new note for three
signals (it does **not** run a separate model pass on him — it reads what the
synthesis already saw):

1. **Did the hedge disappear?** A loop opens on a hedge (*"I'll just assume I got
   it," "I'm in the process of building it," "not sure about the correctness"*).
   If the same concept returns later stated as *settled*, the hedge is gone → the
   loop closes.
2. **Was the exercise / section mentioned?** If the loop's book anchor (the named
   exercise or section from #5) shows up in a later note as worked, the loop
   closes.
3. **Did the concept return *resolved*?** Broader than the hedge test: the
   concept reappears in the `concepts` trail and the note's stance toward it is
   *resolved* — he builds on it, uses it as settled, moves past it — versus
   *re-stuck* — he re-hedges, re-backtracks.

Inference yields a **confidence, not a boolean**, with three outcomes:

- **Confident closed** → close silently, acknowledge in one line.
- **Confident still-open** (concept came back but *re-hedged*) → keep the loop
  alive and visible, but **do not** auto-fire a new card — that's #1's decision.
- **Can't tell** (concept didn't return, or the note is unrelated/light) →
  **silence**. Age the loop toward decay. *Can't tell ≠ not done.*

### D. Graceful decay — the anti-nag spine

Loops must never become a pile of guilt-debt. Decay is tied to **cadence, not a
fixed timer** (the rhythm comes from #6):

- The check is promised at a cadence boundary (*"I'll ask Sunday"*). If that
  boundary passes with no closure signal and no tap, the banner line **softens** —
  from an active prompt ("redo the 3×3 grid") to a quiet trailing mention — and
  then **drops off entirely** after a bounded number of cadence cycles.
- **Snooze** (`not yet` / `▾`) pushes the check to the next boundary, a *bounded*
  number of times. A loop can't be snoozed forever into a permanent guilt object.
- Decay is **silent**: a decayed loop is never announced ("you failed to do X").
  It just stops appearing.
- A decayed loop is only ever resurfaced if the **math itself comes back** — the
  same anchor reappears and he's still stuck — and even then re-opening is *#1's*
  call, not a nag from this facet.

The feel to aim for: the mentor *letting it go gracefully*, the way a good tutor
doesn't keep raising the exercise you clearly abandoned three weeks ago — unless
it becomes live again.

### E. Self-limiting — how many loops can coexist

The product fires "at most one card, most nights nothing," so loops accrue slowly.
But across the Sunday + math-day rhythm they can stack. The policy:

- A **small cap** on visible open loops (~3). Beyond it, the banner shows the most
  recent / most cadence-relevant and folds the rest.
- When the cap is full of fresh, un-acted loops, the loop-close exposes "**loop
  budget full**" back to #1 as a gate — restraint *compounds*: a full loop set is
  a reason for #1 to stay silent tonight. (I expose the count; #1 decides whether
  to speak. I do not design #1's firing logic.)
- **Math day is the natural flush.** The accumulated open loops pre-load as
  *"today's the day to close these"* (grounded: 06-20, a math day, four sessions).
- **The Tu→next-book switch is the other flush.** At the book switch the open
  loops become the "close these before the next book" audit. This facet supplies
  the *open set*; #6 designs the pivot moment.

Rationale: more than a few open loops at once *is* the nagging the whole product
is built to avoid. The cap is a restraint signal, not a UI convenience.

---

## Grounded in his real notes

### Arc 1 — the van Kampen abandoned crux *(the canonical loop)*

- **Open.** 06-28 (Sunday, 2h, 4 pages — a deep day). At the end of the hardest
  part of the proof he says, on tape: *"this is a bit harder, it's easy to
  believe, harder to explicitly show with figures, but this is okay. I think next
  time I will just keep moving and assume I got it."* A card fires (#1/#2), anchor
  "Hatcher §1.2 + Ex 1.2.4," check promised *"Sunday."*
- **Carry.** He records mid-week on his **daily Tu** track (orientation — a
  *different* thread). The banner shows the loop but keeps it a quiet line, not a
  demand, because the day's work isn't Hatcher. The **next Sunday** the banner
  foregrounds it: *"Last Sunday: redo the 3×3 grid + Ex 1.2.4. Did you?"*
- **Close**, four ways:
  - taps `did it` → closed, acknowledged;
  - taps `it's in today's note` → next synthesis verifies the 3×3 grid is now
    worked;
  - says nothing, but the next Sunday note discusses the homotopy-square / 3×3
    construction *confidently* → inferred closed, hedge gone;
  - says nothing and van Kampen never recurs → **can't tell → silence** → decays
    after ~2 Sundays, no failure message.

### Arc 2 — the self-closing loop *(inference, zero taps)*

This is the existence proof, straight off his corpus, one day apart:

- **Open.** 06-25: *"now I'm working on orientability of a regular level set… the
  key… is to build a non-vanishing top form. And I am in the process of building
  it. I've seen it before. I just need to remember it… I don't wanna be spoiled."*
  A hedge on an open exercise — a loop, anchored to **Problem 2.16**.
- **Close.** 06-26: *"today I tackled a very hard problem… orientability of
  regular level sets… I had to look at some of the examples on a sphere. But yeah,
  I kind of figured it out… this allowed me to prove that the form is well
  defined."* The same concepts (`regular level set`, `non-vanishing top form`)
  return **resolved**, the hedge is gone.

And the existing synthesis *already names the closure for me*: the 06-26 note's
`summary` literally reads *"The learner **revisits a previously difficult
exercise**, using the worked example of the sphere to unlock the construction,"*
with `Problem 2.16` as the heading and the same `concepts` recurring. The
closure-inference pass doesn't need new intelligence — it needs to **read what the
synthesis already saw**: same anchor + same concepts + resolved stance → closed,
no tap, no banner friction. The next synthesis acknowledges it in one line.

### Arc 3 — the decaying / open-at-switch loop

- **Open.** 06-27: *"Honestly, not really sure about the correctness… Lie groups
  are parallelizable… trying to prove they are orientable through building a
  non-vanishing top form."* An unverified-proof loop, anchored to the Lie-group
  exercise.
- **Carry.** It never recurs in the corpus (it's near the end of his trail). →
  **can't tell → silence.** It does not nag.
- **Flush / decay.** It surfaces *once more* at the **Tu→next-book transition** as
  part of the "close these before the next book" audit (handed to #6), then decays
  silently if still untouched. This facet supplies the open set; #6 owns the pivot.

### A note on the light day

06-24: *"one hour and a bit short… I was distracted full time, 15 minutes from
the session."* On a day like this the banner must not arrive as homework. The
loop-close *consumes* the magnitude/cadence read (#6/#5 own producing it — the
`magnitude` block already carries `density_tier`) to decide whether to even
foreground the banner that day. On a light day: a gentle one-liner or nothing,
never a "did you do your exercise?" demand.

---

## Key design decisions & open questions

**Decisions taken**

- **Closure is inferred by default; taps are an accelerant, not a requirement.**
  The paper learner who never reports is the *normal* case, not the edge case. The
  loop must be able to live and die with zero taps.
- **"Can't tell" resolves to silence, always.** This is the load-bearing rule of
  the facet. We never convert "no evidence" into "not done."
- **Decay is cadence-relative and silent.** Loops fade on his rhythm, not on a
  wall-clock, and fading is never announced.
- **A hard, small cap on concurrent open loops, with back-pressure onto #1.**
  Restraint compounds across facets; a full loop set is a reason to stay quiet.
- **Inference rides the existing synthesis output** (`summary` / `concepts` /
  `markdown`), not a new analysis of him. We already produce the trail; we read it.

**Open questions** (flagged, not resolved here)

- **The exact decay budget** — how many cadence cycles / snoozes before a loop
  drops off. Needs to be tuned against his real rhythm with #6; my instinct is
  "~2 Sundays for a Hatcher loop," but that's a #6-shaped number.
- **The visible-loop cap value** (~3 is a placeholder). It's a restraint knob, so
  it should be set conservatively and revisited only if loops genuinely feel
  under-served — never raised to "show more."
- **Bridge loops may have no check-time.** A repair card promises *"I'll ask
  Sunday"*; a bridge card (#3) is desire-pull, an *invitation*. Open question for
  the seam: do invitation-loops carry in the same banner but decay faster and
  never get a "did you?" framing? My default: yes — they appear, they tempt, they
  fade quietly, they're never homework. #3 owns whether a bridge wants a check at
  all.
- **De-dup granularity** — when two loops touch the same thread (two van Kampen
  steps), how aggressively to merge them into one carried thread so the cap and
  the banner don't double-count.

---

## Edge cases / failure modes

| Case | What happens |
|---|---|
| **Did it on paper, never says so, concept never recurs** (the common case for a paper learner) | Can't tell → **silence** → graceful decay. Never assume failure. |
| **Taps `did it`, but a later note shows he's still stuck** | Trust the tap to close *this* loop. If #1 re-detects the same hedge later it's a **fresh** loop, never "you lied." No contradiction-policing. |
| **Concept returns but *re-hedged*** (the 06-20 *"Still figuring it out"* pattern) | Loop stays open and visible; **no** new card auto-fires. We distinguish "returned resolved" from "returned still-stuck." |
| **Two loops on the same thread** | De-dup / merge into one carried thread so the banner doesn't double-count and inflate the cap. |
| **Light / distracted day** (06-24) | Don't surface the banner as homework — suppress or soften the check. We consume the magnitude read; we don't decide it. |
| **Snooze-forever learner** (taps `not yet` every time) | **Bounded** snoozes, then graceful decay. The loop is not a debt collector. |
| **Decayed loop's concept reappears in a *different* context** | Require the **same book anchor** to consider resurfacing; otherwise treat as new. Anchors prevent false resurrection. |
| **Closure false-positive** (passing mention read as "returned resolved") | Confidence threshold; "mentioned in passing" ≠ "returned resolved." When unsure, keep open and let the *next* note or a tap settle it — **still silent**, no poke. |
| **A card with no check-time** (a bridge invitation) | Carries as an *invitation*, not an obligation — appears in the banner, decays faster, never framed as "did you?" (#3 owns whether it wanted a check at all). |

---

## Seams (what I receive / hand off — named, not designed)

**I receive**

- **From #1 (Detection & restraint):** a freshly-opened loop — a fired card with
  its anchor, its move, and (if any) a promised check-time. I do **not** decide
  *when* #1 speaks; I expose the open-loop count back to it as a gate.
- **From #2 (Repair) / #3 (Bridge):** the card's content and whether it's an
  *obligation* (*"I'll ask Sunday"*) or an *invitation* (bridge desire-pull). I
  carry and decay accordingly; I do **not** write the card text.
- **From #5 (Book skeleton):** the canonical anchor coordinates ("Hatcher §1.2,"
  "Problem 2.16," "Ex 1.2.4"). The banner displays *these*, never OCR garble, and
  closure-by-exercise-mention matches against them.
- **From #6 (Cadence & fit):** the rhythm model — which session is Sunday /
  math-day, when *"I'll ask Sunday"* resolves, and the light-day / magnitude read.
  I consume it to time the check and decide whether to show the banner. I do
  **not** design the rhythm or the finish-Tu pivot.

**I hand off**

- **To the next synthesis pass (#1's brain):** the set of open loops as context,
  plus per-loop inference hints ("look for the 3×3 grid being worked") and the
  "it's in today's note" flag that raises verification confidence.
- **To #6:** the accumulated open-loop set, for math-day pre-load and the
  Tu→next-book "close these first" audit.
- **To #1:** the open-loop count as back-pressure — restraint compounding across
  the loop.

---

*Closes the loop named in #43: **Detect → one move → carry → close.** Facets 1–3
detect and move; this is the carry and the close — the half that earns the word
"loop."*

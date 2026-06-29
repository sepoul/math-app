# 03 — The Streak (Strava-for-math)

*Lens: growth / behavioral-design PM. Direction #3 of 7. Sibling bottles: Atlas
(#1), Mentor-Loop (#2), Concept-Web (#4), Recall-Engine (#5), Companion (#6),
Skeptic (#7). This doc stays militantly in its lane: **retention and motivation
are THE product.** Not pedagogy, not prescriptions, not navigation.*

## The bet

This product **is a streak that has substance.** Not a tap-counter — a *trail
walked through a real book.* Every other bottle in this crate (Atlas, Concept-Web,
Recall, Companion, Mentor) is a **consumption** product that silently assumes the
notes corpus exists and keeps growing. The Streak is the only **production**
product: its one job is to protect the **fragile 2-week-old logging habit** so the
corpus ever gets big enough for any of the other six to be worth building. The
single KPI is blunt: **did he log again tomorrow.**

## The job & the moment

The corpus is not just small — it is *infant and already injured.* The full prod
data is **10 notes across 10 calendar days (Jun 19–28)**, and the chain already
snapped once:

```
Jun 19 Fri  ●  Tu (orientation)
Jun 20 Sat  ●●●●  Hatcher marathon — 4 notes, van Kampen + quotient groups   ← the big day
Jun 21 Sun  ✗
Jun 22 Mon  ✗   ← 3-day lapse, right after the marathon. Textbook overreach→crash.
Jun 23 Tue  ✗
Jun 24 Wed  ●  Tu      ┐
Jun 25 Thu  ●  Tu      │
Jun 26 Fri  ●  Tu      │  5-day recovery streak — the real achievement, currently invisible
Jun 27 Sat  ●  Tu      │
Jun 28 Sun  ●  Hatcher ┘  "All right, so this is Sunday. I do two hours of math." (his words)
```

That arc — **burst → crash → comeback** — is the most important behavioral fact in
the whole dataset, and *nothing in the app today reflects it.* He doesn't know he's
on a 5-day streak. He doesn't know his comeback after a 3-day break is harder and
more praiseworthy than the marathon was. He himself named the need:

> "first a vanity visibility over my progress… but the goal is to **re-engage my
> practice via a reinforcing loop.**"

**The moment** is the **last 10 seconds of each session** — right after he stops the
voice memo. That is when the reward must fire, because in behavioral terms the
reward must attach to the *action we want repeated* (logging), not to some later
visit. Secondary moments: a **Sunday recap** (his natural fresh-start anchor — Jun
28 confirms Sunday = Hatcher), and the **monthly 5h math-day** treated as a *race
day*.

## The experience / the aha

He finishes today's voice note. Instead of a spinner and silence, a **summit card**
slides up:

> **Day 5 🔥** · longest streak this month
> +4 pages of *Tu* · you crossed into §21, **Orientations**
> **78 pages to the summit** (■■■■■■■□□□ 76%)
> 47 theorems met · "van Kampen" is the concept you've returned to most

The dopamine is real because the number is real. A Duolingo streak says *you opened
the app*. This says *you walked four more pages of a 400-page book and you can see
the summit.* **Book-grounding is what makes the streak non-hollow** — the counter is
denominated in *terrain*, not taps. (He's 80 pages from finishing Tu — so the
progress bar is, right now, almost full. The single most motivating screen we could
ever show him is "**the summit is in sight,**" and we have the data to show it
today.)

The second aha is periodic, Strava's "Year in Sport" move: a **Year in Math** card
that makes 10 mostly-solitary months *feel* like the achievement it is —
"**287 study-days · 4 books touched · 612 theorems met · longest streak 23 days.**"
He has done something genuinely rare and has *zero* artifact of it. We mint one.

## MVP

Smallest slice that delivers the aha, no new ingestion pipeline required — the
synthesis already emits `concepts`, `pages`, and a `magnitude` tier:

1. **The post-session summit card.** Streak count + this-session's page/concept
   delta + a book progress bar. (Book "length" can be a single number he types once,
   or inferred from his page logs — grounding doesn't need the full Atlas to start.)
2. **Streak with grace built in.** Daily target, but **two rest-days banked per
   week** and **auto-freeze** so a Sun/Mon/Tue like Jun 21–23 *bends, doesn't
   break.* No red. No "you lost it."
3. **The comeback badge.** First session after a gap is celebrated *more* than a
   normal one — "welcome back, that's the hard part." Recovery > perfection.

That's it. One card, one forgiving counter, one comeback rule. Everything else
(milestone library, Year-in-Math, math-day race mode) is fast-follow.

## Why this angle wins

- **It's the only bottle that's valuable at n=10 notes.** An Atlas of 10 notes is a
  blank map; a Concept-Web is three nodes; a Recall-Engine has nothing aged enough
  to space. The Streak is the *only* direction that delivers value on a two-week-old
  corpus — and it is **upstream of all six others.** Kill the habit and there is no
  corpus to build an Atlas, a Web, or a Recall queue *on.* This bottle protects the
  input to every other bottle.
- **It already broke once — so it's the proven risk.** We don't have to speculate
  about churn; the 3-day gap is in the data. This is the live wound to dress.
- **Substance is the moat over generic habit apps.** Strava works because the metric
  is *the run.* Duolingo's streak is mocked because the metric is *the open.*
  Book-grounding puts us on the Strava side: the streak measures a real position in
  real mathematics.

## Risks / why it might fail

- **Over-justification — the sharpest risk for *this* person.** He has done 10
  months, daily, with *no app and no reward.* That's pure intrinsic motivation.
  Bolting extrinsic points onto an intrinsically-loved activity can **crowd the love
  out** (the over-justification effect) — turn play into a chore he now does "for the
  streak." Mitigation is a hard design constraint: **the metric must always point
  back at the math** (pages, theorems, the summit), never at the app (taps, opens,
  XP). The day he studies *to keep the number* instead of *to learn*, we've broken
  him.
- **Streak anxiety / guilt backfires.** Loss aversion is a sharp tool that cuts both
  ways: a guilt-trip on the day he misses can make him quit rather than return — and
  he already misses (Jun 21–23). Hence grace-by-default, comebacks celebrated, and
  **zero shame mechanics.** No nag notifications; gentle "your trail is cooling," not
  "YOU FAILED."
- **Cadence mismatch.** His real rhythm is textured — 1h daily, 2h Sunday Hatcher,
  monthly 5h — not a flat daily metronome. A naïve daily streak punishes that texture
  (it would have scored his Jun-20 marathon and his quiet Jun-27 identically). The
  streak must **speak his cadence**: Sundays and math-days are *features*, not
  threats to the chain.
- **He may simply not want a game.** He stepped away from Lean for feeling too much
  like "programming." A loud, badge-spammy game could read the same way. Antidote:
  quiet, earnest, *Strava-serious* — a logbook that respects the discipline, not a
  toy that infantilizes it.

## Napkin sketch

```
┌──────────────────────────────────────────────┐
│  after he taps ⏹ on today's voice note…       │
│                                                │
│   🔥  DAY 5        longest streak this month   │
│   ────────────────────────────────────────    │
│   Today:  +4 pages · 18 concepts               │
│           you entered §21 Orientations         │
│                                                │
│   Tu — Intro to Manifolds                      │
│   ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░  322 / 400             │
│   🏔  78 pages to the summit                    │
│                                                │
│   This week ▁▃▅▂▆▇·   ·=rest, banked 2/2       │
│   Sunday = Hatcher ✓   Math-day in 9 days      │
└──────────────────────────────────────────────┘

      weekly Sunday recap                 the rare artifact
┌───────────────────────┐        ┌─────────────────────────────┐
│  THIS WEEK             │        │   YEAR IN MATH              │
│  5 sessions · 16 pages │        │   287 study-days            │
│  most-revisited:       │        │   4 books · 612 theorems    │
│   "van Kampen" (×4)    │        │   longest streak: 23 days   │
│  comeback after 3 off  │        │   "you did something rare"  │
│   — nice 👏            │        └─────────────────────────────┘
└───────────────────────┘
```

## Fit to his practice

- **Tu, ~80 pages from done.** The progress bar is nearly full *right now* — the
  goal-gradient effect (motivation spikes near a goal) is handed to us for free. And
  the **finish-Tu → pick-new-book transition** is the single highest-churn moment in
  his future: the bar hits 100%, the obvious next move is to bask and drift. The
  Streak's job there is the *summit celebration → "what's the next mountain?"* hand-
  off that keeps the chain alive across the book boundary.
- **Daily 1h** → the post-session card; this is the core loop.
- **Sunday 2h Hatcher** (confirmed: "this is Sunday, I do two hours of math") → a
  recurring *named ritual* and the weekly-recap anchor (the fresh-start effect lives
  on Sundays).
- **Monthly 5h math-day** → *race day.* A pre-event nudge, a bigger card after. The
  Jun-20 marathon shows the failure mode too: the big day was followed by a 3-day
  crash, so math-day mode must include a "rest is part of training" cool-down, not a
  streak-pressure hangover.
- **The 2-week corpus, already injured.** The 5-day recovery streak (Jun 24–28) and
  the comeback from the Jun 21–23 gap are, today, *completely invisible to him.* The
  whole product is just: **make him see that, and make him want tomorrow's.**

---
*Lane check: this is retention/motivation only. The map belongs to Atlas, the "go
do exercise 9.3" belongs to Mentor-Loop, the idea-graph to Concept-Web, the spaced
prompts to Recall-Engine. The Streak borrows their data to denominate a number — it
does not become them.*

## Round 2 — defense & why mine wins

### Rebutting the Skeptic (07) — its pre-mortem ends at my front door

The Skeptic lands real hits, but read where they land. *"He already self-locates"*
(his notes are titled "Problem 2.16," "§21.4") kills the **Atlas's** "where am I"
job — not mine; I never claim to tell him where he is in the book, I tell him he
showed up five days running, which *nothing in his world tells him.* *"Don't spoil…
I'm working on it, please"* (06-25) and *"I wanna take my time… alone"* (06-24)
veto the **Mentor / Recall / Companion** — anything that probes, tests, or
prescribes. **The Streak prescribes nothing and tests nothing.** It is the only
direction that fully honors his productive-struggle ethic: it celebrates the *act
of logging* and never touches the math's difficulty. *"The synthesis is already the
magic"* — agreed, and that's my ally: the synthesis is the **reward I deliver at the
end of the log.** Magic he doesn't return to receive is wasted; I am the frame that
brings him back tomorrow.

Then the Skeptic's own words convict it. Its pre-mortem concludes: *"Even the habit
we're betting on already skipped (06-21→06-23)… **Stabilize and reward the logging
before we couple a map to it.**"* That sentence **is my product spec.** And the
cheapest thing it says to build — what the learner *literally asked for*, *"a vanity
visibility over my progress"* — is a progress view, not a cartographic substrate;
the Skeptic's own leanest variant ("Tu · Orientation · ~80pp left") is a degenerate
summit card. Its n=1 caution cuts toward me, not away: you cannot run a four-week
Wizard-of-Oz digest test on a corpus that died in week three. **I am the only bottle
that keeps n growing toward the mass all six others silently assume.**

What I *absorb* from it: the 06-20 line — *"not adding a photo this time, the photos
are huge and they're bugging the application"* — proves the ritual sheds the instant
friction appears. So the streak must add **zero capture surface**: pure pull at the
synthesis moment, no notification nagging, nothing new to tend. That's not a wound;
it's evidence for exactly the fragility I exist to defend, and it tightens my one
hard constraint.

> **Editor's note (control plane, post-hoc):** the "photos bugging the app" friction
> (06-20) was *already fixed* before this exploration — client-side downscale in
> `math-ui/lib/domains/math-notes/image.ts`. So it is **no longer live evidence of
> fragility**; the Streak's fragility case rests on the single 3-day gap (06-21→23),
> weighed against 10 months of unprompted practice + a self-staged comeback. The
> "zero capture surface" design principle still stands on its own merits.

### Against the five advocates

- **Atlas (#1)** is my closest rival for the "vanity visibility" he named — and it
  concedes its own core risk: *"the Atlas wagers that orientation alone changes
  behavior… pretty but inert."* A map you only admire is a poster. **I am the loop
  that makes him return to look at any surface** — so I *absorb* the Atlas: the
  lit-territory delta is the best possible **content for my card.** Map without loop
  is inert; loop without content is hollow. I supply the loop and borrow its visual.
- **Recall-Engine (#5)** makes the sharpest honest point — for a no-exam hobbyist the
  long-run enemy is *forgetting*, and that's its lane, not mine. True. But Recall
  *consumes* aged notes ("two-week-old corpus is thin," it admits) and it's a **test**
  — the precise thing the "let me struggle alone" learner is escaping ("feels like
  school — fatal if it nags"). Sequence is everything: **the Streak produces the
  corpus Recall needs.** Protect the habit first; make it stick once there's mass.
- **Mentor (#2)** is the most directly vetoed — its whole thesis (prescribe the next
  move) is the thing he twice told the app *not* to do, and it admits *"a wrong
  prescription burns trust permanently."* I direct nothing.
- **Companion (#6)** has the strongest "he already talks to the app" point — *"this is
  a message for you, synthesists"* (06-25). I *absorb* it: that emotional engagement
  is exactly why an earnest, personal card ("Day 5, your longest this month — comeback
  after a 3-day gap") lands as recognition, not a cold counter. But the Companion is
  **pull** (he reads notes only "now and then") and a new behavior for a pen-and-paper
  purist who left Lean for feeling like programming. I fire **unprompted**, at a
  moment he's already in, with zero new muscle.
- **Concept-Web (#4)** names me as its own conqueror: *"if his real need is behavioral
  nudging, the Streak or Mentor beats it,"* and it's thinnest at week 2. I *absorb* its
  best moment — the "you've touched the determinant from four sides" bridge becomes a
  **milestone event** in my loop.

### My wedge — the one thing only I do

**Every other bottle fights over how to *spend* the corpus; I'm the only one fighting
to make sure there *is* one.** My KPI is blunt — *did he log tomorrow* — and at
n=10-over-2-weeks that is the *only* KPI that matters, because the other six are
worthless on an empty corpus. The proof is in his own data: the **5-day recovery
streak (06-24→28) after the 3-day gap is completely invisible to him today.** He
doesn't know he staged a comeback. Not the book, not the synthesis, not a map, not a
quiz tells him *"you came back, and you've now strung five."* That signal, at that
brittle moment, is mine alone — and even his *"distracted… 15 minutes"* day (06-24)
becomes a kept link instead of a near-miss.

### Honest concession

**Recall-Engine beats me outright in one world: if the habit isn't actually
fragile.** He did ten months with no app and no reward; he logged a distracted
15-minute day and staged his own comeback *unprompted.* If that intrinsic engine is
robust, gamifying it is redundant at best and over-justification poison at worst —
and then the enemy that never goes away is decay, which is Recall's to own, not mine.
My bet is that a two-week-old habit with a gap and a friction-shed already on its
record is not yet that engine. If I'm wrong about the fragility, I lose to Recall.

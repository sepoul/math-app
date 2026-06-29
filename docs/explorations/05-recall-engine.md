# 05 — The Recall Engine

*Lens: a learning scientist. Retrieval practice, the spacing effect, desirable
difficulty, the testing effect. One of 7 divergent explorations of issue #35 —
this one stays strictly in the "make it stick" lane.*

## The bet

**This product *is* a spaced-retrieval coach grounded in his own trail.** It
doesn't show him what he's learned — it asks him to *prove he still has it*, at
the moment forgetting is about to win, using questions generated from his own
notes and anchored to the book. The other six make his practice **visible**
(Atlas), **directed** (Mentor), **rewarding** (Streak), **connected**
(Concept-Web), **conversational** (Companion), or **questioned** (Skeptic). This
one makes it **durable**. It is the only direction that fights forgetting.

## The job & the moment

He studies from books, no exams, no deadlines. **Nothing in his world ever
tests him.** A book never asks "do you still remember orientation forms three
weeks later?" — so the default outcome for a hobby learner is quiet decay of
everything not currently open on the desk. He already feels the pull: he reads
his notes *"now and then."* But re-reading is the single weakest study strategy
known to cognitive science (Roediger & Karpicke, 2006) — it produces *fluency*
("yeah, I recognize this") and mistakes it for *mastery*. The Recall Engine is
the evidence-based upgrade of the exact habit he already reaches for.

The moment is **the 2-minute warm-up at the start of a session** — before he
opens the book. This is deliberate: retrieval *before* restudy (the pretesting
effect) both consolidates the old and primes the new. He already does this by
hand — his 6/28 note literally *"opens by recalling the surjectivity setup"*
before continuing the proof. We just front-run it, and aim it at the thing he's
actually shaky on instead of whatever he happens to reread.

## The experience / the aha

The killer demo comes straight from his real data. On **6/28**, mid–Van Kampen,
he said into the mic:

> "this is the hardest part of the proof, at least for me … I think next time
> I'll just keep moving and **assume I got it**, yeah."

The app *heard that*. Ten days later, Sunday morning, before Hatcher opens:

```
Quick check before you start (90 sec) ─────────────────────────────
On Jun 28 you decided to "assume you got" the hardest step of Van
Kampen and move on. Gut check — can you still say why two successive
grid vertices must share a common A_i?

   🎙️ say it   |   ✍️ type it   |   🤔 no idea, show me
───────────────────────────────────────────────────────────────────
```

He mutters a 20-second answer into the mic (his native input — he already
records voice notes). Tap reveals **what he wrote that day** *plus* **Hatcher's
own statement** as the answer key. Then one honest self-grade: **Solid / Fuzzy /
Gone.** That's the whole loop.

The aha is three things landing at once: it surfaced *the exact step he flagged*,
*right when context was warm*, and *it took 90 seconds and felt good* — the small
satisfying click of "oh, I do still have this." Not homework. A "still got it?"
move you'd happily make over coffee.

## MVP

The smallest slice that delivers that click:

1. **Mine flagged-uncertainty moments first.** Scan transcripts for hedges —
   *"hardest part," "assume I got it," "deliberately unfinished," "a bit
   harder."* These are the highest-value cards and they prove the grounding
   instantly. (Real seeds already sitting in the corpus: the 6/28 vertex step,
   the 6/25 regular-level-set orientability *"left deliberately unfinished,"* the
   6/26 *"previously difficult exercise."*)
2. **Generate one reconstruction prompt** per seed from the note's concepts +
   summary — *"reconstruct why…," "rebuild the construction for…"* — never
   term→definition matching (see Risks).
3. **One card, at session start, drawn from a note 1–3 weeks old.** Reveal = his
   original note + the book section. Self-grade: Solid / Fuzzy / Gone.
4. **Expanding reschedule** off the grade: Solid pushes the next showing out
   (~3 → 7 → 16 → 35 days); Fuzzy holds; Gone resets short and suggests the
   reread. No deck to manage, no streak, no due-count.

One card, one tap, voice optional. Everything else is later.

## Why this angle wins (for *this* learner)

- **He has no other forcing function.** Exams are what normally consolidate;
  he has none. Of the seven, only Recall replaces that missing pressure — without
  it, ten months of manifolds quietly evaporates the day he closes Tu.
- **It calls the bluff the others would honor.** When he says "I'll assume I got
  it," the Atlas lights that territory as *walked*, the Streak rewards the *log*,
  the Concept-Web *links* it — all of them take his word. Only the Recall Engine
  says "let's check in 10 days." That skepticism *about his own retention* is
  uniquely this product's.
- **The book makes the questions good.** His notes supply *what he struggled
  with* and *his phrasing*; the book supplies the *canonical answer* and the
  *right grain*. Together they let the app ask at desirable difficulty (Bjork) —
  not "what is Van Kampen" (trivial, he just did it) but "rebuild the detour-loop
  trick along γ_R" (the precise step he flagged) — and still grade honestly
  against the book's statement.
- **He's already doing the weak version.** Re-reading "now and then" and manually
  reciting the setup at session start *are* retrieval instincts. This is the
  smallest, most natural intervention because it's the upgrade of a behavior he
  already has — not a new ritual to adopt.

## Risks / why it might fail

- **It feels like school — the thing he's escaping.** Fatal if it nags. Mitigate:
  tiny, opt-in, voice-first, framed as "still got it?" play; *never* a red badge
  or a guilt-tripping "14 cards due." Reward is the felt click of remembering and
  visible compounding ("23 concepts kept alive across 6 weeks"), not a score.
- **Math isn't flashcard-atomic.** A proof is not a fact; trivializing deep
  understanding into Anki term-cards would insult the material. Mitigate: prompt
  for *reconstruction / explain-it-back* (free recall, the generation effect),
  not definition-matching. Tier prompts: 30-sec concept checks vs. "reprove the
  hard step."
- **Auto-grading free-form math is unsolved.** Mitigate: don't try. **Self-grade**
  against the revealed note + book statement — honest, cheap, and it keeps the
  learner in the loop (which is itself good for learning).
- **A dumb question breaks trust instantly.** One "what is a set?" and he's gone.
  Mitigate: seed only from flagged-uncertainty and load-bearing recurring
  techniques; ship few, high-confidence cards; let him 👎 a card to kill it.
- **Two-week-old corpus is thin** for spacing. Mitigate: it grows daily and even
  now yields a real 8-day Van Kampen gap; cold-start questions from the **book's**
  chapter structure until notes accumulate.

## Napkin sketch

```
┌─ Today, before you start ───────────────────────────────┐
│  🔁 One quick recall   ·   ~90 sec   ·   from Jun 28     │
│                                                          │
│  You set this one aside as "I'll assume I got it."       │
│                                                          │
│  ❝ Why must two successive grid vertices share a         │
│    common open set A_i in the Van Kampen homotopy? ❞     │
│                                                          │
│        🎙️ say it      ✍️ type it      🤔 show me         │
│ ──────────────────────────────────────────────────────  │
│  After reveal:   your note (Jun 28) │ Hatcher §1.2       │
│            How'd it go?  [ Solid ]  [ Fuzzy ]  [ Gone ]  │
└──────────────────────────────────────────────────────────┘

Kept alive:  ▓▓▓▓▓▓▓▓░░  23 concepts · longest hold 41d
Fading soon: orientation forms · interior product · IFT
```

No deck, no streak, no due-pile. One card a day, then the book.

## Fit to his practice

- **Tu (weekday manifolds):** one theme is being hammered organically —
  *"nowhere-vanishing top form"* is the orientation construction in 6/19, 6/24,
  6/25, 6/26 *and* 6/27. That's spaced repetition happening by accident on a
  *transferable technique* — the ideal retrieval target. "You've built an
  orientation three ways now (level set, Lie group, parallelizable manifold) —
  without looking, what's the one move they share?"
- **Hatcher (Sunday AT):** the Van Kampen proof spans 6/20 (four sessions in one
  day) → 6/28 (eight days later), and he restarts by reciting the setup. Sunday
  morning is the natural slot for an AT recall card; the long inter-Sunday gap is
  *exactly* the spacing the science wants.
- **Monthly 5h math-day:** a perfect "consolidation sweep" — a slightly longer
  retrieval set across the month's hardest-flagged steps, the one day there's
  room for it.
- **Finishing Tu (~80 pages out):** the single highest-value moment for this
  product. The day he closes Tu, all of manifolds stops being touched and starts
  decaying. The Recall Engine should ramp manifolds retrieval up *precisely then*
  — "you've moved on from Tu; here's the keep-alive plan so ten months of work
  doesn't fade" — turning a clean ending into durable knowledge instead of a
  closed book.
- **Cadence:** he studies 1h/day, every day — enormous surface area for a
  90-second warm-up. The constraint is never opportunity; it's keeping the ask
  small, kind, and grounded enough that he *wants* the check.

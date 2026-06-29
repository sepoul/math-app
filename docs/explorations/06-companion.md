# 06 — The Companion

*Lens: conversational-product designer. Sibling directions: Atlas (map), Mentor-Loop (prescribed actions), Streak (motivation), Concept-Web (idea-graph), Recall-Engine (scheduled review), Skeptic (pre-mortem). This one stays in its lane: **free-form, grounded conversation is the entire product.***

## The bet

This product **is a study partner you talk to** — one that has read your book *and* every session note you've ever recorded. Not a dashboard, not a queue, not a map: a text box and a mic. The moat over ChatGPT is that it knows your **exact position and your ten-month trail**, in *your* words. The relationship is the product.

## The job & the moment

He studies alone. No teacher, no study group, no exams, ten months and counting. The thing he is missing is not information (the book has it) and not tracking (he barely reads his own notes) — it is **an interlocutor who already knows where he is.** The Companion is the study partner he never had.

He'd reach for it at four real moments, all visible in his actual corpus:

- **Re-entry (start of session).** His two tracks are interleaved — Tu daily, Hatcher on Sundays — so a week passes between algebraic-topology sittings. "Where was I?" is a genuine cold-start cost every Sunday. On **2026-06-28** he ended mid-proof; the following Sunday he'll be staring at a notebook trying to reload the whole Van Kampen grid from scratch.
- **Stuck, mid-session (rubber-duck).** His 06-28 note is literally a person thinking out loud through the hardest step — *"we declare the concept of vertices… each vertex belongs to two or three rectangles…"* He talks his way through it now to no one. The Companion talks back.
- **Self-check.** 06-27: *"Honestly, not really sure about the correctness"* (Lie groups parallelizable). 06-26: *"I've seen the problem before, I just was not figuring it out."* He wants a peer to press on his proof.
- **Sunday reflection / the transition.** "What did I actually do this week?" — and, with ~80 pages left in Tu, the big one: "given everything I've worked through, what should I read next?"

The tell that this direction fits *him* specifically: **he already talks to the app.** On 2026-06-25 he opened a voice note with *"this is a message for you, synthesists… don't spoil the last exercise, I'm working on it, please."* The recording ritual is already a monologue *to* an interlocutor. The Companion just turns the monologue into a dialogue — no new muscle to build.

## The experience / the aha

He types (or says): **"What was I stuck on last Sunday?"**

> *You were on the Van Kampen proof — the step you called "the hardest part, at least for me": restricting the homotopy `F` to the path `γ_R` and building, for each vertex `V`, a path `J_V` sitting inside every rectangle that shares `V`, so two successive vertices land in a common `A_α`. You wrapped up saying you'd "just keep moving and assume I got it." Want to actually close that today, or keep moving?*  — *from your 06-28 note · Hatcher §1.2*

That is the aha. It remembered the gap **better than he did, in his own language, about his own math, and caught the confusion he chose to defer.** ChatGPT can explain Van Kampen all day; it can never say *you* got stuck *here*, in *these words*, and quietly skipped it. That sentence is impossible to paste into a fresh chat — it's his trail, not the book.

Everything else is the same surface. "Quiz me on orientations" → questions drawn from his Tu sections (pointwise orientation → oriented atlas → non-vanishing top form), at the depth his notes show he reached. "Does the orientation-form stuff connect to anything in Hatcher?" → answered in prose, grounded in both books. "Is my parallelizability proof right?" → it presses on the left-invariant-frame argument the way his book frames it. One box absorbs every other product's job — without making him learn a new UI.

## MVP

A single chat surface over a retrieval layer that already mostly exists. The synthesizer already emits, per note: `transcript`, sectioned `synthesis.markdown`, extracted `concepts[]`, a `summary`, and `magnitude` — a clean, concept-tagged substrate. Add one thing: the **table of contents / section structure of his two books** (Tu, Hatcher), so answers can anchor to "§1.2" not just "your notes."

One system prompt, ruthless about grounding: *"You are his study partner. You have read his book and every session note. Answer from HIS position and HIS words; cite the note date and book section. If something isn't in his trail or the book, say so — never invent what he proved, never spoil an exercise he's working on."*

Three intents proven day one: **"where was I?", "quiz me on X", "I'm stuck on X."** No scheduler, no map, no streak, no prescription engine.

Leanest possible seed: a **reply box under each daily note** — the conversation is born inside the artifact he already creates, context pre-loaded with that note and its neighbors — before it graduates into a standing companion he opens anytime.

## Why this angle wins

The other six are all **things you look at**: a map, a review queue, a streak counter, a concept graph, a prescription list, a memo. The Companion is the only one that's **someone you talk to.** For a solo hobbyist that asymmetry is the whole game — his deficit is conversational, not informational. It's also the **lowest-friction surface in the bunch**: a text box quietly does the Atlas's "where am I," the Recall Engine's "quiz me," and the Mentor's "what next," on demand and in his words, with zero UI to learn. And it's the only direction whose value **compounds with tenure** — every session makes it more uniquely his, which is exactly the asset ChatGPT can never accumulate.

## Risks / why it might fail

- **The corpus is two weeks old.** The "knows me for ten months" magic is back-loaded; in month one it's barely better than ChatGPT-with-a-good-paste. The book grounding has to carry the early weeks while the trail thickens.
- **He's a pen-and-paper purist.** He *left Lean because it felt too much like programming.* A chatbot may be the wrong texture for contemplative solo math — turning his monologue into dialogue is a real behavior change, not a given (even if he already half-does it).
- **Hallucination at the exact edge of his knowledge is fatal.** If it ever fabricates "you proved X" when he didn't — or spoils the exercise he explicitly asked it not to (06-25!) — trust dies in one turn. Grounding-or-silence must be ironclad, matching the synthesizer's existing "stores nothing rather than guessing" ethos.
- **Blank-box paralysis.** A mic and an empty thread is intimidating; he may never form the question. Needs gentle openers seeded from his last session ("Pick up the `J_V` gap from Sunday?").
- **It competes with the page.** Mid-proof, reaching for a chat could break flow rather than restore it. The stuck-moment value must clearly beat "keep staring at the notebook."

## Napkin sketch

```
┌──────────────────────────────────────────────┐
│  your study partner                          │
│                                              │
│            What was I stuck on last Sunday? ▕│  ← his turn
│                                              │
│ ▏ The Van Kampen proof — the step you called │
│ ▏ "the hardest part." Restricting F to γ_R   │
│ ▏ and the vertex paths J_V. You said you'd   │
│ ▏ "keep moving and assume I got it."         │
│ ▏  ┌ from your 06-28 note · Hatcher §1.2 ┐   │  ← grounding chips
│ ▏  Close that gap now, or keep moving?       │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │ ask anything…                      🎙  ▶ │  │  ← text OR voice-in
│  └────────────────────────────────────────┘  │
└──────────────────────────────────────────────┘
   no nav · no map · no queue — just the conversation
```

**Voice vs text — a deliberate split.** Logging is voice (he already does it). *Conversation* splits by mode: **voice for the messy thinking-out-loud** when he's stuck mid-proof with a pen in hand (exactly his 06-28 register — "we declare the concept of vertices…"), **text for precise quizzing and lookups** where he needs to *read* the LaTeX. Voice-in lowers the activation energy at the stuck-moment to nearly zero: he just says the question he'd otherwise mutter to himself.

## Fit to his practice

- **Daily Tu (1h):** re-entry ("where was I in orientations?") and self-check on proofs he's unsure of (06-27, 06-26 modes).
- **Sunday Hatcher (2h):** the week-long gap between sittings is precisely where "what was I doing last Sunday?" earns its keep — it reloads the `γ_R` / `J_V` thread he'd otherwise rebuild from cold.
- **Monthly 5h math-day (06-20):** a sustained think-out-loud partner for the whole day — the closest thing to a study group he'll get.
- **Finishing Tu (~80 pp left):** the standout moment — "given my entire trail, what next?" answered by the one entity that has read every session. The peer who knows where you've been is the right one to ask where to go.
- **2-week corpus:** named honestly as the cold-start weakness. The relationship is a promise that compounds; the book grounding carries the first month while the trail catches up.

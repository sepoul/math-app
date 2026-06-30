# Track C — Indexing & hybrid-retrieval bake-off — FINDINGS

Scope/contract: issue **#57** (Track C). Leads on **the headline result**.
Tables: `c_chunks`, `c_baseline_chunks`. Consumes `a_*`/`b_*` (or seed) **and
Track D's `d_queries`/`d_gold`**. Bucket: `track-c/`.

**Question (the headline):** does coarse-to-fine, structure-aware hybrid
retrieval (lexical FTS + pgvector + metadata/type boosts + rerank) **beat a
naive fixed-window chunk-embedding baseline** on Tu's queries — and which
signals carry the weight?

> Do NOT invent your own metrics — score against Track D's query set/gold.

---

## ROUND 1 — substrate stood up + naive baseline + both search paths (DONE)

R1 theme was **stand up the retrieval substrate + the naive baseline**, not the
scored head-to-head (that is R2, gated on Track D's gold). All R1 deliverables
landed and both index families are embedded and queryable.

### Source used
**`fitz_extract`** (the degrade-gracefully fallback). Track A's `a_nodes` was
**empty** at R1 (0 rows) and there is no seed fixture in `_shared/seed/`, so
`build_index.py` fell through to a direct PyMuPDF extract of the slice
(`extract_slice.py`). `build_index.py` already prefers `a_nodes` -> `seed` ->
`fitz_extract` (printed in its `source` field); when A lands, re-run
`build_index.py --source a_nodes` and the same `Node`-shaped rows swap in behind
the same code with no retriever changes.

The slice (per `_shared.db.SLICE`), in **PDF page** numbers — note **§7
Quotients is in Chapter 1**, not Chapter 7 (Tu numbers sections globally
§1..§29; the issue's "Ch7 §7" = the section number):

| section | title | pdf pages | leaves |
|---|---|---|---|
| §1 | Smooth Functions on a Euclidean Space | 22–28 | 6 |
| §2 | Tangent Vectors in R^n as Derivations | 29–36 | 9 |
| §3 | The Exterior Algebra of Multicovectors | 37–52 | 47 |
| §7 | Quotients | 90–104 | 24 |

### Tables (counts + dim + structure)

| table | rows | embedded | dim | unit |
|---|---|---|---|---|
| `c_chunks` (structured) | **90** | 90 | **1536** | 4 section + 86 leaf nodes |
| `c_baseline_chunks` (naive) | **40** | 40 | **1536** | ~450-word fixed windows, 60-word overlap |

`c_chunks` by kind: proof 25, example 21, proposition 13, corollary 8,
exercise 7, lemma 6, section 4, theorem 4, remark 2 · **definition 0** (see
risks). Proof->theorem links recovered: **25** (stored in `meta.proves` —
available to Track B / structural queries). Embedder: OpenAI
`text-embedding-3-small`, 1536-d, identical for both tables (so the variable
under test is *structure*, not the embedder). `embed_input` for structured
units is the §12 contextualized block (Book/Chapter/Section/Type/Label + text);
baseline `embed_input` is the raw window.
`tsv = to_tsvector('english', heading_path || label || title || text)`.

### The two systems
- **Structured-hybrid** (`retrieve.hybrid` over `c_chunks`): candidate pool =
  union of lexical (`tsv @@ plainto_tsquery` + `ts_rank`) U vector (`<=>` cosine)
  top-30; score = `w_vec*vec_n + w_lex*lex_n + w_type*type_boost + w_label*label_boost`
  with min-max-normalized lexical/vector. **type_boost** = light intent->kind map
  (spec §13: "what is" -> definition; "theorem/prove" -> theorem/prop/lemma/cor +
  proof; "example/intuition" -> example/remark; "problem/exercise" -> exercise).
  **label_boost** = exact `label` match for "Theorem 7.7"-style queries.
  Reranker term is a **stub** (LLM/cross-encoder rerank lands R2).
- **Naive baseline** (`c_baseline_chunks`): fixed 450-word windows, no structure,
  no labels, no type. Searchable by vector + lexical for an apples-to-apples
  comparison.

---

## QUALITY — qualitative structured-vs-naive on the 5 probes (eyeball, R1)

Real scoring vs gold is R2. These are R1 observations from `bakeoff.py`.

| probe | structured-hybrid top hit | naive (vector) top hit | what structure bought |
|---|---|---|---|
| "definition of quotient topology" | Theorem 7.7 (p94) — vector-led; right *neighborhood* | a window on p90 mentioning "quotient construction" | structured returns whole typed units (Thm/Example/Cor on quotients) vs mid-sentence windows; but **no `definition` leaf exists** so neither nails a crisp definition (book property, not a retriever bug) |
| "theorem about the quotient construction" | **Theorem 7.7** (p94), boosted past a bare quotient window by `type_boost=0.8` | window on p90 (gluing edges prose) | **clear win**: type boost promotes the actual theorem statement over prose that merely contains the words |
| "Problem 7.11" (structural/label) | surfaces **Exercise 7.11** (p96) via `type_boost=1.0`; lexical pulls the §7 section + Example 7.13 (which cites it) | unrelated projective-space windows (p98/p100); naive **lexical returns rank-0 garbage** | **clearest structure win**: label/type awareness finds the right exercise; naive has no notion of a labeled unit. (label_boost didn't fire — query says "Problem", node label is "Exercise" — see risk #2) |
| "smooth versus analytic functions" | §1 section node (lexical) + **Example 1.2/1.3** (the C-infinity-vs-analytic examples, p23–24) | windows on p23–24 (right pages) | near-tie on *page*, but structured returns the **named worked examples** ("A C-infinity function very flat at 0") as whole units vs truncated windows |
| "regular value" (CONTROL — not in slice) | drifts to §7 / Example 1.3 / a §3 corollary | low-sim windows (~0.33) on tangent-vector pages | both correctly weak; structured at least returns coherent units. No false confidence. |

**What structure already seems to buy (R1, pre-gold):**
1. **Retrieval units are whole semantic objects** (a theorem, a proof, a worked
   example) carrying label + heading-path + page — directly source-traceable
   (§17). Naive windows are mid-sentence and split statements across windows.
2. **Type/metadata boosts demonstrably re-rank** — the "theorem about…" and
   "Problem 7.11" probes both promote the structurally-correct unit over a
   lexically/semantically similar but wrong-type passage. This is the signal the
   spec (§13) predicts carries weight for math; R1 supports that qualitatively.
3. **Label routing is feasible** — exact-label match is a strong, cheap signal
   the baseline structurally cannot have.
4. **Lexical is essential alongside vectors** — for "Problem 7.11" and "smooth
   vs analytic" the lexical term carried the right hit; pure vector under-ranked
   them. Confirms §13 ("embeddings should not be the only mechanism").

---

## SPEED / cost (R1, slice scale)

**Index build (one-time):**
- Embedding 90 structured inputs: **0.71 s** / 41,847 tokens.
- Embedding 40 baseline windows: **0.28 s** / 31,332 tokens.
- Full `build_index.py` end-to-end (fitz extract + embed + DB writes): **~8 s**.
- Cost @ `text-embedding-3-small` ($0.02/1M tok): **~$0.0015** to embed the whole
  slice. Negligible — comfortably inside a daily synthesis pass.

**Per-query latency** (mean over 5 probes, *cold* — fresh connection each call):

| path | mean | min | max |
|---|---|---|---|
| structured-hybrid | 2291 ms | 1902 | 3700 |
| naive vector | 1015 ms | 966 | 1116 |
| naive lexical | 831 ms | 811 | 881 |

**Latency decomposition (the honest read):** the headline ms are dominated by
**fixed overheads, not retrieval work**:
- query embedding API call: **~600 ms** (one per query)
- opening a fresh Supabase connection over TLS: **~800 ms** (the R1 code calls
  `connect()` inside *each* primitive, so hybrid pays this 3x)
- the actual pgvector KNN SQL, **warm on a shared connection: ~39 ms** for top-10
  over 90 rows; lexical is similar.

So true retrieval cost at slice scale is **tens of ms**; the seconds are
connection setup + the embedding round-trip, both eliminable (pool/reuse one
connection; cache/batch the query embedding). R2 will report warm latency with a
shared connection so the speed verdict isn't an artifact of scrappy R1 plumbing.

---

## BLOCKERS / RISKS

1. **Depends on Track A's `a_nodes`** for the *real* structured corpus. R1 ran on
   a self-built fitz extract — good enough to stand up the substrate and show the
   structure effect, but its segmentation is scrappy (regex leaf boundaries, no
   block-geometry, equations inlined as glyph-soup). Quality numbers in R2 will
   only be as good as A's skeleton. **Need: A's `a_nodes` populated for the slice.**
2. **Depends on Track D's gold** for the scored head-to-head + ablation (the
   headline). Cannot compute recall@k / MRR / exact-label-hit without
   `d_queries`/`d_gold`. **Coordinated the format in `track-c/GOLD_CONTRACT.md`**
   — key asks: (a) put a **pdf page range on every gold row** so the label-less
   naive baseline can be scored on the same stick; (b) prefer **`gold_label`**
   over node-id (C's fallback ids change when A lands); (c) gold for
   "definition of X" queries must target a **section/page**, not a `definition`
   leaf, because **Tu has 0 "Definition N.M" labels in this slice** (definitions
   are bold-inline); (d) "Problem N" should map to gold_label "Exercise N"
   (Tu body label) — the "Problem"/"Exercise" naming split is real.
3. **Math is glyph-soup.** Display/inline math extracts as broken glyphs
   (`pi-1[alpha...`, NUL bytes — now stripped). Lexical search on symbol-heavy
   queries will be weak; this is a known §9 limitation, not fixable at the
   retrieval layer. Symbol queries will lean on vector + label.
4. **Section-node embeddings are truncated.** §3 is 16 pages; its raw
   concatenation exceeds the 8192-token embed cap, so it's truncated at ~22k
   chars. A real build should embed a **section summary** (spec §12), not raw
   text. Doesn't affect leaf retrieval; mildly weakens coarse section retrieval.

---

## NEXT (what Track C needs from A / B / D in R2)

- **From D (hard dependency, the headline):** publish `d_queries` + `d_gold`
  per `GOLD_CONTRACT.md` — graded relevance + **pdf page ranges** + label-based
  gold. Without it there is no scored bake-off.
- **From A:** populate `a_nodes` for the slice (real segmentation + page mapping
  + confidence). C re-runs `build_index.py --source a_nodes` to swap the corpus.
  Especially want A's take on **bold-inline definition** recovery.
- **From B:** `b_node_edges` (`proven_by`, `references`, `next`/`previous`) for
  the **structural / graph-expansion** query categories. C has `proves` already
  (25 links) and can degrade to section-membership, but real edges enable the
  §14 structural lookups properly.
- **Track C R2 plan:** (1) scored head-to-head structured-hybrid vs naive on D's
  gold (recall@5, MRR, exact-label hit, source-traceability); (2) per-signal
  **ablation** (drop type_boost / label_boost / lexical / vector — the
  `use_type` / `use_label` / weight knobs already exist in `retrieve.hybrid`);
  (3) add the **rerank** stage (LLM scorer via the Anthropic client, top-20->top-10);
  (4) warm-connection latency so speed numbers aren't plumbing artifacts.

---

## Files (track-c/)
- `extract_slice.py` — R1 fallback structured extractor (fitz, spec §8 regexes).
- `baseline.py` — naive fixed-window chunker.
- `embed.py` — OpenAI `text-embedding-3-small` (1536-d) helper.
- `build_index.py` — writes `c_chunks` + `c_baseline_chunks` (source: a_nodes->seed->fitz).
- `retrieve.py` — lexical / vector / hybrid primitives over either table.
- `bakeoff.py` — the 5-probe R1 sanity bake-off.
- `GOLD_CONTRACT.md` — gold-format coordination for Track D.

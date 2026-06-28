/**
 * Tests for the `validate_latex` validation core (issue #33).
 *
 * Focus: the new render-aware `markdown` mode rejects a document that would
 * render raw under remark-math — leftover `\[…\]` / `\(…\)`, or math-like
 * content outside any `$` delimiter — while `document` mode keeps accepting the
 * legacy delimiters math_qa relies on.
 *
 * Compiled by `tsconfig.test.json` (Node can't strip TS types here), then run
 * with `npm test`. See package.json `test` script.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import {
  validateLatex,
  findLegacyDelimiter,
  findStrayMath,
  findUnfencedDisplay,
} from "../app/api/tools/validate-latex/validate.js";

// ---- markdown mode: the issue #33 close-out ----

test("markdown mode REJECTS a doc with `\\[ … \\]` display math", () => {
  const doc = "The flux is\n\n\\[ \\iint_S F\\cdot n\\,dS \\]\n\nfor the region.";
  const res = validateLatex(doc, "markdown");
  assert.equal(res.valid, false);
  assert.match(res.error ?? "", /\\\[/); // error names the offending delimiter
});

test("markdown mode REJECTS a doc with `\\( … \\)` inline math", () => {
  const res = validateLatex("Let \\( x \\) be real.", "markdown");
  assert.equal(res.valid, false);
  assert.match(res.error ?? "", /remark-math/);
});

test("markdown mode REJECTS a bare TeX command outside any `$`", () => {
  const res = validateLatex("The derivative \\frac{dy}{dx} grows.", "markdown");
  assert.equal(res.valid, false);
  assert.match(res.error ?? "", /outside any/);
});

test("markdown mode REJECTS a stray braced subscript outside `$`", () => {
  const res = validateLatex("the term i_{\\alpha\\beta} appears", "markdown");
  assert.equal(res.valid, false);
});

test("markdown mode ACCEPTS canonical `$`/`$$` math + prose", () => {
  const doc = "## Result\n\nWe have $a + b$ and then\n\n$$\nx^2 \\ge 0\n$$\n\ndone.";
  assert.deepEqual(validateLatex(doc, "markdown"), { valid: true });
});

test("markdown mode ACCEPTS a prose-only document (no math)", () => {
  assert.deepEqual(validateLatex("Just words, no math here.", "markdown"), {
    valid: true,
  });
});

test("markdown mode ACCEPTS prose with a `$5 and $10` false-positive", () => {
  // The inline `$` pattern won't match currency, and `5`/`10` aren't math-like.
  assert.deepEqual(validateLatex("It cost $5 and then $10 total.", "markdown"), {
    valid: true,
  });
});

test("markdown mode still KaTeX-compiles the `$` segments (catches bad TeX)", () => {
  const res = validateLatex("Broken: $\\frac{1}$ here.", "markdown");
  assert.equal(res.valid, false);
  assert.equal(res.segment, "\\frac{1}");
  assert.equal(res.segment_index, 0);
});

// ---- markdown mode: glued multi-line $$ display (issue #33, 2nd trigger) ----

test("markdown mode REJECTS a glued multi-line `$$ … $$` display block", () => {
  const doc = "Result:\n\n$$i_{\\alpha}^{\\beta} \\colon A \\to B, \\qquad\nj \\colon B \\to C.$$";
  const res = validateLatex(doc, "markdown");
  assert.equal(res.valid, false);
  assert.match(res.error ?? "", /own line/);
});

test("markdown mode ACCEPTS a properly fenced multi-line `$$` block", () => {
  const doc = "Result:\n\n$$\ni_{\\alpha}^{\\beta} \\colon A \\to B, \\qquad\nj \\colon B \\to C.\n$$";
  assert.deepEqual(validateLatex(doc, "markdown"), { valid: true });
});

test("markdown mode ACCEPTS a single-line `$$x$$` (renders fine)", () => {
  assert.deepEqual(validateLatex("inline-ish $$x^2$$ display", "markdown"), {
    valid: true,
  });
});

test("document mode does NOT require `$$` fencing (math_qa unaffected)", () => {
  // <Latex> handles multi-line `$$` fine, so document mode must not flag it.
  const doc = "$$a, \\qquad\nb.$$";
  assert.deepEqual(validateLatex(doc, "document"), { valid: true });
});

// ---- document mode: math_qa back-compat MUST be preserved ----

test("document mode STILL accepts `\\[ … \\]` (math_qa render target)", () => {
  // math_qa answers use \(...\) / \[...\] and render via <Latex>; document mode
  // must keep validating them as math, not reject them.
  assert.deepEqual(validateLatex("Display:\n\\[ x^2 \\ge 0 \\]", "document"), {
    valid: true,
  });
});

test("document mode accepts `\\( … \\)` inline and `$$ … $$`", () => {
  assert.deepEqual(validateLatex("Let \\( x \\) be, so $$y = x$$.", "document"), {
    valid: true,
  });
});

test("document mode still reports a failing legacy segment", () => {
  const res = validateLatex("\\[ \\frac{1} \\]", "document");
  assert.equal(res.valid, false);
  assert.equal(res.segment_index, 0);
});

// ---- inline / block modes unchanged ----

test("inline mode validates a bare expression", () => {
  assert.deepEqual(validateLatex("x^2 + 1", "inline"), { valid: true });
  assert.equal(validateLatex("\\frac{1}", "inline").valid, false);
});

test("block mode validates a bare display expression", () => {
  assert.deepEqual(validateLatex("\\sum_{n=1}^\\infty 1/n^2", "block"), {
    valid: true,
  });
});

// ---- pure helpers ----

test("findLegacyDelimiter finds each delimiter and returns null when clean", () => {
  assert.equal(findLegacyDelimiter("a \\[ x \\]"), "\\[");
  assert.equal(findLegacyDelimiter("a \\( x \\)"), "\\(");
  assert.equal(findLegacyDelimiter("$x$ and $$y$$"), null);
  // `\left(` is backslash-letter, NOT `\(` — must not false-positive.
  assert.equal(findLegacyDelimiter("$\\left( x \\right)$"), null);
});

test("findStrayMath ignores math inside `$`, flags it outside", () => {
  assert.equal(findStrayMath("all good $\\frac{a}{b}$ here"), null);
  assert.equal(findStrayMath("bad \\frac{a}{b} here"), "\\frac");
  // Markdown escapes (backslash + punctuation) are not flagged.
  assert.equal(findStrayMath("a \\* b \\_ c \\# d"), null);
});

test("findUnfencedDisplay flags glued multi-line, allows fenced + single-line", () => {
  assert.equal(findUnfencedDisplay("$$x$$"), null); // single-line is fine
  assert.equal(findUnfencedDisplay("$$\nx\ny\n$$"), null); // properly fenced
  assert.equal(findUnfencedDisplay("$$x\ny$$"), "$$x\ny$$"); // both glued
  assert.equal(findUnfencedDisplay("$$x\ny\n$$"), "$$x\ny\n$$"); // opener glued
  assert.equal(findUnfencedDisplay("$$\nx\ny$$"), "$$\nx\ny$$"); // closer glued
  assert.equal(findUnfencedDisplay("no display here, just $inline$"), null);
});

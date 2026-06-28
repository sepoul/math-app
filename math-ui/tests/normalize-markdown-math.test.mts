/**
 * Tests for the code-aware renderer pre-process (issue #33, second trigger).
 *
 * `normalizeMarkdownMath` converts legacy delimiters and flow-fences glued `$$`
 * so stored notes render correctly through remark-math — WITHOUT touching code
 * blocks or inline code. Compiled by `tsconfig.test.json`, run via `npm test`.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeMarkdownMath } from "../components/library/normalize-markdown-math.js";

// ---- conversion + flow-fencing on plain text ----

test("converts legacy `\\[ … \\]` to a fenced `$$` block", () => {
  const out = normalizeMarkdownMath("Before \\[ x^2 \\] after");
  assert.ok(out.includes("$$\nx^2\n$$"));
  assert.ok(!out.includes("\\["));
});

test("converts legacy `\\( … \\)` to inline `$`", () => {
  assert.ok(normalizeMarkdownMath("let \\(y\\) be").includes("$y$"));
});

test("flow-fences a single-line `$$x$$`", () => {
  assert.ok(normalizeMarkdownMath("$$x$$").includes("$$\nx\n$$"));
});

test("flow-fences a glued multi-line `$$` (the confirmed trigger)", () => {
  const out = normalizeMarkdownMath("$$a, \\qquad\nb.$$");
  assert.ok(out.includes("$$\na, \\qquad\nb.\n$$"));
  assert.ok(!out.includes("$$a,")); // opener no longer glued
});

test("leaves inline `$x$` math untouched", () => {
  assert.equal(normalizeMarkdownMath("a $x+y$ b"), "a $x+y$ b");
});

// ---- CODE-AWARENESS: must not mangle code ----

test("leaves a fenced code block VERBATIM (delimiters + glued $$ survive)", () => {
  const src =
    "Before $$out$$\n\n```\n\\[ code \\]\n$$glued\nmore$$\n```\n\nAfter";
  const out = normalizeMarkdownMath(src);
  // Inside the fence, nothing is rewritten:
  assert.ok(out.includes("\\[ code \\]"));
  assert.ok(out.includes("$$glued\nmore$$"));
  // Outside the fence, the real display math IS fenced:
  assert.ok(out.includes("$$\nout\n$$"));
});

test("leaves an inline code span VERBATIM", () => {
  const out = normalizeMarkdownMath("use `$$not math$$` and \\[real\\] here");
  assert.ok(out.includes("`$$not math$$`")); // inline code untouched
  assert.ok(out.includes("$$\nreal\n$$")); // real math converted + fenced
});

test("respects ~~~ fences and longer ``` runs", () => {
  const src = "~~~\n\\[ keep \\]\n~~~\nthen \\[ go \\]";
  const out = normalizeMarkdownMath(src);
  assert.ok(out.includes("\\[ keep \\]")); // inside ~~~ fence: verbatim
  assert.ok(out.includes("$$\ngo\n$$")); // outside: converted
});

// ---- idempotency ----

test("is idempotent", () => {
  const cases = [
    "$$x$$",
    "text \\[ y \\] and \\(z\\)",
    "$$a, \\qquad\nb.$$",
    "## H\n\n$$\nE = mc^2\n$$\n\nprose `code` and $inline$",
    "t $$x$$\n\n```\ncode \\[ x \\]\n```\nafter",
    "no math here at all",
  ];
  for (const src of cases) {
    const once = normalizeMarkdownMath(src);
    assert.equal(normalizeMarkdownMath(once), once, `not idempotent for: ${src}`);
  }
});

test("returns empty string unchanged", () => {
  assert.equal(normalizeMarkdownMath(""), "");
});

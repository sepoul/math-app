import katex from "katex";

/**
 * Pure LaTeX-validation core for the `validate_latex` agent tool, split out of
 * `route.ts` so it is unit-testable without Next's request plumbing.
 *
 * Modes:
 *
 * - `"inline"` / `"block"` — `latex` is a bare math expression; KaTeX-compile it
 *   with the matching `displayMode`.
 * - `"document"` (default) — mixed prose + math destined for the `<Latex>`
 *   renderer (`components/library/latex.tsx`), which supports BOTH `$...$` /
 *   `$$...$$` AND legacy `\(...\)` / `\[...\]`. Split on every delimiter and
 *   KaTeX-compile each math segment; prose is ignored. (math_qa answers use the
 *   legacy delimiters, so this mode must keep accepting them.)
 * - `"markdown"` — mixed prose + math destined for the **remark-math** renderer
 *   (`components/library/markdown-math.tsx`), i.e. `daily_note.synthesis`.
 *   remark-math lexes ONLY `$...$` / `$$...$$`, so this mode is render-aware:
 *   it REJECTS leftover `\(...\)` / `\[...\]` (they render raw) and math-like
 *   content sitting outside any `$` delimiter, in addition to KaTeX-compiling
 *   the dollar segments. This closes the issue #33 blind spot where `\[…\]`
 *   display math passed `document` validation yet rendered as raw text.
 */

export type ValidateMode = "inline" | "block" | "document" | "markdown";

export interface ValidationResult {
  valid: boolean;
  error?: string;
  segment?: string;
  segment_index?: number;
}

interface MathSegment {
  value: string;
  displayMode: boolean;
}

// `document` mode — mirrors `components/library/latex.tsx`'s SEGMENT_RE so the
// validator sees exactly the segments that renderer will. Order matters: `$$`
// before single `$`, otherwise the lazier `$` pattern eats both dollars. The
// inline `$` form requires a non-`$`/newline interior so "$5 and $10" doesn't
// match.
//   group 1: $$...$$   (block)    group 3: \(...\)   (inline, legacy)
//   group 2: \[...\]   (block)    group 4: $...$     (inline)
const DOCUMENT_SEGMENT_RE =
  /\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\]|\\\((.+?)\\\)|\$(\S(?:[^$\n]*?\S)?)\$/g;

// `markdown` mode — ONLY the dollar delimiters remark-math lexes. Same `$$`
// before `$` ordering and the same inline-`$` guard.
//   group 1: $$...$$   (block)    group 2: $...$   (inline)
const MARKDOWN_SEGMENT_RE = /\$\$([\s\S]+?)\$\$|\$(\S(?:[^$\n]*?\S)?)\$/g;

// A KaTeX-style delimiter remark-math ignores: `\[`, `\]`, `\(`, or `\)`. (No
// valid KaTeX math contains these adjacent pairs — `\left(` etc. are
// backslash-letter, not `\(` — so scanning the whole document is safe.)
const LEGACY_DELIMITER_RE = /\\[[\]()]/;

// Math-like content: a TeX control word (`\frac`, `\alpha`, `\colon`, …) or a
// braced super/subscript (`^{`, `_{`). Markdown escapes (`\*`, `\_`, `\#`,
// `\$`, `\\`) are backslash + punctuation, so the `\letter` form never matches
// them — only genuine TeX commands.
const STRAY_MATH_RE = /\\[a-zA-Z]+|[\^_]\{/;

function tryRender(value: string, displayMode: boolean): string | null {
  try {
    katex.renderToString(value, {
      displayMode,
      throwOnError: true,
      strict: "error",
    });
    return null;
  } catch (err) {
    return err instanceof Error ? err.message : "KaTeX failed to parse the input";
  }
}

function extractDocumentSegments(source: string): MathSegment[] {
  const out: MathSegment[] = [];
  for (const match of source.matchAll(DOCUMENT_SEGMENT_RE)) {
    if (match[1] !== undefined) {
      out.push({ value: match[1], displayMode: true }); // $$...$$
    } else if (match[2] !== undefined) {
      out.push({ value: match[2], displayMode: true }); // \[...\]
    } else if (match[3] !== undefined) {
      out.push({ value: match[3], displayMode: false }); // \(...\)
    } else if (match[4] !== undefined) {
      out.push({ value: match[4], displayMode: false }); // $...$
    }
  }
  return out;
}

function extractMarkdownSegments(source: string): MathSegment[] {
  const out: MathSegment[] = [];
  for (const match of source.matchAll(MARKDOWN_SEGMENT_RE)) {
    if (match[1] !== undefined) {
      out.push({ value: match[1], displayMode: true }); // $$...$$
    } else if (match[2] !== undefined) {
      out.push({ value: match[2], displayMode: false }); // $...$
    }
  }
  return out;
}

/**
 * The first `\[`/`\]`/`\(`/`\)` in `source`, or `null` if none. Exported for
 * tests — these delimiters render raw under remark-math (issue #33).
 */
export function findLegacyDelimiter(source: string): string | null {
  const m = source.match(LEGACY_DELIMITER_RE);
  return m ? m[0] : null;
}

/**
 * The first math-like token sitting OUTSIDE any `$`/`$$` segment, or `null`.
 * Strips the dollar math first, then scans the remaining prose for a TeX
 * control word or braced sup/subscript. Exported for tests.
 */
export function findStrayMath(source: string): string | null {
  const prose = source.replace(MARKDOWN_SEGMENT_RE, " ");
  const m = prose.match(STRAY_MATH_RE);
  return m ? m[0] : null;
}

function validateDocument(latex: string): ValidationResult {
  const segments = extractDocumentSegments(latex);
  if (segments.length === 0) {
    // No delimiters at all — a markdown document with no math is well-formed.
    return { valid: true };
  }
  for (let i = 0; i < segments.length; i++) {
    const error = tryRender(segments[i].value, segments[i].displayMode);
    if (error != null) {
      return { valid: false, error, segment: segments[i].value, segment_index: i };
    }
  }
  return { valid: true };
}

function validateMarkdown(latex: string): ValidationResult {
  // 1. Legacy KaTeX-style delimiters don't render via remark-math → reject,
  //    pointing the agent at the exact fix.
  const legacy = findLegacyDelimiter(latex);
  if (legacy != null) {
    return {
      valid: false,
      error:
        `Found a \`${legacy}\` delimiter. This document renders with remark-math, ` +
        "which only supports `$...$` (inline) and `$$...$$` (display) math — " +
        "`\\(...\\)` / `\\[...\\]` render as raw text. Replace every `\\(...\\)` " +
        "with `$...$` and every `\\[...\\]` with `$$...$$`.",
    };
  }
  // 2. KaTeX-compile each `$`/`$$` segment (exactly what the renderer lexes).
  const segments = extractMarkdownSegments(latex);
  for (let i = 0; i < segments.length; i++) {
    const error = tryRender(segments[i].value, segments[i].displayMode);
    if (error != null) {
      return { valid: false, error, segment: segments[i].value, segment_index: i };
    }
  }
  // 3. Math-like content OUTSIDE any `$`/`$$` delimiter would render raw.
  const stray = findStrayMath(latex);
  if (stray != null) {
    return {
      valid: false,
      error:
        `Found math-like content (\`${stray}\`) outside any \`$\`/\`$$\` delimiter; ` +
        "it would render as raw text. Wrap inline math in `$...$` and display math " +
        "in `$$...$$`.",
    };
  }
  return { valid: true };
}

/**
 * Validate `latex` per `mode`. Pure — no I/O — so `route.ts` can wrap it in a
 * `NextResponse` and tests can call it directly.
 */
export function validateLatex(latex: string, mode: ValidateMode): ValidationResult {
  if (mode === "inline" || mode === "block") {
    const error = tryRender(latex, mode === "block");
    return error == null ? { valid: true } : { valid: false, error };
  }
  if (mode === "markdown") {
    return validateMarkdown(latex);
  }
  return validateDocument(latex);
}

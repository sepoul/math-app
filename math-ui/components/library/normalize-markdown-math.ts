/**
 * Code-aware pre-process that makes stored synthesis Markdown render correctly
 * through remark-math, repairing the issue #33 drift at READ time (no data
 * migration). It mirrors the backend normalizer (`mathai.math_notes.text`):
 *
 *   1. Legacy `\(...\)` / `\[...\]` → `$...$` / `$$...$$` (remark-math only
 *      lexes the dollar forms).
 *   2. Flow-fence every `$$...$$` onto its own lines (`$$\n...\n$$`, blank-line
 *      separated). A `$$` glued to its first content line that then spans a
 *      newline is mis-lexed by micromark as single-line text math and renders
 *      raw; fencing forces it to parse as a multi-line display block.
 *
 * Why a string pre-process and not a remark transformer: remark-math tokenizes
 * math at PARSE time (a micromark extension), so by the time an mdast
 * transformer runs, the glued `$$` is already mis-parsed. We must fix the raw
 * text before `<ReactMarkdown>` parses it.
 *
 * CRITICAL — it must not touch code. The transform is applied ONLY to text
 * outside fenced code blocks (``` / ~~~) and inline code spans (`` ` ``), so a
 * `` `$$not math$$` `` snippet or a fenced TeX example is left verbatim.
 * (Indented 4-space code blocks are intentionally not special-cased — they are
 * ambiguous with list-item continuation and synthesis output uses fenced code.)
 *
 * Pure and idempotent — re-running is a no-op (legacy delimiters are gone, an
 * already-fenced `$$` re-fences to itself, 3+ newlines collapse to 2).
 */

// Replacers are FUNCTIONS, not strings: a `$$` in a `String.replace` replacement
// string is an escaped single `$`, which would silently turn `\[` into `$`
// (inline) instead of `$$` (display). A function return value is used verbatim.
const LEGACY: ReadonlyArray<readonly [RegExp, () => string]> = [
  [/\\\(/g, () => "$"],
  [/\\\)/g, () => "$"],
  [/\\\[/g, () => "$$"],
  [/\\\]/g, () => "$$"],
];

// A `$$...$$` display span (non-greedy, spans newlines for the glued case).
const DISPLAY_RE = /\$\$([\s\S]+?)\$\$/g;
const BLANK_RUN_RE = /\n{3,}/g;
// An inline code span: a run of N backticks, content, then a run of N backticks
// not followed by another backtick (so a longer run isn't split).
const INLINE_CODE_RE = /(`+)([\s\S]+?)\1(?!`)/g;
// The opening of a fenced code block (optionally indented): 3+ ` or 3+ ~.
const FENCE_OPEN_RE = /^(\s*)(`{3,}|~{3,})/;
// A line that is only a closing fence (no info string).
const FENCE_CLOSE_RE = /^(\s*)(`{3,}|~{3,})\s*$/;

/** Convert legacy delimiters and flow-fence `$$` in a span of plain text. */
function normalizeMath(text: string): string {
  let out = text;
  for (const [re, replacer] of LEGACY) out = out.replace(re, replacer);
  out = out.replace(
    DISPLAY_RE,
    (_match, content: string) => `\n\n$$\n${content.trim()}\n$$\n\n`
  );
  return out.replace(BLANK_RUN_RE, "\n\n");
}

/** Normalize only the text OUTSIDE inline code spans within one non-fenced block. */
function normalizeOutsideInlineCode(block: string): string {
  let result = "";
  let last = 0;
  INLINE_CODE_RE.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = INLINE_CODE_RE.exec(block)) !== null) {
    result += normalizeMath(block.slice(last, match.index));
    result += match[0]; // inline code span — verbatim
    last = match.index + match[0].length;
  }
  result += normalizeMath(block.slice(last));
  return result;
}

export function normalizeMarkdownMath(source: string): string {
  if (!source) return source;

  const lines = source.split("\n");
  const out: string[] = [];
  let buffer: string[] = [];
  let fenceMarker = ""; // the opening run, e.g. "```" — "" when not in a fence

  const flush = () => {
    if (buffer.length) {
      out.push(normalizeOutsideInlineCode(buffer.join("\n")));
      buffer = [];
    }
  };

  for (const line of lines) {
    if (!fenceMarker) {
      const open = line.match(FENCE_OPEN_RE);
      if (open) {
        flush();
        fenceMarker = open[2];
        out.push(line);
      } else {
        buffer.push(line);
      }
    } else {
      out.push(line); // inside a fenced code block — verbatim
      const close = line.match(FENCE_CLOSE_RE);
      if (
        close &&
        close[2][0] === fenceMarker[0] &&
        close[2].length >= fenceMarker.length
      ) {
        fenceMarker = "";
      }
    }
  }
  flush();
  return out.join("\n");
}

import { NextResponse } from "next/server";
import { validateLatex, type ValidateMode } from "./validate";

/**
 * LaTeX validation service for backend agents (the `validate_latex` tool).
 *
 * The validation core lives in `./validate.ts` (pure, unit-tested); this route
 * only parses the request and wraps the result in a `NextResponse`.
 *
 * Modes (selected by `mode`, default `"document"`):
 *
 * - `"inline"` / `"block"` — `latex` is a bare math expression.
 * - `"document"` — mixed prose + math for the `<Latex>` renderer; recognises
 *   both `$...$` / `$$...$$` and legacy `\(...\)` / `\[...\]` (math_qa answers).
 * - `"markdown"` — mixed prose + math for the **remark-math** renderer
 *   (`daily_note.synthesis`); `$`-only, and additionally rejects leftover
 *   `\(...\)` / `\[...\]` and math-like content outside any `$` delimiter so a
 *   note can't pass validation yet render raw (issue #33).
 *
 * Response: `{ valid: true }` or
 * `{ valid: false, error, segment?, segment_index? }`.
 */

interface RequestBody {
  latex?: string;
  mode?: ValidateMode;
}

export async function POST(request: Request) {
  let body: RequestBody;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { valid: false, error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  const latex = typeof body.latex === "string" ? body.latex : null;
  if (!latex) {
    return NextResponse.json(
      { valid: false, error: "Missing `latex` field" },
      { status: 400 }
    );
  }

  const mode: ValidateMode = body.mode ?? "document";
  return NextResponse.json(validateLatex(latex, mode));
}

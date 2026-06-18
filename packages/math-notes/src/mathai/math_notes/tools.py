"""Agent tools for the math_notes page-parse step.

`validate_latex` round-trips content through the math-ui Next.js endpoint
(`POST /api/tools/validate-latex`), where KaTeX runs with
`throwOnError: true`, returning a structured pass/fail so an agent can
self-correct on retry. This is a **deliberate duplicate** of the math_qa
tool of the same name: the two domains ship as separate wheels into
(potentially) different worker images, so cross-importing a sibling
domain would couple their install graphs. The client is ~30 lines; the
copy keeps each domain self-contained (see `docs/math-conversation.md` →
the same "duplicate the thin client" call).

The endpoint URL is read from `UI_TOOL_API_URL` (in compose:
`http://math-ui:7860`; default `http://localhost:3000` for bare-metal
dev). When the UI is unreachable the caller treats validation as
unavailable and stores no LaTeX rather than guessing.
"""
from __future__ import annotations

import os
from typing import Literal, Optional

import httpx
from pydantic import BaseModel

_DEFAULT_UI_URL = "http://localhost:3000"
_TIMEOUT_SECONDS = 10.0


class LatexValidationResult(BaseModel):
    valid: bool
    error: Optional[str] = None
    # Populated when `mode="document"` and a specific math segment failed —
    # lets the agent locate the issue without re-scanning.
    segment: Optional[str] = None
    segment_index: Optional[int] = None


def _ui_url() -> str:
    return os.getenv("UI_TOOL_API_URL", _DEFAULT_UI_URL).rstrip("/")


async def validate_latex(
    latex: str,
    mode: Literal["inline", "block", "document"] = "document",
) -> LatexValidationResult:
    """Validate KaTeX-compilable content via the math-ui server.

    `mode="document"` (default): `latex` is markdown with `\\(...\\)` /
    `\\[...\\]` math delimiters; each math segment is validated
    independently and prose is ignored. `mode="inline"` / `"block"`:
    `latex` is a bare math expression.

    Returns `{valid: true}` on success, else `{valid: false, error,
    segment?, segment_index?}` — the agent reads `error` (and `segment`)
    to locate the issue and correct on the next turn.
    """
    url = f"{_ui_url()}/api/tools/validate-latex"
    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
        response = await client.post(url, json={"latex": latex, "mode": mode})
        response.raise_for_status()
        return LatexValidationResult.model_validate(response.json())

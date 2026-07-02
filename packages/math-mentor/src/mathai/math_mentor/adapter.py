"""`PlatformBookRetrieve` — the production `BookRetrieveFn`, backed by a platform.

A thin concrete adapter implementing the `BookRetrieveFn` port (see `port.py`)
by submitting a real `book_retrieve` job to a running ai-platform and parsing the
result back into a `BookRetrievalResult`.

`ai_platform` is imported **lazily, inside `__call__`** — never at module import
time — so unit tests (which inject an in-memory fake port) never require the
platform SDK to be installed. Importing `mathai.math_mentor` stays lightweight.
"""
from __future__ import annotations

from typing import Any, Optional

from mathai.math_book.models import BookRetrievalResult, BookRetrieveInput


class PlatformBookRetrieve:
    """A `BookRetrieveFn` that runs `book_retrieve` on a live ai-platform.

    Usage::

        retrieve = PlatformBookRetrieve(api_url="http://localhost:8000")
        anchor = resolve_anchor(retrieve, book_id="Tu", coordinate="Problem 2.16",
                                topic="Stokes' theorem", intent="theorem")

    One `PlatformSession` is opened (and closed) per call; retrieval is a short
    request/response so a long-lived session isn't warranted here.
    """

    def __init__(
        self,
        api_url: str,
        *,
        connect_timeout: float = 30.0,
        wait_timeout: float = 120.0,
        poll_interval: float = 1.0,
    ) -> None:
        self._api_url = api_url
        self._connect_timeout = connect_timeout
        self._wait_timeout = wait_timeout
        self._poll_interval = poll_interval

    def __call__(self, req: BookRetrieveInput) -> BookRetrievalResult:
        # Lazy import: keeps the platform SDK out of the unit-test dependency
        # surface. Only a real, platform-backed call needs it.
        from ai_platform.session.session import PlatformSession

        with PlatformSession.connect(
            self._api_url, timeout=self._connect_timeout
        ) as session:
            handle = session.submit_job("book_retrieve", req.model_dump())
            # `.result()` blocks until the job is terminal, then GETs the typed
            # result envelope: {"job_id": ..., "result": {<BookRetrievalResult>}}.
            payload: Any = handle.result(
                timeout=self._wait_timeout, poll_interval=self._poll_interval
            )

        return self._parse_result(payload)

    @staticmethod
    def _parse_result(payload: Any) -> BookRetrievalResult:
        """Unwrap the `/jobs/{id}/result` envelope into a `BookRetrievalResult`.

        The API returns ``{"job_id": ..., "result": {...}}``; older/preview
        shapes may hand back the bare result body. Accept both.
        """
        body: Optional[Any] = payload
        if isinstance(payload, dict) and "result" in payload:
            body = payload["result"]
        if body is None:
            # Succeeded but no result body — return an empty (ungrounded) result
            # rather than raising; the resolver treats empty hits as ungrounded.
            return BookRetrievalResult(hits=[])
        return BookRetrievalResult.model_validate(body)

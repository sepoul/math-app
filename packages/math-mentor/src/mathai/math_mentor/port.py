"""The retrieval PORT — the single seam onto `book_retrieve`.

`resolve_anchor` (see `anchor.py`) reads book knowledge through *exactly one*
interface: a callable that takes a `BookRetrieveInput` and returns a
`BookRetrievalResult`. That callable is the `BookRetrieveFn` port defined here.

Why a port (and not a direct call into a vector store / SQL / OCR)?

  * **One source of truth for retrieval.** The already-shipped `book_retrieve`
    job owns hybrid retrieval (lexical + vector + type/label + intent-gated
    graph expansion, optionally Claude-reranked). The resolver must not
    re-implement or side-channel around any of that — it asks the port and
    trusts the ranked hits.
  * **Testability.** Unit tests inject an in-memory fake implementing this
    Protocol; production injects `PlatformBookRetrieve` (see `adapter.py`),
    which talks to a running platform. Neither the resolver nor its tests know
    or care which is wired in.

The contract types come from `mathai.math_book.models` — the single source of
truth. We import them; we never copy or redefine them.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from mathai.math_book.models import BookRetrievalResult, BookRetrieveInput


@runtime_checkable
class BookRetrieveFn(Protocol):
    """A synchronous `book_retrieve` port: `(BookRetrieveInput) -> BookRetrievalResult`.

    Any callable with this shape is a valid retrieval source for
    `resolve_anchor` — an in-memory fake in tests, the platform-backed
    `PlatformBookRetrieve` in production. `runtime_checkable` so tests can
    `isinstance`-assert a fake satisfies the port if they want to.

    Implementations MUST be book-scoped by honouring `req.book_id` (a Tu query
    must never surface Hatcher hits) and MUST NOT mutate the request.
    """

    def __call__(self, req: BookRetrieveInput) -> BookRetrievalResult:  # noqa: D401,E704
        ...

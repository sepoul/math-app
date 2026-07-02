# math-mentor

The tutoring layer over the book-RAG corpus. **This package currently ships only
issue #68: the `GroundedAnchor` resolver** — the single seam onto the
already-shipped `book_retrieve` RAG job.

> **Deploy wiring is deferred.** This issue is the resolver *logic contract*
> only. There is intentionally **no** `bundle.toml`, `control.py`, or
> `execution.py` here yet — turning `math_mentor` into a deployable platform job
> is future work (#69/#70/#71).

## What #68 is

`resolve_anchor(retrieve, book_id, coordinate, topic, intent)` takes a request to
locate a spot in a book and returns a `GroundedAnchor` — a source-traceable
citation with an **honest trust level**:

| trust level        | meaning                                                            | `matched` |
|--------------------|--------------------------------------------------------------------|-----------|
| `grounded`         | a returned hit's label matches the requested coordinate exactly    | `True`    |
| `section-grounded` | no coordinate match, but a topical hit clears the score floor      | `True`    |
| `ungrounded`       | no usable hit (empty, or nothing above the floor)                  | `False`   |

`matched == (trust_level != "ungrounded")`.

The resolver **never fabricates** a `label`/`node_id`: those are only ever copied
from a hit the retriever returned. A coordinate with no matching label yields at
most `section-grounded` (with `label=None`, `node_id=None`) — never a confident
wrong label.

## The one seam: `book_retrieve`

The resolver's *only* source of retrieval data is a **`BookRetrieveFn` port** — a
`typing.Protocol` of `(BookRetrieveInput) -> BookRetrievalResult`. No SQL, no
OCR, no regex over book text, no vector store, no filesystem/DB access — every
byte of book knowledge flows through that one port call, made exactly once per
`resolve_anchor`.

- The contract types (`BookRetrieveInput`, `BookRetrievalResult`,
  `BookRetrievalHit`, `RetrievalIntent`) are imported from
  `mathai.math_book.models` — the single source of truth. We never redefine them.
- `PlatformBookRetrieve` is a thin production adapter implementing the port via
  `ai_platform.session.PlatformSession` (submit `book_retrieve` → wait → parse).
  It imports `ai_platform` **lazily**, so unit tests never need the platform.

## Layout

```
src/mathai/math_mentor/
  port.py      BookRetrieveFn (the retrieval Protocol / port)
  anchor.py    GroundedAnchor model + resolve_anchor + coordinate normalization
  adapter.py   PlatformBookRetrive — the concrete platform-backed port
tests/
  test_resolve_anchor.py   comprehensive AC coverage with an in-memory fake port
```

## Tests

The resolver is tested entirely against an in-memory fake port (no live
platform):

```bash
uv venv --python 3.13 /tmp/mentor-venv
uv pip install --python /tmp/mentor-venv/bin/python pydantic pytest
uv pip install --python /tmp/mentor-venv/bin/python --no-deps \
  -e /ABS/PATH/ai-platform/packages/core \
  -e packages/math-book \
  -e packages/math-mentor
/tmp/mentor-venv/bin/python -m pytest packages/math-mentor/tests -q
```

## Open seams / judgment calls (settle with #55 calibration)

- `DEFAULT_SCORE_FLOOR = 0.35` — provisional; #55 calibrates real numbers.
- `section-grounded` sets `node_id=None` (no false precision — we only trust a
  node_id when it comes with an exact coordinate-label match).
- "Topically relevant" is operationalized as *clears the score floor*: the port
  is the sole data source and it already scoped by `book_id` + the query, so any
  hit above the floor is by construction a relevant hit for this query.

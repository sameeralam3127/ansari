"""Shared pagination bounds.

Every list endpoint is paginated: an unbounded `GET` returns the whole table,
which is fine with four rows and an outage with forty thousand. The cap is
enforced by FastAPI's `Query(le=MAX_PAGE_SIZE)` so an over-large request is a
422 rather than a slow success.
"""

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200

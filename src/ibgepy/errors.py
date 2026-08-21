from __future__ import annotations


class IbgeError(Exception):
    """Base class for errors raised by ibgepy."""


class InvalidQueryError(IbgeError, ValueError):
    """The caller supplied an invalid or contradictory API query."""


class QueryTooLargeError(InvalidQueryError):
    """The query exceeds, or cannot be proven within, SIDRA's value limit."""


class HttpStatusError(IbgeError):
    """The official endpoint returned a non-success status."""

    def __init__(
        self,
        status_code: int,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(f"IBGE endpoint returned HTTP {status_code}: {url}")
        self.status_code = status_code
        self.url = url
        self.headers = dict(headers or {})
        self.retry_after = retry_after


class TransportError(IbgeError):
    """The official endpoint could not be reached."""


class ParseError(IbgeError, ValueError):
    """A recorded response could not be parsed according to its API format."""

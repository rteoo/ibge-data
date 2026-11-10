from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .transport import RawResponse


class IbgeError(Exception):
    """Base class for errors raised by ibge_data."""


class InvalidQueryError(IbgeError, ValueError):
    """The caller supplied an invalid or contradictory API query."""


class QueryTooLargeError(InvalidQueryError):
    """The query exceeds, or cannot be proven within, SIDRA's value limit."""

    def __init__(
        self,
        message: str,
        *,
        estimated_values: int | None = None,
        max_values: int | None = None,
        unknown_dimensions: tuple[str, ...] = (),
    ):
        super().__init__(message)
        self.estimated_values = estimated_values
        self.max_values = max_values
        self.unknown_dimensions = unknown_dimensions


class HttpStatusError(IbgeError):
    """The official endpoint returned a non-success status."""

    def __init__(
        self,
        status_code: int,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        retry_after: float | None = None,
        response: RawResponse | None = None,
    ):
        super().__init__(f"IBGE endpoint returned HTTP {status_code}: {url}")
        self.status_code = status_code
        self.url = url
        self.headers = dict(headers or {})
        self.retry_after = retry_after
        self.response = response


class TransportError(IbgeError):
    """The official endpoint could not be reached."""


class ParseError(IbgeError, ValueError):
    """A recorded response could not be parsed according to its API format."""

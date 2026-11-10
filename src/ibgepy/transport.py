from __future__ import annotations

import hashlib
import math
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from types import MappingProxyType
from typing import Protocol

from .errors import HttpStatusError, TransportError

PARSER_VERSION = "ibge-json-2"


@dataclass(frozen=True)
class RawResponse:
    """Immutable response artifact retained for replay and provenance."""

    url: str
    status_code: int
    headers: Mapping[str, str]
    body: bytes
    fetched_at: datetime
    request_headers: Mapping[str, str] = field(default_factory=dict)
    library_version: str = "0.1.0"
    parser_version: str = PARSER_VERSION
    retry_after: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))
        object.__setattr__(self, "request_headers", MappingProxyType(dict(self.request_headers)))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body).hexdigest()

    @property
    def byte_size(self) -> int:
        return len(self.body)

    def raise_for_status(self) -> None:
        if self.status_code < 200 or self.status_code >= 300:
            raise HttpStatusError(
                self.status_code,
                self.url,
                headers=dict(self.headers),
                retry_after=self.retry_after,
                response=self,
            )


class Transport(Protocol):
    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> RawResponse:
        """Return a response without parsing its body."""


class UrllibTransport:
    """Opt-in standard-library HTTP transport."""

    def __init__(self, *, timeout: float = 30.0):
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise ValueError("timeout must be a finite positive number")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a finite positive number")
        self.timeout = timeout

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> RawResponse:
        request_headers = dict(headers or {})
        request_headers.setdefault("User-Agent", "ibgepy/0.1")
        request = urllib.request.Request(url, headers=request_headers, method="GET")
        fetched_at = datetime.now(timezone.utc)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return RawResponse(
                    url=url,
                    status_code=response.status,
                    headers=dict(response.headers.items()),
                    body=response.read(),
                    fetched_at=fetched_at,
                    request_headers=request_headers,
                    retry_after=_retry_after(dict(response.headers.items())),
                )
        except urllib.error.HTTPError as error:
            response_headers = dict(error.headers.items())
            return RawResponse(
                url=url,
                status_code=error.code,
                headers=response_headers,
                body=error.read(),
                fetched_at=fetched_at,
                request_headers=request_headers,
                retry_after=_retry_after(response_headers),
            )
        except urllib.error.URLError as error:
            raise TransportError(f"IBGE request failed for {url}: {error.reason}") from error
        except OSError as error:
            raise TransportError(f"IBGE request failed for {url}: {error}") from error


def _retry_after(headers: Mapping[str, str]) -> float | None:
    raw = next((value for key, value in headers.items() if key.casefold() == "retry-after"), None)
    if not raw:
        return None
    try:
        seconds = float(raw)
        return max(seconds, 0.0) if math.isfinite(seconds) else None
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
        return max(when.timestamp() - datetime.now(timezone.utc).timestamp(), 0.0)
    except (TypeError, ValueError, OverflowError):
        return None

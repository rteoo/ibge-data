from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from ibgedata.transport import RawResponse


class FixtureTransport:
    def __init__(
        self, body: bytes, *, status_code: int = 200, url: str = "https://fixture.invalid"
    ):
        self.body = body
        self.status_code = status_code
        self.url = url
        self.calls: list[tuple[str, Mapping[str, str]]] = []

    def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> RawResponse:
        self.calls.append((url, headers or {}))
        return RawResponse(
            url=url,
            status_code=self.status_code,
            headers={"content-type": "application/json"},
            body=self.body,
            fetched_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
            request_headers=headers or {},
        )

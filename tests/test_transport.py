from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ibgepy import HttpStatusError, RawResponse, TransportError, UrllibTransport


def test_raw_response_hash_is_content_addressed() -> None:
    response = RawResponse(
        url="https://example.invalid",
        status_code=200,
        headers={},
        body=b"fixture",
        fetched_at=datetime(2026, 8, 21, tzinfo=timezone.utc),
    )
    assert response.sha256 == "f16d05ec6b29248d2c61adb1e9263f78e4f7bace1b955014a2d17872cfe4064d"
    assert response.byte_size == 7
    assert response.library_version == "0.1.0"
    assert response.parser_version == "ibge-json-2"
    with pytest.raises(TypeError):
        response.headers["etag"] = "changed"  # type: ignore[index]


def test_non_success_response_raises_only_when_checked() -> None:
    response = RawResponse(
        "https://example.invalid",
        503,
        {"retry-after": "5"},
        b"busy",
        datetime.now(timezone.utc),
        retry_after=5.0,
    )
    with pytest.raises(HttpStatusError) as error:
        response.raise_for_status()
    assert error.value.retry_after == 5.0


def test_transport_normalizes_timeout(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr("urllib.request.urlopen", timeout)
    with pytest.raises(TransportError, match="timed out"):
        UrllibTransport().get("https://example.invalid")

from __future__ import annotations

import gzip
import io
import json
import math
import zlib
from typing import Any

from .errors import ParseError
from .transport import RawResponse, Transport

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None

# ceiling: decode at most 128 MiB per JSON artifact; raise this only for an
# observed official response after reviewing the parser's memory budget.
MAX_JSON_BYTES = 128 * 1024 * 1024


def fetch_json(url: str, transport: Transport) -> RawResponse:
    response = transport.get(url, headers={"Accept": "application/json"})
    response.raise_for_status()
    return response


def parse_json(response: RawResponse) -> JsonValue:
    response.raise_for_status()
    try:
        return json.loads(
            _json_body(response).decode("utf-8"),
            parse_constant=_invalid_constant,
            parse_float=_finite_float,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ParseError(f"invalid JSON response from {response.url}") from error


def _json_body(response: RawResponse) -> bytes:
    encoding = next(
        (value for key, value in response.headers.items() if key.lower() == "content-encoding"),
        "identity",
    ).strip().lower()
    if encoding in {"", "identity"}:
        body = response.body
    elif encoding == "gzip":
        try:
            with gzip.GzipFile(fileobj=io.BytesIO(response.body)) as stream:
                body = stream.read(MAX_JSON_BYTES + 1)
        except (OSError, EOFError, zlib.error) as error:
            raise ParseError("invalid gzip encoding in IBGE response") from error
    else:
        raise ParseError("unsupported Content-Encoding; request identity or gzip JSON")
    if len(body) > MAX_JSON_BYTES:
        raise ParseError("decoded JSON exceeds the 128 MiB parser limit")
    return body


def _invalid_constant(value: str) -> None:
    raise ParseError("non-finite JSON number in IBGE response")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ParseError("non-finite JSON number in IBGE response")
    return number


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ParseError("duplicate JSON object key in IBGE response")
        result[key] = value
    return result


def as_records(payload: JsonValue, *, url: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        for key in ("data", "resultados", "results", "agregados", "calendario", "items"):
            candidate = payload.get(key)
            if isinstance(candidate, list):
                records = candidate
                break
        else:
            records = [payload]
    else:
        raise ParseError(f"expected JSON object or array from {url}")
    if not all(isinstance(record, dict) for record in records):
        raise ParseError(f"expected object records from {url}")
    return records

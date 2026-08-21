from __future__ import annotations

import json
from typing import Any

from .errors import ParseError
from .transport import RawResponse, Transport

JsonValue = dict[str, Any] | list[Any] | str | int | float | bool | None


def fetch_json(url: str, transport: Transport) -> RawResponse:
    response = transport.get(url, headers={"Accept": "application/json"})
    response.raise_for_status()
    return response


def parse_json(response: RawResponse) -> JsonValue:
    response.raise_for_status()
    try:
        return json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ParseError(f"invalid JSON response from {response.url}") from error


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

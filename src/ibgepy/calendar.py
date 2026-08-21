from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping
from urllib.parse import quote, urlencode

from ._json import as_records, fetch_json, parse_json
from .errors import InvalidQueryError
from .transport import RawResponse, Transport

CALENDAR_BASE = "https://servicodados.ibge.gov.br/api/v3/calendario"


@dataclass(frozen=True)
class CalendarQuery:
    research: str | None = None
    quantity: int | None = None
    start: date | None = None
    end: date | None = None

    def __post_init__(self) -> None:
        if self.research is not None and not self.research:
            raise InvalidQueryError("calendar research cannot be empty")

    def params(self) -> dict[str, str]:
        if self.quantity is not None and self.quantity <= 0:
            raise InvalidQueryError("quantity must be positive")
        if self.start and self.end and self.start > self.end:
            raise InvalidQueryError("calendar start cannot be after end")
        values: dict[str, str] = {}
        if self.quantity is not None:
            values["qtd"] = str(self.quantity)
        if self.start is not None:
            values["de"] = self.start.isoformat()
        if self.end is not None:
            values["ate"] = self.end.isoformat()
        return values


@dataclass(frozen=True)
class CalendarEntry:
    research: str | None
    reference_period: str | None
    expected_date: date | None
    published_at: date | None
    raw: Mapping[str, Any]
    fetched_at: datetime
    revision_state: str = "unknown"
    entry_id: int | None = None
    product: str | None = None
    publication_type: str | None = None


def fetch_calendar(query: CalendarQuery, transport: Transport) -> RawResponse:
    path = f"/{quote(query.research, safe='')}" if query.research else "/"
    params = urlencode(query.params())
    url = f"{CALENDAR_BASE}{path}"
    if params:
        url = f"{url}?{params}"
    return fetch_json(url, transport)


def parse_calendar(response: RawResponse) -> tuple[CalendarEntry, ...]:
    records = as_records(parse_json(response), url=response.url)
    return tuple(
        CalendarEntry(
            research=_first_string(
                record, "pesquisa", "research", "nomePesquisa", "titulo", "nome_produto"
            ),
            reference_period=_reference_period(record),
            expected_date=_first_date(record, "previsao", "dataPrevista", "expected_date"),
            published_at=_first_date(
                record, "dataDivulgacao", "dataPublicacao", "published_at", "data_divulgacao"
            ),
            raw=record,
            fetched_at=response.fetched_at,
            entry_id=_first_int(record, "id"),
            product=_first_string(record, "produto", "nome_produto", "alias_produto"),
            publication_type=_first_string(record, "tipo", "publication_type"),
        )
        for record in records
    )


def _first_string(record: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value is not None:
            return str(value)
    return None


def _first_date(record: Mapping[str, Any], *keys: str) -> date | None:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        try:
            text = str(value)
            if len(text) >= 10 and text[2] == "/" and text[5] == "/":
                return date.fromisoformat(f"{text[6:10]}-{text[3:5]}-{text[:2]}")
            return date.fromisoformat(text[:10])
        except ValueError:
            continue
    return None


def _reference_period(record: Mapping[str, Any]) -> str | None:
    explicit = _first_string(record, "periodoReferencia", "periodo", "reference_period")
    if explicit is not None:
        return explicit
    year = record.get("ano_referencia_inicio")
    month = record.get("mes_referencia_inicio")
    if year and month:
        return f"{int(year):04d}-{int(month):02d}"
    return None


def _first_int(record: Mapping[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = record.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                return None
    return None

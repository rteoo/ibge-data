from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import quote, urlencode

from ._json import as_records, fetch_json, parse_json
from .errors import InvalidQueryError, ParseError
from .transport import RawResponse, Transport

AGGREGATES_BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"


@dataclass(frozen=True)
class AggregateFilters:
    periodo: str | None = None
    assunto: str | None = None
    classificacao: str | None = None
    periodicidade: str | None = None
    nivel: str | None = None

    def as_params(self) -> dict[str, str]:
        return {
            key: value
            for key, value in {
                "periodo": self.periodo,
                "assunto": self.assunto,
                "classificacao": self.classificacao,
                "periodicidade": self.periodicidade,
                "nivel": self.nivel,
            }.items()
            if value is not None
        }


@dataclass(frozen=True)
class AggregateSummary:
    aggregate_id: int
    name: str | None
    survey: str | None
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class AggregateDocument:
    endpoint: str
    records: tuple[Mapping[str, Any], ...]
    fetched_at: Any
    sha256: str


def _url(path: str = "", params: Mapping[str, str] | None = None) -> str:
    result = f"{AGGREGATES_BASE}{path}"
    encoded = urlencode(params or {})
    return f"{result}?{encoded}" if encoded else result


def fetch_aggregates(filters: AggregateFilters, transport: Transport) -> RawResponse:
    return fetch_json(_url(params=filters.as_params()), transport)


def fetch_metadata(aggregate: int, transport: Transport) -> RawResponse:
    return fetch_json(_url(f"/{_positive_id(aggregate)}/metadados"), transport)


def fetch_periods(aggregate: int, transport: Transport) -> RawResponse:
    return fetch_json(_url(f"/{_positive_id(aggregate)}/periodos"), transport)


def fetch_localities(aggregate: int, level: str, transport: Transport) -> RawResponse:
    if not level:
        raise InvalidQueryError("locality level cannot be empty")
    return fetch_json(_url(f"/{_positive_id(aggregate)}/localidades/{quote(level, safe='')}"), transport)


def fetch_variable(
    aggregate: int,
    variable: int,
    periods: str,
    *,
    localities: str,
    transport: Transport,
    classification: str | None = None,
    view: str | None = None,
) -> RawResponse:
    if not localities:
        raise InvalidQueryError("localities cannot be empty")
    params = {"localidades": localities}
    if classification is not None:
        params["classificacao"] = classification
    if view is not None:
        params["view"] = view
    if not periods:
        raise InvalidQueryError("period selector cannot be empty")
    path = (
        f"/{_positive_id(aggregate)}/periodos/{quote(periods, safe=',.-')}/"
        f"variaveis/{_positive_id(variable)}"
    )
    return fetch_json(_url(path, params), transport)


def fetch_variable_latest(
    aggregate: int,
    variable: int,
    *,
    localities: str,
    transport: Transport,
    classification: str | None = None,
    view: str | None = None,
) -> RawResponse:
    """Fetch the documented last-six-period aggregate shorthand."""

    if not localities:
        raise InvalidQueryError("localities cannot be empty")
    params = {"localidades": localities}
    if classification is not None:
        params["classificacao"] = classification
    if view is not None:
        params["view"] = view
    path = f"/{_positive_id(aggregate)}/variaveis/{_positive_id(variable)}"
    return fetch_json(_url(path, params), transport)


def parse_aggregate_list(response: RawResponse) -> tuple[AggregateSummary, ...]:
    records = as_records(parse_json(response), url=response.url)
    summaries: list[AggregateSummary] = []
    for record in records:
        nested = record.get("agregados")
        if isinstance(nested, list):
            survey = _first_string(record, "nome", "pesquisa", "survey")
            if not all(isinstance(item, dict) for item in nested):
                raise ParseError(f"aggregate survey has malformed entries: {record!r}")
            summaries.extend(_aggregate_summary(item, survey=survey) for item in nested)
            continue
        summaries.append(
            _aggregate_summary(record, survey=_first_string(record, "pesquisa", "survey"))
        )
    return tuple(summaries)


def _aggregate_summary(record: Mapping[str, Any], *, survey: str | None) -> AggregateSummary:
    identifier = record.get("id", record.get("agregado"))
    try:
        aggregate_id = int(identifier)
    except (TypeError, ValueError) as error:
        raise ParseError(f"aggregate record has no numeric id: {record!r}") from error
    return AggregateSummary(
        aggregate_id=aggregate_id,
        name=_first_string(record, "nome", "name", "descricao"),
        survey=survey,
        raw=record,
    )


def parse_aggregate_document(response: RawResponse) -> AggregateDocument:
    records = tuple(as_records(parse_json(response), url=response.url))
    return AggregateDocument(response.url, tuple(records), response.fetched_at, response.sha256)


def _positive_id(value: int) -> int:
    if value <= 0:
        raise InvalidQueryError("aggregate and variable IDs must be positive integers")
    return value


def _first_string(record: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value is not None:
            return str(value)
    return None

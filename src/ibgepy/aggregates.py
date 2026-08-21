from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping
from urllib.parse import quote, urlencode

from ._json import as_records, fetch_json, parse_json
from .errors import InvalidQueryError, ParseError
from .sidra import SpecialValue, _decode_value
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


@dataclass(frozen=True)
class AggregateObservation:
    aggregate_id: int
    variable_id: str
    variable_name: str | None
    unit: str | None
    locality_id: str
    locality_name: str | None
    locality_level: str | None
    period_code: str
    classifications: tuple[tuple[str, str, str], ...]
    raw_value: str
    value: Decimal | None
    special_value: SpecialValue | None
    fetched_at: datetime
    revision_state: str = "unknown"


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


def parse_aggregate_observations(
    response: RawResponse,
    *,
    aggregate_id: int,
) -> tuple[AggregateObservation, ...]:
    """Parse the self-describing Aggregates v3 variable-result layout."""

    records = as_records(parse_json(response), url=response.url)
    observations: list[AggregateObservation] = []
    for variable in records:
        variable_id = _required_string(variable, "id", context="variable")
        variable_name = _first_string(variable, "variavel", "nome")
        unit = _first_string(variable, "unidade")
        results = variable.get("resultados")
        if not isinstance(results, list):
            raise ParseError("aggregate variable record has no resultados list")
        for result in results:
            if not isinstance(result, dict):
                raise ParseError("aggregate resultado must be an object")
            classifications = _classifications(result.get("classificacoes", []))
            series = result.get("series")
            if not isinstance(series, list):
                raise ParseError("aggregate resultado has no series list")
            for item in series:
                if not isinstance(item, dict):
                    raise ParseError("aggregate series must be an object")
                locality = item.get("localidade")
                values = item.get("serie")
                if not isinstance(locality, dict) or not isinstance(values, dict):
                    raise ParseError("aggregate series lacks locality or period values")
                locality_id = _required_string(locality, "id", context="locality")
                level = locality.get("nivel")
                level_id = _first_string(level, "id") if isinstance(level, dict) else None
                for period_code, raw in values.items():
                    raw_value = str(raw)
                    value, special = _decode_value(raw_value)
                    observations.append(
                        AggregateObservation(
                            aggregate_id=_positive_id(aggregate_id),
                            variable_id=variable_id,
                            variable_name=variable_name,
                            unit=unit,
                            locality_id=locality_id,
                            locality_name=_first_string(locality, "nome"),
                            locality_level=level_id,
                            period_code=str(period_code),
                            classifications=classifications,
                            raw_value=raw_value,
                            value=value,
                            special_value=special,
                            fetched_at=response.fetched_at,
                        )
                    )
    return tuple(observations)


def _classifications(value: object) -> tuple[tuple[str, str, str], ...]:
    if not isinstance(value, list):
        raise ParseError("aggregate classifications must be a list")
    output: list[tuple[str, str, str]] = []
    for classification in value:
        if not isinstance(classification, dict):
            raise ParseError("aggregate classification must be an object")
        classification_id = _required_string(classification, "id", context="classification")
        categories = classification.get("categoria")
        if not isinstance(categories, dict):
            raise ParseError("aggregate classification has no categoria object")
        for category_id, category_name in categories.items():
            output.append((classification_id, str(category_id), str(category_name)))
    return tuple(output)


def _required_string(record: Mapping[str, Any], key: str, *, context: str) -> str:
    value = record.get(key)
    if value is None or not str(value):
        raise ParseError(f"aggregate {context} has no {key}")
    return str(value)


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

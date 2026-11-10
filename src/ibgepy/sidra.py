from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Literal
from urllib.parse import quote

from ._json import as_records, fetch_json, parse_json
from .errors import InvalidQueryError, ParseError, QueryTooLargeError
from .transport import RawResponse, Transport

SIDRA_VALUES_BASE = "https://apisidra.ibge.gov.br/values"
SIDRA_DESCRIPTOR_BASE = "https://apisidra.ibge.gov.br/DescritoresTabela/t"
MAX_VALUES = 100_000


def _positive_integer(value: object, *, field: str) -> None:
    if type(value) is not int or value <= 0:
        raise InvalidQueryError(f"{field} must be a positive integer")


def _atomic_codes(values: object, *, field: str) -> None:
    if not isinstance(values, tuple) or not values:
        raise InvalidQueryError(f"{field} must be a non-empty tuple of atomic numeric codes")
    if any(not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value) for value in values):
        raise InvalidQueryError(
            f"{field} must contain non-empty atomic numeric codes; use one code per tuple member"
        )
    if len(set(values)) != len(values):
        raise InvalidQueryError(f"{field} cannot contain duplicate codes")


def _selection(values: object, known_count: object, *, field: str, wildcards: set[str]) -> None:
    if isinstance(values, str):
        if values not in wildcards:
            raise InvalidQueryError(f"unsupported {field} selector")
    else:
        _atomic_codes(values, field=field)
    if known_count is not None:
        _positive_integer(known_count, field="known_count")
        if isinstance(values, tuple) and known_count != len(values):
            raise InvalidQueryError("known_count must match the number of explicit codes")


@dataclass(frozen=True)
class VariableSelection:
    values: tuple[str, ...] | Literal["all", "allxp"]
    known_count: int | None = None

    def __post_init__(self) -> None:
        _selection(self.values, self.known_count, field="variables", wildcards={"all", "allxp"})

    @property
    def count(self) -> int | None:
        return len(self.values) if isinstance(self.values, tuple) else self.known_count

    def token(self) -> str:
        return ",".join(self.values) if isinstance(self.values, tuple) else self.values


@dataclass(frozen=True)
class GeographySelection:
    level: str
    values: tuple[str, ...] | Literal["all"]
    known_count: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.level, str) or self.level not in {"n1", "n2", "n3", "n6"}:
            raise InvalidQueryError("geography level must be one of n1, n2, n3, or n6")
        _selection(self.values, self.known_count, field="geography", wildcards={"all"})

    @property
    def count(self) -> int | None:
        return len(self.values) if isinstance(self.values, tuple) else self.known_count

    def token(self) -> str:
        return ",".join(self.values) if isinstance(self.values, tuple) else self.values


@dataclass(frozen=True)
class ClassificationSelection:
    code: str
    categories: tuple[str, ...] | Literal["all", "allxt"]
    known_count: int | None = None

    def __post_init__(self) -> None:
        _atomic_codes((self.code,), field="classification code")
        _selection(
            self.categories, self.known_count, field="categories", wildcards={"all", "allxt"}
        )

    @property
    def count(self) -> int | None:
        return len(self.categories) if isinstance(self.categories, tuple) else self.known_count

    def token(self) -> str:
        return ",".join(self.categories) if isinstance(self.categories, tuple) else self.categories


@dataclass(frozen=True)
class OutputOptions:
    header: bool = True
    fields: Literal["a", "c", "n", "u"] = "a"
    decimals: Literal["s", "m"] | int = "m"

    def __post_init__(self) -> None:
        if type(self.header) is not bool:
            raise InvalidQueryError("header must be a boolean")
        if not isinstance(self.fields, str) or self.fields not in {"a", "c", "n", "u"}:
            raise InvalidQueryError("fields must be one of a, c, n, or u")
        if type(self.decimals) is int and 0 <= self.decimals <= 9:
            return
        if not isinstance(self.decimals, str) or self.decimals not in {"s", "m"}:
            raise InvalidQueryError("decimals must be s, m, or an integer from 0 to 9")


@dataclass(frozen=True)
class SidraQuery:
    table: int
    periods: tuple[str, ...] | str
    variables: VariableSelection
    geography: GeographySelection
    classifications: tuple[ClassificationSelection, ...] = ()
    output: OutputOptions = field(default_factory=OutputOptions)
    include_extinct_territories: bool = False

    def __post_init__(self) -> None:
        _positive_integer(self.table, field="table")
        if isinstance(self.periods, str):
            if self.periods != "all" and not re.fullmatch(r"[0-9]+|last [1-9][0-9]*", self.periods):
                raise InvalidQueryError("periods must be atomic codes, a single code, or 'last N'")
        else:
            _atomic_codes(self.periods, field="periods")
        if not isinstance(self.variables, VariableSelection):
            raise InvalidQueryError("variables must be a VariableSelection")
        if not isinstance(self.geography, GeographySelection):
            raise InvalidQueryError("geography must be a GeographySelection")
        if not isinstance(self.output, OutputOptions):
            raise InvalidQueryError("output must be OutputOptions")
        if type(self.include_extinct_territories) is not bool:
            raise InvalidQueryError("include_extinct_territories must be a boolean")
        if not isinstance(self.classifications, tuple) or any(
            not isinstance(item, ClassificationSelection) for item in self.classifications
        ):
            raise InvalidQueryError("classifications must be a tuple of ClassificationSelection")
        if len(self.classifications) > 6:
            raise InvalidQueryError("SIDRA permits at most six classifications")
        if len({item.code for item in self.classifications}) != len(self.classifications):
            raise InvalidQueryError("classification codes cannot be repeated")

    @property
    def period_count(self) -> int | None:
        if isinstance(self.periods, tuple):
            return len(self.periods)
        if re.fullmatch(r"[0-9]+", self.periods):
            return 1
        match = re.fullmatch(r"last ([1-9][0-9]*)", self.periods)
        if match:
            return int(match.group(1))
        return None

    @property
    def estimated_values(self) -> int | None:
        counts = [self.period_count, self.variables.count, self.geography.count]
        counts.extend(item.count for item in self.classifications)
        if any(count is None for count in counts):
            return None
        result = 1
        for count in counts:
            result *= count or 0
        return result

    @property
    def dimension_order(self) -> tuple[str, ...]:
        return (
            "geography",
            "variable",
            "period",
            *(f"classification:{item.code}" for item in self.classifications),
        )

    def validate_bound(self, *, max_values: int = MAX_VALUES) -> None:
        if type(max_values) is not int or not 0 < max_values <= MAX_VALUES:
            raise InvalidQueryError(f"max_values must be between 1 and {MAX_VALUES}")
        estimate = self.estimated_values
        if estimate is None:
            counts = (self.geography.count, self.variables.count, self.period_count)
            counts += tuple(item.count for item in self.classifications)
            unknown = tuple(
                role for role, count in zip(self.dimension_order, counts) if count is None
            )
            raise QueryTooLargeError(
                "query cardinality is unknown; supply explicit selectors or known_count metadata",
                max_values=max_values,
                unknown_dimensions=unknown,
            )
        if estimate is not None and estimate > max_values:
            raise QueryTooLargeError(
                f"query estimates {estimate} values; limit is {max_values}",
                estimated_values=estimate,
                max_values=max_values,
            )


class SpecialValue(str, Enum):
    ABSOLUTE_ZERO = "-"
    CALCULATED_ZERO = "0"
    SUPPRESSED = "X"
    NOT_APPLICABLE = ".."
    UNAVAILABLE = "..."
    RANGE = "range"


@dataclass(frozen=True)
class DimensionValue:
    position: int
    code: str | None
    name: str | None
    role: str | None


@dataclass(frozen=True)
class SidraObservation:
    table: int
    variable_code: str | None
    period_code: str | None
    dimensions: tuple[DimensionValue, ...]
    unit_code: str | None
    unit_name: str | None
    raw_value: str
    value: Decimal | None
    special_value: SpecialValue | None
    fetched_at: datetime | None = None
    published_at: date | None = None
    revision_state: Literal["unknown", "declared"] = "unknown"


def _escaped(value: str) -> str:
    return quote(value, safe=",.-_")


def build_values_url(query: SidraQuery, *, base_url: str = SIDRA_VALUES_BASE) -> str:
    query.validate_bound()
    segments = [
        base_url.rstrip("/"),
        "t",
        str(query.table),
        query.geography.level,
        _escaped(query.geography.token()),
        "v",
        _escaped(query.variables.token()),
        "p",
        _escaped(_period_token(query.periods)),
    ]
    for classification in query.classifications:
        segments.extend((f"c{classification.code}", _escaped(classification.token())))
    segments.extend(
        (
            "h",
            "y" if query.output.header else "n",
            "f",
            query.output.fields,
            "d",
            str(query.output.decimals),
        )
    )
    if query.include_extinct_territories:
        segments.extend(("u", "y"))
    return "/".join(segments)


def _period_token(periods: tuple[str, ...] | str) -> str:
    if isinstance(periods, tuple):
        return ",".join(periods)
    if not periods:
        raise InvalidQueryError("period selector cannot be empty")
    return periods


def fetch_values(query: SidraQuery, transport: Transport) -> RawResponse:
    return fetch_json(build_values_url(query), transport)


def fetch_descriptor(table: int, transport: Transport) -> RawResponse:
    _positive_integer(table, field="table")
    return fetch_json(f"{SIDRA_DESCRIPTOR_BASE}/{table}", transport)


def _decode_value(raw: str) -> tuple[Decimal | None, SpecialValue | None]:
    if not isinstance(raw, str):
        raise ParseError("IBGE observation values must be strings; preserve the original token")
    special = {
        "-": SpecialValue.ABSOLUTE_ZERO,
        "0": SpecialValue.CALCULATED_ZERO,
        "X": SpecialValue.SUPPRESSED,
        "..": SpecialValue.NOT_APPLICABLE,
        "...": SpecialValue.UNAVAILABLE,
    }.get(raw)
    if special is not None:
        return (Decimal("0") if raw in {"-", "0"} else None), special
    if re.fullmatch(r"[+-]?[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", raw):
        try:
            number = Decimal(raw)
        except InvalidOperation as error:
            raise ParseError("SIDRA numeric token is outside Decimal's supported range") from error
        if number.is_finite():
            return number, None
    if re.fullmatch(r"[A-Z]", raw):
        return None, SpecialValue.RANGE
    raise ParseError("unknown SIDRA value token; inspect the retained raw response")


def parse_values(response: RawResponse, query: SidraQuery) -> tuple[SidraObservation, ...]:
    payload = parse_json(response)
    if not isinstance(payload, list):
        raise ParseError("SIDRA Values response must be a JSON array")
    records = as_records(payload, url=response.url)
    observations: list[SidraObservation] = []
    estimate = query.estimated_values
    seen: set[tuple[str | None, ...]] = set()
    selections = (query.geography.values, query.variables.values, query.periods)
    selections += tuple(item.categories for item in query.classifications)
    memberships = tuple(
        frozenset(selection) if isinstance(selection, tuple) else selection
        for selection in selections
    )
    for index, record in enumerate(records):
        if "V" not in record:
            raise ParseError(f"SIDRA record {index} is missing V")
        if _is_header_record(record):
            if index != 0:
                raise ParseError("SIDRA header must occur only at the start of a response")
            _validate_dimensions(record, query, memberships, header=True)
            continue
        if index == 0 and query.output.header:
            raise ParseError("SIDRA response is missing the requested header")
        if estimate is not None and len(observations) >= estimate:
            raise ParseError(
                "SIDRA response exceeds the asserted query bound; verify count metadata"
            )
        _validate_dimensions(record, query, memberships)
        raw_value = record["V"]
        value, special = _decode_value(raw_value)
        dimensions: list[DimensionValue] = []
        for position, role in enumerate(query.dimension_order, start=1):
            code = _optional_string(record.get(f"D{position}C"))
            name = _optional_string(record.get(f"D{position}N"))
            dimensions.append(DimensionValue(position, code, name, role))
        dimension_key = tuple(dimension.code for dimension in dimensions)
        if all(code is not None for code in dimension_key):
            if dimension_key in seen:
                raise ParseError("SIDRA response contains duplicate dimension codes")
            seen.add(dimension_key)
        period_index = query.dimension_order.index("period") + 1
        variable_index = query.dimension_order.index("variable") + 1
        observations.append(
            SidraObservation(
                table=query.table,
                variable_code=_optional_string(record.get(f"D{variable_index}C")),
                period_code=_optional_string(record.get(f"D{period_index}C")),
                dimensions=tuple(dimensions),
                unit_code=_optional_string(record.get("MC")),
                unit_name=_optional_string(record.get("MN")),
                raw_value=raw_value,
                value=value,
                special_value=special,
                fetched_at=response.fetched_at,
            )
        )
    return tuple(observations)


def _validate_dimensions(
    record: Mapping[str, Any],
    query: SidraQuery,
    selections: tuple[frozenset[str] | str, ...],
    *,
    header: bool = False,
) -> None:
    expected = len(query.dimension_order)
    allowed_keys = {
        f"D{position}{field_name}"
        for position in range(1, expected + 1)
        for field_name in "CN"
    }
    actual_keys = {key for key in record if re.fullmatch(r"D[0-9]+[CN]", key)}
    if not actual_keys.issubset(allowed_keys):
        raise ParseError(
            "SIDRA dimensions do not match the query; select classifications explicitly"
        )
    for position, selection in enumerate(selections, start=1):
        fields = {
            "a": "CN", "c": "C", "n": "N", "u": "CN" if position == 1 else "N"
        }[query.output.fields]
        for field_name in fields:
            value = record.get(f"D{position}{field_name}")
            if not isinstance(value, str) or not value:
                raise ParseError(
                    f"SIDRA dimension D{position}{field_name} must be a non-empty string"
                )
        code = record.get(f"D{position}C")
        if not header and code is not None:
            if not isinstance(code, str) or not re.fullmatch(r"[0-9]+", code):
                raise ParseError(f"SIDRA dimension D{position}C must be a numeric code")
            if isinstance(selection, frozenset) and code not in selection:
                raise ParseError(f"SIDRA dimension D{position}C is outside the explicit selection")
            if position == 3 and isinstance(selection, str) and re.fullmatch(r"[0-9]+", selection):
                if code != selection:
                    raise ParseError("SIDRA period is outside the explicit selection")
    if header:
        geography_name = {
            "n1": "Brasil", "n2": "Grande Região", "n3": "Unidade da Federação", "n6": "Município"
        }[query.geography.level]
        geography_label = record.get("D1N", record.get("D1C"))
        if geography_label not in {geography_name, f"{geography_name} (Código)"}:
            raise ParseError("SIDRA geography dimension is not in the expected position")
        label = record.get("D2N", record.get("D2C"))
        if label not in {"Variável", "Variável (Código)"}:
            raise ParseError("SIDRA variable dimension is not in the expected position")


def _is_header_record(record: Mapping[str, Any]) -> bool:
    """SIDRA emits a labels row when `h/y` is requested."""

    return record.get("V") == "Valor"


def _optional_string(value: Any) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ParseError("SIDRA fields must be strings or null; coercion would lose source meaning")
    return value

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Literal, Mapping
from urllib.parse import quote

from ._json import as_records, fetch_json, parse_json
from .errors import InvalidQueryError, ParseError, QueryTooLargeError
from .transport import RawResponse, Transport

SIDRA_VALUES_BASE = "https://apisidra.ibge.gov.br/values"
SIDRA_DESCRIPTOR_BASE = "https://apisidra.ibge.gov.br/DescritoresTabela/t"
MAX_VALUES = 100_000


@dataclass(frozen=True)
class VariableSelection:
    values: tuple[str, ...] | Literal["all", "allxp"]
    known_count: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.values, tuple) and not self.values:
            raise InvalidQueryError("variables cannot be empty")
        if isinstance(self.values, tuple) and any(not value for value in self.values):
            raise InvalidQueryError("variable values cannot contain empty members")
        if isinstance(self.values, str) and self.values not in {"all", "allxp"}:
            raise InvalidQueryError("unsupported variable selector")
        if self.known_count is not None and self.known_count <= 0:
            raise InvalidQueryError("known_count must be positive")

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
        if self.level not in {"n1", "n2", "n3", "n6"}:
            raise InvalidQueryError("geography level must be one of n1, n2, n3, or n6")
        if isinstance(self.values, tuple) and not self.values:
            raise InvalidQueryError("geography values cannot be empty")
        if isinstance(self.values, tuple) and any(not value for value in self.values):
            raise InvalidQueryError("geography values cannot contain empty members")
        if isinstance(self.values, str) and self.values != "all":
            raise InvalidQueryError("unsupported geography selector")
        if self.known_count is not None and self.known_count <= 0:
            raise InvalidQueryError("known_count must be positive")

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
        if not self.code:
            raise InvalidQueryError("classification code cannot be empty")
        if isinstance(self.categories, tuple) and not self.categories:
            raise InvalidQueryError("classification categories cannot be empty")
        if isinstance(self.categories, tuple) and any(not value for value in self.categories):
            raise InvalidQueryError("classification categories cannot contain empty members")
        if isinstance(self.categories, str) and self.categories not in {"all", "allxt"}:
            raise InvalidQueryError("unsupported classification selector")
        if self.known_count is not None and self.known_count <= 0:
            raise InvalidQueryError("known_count must be positive")

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
        if self.fields not in {"a", "c", "n", "u"}:
            raise InvalidQueryError("fields must be one of a, c, n, or u")
        if isinstance(self.decimals, int) and not 0 <= self.decimals <= 9:
            raise InvalidQueryError("decimals must be between 0 and 9")
        if not isinstance(self.decimals, int) and self.decimals not in {"s", "m"}:
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
        if self.table <= 0:
            raise InvalidQueryError("table must be a positive integer")
        if isinstance(self.periods, tuple) and not self.periods:
            raise InvalidQueryError("periods cannot be empty")
        if isinstance(self.periods, tuple) and any(not period for period in self.periods):
            raise InvalidQueryError("periods cannot contain empty members")
        if isinstance(self.periods, str) and not self.periods:
            raise InvalidQueryError("period selector cannot be empty")
        if len(self.classifications) > 6:
            raise InvalidQueryError("SIDRA permits at most six classifications")
        if any(not item.code for item in self.classifications):
            raise InvalidQueryError("classification codes cannot be empty")

    @property
    def period_count(self) -> int | None:
        if isinstance(self.periods, tuple):
            return len(self.periods)
        if re.fullmatch(r"\d+", self.periods):
            return 1
        match = re.fullmatch(r"last\s+(\d+)", self.periods, flags=re.IGNORECASE)
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
        if max_values <= 0 or max_values > MAX_VALUES:
            raise InvalidQueryError(f"max_values must be between 1 and {MAX_VALUES}")
        estimate = self.estimated_values
        if estimate is None:
            raise QueryTooLargeError(
                "query cardinality is unknown; supply explicit selectors or known_count metadata"
            )
        if estimate is not None and estimate > max_values:
            raise QueryTooLargeError(f"query estimates {estimate} values; limit is {max_values}")


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
    if table <= 0:
        raise InvalidQueryError("table must be a positive integer")
    return fetch_json(f"{SIDRA_DESCRIPTOR_BASE}/{table}", transport)


def _decode_value(raw: str) -> tuple[Decimal | None, SpecialValue | None]:
    special = {
        "-": SpecialValue.ABSOLUTE_ZERO,
        "0": SpecialValue.CALCULATED_ZERO,
        "X": SpecialValue.SUPPRESSED,
        "..": SpecialValue.NOT_APPLICABLE,
        "...": SpecialValue.UNAVAILABLE,
    }.get(raw)
    if special is not None:
        return (Decimal("0") if raw in {"-", "0"} else None), special
    try:
        return Decimal(raw), None
    except InvalidOperation:
        pass
    if len(raw) == 1 and raw.isalpha() and raw.isupper():
        return None, SpecialValue.RANGE
    raise ParseError(f"unknown SIDRA value token: {raw!r}")


def parse_values(response: RawResponse, query: SidraQuery) -> tuple[SidraObservation, ...]:
    payload = parse_json(response)
    records = as_records(payload, url=response.url)
    observations: list[SidraObservation] = []
    for record in records:
        if "V" not in record:
            continue
        if _is_header_record(record):
            continue
        raw_value = str(record["V"])
        value, special = _decode_value(raw_value)
        dimensions: list[DimensionValue] = []
        for position, role in enumerate(query.dimension_order, start=1):
            code = _optional_string(record.get(f"D{position}C"))
            name = _optional_string(record.get(f"D{position}N"))
            dimensions.append(DimensionValue(position, code, name, role))
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


def _is_header_record(record: Mapping[str, Any]) -> bool:
    """SIDRA emits a labels row when `h/y` is requested."""

    return record.get("V") == "Valor"


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)

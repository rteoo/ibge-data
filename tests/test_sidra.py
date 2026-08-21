from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from ibgepy import (
    GeographySelection,
    InvalidQueryError,
    OutputOptions,
    QueryTooLargeError,
    SidraQuery,
    SpecialValue,
    VariableSelection,
    build_values_url,
    fetch_values,
    parse_values,
)
from conftest import FixtureTransport

FIXTURES = Path(__file__).parent / "fixtures"


def query(**kwargs) -> SidraQuery:
    values = {
        "table": 1737,
        "periods": ("202401",),
        "variables": VariableSelection(("2265",)),
        "geography": GeographySelection("n1", ("1",)),
    }
    values.update(kwargs)
    return SidraQuery(**values)


def test_builds_canonical_values_url() -> None:
    built = build_values_url(query())
    assert built == (
        "https://apisidra.ibge.gov.br/values/t/1737/n1/1/v/2265/p/202401/"
        "h/y/f/a/d/m"
    )


def test_rejects_known_over_limit() -> None:
    with pytest.raises(QueryTooLargeError, match="100000"):
        build_values_url(
            query(
                periods=tuple(str(year) for year in range(2000, 2051)),
                variables=VariableSelection(tuple(str(value) for value in range(2000))),
                geography=GeographySelection("n1", tuple(str(value) for value in range(2))),
            )
        )


def test_rejects_unknown_cardinality() -> None:
    with pytest.raises(QueryTooLargeError, match="unknown"):
        build_values_url(
            query(
                periods="last 12",
                variables=VariableSelection("all"),
                geography=GeographySelection("n2", "all"),
            )
        )


def test_counts_single_and_last_n_period_selectors() -> None:
    assert query(periods="202401").estimated_values == 1
    assert query(periods="last 12").estimated_values == 12


def test_rejects_empty_members_and_invalid_output_options() -> None:
    with pytest.raises(InvalidQueryError, match="empty"):
        VariableSelection(("",))
    with pytest.raises(InvalidQueryError, match="fields"):
        OutputOptions(fields="bad")  # type: ignore[arg-type]


def test_names_only_header_and_all_special_tokens() -> None:
    records = [
        {"V": "Valor", "D1N": "Brasil", "D2N": "Variável", "D3N": "Mês"},
        {"V": "..", "D1C": "1", "D2C": "2265", "D3C": "202401"},
        {"V": "...", "D1C": "1", "D2C": "2265", "D3C": "202402"},
        {"V": "A", "D1C": "1", "D2C": "2265", "D3C": "202403"},
    ]
    q = query(periods=("202401", "202402", "202403"), output=OutputOptions(fields="n"))
    transport = FixtureTransport(json.dumps(records).encode())
    observations = parse_values(fetch_values(q, transport), q)
    assert [item.special_value for item in observations] == [
        SpecialValue.NOT_APPLICABLE,
        SpecialValue.UNAVAILABLE,
        SpecialValue.RANGE,
    ]


def test_parses_numeric_and_special_values() -> None:
    response = FixtureTransport((FIXTURES / "sidra_values.json").read_bytes())
    q = query(
        periods=("202401", "202402", "202403", "202404"),
        geography=GeographySelection("n1", ("1",)),
    )
    observations = parse_values(fetch_values(q, response), q)
    assert observations[0].value == Decimal("6543.2100")
    assert observations[0].period_code == "202401"
    assert observations[1].value is None
    assert observations[1].special_value is SpecialValue.SUPPRESSED
    assert observations[2].raw_value == "-"
    assert observations[2].special_value is SpecialValue.ABSOLUTE_ZERO
    assert observations[3].value == Decimal("0")
    assert observations[3].special_value is SpecialValue.CALCULATED_ZERO


def test_fetch_is_injectable_and_sends_json_accept_header() -> None:
    transport = FixtureTransport(b"[]")
    q = query()
    fetch_values(q, transport)
    assert transport.calls[0][1]["Accept"] == "application/json"

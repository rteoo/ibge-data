from __future__ import annotations

from pathlib import Path

from ibgedata import (
    AggregateFilters,
    fetch_aggregates,
    fetch_localities,
    fetch_metadata,
    fetch_periods,
    fetch_variable,
    fetch_variable_latest,
    parse_aggregate_observations,
    parse_aggregate_list,
)
from conftest import FixtureTransport


def test_aggregate_list_is_typed_and_retains_raw_record() -> None:
    fixture = Path(__file__).parent / "fixtures" / "aggregates.json"
    transport = FixtureTransport(fixture.read_bytes())
    response = fetch_aggregates(AggregateFilters(periodicidade="mensal"), transport)
    summaries = parse_aggregate_list(response)
    assert summaries[0].aggregate_id == 1737
    assert summaries[0].survey == "Índice Nacional de Preços ao Consumidor Amplo"
    assert "nome" in summaries[0].raw
    assert "periodicidade=mensal" in transport.calls[0][0]


def test_all_aggregate_endpoints_build_official_paths() -> None:
    transport = FixtureTransport(b"[]")
    fetch_metadata(7060, transport)
    fetch_periods(7060, transport)
    fetch_localities(7060, "N1/test", transport)
    fetch_variable(7060, 63, "202607", localities="N1[all]", transport=transport)
    fetch_variable_latest(7060, 63, localities="N1[all]", transport=transport)
    urls = [call[0] for call in transport.calls]
    assert urls[0].endswith("/7060/metadados")
    assert urls[1].endswith("/7060/periodos")
    assert urls[2].endswith("/7060/localidades/N1%2Ftest")
    assert "/7060/periodos/202607/variaveis/63?" in urls[3]
    assert "/7060/variaveis/63?" in urls[4]


def test_parses_self_describing_aggregate_observations() -> None:
    fixture = Path(__file__).parent / "fixtures" / "aggregate_values.json"
    transport = FixtureTransport(fixture.read_bytes())
    response = fetch_variable(7060, 63, "202606,202607", localities="N1[all]", transport=transport)
    observations = parse_aggregate_observations(response, aggregate_id=7060)
    assert observations[0].variable_id == "63"
    assert observations[0].period_code == "202606"
    assert str(observations[0].value) == "0.16"
    assert observations[0].classifications == (("315", "7169", "Índice geral"),)
    assert observations[1].value is None
    assert observations[1].special_value.value == "..."

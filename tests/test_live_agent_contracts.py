from __future__ import annotations

import pytest

from ibge_data import (
    ClassificationSelection,
    GeographySelection,
    OutputOptions,
    SidraQuery,
    UrllibTransport,
    VariableSelection,
    fetch_metadata,
    fetch_values,
    fetch_variable,
    parse_aggregate_document,
    parse_aggregate_observations,
    parse_values,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("fields", ["a", "c", "n", "u"])
def test_live_single_value_field_modes(fields) -> None:
    query = SidraQuery(
        table=1737,
        periods=("202401",),
        variables=VariableSelection(("2265",)),
        geography=GeographySelection("n1", ("1",)),
        output=OutputOptions(fields=fields),
    )
    raw = fetch_values(query, UrllibTransport(timeout=10))
    observation, = parse_values(raw, query)
    assert observation.value is not None
    assert observation.variable_code == ("2265" if fields in {"a", "c"} else None)


def test_live_single_aggregate_value() -> None:
    raw = fetch_variable(
        7060, 63, "202401", localities="N1[1]", classification="315[7169]",
        transport=UrllibTransport(timeout=10),
    )
    observation, = parse_aggregate_observations(raw, aggregate_id=7060)
    assert observation.variable_id == "63"
    assert observation.locality_id == "1"
    assert observation.period_code == "202401"
    assert observation.classifications[0][:2] == ("315", "7169")
    assert observation.value is not None


def test_live_metadata_decodes_the_official_response_encoding() -> None:
    raw = fetch_metadata(9514, UrllibTransport(timeout=10))
    document = parse_aggregate_document(raw)
    assert document.records[0]["id"] == 9514
    assert document.records[0]["classificacoes"]
    assert raw.body and raw.sha256 == document.sha256


@pytest.mark.parametrize("level,code", [
    ("n1", "1"), ("n2", "1"), ("n3", "11"), ("n6", "1100015"),
])
def test_live_geography_and_classification_order(level, code) -> None:
    query = SidraQuery(
        table=9514,
        periods=("2022",),
        variables=VariableSelection(("93",)),
        geography=GeographySelection(level, (code,)),
        classifications=(
            ClassificationSelection("286", ("113635",)),
            ClassificationSelection("287", ("100362",)),
            ClassificationSelection("2", ("6794",)),
        ),
    )
    raw = fetch_values(query, UrllibTransport(timeout=10))
    observation, = parse_values(raw, query)
    assert query.estimated_values == 1
    assert observation.dimensions[0].code == code
    assert observation.period_code == "2022"
    assert [(dimension.role, dimension.code) for dimension in observation.dimensions[3:]] == [
        ("classification:286", "113635"),
        ("classification:287", "100362"),
        ("classification:2", "6794"),
    ]

from __future__ import annotations

import pytest

from ibge_data import (
    GeographySelection,
    SidraQuery,
    UrllibTransport,
    VariableSelection,
    fetch_values,
    parse_values,
)


@pytest.mark.integration
def test_live_sidra_values() -> None:
    query = SidraQuery(
        table=1737,
        periods=("202401",),
        variables=VariableSelection(("2265",)),
        geography=GeographySelection("n1", ("1",)),
    )
    raw = fetch_values(query, UrllibTransport(timeout=30.0))
    observations = parse_values(raw, query)

    assert raw.status_code == 200
    assert raw.byte_size > 0
    assert len(observations) == 1
    assert observations[0].table == 1737
    assert observations[0].variable_code == "2265"
    assert observations[0].period_code == "202401"
    assert observations[0].value is not None

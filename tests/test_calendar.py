from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from ibgepy import CalendarQuery, InvalidQueryError, fetch_calendar, parse_calendar
from conftest import FixtureTransport


def test_calendar_separates_reference_period_and_release_date() -> None:
    fixture = Path(__file__).parent / "fixtures" / "calendar.json"
    transport = FixtureTransport(fixture.read_bytes())
    response = fetch_calendar(
        CalendarQuery(research="indice-nacional-de-precos-ao-consumidor-amplo"),
        transport,
    )
    entry = parse_calendar(response)[0]
    assert entry.reference_period == "2026-07"
    assert entry.published_at == date(2026, 8, 11)
    assert entry.entry_id == 4282
    assert entry.publication_type == "Divulgação de Indicadores"
    assert entry.revision_state == "unknown"
    assert transport.calls[0][0].endswith(
        "/calendario/indice-nacional-de-precos-ao-consumidor-amplo"
    )


def test_calendar_validates_and_escapes_selectors() -> None:
    with pytest.raises(InvalidQueryError, match="empty"):
        CalendarQuery(research="")
    with pytest.raises(InvalidQueryError, match="after"):
        CalendarQuery(start=date(2026, 9, 1), end=date(2026, 8, 1)).params()
    transport = FixtureTransport(b'{"items":[]}')
    fetch_calendar(CalendarQuery(research="a/b"), transport)
    assert transport.calls[0][0].endswith("/calendario/a%2Fb")

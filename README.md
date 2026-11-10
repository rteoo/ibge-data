# ibge-data

<p align="center">
  <img src="https://raw.githubusercontent.com/rteoo/ibge-data/main/docs/ibge-data-icon.svg" width="128" alt="ibge-data statistical columns icon">
</p>

<p align="center">
  A typed Python client for IBGE's SIDRA Values, Aggregates, and Calendar APIs,
  with raw data provenance and no runtime dependencies.
</p>

<p align="center">
  <a href="https://github.com/rteoo/ibge-data/actions/workflows/tests.yml"><img src="https://github.com/rteoo/ibge-data/actions/workflows/tests.yml/badge.svg" alt="Test status"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10 or newer"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
</p>

Fetch Brazilian statistical observations, aggregate metadata, and publication
calendar entries from the [Instituto Brasileiro de Geografia e Estatística](https://www.ibge.gov.br/).
Keep acquired bytes separate from parsing so responses can be recorded and
replayed offline. This is an independent client, not an official IBGE product.

## Highlights

- Typed queries and observations for SIDRA Values, Aggregates v3, and Calendar v3.
- **No runtime dependencies**: HTTP uses the Python standard library.
- Injectable transports and deterministic parsing for offline tests and replay.
- Raw response artifacts with URL, status, headers, bytes, fetch time, and SHA-256.
- SIDRA query bounds checked before acquisition, including unknown cardinalities.
- Original special-value tokens retained alongside numeric values and classifications.

## Installation

Install the `ibge-data` distribution; use `ibge_data` in Python imports.
The first PyPI release is being prepared. After publication:

```bash
pip install ibge-data
```

Until then, install from source:

```bash
git clone https://github.com/rteoo/ibge-data.git
cd ibge-data
pip install .
```

### Requirements

- Python 3.10+
- No third-party runtime dependencies

## Quick Start

```python
from ibge_data import (
    GeographySelection,
    SidraQuery,
    UrllibTransport,
    VariableSelection,
    fetch_values,
    parse_values,
)

# One variable, one reference month, and Brazil as the geography
query = SidraQuery(
    table=1737,
    periods=("202401",),
    variables=VariableSelection(("2265",)),
    geography=GeographySelection(level="n1", values=("1",)),
)
raw = fetch_values(query, UrllibTransport())
observations = parse_values(raw, query)
print(raw.sha256, raw.url)
for observation in observations:
    print(observation.period_code, observation.value, observation.special_value)
```

## API Reference

### SIDRA Values

| Function or type | Purpose |
|---|---|
| `SidraQuery` | Select a table, periods, variables, geography, classifications, and output options |
| `build_values_url(query)` | Validate the query bound and build its URL without network access |
| `fetch_values(query, transport)` | Acquire the response as a `RawResponse` |
| `parse_values(response, query)` | Parse recorded bytes into a tuple of `SidraObservation` records |
| `fetch_descriptor(table, transport)` | Acquire the table descriptor |

`VariableSelection`, `GeographySelection`, `ClassificationSelection`, and
`OutputOptions` describe the supported query dimensions. Observations retain
dimensions, units, reference periods, raw tokens, `Decimal` values, and
`SpecialValue` classifications rather than silently treating every token as missing.

### Aggregates v3

Use `fetch_aggregates(AggregateFilters(), transport)` and `parse_aggregate_list`
to discover aggregates. `fetch_metadata`, `fetch_periods`, and `fetch_localities`
retrieve their descriptors. `parse_aggregate_document` retains these documents
with provenance.

```python
from ibge_data import UrllibTransport, fetch_variable, parse_aggregate_observations

raw = fetch_variable(
    1737,
    2265,
    "202401",
    localities="N1[all]",
    transport=UrllibTransport(),
)
observations = parse_aggregate_observations(raw, aggregate_id=1737)
print(observations[0].raw_value)
```

`fetch_variable_latest` uses the API's last-six-period shorthand. The SIDRA
Values query-bound checks apply to `SidraQuery`, not to Aggregates requests;
keep aggregate selections deliberately bounded.

### Calendar v3

```python
from ibge_data import CalendarQuery, UrllibTransport, fetch_calendar, parse_calendar

raw = fetch_calendar(
    CalendarQuery(research="indice-nacional-de-precos-ao-consumidor-amplo", quantity=5),
    UrllibTransport(),
)
for entry in parse_calendar(raw):
    print(entry.reference_period, entry.expected_date, entry.published_at)
```

Research selectors use the official product alias, as above, rather than a
display abbreviation such as `IPCA`.

### Exceptions

| Exception | When |
|---|---|
| `IbgeError` | Base class for library errors |
| `InvalidQueryError` | An invalid or unsupported query |
| `QueryTooLargeError` | SIDRA query exceeds its limit or its bound cannot be proven |
| `HttpStatusError` | A non-success HTTP status; includes status, URL, headers, and optional `retry_after` |
| `TransportError` | A network request fails |
| `ParseError` | Response bytes do not match the expected format |

## API Limits

- **SIDRA Values:** at most 100,000 values. Explicit selections are counted before
  acquisition. Broad selectors such as `all` require `known_count` metadata;
  queries with an unknown bound are rejected.
- **Geography:** version 0.1.0 supports one SIDRA `N` selector: `n1`, `n2`, `n3`,
  or `n6`. The broader `G` views and multiple simultaneous `N` selectors are
  unsupported and must not be approximated.
- **HTTP:** `UrllibTransport(timeout=30.0)` uses a finite timeout. The client
  exposes failures and `Retry-After` metadata without automatically retrying.
- **Release metadata:** reference periods are not row-level release timestamps.
  `published_at` is optional and revision state defaults to `unknown`.

## Safety and Provenance

For agent workflows, start with the [agent guide](docs/agent-guide.md): it covers
preflight bounds, structured failures, raw evidence, parsing limits, and retry budgets.

Every acquired response retains its URL, request metadata, status, headers, body,
fetch time, byte size, library/parser version, and SHA-256. A content hash
identifies an acquired artifact; it does not invent an IBGE revision identifier.

Calendar entries and observations are separate records. Match product and
reference period explicitly before attaching a publication date to an observation.
See the [API boundary decision](docs/adr/0001-official-api-boundaries.md).

## Project Structure

```text
ibge-data/
├── src/ibge_data/
│   ├── __init__.py      # Public API exports
│   ├── aggregates.py    # Aggregates v3 queries and parsers
│   ├── calendar.py      # Calendar v3 queries and parsers
│   ├── sidra.py         # SIDRA queries, bounds, and observations
│   ├── transport.py     # RawResponse and injectable HTTP transport
│   ├── errors.py        # Exception hierarchy
│   └── py.typed         # Typed-package marker
├── docs/
│   ├── adr/             # API boundary decisions
│   └── ibge-data-icon.svg  # Editable project icon
├── tests/               # Offline tests and recorded fixtures
├── pyproject.toml       # Packaging and test configuration
└── README.md
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest
python -m build
```

The default suite uses fixture transports and excludes `integration` tests.
The bounded live SIDRA test is opt-in: run
`python -m pytest tests/test_integration.py -m integration` deliberately when
network access and live endpoint validation are intended. Offline tests do not
establish current IBGE availability. The examples above make real requests when
run with `UrllibTransport`.

## Data Source

This library accesses the official IBGE APIs:

- [SIDRA API help](https://apisidra.ibge.gov.br/home/ajuda)
- [Aggregates API v3](https://servicodados.ibge.gov.br/api/docs/agregados?versao=3)
- [Calendar API v3](https://servicodados.ibge.gov.br/api/docs/calendario?versao=3)

## License

MIT (see [LICENSE](LICENSE)). The code license does not relicense IBGE data;
check the source's terms and attribution requirements when redistributing it.

## Releasing

The first `ibge-data` release is prepared as 0.1.0. The package uses the new
`ibge_data` import namespace and does not install the unrelated PyPI project's
`ibgepy` namespace. See [release preparation](docs/releasing.md) for publisher
configuration and release gates. No PyPI upload is performed by preparing this patch.

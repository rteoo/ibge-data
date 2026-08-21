# ibgepy

`ibgepy` is a small, typed client for the official IBGE APIs:

- SIDRA Values (`apisidra.ibge.gov.br`)
- Aggregates v3 (`servicodados.ibge.gov.br/api/v3/agregados`)
- Calendar v3 (`servicodados.ibge.gov.br/api/v3/calendario`)

It has no runtime dependencies. HTTP acquisition is injectable, so raw responses can be recorded once and parsed offline in tests or downstream applications.

## Safety and provenance

SIDRA documents a maximum of 100,000 returned values. `SidraQuery` estimates explicit selections and rejects known over-limit queries. Requests containing `all` or another unknown cardinality require `known_count` metadata and are rejected when their bound cannot be proven.

Every acquired response keeps its URL, request metadata, status, headers, body, fetch time, and SHA-256 content hash. `published_at` is optional because the Values API exposes reference periods, not a universal row-level release timestamp. Revision state defaults to `unknown`; the content hash identifies the artifact without inventing an IBGE revision identifier.

## Example

```python
from ibgepy import GeographySelection, SidraQuery, VariableSelection, fetch_values
from ibgepy.transport import UrllibTransport

query = SidraQuery(
    table=1737,
    periods=("202401",),
    variables=VariableSelection(("2265",)),
    geography=GeographySelection(level="n1", values=("1",)),
)
raw = fetch_values(query, UrllibTransport())
print(raw.sha256)
```

Calendar research selectors use the official product alias, for example
`indice-nacional-de-precos-ao-consumidor-amplo`, rather than the display abbreviation `IPCA`.

The default tests use fixture transports and never contact IBGE. Live tests are marked `integration` and opt-in.

Version 0.1.0 intentionally supports one explicit SIDRA `N` geography selector (`n1`, `n2`, `n3`, or `n6`). The broader `G` views and multi-`N` query forms remain a capability gap; unsupported levels fail before network access.

Official references:

- [SIDRA API help](https://apisidra.ibge.gov.br/home/ajuda)
- [Aggregates API v3](https://servicodados.ibge.gov.br/api/docs/agregados?versao=3)
- [Calendar API v3](https://servicodados.ibge.gov.br/api/docs/calendario?versao=3)

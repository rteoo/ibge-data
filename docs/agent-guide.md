# Using ibgepy in agents

ibgepy is an acquisition library: explicit queries in, immutable raw response
artifacts and typed observations out. It has no runtime dependencies, background
tasks, automatic retries, implicit cache, or automatic query expansion.

## Choose the acquisition surface

| Need | Surface | Request bound |
| --- | --- | --- |
| Observation values with a preflight size check | `SidraQuery`, `fetch_values`, `parse_values` | Known selections must fit within 100,000 values |
| Discover tables, metadata, periods, or localities | Aggregates `fetch_*` functions | Low-level endpoint calls; no cardinality guarantee |
| Aggregates default-view observations | `fetch_variable`, `parse_aggregate_observations` | Low-level endpoint call; no cardinality guarantee |
| Product release dates | `CalendarQuery`, `fetch_calendar`, `parse_calendar` | Use explicit date/quantity filters |

For bounded observation acquisition, use SIDRA Values. The Aggregates functions
are explicit low-level calls, not a bounded query planner. Their string filters
are passed to the official endpoint; URL encoding is not metadata validation.
`parse_aggregate_observations` accepts only the default array view, not OLAP or
flat-view results.

## Plan before acquiring

```python
from ibgepy import (
    GeographySelection, SidraQuery, UrllibTransport, VariableSelection,
    build_values_url, fetch_values, parse_values,
)

query = SidraQuery(
    table=1737,
    periods=("202401",),
    variables=VariableSelection(("2265",)),
    geography=GeographySelection("n1", ("1",)),
)

# Both operations are offline. Use a lower per-task ceiling when appropriate.
query.validate_bound(max_values=1_000)
url = build_values_url(query)
assert query.estimated_values == 1

raw = fetch_values(query, UrllibTransport(timeout=15.0))
# Persist raw before parsing, using the application's approved storage policy.
observations = parse_values(raw, query)
assert observations[0].period_code == "202401"
```

Each tuple member must be one ASCII numeric code. Lists, duplicates, compound
members such as `("1,2",)`, ranges, and wildcards inside tuples fail with
`InvalidQueryError`. Use `("1", "2")` for two codes. Periods accept a tuple of
codes, one code as a string, or `"last N"` with a positive integer N.

Use only identifiers obtained from official metadata or an explicit caller
selection. Syntactic validation does not prove that a table/code exists.
One SIDRA geography selector is supported: `n1`, `n2`, `n3`, or `n6`.
Classification codes must be unique; at most six may be supplied.

Wildcards are standalone strings. `all` and `allxp` variables, `all` geography,
and `all`/`allxt` categories retain their different meanings. They need a
positive integer `known_count` established from matching metadata. Never guess
counts to satisfy validation; an incorrect caller assertion cannot establish a
real acquisition bound. Parsing rejects responses exceeding the asserted count,
but that detects the problem after download. If explicit codes also have
`known_count`, the count must match.
`periods="all"` has unknown cardinality and cannot be fetched; enumerate the
period codes from metadata instead.

The library never subdivides or broadens a query automatically. For large jobs,
enumerate explicit selections, construct smaller queries, validate each one,
and set an application-level request and time budget.

## Handle failures without parsing messages

| Exception | Structured evidence | Agent action |
| --- | --- | --- |
| `InvalidQueryError` | Invalid field described in the message | Correct the input; do not retry unchanged |
| `QueryTooLargeError` | `estimated_values`, `max_values`, `unknown_dimensions` | Reduce the explicit selection or acquire missing metadata |
| `HttpStatusError` | `status_code`, `headers`, `retry_after`, `response` | Retain the raw response; classify the status under the task's retry budget |
| `TransportError` | Chained underlying error | Inspect connectivity/configuration; retry only within a bounded policy |
| `ParseError` | Original `RawResponse` held by the caller | Retain the artifact; inspect the schema/token before continuing |

Catch `QueryTooLargeError` before `InvalidQueryError`, because it is a subclass.
`unknown_dimensions` uses `geography`, `variable`, `period`, and
`classification:<code>` identifiers. The over-limit case has an estimate; the
unknown-cardinality case has `estimated_values=None`.

HTTP errors raised from an acquired response expose that same artifact as
`error.response`, including bytes, URL, headers, timestamp, and hash. Its value
can be `None` if an application constructs the exception directly. Avoid
putting response bodies, headers, or private task data in public logs.

The transport performs one GET per call. Do not blindly retry HTTP 500: it can
represent an invalid or oversized request. For temporary failures, the caller
owns the attempt limit, total deadline, and maximum delay. Treat `retry_after`
as optional and cap it under that policy; malformed and non-finite delays are
reported as `None`. Successful test execution does not authorize unlimited
network activity.

## Preserve evidence and meaning

Store the original `RawResponse.body` with `url`, `status_code`, headers,
`request_headers`, `fetched_at`, `sha256`, `library_version`, and
`parser_version`. The hash identifies bytes, not an official revision. The
current parser version is `ibge-json-2`; stricter validation can reject an old
artifact that an earlier parser accepted.

The parser honors `Content-Encoding: gzip` without changing the raw response
bytes or their hash. Identity and gzip are supported; other encodings fail
explicitly. Decoded JSON is limited to 128 MiB per artifact, including compressed
responses, to bound parser memory use. This is a decoding limit, not a network
download-size guarantee.

Keep numeric values as `Decimal` or exact strings when serializing tool
results. `raw_value` is authoritative for the original token; `special_value`
distinguishes absolute zero, calculated zero, suppressed, unavailable,
not-applicable, and range-coded results. Do not replace these distinctions with
a single null, and do not convert exact decimals to binary floats implicitly.

SIDRA dimension roles follow the library's canonical URL order. The parser
requires a requested header for nonempty data and checks geography and variable
header positions, expected dimensions, and explicit code membership. It rejects
duplicate dimension-code tuples when every dimension's code is present. Outputs
without complete codes cannot establish row identity by code alone.
Unexpected dimensions require explicit classifications or schema
investigation; they are not silently discarded. Outputs `f/n` and `f/u` omit
some identifiers: the corresponding observation codes stay `None`. Prefer
the default `OutputOptions(fields="a")` for stable joins.

Malformed records, missing values/dimensions, duplicate JSON keys, non-standard
JSON numbers, unknown tokens, and non-finite observation numbers raise
`ParseError`. A valid empty array returns an empty tuple. A parser error must
not be treated as an empty successful result.

Calendar publication dates belong to products and reference periods. Never
assign one to an observation without an explicit matching rule.
`published_at` may be absent and revision state remains `unknown`.

## Verification

```console
python -m pytest
python -m pytest -m integration
```

The default suite is offline. The second command explicitly opts into live
official requests and requires network access. Keep production data and costs
out of default tests. `tests/fixtures/sidra_1737_live.json` is a normalized JSON
snapshot of the one-value response observed on 2026-11-10 at
`https://apisidra.ibge.gov.br/values/t/1737/n1/1/v/2265/p/202401/h/y/f/a/d/m`;
its whitespace is normalized and is not a byte-identical acquisition artifact.
The other small fixtures also exercise synthetic precision and special tokens.

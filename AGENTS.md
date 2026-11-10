# ibgedata

Standalone, no-runtime-dependency Python client for the official IBGE SIDRA Values, Aggregates v3, and Calendar APIs.

- Python `>=3.10`; runtime uses only the standard library.
- Network acquisition is injectable through `ibgedata.transport.Transport`; tests use recorded fixtures and never contact IBGE.
- Raw responses retain URL, status, headers, body, fetch time, and SHA-256. Parsing is deterministic and accepts recorded bytes.
- The SIDRA Values API has a documented 100,000-value limit. Query construction must reject known over-limit requests and unknown cardinality; there is no unbounded escape hatch.
- Special SIDRA values remain available as their original token and typed classification; they must not be silently coerced to missing or numeric data.
- `published_at` and revision state are optional/unknown. A content hash identifies an acquired artifact; ibgedata does not invent revision IDs.
- Live integration tests are opt-in and require network access. The default test suite is offline.

## Release identity

- Canonical repository, distribution, and import package: `rteoo/ibgedata`, `ibgedata`, and `ibgedata`.
- Do not ship an `ibgepy` import alias; that PyPI name belongs to an unrelated project.
- Keep the project version, runtime `__version__`, raw-response library version, and HTTP user agent aligned.
- `publish.yml` runs only on a final GitHub Release; it requires a matching PyPI Trusted Publisher and protected `pypi` environment. See `docs/releasing.md`.

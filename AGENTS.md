# ibgepy

Standalone, no-runtime-dependency Python client for the official IBGE SIDRA Values, Aggregates v3, and Calendar APIs.

- Python `>=3.10`; runtime uses only the standard library.
- Network acquisition is injectable through `ibgepy.transport.Transport`; tests use recorded fixtures and never contact IBGE.
- Raw responses retain URL, status, headers, body, fetch time, and SHA-256. Parsing is deterministic and accepts recorded bytes.
- The SIDRA Values API has a documented 100,000-value limit. Query construction must reject known over-limit requests and unknown cardinality; there is no unbounded escape hatch.
- Special SIDRA values remain available as their original token and typed classification; they must not be silently coerced to missing or numeric data.
- `published_at` and revision state are optional/unknown. A content hash identifies an acquired artifact; ibgepy does not invent revision IDs.
- Live integration tests are opt-in and require network access. The default test suite is offline.

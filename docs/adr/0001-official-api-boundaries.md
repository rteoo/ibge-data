# ADR 0001: Keep release and revision metadata separate from SIDRA values

- **Status:** Accepted
- **Date:** 2026-08-21

## Context

SIDRA Values and Aggregates v3 expose reference periods and observations. Calendar v3 exposes product publication dates. None provides a universal row-level revision identifier.

## Decision

Use the official Values, Aggregates, and Calendar contracts as separate acquisition surfaces. Preserve each raw response with its URL, headers, fetch time, parser/library version, byte size, and SHA-256. Map a calendar entry to an observation only when the product and reference period match explicitly. Default revision state to `unknown`; changed bytes create a new artifact.

SIDRA’s documented 100,000-value ceiling is enforced before acquisition. Unknown cardinality is rejected; there is no unbounded escape hatch.

## Consequences

Downstream systems can replay and compare revisions without fabricated identifiers. Release dates remain nullable when no authoritative mapping exists. Broad `all` queries require a proven cardinality.

The initial SIDRA surface supports one explicit `N` geography selector. `G` territorial views and multiple simultaneous `N` parameters remain outside version 0.1.0 and must not be approximated.

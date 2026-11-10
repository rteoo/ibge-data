from __future__ import annotations

import gzip
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from conftest import FixtureTransport

from ibgepy import (
    ClassificationSelection,
    GeographySelection,
    HttpStatusError,
    InvalidQueryError,
    OutputOptions,
    ParseError,
    QueryTooLargeError,
    SidraQuery,
    UrllibTransport,
    VariableSelection,
    build_values_url,
    fetch_values,
    parse_aggregate_document,
    parse_aggregate_list,
    parse_aggregate_observations,
    parse_values,
)
from ibgepy.transport import _retry_after


def query(**changes) -> SidraQuery:
    values = dict(
        table=1737,
        periods=("202401",),
        variables=VariableSelection(("2265",)),
        geography=GeographySelection("n1", ("1",)),
        output=OutputOptions(header=False),
    )
    values.update(changes)
    return SidraQuery(**values)


def response(payload):
    return FixtureTransport(json.dumps(payload).encode()).get("https://fixture.invalid")


def row(**changes):
    result = dict(V="4.51", D1C="1", D1N="Brasil", D2C="2265", D2N="IPCA",
                  D3C="202401", D3N="janeiro 2024")
    result.update(changes)
    return result


@pytest.mark.parametrize("token", ["all", "allxp", "1,2", "1-9", "1/2", "1|2", " 1", "١", 1, True])
@pytest.mark.parametrize("kind", ["variable", "geography", "classification", "period"])
def test_compound_and_non_atomic_tuple_members_are_rejected(token, kind) -> None:
    with pytest.raises(InvalidQueryError, match="atomic"):
        if kind == "variable":
            VariableSelection((token,))
        elif kind == "geography":
            GeographySelection("n1", (token,))
        elif kind == "classification":
            ClassificationSelection("315", (token,))
        else:
            query(periods=(token,))


@pytest.mark.parametrize("values", [None, 1, ["1"], {"1"}, ("1", "1")])
def test_selector_containers_fail_with_typed_errors(values) -> None:
    with pytest.raises(InvalidQueryError):
        VariableSelection(values)


@pytest.mark.parametrize("count", [True, 1.5, "1", 0, -1])
def test_untrusted_cardinality_is_an_integer(count) -> None:
    with pytest.raises(InvalidQueryError, match="positive integer"):
        GeographySelection("n6", "all", known_count=count)


def test_cardinality_metadata_cannot_contradict_explicit_codes() -> None:
    with pytest.raises(InvalidQueryError, match="match"):
        VariableSelection(("1", "2"), known_count=1)


@pytest.mark.parametrize("changes", [
    {"table": True}, {"table": 1.5}, {"variables": {}}, {"geography": []},
    {"output": {}}, {"classifications": []}, {"include_extinct_territories": "false"},
    {"periods": "last 0"}, {"periods": "202401,202402"}, {"periods": "202401-202412"},
])
def test_query_runtime_types_and_period_grammar(changes) -> None:
    with pytest.raises(InvalidQueryError):
        query(**changes)


@pytest.mark.parametrize(
    "options", [{"header": 1}, {"decimals": True}, {"decimals": []}, {"fields": []}]
)
def test_output_runtime_types(options) -> None:
    with pytest.raises(InvalidQueryError):
        OutputOptions(**options)


def test_classifications_have_atomic_unique_codes() -> None:
    with pytest.raises(InvalidQueryError):
        ClassificationSelection("315/all", ("7169",))
    selected = ClassificationSelection("315", ("7169",))
    with pytest.raises(InvalidQueryError, match="repeated"):
        query(classifications=(selected, selected))


def test_unknown_bound_is_structured_and_never_calls_transport() -> None:
    transport = FixtureTransport(b"[]")
    q = query(variables=VariableSelection("all"), geography=GeographySelection("n6", "all"))
    with pytest.raises(QueryTooLargeError) as caught:
        fetch_values(q, transport)
    assert caught.value.unknown_dimensions == ("geography", "variable")
    assert caught.value.estimated_values is None
    assert caught.value.max_values == 100_000
    assert transport.calls == []


def test_bound_enforces_the_exact_ceiling_and_retains_failure_details() -> None:
    q = query(periods="last 100000")
    assert q.estimated_values == 100_000
    assert "/last%20100000/" in build_values_url(q)
    with pytest.raises(QueryTooLargeError) as caught:
        replace(q, periods="last 100001").validate_bound()
    assert caught.value.estimated_values == 100_001
    assert caught.value.max_values == 100_000
    for limit in (True, 1.5, 0, 100_001):
        with pytest.raises(InvalidQueryError):
            q.validate_bound(max_values=limit)


def test_proven_wildcards_keep_their_distinct_meaning() -> None:
    q = query(variables=VariableSelection("allxp", known_count=4),
              geography=GeographySelection("n3", "all", known_count=27),
              classifications=(ClassificationSelection("315", "allxt", known_count=2),))
    assert q.estimated_values == 216
    url = build_values_url(q)
    assert "/v/allxp/" in url and "/n3/all/" in url and "/c315/allxt/" in url


@pytest.mark.parametrize(
    "value", ["NaN", "sNaN", "Infinity", "-Infinity", "1_000", " 1", 1.5, None, True]
)
def test_values_reject_non_finite_or_coerced_tokens(value) -> None:
    with pytest.raises(ParseError):
        parse_values(response([row(V=value)]), query())


def test_precision_and_original_token_are_preserved() -> None:
    token = "9007199254740993.0100"
    observation, = parse_values(response([row(V=token)]), query())
    assert observation.raw_value == token
    assert str(observation.value) == token
    assert observation.value == Decimal(token)


def test_nonempty_malformed_response_is_not_empty_success() -> None:
    malformed = row()
    del malformed["V"]
    with pytest.raises(ParseError, match="missing V"):
        parse_values(response([malformed]), query())
    with pytest.raises(ParseError, match="JSON array"):
        parse_values(response({"error": "query failed"}), query())
    assert parse_values(response([]), query()) == ()


@pytest.mark.parametrize("payload", [b'[{"V":"1","V":"2"}]', b'[{"V":NaN}]'])
def test_ambiguous_json_fails_without_discarding_raw_bytes(payload) -> None:
    raw = FixtureTransport(payload).get("https://fixture.invalid")
    with pytest.raises(ParseError):
        parse_values(raw, query())
    assert raw.body == payload


@pytest.mark.parametrize("token", [b"1e400", b"-1e400"])
def test_generic_json_float_overflow_is_rejected(token) -> None:
    payload = b'[{"x":' + token + b'}]'
    raw = FixtureTransport(payload).get("https://fixture.invalid")
    with pytest.raises(ParseError, match="non-finite"):
        parse_aggregate_document(raw)
    assert raw.body == payload


def test_generic_json_finite_numbers_keep_their_types() -> None:
    raw = FixtureTransport(b'[{"x":1.25,"y":-2.5e2,"count":3}]').get("https://fixture.invalid")
    document = parse_aggregate_document(raw)
    assert document.records == ({"x": 1.25, "y": -250.0, "count": 3},)
    assert type(document.records[0]["x"]) is float
    assert type(document.records[0]["count"]) is int


def test_response_cannot_exceed_the_asserted_cardinality() -> None:
    q = query(geography=GeographySelection("n3", "all", known_count=1))
    raw = response([row(D1C="11"), row(D1C="12")])
    with pytest.raises(ParseError, match="bound"):
        parse_values(raw, q)


def test_duplicate_complete_dimension_keys_are_not_successful_observations() -> None:
    q = query(periods="last 2")
    with pytest.raises(ParseError, match="duplicate"):
        parse_values(response([row(), row(V="5.00")]), q)


def test_distinct_rows_at_the_bound_are_accepted() -> None:
    q = query(periods=("202401", "202402"))
    observations = parse_values(response([row(), row(D3C="202402")]), q)
    assert len(observations) == q.estimated_values == 2


def test_requested_header_is_required_for_nonempty_data() -> None:
    with pytest.raises(ParseError, match="header"):
        parse_values(response([row()]), query(output=OutputOptions(header=True)))


def test_swapped_geography_and_period_headers_are_rejected() -> None:
    q = query(periods="last 1", geography=GeographySelection("n1", "all", known_count=1))
    header = row(V="Valor", D1N="Mês", D2N="Variável", D3N="Brasil")
    data = row(D1C="202401", D3C="1")
    with pytest.raises(ParseError, match="geography"):
        parse_values(response([header, data]), q)


@pytest.mark.parametrize("field", ["MC", "MN"])
@pytest.mark.parametrize("value", [2, {}, [], True])
def test_sidra_units_are_never_coerced(field, value) -> None:
    with pytest.raises(ParseError, match="string"):
        parse_values(response([row(**{field: value})]), query())


def test_gzip_json_decodes_without_mutating_the_artifact() -> None:
    payload = gzip.compress(b'[{"id":9514,"nome":"Census"}]', mtime=0)
    raw = replace(response([]), body=payload, headers={"Content-Encoding": "gzip"})
    digest = raw.sha256
    document = parse_aggregate_document(raw)
    assert document.records == ({"id": 9514, "nome": "Census"},)
    assert raw.body == payload and raw.sha256 == digest


@pytest.mark.parametrize("payload", [b"not gzip", b"\x1f\x8b"])
def test_malformed_gzip_raises_a_typed_error(payload) -> None:
    raw = replace(response([]), body=payload, headers={"content-encoding": "GZip"})
    with pytest.raises(ParseError):
        parse_aggregate_document(raw)


@pytest.mark.parametrize("compressed", [False, True])
def test_decoded_json_has_a_bounded_size(monkeypatch, compressed) -> None:
    monkeypatch.setattr("ibgepy._json.MAX_JSON_BYTES", 32)
    body = b'[{"name":"' + b"x" * 64 + b'"}]'
    payload = gzip.compress(body, mtime=0) if compressed else body
    headers = {"content-encoding": "gzip"} if compressed else {}
    raw = replace(response([]), body=payload, headers=headers)
    with pytest.raises(ParseError, match="parser limit"):
        parse_aggregate_document(raw)
    assert raw.body == payload


def test_unsupported_content_encoding_fails_explicitly() -> None:
    raw = replace(response([]), headers={"Content-Encoding": "br"})
    with pytest.raises(ParseError, match="unsupported Content-Encoding"):
        parse_aggregate_document(raw)


def test_reordered_missing_extra_or_mismatched_dimensions_fail() -> None:
    for changes in ({"D2C": "202401", "D3C": "2265"}, {"D3C": None},
                    {"D4C": "1", "D4N": "unknown"}, {"D2C": "63"}):
        with pytest.raises(ParseError):
            parse_values(response([row(**changes)]), query())
    header = row(V="Valor", D2C="Mês (Código)", D2N="Mês")
    with pytest.raises(ParseError, match="position"):
        parse_values(response([header, row()]), query())
    header["D2N"] = "Variável"
    with pytest.raises(ParseError, match="start"):
        parse_values(response([row(), header]), query())


@pytest.mark.parametrize("fields", ["a", "c", "n", "u"])
def test_official_field_variants_preserve_only_the_available_identifiers(fields) -> None:
    data = row()
    for key in tuple(data):
        if (fields == "c" and key.endswith("N")) or (fields == "n" and key.endswith("C")):
            del data[key]
        elif fields == "u" and key in {"D2C", "D3C"}:
            del data[key]
    observation, = parse_values(
        response([data]), query(output=OutputOptions(fields=fields, header=False))
    )
    assert observation.value == Decimal("4.51")
    assert observation.variable_code == ("2265" if fields in {"a", "c"} else None)


def test_live_shape_replays_offline() -> None:
    fixture = Path(__file__).parent / "fixtures" / "sidra_1737_live.json"
    raw = FixtureTransport(fixture.read_bytes()).get("https://fixture.invalid")
    observation, = parse_values(raw, query())
    assert observation.period_code == "202401"
    assert observation.variable_code == "2265"
    assert observation.value == Decimal("4.51")


def test_aggregate_values_share_strict_numeric_decoding() -> None:
    fixture = Path(__file__).parent / "fixtures" / "aggregate_values.json"
    for token in ("NaN", "Infinity", None, 1.5):
        payload = json.loads(fixture.read_bytes())
        payload[0]["resultados"][0]["series"][0]["serie"]["202606"] = token
        with pytest.raises(ParseError):
            parse_aggregate_observations(response(payload), aggregate_id=7060)
    with pytest.raises(ParseError, match="default JSON array"):
        parse_aggregate_observations(response({"error": "bad query"}), aggregate_id=7060)


@pytest.mark.parametrize("identifier", [True, 1.5, [], {}, None, "all"])
def test_aggregate_identifiers_are_not_coerced(identifier) -> None:
    with pytest.raises(ParseError):
        parse_aggregate_list(response([{"id": identifier}]))
    fixture = Path(__file__).parent / "fixtures" / "aggregate_values.json"
    payload = json.loads(fixture.read_bytes())
    payload[0]["id"] = identifier
    with pytest.raises(ParseError):
        parse_aggregate_observations(response(payload), aggregate_id=7060)


def test_aggregate_classification_identifiers_and_names_are_preserved_or_rejected() -> None:
    fixture = Path(__file__).parent / "fixtures" / "aggregate_values.json"
    for categories in ({}, {"7169": None}, {"unknown": "Total"}):
        payload = json.loads(fixture.read_bytes())
        payload[0]["resultados"][0]["classificacoes"][0]["categoria"] = categories
        with pytest.raises(ParseError):
            parse_aggregate_observations(response(payload), aggregate_id=7060)


def test_http_failures_retain_the_complete_response_for_agent_inspection() -> None:
    transport = FixtureTransport(b'{"error":"busy"}', status_code=503)
    with pytest.raises(HttpStatusError) as caught:
        fetch_values(query(), transport)
    assert caught.value.response is not None
    assert caught.value.response.body == b'{"error":"busy"}'
    assert caught.value.response.sha256
    assert len(transport.calls) == 1


@pytest.mark.parametrize("timeout", [True, "30", float("nan"), float("inf"), 0, -1])
def test_transport_timeouts_are_finite_and_positive(timeout) -> None:
    with pytest.raises(ValueError, match="finite positive"):
        UrllibTransport(timeout=timeout)


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_retry_after_never_returns_non_finite_delays(token) -> None:
    assert _retry_after({"Retry-After": token}) is None

"""Distribution identity and the source evidence contract must stay aligned."""

from importlib import metadata

import pytest

import ibge_data
from ibge_data import RawResponse, UrllibTransport


def test_public_exports_exist():
    assert all(hasattr(ibge_data, name) for name in ibge_data.__all__)


def test_distribution_version_matches_runtime():
    try:
        installed = metadata.version("ibge-data")
    except metadata.PackageNotFoundError:
        pytest.skip("ibge_data distribution metadata is not installed")
    assert installed == ibge_data.__version__


def test_raw_response_default_version_matches_runtime():
    assert RawResponse.__dataclass_fields__["library_version"].default == ibge_data.__version__


def test_http_user_agent_uses_canonical_name(monkeypatch):
    import urllib.error

    def reject(request, *, timeout):
        assert request.get_header("User-agent") == "ibge-data/0.1"
        raise urllib.error.URLError("fixture refuses network")

    monkeypatch.setattr("ibge_data.transport.urllib.request.urlopen", reject)
    with pytest.raises(ibge_data.TransportError):
        UrllibTransport().get("https://fixture.invalid")

"""Distribution identity and the source evidence contract must stay aligned."""

from importlib import metadata

import pytest

import ibgedata
from ibgedata import RawResponse, UrllibTransport


def test_public_exports_exist():
    assert all(hasattr(ibgedata, name) for name in ibgedata.__all__)


def test_distribution_version_matches_runtime():
    try:
        installed = metadata.version("ibgedata")
    except metadata.PackageNotFoundError:
        pytest.skip("ibgedata distribution metadata is not installed")
    assert installed == ibgedata.__version__


def test_raw_response_default_version_matches_runtime():
    assert RawResponse.__dataclass_fields__["library_version"].default == ibgedata.__version__


def test_http_user_agent_uses_canonical_name(monkeypatch):
    import urllib.error

    def reject(request, *, timeout):
        assert request.get_header("User-agent") == "ibgedata/0.1"
        raise urllib.error.URLError("fixture refuses network")

    monkeypatch.setattr("ibgedata.transport.urllib.request.urlopen", reject)
    with pytest.raises(ibgedata.TransportError):
        UrllibTransport().get("https://fixture.invalid")

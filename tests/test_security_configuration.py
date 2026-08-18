import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.settings import Settings


pytestmark = pytest.mark.no_db


def test_trusted_origins_rejects_wildcard_with_credentials():
    with pytest.raises(ValidationError):
        Settings(origins=["https://trusted.example", "*"])


def test_trusted_origins_parses_json_and_delimited_values(monkeypatch):
    monkeypatch.setenv(
        "TRUSTED_ORIGINS",
        '["https://dandjoo.bio.wa.gov.au","http://localhost:8080"]',
    )
    assert Settings().origins == [
        "https://dandjoo.bio.wa.gov.au",
        "http://localhost:8080",
    ]

    monkeypatch.setenv(
        "TRUSTED_ORIGINS",
        "https://dandjoo.bio.wa.gov.au, http://localhost:8080",
    )
    assert Settings().origins == [
        "https://dandjoo.bio.wa.gov.au",
        "http://localhost:8080",
    ]


def test_cors_does_not_reflect_untrusted_origin_with_credentials():
    client = TestClient(create_app(Settings(origins=["https://trusted.example"])))

    response = client.options(
        "/records/clusters/",
        headers={
            "Origin": "https://attacker.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_trusted_origin_with_credentials():
    client = TestClient(create_app(Settings(origins=["https://trusted.example"])))

    response = client.options(
        "/records/clusters/",
        headers={
            "Origin": "https://trusted.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://trusted.example"
    assert response.headers["access-control-allow-credentials"] == "true"

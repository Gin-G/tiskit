"""Smoke tests for the FastAPI app.

The container build has historically shipped startup-time bugs (env var
parsing, middleware API mismatch). These tests import the app and drive
it through Starlette's TestClient so any such bug fails CI instead of
the cluster.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_healthz_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_readyz_ok(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200


def test_security_headers_applied(client: TestClient) -> None:
    """Exercises SecurityHeadersMiddleware end-to-end.

    This is the path that broke with `MutableHeaders.pop` — without a
    request flowing through the middleware, the bug is invisible.
    """
    r = client.get("/healthz")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "strict-transport-security" in r.headers
    assert "content-security-policy" in r.headers
    # The middleware strips the server identifier; TestClient doesn't set
    # one, but the deletion path itself must not raise.
    assert "server" not in {k.lower() for k in r.headers}


def test_request_id_round_trip(client: TestClient) -> None:
    r = client.get("/healthz", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"


def test_rejects_non_pdf_content_type(client: TestClient) -> None:
    r = client.post(
        "/api/templates/analyze",
        files={"file": ("x.txt", b"not a pdf", "text/plain")},
    )
    assert r.status_code == 415


def test_rejects_pdf_without_magic_bytes(client: TestClient) -> None:
    r = client.post(
        "/api/templates/analyze",
        files={"file": ("x.pdf", b"garbage", "application/pdf")},
    )
    assert r.status_code == 415

import pytest
from fastapi.testclient import TestClient

from ai_hq.api import create_app
from ai_hq.config import Settings

KEY = "hardening-test-key-1234567890abcdefghij"


@pytest.fixture
def client(tmp_path):
    app = create_app(Settings(data_dir=tmp_path / "data"), bootstrap_key=KEY, start_worker=False)

    @app.get("/api/explode")
    def explode():
        raise RuntimeError("internal detail token=abcdefghijklmnop1234")

    with TestClient(app) as test_client:
        test_client.headers["X-CSRF-Token"] = test_client.post("/api/session", json={"key": KEY}).json()["csrf_token"]
        yield test_client


def test_unexpected_error_answers_500_without_internals_and_is_logged_redacted(client):
    response = client.get("/api/explode")
    assert response.status_code == 500
    detail = response.json()["detail"]
    assert "reference" in detail and "abcdefghijklmnop1234" not in detail and "RuntimeError" not in detail
    lines = "\n".join(client.get("/api/logs").json()["lines"])
    assert "GET /api/explode failed" in lines and "RuntimeError" in lines
    assert "abcdefghijklmnop1234" not in lines


def test_logs_need_a_session(client):
    client.cookies.clear()
    assert client.get("/api/logs").status_code == 401


def test_changes_are_rate_limited_per_session(client):
    answers = [client.delete("/api/business/gmail").status_code for _ in range(301)]
    assert 429 not in answers[:300] and answers[300] == 429
    refused = client.delete("/api/business/gmail")
    assert refused.status_code == 429 and int(refused.headers["Retry-After"]) > 0
    assert client.get("/api/logs").status_code == 200  # reading is never limited


def test_the_bundled_fonts_are_served_as_fonts(client):
    response = client.get("/static/fonts/Inter-Regular.woff2")
    assert response.status_code == 200 and response.headers["content-type"] == "font/woff2" and len(response.content) > 50000
    assert client.get("/static/fonts/Inter-LICENSE.txt").status_code == 200  # the licence travels with the fonts

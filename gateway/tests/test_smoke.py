from fastapi.testclient import TestClient

from ltplus.config import _ROOT
from ltplus.main import app

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_repository_defaults_resolve() -> None:
    assert (_ROOT / "modes").is_dir()

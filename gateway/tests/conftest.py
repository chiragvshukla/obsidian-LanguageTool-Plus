from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ltplus.config import Settings
from ltplus.main import create_app

MODES_DIR = Path(__file__).resolve().parents[2] / "modes"


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        lt_url="http://lt.test",
        modes_dir=MODES_DIR,
        default_mode="neutral",
        default_language="de-DE",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client

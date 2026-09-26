import json
from pathlib import Path

import pytest

from app.config import get_settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def golden_case() -> dict:
    return json.loads((FIXTURES / "golden_case.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def mock_data(settings) -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in settings.mock_data_dir.glob("*.json")}

import os
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv


SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

load_dotenv(REPO_ROOT / ".env", override=False)

REAL_MODEL_TESTS = os.getenv("REAL_MODEL_TESTS") == "1"

if REAL_MODEL_TESTS:
    os.environ["APP_ENV"] = "local"
    os.environ["MOCK_MODEL_ENABLED"] = "false"
else:
    os.environ["APP_ENV"] = "test"
    os.environ["MOCK_MODEL_ENABLED"] = "true"

os.environ.setdefault("MIMO_API_KEY", "test-key")
os.environ.setdefault("TRACE_PERSISTENCE_ENABLED", "false")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "real_model: integration tests against configured MiMo provider")


@pytest.fixture(autouse=True)
def reset_settings_cache() -> None:
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()

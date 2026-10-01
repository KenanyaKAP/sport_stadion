import os
import tempfile

# Point the app at a throwaway database before it is imported by any test module.
_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["SPORTSTADION_DB_URL"] = f"sqlite:///{_db.name}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c

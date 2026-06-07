import sys
from pathlib import Path

import pytest

# Ensure backend root is importable during pytest collection.
backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.db import sqlite as sqlite_db

TEST_DB_PATH = backend_root / ".pytest_cache" / "metadata_test.db"
sqlite_db.DB_PATH = TEST_DB_PATH


@pytest.fixture(autouse=True)
def isolated_metadata_db():
    sqlite_db.DB_PATH = TEST_DB_PATH
    TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    sqlite_db.run_migrations()
    yield

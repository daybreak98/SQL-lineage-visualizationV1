import sys
from pathlib import Path
import sqlite3

import pytest

# Ensure backend root is importable during pytest collection.
backend_root = Path(__file__).parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.db.sqlite import DB_PATH, run_migrations


@pytest.fixture(autouse=True)
def reset_metadata_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    run_migrations()
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("DELETE FROM column_metadata")
        conn.execute("DELETE FROM table_metadata")
        conn.execute("DELETE FROM metadata_imports")
        conn.commit()
    finally:
        conn.close()
    yield

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from accountdomino import db  # noqa: E402


@pytest.fixture
def db_file(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("ACCOUNTDOMINO_DB", str(path))
    return path


@pytest.fixture
def conn(db_file):
    c = db.connect(db_file)
    db.init_schema(c)
    yield c
    c.close()

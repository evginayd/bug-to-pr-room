"""Regression tests added by the agents.

The repro agent writes a failing test here for each bug it reproduces, and
the fixer agent keeps it when it fixes the bug, so the bug cannot return.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app, reset_store

client = TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def clean_store():
    reset_store()
    yield
    reset_store()

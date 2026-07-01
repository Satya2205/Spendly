"""Shared fixtures for the Spendly test suite.

Each test gets an isolated in-memory SQLite database so tests are
independent and deterministic. The `auth_client` fixture registers and
signs in a seeded user before yielding a Flask test client, so feature
tests that need an authenticated session can request it directly.
"""

import os
import sys
import tempfile

import pytest

# Make the project root importable when pytest is launched from any cwd.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import app as flask_app  # noqa: E402
from database.db import init_db  # noqa: E402


@pytest.fixture
def app():
    """Yield a Flask app configured for testing with a fresh DB per test."""
    # Use a temp file (not :memory:) because the app's get_db() reads DB_PATH
    # at call time and our db helpers expect a file path.
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret",
        DATABASE=db_path,
    )

    # Point the db module at this test's file and initialise the schema.
    import database.db as db_module

    db_module.DB_PATH = db_path
    init_db()

    yield flask_app

    # Cleanup: drop the temp DB file.
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def client(app):
    """Unauthenticated Flask test client."""
    return app.test_client()


@pytest.fixture
def auth_client(client):
    """A Flask test client that has registered and signed in a test user.

    The seeded user owns no expenses so tests can add their own fixtures
    against a known-empty baseline when needed.
    """
    client.post(
        "/register",
        data={
            "name": "Test User",
            "email": "test@spendly.com",
            "password": "testpass123",
        },
    )
    return client
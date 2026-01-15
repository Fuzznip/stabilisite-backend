"""
Pytest configuration file
This runs once before all tests to set up the database schema
"""
import pytest
from app import app, db
from sqlalchemy import text


@pytest.fixture(scope="session", autouse=True)
def setup_database_schema():
    """Create the new_stability schema before any tests run"""
    with app.app_context():
        # Create the schema if it doesn't exist
        with db.engine.connect() as conn:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS new_stability"))
            conn.commit()

    yield

    # Teardown: Drop the schema after all tests
    with app.app_context():
        with db.engine.connect() as conn:
            conn.execute(text("DROP SCHEMA IF EXISTS new_stability CASCADE"))
            conn.commit()

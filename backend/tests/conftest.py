"""Pytest fixtures shared across the test suite.

Provides:
  - pg_container  – session-scoped PostgreSQL 18 + pgvector container
  - test_engine   – SQLAlchemy engine pointed at the container
  - db_session    – per-test transactional session (rolls back after each test)
  - test_client   – FastAPI TestClient wired to the test database
"""
from __future__ import annotations

import sys
import os
import pytest

# Make the backend/app package importable when running pytest from backend/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# PostgreSQL testcontainer (session-scoped – starts once per pytest run)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pg_container():
    """Start a PostgreSQL 18 + pgvector container for the test session."""
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer(
        image="pgvector/pgvector:pg18",
        username="test",
        password="test",
        dbname="test_clusterizer",
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def test_engine(pg_container):
    """Create the SQLAlchemy engine and initialise the schema."""
    from sqlalchemy import create_engine, text
    from app.database import Base
    from app import models  # noqa: F401 — registers all ORM models with Base.metadata

    url = pg_container.get_connection_url()
    engine = create_engine(url, pool_pre_ping=True)

    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(test_engine):
    """Provide a transactional session that is rolled back after each test."""
    from sqlalchemy.orm import sessionmaker

    Session = sessionmaker(bind=test_engine)
    session = Session()
    yield session
    session.rollback()
    session.close()


# ---------------------------------------------------------------------------
# FastAPI test client with DB dependency override
# ---------------------------------------------------------------------------

@pytest.fixture
def test_client(test_engine):
    """FastAPI TestClient that uses the test database.

    Both the dependency-injected ``get_db`` sessions *and* the engine used
    by the startup event handler are replaced with the test engine so the
    client never tries to connect to the production ``localhost:5432``.
    """
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker
    from app.main import app
    from app.database import get_db
    import app.main as main_module

    Session = sessionmaker(bind=test_engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Redirect the startup-event engine to the test container.
    # main.py does `from .database import engine` at module level, so we must
    # patch the name in app.main (not app.database) to affect the startup handler.
    import app.main as main_module
    original_engine = main_module.engine
    main_module.engine = test_engine

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client

    app.dependency_overrides.clear()
    main_module.engine = original_engine

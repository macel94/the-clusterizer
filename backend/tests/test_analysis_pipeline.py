"""Integration tests for the full analysis pipeline.

Spins up a real PostgreSQL 18 + pgvector container (via testcontainers),
mocks Jira HTTP and Ollama HTTP with *responses*, and patches
``generate_embeddings`` with deterministic random vectors so no Ollama
instance is required.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import numpy as np
import pytest
import responses as rsps_lib

from tests.generators import generate_tickets, generate_jira_api_response

JIRA_URL = "https://jira.pipeline-test.example"
_TICKETS = generate_tickets()          # 40 tickets across 5 themes
_N_TICKETS = len(_TICKETS)


def _fake_embeddings(texts):
    """Return deterministic random vectors matching the configured embed dim."""
    from app.config import settings
    rng = np.random.default_rng(seed=42)
    return rng.standard_normal((len(texts), settings.OLLAMA_EMBED_DIM)).astype(np.float32)


def _register_ollama_llm_mock(label: str = "Mocked Cluster Label") -> None:
    """Register a mock for every Ollama /api/generate call."""
    rsps_lib.add(
        rsps_lib.POST,
        "http://localhost:11434/api/generate",
        json={"response": label, "done": True},
        status=200,
    )


# ---------------------------------------------------------------------------
# Full happy-path pipeline
# ---------------------------------------------------------------------------

@rsps_lib.activate
@patch("app.services.analysis.generate_embeddings", side_effect=_fake_embeddings)
def test_full_pipeline_completed(mock_embed, test_engine, db_session):
    """run_analysis should set status=completed and persist all tickets."""
    from sqlalchemy.orm import sessionmaker
    from app.models import Analysis
    from app.services.analysis import run_analysis

    rsps_lib.add(rsps_lib.GET, f"{JIRA_URL}/rest/api/3/search",
                 json=generate_jira_api_response(_TICKETS), status=200)
    # Register one LLM mock per cluster (up to 5)
    for _ in range(5):
        _register_ollama_llm_mock()

    analysis = Analysis(
        id=uuid.uuid4(), jira_url=JIRA_URL, jql_filter="project = TEST",
        num_clusters=5, status="pending", total_tickets=0,
    )
    db_session.add(analysis)
    db_session.commit()

    TestSession = sessionmaker(bind=test_engine)
    with patch("app.database.SessionLocal", TestSession):
        run_analysis(str(analysis.id), JIRA_URL, "user@example.com",
                     "test-pat", "project = TEST", 5)

    db_session.expire_all()
    refreshed = db_session.query(Analysis).filter_by(id=analysis.id).first()
    assert refreshed is not None
    assert refreshed.status == "completed", (
        f"Expected completed, got {refreshed.status}: {refreshed.error_message}"
    )
    assert refreshed.total_tickets == _N_TICKETS
    assert refreshed.completed_at is not None


@rsps_lib.activate
@patch("app.services.analysis.generate_embeddings", side_effect=_fake_embeddings)
def test_full_pipeline_creates_clusters(mock_embed, test_engine, db_session):
    """Completed analysis should have the requested number of Cluster rows."""
    from sqlalchemy.orm import sessionmaker
    from app.models import Analysis, Cluster
    from app.services.analysis import run_analysis

    rsps_lib.add(rsps_lib.GET, f"{JIRA_URL}/rest/api/3/search",
                 json=generate_jira_api_response(_TICKETS), status=200)
    for _ in range(5):
        _register_ollama_llm_mock("Auth and Login Failures")

    analysis = Analysis(
        id=uuid.uuid4(), jira_url=JIRA_URL, jql_filter="project = TEST",
        num_clusters=5, status="pending", total_tickets=0,
    )
    db_session.add(analysis)
    db_session.commit()

    TestSession = sessionmaker(bind=test_engine)
    with patch("app.database.SessionLocal", TestSession):
        run_analysis(str(analysis.id), JIRA_URL, None, "test-pat",
                     "project = TEST", 5)

    db_session.expire_all()
    clusters = db_session.query(Cluster).filter_by(analysis_id=analysis.id).all()
    assert len(clusters) >= 1
    for c in clusters:
        assert c.ticket_count >= 1
        assert c.label  # label set either by LLM or keyword fallback
        assert isinstance(c.keywords, list)


# ---------------------------------------------------------------------------
# LLM label fallback: if Ollama /api/generate returns an error the pipeline
# should still complete using keyword-derived labels.
# ---------------------------------------------------------------------------

@rsps_lib.activate
@patch("app.services.analysis.generate_embeddings", side_effect=_fake_embeddings)
def test_pipeline_falls_back_to_keywords_when_llm_unavailable(
    mock_embed, test_engine, db_session
):
    from sqlalchemy.orm import sessionmaker
    from app.models import Analysis, Cluster
    from app.services.analysis import run_analysis

    rsps_lib.add(rsps_lib.GET, f"{JIRA_URL}/rest/api/3/search",
                 json=generate_jira_api_response(_TICKETS), status=200)
    # LLM endpoint is down
    rsps_lib.add(rsps_lib.POST, "http://localhost:11434/api/generate", status=500)

    analysis = Analysis(
        id=uuid.uuid4(), jira_url=JIRA_URL, jql_filter="project = TEST",
        num_clusters=5, status="pending", total_tickets=0,
    )
    db_session.add(analysis)
    db_session.commit()

    TestSession = sessionmaker(bind=test_engine)
    with patch("app.database.SessionLocal", TestSession):
        run_analysis(str(analysis.id), JIRA_URL, None, "test-pat",
                     "project = TEST", 5)

    db_session.expire_all()
    refreshed = db_session.query(Analysis).filter_by(id=analysis.id).first()
    assert refreshed.status == "completed", (
        f"Expected completed with keyword fallback, got {refreshed.status}: "
        f"{refreshed.error_message}"
    )
    clusters = db_session.query(Cluster).filter_by(analysis_id=analysis.id).all()
    for c in clusters:
        assert c.label  # keyword-derived labels still produced


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_pipeline_fails_gracefully_on_auth_error(test_engine, db_session):
    """If Jira returns 401, analysis.status should become 'failed'."""
    from sqlalchemy.orm import sessionmaker
    from app.models import Analysis
    from app.services.analysis import run_analysis

    rsps_lib.add(rsps_lib.GET, f"{JIRA_URL}/rest/api/3/search", status=401)
    rsps_lib.add(rsps_lib.GET, f"{JIRA_URL}/rest/api/2/search", status=401)

    analysis = Analysis(
        id=uuid.uuid4(), jira_url=JIRA_URL, jql_filter="project = TEST",
        num_clusters=3, status="pending", total_tickets=0,
    )
    db_session.add(analysis)
    db_session.commit()

    TestSession = sessionmaker(bind=test_engine)
    with patch("app.database.SessionLocal", TestSession):
        run_analysis(str(analysis.id), JIRA_URL, "user@example.com",
                     "bad-token", "project = TEST", 3)

    db_session.expire_all()
    refreshed = db_session.query(Analysis).filter_by(id=analysis.id).first()
    assert refreshed.status == "failed"
    assert refreshed.error_message


@rsps_lib.activate
def test_pipeline_fails_gracefully_on_empty_jql(test_engine, db_session):
    """If JQL returns no tickets, analysis should fail with a clear message."""
    from sqlalchemy.orm import sessionmaker
    from app.models import Analysis
    from app.services.analysis import run_analysis

    rsps_lib.add(
        rsps_lib.GET, f"{JIRA_URL}/rest/api/3/search",
        json={"total": 0, "startAt": 0, "maxResults": 100, "issues": []},
        status=200,
    )

    analysis = Analysis(
        id=uuid.uuid4(), jira_url=JIRA_URL, jql_filter="project = NONEXISTENT",
        num_clusters=3, status="pending", total_tickets=0,
    )
    db_session.add(analysis)
    db_session.commit()

    TestSession = sessionmaker(bind=test_engine)
    with patch("app.database.SessionLocal", TestSession):
        run_analysis(str(analysis.id), JIRA_URL, None, "tok",
                     "project = NONEXISTENT", 3)

    db_session.expire_all()
    refreshed = db_session.query(Analysis).filter_by(id=analysis.id).first()
    assert refreshed.status == "failed"
    assert "No tickets" in (refreshed.error_message or "")

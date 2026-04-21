"""Tests for the FastAPI REST endpoints.

Uses a real PostgreSQL testcontainer for the database and the `responses`
library to prevent any accidental outbound Jira HTTP calls.
"""
from __future__ import annotations

import uuid

import numpy as np
import pytest
import responses as rsps_lib

from tests.generators import generate_tickets, generate_jira_api_response

JIRA_URL = "https://jira.test"


@pytest.fixture(autouse=True)
def _disable_ollama_retry_sleep(monkeypatch):
    monkeypatch.setattr("app.services.ollama.time.sleep", lambda *_args, **_kwargs: None)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(test_client):
    resp = test_client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /api/analyses — validation
# ---------------------------------------------------------------------------

def test_create_analysis_missing_jira_url(test_client):
    resp = test_client.post(
        "/api/analyses",
        json={"pat": "tok", "jql_filter": "project=X", "num_clusters": 3},
    )
    assert resp.status_code == 422


def test_create_analysis_missing_pat(test_client):
    resp = test_client.post(
        "/api/analyses",
        json={"jira_url": JIRA_URL, "jql_filter": "project=X", "num_clusters": 3},
    )
    assert resp.status_code == 422


def test_create_analysis_num_clusters_too_low(test_client):
    resp = test_client.post(
        "/api/analyses",
        json={
            "jira_url": JIRA_URL,
            "pat": "tok",
            "jql_filter": "project=X",
            "num_clusters": 1,
        },
    )
    assert resp.status_code == 422


def test_create_analysis_num_clusters_too_high(test_client):
    resp = test_client.post(
        "/api/analyses",
        json={
            "jira_url": JIRA_URL,
            "pat": "tok",
            "jql_filter": "project=X",
            "num_clusters": 21,
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/analyses — happy path (background task runs inline with TestClient)
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_create_analysis_returns_201(test_client):
    """POST should immediately return 201 with status=pending."""
    # The background task will try to contact Jira; mock it out.
    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/3/search",
        json=generate_jira_api_response(generate_tickets()),
        status=200,
    )
    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/2/search",
        json=generate_jira_api_response(generate_tickets()),
        status=200,
    )

    resp = test_client.post(
        "/api/analyses",
        json={
            "jira_url": JIRA_URL,
            "username": "user@example.com",
            "pat": "test-token",
            "jql_filter": "project = TEST",
            "num_clusters": 5,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["jira_url"] == JIRA_URL
    assert body["jql_filter"] == "project = TEST"
    assert body["num_clusters"] == 5
    assert body["status"] in ("pending", "running", "completed")
    assert "status_detail" in body
    assert isinstance(body["progress_current"], int)
    assert isinstance(body["progress_total"], int)
    assert isinstance(body["progress_unit"], str)
    # PAT must never appear in the response
    assert "pat" not in body


# ---------------------------------------------------------------------------
# GET /api/analyses
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_list_analyses_returns_array(test_client):
    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/3/search",
        json=generate_jira_api_response(generate_tickets()),
        status=200,
    )
    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/2/search",
        json=generate_jira_api_response(generate_tickets()),
        status=200,
    )

    test_client.post(
        "/api/analyses",
        json={
            "jira_url": JIRA_URL,
            "pat": "tok",
            "jql_filter": "project = TEST",
            "num_clusters": 3,
        },
    )

    resp = test_client.get("/api/analyses")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) >= 1


# ---------------------------------------------------------------------------
# GET /api/analyses/{id}
# ---------------------------------------------------------------------------

def test_get_analysis_not_found(test_client):
    resp = test_client.get(f"/api/analyses/{uuid.uuid4()}")
    assert resp.status_code == 404


@rsps_lib.activate
def test_get_analysis_returns_analysis(test_client):
    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/3/search",
        json=generate_jira_api_response(generate_tickets()),
        status=200,
    )
    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/2/search",
        json=generate_jira_api_response(generate_tickets()),
        status=200,
    )

    create_resp = test_client.post(
        "/api/analyses",
        json={
            "jira_url": JIRA_URL,
            "pat": "tok",
            "jql_filter": "project = TEST",
            "num_clusters": 3,
        },
    )
    assert create_resp.status_code == 201
    analysis_id = create_resp.json()["id"]

    get_resp = test_client.get(f"/api/analyses/{analysis_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["id"] == analysis_id
    assert "status_detail" in body
    assert "progress_current" in body
    assert "progress_total" in body
    assert "progress_unit" in body


# ---------------------------------------------------------------------------
# DELETE /api/analyses/{id}
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_delete_analysis(test_client):
    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/3/search",
        json=generate_jira_api_response(generate_tickets()),
        status=200,
    )
    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/2/search",
        json=generate_jira_api_response(generate_tickets()),
        status=200,
    )

    create_resp = test_client.post(
        "/api/analyses",
        json={
            "jira_url": JIRA_URL,
            "pat": "tok",
            "jql_filter": "project = TEST",
            "num_clusters": 3,
        },
    )
    analysis_id = create_resp.json()["id"]

    del_resp = test_client.delete(f"/api/analyses/{analysis_id}")
    assert del_resp.status_code == 204

    get_resp = test_client.get(f"/api/analyses/{analysis_id}")
    assert get_resp.status_code == 404


def test_delete_analysis_not_found(test_client):
    resp = test_client.delete(f"/api/analyses/{uuid.uuid4()}")
    assert resp.status_code == 404


def _make_vector(x: float, y: float = 0.0) -> list[float]:
    from app.config import settings

    vec = [0.0] * settings.OLLAMA_EMBED_DIM
    vec[0] = x
    vec[1] = y
    return vec


def _seed_ticket_analysis(db_session):
    from app.models import Analysis, Cluster, Ticket

    analysis = Analysis(
        id=uuid.uuid4(),
        jira_url=JIRA_URL,
        jql_filter="project = TEST",
        num_clusters=2,
        status="completed",
        status_detail="Analysis completed",
        progress_current=2,
        progress_total=2,
        progress_unit="clusters",
        total_tickets=2,
    )
    db_session.add(analysis)
    db_session.add_all(
        [
            Cluster(
                analysis_id=analysis.id,
                cluster_number=0,
                label="Authentication Issues",
                ticket_count=1,
                keywords=["login"],
                representative_tickets=[{"key": "TEST-1", "summary": "User login fails"}],
            ),
            Cluster(
                analysis_id=analysis.id,
                cluster_number=1,
                label="Reporting Problems",
                ticket_count=1,
                keywords=["dashboard"],
                representative_tickets=[{"key": "TEST-2", "summary": "Dashboard export is blank"}],
            ),
            Ticket(
                analysis_id=analysis.id,
                jira_key="TEST-1",
                summary="User login fails after password reset",
                description="Users cannot sign in after a password reset flow.",
                issue_type="Bug",
                priority="High",
                ticket_status="To Do",
                cluster_id=0,
                embedding=_make_vector(1.0, 0.0),
            ),
            Ticket(
                analysis_id=analysis.id,
                jira_key="TEST-2",
                summary="Dashboard export generates blank CSV files",
                description="Exported reporting files are blank for finance users.",
                issue_type="Bug",
                priority="Medium",
                ticket_status="In Progress",
                cluster_id=1,
                embedding=_make_vector(0.0, 1.0),
            ),
        ]
    )
    db_session.commit()
    return analysis


def test_list_analysis_tickets_returns_ticket_page(test_client, db_session):
    analysis = _seed_ticket_analysis(db_session)

    resp = test_client.get(f"/api/analyses/{analysis.id}/tickets")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["limit"] == 20
    assert body["offset"] == 0
    assert body["query"] is None
    assert [item["jira_key"] for item in body["items"]] == ["TEST-1", "TEST-2"]
    assert body["items"][0]["cluster_label"] == "Authentication Issues"


def test_get_analysis_includes_progress_fields(test_client, db_session):
    analysis = _seed_ticket_analysis(db_session)

    resp = test_client.get(f"/api/analyses/{analysis.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["status_detail"] == "Analysis completed"
    assert body["progress_current"] == 2
    assert body["progress_total"] == 2
    assert body["progress_unit"] == "clusters"


def test_search_analysis_tickets_returns_semantic_matches(test_client, db_session, monkeypatch):
    analysis = _seed_ticket_analysis(db_session)

    def fake_generate_embeddings(texts):
        assert texts == ["login reset problems"]
        return np.array([_make_vector(1.0, 0.0)], dtype=np.float32)

    monkeypatch.setattr("app.routes.analyses.generate_embeddings", fake_generate_embeddings)

    resp = test_client.get(f"/api/analyses/{analysis.id}/tickets", params={"query": "login reset problems"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "login reset problems"
    assert body["items"][0]["jira_key"] == "TEST-1"
    assert body["items"][0]["similarity_score"] >= body["items"][1]["similarity_score"]


def test_get_analysis_ticket_returns_ticket_detail(test_client, db_session):
    analysis = _seed_ticket_analysis(db_session)

    resp = test_client.get(f"/api/analyses/{analysis.id}/tickets/by-key/TEST-2")
    assert resp.status_code == 200
    body = resp.json()
    assert body["jira_key"] == "TEST-2"
    assert body["cluster_label"] == "Reporting Problems"
    assert body["jira_issue_url"] == f"{JIRA_URL}/browse/TEST-2"


def test_get_analysis_ticket_not_found(test_client, db_session):
    analysis = _seed_ticket_analysis(db_session)

    resp = test_client.get(f"/api/analyses/{analysis.id}/tickets/by-key/TEST-999")
    assert resp.status_code == 404

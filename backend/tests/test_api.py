"""Tests for the FastAPI REST endpoints.

Uses a real PostgreSQL testcontainer for the database and the `responses`
library to prevent any accidental outbound Jira HTTP calls.
"""
from __future__ import annotations

import uuid

import pytest
import responses as rsps_lib

from tests.generators import generate_tickets, generate_jira_api_response

JIRA_URL = "https://jira.test"


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
    assert get_resp.json()["id"] == analysis_id


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

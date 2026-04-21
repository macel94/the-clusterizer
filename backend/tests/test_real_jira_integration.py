from __future__ import annotations

import os
from unittest.mock import patch

import numpy as np
import pytest

from app.services.jira import JiraService

pytestmark = pytest.mark.real_jira


def _real_jira_enabled() -> bool:
    return os.getenv("RUN_REAL_JIRA_TESTS") == "1"


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _fake_embeddings(texts):
    from app.config import settings

    rng = np.random.default_rng(seed=42)
    return rng.standard_normal((len(texts), settings.OLLAMA_EMBED_DIM)).astype(np.float32)


@pytest.mark.skipif(not _real_jira_enabled(), reason="real Jira tests are disabled")
def test_real_jira_service_fetches_seeded_issues():
    jira = JiraService(
        _require_env("REAL_JIRA_URL"),
        _require_env("REAL_JIRA_USERNAME"),
        _require_env("REAL_JIRA_PASSWORD"),
    )

    tickets = jira.fetch_tickets(_require_env("REAL_JIRA_JQL"))

    assert len(tickets) >= 6
    assert any("Login" in ticket["summary"] for ticket in tickets)
    assert any("Dashboard" in ticket["summary"] for ticket in tickets)


@pytest.mark.skipif(not _real_jira_enabled(), reason="real Jira tests are disabled")
@patch("app.services.analysis.generate_cluster_label", return_value="Real Jira Cluster")
@patch("app.services.analysis.generate_embeddings", side_effect=_fake_embeddings)
def test_real_jira_analysis_completes_via_api(mock_embeddings, mock_label, test_client):
    response = test_client.post(
        "/api/analyses",
        json={
            "jira_url": _require_env("REAL_JIRA_URL"),
            "username": _require_env("REAL_JIRA_USERNAME"),
            "pat": _require_env("REAL_JIRA_PASSWORD"),
            "jql_filter": _require_env("REAL_JIRA_JQL"),
            "num_clusters": 3,
        },
    )

    assert response.status_code == 201
    analysis_id = response.json()["id"]

    result = test_client.get(f"/api/analyses/{analysis_id}")
    assert result.status_code == 200

    body = result.json()
    assert body["status"] == "completed"
    assert body["total_tickets"] >= 6
    assert len(body["clusters"]) >= 1
    assert all(cluster["label"] for cluster in body["clusters"])

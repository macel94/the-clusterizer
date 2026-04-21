"""Unit tests for the Jira REST client.

HTTP calls are intercepted with the *responses* library so no real Jira
instance is required.
"""
from __future__ import annotations

import pytest
import responses as rsps_lib

from app.services.jira import JiraService, JiraAuthError
from tests.generators import generate_tickets, generate_jira_api_response

JIRA_URL = "https://jira.example.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(username: str = "user@example.com", pat: str = "token") -> JiraService:
    return JiraService(JIRA_URL, username, pat)


# ---------------------------------------------------------------------------
# Basic fetch
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_fetch_tickets_returns_all_tickets():
    tickets = generate_tickets()
    payload = generate_jira_api_response(tickets)

    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/3/search",
        json=payload,
        status=200,
    )

    svc = _make_service()
    result = svc.fetch_tickets("project = TEST")

    assert len(result) == len(tickets)


@rsps_lib.activate
def test_fetch_tickets_fields_mapped_correctly():
    tickets = generate_tickets()[:1]
    payload = generate_jira_api_response(tickets)

    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/3/search",
        json=payload,
        status=200,
    )

    svc = _make_service()
    result = svc.fetch_tickets("project = TEST")

    assert result[0]["key"] == tickets[0]["key"]
    assert result[0]["summary"] == tickets[0]["summary"]
    assert result[0]["issue_type"] == tickets[0]["issue_type"]
    assert result[0]["priority"] == tickets[0]["priority"]
    assert result[0]["status"] == tickets[0]["status"]


# ---------------------------------------------------------------------------
# API version fallback (v3 → v2)
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_fetch_tickets_falls_back_to_api_v2():
    """If v3 endpoint returns 404, the client should retry against v2."""
    tickets = generate_tickets()[:5]
    payload = generate_jira_api_response(tickets)

    # v3 returns 404
    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/3/search",
        status=404,
    )
    # v2 succeeds
    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/2/search",
        json=payload,
        status=200,
    )

    svc = _make_service()
    result = svc.fetch_tickets("project = TEST")
    assert len(result) == len(tickets)


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_fetch_tickets_paginates_correctly():
    """Tickets spread across two pages should all be returned."""
    all_tickets = generate_tickets()
    page1_tickets = all_tickets[:20]
    page2_tickets = all_tickets[20:]

    page1 = generate_jira_api_response(page1_tickets, start_at=0)
    page1["total"] = len(all_tickets)
    page1["maxResults"] = 20

    page2 = generate_jira_api_response(page2_tickets, start_at=20)
    page2["total"] = len(all_tickets)
    page2["maxResults"] = 20

    rsps_lib.add(rsps_lib.GET, f"{JIRA_URL}/rest/api/3/search", json=page1, status=200)
    rsps_lib.add(rsps_lib.GET, f"{JIRA_URL}/rest/api/3/search", json=page2, status=200)

    svc = _make_service()
    result = svc.fetch_tickets("project = TEST", max_results=1000)

    assert len(result) == len(all_tickets)


@rsps_lib.activate
def test_fetch_tickets_stops_when_no_issues_returned():
    """Empty issues list should terminate pagination early."""
    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/3/search",
        json={"total": 100, "startAt": 0, "maxResults": 0, "issues": []},
        status=200,
    )

    svc = _make_service()
    result = svc.fetch_tickets("project = TEST")
    assert result == []


# ---------------------------------------------------------------------------
# Auth errors
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_raises_auth_error_on_401():
    rsps_lib.add(rsps_lib.GET, f"{JIRA_URL}/rest/api/3/search", status=401)
    rsps_lib.add(rsps_lib.GET, f"{JIRA_URL}/rest/api/2/search", status=401)

    svc = _make_service()
    with pytest.raises(JiraAuthError, match="Authentication failed"):
        svc.fetch_tickets("project = TEST")


@rsps_lib.activate
def test_raises_auth_error_on_403():
    rsps_lib.add(rsps_lib.GET, f"{JIRA_URL}/rest/api/3/search", status=403)
    rsps_lib.add(rsps_lib.GET, f"{JIRA_URL}/rest/api/2/search", status=403)

    svc = _make_service()
    with pytest.raises(JiraAuthError, match="Access forbidden"):
        svc.fetch_tickets("project = TEST")


# ---------------------------------------------------------------------------
# Connection error
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_raises_connection_error_when_host_unreachable():
    import requests as req_lib

    rsps_lib.add(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/3/search",
        body=req_lib.exceptions.ConnectionError("Connection refused"),
    )

    svc = _make_service()
    with pytest.raises(ConnectionError, match="Could not connect"):
        svc.fetch_tickets("project = TEST")


# ---------------------------------------------------------------------------
# Bearer token (Server / Data Center)
# ---------------------------------------------------------------------------

@rsps_lib.activate
def test_bearer_token_used_when_no_username():
    """When username is omitted, Authorization: Bearer header is sent."""
    tickets = generate_tickets()[:3]
    payload = generate_jira_api_response(tickets)

    def _check_auth(request):
        assert request.headers.get("Authorization", "").startswith("Bearer ")
        return (200, {}, __import__("json").dumps(payload))

    rsps_lib.add_callback(
        rsps_lib.GET,
        f"{JIRA_URL}/rest/api/3/search",
        callback=_check_auth,
        content_type="application/json",
    )

    svc = JiraService(JIRA_URL, username=None, pat="my-pat")
    result = svc.fetch_tickets("project = TEST")
    assert len(result) == len(tickets)


# ---------------------------------------------------------------------------
# ADF description extraction
# ---------------------------------------------------------------------------

def test_extract_text_from_adf_simple():
    svc = _make_service()
    adf = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "text", "text": " world"},
                ],
            }
        ],
    }
    result = svc._extract_text_from_adf(adf)
    assert "Hello" in result
    assert "world" in result


def test_extract_text_from_adf_nested():
    svc = _make_service()
    adf = {
        "type": "doc",
        "content": [
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Item one"}],
                            }
                        ],
                    }
                ],
            }
        ],
    }
    result = svc._extract_text_from_adf(adf)
    assert "Item one" in result


def test_extract_text_from_adf_returns_empty_for_non_dict():
    svc = _make_service()
    assert svc._extract_text_from_adf("plain string") == ""
    assert svc._extract_text_from_adf(None) == ""

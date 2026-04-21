import logging
from typing import List, Dict, Optional

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

_CLOUD_SEARCH_PATH = "/rest/api/3/search/jql"
_LEGACY_SEARCH_PATHS = ["/rest/api/3/search", "/rest/api/2/search"]
_SEARCH_FIELDS = ["summary", "description", "issuetype", "priority", "status"]


class JiraAuthError(Exception):
    pass


class JiraService:
    def __init__(self, base_url: str, username: Optional[str], pat: str):
        self.base_url = base_url.rstrip("/")
        self.is_cloud = bool(username)
        if username:
            self.auth = HTTPBasicAuth(username, pat)
            self.headers = {"Accept": "application/json"}
        else:
            # Personal Access Token (Bearer) — used for Server / Data Center
            self.auth = None
            self.headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {pat}",
            }

    def _request(self, method: str, path: str, *, params: Optional[dict] = None, json: Optional[dict] = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(
                method,
                url,
                params=params,
                json=json,
                headers=self.headers,
                auth=self.auth,
                timeout=30,
                verify=True,
            )
        except requests.exceptions.ConnectionError as exc:
            raise ConnectionError(
                f"Could not connect to Jira at {self.base_url}. "
                "Please check the URL."
            ) from exc

        if resp.status_code == 401:
            raise JiraAuthError(
                "Authentication failed. Check your username and API token."
            )
        if resp.status_code == 403:
            raise JiraAuthError(
                "Access forbidden. Your token may lack the required permissions."
            )

        resp.raise_for_status()
        return resp.json()

    def _search_cloud_page(self, jql: str, max_results: int, next_page_token: Optional[str] = None) -> dict:
        payload = {
            "jql": jql,
            "maxResults": max_results,
            "fields": _SEARCH_FIELDS,
        }
        if next_page_token:
            payload["nextPageToken"] = next_page_token
        return self._request("POST", _CLOUD_SEARCH_PATH, json=payload)

    def _search_legacy_page(self, jql: str, start_at: int, max_results: int) -> dict:
        params = {
            "jql": jql,
            "startAt": start_at,
            "maxResults": max_results,
            "fields": _SEARCH_FIELDS,
        }

        last_exc: Exception = RuntimeError("No Jira legacy search endpoint tried")
        for path in _LEGACY_SEARCH_PATHS:
            try:
                return self._request("GET", path, params=params)
            except JiraAuthError:
                raise
            except requests.exceptions.HTTPError as exc:
                last_exc = exc
                continue

        raise last_exc

    def _fetch_tickets_cloud(self, jql: str, max_results: int) -> List[Dict]:
        tickets: List[Dict] = []
        next_page_token: Optional[str] = None
        batch_size = 100

        while len(tickets) < max_results:
            remaining = min(batch_size, max_results - len(tickets))
            data = self._search_cloud_page(jql, remaining, next_page_token)
            issues = data.get("issues", [])
            if not issues:
                break

            for issue in issues:
                fields = issue.get("fields", {})
                description = fields.get("description", "") or ""
                if isinstance(description, dict):
                    description = self._extract_text_from_adf(description)

                tickets.append(
                    {
                        "key": issue["key"],
                        "summary": fields.get("summary") or "",
                        "description": description,
                        "issue_type": (
                            fields.get("issuetype", {}).get("name", "")
                            if fields.get("issuetype")
                            else ""
                        ),
                        "priority": (
                            fields.get("priority", {}).get("name", "")
                            if fields.get("priority")
                            else ""
                        ),
                        "status": (
                            fields.get("status", {}).get("name", "")
                            if fields.get("status")
                            else ""
                        ),
                    }
                )

            if data.get("isLast"):
                break

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

        return tickets

    def _fetch_tickets_legacy(self, jql: str, max_results: int) -> List[Dict]:
        tickets: List[Dict] = []
        start_at = 0
        batch_size = 100

        while len(tickets) < max_results:
            remaining = min(batch_size, max_results - len(tickets))
            data = self._search_legacy_page(jql, start_at, remaining)
            issues = data.get("issues", [])
            if not issues:
                break

            for issue in issues:
                fields = issue.get("fields", {})
                description = fields.get("description", "") or ""
                if isinstance(description, dict):
                    description = self._extract_text_from_adf(description)

                tickets.append(
                    {
                        "key": issue["key"],
                        "summary": fields.get("summary") or "",
                        "description": description,
                        "issue_type": (
                            fields.get("issuetype", {}).get("name", "")
                            if fields.get("issuetype")
                            else ""
                        ),
                        "priority": (
                            fields.get("priority", {}).get("name", "")
                            if fields.get("priority")
                            else ""
                        ),
                        "status": (
                            fields.get("status", {}).get("name", "")
                            if fields.get("status")
                            else ""
                        ),
                    }
                )

            start_at += len(issues)
            total = data.get("total", 0)
            if start_at >= total:
                break

        return tickets

    def fetch_tickets(self, jql: str, max_results: int = 1000) -> List[Dict]:
        if self.is_cloud:
            try:
                return self._fetch_tickets_cloud(jql, max_results)
            except requests.exceptions.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code not in {404, 405, 410, 501}:
                    raise
                logger.info(
                    "Falling back to legacy Jira search endpoints after %s from %s",
                    status_code,
                    _CLOUD_SEARCH_PATH,
                )

        return self._fetch_tickets_legacy(jql, max_results)

    def _extract_text_from_adf(self, node) -> str:
        """Recursively extract plain text from Atlassian Document Format."""
        if not isinstance(node, dict):
            return ""
        if node.get("type") == "text":
            return node.get("text", "")
        parts = [self._extract_text_from_adf(child) for child in node.get("content", [])]
        return " ".join(p for p in parts if p)

import logging
from typing import List, Dict, Optional

import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)

_API_VERSIONS = ["/rest/api/3/search", "/rest/api/2/search"]


class JiraAuthError(Exception):
    pass


class JiraService:
    def __init__(self, base_url: str, username: Optional[str], pat: str):
        self.base_url = base_url.rstrip("/")
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

    def _get(self, path: str, params: dict) -> dict:
        """GET with automatic API version fallback (v3 → v2)."""
        last_exc: Exception = RuntimeError("No API endpoint tried")
        for version in _API_VERSIONS:
            url = f"{self.base_url}{version}"
            try:
                resp = requests.get(
                    url,
                    params=params,
                    headers=self.headers,
                    auth=self.auth,
                    timeout=30,
                    verify=True,
                )
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
            except JiraAuthError:
                raise
            except requests.exceptions.HTTPError as exc:
                last_exc = exc
                continue
            except requests.exceptions.ConnectionError as exc:
                raise ConnectionError(
                    f"Could not connect to Jira at {self.base_url}. "
                    "Please check the URL."
                ) from exc
        raise last_exc

    def fetch_tickets(self, jql: str, max_results: int = 1000) -> List[Dict]:
        tickets: List[Dict] = []
        start_at = 0
        batch_size = 100

        while len(tickets) < max_results:
            remaining = min(batch_size, max_results - len(tickets))
            data = self._get(
                "/search",
                {
                    "jql": jql,
                    "startAt": start_at,
                    "maxResults": remaining,
                    "fields": "summary,description,issuetype,priority,status",
                },
            )
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

    def _extract_text_from_adf(self, node) -> str:
        """Recursively extract plain text from Atlassian Document Format."""
        if not isinstance(node, dict):
            return ""
        if node.get("type") == "text":
            return node.get("text", "")
        parts = [self._extract_text_from_adf(child) for child in node.get("content", [])]
        return " ".join(p for p in parts if p)

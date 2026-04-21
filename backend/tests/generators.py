"""Synthetic Jira ticket data generator.

Creates realistic-looking Jira tickets grouped into thematic clusters so that
the clustering pipeline can be exercised and validated in tests.
"""
from __future__ import annotations

import uuid
from typing import List, Dict

# ---------------------------------------------------------------------------
# Ticket templates organised by cluster theme
# ---------------------------------------------------------------------------
_CLUSTER_TEMPLATES: List[Dict] = [
    # ── Cluster A: Authentication / Login ────────────────────────────────
    {
        "issue_type": "Bug",
        "priority": "High",
        "status": "Open",
        "tickets": [
            ("AUTH-1",  "Login page returns 500 for passwords with special characters",
             "Users report that logging in with passwords containing @, #, or ! triggers a 500 error. "
             "Stack-trace shows NullPointerException in AuthController.login()."),
            ("AUTH-2",  "SSO redirect loop after SAML assertion",
             "After successful SAML assertion, the service provider redirects the user back to the "
             "identity provider in an infinite loop. Seen with Okta and Azure AD."),
            ("AUTH-3",  "Remember-me token not invalidated on logout",
             "The persistent authentication cookie is not cleared server-side when the user logs out. "
             "Revisiting the site within the token TTL re-authenticates without prompting."),
            ("AUTH-4",  "Password reset email not delivered when username has uppercase letters",
             "The password-reset flow lowercases the stored email before querying but not the lookup "
             "key, causing a miss and no email delivery."),
            ("AUTH-5",  "Session expires too quickly under heavy load",
             "Under high concurrency the session store TTL renewal is skipped, causing users to be "
             "logged out after ~5 minutes instead of the configured 30 minutes."),
            ("AUTH-6",  "OAuth2 PKCE flow fails on Safari 17",
             "The code-verifier is not correctly percent-encoded on Safari 17. "
             "Authorization code exchange returns invalid_grant."),
            ("AUTH-7",  "Two-factor authentication bypass via direct URL access",
             "A user who has 2FA enabled can skip the verification step by navigating directly to "
             "the post-login URL. The middleware guard is missing on those routes."),
            ("AUTH-8",  "LDAP authentication fails when DN contains comma",
             "Distinguished names that include a comma (e.g. OU=Sales, Inc) break the LDAP bind call "
             "because the DN is not properly escaped."),
        ],
    },
    # ── Cluster B: Performance / Slowness ────────────────────────────────
    {
        "issue_type": "Bug",
        "priority": "Medium",
        "status": "In Progress",
        "tickets": [
            ("PERF-1", "Dashboard takes >10 seconds to load for accounts with >500 projects",
             "The project list query performs N+1 selects against the permissions table. "
             "Adding an eager-load join should fix this."),
            ("PERF-2", "Search results timeout for queries with more than 3 filter criteria",
             "ElasticSearch queries with compound filters time out after 5 s. "
             "Query planning shows missing composite index on (status, priority, assignee)."),
            ("PERF-3", "PDF export hangs when report contains more than 200 rows",
             "The PDF renderer loads all rows into memory at once. "
             "Streaming or pagination is required to prevent OOM and timeout."),
            ("PERF-4", "API response time degrades linearly with number of open issues",
             "The /api/issues endpoint re-counts total open issues on every request. "
             "Caching the count or using a materialized view would improve latency."),
            ("PERF-5", "Slow startup time when connection pool is exhausted",
             "If all database connections are occupied during application startup, "
             "the health-check endpoint times out and Kubernetes restarts the pod unnecessarily."),
            ("PERF-6", "Bulk import endpoint blocks the event loop for >30 seconds",
             "CSV import is processed synchronously in the request handler. "
             "Moving it to a background task queue would unblock the worker."),
            ("PERF-7", "Notification fan-out causes latency spikes during peak hours",
             "Sending notifications to all project members is done synchronously in a loop. "
             "At peak, 800+ notifications block the worker thread for 45 seconds."),
            ("PERF-8", "Autocomplete suggestions lag by 2-3 seconds on slow networks",
             "The autocomplete widget waits for the full response before rendering. "
             "Streaming or progressive rendering would improve perceived performance."),
        ],
    },
    # ── Cluster C: UI / Frontend ─────────────────────────────────────────
    {
        "issue_type": "Bug",
        "priority": "Low",
        "status": "Open",
        "tickets": [
            ("UI-1",  "Dropdown menu overflows viewport on mobile screens",
             "On viewports narrower than 375px the dropdown overflows to the right. "
             "Adding overflow-x: hidden and a max-width constraint fixes the issue."),
            ("UI-2",  "Dark mode toggle resets to light mode after page refresh",
             "The user preference is stored only in React state and not persisted to localStorage. "
             "After a hard refresh the theme reverts to the default."),
            ("UI-3",  "Table column resizing broken in Firefox 120",
             "The drag-to-resize handler uses a deprecated Mouse-Events API that Firefox 120 removed. "
             "PointerEvents API should be used instead."),
            ("UI-4",  "Tooltip z-index conflicts with modal overlay",
             "When a tooltip is triggered inside a modal, it renders behind the overlay backdrop "
             "due to a lower z-index stacking context."),
            ("UI-5",  "File upload button not accessible via keyboard navigation",
             "The custom file-input widget suppresses the native focus ring and has no tabindex, "
             "making it unreachable without a mouse."),
            ("UI-6",  "Date picker shows incorrect month when locale uses non-Gregorian calendar",
             "The date-picker component assumes the Gregorian calendar. "
             "Persian and Hebrew locales display the wrong month header."),
            ("UI-7",  "Sidebar layout breaks when browser zoom is set to 150%",
             "At 150% zoom the CSS grid overflows and the main content panel is hidden "
             "behind the sidebar."),
            ("UI-8",  "Icon buttons missing aria-label causing screen-reader issues",
             "Buttons that display only an icon have no accessible name. "
             "Screen readers announce them as unlabelled, failing WCAG 2.1 AA."),
        ],
    },
    # ── Cluster D: Backend / Database errors ─────────────────────────────
    {
        "issue_type": "Bug",
        "priority": "Critical",
        "status": "Open",
        "tickets": [
            ("DB-1",  "Foreign key violation on concurrent ticket creation",
             "Under concurrent load two requests try to insert a ticket with the same parent_id. "
             "One succeeds, the other raises a foreign-key constraint error because the parent was "
             "not yet committed."),
            ("DB-2",  "Migration fails on PostgreSQL 18 due to reserved keyword",
             "Column named 'value' was reserved in PostgreSQL 18. "
             "ALTER TABLE rename is needed before running migration 0043."),
            ("DB-3",  "Deadlock detected when bulk-updating issue statuses",
             "Two background jobs update overlapping sets of issues in opposite order, "
             "causing a deadlock. Using SELECT ... FOR UPDATE with a consistent ordering fixes this."),
            ("DB-4",  "Connection pool exhausted after failed transaction rollback",
             "If an exception occurs mid-transaction and the rollback is not called, "
             "the connection is returned in a dirty state and eventually exhausts the pool."),
            ("DB-5",  "Full-text search index not updated after issue rename",
             "The tsvector index on the issues table is populated via a trigger that fires only on "
             "INSERT, not on UPDATE. Renaming an issue makes the old title searchable."),
            ("DB-6",  "Cascade delete removes child records before parent audit log is written",
             "The ON DELETE CASCADE constraint fires before the audit trigger, "
             "resulting in orphaned audit entries that reference deleted rows."),
            ("DB-7",  "JSONB query fails with parse error for null values in nested objects",
             "The jsonb_path_query function returns an error when traversing a path that contains "
             "null mid-level nodes. Explicit null checks are required."),
            ("DB-8",  "Slow query plan chosen for paginated results with large offsets",
             "OFFSET-based pagination on the issues table degrades to sequential scan after page 50. "
             "Keyset pagination (WHERE id > last_seen_id) would maintain consistent performance."),
        ],
    },
    # ── Cluster E: Feature Requests / Improvements ───────────────────────
    {
        "issue_type": "Story",
        "priority": "Medium",
        "status": "Backlog",
        "tickets": [
            ("FEAT-1", "Add bulk label assignment from issue list view",
             "Users want to select multiple issues and apply or remove labels in one action "
             "without opening each issue individually."),
            ("FEAT-2", "Implement Slack integration for issue notifications",
             "Teams want to receive create/update/close notifications in a designated Slack channel. "
             "The integration should support per-project channel configuration."),
            ("FEAT-3", "Support custom fields in CSV export",
             "The CSV export currently only includes built-in fields. "
             "Users want to include custom fields and choose column order."),
            ("FEAT-4", "Add issue dependency graph visualization",
             "Product managers want a visual graph showing blocking/blocked-by relationships "
             "between issues, similar to a dependency map."),
            ("FEAT-5", "Implement SLA tracking for customer-reported issues",
             "Support teams need automatic SLA timers that trigger escalation emails when "
             "response or resolution deadlines are approaching."),
            ("FEAT-6", "Allow markdown in issue descriptions",
             "Currently only plain text is supported. Teams want to use **bold**, *italic*, "
             "code blocks, and bullet lists in issue descriptions."),
            ("FEAT-7", "Add recurring issue templates for weekly maintenance tasks",
             "DevOps teams create the same maintenance tasks every week. "
             "A scheduling feature that auto-creates issues from templates would save time."),
            ("FEAT-8", "Provide REST API endpoint for issue analytics",
             "Data teams want to pull issue metrics (created vs closed, average age, "
             "throughput by team) via API instead of using the UI reports."),
        ],
    },
]


def generate_tickets() -> List[Dict]:
    """Return a flat list of synthetic Jira ticket dicts."""
    tickets = []
    for cluster in _CLUSTER_TEMPLATES:
        for key, summary, description in cluster["tickets"]:
            tickets.append(
                {
                    "key": key,
                    "summary": summary,
                    "description": description,
                    "issue_type": cluster["issue_type"],
                    "priority": cluster["priority"],
                    "status": cluster["status"],
                }
            )
    return tickets


def generate_jira_api_response(tickets: List[Dict], start_at: int = 0) -> Dict:
    """Wrap tickets in the shape of a Jira search API response."""
    issues = []
    for t in tickets:
        issues.append(
            {
                "id": str(uuid.uuid4()),
                "key": t["key"],
                "fields": {
                    "summary": t["summary"],
                    "description": t["description"],
                    "issuetype": {"name": t["issue_type"]},
                    "priority": {"name": t["priority"]},
                    "status": {"name": t["status"]},
                },
            }
        )
    return {
        "total": len(issues),
        "startAt": start_at,
        "maxResults": len(issues),
        "issues": issues,
    }

"""
GitHub Tool - Retrieves issues, PRs, and commit data.
Uses real GitHub API if GITHUB_TOKEN is set, otherwise mocks.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .registry import BaseTool, ToolResult

GITHUB_API = "https://api.github.com"


class GitHubTool(BaseTool):
    name = "github"
    description = "Search GitHub issues, pull requests, and commits in your organization"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search_issues", "get_issue", "list_prs", "search_commits"],
                "description": "Action to perform",
            },
            "query": {"type": "string", "description": "Search query"},
            "repo": {"type": "string", "description": "Repository name (owner/repo)"},
            "days": {"type": "integer", "description": "Number of days back to search"},
            "state": {"type": "string", "enum": ["open", "closed", "all"]},
            "labels": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["action"],
    }

    def __init__(self):
        self.token = os.getenv("GITHUB_TOKEN", "")
        self.org = os.getenv("GITHUB_ORG", "my-org")
        self._use_mock = not self.token

    async def run(self, action: str, **kwargs) -> ToolResult:
        if self._use_mock:
            return await self._mock_run(action, **kwargs)
        return await self._real_run(action, **kwargs)

    async def _real_run(self, action: str, **kwargs) -> ToolResult:
        headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json",
        }
        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            if action == "search_issues":
                return await self._search_issues(client, **kwargs)
            elif action == "get_issue":
                return await self._get_issue(client, **kwargs)
            elif action == "list_prs":
                return await self._list_prs(client, **kwargs)
            else:
                return ToolResult(tool_name=self.name, success=False, data=None, error=f"Unknown action: {action}")

    async def _search_issues(self, client: httpx.AsyncClient, query: str = "", days: int = 30, repo: str = "", state: str = "open", **kwargs) -> ToolResult:
        since = (datetime.now(tz=timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        q = f"{query} created:>={since} state:{state}"
        if repo:
            q += f" repo:{repo}"
        elif self.org:
            q += f" org:{self.org}"

        resp = await client.get(f"{GITHUB_API}/search/issues", params={"q": q, "per_page": 20})
        resp.raise_for_status()
        data = resp.json()

        issues = []
        for item in data.get("items", []):
            issues.append({
                "number": item["number"],
                "title": item["title"],
                "state": item["state"],
                "url": item["html_url"],
                "created_at": item["created_at"],
                "labels": [l["name"] for l in item.get("labels", [])],
                "body_preview": (item.get("body") or "")[:200],
            })

        return ToolResult(tool_name=self.name, success=True, data=issues, metadata={"total": data.get("total_count", 0)})

    async def _get_issue(self, client, repo: str, number: int, **kwargs) -> ToolResult:
        resp = await client.get(f"{GITHUB_API}/repos/{repo}/issues/{number}")
        resp.raise_for_status()
        return ToolResult(tool_name=self.name, success=True, data=resp.json())

    async def _list_prs(self, client, repo: str = "", state: str = "open", **kwargs) -> ToolResult:
        target = repo or f"{self.org}/main"
        resp = await client.get(f"{GITHUB_API}/repos/{target}/pulls", params={"state": state, "per_page": 10})
        resp.raise_for_status()
        return ToolResult(tool_name=self.name, success=True, data=resp.json())

    async def _mock_run(self, action: str, query: str = "", days: int = 30, **kwargs) -> ToolResult:
        """Return realistic mock data for demos without API token."""
        mock_issues = [
            {
                "number": 1042,
                "title": "Authentication tokens expire prematurely during peak load",
                "state": "open",
                "url": "https://github.com/my-org/backend/issues/1042",
                "created_at": (datetime.now(tz=timezone.utc) - timedelta(days=3)).isoformat(),
                "labels": ["bug", "authentication", "high-priority"],
                "body_preview": "Users report being logged out unexpectedly when traffic spikes. JWT expiry appears to be misconfigured under high concurrency...",
            },
            {
                "number": 1038,
                "title": "Login fails for users with SSO enabled intermittently",
                "state": "open",
                "url": "https://github.com/my-org/backend/issues/1038",
                "created_at": (datetime.now(tz=timezone.utc) - timedelta(days=7)).isoformat(),
                "labels": ["bug", "authentication", "sso"],
                "body_preview": "SSO callback URL is occasionally returning 404. Seems to be a race condition in session initialization...",
            },
            {
                "number": 1027,
                "title": "Password reset emails not being delivered",
                "state": "open",
                "url": "https://github.com/my-org/backend/issues/1027",
                "created_at": (datetime.now(tz=timezone.utc) - timedelta(days=12)).isoformat(),
                "labels": ["bug", "email", "authentication"],
                "body_preview": "SMTP service failing silently. No error logged. Users not receiving reset emails for 2+ days...",
            },
            {
                "number": 1019,
                "title": "Rate limiting on /auth/token endpoint too aggressive",
                "state": "open",
                "url": "https://github.com/my-org/backend/issues/1019",
                "created_at": (datetime.now(tz=timezone.utc) - timedelta(days=18)).isoformat(),
                "labels": ["enhancement", "authentication", "performance"],
                "body_preview": "Legitimate mobile clients are getting 429 errors due to token refresh patterns...",
            },
            {
                "number": 1011,
                "title": "CSRF tokens not validated on /api/auth/refresh",
                "state": "open",
                "url": "https://github.com/my-org/backend/issues/1011",
                "created_at": (datetime.now(tz=timezone.utc) - timedelta(days=25)).isoformat(),
                "labels": ["security", "authentication"],
                "body_preview": "Security audit found that refresh endpoint accepts requests without CSRF header...",
            },
        ]

        if query:
            filtered = [i for i in mock_issues if any(
                kw.lower() in i["title"].lower() or kw.lower() in i["body_preview"].lower()
                for kw in query.split()
            )]
        else:
            filtered = mock_issues

        filtered = [i for i in filtered if
            (datetime.now(tz=timezone.utc) - datetime.fromisoformat(i["created_at"])).days <= days]

        return ToolResult(
            tool_name=self.name,
            success=True,
            data=filtered,
            metadata={"total": len(filtered), "mock": True},
        )

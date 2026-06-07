"""
Slack Tool - Retrieve messages, thread summaries.
Uses real Slack API if SLACK_BOT_TOKEN is set, otherwise mocks.
"""

import os
from datetime import datetime, timedelta, timezone

import httpx

from .registry import BaseTool, ToolResult

SLACK_API = "https://slack.com/api"


class SlackTool(BaseTool):
    name = "slack"
    description = "Search Slack channels for messages, incidents, and discussions"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["search_messages", "get_channel_history", "get_thread"],
                "description": "Action to perform",
            },
            "query": {"type": "string", "description": "Search query"},
            "channel": {"type": "string", "description": "Channel name (without #)"},
            "days": {"type": "integer", "description": "Days back to search"},
        },
        "required": ["action"],
    }

    def __init__(self):
        self.token = os.getenv("SLACK_BOT_TOKEN", "")
        self._use_mock = not self.token

    async def run(self, action: str, **kwargs) -> ToolResult:
        if self._use_mock:
            return await self._mock_run(action, **kwargs)
        return await self._real_run(action, **kwargs)

    async def _real_run(self, action: str, query: str = "", channel: str = "", days: int = 7, **kwargs) -> ToolResult:
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(headers=headers, timeout=30) as client:
            if action == "search_messages":
                resp = await client.get(f"{SLACK_API}/search.messages", params={"query": query, "count": 20})
                data = resp.json()
                if not data.get("ok"):
                    return ToolResult(tool_name=self.name, success=False, data=None, error=data.get("error"))
                messages = [
                    {"text": m["text"], "user": m.get("username", ""), "ts": m["ts"], "channel": m.get("channel", {}).get("name", "")}
                    for m in data["messages"]["matches"]
                ]
                return ToolResult(tool_name=self.name, success=True, data=messages)
            else:
                return ToolResult(tool_name=self.name, success=False, data=None, error=f"Unsupported action: {action}")

    async def _mock_run(self, action: str, query: str = "", channel: str = "incidents", **kwargs) -> ToolResult:
        mock_messages = [
            {
                "text": "🚨 Auth service down - users can't login. Rolling back last deploy.",
                "user": "alice",
                "channel": "incidents",
                "ts": (datetime.now(tz=timezone.utc) - timedelta(hours=6)).isoformat(),
            },
            {
                "text": "Investigation: login failures correlating with Redis cache evictions. Cache hit rate dropped to 12%.",
                "user": "bob",
                "channel": "incidents",
                "ts": (datetime.now(tz=timezone.utc) - timedelta(hours=5, minutes=30)).isoformat(),
            },
            {
                "text": "Root cause: JWT signing key rotation wasn't propagated to all pod instances. Fix deployed to staging.",
                "user": "charlie",
                "channel": "engineering",
                "ts": (datetime.now(tz=timezone.utc) - timedelta(hours=4)).isoformat(),
            },
            {
                "text": "Post-mortem scheduled for tomorrow 10am. Auth service fully recovered. 847 users affected.",
                "user": "alice",
                "channel": "incidents",
                "ts": (datetime.now(tz=timezone.utc) - timedelta(hours=3)).isoformat(),
            },
        ]

        if query:
            filtered = [m for m in mock_messages if query.lower() in m["text"].lower()]
        elif channel:
            filtered = [m for m in mock_messages if m["channel"] == channel]
        else:
            filtered = mock_messages

        return ToolResult(tool_name=self.name, success=True, data=filtered, metadata={"mock": True})

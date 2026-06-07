"""
Database Tool - Safe read-only database introspection and querying.
"""

import os
from .registry import BaseTool, ToolResult


class DatabaseTool(BaseTool):
    name = "database"
    description = "Inspect database schema and run read-only queries for analysis"
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_tables", "describe_table", "query"],
            },
            "table": {"type": "string"},
            "sql": {"type": "string", "description": "Read-only SQL query (SELECT only)"},
        },
        "required": ["action"],
    }

    async def run(self, action: str, **kwargs) -> ToolResult:
        # Mock implementation - replace with actual DB connection
        db_url = os.getenv("DATABASE_URL", "")

        if action == "list_tables":
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=["users", "sessions", "auth_tokens", "audit_logs", "api_keys"],
                metadata={"mock": not db_url},
            )
        elif action == "describe_table":
            table = kwargs.get("table", "")
            schemas = {
                "users": ["id (uuid)", "email (varchar)", "created_at (timestamp)", "last_login (timestamp)", "status (enum)"],
                "sessions": ["id (uuid)", "user_id (uuid)", "token_hash (varchar)", "expires_at (timestamp)", "ip_address (inet)"],
                "auth_tokens": ["id (uuid)", "user_id (uuid)", "token (varchar)", "type (enum: access/refresh)", "expires_at (timestamp)", "revoked_at (timestamp)"],
                "audit_logs": ["id (uuid)", "user_id (uuid)", "action (varchar)", "resource (varchar)", "timestamp (timestamp)", "success (bool)"],
            }
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=schemas.get(table, [f"Table '{table}' not found"]),
            )
        elif action == "query":
            sql = kwargs.get("sql", "")
            if not sql.strip().upper().startswith("SELECT"):
                return ToolResult(
                    tool_name=self.name,
                    success=False,
                    data=None,
                    error="Only SELECT queries are permitted for safety",
                )
            # Mock query results
            return ToolResult(
                tool_name=self.name,
                success=True,
                data=[
                    {"note": "Mock query result — configure DATABASE_URL for real data"},
                    {"query": sql},
                ],
                metadata={"mock": True},
            )

        return ToolResult(tool_name=self.name, success=False, data=None, error=f"Unknown action: {action}")

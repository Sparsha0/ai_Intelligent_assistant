"""
MCP-compatible Tool Registry
All tools follow a consistent interface for the agent layer.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Standard result from any tool call."""
    tool_name: str
    success: bool
    data: Any
    error: str | None = None
    metadata: dict = field(default_factory=dict)

    def to_text(self) -> str:
        if not self.success:
            return f"[Tool Error: {self.tool_name}] {self.error}"
        if isinstance(self.data, str):
            return self.data
        if isinstance(self.data, list):
            return "\n".join(str(item) for item in self.data)
        return str(self.data)


class BaseTool(ABC):
    """Base class for all tools."""
    name: str
    description: str
    parameters: dict  # JSON Schema for parameters

    @abstractmethod
    async def run(self, **kwargs) -> ToolResult:
        """Execute the tool."""
        ...

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


class ToolRegistry:
    """Registry for all available tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    async def run(self, tool_name: str, **kwargs) -> ToolResult:
        """Run a tool by name with error handling."""
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=f"Tool '{tool_name}' not found in registry",
            )
        try:
            result = await tool.run(**kwargs)
            logger.info(f"Tool '{tool_name}' executed successfully")
            return result
        except Exception as e:
            logger.error(f"Tool '{tool_name}' failed: {e}")
            return ToolResult(
                tool_name=tool_name,
                success=False,
                data=None,
                error=str(e),
            )


# Global registry singleton
_registry: ToolRegistry | None = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_default_tools(_registry)
    return _registry


def _register_default_tools(registry: ToolRegistry):
    """Register all built-in tools."""
    from .github_tool import GitHubTool
    from .slack_tool import SlackTool
    from .database_tool import DatabaseTool
    from .filesystem_tool import FileSystemTool

    registry.register(GitHubTool())
    registry.register(SlackTool())
    registry.register(DatabaseTool())
    registry.register(FileSystemTool())

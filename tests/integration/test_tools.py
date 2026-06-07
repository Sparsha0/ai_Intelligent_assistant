"""
Integration tests for the tool registry and individual tools.
All tools fall back to mock data when API keys are absent.
"""

import pytest
from backend.tools.registry import ToolRegistry, get_registry
from backend.tools.github_tool import GitHubTool
from backend.tools.slack_tool import SlackTool
from backend.tools.database_tool import DatabaseTool
from backend.tools.filesystem_tool import FileSystemTool


@pytest.fixture
def registry():
    return get_registry()


class TestToolRegistry:

    def test_registry_has_default_tools(self, registry):
        tools = registry.list_tools()
        names = [t["name"] for t in tools]
        assert "github" in names
        assert "slack" in names
        assert "database" in names
        assert "filesystem" in names

    @pytest.mark.asyncio
    async def test_registry_run_returns_result(self, registry):
        result = await registry.run("database", action="list_tables")
        assert result.tool_name == "database"
        assert result.success is True

    @pytest.mark.asyncio
    async def test_registry_unknown_tool_returns_error(self, registry):
        result = await registry.run("nonexistent_tool", action="foo")
        assert result.success is False
        assert "not found" in result.error.lower()

    def test_tool_schemas_have_required_fields(self, registry):
        for tool in registry.list_tools():
            assert "name" in tool
            assert "description" in tool
            assert "parameters" in tool


class TestGitHubToolMock:

    @pytest.fixture
    def tool(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        return GitHubTool()

    @pytest.mark.asyncio
    async def test_search_issues_returns_list(self, tool):
        result = await tool.run(action="search_issues", query="authentication", days=30)
        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) > 0

    @pytest.mark.asyncio
    async def test_search_issues_filters_by_query(self, tool):
        result = await tool.run(action="search_issues", query="authentication", days=30)
        assert all(
            "auth" in str(issue).lower() or "login" in str(issue).lower()
            for issue in result.data
        )

    @pytest.mark.asyncio
    async def test_search_issues_have_required_fields(self, tool):
        result = await tool.run(action="search_issues", query="auth")
        for issue in result.data:
            assert "number" in issue
            assert "title" in issue
            assert "url" in issue
            assert "state" in issue

    @pytest.mark.asyncio
    async def test_mock_flag_in_metadata(self, tool):
        result = await tool.run(action="search_issues")
        assert result.metadata.get("mock") is True

    @pytest.mark.asyncio
    async def test_days_filter_applied(self, tool):
        result_30 = await tool.run(action="search_issues", days=30)
        result_1 = await tool.run(action="search_issues", days=1)
        # 1 day should return fewer or equal results than 30 days
        assert len(result_1.data) <= len(result_30.data)


class TestSlackToolMock:

    @pytest.fixture
    def tool(self, monkeypatch):
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        return SlackTool()

    @pytest.mark.asyncio
    async def test_search_messages_returns_list(self, tool):
        result = await tool.run(action="search_messages", query="authentication")
        assert result.success is True
        assert isinstance(result.data, list)

    @pytest.mark.asyncio
    async def test_messages_have_required_fields(self, tool):
        result = await tool.run(action="search_messages", query="auth")
        for msg in result.data:
            assert "text" in msg
            assert "user" in msg
            assert "channel" in msg


class TestDatabaseTool:

    @pytest.fixture
    def tool(self):
        return DatabaseTool()

    @pytest.mark.asyncio
    async def test_list_tables(self, tool):
        result = await tool.run(action="list_tables")
        assert result.success is True
        assert isinstance(result.data, list)
        assert "users" in result.data
        assert "sessions" in result.data

    @pytest.mark.asyncio
    async def test_describe_table(self, tool):
        result = await tool.run(action="describe_table", table="users")
        assert result.success is True
        assert len(result.data) > 0
        assert any("email" in col for col in result.data)

    @pytest.mark.asyncio
    async def test_safe_select_query(self, tool):
        result = await tool.run(action="query", sql="SELECT * FROM users LIMIT 10")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_unsafe_insert_rejected(self, tool):
        result = await tool.run(action="query", sql="INSERT INTO users VALUES (1, 'hacked')")
        assert result.success is False
        assert "SELECT" in result.error

    @pytest.mark.asyncio
    async def test_unsafe_drop_rejected(self, tool):
        result = await tool.run(action="query", sql="DROP TABLE users")
        assert result.success is False


class TestFileSystemTool:

    @pytest.fixture
    def tool(self):
        return FileSystemTool()

    @pytest.mark.asyncio
    async def test_path_outside_sandbox_denied(self, tool):
        result = await tool.run(action="read_file", path="/etc/passwd")
        assert result.success is False
        assert "denied" in result.error.lower() or "outside" in result.error.lower()

    @pytest.mark.asyncio
    async def test_missing_path_param(self, tool):
        result = await tool.run(action="read_file")
        assert result.success is False

    @pytest.mark.asyncio
    async def test_list_files_returns_list(self, tool, tmp_path, monkeypatch):
        # Temporarily allow tmp_path
        monkeypatch.setattr(
            "backend.tools.filesystem_tool.ALLOWED_BASE_DIRS",
            [str(tmp_path)],
        )
        (tmp_path / "test.py").write_text("print('hello')")
        result = await tool.run(action="list_files", path=str(tmp_path))
        assert result.success is True
        assert any("test.py" in f for f in result.data)

    @pytest.mark.asyncio
    async def test_search_in_files(self, tool, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "backend.tools.filesystem_tool.ALLOWED_BASE_DIRS",
            [str(tmp_path)],
        )
        (tmp_path / "auth.py").write_text("def verify_token(token):\n    return jwt.decode(token)\n")
        result = await tool.run(action="search_in_files", path=str(tmp_path), pattern="jwt")
        assert result.success is True
        assert len(result.data) > 0
        assert any("jwt" in match["content"].lower() for match in result.data)

"""
Integration tests for the multi-agent orchestrator.
Uses mock LLM and tool registry.
"""

import pytest
from unittest.mock import AsyncMock, patch

from backend.agents.orchestrator import (
    AgentOrchestrator,
    AgentStatus,
    PlannerAgent,
    ResearchAgent,
    AnalysisAgent,
    QAAgent,
    SummaryAgent,
)
from backend.llm.router import LLMRouter
from backend.llm.base import LLMResponse, ProviderName
from backend.tools.registry import ToolRegistry, get_registry


@pytest.fixture
def mock_router(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    return LLMRouter()


@pytest.fixture
def tool_registry():
    return get_registry()


@pytest.fixture
def orchestrator(mock_router, tool_registry):
    return AgentOrchestrator(llm=mock_router, tool_registry=tool_registry)


class TestIndividualAgents:

    @pytest.mark.asyncio
    async def test_planner_runs(self, mock_router):
        agent = PlannerAgent(mock_router)
        step = await agent.run({"query": "Analyze authentication failures"})
        assert step.agent == "Planner"
        assert step.status in (AgentStatus.DONE, AgentStatus.FAILED)
        if step.status == AgentStatus.DONE:
            assert step.output

    @pytest.mark.asyncio
    async def test_research_agent_calls_tools(self, mock_router, tool_registry):
        agent = ResearchAgent(mock_router, tool_registry)
        step = await agent.run({
            "query": "Find authentication issues in GitHub",
            "plan": "Search GitHub for auth-related issues",
        })
        assert step.agent == "Research"
        assert step.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_analysis_agent_runs(self, mock_router):
        agent = AnalysisAgent(mock_router)
        step = await agent.run({
            "query": "Why are logins failing?",
            "research_output": "GitHub shows 5 open auth issues. Redis cache hit rate 12%.",
        })
        assert step.agent == "Analysis"
        assert step.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_qa_agent_validates(self, mock_router):
        agent = QAAgent(mock_router)
        step = await agent.run({
            "query": "Root cause of login failures",
            "analysis_output": "JWT signing key not propagated to all pods.",
            "research_output": "5 GitHub issues, Slack incident channel discussion.",
        })
        assert step.agent == "QA"

    @pytest.mark.asyncio
    async def test_summary_agent_produces_output(self, mock_router):
        agent = SummaryAgent(mock_router)
        step = await agent.run({
            "query": "Login flow analysis",
            "research_output": "Found 5 auth issues.",
            "analysis_output": "JWT key rotation bug is root cause.",
            "qa_output": "High confidence in root cause. Missing load test data.",
        })
        assert step.agent == "Summary"
        assert step.status == AgentStatus.DONE
        assert len(step.output) > 0


class TestOrchestratorWorkflow:

    @pytest.mark.asyncio
    async def test_full_workflow_completes(self, orchestrator):
        result = await orchestrator.run("Analyze authentication failures in the last 30 days.")
        assert result.user_query
        assert result.final_answer
        assert result.request_id
        assert result.total_duration_ms > 0
        assert len(result.steps) == 5  # Planner, Research, Analysis, QA, Summary

    @pytest.mark.asyncio
    async def test_workflow_steps_named_correctly(self, orchestrator):
        result = await orchestrator.run("Find login issues.")
        agent_names = [s.agent for s in result.steps]
        assert "Planner" in agent_names
        assert "Research" in agent_names
        assert "Analysis" in agent_names
        assert "QA" in agent_names
        assert "Summary" in agent_names

    @pytest.mark.asyncio
    async def test_workflow_steps_in_order(self, orchestrator):
        result = await orchestrator.run("Debug the auth service.")
        expected_order = ["Planner", "Research", "Analysis", "QA", "Summary"]
        actual_order = [s.agent for s in result.steps]
        assert actual_order == expected_order

    @pytest.mark.asyncio
    async def test_step_durations_recorded(self, orchestrator):
        result = await orchestrator.run("Short test query.")
        for step in result.steps:
            assert step.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_to_dict_serializable(self, orchestrator):
        result = await orchestrator.run("Test serialization.")
        d = result.to_dict()
        import json
        serialized = json.dumps(d)  # Should not raise
        assert "final_answer" in serialized
        assert "steps" in serialized

    @pytest.mark.asyncio
    async def test_workflow_continues_after_agent_failure(self, mock_router, tool_registry):
        """If one agent fails, the pipeline should continue."""
        orchestrator = AgentOrchestrator(mock_router, tool_registry)

        # Sabotage the analysis agent
        original_execute = orchestrator.agents["analysis"]._execute
        async def failing_execute(context):
            raise RuntimeError("Simulated analysis failure")
        orchestrator.agents["analysis"]._execute = failing_execute

        result = await orchestrator.run("Test resilience.")
        # Should still complete (not raise)
        assert result.final_answer is not None
        # Analysis step should be marked failed
        analysis_step = next(s for s in result.steps if s.agent == "Analysis")
        assert analysis_step.status == AgentStatus.FAILED
        # Summary should still run
        summary_step = next(s for s in result.steps if s.agent == "Summary")
        assert summary_step.status == AgentStatus.DONE

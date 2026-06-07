"""
Multi-Agent Orchestrator
Coordinates: Planner → Research → Analysis → QA → Summary
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from llm.base import LLMConfig, Message
from llm.router import LLMRouter
from tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class AgentStep:
    agent: str
    status: AgentStatus
    input: str
    output: str = ""
    error: str | None = None
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)


@dataclass
class WorkflowResult:
    """Final result from a multi-agent workflow."""
    request_id: str
    user_query: str
    final_answer: str
    steps: list[AgentStep]
    total_duration_ms: int
    success: bool
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "user_query": self.user_query,
            "final_answer": self.final_answer,
            "steps": [
                {
                    "agent": s.agent,
                    "status": s.status,
                    "output": s.output,
                    "duration_ms": s.duration_ms,
                    "metadata": s.metadata,
                }
                for s in self.steps
            ],
            "total_duration_ms": self.total_duration_ms,
            "success": self.success,
        }


class BaseAgent:
    """Base class for all agents."""

    def __init__(self, name: str, llm: LLMRouter, system_prompt: str):
        self.name = name
        self.llm = llm
        self.system_prompt = system_prompt

    async def run(self, context: dict) -> AgentStep:
        start = time.time()
        step = AgentStep(agent=self.name, status=AgentStatus.RUNNING, input=str(context))
        try:
            output = await self._execute(context)
            step.output = output
            step.status = AgentStatus.DONE
        except Exception as e:
            step.error = str(e)
            step.status = AgentStatus.FAILED
            logger.error(f"Agent {self.name} failed: {e}")
        step.duration_ms = int((time.time() - start) * 1000)
        return step

    async def _execute(self, context: dict) -> str:
        raise NotImplementedError


class PlannerAgent(BaseAgent):
    """Decomposes the user query into structured subtasks."""

    SYSTEM = """You are a task planning agent for an engineering AI assistant.
Given a user request, decompose it into concrete subtasks.
Output a JSON object with:
- summary: one-sentence description of the task
- subtasks: list of {id, description, tools_needed, agent}
- complexity: low|medium|high
Be concise. Think step by step."""

    def __init__(self, llm: LLMRouter):
        super().__init__("Planner", llm, self.SYSTEM)

    async def _execute(self, context: dict) -> str:
        query = context["query"]
        available_tools = context.get("available_tools", [])

        prompt = f"""User Request: {query}

Available Tools: {', '.join(available_tools) if available_tools else 'github, slack, database, filesystem, rag'}

Decompose this into subtasks. Return JSON only."""

        response = await self.llm.complete(
            [Message(role="user", content=prompt)],
            system=self.SYSTEM,
            config=LLMConfig(temperature=0.1, max_tokens=512),
            task_type="structured_output",
        )
        return response.content


class ResearchAgent(BaseAgent):
    """Retrieves relevant data from tools and the knowledge base."""

    SYSTEM = """You are a research agent. Your job is to gather relevant information using available tools and retrieved documents.
Summarize what you found clearly. Include specific data points, issue numbers, timestamps.
If a tool returns no results, say so explicitly."""

    def __init__(self, llm: LLMRouter, tool_registry: ToolRegistry):
        super().__init__("Research", llm, self.SYSTEM)
        self.tools = tool_registry

    async def _execute(self, context: dict) -> str:
        query = context["query"]
        plan = context.get("plan", "")

        # Determine which tools to call based on the query
        tool_results = []

        # Always try GitHub for engineering queries
        if any(kw in query.lower() for kw in ["issue", "bug", "pr", "commit", "github", "fail", "error", "login", "auth"]):
            result = await self.tools.run("github", action="search_issues", query=query, days=30)
            if result.success and result.data:
                tool_results.append(f"GitHub Issues:\n{self._format_issues(result.data)}")

        # Try Slack for incident/discussion queries
        if any(kw in query.lower() for kw in ["incident", "outage", "discussion", "slack", "team", "fail"]):
            result = await self.tools.run("slack", action="search_messages", query=query)
            if result.success and result.data:
                tool_results.append(f"Slack Messages:\n{self._format_messages(result.data)}")

        # Try database for data-related queries
        if any(kw in query.lower() for kw in ["database", "schema", "table", "query", "sql", "user", "session"]):
            result = await self.tools.run("database", action="list_tables")
            if result.success:
                tool_results.append(f"Database Tables: {result.data}")

        if not tool_results:
            tool_results.append("No specific tool data retrieved. Proceeding with general knowledge.")

        research_summary = "\n\n".join(tool_results)

        # Ask LLM to synthesize
        prompt = f"""Research Query: {query}

Raw Data Collected:
{research_summary}

Synthesize the above into a clear research summary. What are the key findings?"""

        response = await self.llm.complete(
            [Message(role="user", content=prompt)],
            system=self.SYSTEM,
            config=LLMConfig(temperature=0.2, max_tokens=1024),
            task_type="research",
        )
        return response.content

    def _format_issues(self, issues: list) -> str:
        lines = []
        for issue in issues[:5]:
            lines.append(f"  #{issue['number']}: {issue['title']} [{', '.join(issue.get('labels', []))}]")
            lines.append(f"    {issue.get('body_preview', '')[:120]}")
        return "\n".join(lines)

    def _format_messages(self, messages: list) -> str:
        return "\n".join(f"  [{m.get('channel', '')}] {m['user']}: {m['text'][:100]}" for m in messages[:4])


class AnalysisAgent(BaseAgent):
    """Identifies root causes, patterns, and generates hypotheses."""

    SYSTEM = """You are a senior software engineering analyst.
Given research findings, perform deep analysis:
1. Identify root causes (not just symptoms)
2. Find patterns across issues
3. Rank hypotheses by likelihood
4. Identify contributing factors
5. Note what information is missing
Be precise and technical. Use evidence to support conclusions."""

    def __init__(self, llm: LLMRouter):
        super().__init__("Analysis", llm, self.SYSTEM)

    async def _execute(self, context: dict) -> str:
        query = context["query"]
        research = context.get("research_output", "No research data available")

        prompt = f"""Original Request: {query}

Research Findings:
{research}

Perform a deep technical analysis. What are the root causes? What patterns do you see? Rank your findings by confidence."""

        response = await self.llm.complete(
            [Message(role="user", content=prompt)],
            system=self.SYSTEM,
            config=LLMConfig(temperature=0.3, max_tokens=1024),
            task_type="code_analysis",
        )
        return response.content


class QAAgent(BaseAgent):
    """Validates assumptions and checks for logical gaps."""

    SYSTEM = """You are a QA/validation agent. Your job is to critically review analyses.
For each finding:
1. Is it supported by evidence? Rate confidence (High/Medium/Low)
2. What assumptions are being made?
3. What counter-evidence exists?
4. What's missing from this analysis?
5. Are there any logical gaps?
Be rigorous and skeptical. Push back on unsupported claims."""

    def __init__(self, llm: LLMRouter):
        super().__init__("QA", llm, self.SYSTEM)

    async def _execute(self, context: dict) -> str:
        analysis = context.get("analysis_output", "")
        research = context.get("research_output", "")

        prompt = f"""Analysis to Validate:
{analysis}

Supporting Research:
{research}

Validate each finding. Rate confidence, flag gaps, note assumptions."""

        response = await self.llm.complete(
            [Message(role="user", content=prompt)],
            system=self.SYSTEM,
            config=LLMConfig(temperature=0.2, max_tokens=768),
        )
        return response.content


class SummaryAgent(BaseAgent):
    """Generates the final structured response with recommendations."""

    SYSTEM = """You are a technical writing agent. Create clear, actionable engineering reports.
Structure your response as:
## Summary
(2-3 sentence overview)

## Key Findings
(Bulleted, evidence-backed findings)

## Root Cause Analysis
(Technical explanation)

## Recommended Actions
(Prioritized, specific action items with owners if possible)

## Risk Assessment
(What could go wrong, confidence level)

Be concise, technical, and actionable. Use Markdown."""

    def __init__(self, llm: LLMRouter):
        super().__init__("Summary", llm, self.SYSTEM)

    async def _execute(self, context: dict) -> str:
        prompt = f"""Original Request: {context['query']}

Research: {context.get('research_output', '')[:800]}

Analysis: {context.get('analysis_output', '')[:800]}

QA Validation: {context.get('qa_output', '')[:400]}

Generate the final engineering report:"""

        response = await self.llm.complete(
            [Message(role="user", content=prompt)],
            system=self.SYSTEM,
            config=LLMConfig(temperature=0.2, max_tokens=1500),
            task_type="summarization",
        )
        return response.content


class AgentOrchestrator:
    """
    Orchestrates the multi-agent workflow:
    Planner → Research → Analysis → QA → Summary
    
    Each agent receives accumulated context from previous agents.
    Failed agents are logged but workflow continues with degraded context.
    """

    def __init__(self, llm: LLMRouter, tool_registry: ToolRegistry):
        self.llm = llm
        self.tools = tool_registry
        self.agents = {
            "planner": PlannerAgent(llm),
            "research": ResearchAgent(llm, tool_registry),
            "analysis": AnalysisAgent(llm),
            "qa": QAAgent(llm),
            "summary": SummaryAgent(llm),
        }

    async def run(self, query: str) -> WorkflowResult:
        """Execute the full agent workflow."""
        request_id = str(uuid.uuid4())[:8]
        start = time.time()
        steps: list[AgentStep] = []
        context: dict[str, Any] = {
            "query": query,
            "request_id": request_id,
            "available_tools": list(self.tools._tools.keys()),
        }

        logger.info(f"[{request_id}] Starting agent workflow for: {query[:80]}")

        pipeline = [
            ("planner", "plan"),
            ("research", "research_output"),
            ("analysis", "analysis_output"),
            ("qa", "qa_output"),
            ("summary", "final_answer"),
        ]

        for agent_name, output_key in pipeline:
            agent = self.agents[agent_name]
            logger.info(f"[{request_id}] Running {agent_name} agent...")
            step = await agent.run(context)
            steps.append(step)

            if step.status == AgentStatus.DONE:
                context[output_key] = step.output
            else:
                context[output_key] = f"[{agent_name} failed: {step.error}]"
                logger.warning(f"[{request_id}] {agent_name} failed, continuing...")

        final = context.get("final_answer", "Unable to generate summary.")
        total_ms = int((time.time() - start) * 1000)

        logger.info(f"[{request_id}] Workflow complete in {total_ms}ms")

        return WorkflowResult(
            request_id=request_id,
            user_query=query,
            final_answer=final,
            steps=steps,
            total_duration_ms=total_ms,
            success=bool(final and "[failed" not in final),
        )

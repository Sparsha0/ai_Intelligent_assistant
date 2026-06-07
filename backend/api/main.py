"""
FastAPI Application - Main entry point
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field
import asyncio
import json

from llm.router import get_router, LLMRouter
from rag.retrieval import RAGPipeline
from rag.vectorstore import VectorStore
from rag.ingestion import DocumentIngester
from agents.orchestrator import AgentOrchestrator
from tools.registry import get_registry
from security.injection_guard import get_guard, SecurityError
from observability.tracer import get_tracer, get_token_tracker, configure_logging
from llm.base import Message, LLMConfig

# Configure logging
configure_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_output=os.getenv("LOG_FORMAT", "console") == "json",
)
logger = logging.getLogger(__name__)

# Global instances (initialized in lifespan)
_rag: RAGPipeline | None = None
_orchestrator: AgentOrchestrator | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize all services."""
    global _rag, _orchestrator
    logger.info("Initializing Engineering AI Assistant...")

    router = get_router()
    registry = get_registry()

    vector_store = VectorStore()
    _rag = RAGPipeline(vector_store, router)

    _orchestrator = AgentOrchestrator(router, registry)

    # Ingest sample docs if knowledge base is empty
    if vector_store.count() == 0:
        await _seed_knowledge_base(_rag)

    logger.info(f"Ready. Providers: {router.available_providers}")
    yield
    logger.info("Shutting down...")


async def _seed_knowledge_base(rag: RAGPipeline):
    """Seed with sample engineering documentation."""
    sample_docs = [
        (
            """# Authentication Architecture

Our authentication system uses JWT (JSON Web Tokens) with RS256 signing.

## Token Lifecycle
- Access tokens expire after 15 minutes
- Refresh tokens expire after 7 days
- Tokens are invalidated on password change or explicit logout

## JWT Structure
Header: {alg: RS256, typ: JWT}
Payload: {sub: user_id, iat: issued_at, exp: expiry, jti: token_id}

## Key Rotation
Signing keys are rotated every 90 days. During rotation, both old and new keys are valid for 24 hours to allow graceful token refresh.

## Session Management
Sessions are stored in Redis with a TTL matching the refresh token expiry.
Active sessions are tracked per user with a maximum of 10 concurrent sessions.

## Security Controls
- CSRF protection on all state-changing endpoints
- Rate limiting: 10 login attempts per minute per IP
- Audit logging for all authentication events
""",
            "auth-architecture.md",
        ),
        (
            """# Incident Response Playbook

## Severity Levels
- P0: Complete service outage (15 min response SLA)
- P1: Major feature broken affecting >20% users (1 hour response SLA)
- P2: Partial degradation affecting <20% users (4 hour SLA)
- P3: Minor issues (next business day)

## Authentication Failures
If users cannot log in:
1. Check auth service health: `kubectl get pods -n auth`
2. Verify Redis connection: `redis-cli ping`
3. Check JWT signing key availability
4. Review error logs: `kubectl logs -l app=auth-service --tail=100`
5. Check if recent deployment in last 30 min

## Escalation Path
On-call → Team Lead → VP Engineering
""",
            "incident-playbook.md",
        ),
        (
            """# API Gateway Configuration

## Rate Limiting Rules
- /auth/login: 10 req/min per IP
- /auth/token: 60 req/min per IP
- /api/*: 1000 req/min per authenticated user
- /api/admin/*: 100 req/min per authenticated admin

## Circuit Breaker Settings
Threshold: 50% failure rate over 10 second window
Half-open probe: 1 request per 5 seconds
Recovery threshold: 3 consecutive successes

## Upstream Services
- auth-service: auth.internal:8080
- user-service: users.internal:8081
- notification-service: notify.internal:8082
""",
            "api-gateway-config.md",
        ),
    ]

    for content, source in sample_docs:
        try:
            await rag.ingest_text(content, source, metadata={"filename": source, "category": "documentation"})
        except Exception as e:
            logger.warning(f"Failed to seed {source}: {e}")

    logger.info(f"Knowledge base seeded with {len(sample_docs)} documents")


app = FastAPI(
    title="Engineering AI Assistant",
    description="AI-powered engineering intelligence platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request/Response Models ───────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    mode: str = Field(default="auto", pattern="^(auto|rag|agent|chat)$")
    stream: bool = False


class RAGIngestRequest(BaseModel):
    text: str
    source: str
    metadata: dict = {}


class ToolRunRequest(BaseModel):
    tool_name: str
    params: dict = {}


# ─── Dependencies ──────────────────────────────────────────────────────────────

def get_rag() -> RAGPipeline:
    if _rag is None:
        raise HTTPException(503, "RAG pipeline not initialized")
    return _rag


def get_orchestrator() -> AgentOrchestrator:
    if _orchestrator is None:
        raise HTTPException(503, "Orchestrator not initialized")
    return _orchestrator


# ─── Routes ───────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {
        "status": "running",
        "message": "Engineering AI Assistant API is live",
        "docs": "/docs"
    }

@app.get("/health")
async def health():
    router = get_router()
    rag = get_rag()
    return {
        "status": "healthy",
        "providers": router.available_providers,
        "knowledge_base": {
            "chunks": rag.stats()["total_chunks"],
            "sources": len(rag.stats()["sources"]),
        },
        "token_usage": get_token_tracker().summary(),
    }


@app.post("/chat")
async def chat(req: ChatRequest):
    """
    Main chat endpoint. Routes to RAG, agents, or direct chat based on mode.
    """
    guard = get_guard()
    tracer = get_tracer()

    try:
        safe_message = guard.validate(req.message)
    except SecurityError as e:
        raise HTTPException(400, str(e))

    correlation_id = tracer.start_request(safe_message)

    if req.stream:
        return StreamingResponse(
            _stream_chat(safe_message, req.mode),
            media_type="text/event-stream",
            headers={"X-Correlation-ID": correlation_id},
        )

    # Non-streaming
    result = await _process_chat(safe_message, req.mode)
    return {**result, "correlation_id": correlation_id}


async def _process_chat(message: str, mode: str) -> dict:
    rag = get_rag()
    orchestrator = get_orchestrator()
    router = get_router()

    # Auto-detect mode
    if mode == "auto":
        agent_keywords = ["analyze", "investigate", "find issues", "github", "slack", "failing", "debug", "root cause"]
        mode = "agent" if any(kw in message.lower() for kw in agent_keywords) else "rag"

    if mode == "agent":
        result = await orchestrator.run(message)
        return {
            "mode": "agent",
            "answer": result.final_answer,
            "steps": [
                {
                    "agent": s.agent,
                    "status": s.status,
                    "output": s.output[:500] if s.output else "",
                    "duration_ms": s.duration_ms,
                }
                for s in result.steps
            ],
            "duration_ms": result.total_duration_ms,
        }

    elif mode == "rag":
        result = await rag.query(message)
        return {
            "mode": "rag",
            "answer": result.answer,
            "sources": result.sources,
            "grounded": result.grounded,
            "relevance_score": round(result.max_relevance_score, 3),
            "chunks_used": result.chunks_used,
        }

    else:  # direct chat
        response = await router.complete(
            [Message(role="user", content=message)],
            system="You are a helpful engineering assistant.",
            config=LLMConfig(temperature=0.4, max_tokens=1024),
        )
        return {
            "mode": "chat",
            "answer": response.content,
            "tokens": {"input": response.input_tokens, "output": response.output_tokens},
        }


async def _stream_chat(message: str, mode: str):
    """SSE streaming for chat responses."""
    router = get_router()
    try:
        async for token in router.stream(
            [Message(role="user", content=message)],
            system="You are a helpful engineering assistant.",
            config=LLMConfig(temperature=0.3, max_tokens=1024),
        ):
            yield f"data: {json.dumps({'token': token})}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@app.post("/rag/ingest")
async def ingest_text(req: RAGIngestRequest, rag: RAGPipeline = Depends(get_rag)):
    """Ingest text into the knowledge base."""
    chunks = await rag.ingest_text(req.text, req.source, req.metadata)
    return {"chunks_created": chunks, "source": req.source}


@app.post("/rag/ingest/file")
async def ingest_file(file: UploadFile = File(...), rag: RAGPipeline = Depends(get_rag)):
    """Upload and ingest a file."""
    import tempfile, os
    allowed = {".pdf", ".md", ".txt", ".html"}
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(400, f"File type {ext} not supported. Allowed: {allowed}")

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        chunks = await rag.ingest_file(tmp_path)
        return {"chunks_created": chunks, "filename": file.filename}
    finally:
        os.unlink(tmp_path)


@app.get("/rag/stats")
async def rag_stats(rag: RAGPipeline = Depends(get_rag)):
    return rag.stats()


@app.post("/tools/run")
async def run_tool(req: ToolRunRequest):
    """Run a registered tool directly."""
    registry = get_registry()
    result = await registry.run(req.tool_name, **req.params)
    return {
        "tool": req.tool_name,
        "success": result.success,
        "data": result.data,
        "error": result.error,
    }


@app.get("/tools/list")
async def list_tools():
    registry = get_registry()
    return registry.list_tools()


@app.get("/observability/traces")
async def get_traces():
    return get_tracer().get_summary()


@app.get("/observability/tokens")
async def get_token_usage():
    return get_token_tracker().summary()

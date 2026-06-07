# 🤖 AI-Powered Engineering Intelligence Assistant

A production-grade AI platform that helps software teams analyze issues, retrieve organizational knowledge, interact with external systems, and generate actionable insights.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                         │
│              Chat UI · RAG Explorer · Agent Monitor             │
└────────────────────────────┬────────────────────────────────────┘
                             │ REST / SSE
┌────────────────────────────▼────────────────────────────────────┐
│                      FastAPI Backend                            │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │  RAG API │  │  Agent API   │  │    Tool/MCP API        │   │
│  └────┬─────┘  └──────┬───────┘  └──────────┬─────────────┘   │
│       │               │                      │                  │
│  ┌────▼───────────────▼──────────────────────▼──────────────┐  │
│  │                  Orchestration Layer                      │  │
│  │  Planner → Research → Analysis → QA → Summary            │  │
│  └────────────────────────────┬──────────────────────────────┘  │
│                               │                                  │
│  ┌────────────────────────────▼──────────────────────────────┐  │
│  │               LLM Provider Abstraction                    │  │
│  │        OpenAI · Anthropic · Gemini · Fallback             │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────┐ │
│  │ Vector Store │  │  Tool Registry│  │  Observability       │ │
│  │  (ChromaDB)  │  │  GitHub/Slack │  │  Logging + Tracing   │ │
│  └──────────────┘  └───────────────┘  └──────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

---

## Features

### ✅ RAG System
- Multi-format document ingestion (PDF, Markdown, TXT, HTML)
- Recursive text chunking with overlap
- Embedding generation (OpenAI / local fallback)
- ChromaDB vector storage
- Semantic retrieval with MMR diversity
- Source citations on every answer
- "I don't know" responses when context is insufficient

### ✅ MCP / Tool Integration
- GitHub: Issues, PRs, commits search
- Slack: Channel messages, thread summaries
- Database: Schema inspection, query execution
- File system: Code reading, file search
- Internal API: Mock endpoints for demo

### ✅ Multi-Agent Workflow
- **Planner Agent**: Decomposes tasks into subtasks
- **Research Agent**: Retrieves docs, logs, external data
- **Analysis Agent**: Identifies root causes, patterns
- **QA Agent**: Validates assumptions and facts
- **Summary Agent**: Generates structured final responses

### ✅ Multi-LLM Support
- Provider abstraction layer
- Configurable routing (by cost, capability, task type)
- Retry with exponential backoff
- Automatic fallback chain
- Structured output support

### ✅ Reliability & Observability
- Structured JSON logging
- Request tracing with correlation IDs
- Token usage tracking
- Tool failure recovery
- Graceful degradation

### ✅ Security Awareness
- Prompt injection detection
- Tool execution sandboxing
- Secret management via environment variables
- Rate limiting per user
- Input sanitization

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Docker & Docker Compose (optional)

### Option A: Docker (Recommended)
```bash
cp .env.example .env
# Fill in your API keys in .env
docker-compose up --build
```

### Option B: Manual Setup

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp ../.env.example ../.env
# Edit .env with your API keys
uvicorn api.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173`

---

## Environment Variables

```env
# LLM Providers (at least one required)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=...

# Primary provider preference
LLM_PROVIDER=anthropic   # openai | anthropic | gemini

# GitHub (optional - uses mock if absent)
GITHUB_TOKEN=ghp_...
GITHUB_ORG=your-org

# Slack (optional - uses mock if absent)
SLACK_BOT_TOKEN=xoxb-...

# Database (optional)
DATABASE_URL=postgresql://user:pass@localhost/dbname

# Vector DB
CHROMA_PERSIST_DIR=./data/chroma

# Security
SECRET_KEY=your-secret-key-here
ALLOWED_ORIGINS=http://localhost:5173
```

---

## Sample Prompts & Expected Outputs

### 1. RAG Query
**Prompt:** "What is our authentication flow and how do JWT tokens expire?"

**Expected:** Grounded answer with source citations from ingested docs, or "I don't have enough information in the knowledge base about this topic."

### 2. Tool-Augmented Query
**Prompt:** "Find all authentication-related GitHub issues opened in the last 30 days and summarize recurring failures."

**Expected:** Agent retrieves GitHub issues → clusters by theme → returns structured markdown report with issue links.

### 3. Multi-Agent Workflow
**Prompt:** "Analyze our failing login flow and suggest possible fixes."

**Expected:**
```
[Planner] Decomposed into 4 subtasks...
[Research] Found 12 relevant docs, 5 GitHub issues...
[Analysis] Root causes: token expiry misconfiguration, race condition in session...
[QA] Validated: 3/4 hypotheses confirmed against logs...
[Summary] Final recommendations with confidence scores...
```

### 4. Code Analysis
**Prompt:** "Review the authentication middleware for security vulnerabilities."

**Expected:** Code analysis with OWASP-aligned findings, severity levels, and fix suggestions.

---

## Project Structure

```
engineering-ai-assistant/
├── backend/
│   ├── agents/          # Multi-agent orchestration
│   │   ├── planner.py
│   │   ├── research.py
│   │   ├── analysis.py
│   │   ├── qa.py
│   │   ├── summary.py
│   │   └── orchestrator.py
│   ├── rag/             # RAG pipeline
│   │   ├── ingestion.py
│   │   ├── chunking.py
│   │   ├── embeddings.py
│   │   ├── vectorstore.py
│   │   └── retrieval.py
│   ├── llm/             # LLM abstraction
│   │   ├── base.py
│   │   ├── openai_provider.py
│   │   ├── anthropic_provider.py
│   │   ├── gemini_provider.py
│   │   └── router.py
│   ├── tools/           # MCP-style tools
│   │   ├── registry.py
│   │   ├── github_tool.py
│   │   ├── slack_tool.py
│   │   ├── database_tool.py
│   │   └── filesystem_tool.py
│   ├── security/        # Security layer
│   │   ├── sanitizer.py
│   │   └── injection_guard.py
│   ├── observability/   # Logging & tracing
│   │   ├── logger.py
│   │   └── tracer.py
│   ├── api/             # FastAPI routes
│   │   ├── main.py
│   │   ├── routes/
│   │   └── middleware/
│   └── utils/
├── frontend/            # React app
├── tests/
├── docs/
├── docker/
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Vector DB | ChromaDB | Zero-infrastructure, file-based, easy to swap |
| Agent Framework | Custom (inspired by LangGraph) | Full control, no framework lock-in |
| LLM Abstraction | Adapter pattern | Clean interface, easy to add providers |
| API Framework | FastAPI | Async, typed, SSE support, auto-docs |
| Chunking | Recursive text splitter | Preserves semantic boundaries |
| Embedding | Provider-agnostic | Falls back to local if API unavailable |

## Tradeoffs Acknowledged

- **ChromaDB vs Pinecone**: ChromaDB chosen for zero-setup; swap `vectorstore.py` for production scale
- **Custom agents vs LangGraph**: Custom gives transparency; LangGraph better for complex graphs
- **Sync vs Async**: Full async for I/O bound tool calls; agents are sync-compatible
- **Mock tools vs Real APIs**: Mock implementations provided; real connectors toggle via env vars

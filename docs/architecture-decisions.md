# Architecture Decision Records (ADRs)

## ADR-001: Vector Database Selection

**Status:** Accepted  
**Date:** 2024-01

### Context
We needed a vector database for semantic search over engineering documentation.
Options evaluated: Pinecone, Qdrant, Weaviate, ChromaDB, PGVector.

### Decision
Use **ChromaDB** for the prototype.

### Rationale
- Zero infrastructure: file-based persistence, no separate server
- Python-native client with async support
- Easy to swap: our `VectorStore` class abstracts the interface
- Sufficient for prototype scale (<1M chunks)

### Consequences
- **Good:** Zero setup, works out of the box
- **Bad:** Not suitable for production scale, no built-in replication
- **Migration path:** Replace `vectorstore.py` with Qdrant or Pinecone adapter when scaling

---

## ADR-002: Agent Architecture — Custom vs Framework

**Status:** Accepted  
**Date:** 2024-01

### Context
We needed a multi-agent orchestration system. Options: LangGraph, CrewAI, AutoGen, custom.

### Decision
Use a **custom orchestrator** inspired by LangGraph concepts.

### Rationale
- Full control over agent communication and error handling
- No framework version pinning or breaking changes
- Transparent: easy to understand, debug, and explain
- The pipeline is linear (Planner→Research→Analysis→QA→Summary), not a complex DAG

### Consequences
- **Good:** Simple, debuggable, no hidden magic
- **Bad:** More code to maintain, no community plugins
- **Migration path:** Each agent implements a standard `run(context) → AgentStep` interface — easy to wrap with LangGraph later

---

## ADR-003: LLM Provider Strategy

**Status:** Accepted  
**Date:** 2024-01

### Context
We need to support multiple LLM providers and handle failures gracefully.

### Decision
Implement an **Adapter pattern** with a **fallback chain**.

### Design
```
LLMRouter
  ├── Primary provider (configurable via LLM_PROVIDER env)
  ├── Task-based routing (code_analysis → Anthropic, research → Gemini)
  ├── Retry: exponential backoff, max 3 attempts per provider
  └── Fallback: tries next provider in chain on failure
```

### Consequences
- **Good:** Resilient, cost-optimizable, provider-agnostic application code
- **Bad:** Slight latency overhead on fallback scenarios
- **Trade-off:** We accept eventual consistency in provider capability (different models may produce different quality answers)

---

## ADR-004: Security Model

**Status:** Accepted  
**Date:** 2024-01

### Threat Model
1. Prompt injection via user input
2. Tool execution abuse (filesystem, DB)
3. Secret leakage in tool outputs
4. Unauthorized access to tool endpoints

### Mitigations
| Threat | Mitigation |
|--------|------------|
| Prompt injection | Pattern-based detection on all inputs (`injection_guard.py`) |
| Tool abuse | Filesystem sandboxed to allowed dirs; DB restricted to SELECT only |
| Secret leakage | Output scrubbing with regex patterns for common secret formats |
| API access | Rate limiting middleware (future: JWT auth on API endpoints) |

### Acknowledged Risks
- Pattern-based injection detection has false negatives. Production should add LLM-based classification.
- Mock tools don't exercise real security boundaries. Real tool integrations need additional sandboxing.

---

## ADR-005: RAG Relevance Threshold

**Status:** Accepted  
**Date:** 2024-01

### Context
When should the system answer "I don't know" vs. attempt an answer?

### Decision
Use a **cosine similarity threshold of 0.35** (ChromaDB cosine distance converted to similarity).

### Rationale
- Below 0.35: retrieved chunks are unlikely to be relevant → return "I don't have enough information"
- Prevents hallucination on out-of-domain questions
- 0.35 is conservative; tunable via environment variable in production

### Consequences
- May return "I don't know" for questions that are loosely related to documentation
- Explicitly correct behavior: better to admit ignorance than hallucinate

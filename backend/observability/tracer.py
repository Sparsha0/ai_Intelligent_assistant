"""
Observability - Structured logging and request tracing.
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

import structlog

# Context var for correlation ID (propagated through async calls)
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
_token_tracker: ContextVar[dict] = ContextVar("token_tracker", default={})


def configure_logging(level: str = "INFO", json_output: bool = False):
    """Configure structured logging."""
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_output:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    return structlog.get_logger(name)


@dataclass
class TraceSpan:
    """A single traced operation."""
    name: str
    trace_id: str
    parent_id: str | None
    start_time: float
    end_time: float | None = None
    attributes: dict = field(default_factory=dict)
    error: str | None = None

    @property
    def duration_ms(self) -> float:
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "duration_ms": round(self.duration_ms, 2),
            "attributes": self.attributes,
            "error": self.error,
        }


class RequestTracer:
    """
    Simple request tracer.
    In production, replace with OpenTelemetry.
    """

    def __init__(self):
        self._traces: list[TraceSpan] = []
        self.logger = get_logger("tracer")

    def start_request(self, user_query: str) -> str:
        """Start a new request trace. Returns correlation ID."""
        correlation_id = str(uuid.uuid4())[:12]
        _correlation_id.set(correlation_id)
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)
        self.logger.info("request_start", query_preview=user_query[:80])
        return correlation_id

    @asynccontextmanager
    async def span(self, name: str, **attributes):
        """Context manager for tracing an operation."""
        span = TraceSpan(
            name=name,
            trace_id=_correlation_id.get() or "none",
            parent_id=None,
            start_time=time.time(),
            attributes=attributes,
        )
        try:
            yield span
            span.end_time = time.time()
            self.logger.debug("span_complete", span=name, duration_ms=round(span.duration_ms, 1))
        except Exception as e:
            span.end_time = time.time()
            span.error = str(e)
            self.logger.error("span_error", span=name, error=str(e))
            raise
        finally:
            self._traces.append(span)

    def get_summary(self) -> list[dict]:
        return [t.to_dict() for t in self._traces[-50:]]  # Last 50 spans


class TokenUsageTracker:
    """Track token usage across requests."""

    def __init__(self):
        self._usage: dict[str, int] = {
            "total_input": 0,
            "total_output": 0,
            "total_requests": 0,
        }

    def record(self, input_tokens: int, output_tokens: int, provider: str = ""):
        self._usage["total_input"] += input_tokens
        self._usage["total_output"] += output_tokens
        self._usage["total_requests"] += 1

    def summary(self) -> dict:
        total = self._usage["total_input"] + self._usage["total_output"]
        return {
            **self._usage,
            "total_tokens": total,
            "estimated_cost_usd": round(total * 0.000003, 4),  # ~$3/1M tokens average
        }


# Singletons
_tracer: RequestTracer | None = None
_token_tracker_singleton: TokenUsageTracker | None = None


def get_tracer() -> RequestTracer:
    global _tracer
    if _tracer is None:
        _tracer = RequestTracer()
    return _tracer


def get_token_tracker() -> TokenUsageTracker:
    global _token_tracker_singleton
    if _token_tracker_singleton is None:
        _token_tracker_singleton = TokenUsageTracker()
    return _token_tracker_singleton

"""
LMIS Structured Logging
=======================
Configures structlog with:
- JSON renderer in production
- Pretty ConsoleRenderer in development
- request_id context variable injected automatically
"""
from __future__ import annotations

import logging
import sys
from contextvars import ContextVar
from typing import Any, MutableMapping
from uuid import uuid4

import structlog
from structlog.types import EventDict, WrappedLogger

# ─── Context Variable ─────────────────────────────────────────────────────────
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the current request_id from context, generating one if absent."""
    rid = request_id_var.get()
    if not rid:
        rid = str(uuid4())
        request_id_var.set(rid)
    return rid


def set_request_id(request_id: str) -> None:
    """Set the request_id in the current async context."""
    request_id_var.set(request_id)


# ─── Custom Processors ────────────────────────────────────────────────────────

def inject_request_id(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Inject the current request_id into every log event."""
    event_dict["request_id"] = get_request_id()
    return event_dict


def add_app_context(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Add static application context fields."""
    event_dict.setdefault("app", "lmis")
    return event_dict


def drop_color_message_key(
    logger: WrappedLogger,
    method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Remove uvicorn's 'color_message' duplicate key before serialisation."""
    event_dict.pop("color_message", None)
    return event_dict


# ─── Setup Function ───────────────────────────────────────────────────────────

def setup_logging(app_env: str = "development", log_level: str = "INFO") -> None:
    """Configure structlog and stdlib logging.

    Parameters
    ----------
    app_env:
        One of ``"development"``, ``"staging"``, or ``"production"``.
    log_level:
        Standard Python log level string.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        inject_request_id,
        add_app_context,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        drop_color_message_key,
    ]

    if app_env == "production":
        # JSON output suitable for log-aggregation systems (Loki, ELK, Datadog)
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        # Human-friendly colour output during local development
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(log_level)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(log_level)

    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "asyncio", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Return a bound structlog logger.

    Usage::

        log = get_logger(__name__)
        log.info("event", key="value")
    """
    return structlog.get_logger(name)

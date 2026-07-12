"""
OptiTrade — Logging Configuration
===================================
Provides structured JSON logging for production and human-readable
formatting for development.

Call setup_logging() exactly once at application startup (main.py).
All other modules obtain loggers via logging.getLogger(__name__).
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any


class _JSONFormatter(logging.Formatter):
    """Emit one JSON object per log line for easy parsing in log aggregators."""

    _EXTRA_FIELDS = (
        "request_id", "path", "method", "status_code",
        "duration_ms", "symbol", "uid",
    )

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts":      datetime.now(timezone.utc).isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "msg":     record.getMessage(),
        }
        # Include any extra structured fields the caller attached
        for field in self._EXTRA_FIELDS:
            if hasattr(record, field):
                entry[field] = getattr(record, field)
        # Exceptions
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(debug: bool = False, log_level: str = "INFO") -> None:
    """
    Configure root logger.  Call once at startup.

    In debug mode: human-readable with colors (uses uvicorn defaults if available).
    In production: JSON lines to stdout.
    """
    level = logging.DEBUG if debug else getattr(logging, log_level.upper(), logging.INFO)

    if debug:
        fmt = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
        formatter: logging.Formatter = logging.Formatter(fmt, datefmt="%H:%M:%S")
    else:
        formatter = _JSONFormatter()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Suppress chatty third-party loggers
    for name in ("uvicorn.access", "yfinance", "peewee", "urllib3", "httpx"):
        logging.getLogger(name).setLevel(logging.WARNING)

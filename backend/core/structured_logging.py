"""
OptiTrade — Structured Logging Helper
========================================
A single, reusable way to emit machine-readable log events, instead of
ad-hoc f-string log lines scattered per call site. Every event is a flat
JSON object with a fixed set of well-known keys (timestamp, component,
module, operation, status, and — where applicable — symbol,
execution_time_ms, error_type), so a future log shipper/observability
pipeline can parse every event emitted through this helper the same way,
regardless of which module produced it.

Deliberately excludes user-facing text: no LLM commentary, trader
narratives, or other natural-language explanations belong in a structured
event — this is operational telemetry (what ran, on what, how long it
took, whether it succeeded), not user-facing content. Only structured,
typed values (numbers, short status codes, symbol identifiers) should be
passed as extra fields.

This module only adds a logging helper; it does not configure any
handler/formatter globally (main.py's existing `logging.basicConfig(...)`
is untouched). Each event is serialized to a JSON string and passed as
the log message body, so it is machine-readable in whatever log sink is
already configured today, without requiring any change to that sink.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Conventional `status` values. Not enforced (this stays a thin logging
# helper, not a new validation layer) - documented here for consistency
# across call sites.
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_SKIPPED = "skipped"


def log_event(
    logger: logging.Logger,
    *,
    component: str,
    module: str,
    operation: str,
    status: str,
    symbol: Optional[str] = None,
    execution_time_ms: Optional[float] = None,
    error_type: Optional[str] = None,
    level: int = logging.INFO,
    **extra_fields: Any,
) -> None:
    """Logs one structured, machine-readable event as a JSON log line.

    Required fields: timestamp (added automatically, UTC ISO-8601),
    component, module, operation, status.
    Optional fields (included only when given, per-field, not all-or-
    nothing): symbol, execution_time_ms, error_type.
    Any additional keyword arguments are included as-is (e.g. numeric
    scores/counters) - never pass free-text narrative through
    `extra_fields`.
    """
    record: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "component": component,
        "module": module,
        "operation": operation,
        "status": status,
    }
    if symbol is not None:
        record["symbol"] = symbol
    if execution_time_ms is not None:
        record["execution_time_ms"] = round(execution_time_ms, 3)
    if error_type is not None:
        record["error_type"] = error_type
    record.update(extra_fields)

    logger.log(level, json.dumps(record, default=str))

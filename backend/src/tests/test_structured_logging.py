"""
Tests for core/structured_logging.py — the shared structured-event
logging helper introduced in Sprint 1 Task 8. Verifies each event is
valid, parseable JSON containing exactly the documented fields (present
only when applicable), and that it never silently drops the required
core fields (timestamp, component, module, operation, status).
"""
import json
import logging

from core.structured_logging import STATUS_ERROR, STATUS_SUCCESS, log_event


def test_log_event_emits_valid_json_with_required_fields(caplog):
    logger = logging.getLogger("test.structured_logging")
    with caplog.at_level(logging.INFO, logger="test.structured_logging"):
        log_event(
            logger,
            component="scoring_engine",
            module="core.scoring",
            operation="get_decision",
            status=STATUS_SUCCESS,
        )

    assert len(caplog.records) == 1
    record = json.loads(caplog.records[0].message)
    assert record["component"] == "scoring_engine"
    assert record["module"] == "core.scoring"
    assert record["operation"] == "get_decision"
    assert record["status"] == "success"
    assert "timestamp" in record
    # Optional fields not passed must not appear at all, rather than being
    # present with a null/None placeholder value.
    assert "symbol" not in record
    assert "execution_time_ms" not in record
    assert "error_type" not in record


def test_log_event_includes_optional_fields_only_when_given(caplog):
    logger = logging.getLogger("test.structured_logging")
    with caplog.at_level(logging.INFO, logger="test.structured_logging"):
        log_event(
            logger,
            component="v2_engine",
            module="v2.core.engine",
            operation="analyze",
            status=STATUS_SUCCESS,
            symbol="BTC-USD",
            execution_time_ms=12.3456,
        )

    record = json.loads(caplog.records[0].message)
    assert record["symbol"] == "BTC-USD"
    assert record["execution_time_ms"] == 12.346  # rounded to 3 decimals
    assert "error_type" not in record


def test_log_event_error_status_includes_error_type(caplog):
    logger = logging.getLogger("test.structured_logging")
    with caplog.at_level(logging.WARNING, logger="test.structured_logging"):
        log_event(
            logger,
            component="scoring_engine",
            module="core.scoring",
            operation="session_adjustment",
            status=STATUS_ERROR,
            error_type="RuntimeError",
            level=logging.WARNING,
        )

    record = json.loads(caplog.records[0].message)
    assert record["status"] == "error"
    assert record["error_type"] == "RuntimeError"
    assert caplog.records[0].levelno == logging.WARNING


def test_log_event_extra_fields_are_included_as_structured_data(caplog):
    logger = logging.getLogger("test.structured_logging")
    with caplog.at_level(logging.INFO, logger="test.structured_logging"):
        log_event(
            logger,
            component="v2_engine",
            module="v2.core.engine",
            operation="analyze",
            status=STATUS_SUCCESS,
            aggregated_score=0.42,
            confidence=0.8,
        )

    record = json.loads(caplog.records[0].message)
    assert record["aggregated_score"] == 0.42
    assert record["confidence"] == 0.8


def test_log_event_timestamp_is_utc_iso8601(caplog):
    logger = logging.getLogger("test.structured_logging")
    with caplog.at_level(logging.INFO, logger="test.structured_logging"):
        log_event(
            logger, component="c", module="m", operation="o", status=STATUS_SUCCESS,
        )

    from datetime import datetime

    record = json.loads(caplog.records[0].message)
    parsed = datetime.fromisoformat(record["timestamp"])
    assert parsed.tzinfo is not None  # timezone-aware, not naive

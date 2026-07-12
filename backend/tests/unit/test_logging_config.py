"""Unit tests for core/logging_config.py."""
import json
import logging
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

from core.logging_config import setup_logging, _JSONFormatter


class TestJSONFormatter:
    def _make_record(self, msg="hello", level=logging.INFO, **extra):
        record = logging.LogRecord(
            name="test", level=level, pathname="", lineno=0,
            msg=msg, args=(), exc_info=None,
        )
        for k, v in extra.items():
            setattr(record, k, v)
        return record

    def test_output_is_valid_json(self):
        fmt = _JSONFormatter()
        record = self._make_record("test message")
        output = fmt.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_required_fields_present(self):
        fmt = _JSONFormatter()
        record = self._make_record("test message")
        parsed = json.loads(fmt.format(record))
        assert "ts" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "msg" in parsed

    def test_message_matches(self):
        fmt = _JSONFormatter()
        record = self._make_record("my message")
        parsed = json.loads(fmt.format(record))
        assert parsed["msg"] == "my message"

    def test_extra_fields_included(self):
        fmt = _JSONFormatter()
        record = self._make_record("msg", request_id="abc123", path="/analyze")
        parsed = json.loads(fmt.format(record))
        assert parsed["request_id"] == "abc123"
        assert parsed["path"] == "/analyze"

    def test_unknown_extra_fields_not_included(self):
        fmt = _JSONFormatter()
        record = self._make_record("msg", unknown_field="surprise")
        parsed = json.loads(fmt.format(record))
        assert "unknown_field" not in parsed

    def test_level_names_correct(self):
        fmt = _JSONFormatter()
        for level, expected in [(logging.DEBUG, "DEBUG"), (logging.ERROR, "ERROR")]:
            record = self._make_record("m", level=level)
            parsed = json.loads(fmt.format(record))
            assert parsed["level"] == expected


class TestSetupLogging:
    def test_setup_does_not_raise_production(self):
        setup_logging(debug=False, log_level="INFO")

    def test_setup_does_not_raise_debug(self):
        setup_logging(debug=True)

    def test_setup_sets_root_level_info(self):
        setup_logging(debug=False, log_level="INFO")
        assert logging.getLogger().level == logging.INFO

    def test_setup_sets_root_level_debug(self):
        setup_logging(debug=True)
        assert logging.getLogger().level == logging.DEBUG

    def test_setup_sets_custom_level(self):
        setup_logging(debug=False, log_level="WARNING")
        assert logging.getLogger().level == logging.WARNING

    def test_handler_present_after_setup(self):
        setup_logging(debug=False)
        assert len(logging.getLogger().handlers) >= 1

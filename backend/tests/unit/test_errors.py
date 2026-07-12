"""Unit tests for core/errors.py."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import pytest
from core.errors import (
    OptiTradeError, SymbolNotFoundError, InsufficientDataError,
    DataProviderError, ProviderNotConfiguredError, AnalysisError,
    ValidationError, AuthenticationError, AuthorizationError, RateLimitError,
)


class TestErrorHierarchy:
    def test_all_inherit_from_optitrade_error(self):
        for cls in (
            SymbolNotFoundError, InsufficientDataError, DataProviderError,
            ProviderNotConfiguredError, AnalysisError, ValidationError,
            AuthenticationError, AuthorizationError, RateLimitError,
        ):
            assert issubclass(cls, OptiTradeError), f"{cls} must inherit OptiTradeError"

    def test_all_inherit_from_exception(self):
        assert issubclass(OptiTradeError, Exception)

    def test_status_codes(self):
        cases = {
            SymbolNotFoundError:        404,
            InsufficientDataError:      422,
            DataProviderError:          503,
            ProviderNotConfiguredError: 503,
            AnalysisError:              500,
            ValidationError:            400,
            AuthenticationError:        401,
            AuthorizationError:         403,
            RateLimitError:             429,
        }
        for cls, expected_code in cases.items():
            assert cls.status_code == expected_code, \
                f"{cls.__name__}.status_code expected {expected_code}, got {cls.status_code}"

    def test_error_codes_are_strings(self):
        for cls in (
            SymbolNotFoundError, InsufficientDataError, DataProviderError,
            ProviderNotConfiguredError, AnalysisError, ValidationError,
            AuthenticationError, AuthorizationError, RateLimitError,
        ):
            assert isinstance(cls.error_code, str)
            assert len(cls.error_code) > 0


class TestOptiTradeError:
    def test_message_stored(self):
        err = OptiTradeError("something went wrong")
        assert err.message == "something went wrong"

    def test_details_defaults_to_empty_dict(self):
        err = OptiTradeError("msg")
        assert err.details == {}

    def test_details_stored(self):
        err = OptiTradeError("msg", details={"symbol": "AAPL"})
        assert err.details["symbol"] == "AAPL"

    def test_to_dict_keys(self):
        err = OptiTradeError("msg", details={"x": 1})
        d = err.to_dict()
        assert set(d.keys()) == {"error", "message", "details"}

    def test_to_dict_values(self):
        err = SymbolNotFoundError("AAPL not found", details={"symbol": "AAPL"})
        d = err.to_dict()
        assert d["error"]   == "SYMBOL_NOT_FOUND"
        assert d["message"] == "AAPL not found"
        assert d["details"]["symbol"] == "AAPL"

    def test_is_catchable_as_exception(self):
        with pytest.raises(Exception):
            raise SymbolNotFoundError("test")

    def test_is_catchable_as_optitrade_error(self):
        with pytest.raises(OptiTradeError):
            raise DataProviderError("network error")

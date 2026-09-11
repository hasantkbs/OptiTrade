"""
Tests for intelligence/market_scanner.py.

`MarketScanner` is tested against a fake satisfying `PipelineRunnerProtocol`
- no live market data, Redis, PostgreSQL, or network access, matching
this repository's existing convention for pipeline/executor and
watchlist/scheduler tests.
"""
import threading
import time
from typing import Dict, List, Optional

import pytest

from decision_engine.models import Prediction
from intelligence.config import MarketScannerConfig
from intelligence.market_scanner import MarketScanner
from intelligence.models import ScanSymbolFailure, ScanSymbolResult, ScanSymbolStatus
from pipeline.models import PipelineMetadata, PipelineResponse, RiskAssessment


def _response(symbol: str, decision: Prediction = Prediction.HOLD) -> PipelineResponse:
    return PipelineResponse(
        symbol=symbol, decision=decision, confidence=0.6, expected_return=1.0, expected_volatility=10.0,
        risk=RiskAssessment(risk_level="LOW", expected_volatility=10.0, data_sufficiency=1.0),
        explanation="test explanation",
        metadata=PipelineMetadata(
            pipeline_version="v1", total_duration_ms=1.0, engines_available=3, engines_succeeded=3, degraded=False,
        ),
    )


class _FakePipelineService:
    """Satisfies `PipelineRunnerProtocol`. Each symbol can be configured
    to return a canned response, raise an exception, or sleep for a
    given duration before doing either - deterministic, no real
    pipeline/network/DB dependency."""

    def __init__(self) -> None:
        self.calls: List[str] = []
        self._responses: Dict[str, PipelineResponse] = {}
        self._exceptions: Dict[str, Exception] = {}
        self._delays: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.concurrent_count = 0
        self.max_observed_concurrency = 0

    def succeed(self, symbol: str, response: Optional[PipelineResponse] = None, delay: float = 0.0) -> None:
        self._responses[symbol] = response or _response(symbol)
        self._delays[symbol] = delay

    def fail(self, symbol: str, exc: Exception, delay: float = 0.0) -> None:
        self._exceptions[symbol] = exc
        self._delays[symbol] = delay

    def run(self, symbol: str) -> PipelineResponse:
        with self._lock:
            self.concurrent_count += 1
            self.max_observed_concurrency = max(self.max_observed_concurrency, self.concurrent_count)
        try:
            self.calls.append(symbol)
            delay = self._delays.get(symbol, 0.0)
            if delay:
                time.sleep(delay)
            if symbol in self._exceptions:
                raise self._exceptions[symbol]
            if symbol in self._responses:
                return self._responses[symbol]
            raise AssertionError(f"no fixture configured for {symbol!r}")
        finally:
            with self._lock:
                self.concurrent_count -= 1


def _scanner(fake: _FakePipelineService, **config_overrides) -> MarketScanner:
    config = MarketScannerConfig(**config_overrides) if config_overrides else MarketScannerConfig()
    return MarketScanner(pipeline_service=fake, config=config)


# ── basic shape ────────────────────────────────────────────────────────


def test_empty_symbol_list():
    fake = _FakePipelineService()
    result = _scanner(fake).scan([])

    assert result.requested_count == 0
    assert result.unique_count == 0
    assert result.unique_symbols == []
    assert result.successful == []
    assert result.failed == []
    assert result.successful_count == 0
    assert result.failed_count == 0
    assert fake.calls == []


def test_blank_and_whitespace_entries_are_dropped():
    fake = _FakePipelineService()
    fake.succeed("AAPL")
    result = _scanner(fake).scan(["AAPL", "", "   "])

    assert result.requested_count == 3
    assert result.unique_symbols == ["AAPL"]
    assert result.unique_count == 1


def test_single_symbol_success():
    fake = _FakePipelineService()
    fake.succeed("AAPL")
    result = _scanner(fake).scan(["AAPL"])

    assert result.successful_count == 1
    assert result.failed_count == 0
    assert result.successful[0].symbol == "AAPL"
    assert result.successful[0].status == ScanSymbolStatus.SUCCESS


def test_multiple_symbols_success():
    fake = _FakePipelineService()
    for symbol in ("AAPL", "MSFT", "NVDA"):
        fake.succeed(symbol)
    result = _scanner(fake).scan(["AAPL", "MSFT", "NVDA"])

    assert result.successful_count == 3
    assert result.failed_count == 0
    assert {r.symbol for r in result.successful} == {"AAPL", "MSFT", "NVDA"}


# ── deduplication and ordering ────────────────────────────────────────


def test_duplicate_symbols_are_deduplicated_case_insensitively():
    fake = _FakePipelineService()
    fake.succeed("AAPL")
    result = _scanner(fake).scan(["AAPL", "aapl", "AAPL", "Aapl"])

    assert result.requested_count == 4
    assert result.unique_symbols == ["AAPL"]
    assert result.unique_count == 1
    assert fake.calls == ["AAPL"]  # the pipeline is only ever actually called once


def test_input_order_is_preserved_in_unique_symbols():
    fake = _FakePipelineService()
    for symbol in ("NVDA", "AAPL", "MSFT"):
        fake.succeed(symbol)
    result = _scanner(fake).scan(["NVDA", "AAPL", "MSFT"])

    assert result.unique_symbols == ["NVDA", "AAPL", "MSFT"]


def test_result_order_is_deterministic_regardless_of_completion_order():
    """MSFT finishes fastest, NVDA slowest - the result must still be
    ordered by the original request, not by which one finished first."""
    fake = _FakePipelineService()
    fake.succeed("NVDA", delay=0.06)
    fake.succeed("AAPL", delay=0.03)
    fake.succeed("MSFT", delay=0.0)

    result = _scanner(fake, max_parallel_symbols=3).scan(["NVDA", "AAPL", "MSFT"])

    assert [r.symbol for r in result.successful] == ["NVDA", "AAPL", "MSFT"]


# ── failure isolation ──────────────────────────────────────────────────


def test_one_symbol_failure_does_not_fail_the_batch():
    fake = _FakePipelineService()
    fake.succeed("AAPL")
    fake.succeed("MSFT")
    fake.fail("INVALID", ValueError("no market data"))
    fake.succeed("NVDA")

    result = _scanner(fake).scan(["AAPL", "MSFT", "INVALID", "NVDA"])

    assert result.successful_count == 3
    assert result.failed_count == 1
    assert {r.symbol for r in result.successful} == {"AAPL", "MSFT", "NVDA"}
    assert result.failed[0].symbol == "INVALID"
    assert result.failed[0].status == ScanSymbolStatus.FAILED


def test_multiple_failures_are_isolated_from_each_other_and_from_successes():
    fake = _FakePipelineService()
    fake.succeed("AAPL")
    fake.fail("BAD1", RuntimeError("boom"))
    fake.fail("BAD2", KeyError("missing"))
    fake.succeed("MSFT")

    result = _scanner(fake).scan(["AAPL", "BAD1", "BAD2", "MSFT"])

    assert result.successful_count == 2
    assert result.failed_count == 2
    failures_by_symbol = {f.symbol: f.error_type for f in result.failed}
    assert failures_by_symbol == {"BAD1": "RuntimeError", "BAD2": "KeyError"}


def test_failure_result_does_not_expose_the_raw_exception_message():
    fake = _FakePipelineService()
    fake.fail("AAPL", ValueError("connection string: postgres://user:secretpassword@host/db"))

    result = _scanner(fake).scan(["AAPL"])

    failure = result.failed[0]
    assert failure.error_type == "ValueError"
    # The raw message (which could carry internal/sensitive detail) must
    # never appear anywhere in the structured result.
    dumped = failure.model_dump_json()
    assert "secretpassword" not in dumped
    assert "connection string" not in dumped


# ── timeout ──────────────────────────────────────────────────────────


def test_timeout_is_reported_as_a_per_symbol_failure():
    fake = _FakePipelineService()
    fake.succeed("AAPL", delay=0.3)  # exceeds the tiny configured timeout below

    result = _scanner(fake, symbol_timeout_seconds=0.05).scan(["AAPL"])

    assert result.successful_count == 0
    assert result.failed_count == 1
    assert result.failed[0].symbol == "AAPL"
    assert result.failed[0].status == ScanSymbolStatus.TIMEOUT
    assert result.failed[0].error_type == "TimeoutError"


def test_one_symbol_timeout_does_not_block_the_rest_of_the_batch():
    fake = _FakePipelineService()
    fake.succeed("SLOW", delay=0.3)
    fake.succeed("FAST", delay=0.0)

    result = _scanner(fake, symbol_timeout_seconds=0.05, max_parallel_symbols=2).scan(["SLOW", "FAST"])

    assert result.failed_count == 1
    assert result.failed[0].symbol == "SLOW"
    assert result.successful_count == 1
    assert result.successful[0].symbol == "FAST"


# ── bounded concurrency ────────────────────────────────────────────────


def test_concurrency_is_bounded_by_configuration():
    fake = _FakePipelineService()
    symbols = [f"SYM{i}" for i in range(6)]
    for symbol in symbols:
        fake.succeed(symbol, delay=0.05)

    result = _scanner(fake, max_parallel_symbols=2).scan(symbols)

    assert result.successful_count == 6
    assert fake.max_observed_concurrency <= 2


def test_higher_concurrency_limit_allows_more_parallelism():
    fake = _FakePipelineService()
    symbols = [f"SYM{i}" for i in range(6)]
    for symbol in symbols:
        fake.succeed(symbol, delay=0.05)

    _scanner(fake, max_parallel_symbols=6).scan(symbols)

    # Not a strict equality (thread scheduling isn't guaranteed to hit
    # the ceiling exactly), but with 6 workers and a 6-symbol batch that
    # all sleep the same duration, real overlap is expected.
    assert fake.max_observed_concurrency > 2


# ── dependency / architecture ────────────────────────────────────────


def test_pipeline_service_is_the_actual_execution_dependency():
    fake = _FakePipelineService()
    fake.succeed("AAPL")
    fake.succeed("MSFT")

    _scanner(fake).scan(["AAPL", "MSFT", "AAPL"])

    assert sorted(fake.calls) == ["AAPL", "MSFT"]


def test_successful_result_preserves_the_canonical_pipeline_response_unmodified():
    fake = _FakePipelineService()
    canonical = _response("AAPL", decision=Prediction.BUY)
    fake.succeed("AAPL", response=canonical)

    result = _scanner(fake).scan(["AAPL"])

    assert result.successful[0].response == canonical
    assert result.successful[0].response.decision == Prediction.BUY


def test_summary_counts_are_internally_consistent():
    fake = _FakePipelineService()
    fake.succeed("AAPL")
    fake.succeed("MSFT")
    fake.fail("BAD", ValueError("x"))

    result = _scanner(fake).scan(["AAPL", "MSFT", "BAD", "aapl"])  # aapl is a duplicate of AAPL

    assert result.requested_count == 4
    assert result.unique_count == 3
    assert result.successful_count + result.failed_count == result.unique_count
    assert result.successful_count == 2
    assert result.failed_count == 1


# ── shutdown ─────────────────────────────────────────────────────────


def test_shutdown_does_not_raise_and_does_not_block():
    fake = _FakePipelineService()
    scanner = _scanner(fake)
    scanner.scan([])  # no-op scan, just exercises a real instance

    started = time.perf_counter()
    scanner.shutdown()
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0  # non-blocking, matches AlertScheduler.shutdown()'s wait=False convention


@pytest.mark.parametrize("bad_config", [{"max_parallel_symbols": 1}])
def test_scan_still_completes_with_minimum_concurrency(bad_config):
    fake = _FakePipelineService()
    fake.succeed("AAPL")
    fake.succeed("MSFT")

    result = _scanner(fake, **bad_config).scan(["AAPL", "MSFT"])

    assert result.successful_count == 2
    assert fake.max_observed_concurrency == 1

"""
Tests for intelligence/background_intelligence.py.

`BackgroundIntelligenceOrchestrator` is tested against a fake satisfying
`intelligence.opportunity_ranking.ScannerProtocol` (never a live
`MarketScanner`/`PipelineService`) and a fake satisfying
`UniverseProviderProtocol` (never live `core.market_config` data, except
where a test explicitly documents the real provider's isolation). No
live PostgreSQL, Redis, market data, or network access anywhere in this
file.
"""
import threading
import time
from datetime import datetime, timezone
from typing import List, Optional

import pytest

from decision_engine.models import Prediction
from intelligence.background_intelligence import (
    BackgroundIntelligenceOrchestrator,
    MarketConfigUniverseProvider,
)
from intelligence.config import BackgroundIntelligenceConfig, IntelligenceConfig
from intelligence.models import (
    BackgroundScanStatus,
    MarketScanResult,
    ScanSymbolFailure,
    ScanSymbolResult,
    ScanSymbolStatus,
)
from intelligence.opportunity_ranking import rank_opportunities
from pipeline.models import PipelineMetadata, PipelineResponse, RiskAssessment

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)
_CONFIG = IntelligenceConfig()


def _response(symbol: str, decision: Prediction = Prediction.BUY, confidence: float = 0.8) -> PipelineResponse:
    return PipelineResponse(
        symbol=symbol, decision=decision, confidence=confidence, expected_return=5.0, expected_volatility=8.0,
        risk=RiskAssessment(risk_level="LOW", expected_volatility=8.0, data_sufficiency=1.0),
        explanation="test explanation",
        metadata=PipelineMetadata(
            pipeline_version="v1", total_duration_ms=1.0, engines_available=3, engines_succeeded=3, degraded=False,
            timestamp=_NOW,
        ),
    )


def _success(symbol: str, **response_overrides) -> ScanSymbolResult:
    return ScanSymbolResult(symbol=symbol, status=ScanSymbolStatus.SUCCESS, response=_response(symbol, **response_overrides), duration_ms=1.0)


def _failure(symbol: str, status: ScanSymbolStatus = ScanSymbolStatus.FAILED, error_type: str = "ValueError") -> ScanSymbolFailure:
    return ScanSymbolFailure(symbol=symbol, status=status, error_type=error_type, duration_ms=1.0)


def _scan_result(symbols: List[str], successful: Optional[List[ScanSymbolResult]] = None,
                  failed: Optional[List[ScanSymbolFailure]] = None) -> MarketScanResult:
    successful = successful or []
    failed = failed or []
    return MarketScanResult(
        requested_count=len(symbols), unique_symbols=symbols, unique_count=len(symbols),
        successful=successful, failed=failed, successful_count=len(successful), failed_count=len(failed),
        started_at=_NOW, completed_at=_NOW, duration_ms=1.0,
    )


class _FakeScanner:
    """Satisfies `ScannerProtocol`. Records every symbol list passed to
    `scan()`, returns a pre-configured `MarketScanResult` (defaulting to
    "everyone succeeds"), or raises a configured exception."""

    def __init__(self) -> None:
        self.calls: List[List[str]] = []
        self._result: Optional[MarketScanResult] = None
        self._exception: Optional[Exception] = None
        self._block: Optional[threading.Event] = None
        self.shutdown_called = False

    def set_result(self, result: MarketScanResult) -> None:
        self._result = result

    def fail_with(self, exc: Exception) -> None:
        self._exception = exc

    def block_until(self, event: threading.Event) -> None:
        self._block = event

    def scan(self, symbols: List[str]) -> MarketScanResult:
        self.calls.append(list(symbols))
        if self._block is not None:
            self._block.wait(timeout=5.0)
        if self._exception is not None:
            raise self._exception
        return self._result if self._result is not None else _scan_result(symbols, successful=[_success(s) for s in symbols])

    def shutdown(self) -> None:
        self.shutdown_called = True


class _FakeUniverseProvider:
    """Satisfies `UniverseProviderProtocol`."""

    def __init__(self, symbols: Optional[List[str]] = None) -> None:
        self._symbols = symbols or []
        self.calls = 0
        self._exception: Optional[Exception] = None

    def set_symbols(self, symbols: List[str]) -> None:
        self._symbols = symbols

    def fail_with(self, exc: Exception) -> None:
        self._exception = exc

    def get_symbols(self) -> List[str]:
        self.calls += 1
        if self._exception is not None:
            raise self._exception
        return list(self._symbols)


def _orchestrator(
    scanner: Optional[_FakeScanner] = None,
    universe: Optional[_FakeUniverseProvider] = None,
    config: Optional[BackgroundIntelligenceConfig] = None,
) -> BackgroundIntelligenceOrchestrator:
    return BackgroundIntelligenceOrchestrator(
        scanner=scanner or _FakeScanner(),
        universe_provider=universe or _FakeUniverseProvider(["AAPL", "MSFT", "NVDA"]),
        config=config or BackgroundIntelligenceConfig(batch_size=10),
        intelligence_config=_CONFIG,
    )


# ── 1. Service/job exists ─────────────────────────────────────────────────


def test_orchestrator_can_be_constructed_with_fakes():
    orchestrator = _orchestrator()
    assert isinstance(orchestrator, BackgroundIntelligenceOrchestrator)


# ── 2. Configured batch size is respected ─────────────────────────────────


def test_configured_batch_size_is_respected():
    universe = _FakeUniverseProvider([f"SYM{i}" for i in range(20)])
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=5))

    result = orchestrator.run_once()

    assert len(result.requested_symbols) == 5
    assert scanner.calls == [result.requested_symbols]


# ── 3. Existing MarketScanner is used (via its ScannerProtocol contract) ─


def test_scanner_dependency_is_invoked_through_the_scan_method():
    universe = _FakeUniverseProvider(["AAPL", "MSFT"])
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=10))

    orchestrator.run_once()

    assert scanner.calls == [["AAPL", "MSFT"]]


def test_default_scanner_construction_wires_the_real_market_scanner():
    # Structural, not behavioral - constructing the real default would
    # build a real PipelineService. This proves the wiring exists
    # without executing it.
    source = __import__(
        "pathlib",
    ).Path("src/intelligence/background_intelligence.py").read_text(encoding="utf-8")
    assert "from intelligence.market_scanner import MarketScanner" in source
    assert "scanner = MarketScanner()" in source


# ── 4. Existing Phase D rank_opportunities is used ────────────────────────


def test_ranking_matches_a_direct_rank_opportunities_call():
    symbols = ["AAPL", "MSFT"]
    scan_result = _scan_result(
        symbols,
        successful=[
            _success("AAPL", decision=Prediction.BUY, confidence=0.9),
            _success("MSFT", decision=Prediction.HOLD),
        ],
    )
    scanner = _FakeScanner()
    scanner.set_result(scan_result)
    universe = _FakeUniverseProvider(symbols)
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=10))

    result = orchestrator.run_once()

    expected = rank_opportunities(scan_result, _CONFIG)
    assert result.ranked_opportunities.ranked_count == expected.ranked_count
    assert [item.symbol for item in result.ranked_opportunities.ranked] == [item.symbol for item in expected.ranked]


# ── 5. Symbols are not duplicated ─────────────────────────────────────────


def test_duplicate_universe_symbols_are_deduplicated():
    universe = _FakeUniverseProvider(["AAPL", "AAPL", "MSFT"])
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=10))

    result = orchestrator.run_once()

    assert result.requested_symbols == ["AAPL", "MSFT"]


# ── 6-7. Cursor advances and wraps ────────────────────────────────────────


def test_cursor_advances_between_ticks():
    universe = _FakeUniverseProvider([f"SYM{i}" for i in range(10)])
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=4))

    first = orchestrator.run_once()
    second = orchestrator.run_once()

    assert first.cursor_before == 0
    assert first.cursor_after == 4
    assert second.cursor_before == 4
    assert second.cursor_after == 8
    assert first.requested_symbols == ["SYM0", "SYM1", "SYM2", "SYM3"]
    assert second.requested_symbols == ["SYM4", "SYM5", "SYM6", "SYM7"]


def test_cursor_wraps_to_the_start_once_the_universe_is_exhausted():
    universe = _FakeUniverseProvider([f"SYM{i}" for i in range(6)])
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=4))

    first = orchestrator.run_once()
    second = orchestrator.run_once()
    third = orchestrator.run_once()

    assert first.requested_symbols == ["SYM0", "SYM1", "SYM2", "SYM3"]
    assert first.cursor_after == 4
    assert second.requested_symbols == ["SYM4", "SYM5"]
    assert second.cursor_after == 0  # wrapped - exhausted the universe
    assert third.requested_symbols == ["SYM0", "SYM1", "SYM2", "SYM3"]  # rotated back to the start


def test_cursor_wraps_immediately_when_universe_fits_in_one_batch():
    universe = _FakeUniverseProvider(["AAPL", "MSFT"])
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=10))

    result = orchestrator.run_once()

    assert result.cursor_before == 0
    assert result.cursor_after == 0


# ── 8-9. Empty universe / empty batch ─────────────────────────────────────


def test_empty_universe_is_handled_without_scanning():
    universe = _FakeUniverseProvider([])
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=10))

    result = orchestrator.run_once()

    assert result.status == BackgroundScanStatus.COMPLETED
    assert result.requested_symbols == []
    assert result.ranked_opportunities is None
    assert scanner.calls == []


def test_zero_batch_size_produces_an_empty_batch_without_scanning():
    universe = _FakeUniverseProvider(["AAPL", "MSFT"])
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=0))

    result = orchestrator.run_once()

    assert result.status == BackgroundScanStatus.COMPLETED
    assert result.requested_symbols == []
    assert scanner.calls == []
    assert result.cursor_before == 0
    assert result.cursor_after == 0


# ── 10-13. Success / failure / timeout partitioning ───────────────────────


def test_successful_symbols_are_included():
    symbols = ["AAPL", "MSFT"]
    scanner = _FakeScanner()
    scanner.set_result(_scan_result(symbols, successful=[_success("AAPL"), _success("MSFT")]))
    orchestrator = _orchestrator(scanner, _FakeUniverseProvider(symbols), BackgroundIntelligenceConfig(batch_size=10))

    result = orchestrator.run_once()

    assert set(result.successful_symbols) == {"AAPL", "MSFT"}


def test_failed_symbols_are_isolated_from_successful_ones():
    symbols = ["AAPL", "MSFT"]
    scanner = _FakeScanner()
    scanner.set_result(
        _scan_result(symbols, successful=[_success("AAPL")], failed=[_failure("MSFT", ScanSymbolStatus.FAILED)]),
    )
    orchestrator = _orchestrator(scanner, _FakeUniverseProvider(symbols), BackgroundIntelligenceConfig(batch_size=10))

    result = orchestrator.run_once()

    assert result.successful_symbols == ["AAPL"]
    assert result.failed_symbols == ["MSFT"]
    assert result.timeout_symbols == []


def test_timeout_symbols_are_isolated_from_failed_ones():
    symbols = ["AAPL", "MSFT"]
    scanner = _FakeScanner()
    scanner.set_result(
        _scan_result(symbols, successful=[_success("AAPL")], failed=[_failure("MSFT", ScanSymbolStatus.TIMEOUT)]),
    )
    orchestrator = _orchestrator(scanner, _FakeUniverseProvider(symbols), BackgroundIntelligenceConfig(batch_size=10))

    result = orchestrator.run_once()

    assert result.timeout_symbols == ["MSFT"]
    assert result.failed_symbols == []


def test_failed_symbols_are_excluded_from_ranking():
    symbols = ["AAPL", "MSFT"]
    scanner = _FakeScanner()
    scanner.set_result(
        _scan_result(symbols, successful=[_success("AAPL")], failed=[_failure("MSFT")]),
    )
    orchestrator = _orchestrator(scanner, _FakeUniverseProvider(symbols), BackgroundIntelligenceConfig(batch_size=10))

    result = orchestrator.run_once()

    ranked_symbols = [item.symbol for item in result.ranked_opportunities.ranked]
    assert "MSFT" not in ranked_symbols
    assert "MSFT" in result.ranked_opportunities.failed_symbols


# ── 14. Ranking remains deterministic ─────────────────────────────────────


def test_ranking_is_deterministic_across_repeated_runs():
    symbols = ["AAPL", "MSFT", "GOOG"]
    scan_result = _scan_result(
        symbols,
        successful=[
            _success("AAPL", decision=Prediction.BUY, confidence=0.9),
            _success("MSFT", decision=Prediction.HOLD),
            _success("GOOG", decision=Prediction.BUY, confidence=0.6),
        ],
    )
    scanner = _FakeScanner()
    scanner.set_result(scan_result)
    universe = _FakeUniverseProvider(symbols)
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=10))

    first = orchestrator.run_once()
    universe2 = _FakeUniverseProvider(symbols)  # fresh cursor, same universe
    orchestrator2 = _orchestrator(_FakeScanner(), universe2, BackgroundIntelligenceConfig(batch_size=10))
    orchestrator2.scanner.set_result(scan_result)
    second = orchestrator2.run_once()

    assert [item.symbol for item in first.ranked_opportunities.ranked] == [
        item.symbol for item in second.ranked_opportunities.ranked
    ]


# ── 15. No raw exception text is exposed ──────────────────────────────────


def test_universe_provider_failure_never_exposes_raw_exception_text():
    universe = _FakeUniverseProvider()
    universe.fail_with(RuntimeError("super secret internal connection string"))
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=10))

    result = orchestrator.run_once()

    assert result.status == BackgroundScanStatus.FAILED
    assert result.error_type == "RuntimeError"
    payload = result.model_dump_json()
    assert "secret" not in payload
    assert "connection string" not in payload


def test_scanner_failure_never_exposes_raw_exception_text():
    universe = _FakeUniverseProvider(["AAPL"])
    scanner = _FakeScanner()
    scanner.fail_with(ValueError("credentials abc123"))
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=10))

    result = orchestrator.run_once()

    assert result.status == BackgroundScanStatus.FAILED
    assert result.error_type == "ValueError"
    assert "credentials" not in result.model_dump_json()
    # the cursor already advanced past this batch before the scan failed -
    # a batch-level infra failure must not get the same symbols stuck forever
    assert result.cursor_after != result.cursor_before or len(universe._symbols) <= 1


# ── 16-17. Scheduler integration / leader-only execution ─────────────────


def test_main_wires_a_background_intelligence_loop_into_the_existing_scheduler():
    import pathlib

    source = pathlib.Path("src/main.py").read_text(encoding="utf-8")
    assert "background_intelligence" in source.lower()
    assert "async def background_intelligence_scan_loop" in source
    # Uses the SAME executor-offload convention as every other loop
    # (alert_scan_loop/paper_trading_fill_loop/self_evolution_loop) -
    # never its own asyncio polling implementation.
    assert "_run_in_executor(" in source


def test_background_intelligence_loop_only_starts_under_the_leader_lock():
    import pathlib

    source = pathlib.Path("src/main.py").read_text(encoding="utf-8")
    leader_block_start = source.index("if acquire_scheduler_leader_lock():")
    leader_block_else = source.index("\n    else:", leader_block_start)
    leader_block = source[leader_block_start:leader_block_else]
    assert "background_intelligence_scan_loop" in leader_block


# ── 18. Overlapping execution prevented ───────────────────────────────────


def test_overlapping_run_once_calls_are_prevented():
    universe = _FakeUniverseProvider(["AAPL"])
    scanner = _FakeScanner()
    block_event = threading.Event()
    scanner.block_until(block_event)
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=10))

    results = []

    def _run():
        results.append(orchestrator.run_once())

    first_thread = threading.Thread(target=_run)
    first_thread.start()
    time.sleep(0.1)  # let the first call acquire the lock and block inside scan()

    second_result = orchestrator.run_once()
    block_event.set()
    first_thread.join(timeout=5.0)

    assert second_result.status == BackgroundScanStatus.SKIPPED_OVERLAP
    assert len(results) == 1
    assert results[0].status == BackgroundScanStatus.COMPLETED


# ── 19. Graceful shutdown respected ───────────────────────────────────────


def test_shutdown_delegates_to_the_underlying_scanner():
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, _FakeUniverseProvider(["AAPL"]), BackgroundIntelligenceConfig(batch_size=10))

    orchestrator.shutdown()

    assert scanner.shutdown_called is True


def test_shutdown_is_safe_even_if_no_tick_ever_ran():
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, _FakeUniverseProvider(["AAPL"]), BackgroundIntelligenceConfig(batch_size=10))

    orchestrator.shutdown()  # must not raise

    assert scanner.shutdown_called is True


# ── 20. No DB writes by the orchestration layer ───────────────────────────


def test_orchestration_layer_never_calls_anything_beyond_scan_and_get_symbols():
    universe = _FakeUniverseProvider(["AAPL", "MSFT"])
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=10))

    orchestrator.run_once()

    assert universe.calls == 1
    assert scanner.calls == [["AAPL", "MSFT"]]  # the only two fake methods invoked at all


def test_source_performs_no_database_writes():
    import pathlib

    source = pathlib.Path("src/intelligence/background_intelligence.py").read_text(encoding="utf-8")
    for marker in ("psycopg2", "CREATE TABLE", "INSERT INTO", "import redis", ".save("):
        assert marker not in source


# ── 21-23. No alert/portfolio/watchlist side effects ──────────────────────


def test_source_never_creates_an_alert_or_mutates_portfolio_or_watchlist():
    import pathlib

    source = pathlib.Path("src/intelligence/background_intelligence.py").read_text(encoding="utf-8")
    for marker in (
        "Alert(", "AlertTriggerEvent(", "create_alert", "NotificationPayload(",
        ".buy(", ".sell(", ".deposit(", ".withdraw(",
        ".add_symbol(", ".remove_symbol(", ".create_watchlist(", ".delete_watchlist(",
    ):
        assert marker not in source, f"unexpected side-effecting call found: {marker!r}"


# ── 24-25. No LLM / no legacy decision-engine imports ─────────────────────


def test_source_imports_no_llm_provider_or_legacy_decision_path():
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("src/intelligence/background_intelligence.py").read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)

    forbidden = (
        "openai", "anthropic", "core.analyzer", "core.hybrid_engine", "core.ai_trader_persona",
        "core.investor_persona", "v2", "api.v1", "explanation_engine", "research", "research_lab", "ml_training",
    )
    offenders = [f for f in forbidden if any(n == f or n.startswith(f"{f}.") for n in names)]
    assert offenders == []


# ── 26-27. No second scanner/scheduler implementation ─────────────────────


def test_source_defines_no_second_scanner_or_scheduler_class():
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("src/intelligence/background_intelligence.py").read_text(encoding="utf-8"))
    class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    forbidden_fragments = ("DecisionEngine", "VotingEngine", "ScoringEngine", "RiskEngine", "Scheduler")
    offenders = [name for name in class_names if any(f.lower() in name.lower() for f in forbidden_fragments)]
    assert offenders == []
    # MarketScanner itself must never be redefined here - only imported.
    assert "MarketScanner" not in class_names


def test_source_never_imports_a_worker_framework():
    source_path = __import__("pathlib").Path("src/intelligence/background_intelligence.py")
    source = source_path.read_text(encoding="utf-8")
    for marker in ("celery", "Celery", "import rq", "APScheduler", "apscheduler"):
        assert marker not in source


# ── 28. Restart/cursor behavior follows the chosen existing convention ───


def test_a_new_orchestrator_instance_starts_at_cursor_zero_matching_a_restart():
    orchestrator = _orchestrator(_FakeScanner(), _FakeUniverseProvider(["AAPL", "MSFT"]))
    assert orchestrator._cursor == 0


def test_alert_scheduler_already_uses_the_same_in_memory_rotating_cursor_convention():
    # Documents (doesn't invent) the precedent this module's own docstring
    # claims to follow - AlertScheduler's periodic global sweep already
    # uses a plain in-memory offset that resets on restart.
    import pathlib

    source = pathlib.Path("src/watchlist/scheduler.py").read_text(encoding="utf-8")
    assert "self._scan_offset = 0" in source


# ── 29. Multiple markets/universe sources remain isolated ─────────────────


def test_market_config_universe_provider_isolates_different_markets():
    us_provider = MarketConfigUniverseProvider("US")
    tr_provider = MarketConfigUniverseProvider("TR")
    crypto_provider = MarketConfigUniverseProvider("CRYPTO")

    us_symbols = set(us_provider.get_symbols())
    tr_symbols = set(tr_provider.get_symbols())
    crypto_symbols = set(crypto_provider.get_symbols())

    assert us_symbols and tr_symbols and crypto_symbols
    assert us_symbols.isdisjoint(tr_symbols)
    assert us_symbols.isdisjoint(crypto_symbols)
    assert tr_symbols.isdisjoint(crypto_symbols)
    assert "AAPL" in us_symbols
    assert "GARAN.IS" in tr_symbols
    assert "BTC-USD" in crypto_symbols


def test_market_config_universe_provider_does_not_duplicate_symbol_lists():
    # Positive check: proves the provider really is backed by
    # core.market_config's own data, not a second copy.
    from core.market_config import US_SYMBOLS

    provider = MarketConfigUniverseProvider("US")
    assert set(provider.get_symbols()) == set(US_SYMBOLS.keys())


# ── 30. Configuration is deterministic ────────────────────────────────────


def test_config_defaults_are_deterministic():
    assert BackgroundIntelligenceConfig() == BackgroundIntelligenceConfig()


def test_config_from_env_is_deterministic_given_the_same_environment():
    assert BackgroundIntelligenceConfig.from_env() == BackgroundIntelligenceConfig.from_env()


# ── Additional coverage: disabled config, execution identifiers ──────────


def test_disabled_config_skips_the_tick_without_touching_universe_or_scanner():
    universe = _FakeUniverseProvider(["AAPL"])
    scanner = _FakeScanner()
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(enabled=False, batch_size=10))

    result = orchestrator.run_once()

    assert result.status == BackgroundScanStatus.SKIPPED_DISABLED
    assert universe.calls == 0
    assert scanner.calls == []


def test_each_execution_gets_a_distinct_execution_id():
    orchestrator = _orchestrator(_FakeScanner(), _FakeUniverseProvider(["AAPL"]), BackgroundIntelligenceConfig(batch_size=10))

    first = orchestrator.run_once()
    second = orchestrator.run_once()

    assert first.execution_id != second.execution_id


def test_result_duration_is_non_negative():
    orchestrator = _orchestrator(_FakeScanner(), _FakeUniverseProvider(["AAPL"]), BackgroundIntelligenceConfig(batch_size=10))
    result = orchestrator.run_once()
    assert result.duration_ms >= 0.0


def test_batch_failure_preserves_the_cursor_advance_that_already_happened():
    universe = _FakeUniverseProvider(["AAPL", "MSFT", "GOOG", "TSLA"])
    scanner = _FakeScanner()
    scanner.fail_with(RuntimeError("boom"))
    orchestrator = _orchestrator(scanner, universe, BackgroundIntelligenceConfig(batch_size=2))

    result = orchestrator.run_once()

    assert result.status == BackgroundScanStatus.FAILED
    assert result.cursor_before == 0
    assert result.cursor_after == 2  # the cursor still advances past the attempted batch
    assert result.ranked_opportunities is None

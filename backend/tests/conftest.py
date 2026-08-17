"""Shared pytest fixtures for FastAPI (main.py) integration tests."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """A TestClient over the real `main.app`, with the pre-existing
    background loops (daily self-evolution retraining over real network
    data, periodic alert scanning, periodic paper-trading resting-order
    fills - none of it what these tests exercise) replaced with no-ops
    so test runs stay fast and don't hit real external state on a
    background timer while the test session is running. Startup still
    runs for real: init_db() and PipelineService() construction both hit
    the real PostgreSQL/Redis, matching this project's established
    real-infrastructure testing philosophy."""
    import main

    async def _noop_loop() -> None:
        return None

    original_self_evolution_loop = main.self_evolution_loop
    original_alert_scan_loop = main.alert_scan_loop
    original_paper_trading_fill_loop = main.paper_trading_fill_loop
    main.self_evolution_loop = _noop_loop
    main.alert_scan_loop = _noop_loop
    main.paper_trading_fill_loop = _noop_loop
    try:
        with TestClient(main.app) as test_client:
            # main.limiter (slowapi) tracks request counts in a single
            # process-wide in-memory store keyed by client IP - shared by
            # every test module in this pytest session, since they all
            # exercise the same fake TestClient IP. Reset it once per
            # module (this fixture is module-scoped) so one test file's
            # register/login/etc. volume can never eat into another
            # file's budget - each module gets the full, real per-minute
            # quota main.py actually configures, matching what a real
            # single client would see.
            main.limiter.reset()
            yield test_client
    finally:
        main.self_evolution_loop = original_self_evolution_loop
        main.alert_scan_loop = original_alert_scan_loop
        main.paper_trading_fill_loop = original_paper_trading_fill_loop

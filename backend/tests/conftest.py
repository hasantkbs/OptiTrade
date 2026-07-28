"""Shared pytest fixtures for FastAPI (main.py) integration tests."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """A TestClient over the real `main.app`, with the pre-existing
    daily self-evolution background task (retrains an XGBoost model
    over real network data - unrelated to what these tests exercise)
    replaced with a no-op so test runs stay fast. Startup still runs
    for real: init_db() and PipelineService() construction both hit
    the real PostgreSQL/Redis, matching this project's established
    real-infrastructure testing philosophy."""
    import main

    async def _noop_self_evolution_loop() -> None:
        return None

    original_loop = main.self_evolution_loop
    main.self_evolution_loop = _noop_self_evolution_loop
    try:
        with TestClient(main.app) as test_client:
            yield test_client
    finally:
        main.self_evolution_loop = original_loop

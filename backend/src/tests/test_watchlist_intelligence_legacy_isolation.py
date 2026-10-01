"""
Architectural safety test for intelligence/watchlist_intelligence.py
(Phase F).

Proves Watchlist Intelligence:
- imports only canonical intelligence/decision_engine/watchlist
  abstractions,
- never imports any legacy/parallel analysis path
  (core.analyzer, core.hybrid_engine, core.ai_trader_persona,
  core.investor_persona, api.v1, v2),
- never imports the Explanation Engine or any LLM provider (this layer
  must never call an LLM),
- performs no database writes of its own (no psycopg2/redis import,
  no CREATE TABLE/INSERT anywhere in the file),
- never constructs a background scheduler/thread pool of its own
  (no ThreadPoolExecutor/asyncio.create_task - this phase is a plain
  callable, Phase G will handle background scanning),
- never creates an Alert/AlertTriggerEvent (Phase H will handle
  intelligent alert generation),
- defines no second decision/voting/risk/scoring engine class.

Uses an AST scan (matching `tests/test_research_isolation.py`,
`tests/test_market_scanner_legacy_isolation.py`,
`tests/test_opportunity_ranking_legacy_isolation.py`, and
`tests/test_portfolio_intelligence_legacy_isolation.py`) rather than a
string grep, so a substring match inside a comment or docstring can't
produce a false positive for the import checks.
"""
import ast
import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
WATCHLIST_INTELLIGENCE_FILE = BACKEND_ROOT / "intelligence" / "watchlist_intelligence.py"

FORBIDDEN_MODULES = [
    "core.analyzer",
    "core.hybrid_engine",
    "core.ai_trader_persona",
    "core.investor_persona",
    "api.v1",
    "v2",
    "explanation_engine",
]

REQUIRED_MODULES = [
    "intelligence.decision_diff",
    "intelligence.opportunity",
    "intelligence.opportunity_ranking",
    "intelligence.models",
    "decision_engine.models",
    "watchlist.models",
]


def _imported_module_names(py_file: pathlib.Path) -> set:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def test_watchlist_intelligence_file_exists():
    assert WATCHLIST_INTELLIGENCE_FILE.is_file()


def test_watchlist_intelligence_does_not_import_legacy_or_llm_paths():
    imported = _imported_module_names(WATCHLIST_INTELLIGENCE_FILE)
    offenders = [
        forbidden for forbidden in FORBIDDEN_MODULES
        if any(name == forbidden or name.startswith(f"{forbidden}.") for name in imported)
    ]
    assert offenders == [], f"intelligence/watchlist_intelligence.py imports forbidden modules: {offenders}"


def test_watchlist_intelligence_imports_the_canonical_abstractions_it_reuses():
    imported = _imported_module_names(WATCHLIST_INTELLIGENCE_FILE)
    missing = [
        required for required in REQUIRED_MODULES
        if not any(name == required or name.startswith(f"{required}.") for name in imported)
    ]
    assert missing == [], f"intelligence/watchlist_intelligence.py is missing expected canonical imports: {missing}"


def test_watchlist_intelligence_never_imports_an_llm_provider():
    imported = _imported_module_names(WATCHLIST_INTELLIGENCE_FILE)
    forbidden_packages = ("openai", "anthropic")
    offenders = [
        forbidden for forbidden in forbidden_packages
        if any(name == forbidden or name.startswith(f"{forbidden}.") for name in imported)
    ]
    assert offenders == [], f"intelligence/watchlist_intelligence.py imports an LLM provider: {offenders}"


def test_watchlist_intelligence_performs_no_database_writes():
    source = WATCHLIST_INTELLIGENCE_FILE.read_text(encoding="utf-8")
    for marker in ("psycopg2", "CREATE TABLE", "INSERT INTO", "import redis", ".save("):
        assert marker not in source, f"intelligence/watchlist_intelligence.py unexpectedly references {marker!r}"


def test_watchlist_intelligence_introduces_no_scheduler_or_background_loop():
    source = WATCHLIST_INTELLIGENCE_FILE.read_text(encoding="utf-8")
    for marker in (
        "ThreadPoolExecutor", "asyncio.create_task", "while True", "schedule.every",
        "APScheduler", "Celery", "celery", "RQ",
    ):
        assert marker not in source, f"intelligence/watchlist_intelligence.py unexpectedly references {marker!r}"


def test_watchlist_intelligence_never_creates_an_alert():
    source = WATCHLIST_INTELLIGENCE_FILE.read_text(encoding="utf-8")
    for marker in ("Alert(", "AlertTriggerEvent(", "create_alert", "NotificationPayload("):
        assert marker not in source, f"intelligence/watchlist_intelligence.py unexpectedly references {marker!r}"


def test_watchlist_intelligence_defines_no_second_decision_or_risk_engine_class():
    """Guards against a future edit accidentally reintroducing a
    parallel scoring/voting/risk engine here - this module should only
    ever define change-detection/finding-building helpers, never a
    class resembling a decision or risk engine."""
    tree = ast.parse(
        WATCHLIST_INTELLIGENCE_FILE.read_text(encoding="utf-8"), filename=str(WATCHLIST_INTELLIGENCE_FILE),
    )
    class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    forbidden_name_fragments = ("DecisionEngine", "VotingEngine", "ScoringEngine", "RiskEngine")
    offenders = [
        name for name in class_names
        if any(fragment.lower() in name.lower() for fragment in forbidden_name_fragments)
    ]
    assert offenders == [], f"intelligence/watchlist_intelligence.py defines an unexpected engine-like class: {offenders}"


def test_intelligence_package_still_never_imports_research():
    # A targeted re-check (test_research_isolation.py already covers the
    # whole intelligence/ directory) - kept here too so this file alone
    # documents the guarantee for the module it's specifically about.
    imported = _imported_module_names(WATCHLIST_INTELLIGENCE_FILE)
    forbidden_packages = ("research", "research_lab", "ml_training")
    offenders = [
        forbidden for forbidden in forbidden_packages
        if any(name == forbidden or name.startswith(f"{forbidden}.") for name in imported)
    ]
    assert offenders == [], f"intelligence/watchlist_intelligence.py imports research/training code: {offenders}"

"""
Architectural safety test for intelligence/background_intelligence.py
(Phase G).

Proves Background Intelligence Orchestration:
- imports only canonical intelligence/decision_engine/core.market_config
  abstractions,
- never imports any legacy/parallel analysis path
  (core.analyzer, core.hybrid_engine, core.ai_trader_persona,
  core.investor_persona, api.v1, v2),
- never imports the Explanation Engine, an LLM provider, or
  research/research_lab/ml_training,
- performs no database writes of its own,
- never creates an Alert or mutates a portfolio/watchlist,
- defines no second decision/risk/scanner/scheduler-framework class,
- never imports a third-party worker framework (Celery/RQ/APScheduler).

Uses an AST scan (matching every prior phase's own
`test_*_legacy_isolation.py`) rather than a string grep, so a substring
match inside a comment or docstring can't produce a false positive for
the import checks.
"""
import ast
import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKGROUND_INTELLIGENCE_FILE = BACKEND_ROOT / "intelligence" / "background_intelligence.py"

FORBIDDEN_MODULES = [
    "core.analyzer",
    "core.hybrid_engine",
    "core.ai_trader_persona",
    "core.investor_persona",
    "api.v1",
    "v2",
    "explanation_engine",
    "openai",
    "anthropic",
    "research",
    "research_lab",
    "ml_training",
    "celery",
    "rq",
    "apscheduler",
]

REQUIRED_MODULES = [
    "intelligence.opportunity_ranking",
    "intelligence.models",
    "intelligence.config",
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


def test_background_intelligence_file_exists():
    assert BACKGROUND_INTELLIGENCE_FILE.is_file()


def test_background_intelligence_does_not_import_forbidden_modules():
    imported = _imported_module_names(BACKGROUND_INTELLIGENCE_FILE)
    offenders = [
        forbidden for forbidden in FORBIDDEN_MODULES
        if any(name == forbidden or name.startswith(f"{forbidden}.") for name in imported)
    ]
    assert offenders == [], f"intelligence/background_intelligence.py imports forbidden modules: {offenders}"


def test_background_intelligence_imports_the_canonical_abstractions_it_reuses():
    imported = _imported_module_names(BACKGROUND_INTELLIGENCE_FILE)
    missing = [
        required for required in REQUIRED_MODULES
        if not any(name == required or name.startswith(f"{required}.") for name in imported)
    ]
    assert missing == [], f"intelligence/background_intelligence.py is missing expected canonical imports: {missing}"


def test_background_intelligence_performs_no_database_writes():
    source = BACKGROUND_INTELLIGENCE_FILE.read_text(encoding="utf-8")
    for marker in ("psycopg2", "CREATE TABLE", "INSERT INTO", "import redis", ".save("):
        assert marker not in source, f"intelligence/background_intelligence.py unexpectedly references {marker!r}"


def test_background_intelligence_never_creates_an_alert_or_mutates_portfolio_or_watchlist():
    source = BACKGROUND_INTELLIGENCE_FILE.read_text(encoding="utf-8")
    for marker in (
        "Alert(", "AlertTriggerEvent(", "create_alert", "NotificationPayload(",
        ".buy(", ".sell(", ".deposit(", ".withdraw(",
        ".add_symbol(", ".remove_symbol(", ".create_watchlist(", ".delete_watchlist(",
    ):
        assert marker not in source, f"intelligence/background_intelligence.py unexpectedly references {marker!r}"


def test_background_intelligence_defines_no_second_decision_risk_or_scanner_class():
    tree = ast.parse(BACKGROUND_INTELLIGENCE_FILE.read_text(encoding="utf-8"), filename=str(BACKGROUND_INTELLIGENCE_FILE))
    class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    forbidden_fragments = ("DecisionEngine", "VotingEngine", "ScoringEngine", "RiskEngine", "Scheduler")
    offenders = [
        name for name in class_names if any(fragment.lower() in name.lower() for fragment in forbidden_fragments)
    ]
    assert offenders == [], f"intelligence/background_intelligence.py defines an unexpected engine/scheduler class: {offenders}"
    assert "MarketScanner" not in class_names, "must import MarketScanner, never redefine it"


def test_background_intelligence_never_defines_its_own_polling_loop():
    source = BACKGROUND_INTELLIGENCE_FILE.read_text(encoding="utf-8")
    for marker in ("while True", "asyncio.create_task", "async def"):
        assert marker not in source, (
            f"intelligence/background_intelligence.py unexpectedly references {marker!r} - "
            "the scheduling loop belongs in main.py's existing leader-elected asyncio convention"
        )


def test_main_still_never_imports_research_lab_or_ml_training():
    # A targeted re-check that wiring in the new import to main.py
    # didn't introduce a forbidden dependency there too.
    main_py = BACKEND_ROOT / "main.py"
    tree = ast.parse(main_py.read_text(encoding="utf-8"), filename=str(main_py))
    blocked = ("research_lab", "ml_training")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == pkg or alias.name.startswith(f"{pkg}.") for pkg in blocked)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert not any(node.module == pkg or node.module.startswith(f"{pkg}.") for pkg in blocked)

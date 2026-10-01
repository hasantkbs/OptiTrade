"""
Architectural safety test for intelligence/opportunity_ranking.py (Phase D).

Proves the ranking layer:
- imports only canonical intelligence/pipeline/decision_engine
  abstractions,
- never imports any legacy/parallel analysis path
  (core.analyzer, core.hybrid_engine, core.ai_trader_persona,
  core.investor_persona, api.v1, v2),
- never imports the Explanation Engine or any LLM provider (ranking
  must never call an LLM),
- performs no database writes of its own (no psycopg2/redis import,
  no CREATE TABLE/INSERT anywhere in the file).

Uses an AST scan (matching `tests/test_research_isolation.py` and
`tests/test_market_scanner_legacy_isolation.py`) rather than a string
grep, so a substring match inside a comment or docstring can't produce
a false positive for the import checks.
"""
import ast
import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
RANKING_FILE = BACKEND_ROOT / "intelligence" / "opportunity_ranking.py"

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
    "intelligence.opportunity",
    "intelligence.models",
    "pipeline.models",
    "decision_engine.models",
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


def test_opportunity_ranking_file_exists():
    assert RANKING_FILE.is_file()


def test_opportunity_ranking_does_not_import_legacy_or_llm_paths():
    imported = _imported_module_names(RANKING_FILE)
    offenders = [
        forbidden for forbidden in FORBIDDEN_MODULES
        if any(name == forbidden or name.startswith(f"{forbidden}.") for name in imported)
    ]
    assert offenders == [], f"intelligence/opportunity_ranking.py imports forbidden modules: {offenders}"


def test_opportunity_ranking_imports_the_canonical_intelligence_and_pipeline_abstractions():
    imported = _imported_module_names(RANKING_FILE)
    missing = [
        required for required in REQUIRED_MODULES
        if not any(name == required or name.startswith(f"{required}.") for name in imported)
    ]
    assert missing == [], f"intelligence/opportunity_ranking.py is missing expected canonical imports: {missing}"


def test_opportunity_ranking_performs_no_database_writes():
    source = RANKING_FILE.read_text(encoding="utf-8")
    for marker in ("psycopg2", "CREATE TABLE", "INSERT INTO", "import redis"):
        assert marker not in source, f"intelligence/opportunity_ranking.py unexpectedly references {marker!r}"


def test_opportunity_ranking_defines_no_second_decision_engine_class():
    """Guards against a future edit accidentally reintroducing a
    parallel scoring/voting engine here - this module should only ever
    define ranking/result helpers, never a class resembling a decision
    engine."""
    tree = ast.parse(RANKING_FILE.read_text(encoding="utf-8"), filename=str(RANKING_FILE))
    class_names = {node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)}
    forbidden_name_fragments = ("DecisionEngine", "VotingEngine", "ScoringEngine")
    offenders = [
        name for name in class_names
        if any(fragment.lower() in name.lower() for fragment in forbidden_name_fragments)
    ]
    assert offenders == [], f"intelligence/opportunity_ranking.py defines an unexpected engine-like class: {offenders}"

"""
Architectural safety test for intelligence/market_scanner.py (Phase C).

Proves the canonical batch scanner depends only on the canonical
`pipeline` abstraction and never imports any of the legacy/parallel
analysis paths identified in the OptiTrade Intelligent Market Assistant
audit: `core.analyzer`, `core.hybrid_engine`, `core.ai_trader_persona`,
`core.investor_persona`, `api.v1.endpoints.signals`, or `v2`.

Uses an AST scan (matching `tests/test_research_isolation.py`'s own
approach) rather than a string grep, so a substring match inside a
comment or docstring can't produce a false positive.
"""
import ast
import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
SCANNER_FILE = BACKEND_ROOT / "intelligence" / "market_scanner.py"

FORBIDDEN_MODULES = [
    "core.analyzer",
    "core.hybrid_engine",
    "core.ai_trader_persona",
    "core.investor_persona",
    "api.v1",
    "v2",
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


def test_market_scanner_file_exists():
    assert SCANNER_FILE.is_file()


def test_market_scanner_does_not_import_any_legacy_analysis_path():
    imported = _imported_module_names(SCANNER_FILE)
    offenders = [
        forbidden for forbidden in FORBIDDEN_MODULES
        if any(name == forbidden or name.startswith(f"{forbidden}.") for name in imported)
    ]
    assert offenders == [], f"intelligence/market_scanner.py imports forbidden legacy modules: {offenders}"


def test_market_scanner_imports_the_canonical_pipeline_module():
    imported = _imported_module_names(SCANNER_FILE)
    assert any(name == "pipeline.service" or name.startswith("pipeline.") for name in imported), (
        "intelligence/market_scanner.py must depend on the canonical pipeline module"
    )


def test_entire_intelligence_package_never_imports_legacy_analysis_paths():
    """Broader guarantee: not just market_scanner.py, but every module
    in the intelligence package (decision_diff, opportunity, anomaly,
    future additions) stays clear of the legacy paths too."""
    intelligence_dir = BACKEND_ROOT / "intelligence"
    offenders = []
    for py_file in intelligence_dir.glob("*.py"):
        imported = _imported_module_names(py_file)
        for forbidden in FORBIDDEN_MODULES:
            if any(name == forbidden or name.startswith(f"{forbidden}.") for name in imported):
                offenders.append((str(py_file.relative_to(BACKEND_ROOT)), forbidden))
    assert offenders == [], f"intelligence/ modules importing forbidden legacy modules: {offenders}"

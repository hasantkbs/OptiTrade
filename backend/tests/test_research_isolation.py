"""
Guards the production/research boundary introduced in Sprint 1, Task 7:
nothing under core/, v2/, models/, data/, api/, feature_store/,
decision_engine/, engine_registry/, or engines/ should import the
`research` package. Research code may depend on production code (it
already does - core.indicators, core.scoring); production must never
depend on research code.

Uses an AST scan rather than a simple string grep so that a substring
match inside a comment or docstring (e.g. this very file's own docstring)
can't produce a false positive.
"""
import ast
import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
PRODUCTION_DIRS = [
    "core", "v2", "models", "data", "api",
    "feature_store", "decision_engine", "engine_registry", "engines",
]


def _imports_research(py_file: pathlib.Path) -> bool:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "research" or alias.name.startswith("research.") for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "research" or node.module.startswith("research.")):
                return True
    return False


def test_no_production_module_imports_research():
    offenders = []
    for dirname in PRODUCTION_DIRS:
        directory = BACKEND_ROOT / dirname
        if not directory.exists():
            continue
        for py_file in directory.rglob("*.py"):
            if _imports_research(py_file):
                offenders.append(str(py_file.relative_to(BACKEND_ROOT)))
    assert offenders == [], f"production modules importing research: {offenders}"


def test_research_package_exists_and_contains_the_moved_scripts():
    research_dir = BACKEND_ROOT / "research"
    assert research_dir.is_dir()
    expected = {
        "__init__.py", "backtest.py", "backtest_advanced.py",
        "ml_trainer.py", "train_v2.py", "train_chart_model.py",
    }
    actual = {p.name for p in research_dir.glob("*.py")}
    assert expected <= actual


def test_research_scripts_are_free_to_import_production_code():
    # The boundary is one-directional - research importing from core/ is
    # expected and fine (backtest.py/backtest_advanced.py/ml_trainer.py all
    # import core.indicators and core.scoring today). This test just
    # documents that fact rather than asserting anything new.
    research_dir = BACKEND_ROOT / "research"
    ml_trainer_source = (research_dir / "ml_trainer.py").read_text(encoding="utf-8")
    assert "from core." in ml_trainer_source

"""
Guards the production/research boundary introduced in Sprint 1, Task 7,
and extended for `research_lab` (the Continuous Learning-era Research
Lab package), the production execution pipeline, `ml_training` (the ML
Training Platform), `model_serving` (the Model Serving Platform),
`portfolio` (the Portfolio Intelligence Platform), and `watchlist` (the
Watchlist & Alert Platform): nothing under core/, v2/, models/, data/,
api/, feature_store/, decision_engine/, engine_registry/, engines/,
learning/, pipeline/, explanation_engine/, portfolio/, or watchlist/
should import the `research`, `research_lab`, or `ml_training`
packages. Research/training code may depend on production code (it
already does - core.indicators, core.scoring, and research_lab/
ml_training both reuse learning/feature_store/decision_engine
extensively); production (including the production-adjacent Continuous
Learning system, the pipeline, and the Portfolio Intelligence and
Watchlist & Alert platforms that must never let Research Lab or model
training execute during a live request) must never depend on research
or training code.

`model_serving` is the one deliberate exception, and deliberately NOT
included in `PRODUCTION_DIRS` above: it is the sole bridge between the
offline Model Registry (`ml_training.registry`) and live serving, so it
alone is allowed to import `ml_training` - loading an already-trained,
already-registered artifact and calling `predict()` on it is not
"research" or "training execution" the way building a dataset, running
Optuna, or computing SHAP values is. Every other production package
reaches `ml_training` only indirectly, through `model_serving` (see
`pipeline.service.PipelineService`) - never directly. `model_serving`
still must never import `research_lab` - that boundary stays exactly as
strict as it is for every other production package.

Uses an AST scan rather than a simple string grep so that a substring
match inside a comment or docstring (e.g. this very file's own docstring)
can't produce a false positive.
"""
import ast
import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
PRODUCTION_DIRS = [
    "core", "v2", "models", "data", "api",
    "feature_store", "decision_engine", "engine_registry", "engines", "learning",
    "pipeline", "explanation_engine", "portfolio", "watchlist",
]
FORBIDDEN_PACKAGES = ["research", "research_lab", "ml_training"]


def _imports_forbidden(py_file: pathlib.Path) -> bool:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(alias.name == pkg or alias.name.startswith(f"{pkg}.") for pkg in FORBIDDEN_PACKAGES):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and any(
                node.module == pkg or node.module.startswith(f"{pkg}.") for pkg in FORBIDDEN_PACKAGES
            ):
                return True
    return False


def test_no_production_module_imports_research():
    offenders = []
    for dirname in PRODUCTION_DIRS:
        directory = BACKEND_ROOT / dirname
        if not directory.exists():
            continue
        for py_file in directory.rglob("*.py"):
            if _imports_forbidden(py_file):
                offenders.append(str(py_file.relative_to(BACKEND_ROOT)))
    assert offenders == [], f"production modules importing research/research_lab/ml_training: {offenders}"


def test_main_module_does_not_import_research_lab_or_ml_training():
    # main.py already has a pre-existing, legitimate dependency on
    # `research.ml_trainer.train` for its self-evolution retraining
    # loop (Sprint 1) - that one stays allowed. `research_lab` and
    # `ml_training` are a different story: neither must ever execute
    # during a live request, so main.py must never import either.
    main_py = BACKEND_ROOT / "main.py"
    tree = ast.parse(main_py.read_text(encoding="utf-8"), filename=str(main_py))
    blocked = ("research_lab", "ml_training")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == pkg or alias.name.startswith(f"{pkg}.") for pkg in blocked), (
                    f"main.py must never import {blocked}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert not any(node.module == pkg or node.module.startswith(f"{pkg}.") for pkg in blocked), (
                    f"main.py must never import {blocked}"
                )


def test_research_lab_package_exists():
    research_lab_dir = BACKEND_ROOT / "research_lab"
    assert research_lab_dir.is_dir()
    expected_subpackages = {
        "experiments", "backtesting", "benchmarking", "datasets", "feature_analysis",
        "model_analysis", "hypothesis", "reports", "shadow", "promotion",
    }
    actual = {p.name for p in research_lab_dir.iterdir() if p.is_dir() and not p.name.startswith("__")}
    assert expected_subpackages <= actual


def test_ml_training_package_exists():
    ml_training_dir = BACKEND_ROOT / "ml_training"
    assert ml_training_dir.is_dir()
    expected_subpackages = {
        "datasets", "labels", "features", "training", "optimization", "evaluation",
        "calibration", "importance", "registry", "shadow", "runs",
    }
    actual = {p.name for p in ml_training_dir.iterdir() if p.is_dir() and not p.name.startswith("__")}
    assert expected_subpackages <= actual


def test_model_serving_package_exists():
    model_serving_dir = BACKEND_ROOT / "model_serving"
    assert model_serving_dir.is_dir()
    expected_modules = {
        "config.py", "exceptions.py", "models.py", "cache.py", "loader.py",
        "inference.py", "shadow.py", "rollback.py", "health.py", "service.py",
    }
    actual = {p.name for p in model_serving_dir.glob("*.py")}
    assert expected_modules <= actual


def test_portfolio_package_exists():
    portfolio_dir = BACKEND_ROOT / "portfolio"
    assert portfolio_dir.is_dir()
    expected_modules = {
        "config.py", "exceptions.py", "models.py", "repository.py", "prices.py",
        "classification.py", "service.py", "analytics.py", "risk.py", "optimization.py",
        "rebalancing.py", "scenarios.py", "recommendations.py", "dashboard.py",
    }
    actual = {p.name for p in portfolio_dir.glob("*.py")}
    assert expected_modules <= actual


def test_watchlist_package_exists():
    watchlist_dir = BACKEND_ROOT / "watchlist"
    assert watchlist_dir.is_dir()
    expected_modules = {
        "config.py", "exceptions.py", "models.py", "repository.py", "watchlist_service.py",
        "alert_engine.py", "price_alerts.py", "technical_alerts.py", "portfolio_alerts.py",
        "news_alerts.py", "notification_router.py", "scheduler.py",
    }
    actual = {p.name for p in watchlist_dir.glob("*.py")}
    assert expected_modules <= actual


def test_model_serving_is_the_bridge_that_imports_ml_training():
    # A positive check, not just the absence of a negative: proves the
    # bridge is actually wired (model_serving really does depend on
    # ml_training.registry to load ACTIVE models), so
    # `test_no_production_module_imports_research` passing for every
    # OTHER production package isn't just vacuously true because nothing
    # imports ml_training anywhere.
    loader_source = (BACKEND_ROOT / "model_serving" / "loader.py").read_text(encoding="utf-8")
    assert "from ml_training" in loader_source


def test_model_serving_never_imports_research_lab_or_bare_research():
    # model_serving sits on the production side of the boundary (it
    # executes during live requests) - unlike ml_training, it does NOT
    # get a research_lab exception. `research`/`research_lab` must stay
    # exactly as forbidden here as everywhere else in PRODUCTION_DIRS.
    model_serving_dir = BACKEND_ROOT / "model_serving"
    offenders = []
    for py_file in model_serving_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(alias.name == pkg or alias.name.startswith(f"{pkg}.") for pkg in ("research", "research_lab")):
                        offenders.append(f"{py_file.name}: {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module and any(
                    node.module == pkg or node.module.startswith(f"{pkg}.") for pkg in ("research", "research_lab")
                ):
                    offenders.append(f"{py_file.name}: {node.module}")
    assert offenders == [], f"model_serving must never import research/research_lab: {offenders}"


def test_research_lab_is_free_to_import_production_and_learning_code():
    # The boundary is one-directional - research_lab importing from
    # feature_store/decision_engine/learning is expected and extensive
    # (model_analysis reuses learning.accuracy, backtesting reads
    # learning.persistence, feature_analysis reads feature_store, ...).
    # This test documents that fact rather than asserting anything new.
    research_lab_dir = BACKEND_ROOT / "research_lab"
    model_analysis_source = (research_lab_dir / "model_analysis" / "analyzer.py").read_text(encoding="utf-8")
    assert "from learning" in model_analysis_source


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

"""
Production-freeze audit: guards against a duplicate/legacy production
decision path silently coming back into existence.

`decision_engine.service.DecisionEngine` is a fully-functional,
independently-invokable orchestrator (registry -> serial vote
collection -> `aggregate_votes` -> persistence) that exists purely as
tested standalone infrastructure - exercised only by
tests/test_decision_engine_service.py and the individual engine test
files, never constructed anywhere reachable from a live request today
(verified: `main.py` never imports `decision_engine.service`).
`pipeline/pipeline.py`'s own docstring explains why it exists without
being the canonical path: it reuses `DecisionEngine`'s pure building
blocks (`decision_engine.aggregation.aggregate_votes`,
`decision_engine.weighting.AccuracyWeightProvider`,
`decision_engine.validation.validate_vote`,
`decision_engine.repository.PostgresExecutionRepository`) directly,
because `DecisionEngine.decide()`'s serial, timeout-free vote
collection cannot satisfy Pipeline's parallel-execution requirement.

That's a real, latent risk if left unguarded: `DecisionEngine.decide()`
looks exactly like "the decision engine" to a future caller (an admin
script, a new endpoint, a CLI command) who doesn't know
`pipeline.service.PipelineService` is the one canonical production
path - and unlike Pipeline's `ParallelEngineExecutor`, `decide()`
enforces no per-engine timeout at all, so it would have materially
worse resilience characteristics even though it shares the same
aggregation math. These tests lock in that `decision_engine.service`
is never imported from main.py or anywhere under pipeline/, so that
risk can't silently reappear.

Uses an AST scan (matching tests/test_research_isolation.py's own
technique) rather than a string grep, so a substring match inside a
comment or docstring (e.g. this very file's own docstring, or
pipeline/pipeline.py's) can't produce a false positive.
"""
import ast
import pathlib

BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent
_FORBIDDEN_MODULE = "decision_engine.service"


def _imports_decision_engine_service(py_file: pathlib.Path) -> bool:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == _FORBIDDEN_MODULE for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == _FORBIDDEN_MODULE:
                return True
    return False


def test_main_does_not_import_decision_engine_service():
    main_py = BACKEND_ROOT / "main.py"
    assert not _imports_decision_engine_service(main_py), (
        "main.py must never import decision_engine.service - the canonical production "
        "decision path is pipeline.service.PipelineService only (see pipeline/pipeline.py's docstring)"
    )


def test_pipeline_package_does_not_import_decision_engine_service():
    pipeline_dir = BACKEND_ROOT / "pipeline"
    offenders = [
        str(py_file.relative_to(BACKEND_ROOT))
        for py_file in pipeline_dir.rglob("*.py")
        if _imports_decision_engine_service(py_file)
    ]
    assert offenders == [], (
        f"pipeline/ must reuse decision_engine's pure building blocks (aggregation/weighting/"
        f"validation/repository) directly, never decision_engine.service.DecisionEngine's own "
        f"orchestration - see pipeline/pipeline.py's docstring. Offenders: {offenders}"
    )


def test_decision_engine_service_still_exists_and_is_importable():
    """Sanity check that this guard is testing something real, not a
    module that got renamed/removed out from under it."""
    import decision_engine.service  # noqa: F401


def test_legacy_analyzer_does_not_import_the_pipeline_or_decision_engine():
    """core/analyzer.py (POST /analyze - see its own module docstring)
    and pipeline.service.PipelineService (POST /quant/analyze) are two
    deliberately separate, separately-tested decision paths - this
    guards against a future change accidentally coupling the pinned
    legacy contract to the new pipeline's behavior, or vice versa."""
    analyzer_py = BACKEND_ROOT / "core" / "analyzer.py"
    tree = ast.parse(analyzer_py.read_text(encoding="utf-8"), filename=str(analyzer_py))
    forbidden = ("pipeline", "decision_engine")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == pkg or alias.name.startswith(f"{pkg}.") for pkg in forbidden), (
                    f"core/analyzer.py must stay independent of {forbidden}"
                )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert not any(node.module == pkg or node.module.startswith(f"{pkg}.") for pkg in forbidden), (
                    f"core/analyzer.py must stay independent of {forbidden}"
                )


def test_legacy_analyze_endpoint_documents_the_duplicate_path_rationale():
    """The docstring test_main_backward_compatibility.py's tests imply
    (a pinned legacy response contract) must actually exist and say so -
    otherwise the duplicate path is exactly the "silent" kind this audit
    exists to prevent."""
    main_py = BACKEND_ROOT / "main.py"
    tree = ast.parse(main_py.read_text(encoding="utf-8"), filename=str(main_py))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "analyze_symbol":
            docstring = ast.get_docstring(node)
            assert docstring, "main.py's /analyze handler (analyze_symbol) must document why it's a separate path"
            assert "pipeline" in docstring.lower()
            return
    raise AssertionError("main.py's analyze_symbol function was not found")

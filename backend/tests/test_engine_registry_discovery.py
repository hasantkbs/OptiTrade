"""
Tests for engine_registry/discovery.py, exercised against a real fixture
package of self-registering fake engines
(tests/fixtures/fake_engines/engine_alpha.py, engine_beta.py) rather than
mocking the import machinery — this proves package-walking + import-time
self-registration genuinely works, not just that the function calls
`importlib.import_module`.

Each test clears `default_registry` first, since fixture modules register
into that shared, process-wide instance by convention (real self-
registering engines will do the same) and Python only re-runs a module's
top-level code once per process (subsequent imports are no-ops), so the
registry must be explicitly reset rather than relying on a fresh import.
"""
import sys

from engine_registry.discovery import discover_engines
from engine_registry.registry import default_registry


def _reset_default_registry_and_forget_fixture_imports():
    default_registry.clear()
    for module_name in list(sys.modules):
        if module_name.startswith("tests.fixtures.fake_engines"):
            del sys.modules[module_name]


def test_discover_engines_imports_every_submodule_and_returns_their_names():
    _reset_default_registry_and_forget_fixture_imports()
    imported = discover_engines("tests.fixtures.fake_engines")

    assert "tests.fixtures.fake_engines.engine_alpha" in imported
    assert "tests.fixtures.fake_engines.engine_beta" in imported


def test_discover_engines_triggers_self_registration_as_an_import_side_effect():
    _reset_default_registry_and_forget_fixture_imports()
    assert len(default_registry) == 0

    discover_engines("tests.fixtures.fake_engines")

    assert len(default_registry) == 2
    names = {engine.engine_name for engine in default_registry.all()}
    assert names == {"FakeEngineAlpha", "FakeEngineBeta"}


def test_discovered_engines_are_usable_through_the_registry():
    _reset_default_registry_and_forget_fixture_imports()
    discover_engines("tests.fixtures.fake_engines")

    engine = default_registry.get("FakeEngineAlpha", "v1")
    vote = engine.vote("BTC-USD")
    assert vote.engine_name == "FakeEngineAlpha"


def test_a_broken_module_is_skipped_without_aborting_discovery_of_the_rest():
    # tests/fixtures/fake_engines/engine_gamma_broken.py raises at import
    # time - discover_engines must log and skip it, not propagate the
    # exception or stop importing engine_alpha.py/engine_beta.py.
    _reset_default_registry_and_forget_fixture_imports()

    imported = discover_engines("tests.fixtures.fake_engines")

    assert "tests.fixtures.fake_engines.engine_gamma_broken" not in imported
    assert "tests.fixtures.fake_engines.engine_alpha" in imported
    assert "tests.fixtures.fake_engines.engine_beta" in imported
    assert len(default_registry) == 2  # alpha + beta still self-registered

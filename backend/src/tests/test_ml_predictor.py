"""
Characterization tests for core/ml_predictor.py.

These document the CURRENT behavior exactly as implemented today,
including the module-level `_MODEL_CACHE` global that makes model loading
process-wide and effectively permanent once it succeeds, the inconsistent
error handling between get_ml_confidence() (broad try/except, returns
None) and get_model_info() (no try/except at all), and the fact that
required (non-Optional) parameters are not actually validated - a None
passed for `volume_ratio`/`price_velocity` is silently coerced to NaN by
numpy rather than rejected. None of this is fixed here, only characterized
and preserved; see docs/architecture/migration-notes.md for the
consolidated risk list.

IMPORTANT — process-wide global state:
`_load_model()` caches its result in the module-level `_MODEL_CACHE`
global. Once a load succeeds, every later call anywhere in the process
returns that same cached object forever, without re-checking the file on
disk at all. To keep these tests independent of each other (and of
whatever real model file happens to exist on disk in this environment),
every test in this file resets `core.ml_predictor._MODEL_CACHE` to None
before running via an autouse fixture, and controls `_MODEL_PATH`
per-test rather than relying on the real `backend/models/` directory.
"""
import os

import joblib
import numpy as np
import pytest

import core.ml_predictor as ml_predictor


class FakeModel:
    """Picklable stand-in for the real XGBClassifier - joblib/pickle can't
    serialize a class defined inside a test function, so this lives at
    module scope."""

    def __init__(self, proba_of_class_1: float = 0.6):
        self.proba_of_class_1 = proba_of_class_1
        self.calls = []

    def predict_proba(self, X):
        self.calls.append(X)
        return np.array([[1.0 - self.proba_of_class_1, self.proba_of_class_1]])


class RaisingModel:
    def predict_proba(self, X):
        raise RuntimeError("simulated feature-shape mismatch")


@pytest.fixture(autouse=True)
def reset_model_cache(monkeypatch):
    """Every test starts from a clean 'not yet loaded' state, regardless
    of what any previous test (or the real environment) already loaded."""
    monkeypatch.setattr(ml_predictor, "_MODEL_CACHE", None)


def _point_model_path_at_missing_file(monkeypatch, tmp_path):
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", str(tmp_path / "does-not-exist.joblib"))


def _dump_fake_package(tmp_path, model, **metadata):
    path = tmp_path / "fake_model.joblib"
    package = {"model": model, **metadata}
    joblib.dump(package, path)
    return str(path)


def _loaded_model():
    """The model instance _load_model() actually holds after a call - NOT
    the original object passed to _dump_fake_package(), since joblib.dump/
    load round-trips through real serialization and reconstructs a brand
    new object. Inspecting the original object's `.calls` would always be
    empty; this fetches the live, deserialized instance instead."""
    return ml_predictor._MODEL_CACHE["model"]


FULL_FEATURE_KWARGS = dict(
    rsi=55.0, macd=0.5, macd_signal=0.2, bollinger_pb=0.7,
    ema_crossover="BULLISH", trend_strength=4.0,
    volume_ratio=1.4, price_velocity=0.6,
)


# ─────────────────────────────────────────────────────────────────────────
# Missing-model scenarios
# ─────────────────────────────────────────────────────────────────────────

def test_get_ml_confidence_returns_none_when_model_file_missing(monkeypatch, tmp_path):
    _point_model_path_at_missing_file(monkeypatch, tmp_path)
    assert ml_predictor.get_ml_confidence(**FULL_FEATURE_KWARGS) is None


def test_is_model_available_false_when_model_file_missing(monkeypatch, tmp_path):
    _point_model_path_at_missing_file(monkeypatch, tmp_path)
    assert ml_predictor.is_model_available() is False


def test_get_model_info_when_model_file_missing(monkeypatch, tmp_path):
    _point_model_path_at_missing_file(monkeypatch, tmp_path)
    assert ml_predictor.get_model_info() == {"available": False}


def test_missing_model_rechecks_disk_on_every_call_no_negative_caching(monkeypatch, tmp_path):
    # Only a *successful* load is cached (_MODEL_CACHE is only ever set
    # inside the try block on success) - a missing/failed load leaves
    # _MODEL_CACHE as None, so every subsequent call re-checks the
    # filesystem from scratch. Verified here by spying on os.path.exists.
    _point_model_path_at_missing_file(monkeypatch, tmp_path)
    calls = []
    real_exists = os.path.exists

    def spy_exists(path):
        calls.append(path)
        return real_exists(path)

    monkeypatch.setattr(ml_predictor.os.path, "exists", spy_exists)

    ml_predictor.is_model_available()
    ml_predictor.is_model_available()
    ml_predictor.is_model_available()
    assert len(calls) == 3


# ─────────────────────────────────────────────────────────────────────────
# Model loading behavior — successful load
# ─────────────────────────────────────────────────────────────────────────

def test_successful_load_makes_model_available(monkeypatch, tmp_path):
    path = _dump_fake_package(tmp_path, FakeModel())
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)
    assert ml_predictor.is_model_available() is True


def test_successful_load_is_cached_and_survives_the_file_disappearing(monkeypatch, tmp_path):
    # Once _load_model() succeeds, _MODEL_CACHE is set and the `if
    # _MODEL_CACHE is not None: return _MODEL_CACHE` short-circuit means
    # the file is never looked at again for the rest of the process -
    # deleting it afterward has no effect on subsequent calls.
    path = _dump_fake_package(tmp_path, FakeModel())
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    assert ml_predictor.is_model_available() is True
    os.remove(path)
    assert ml_predictor.is_model_available() is True  # still True - served from cache, not re-read


def test_failed_load_due_to_corrupt_file_is_not_cached_and_retries_next_call(monkeypatch, tmp_path, caplog):
    # A file that exists but fails to unpickle (joblib.load raises) is
    # caught by _load_model()'s try/except and returns None WITHOUT
    # setting _MODEL_CACHE - so the very next call attempts to load again
    # from scratch, rather than remembering "this file is broken."
    corrupt_path = tmp_path / "corrupt.joblib"
    corrupt_path.write_bytes(b"this is not a valid joblib/pickle file")
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", str(corrupt_path))

    with caplog.at_level("WARNING"):
        first = ml_predictor.is_model_available()
    assert first is False
    assert any("ML modeli y" in rec.message for rec in caplog.records)  # "yüklenemedi" warning logged

    assert ml_predictor._MODEL_CACHE is None  # not cached after failure

    # Fix the file, confirm the very next call successfully loads - proving
    # the previous failure was not "remembered" in any way.
    joblib.dump({"model": FakeModel()}, corrupt_path)
    assert ml_predictor.is_model_available() is True


# ─────────────────────────────────────────────────────────────────────────
# get_ml_confidence — successful prediction path / feature vector shape
# ─────────────────────────────────────────────────────────────────────────

def test_feature_vector_order_and_values_for_full_explicit_inputs(monkeypatch, tmp_path):
    path = _dump_fake_package(tmp_path, FakeModel(proba_of_class_1=0.6))
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    result = ml_predictor.get_ml_confidence(**FULL_FEATURE_KWARGS)

    assert result == pytest.approx(0.6, abs=1e-6)
    model = _loaded_model()
    assert len(model.calls) == 1
    X = model.calls[0]
    # Order: rsi, macd_diff, bollinger_pb, ema_crossover_encoded,
    # trend_strength, price_velocity, volume_ratio.
    expected = [55.0, 0.3, 0.7, 1, 4.0, 0.6, 1.4]  # macd_diff = 0.5 - 0.2
    assert X.shape == (1, 7)
    assert list(X[0]) == pytest.approx(expected, abs=1e-5)


def test_optional_fields_default_when_none(monkeypatch, tmp_path):
    path = _dump_fake_package(tmp_path, FakeModel())
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    ml_predictor.get_ml_confidence(
        rsi=None, macd=0.5, macd_signal=0.2, bollinger_pb=None,
        ema_crossover=None, trend_strength=None,
        volume_ratio=1.0, price_velocity=0.0,
    )
    X = _loaded_model().calls[0]
    assert X[0][0] == pytest.approx(50.0)   # rsi default
    assert X[0][2] == pytest.approx(0.5)    # bollinger_pb default
    assert X[0][3] == pytest.approx(0.0)    # ema_crossover None -> encoded 0
    assert X[0][4] == pytest.approx(0.0)    # trend_strength default


def test_macd_diff_is_zero_if_either_macd_or_signal_is_none(monkeypatch, tmp_path):
    # Not "use whichever one is available" - ANY None among the pair zeroes
    # the whole diff, even if the other value is a large, meaningful number.
    path = _dump_fake_package(tmp_path, FakeModel())
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    ml_predictor.get_ml_confidence(
        rsi=50.0, macd=99.0, macd_signal=None, bollinger_pb=0.5,
        ema_crossover=None, trend_strength=0.0,
        volume_ratio=1.0, price_velocity=0.0,
    )
    model = _loaded_model()
    assert model.calls[0][0][1] == 0.0  # macd_diff, despite macd=99.0

    model.calls.clear()
    ml_predictor.get_ml_confidence(
        rsi=50.0, macd=None, macd_signal=99.0, bollinger_pb=0.5,
        ema_crossover=None, trend_strength=0.0,
        volume_ratio=1.0, price_velocity=0.0,
    )
    assert model.calls[0][0][1] == 0.0  # macd_diff, despite macd_signal=99.0


@pytest.mark.parametrize(
    "ema_crossover,expected_encoding",
    [
        ("GOLDEN_CROSS", 2),
        ("BULLISH", 1),
        (None, 0),
        ("BEARISH", -1),
        ("DEATH_CROSS", -2),
        ("SOME_UNRECOGNIZED_VALUE", 0),  # falls back to the same 0 as None
    ],
)
def test_ema_crossover_encoding(monkeypatch, tmp_path, ema_crossover, expected_encoding):
    path = _dump_fake_package(tmp_path, FakeModel())
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    ml_predictor.get_ml_confidence(
        rsi=50.0, macd=None, macd_signal=None, bollinger_pb=0.5,
        ema_crossover=ema_crossover, trend_strength=0.0,
        volume_ratio=1.0, price_velocity=0.0,
    )
    assert _loaded_model().calls[0][0][3] == expected_encoding


def test_return_value_is_a_native_python_float_not_numpy_float32(monkeypatch, tmp_path):
    model = FakeModel(proba_of_class_1=0.42)
    path = _dump_fake_package(tmp_path, model)
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    result = ml_predictor.get_ml_confidence(**FULL_FEATURE_KWARGS)
    assert type(result) is float
    assert result == pytest.approx(0.42, abs=1e-6)


def test_confidence_is_not_clamped_to_0_1_range(monkeypatch, tmp_path):
    # get_ml_confidence trusts predict_proba()[0][1] completely - there is
    # no min/max clamping on the returned value anywhere in this function.
    model = FakeModel(proba_of_class_1=1.5)  # a deliberately out-of-range "probability"
    path = _dump_fake_package(tmp_path, model)
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    result = ml_predictor.get_ml_confidence(**FULL_FEATURE_KWARGS)
    assert result == pytest.approx(1.5, abs=1e-6)  # returned as-is, out of the documented [0,1] range


def test_get_ml_confidence_is_deterministic_for_identical_inputs(monkeypatch, tmp_path):
    model = FakeModel(proba_of_class_1=0.37)
    path = _dump_fake_package(tmp_path, model)
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    first = ml_predictor.get_ml_confidence(**FULL_FEATURE_KWARGS)
    second = ml_predictor.get_ml_confidence(**FULL_FEATURE_KWARGS)
    assert first == second == pytest.approx(0.37, abs=1e-6)


# ─────────────────────────────────────────────────────────────────────────
# Error handling and fallback behavior
# ─────────────────────────────────────────────────────────────────────────

def test_predict_proba_exception_is_swallowed_and_returns_none(monkeypatch, tmp_path, caplog):
    path = _dump_fake_package(tmp_path, RaisingModel())
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    with caplog.at_level("DEBUG", logger="core.ml_predictor"):
        result = ml_predictor.get_ml_confidence(**FULL_FEATURE_KWARGS)

    assert result is None
    # Logged only at DEBUG (easy to miss in production, where DEBUG is
    # usually disabled) - unlike _load_model()'s failure, which logs at
    # WARNING. Inconsistent log-level choice between the two failure paths.
    debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
    assert any("ML tahmin hatası" in r.message for r in debug_records)


def test_missing_model_key_in_package_returns_none(monkeypatch, tmp_path):
    # package["model"] is a bare bracket lookup - a package dict without a
    # "model" key raises KeyError, caught by the same broad except.
    path = tmp_path / "no_model_key.joblib"
    joblib.dump({"not_the_model_key": object()}, path)
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", str(path))

    assert ml_predictor.get_ml_confidence(**FULL_FEATURE_KWARGS) is None


def test_none_for_a_required_non_optional_param_is_silently_coerced_to_nan(monkeypatch, tmp_path):
    # volume_ratio/price_velocity are typed as plain `float`, not
    # `Optional[float]`, and get no `if x is not None else default`
    # treatment like the Optional params do. Nothing enforces the type
    # hint at runtime: passing None for them does not raise a TypeError -
    # numpy's `np.array(..., dtype=np.float32)` silently converts a Python
    # None into NaN, and that NaN is fed straight into the model.
    path = _dump_fake_package(tmp_path, FakeModel())
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    ml_predictor.get_ml_confidence(
        rsi=50.0, macd=None, macd_signal=None, bollinger_pb=0.5,
        ema_crossover=None, trend_strength=0.0,
        volume_ratio=None, price_velocity=None,  # type hint violated
    )
    X = _loaded_model().calls[0]
    assert np.isnan(X[0][5])  # price_velocity slot
    assert np.isnan(X[0][6])  # volume_ratio slot


def test_get_model_info_raises_uncaught_if_package_is_not_dict_like(monkeypatch, tmp_path):
    # Unlike get_ml_confidence(), get_model_info() has NO try/except at
    # all around its package.get(...) calls - if _load_model() ever
    # returns something that isn't dict-like (e.g. a bare model object,
    # not the expected {"model": ..., "cv_accuracy_mean": ..., ...} dict),
    # this raises AttributeError uncaught rather than degrading gracefully
    # the way get_ml_confidence() does.
    path = tmp_path / "raw_model_not_a_dict.joblib"
    joblib.dump(FakeModel(), path)  # not wrapped in a dict at all
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", str(path))

    with pytest.raises(AttributeError):
        ml_predictor.get_model_info()


# ─────────────────────────────────────────────────────────────────────────
# get_model_info — successful shape
# ─────────────────────────────────────────────────────────────────────────

def test_get_model_info_full_shape_when_model_available(monkeypatch, tmp_path):
    path = _dump_fake_package(
        tmp_path, FakeModel(),
        cv_accuracy_mean=0.572, cv_accuracy_std=0.010,
        train_samples=8952, forward_days=5,
        feature_names=["rsi", "macd_diff", "bollinger_pb"],
    )
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    info = ml_predictor.get_model_info()
    assert info == {
        "available": True,
        "cv_accuracy": 57.2,
        "cv_std": 1.0,
        "train_samples": 8952,
        "forward_days": 5,
        "features": ["rsi", "macd_diff", "bollinger_pb"],
    }


def test_get_model_info_uses_defaults_for_missing_metadata_keys(monkeypatch, tmp_path):
    # A package dict with only "model" and none of the metadata keys is
    # accepted without error - every metadata field has a .get(..., default).
    path = _dump_fake_package(tmp_path, FakeModel())
    monkeypatch.setattr(ml_predictor, "_MODEL_PATH", path)

    info = ml_predictor.get_model_info()
    assert info == {
        "available": True,
        "cv_accuracy": 0.0,
        "cv_std": 0.0,
        "train_samples": 0,
        "forward_days": 5,
        "features": [],
    }


# ─────────────────────────────────────────────────────────────────────────
# Backward compatibility — public API shape guard
# ─────────────────────────────────────────────────────────────────────────

def test_public_api_surface_is_unchanged():
    import inspect

    assert list(inspect.signature(ml_predictor.get_ml_confidence).parameters) == [
        "rsi", "macd", "macd_signal", "bollinger_pb",
        "ema_crossover", "trend_strength", "volume_ratio", "price_velocity",
    ]
    assert list(inspect.signature(ml_predictor.is_model_available).parameters) == []
    assert list(inspect.signature(ml_predictor.get_model_info).parameters) == []

"""Regression test for ml/chart_model.py's per-symbol model paths.

Before this, MODEL_PATH/SCALER_PATH were flat, BTC-only constants -
training a second symbol would silently overwrite BTC's already
trained-and-validated model file. model_path_for()/scaler_path_for()/
meta_path_for() give every symbol its own files, and is_model_available()/
load_model()/predict_chart_signal()/get_model_meta() all default their
`symbol` parameter to MODEL_SYMBOL so every existing BTC-only call site
is unaffected."""
import ml.chart_model as chart_model


def test_different_symbols_get_different_model_paths():
    btc_path = chart_model.model_path_for("BTC-USD")
    eth_path = chart_model.model_path_for("ETH-USD")
    assert btc_path != eth_path
    assert "btc" in btc_path
    assert "eth" in eth_path


def test_model_symbol_constant_matches_the_flat_backward_compatible_paths():
    assert chart_model.MODEL_PATH == chart_model.model_path_for(chart_model.MODEL_SYMBOL)
    assert chart_model.SCALER_PATH == chart_model.scaler_path_for(chart_model.MODEL_SYMBOL)


def test_is_model_available_checks_only_the_given_symbols_own_file(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_model, "MODEL_DIR", str(tmp_path))
    (tmp_path / "btc_chart_model.keras").write_text("fake")
    assert chart_model.is_model_available("BTC-USD") is True
    assert chart_model.is_model_available("ETH-USD") is False


def test_get_model_meta_reads_the_given_symbols_own_meta_file(tmp_path, monkeypatch):
    monkeypatch.setattr(chart_model, "MODEL_DIR", str(tmp_path))
    (tmp_path / "eth_chart_model_meta.json").write_text('{"test_accuracy": 0.5}')
    meta = chart_model.get_model_meta("ETH-USD")
    assert meta["available"] is True
    assert meta["test_accuracy"] == 0.5
    assert chart_model.get_model_meta("BTC-USD")["available"] is False

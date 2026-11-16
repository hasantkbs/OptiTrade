"""
Regression tests for CTO Remediation Plan Finding 1: `ModelEvaluator`
scored financial performance (expected_value/sharpe_ratio/sortino_ratio/
max_drawdown/profit_factor) on EVERY test-set sample's realized return,
regardless of what the model actually predicted - so a model that
predicts SELL/HOLD on every single test sample (never "acting on" any
of them) still got credited with the full, unconditional market drift
of the test period. `ml_training/service.py:309`'s
`_resolve_hypothesis_outcome` (and, with it, the ModelMetrics persisted
on the registry row) used exactly these drift-only numbers to decide
ACCEPTED/REJECTED - the CTO plan's own reproducible failure scenario:
"a test set with mean +0.8% 5-day forward return; an all-SELL model
gets expected_value=+0.8 and positive Sharpe, and is ACCEPTED, purely
from market drift."

The fix (in `MLTrainingService.run_training_job`) now filters
`returns_test` down to only the samples the model actually "acted on"
(via the module's own pre-existing `_select_mask`, previously used only
for an advisory-only benchmark comparison) BEFORE handing it to
`ModelEvaluator.evaluate()` - the same filtering that already existed,
just applied to the real evaluation path instead of only a side
comparison.

No real PostgreSQL/Redis connection is used anywhere in this file -
every test here exercises only pure functions
(`ml_training.service._select_mask`/`_resolve_hypothesis_outcome`,
`ml_training.evaluation.metrics.trading_performance_metrics`) directly,
unlike `tests/test_ml_training_service.py`'s own end-to-end suite
(which legitimately needs a real database and is out of scope for this
read-only-infrastructure task - see this task's own constraints).
"""
import numpy as np

from decision_engine.models import Prediction
from ml_training.config import MLTrainingConfig
from ml_training.evaluation import metrics as metrics_module
from ml_training.models import LabelName, ModelMetrics
from ml_training.service import _resolve_hypothesis_outcome, _select_mask
from research_lab.models import HypothesisOutcome

_CONFIG = MLTrainingConfig(min_training_samples=10)

# The CTO plan's own exact reproducible failure scenario: every test
# sample has a positive ~0.8% 5-day forward return (market drift), but
# the model predicts SELL on every single one of them.
_DRIFT_RETURNS = [0.8, 0.9, 0.7, 0.85, 0.75, 0.82, 0.78, 0.88, 0.72, 0.80]
_ALL_SELL_PREDICTIONS = np.array([Prediction.SELL.value] * len(_DRIFT_RETURNS))


def test_select_mask_for_direction_label_selects_only_buy_calls():
    predictions = np.array([Prediction.BUY.value, Prediction.SELL.value, Prediction.HOLD.value, Prediction.BUY.value])

    mask = _select_mask(LabelName.DIRECTION, predictions)

    assert list(mask) == [True, False, False, True]


def test_an_all_sell_model_produces_an_empty_selected_return_series():
    """The model never "acted on" (BUY'd) a single test sample - the
    filtered return series it should actually be evaluated on is empty,
    not the full drift-laden test set."""
    mask = _select_mask(LabelName.DIRECTION, _ALL_SELL_PREDICTIONS)
    selected_returns = [value for value, selected in zip(_DRIFT_RETURNS, mask) if selected]

    assert selected_returns == []


def test_trading_metrics_on_the_filtered_empty_returns_are_neutral_not_positive():
    """What the FIXED code now actually computes for this all-SELL
    model: expected_value/sharpe_ratio/sortino_ratio/max_drawdown all
    report a neutral 0.0 - never a spurious positive from returns the
    model never acted on."""
    mask = _select_mask(LabelName.DIRECTION, _ALL_SELL_PREDICTIONS)
    selected_returns = [value for value, selected in zip(_DRIFT_RETURNS, mask) if selected]

    fixed_metrics = metrics_module.trading_performance_metrics(selected_returns, _CONFIG.risk_free_rate)

    assert fixed_metrics["expected_value"] == 0.0
    assert fixed_metrics["sharpe_ratio"] == 0.0
    assert fixed_metrics["sortino_ratio"] == 0.0
    assert fixed_metrics["max_drawdown"] == 0.0


def test_resolve_hypothesis_outcome_correctly_rejects_the_all_sell_model_after_the_fix():
    """The actual decision that gates promotion - fed the FIXED,
    filtered metrics - no longer ACCEPTs a model purely from market
    drift it never acted on."""
    mask = _select_mask(LabelName.DIRECTION, _ALL_SELL_PREDICTIONS)
    selected_returns = [value for value, selected in zip(_DRIFT_RETURNS, mask) if selected]
    fixed_metrics = ModelMetrics(**metrics_module.trading_performance_metrics(selected_returns, _CONFIG.risk_free_rate))

    outcome, evidence = _resolve_hypothesis_outcome(fixed_metrics, test_sample_count=len(_DRIFT_RETURNS), config=_CONFIG)

    assert outcome == HypothesisOutcome.REJECTED


def test_characterizes_the_original_bug_unfiltered_drift_would_have_wrongly_accepted():
    """Documents the BEFORE state precisely, using the CTO plan's own
    numbers: computing trading metrics on the raw, UNFILTERED
    returns_test (what the old code did) gives a positive
    expected_value/sharpe_ratio purely from market drift, and
    _resolve_hypothesis_outcome would have ACCEPTED an all-SELL model
    on that basis alone. This is the defect this task fixes - the
    orchestration change (in ml_training/service.py's run_training_job)
    means this unfiltered path is never what actually reaches
    _resolve_hypothesis_outcome anymore; this test exists to prove the
    bug was real, not to exercise the current (fixed) call path."""
    unfiltered_metrics = ModelMetrics(**metrics_module.trading_performance_metrics(_DRIFT_RETURNS, _CONFIG.risk_free_rate))
    assert unfiltered_metrics.expected_value > 0
    assert unfiltered_metrics.sharpe_ratio > 0

    outcome, _evidence = _resolve_hypothesis_outcome(
        unfiltered_metrics, test_sample_count=len(_DRIFT_RETURNS), config=_CONFIG,
    )

    assert outcome == HypothesisOutcome.ACCEPTED


def test_a_model_that_actually_buys_and_profits_is_still_correctly_accepted():
    """Regression guard: the fix must not make every model REJECTED -
    a model that genuinely predicts BUY and profits on those specific
    calls must still be evaluated on its own (positive) selected
    returns and ACCEPTED."""
    predictions = np.array([Prediction.BUY.value] * len(_DRIFT_RETURNS))
    mask = _select_mask(LabelName.DIRECTION, predictions)
    selected_returns = [value for value, selected in zip(_DRIFT_RETURNS, mask) if selected]
    assert selected_returns == _DRIFT_RETURNS  # every sample was BUY'd this time

    metrics = ModelMetrics(**metrics_module.trading_performance_metrics(selected_returns, _CONFIG.risk_free_rate))
    outcome, _evidence = _resolve_hypothesis_outcome(metrics, test_sample_count=len(_DRIFT_RETURNS), config=_CONFIG)

    assert outcome == HypothesisOutcome.ACCEPTED

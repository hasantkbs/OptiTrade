# OptiTrade — CTO Remediation Plan

**Status:** Phase 0 (audit) complete. No production code has been changed by this plan. Everything below is read-only findings plus a proposed, phased plan — not yet implemented.

**Scope of this audit:** `decision_engine`, `pipeline`, `ml_training`, `model_serving`, `feature_store`, `research_lab`, `learning`, `engines`, `providers`, `portfolio`, `paper_trading`, plus the legacy `core/` decision paths (`core/hybrid_engine.py`, `core/advanced_analysis.py`) that this audit discovered sit outside `decision_engine` but still make live trading-signal decisions.

**Method:** three independent read-only audits against the current `main` branch (commit `f1966f4`), each required to verify claims against real code rather than assume them true, with exact file:line citations. One live, read-only Postgres query was run against the production `ml_training_model_registry` table to establish current model-promotion state. No files were edited; no destructive commands were run.

## 0. Executive Summary

Ten claimed issues were checked. **All ten are real** — four are fully confirmed as described, and six are confirmed with a material nuance that changes their severity or exact mechanism (noted per-finding below). The audit also surfaced **eight additional findings** outside the original ten, discovered while surveying `research_lab`, `learning`, `providers`, `portfolio`, and `paper_trading` structurally.

The single most severe finding is **not** in the originally-asked-about `decision_engine`/`pipeline` path: `core/hybrid_engine.py`, a separate, publicly-reachable decision path (`POST /api/v1/signals/analyze`), returns an **LLM-generated BUY/SELL signal as the final answer** whenever the canonical Decision Engine fails or has insufficient data (a threshold crossed whenever only 1 of 3 engines votes) — directly violating this mission's own stated constraint #2 ("LLMs may extract information and explain evidence, but must never generate or override investment decisions"). This is not a latent risk; it is pinned by six passing tests that assert the LLM's signal is returned, and it is live in production today.

The second-most severe finding is that the **Continuous Learning loop never runs in production**. Decisions are recorded, but nothing calls `evaluate_pending()` / `run_learning_cycle()` anywhere outside an offline shadow-evaluation script. No accuracy, calibration, or drift metric has been recomputed from a real production outcome, ever. This matters because several of the other findings' proposed fixes (calibrated confidence, a real expected-return regression, accuracy-weighted voting) all assume this loop is live — it is not, so those fixes cannot be built on top of it as-is.

Everything else clusters into two groups: (a) the **evaluation and validation pipeline measures the wrong thing** (promotion decisions are driven by market drift, not model skill, and there is no purge/embargo at any time-split boundary), and (b) **the system has no concept of prediction horizon** anywhere in its canonical decision path, while a separate legacy path (`core/advanced_analysis.py`'s `/analyze/enhanced`) is already blending 5-day and 30-day signals into one composite score today, and a third path (`core/investor_persona.py`) presents 1-month/1-year LLM opinions with numeric confidence scores that imply a validation history that does not exist.

No model is currently `ACTIVE` in production (`ml_training_model_registry` holds exactly 3 `CANDIDATE` rows, all `horizon_days=5`) — so several of these risks (horizon-mixing inside `decision_engine` specifically) are real but **not yet manifesting** there. They are already manifesting in the legacy `core/` paths, which remain live and publicly reachable.

---

## 1. Verified Findings

### Cluster A — Evaluation & Training Correctness

#### Finding 1: `ModelEvaluator` scores financial performance on all test-set returns, not the model's own decisions
**Verdict:** PARTIALLY TRUE — confirmed for the metrics that actually gate promotion; a filtered comparison exists elsewhere but is advisory only.

**Evidence:**
- `ml_training/service.py:141-147` builds `returns_test` from every test sample's realized forward return, independent of any prediction:
  ```python
  returns = [sample.labels.expected_return for sample in samples]
  return X, y, returns
  ```
- `ml_training/service.py:269`: `metrics = self.evaluation.evaluate(trainer, X_test, y_test, actual_returns=returns_test)`.
- `ml_training/evaluation/evaluator.py:37,50-52`: `y_pred` is computed but never used to filter `actual_returns` before they reach `trading_performance_metrics`.
- `ml_training/evaluation/metrics.py:120-127`: `expected_value`, `sharpe_ratio`, `sortino_ratio`, `max_drawdown`, `profit_factor` are all computed on that unfiltered list.
- `ml_training/service.py:309` + `:163-174` (`_resolve_hypothesis_outcome`): a hypothesis is ACCEPTED when `metrics.expected_value > 0 and metrics.sharpe_ratio > 0` — the unfiltered numbers.
- A filtered path exists (`ml_training/service.py:301-307`) but only feeds `self.benchmarking.compare_models(...)`, an advisory comparison that does not change ACCEPTED/REJECTED. `_select_mask` (`:150-160`) keeps only BUY calls for the DIRECTION label; SELL calls are dropped rather than sign-flipped, and HOLD days are excluded.
- `scripts/train_ml_candidate.py:~203-205` has the same flaw for the out-of-sample evaluation.
- Secondary issue: samples are pooled across symbols and sampled daily (`ml_training/datasets/builder.py:57,99`, `step_days=1`) against a 5-day label horizon, so consecutive "trades" overlap — Sharpe/drawdown then treat overlapping windows as independent sequential trades.

**Reproducible failure scenario:** A test set of 1,000 samples during a bull market, mean 5-day forward return +0.8%. A model that predicts SELL on every row still gets `expected_value=+0.8` and positive Sharpe, because the metric never looks at what the model predicted. `_resolve_hypothesis_outcome` returns ACCEPTED. The reverse also happens: a genuinely skilled model in a falling market gets REJECTED.

**Business impact:** Every number used to decide whether a candidate model is "good" (EV, Sharpe, Sortino, max drawdown, profit factor, and the ACCEPTED/REJECTED verdict itself) measures the market's drift over the test window, not the model's skill. Promotion decisions based on these numbers are uninformative by construction.

**Proposed minimal fix:** Build a strategy return series from `y_pred` inside `ModelEvaluator.evaluate` (+r for BUY, −r for SELL or 0 if long-only, excluded for HOLD/non-selected), pass that to `trading_performance_metrics` instead of raw `actual_returns`. Share the position logic with `_select_mask` so there's one definition. Keep the unconditional series as a separately-named `baseline_*` metric for comparison. Make sampling non-overlapping (step = horizon) or aggregate per-date before computing Sharpe/drawdown.

**Tests required:** an all-SELL predictor in a rising synthetic market gets negative `expected_value`/Sharpe and REJECTED; with 50% BUY/50% HOLD predictions, `trading_performance_metrics` receives exactly the BUY rows; `ModelMetrics.expected_value` differs from the unfiltered baseline whenever predictions aren't all-BUY.

---

#### Finding 2: `MLTrainingService`'s chronological split has no horizon-aware purge/embargo
**Verdict:** CONFIRMED TRUE — no purge, no embargo, split by sample count rather than date.

**Evidence:**
- `ml_training/service.py:328-347` (`_time_split`):
  ```python
  ordered = sorted(samples, key=lambda sample: sample.as_of)
  n = len(ordered)
  n_test = max(1, int(n * self.config.test_size))
  n_val = max(1, int(n * self.config.validation_size))
  train_samples = ordered[: n - n_val - n_test]
  val_samples = ordered[n - n_val - n_test : n - n_test]
  test_samples = ordered[n - n_test :]
  ```
  `horizon_days` is never passed to `_time_split` (call site `:252-254`). Grepping `ml_training/` for "embargo"/"purge" finds nothing.
- Labels look forward `horizon_days` plus up to 5 extra days (`ml_training/labels/generator.py:46,62-71`). Samples are daily and multi-symbol (`ml_training/datasets/builder.py:57,99`), so many samples share one `as_of`.
- `scripts/train_ml_candidate.py:~192` has a fixed 1-day gap (`held_out_start = train_end_date + timedelta(days=1)`), independent of `HORIZON_DAYS=5` (line 68).
- The model actually serving the legacy live path is worse: `research/ml_trainer.py:264-266,282` uses a **random** `train_test_split`/`StratifiedKFold`, not chronological at all — confirmed by the file's own docstring (lines 18-20).

**Reproducible failure scenario:** With `horizon_days=5`, a train sample on day T has a label from `Close[T+5]`. Val/test samples on days T+1..T+4 share overlapping forward windows with the train sample right next to the boundary — the split leaks label information across every boundary it draws, both by horizon-overlap and by the count-based cut landing mid-date across symbols.

**Business impact:** Held-out accuracy/AUC are inflated by boundary leakage, worse for longer horizons. The val set (used for early-stopping, Optuna tuning, and isotonic calibration — see Finding 6) inherits the same leakage, so hyperparameters and calibration maps are biased by it too. The model actually live today (`xgb_signal_model.joblib`) has a fully random split and cannot even detect this problem in its own reported `cv_accuracy`.

**Proposed minimal fix:** Give `_time_split` the horizon; split on unique sorted dates, never sample index; drop every sample within `horizon_days + buffer` of each split boundary. Apply the same rule in `scripts/train_ml_candidate.py`. Replace `research/ml_trainer.py`'s random split with a purged, chronological one.

**Tests required:** `max(train.as_of) + horizon_days(+buffer) < min(val.as_of)` and the same val→test; no date appears in more than one split; increasing `horizon_days` increases the number of purged rows.

---

#### Finding 3: Historical label prices can come from a different provider than live inference prices
**Verdict:** CONFIRMED TRUE for US symbols (when `FINNHUB_API_KEY` is set) and all crypto; does not apply to BIST/Japan, which use yfinance both ways. Extends beyond "labels" — training features and labels can be mixed-vendor within one sample.

**Evidence:**
- Training-label prices are always yfinance: `data/fetcher.py:93-100` hard-codes `yf.Ticker(symbol).history(...)`, used by `ml_training/labels/generator.py:33,60,66`, `ml_training/datasets/builder.py:23,47`, `scripts/train_ml_candidate.py:86`, and `research/ml_trainer.py:140-148,161-162`.
- Live inference prices route through the provider registry: `engines/technical/feature_adapter.py:234` → `fetch_history` → `data/fetcher.py:20-23` → `get_market_provider().fetch_ohlcv(...)` → `providers/registry.py:45-48` (default `HYBRID`) → `providers/hybrid_provider.py:39-47`:
  ```python
  if sym.endswith(".IS") or sym.endswith(".T"):
      return self._yfinance
  if sym.endswith("-USD"):
      return self._binance
  if self._finnhub_enabled:
      return self._finnhub
  return self._yfinance
  ```
- Finnhub and Binance return raw OHLCV with no adjustment handling; yfinance's `history()` is split/dividend-adjusted by default. One training row can therefore combine Finnhub- or Binance-sourced live features with a yfinance-sourced label.

**Reproducible failure scenario:** For BTC-USD, the live Technical Engine computes ATR/RSI/trend from Binance BTCUSDT daily klines; the training label comes from Yahoo's BTC-USD aggregate series, with different daily-bar boundaries and no shared adjustment convention. A label near the decision threshold can flip class purely from vendor disagreement. For US equities, an ex-dividend/split date shifts yfinance's adjusted series while Finnhub's raw candles don't move, so the label's return calculation and the feature's ATR% refer to different price series for the same nominal date.

**Business impact:** Labels near the decision threshold are noisy in a systematic, vendor-dependent way; the model learns a feature→label mapping the live system cannot reproduce. Crypto is the worst case — every live crypto vote uses Binance, every crypto label uses Yahoo.

**Proposed minimal fix:** Add a provider-routed range method (`fetch_ohlcv_range`) to the `MarketDataProvider` protocol (`providers/base.py`); point `data/fetcher.py::fetch_price_history_range` at it; make the adjustment policy explicit and consistent across providers; record which vendor served each training bar so mixed-vendor samples can be rejected or audited.

**Tests required:** with an injected fake provider, `generate_labels` and `fetch_history` both read the fake, never `yf.Ticker` directly; for a `-USD` symbol, labels route to Binance; a dataset-build test asserts every sample's feature vendor equals its label vendor.

---

### Cluster B — Decision Architecture & Horizon Mixing

#### Finding 4: `EngineVote` and `DecisionOutput` carry no prediction-horizon field
**Verdict:** CONFIRMED TRUE.

**Evidence:** `decision_engine/models.py:23-61`, full definitions:
```python
class Prediction(str, Enum):          # :23
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"

class EngineVote(BaseModel):          # :29
    engine_name: str
    engine_version: str
    prediction: Prediction
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_return: float
    volatility: float
    evidence: List[str] = Field(default_factory=list)
    timestamp: datetime = ...

class DecisionOutput(BaseModel):      # :49
    symbol: str
    decision: Prediction
    confidence: float = Field(..., ge=0.0, le=1.0)
    expected_return: float
    expected_volatility: float
    aggregation_strategy_version: str
    data_sufficiency: float = Field(..., ge=0.0, le=1.0)
    evidence: List[str] = Field(default_factory=list)
    engine_results: List[EngineVote] = Field(default_factory=list)
    timestamp: datetime = ...
```
No `horizon`/`horizon_days`/`target_date` field anywhere. `expected_return` has no stated period, and each engine scales it differently (ATR-based for Technical, fixed `%` constants for Fundamental/News — see Finding 7). The ML side **does** carry horizon internally (`ml_training/models.py` has `horizon_days`; model serving is keyed by `(label_name, horizon_days)`), but it is dropped the moment a model becomes a vote: `ml_training/shadow/adapter.py:61,89-91` builds an `EngineVote` with no horizon field to carry it.

**Reproducible failure scenario:** Technical votes BUY with a few-days ATR-scale `expected_return=+1.2`; Fundamental votes BUY with a months-scale valuation thesis `expected_return=+6.0`. The aggregator averages them to `~+3.6%`, a figure belonging to no horizon, which `LearningTracker` then grades against a fixed 5-day realized return regardless of which engine was "right" over which actual timeframe.

**Business impact:** `expected_return`/`confidence` average quantities measured over different holding periods. A correct long-horizon thesis graded at 5 days looks wrong and gets down-weighted by accuracy weighting, independent of whether it was actually right.

**Proposed minimal fix:** Add `horizon_days: int = Field(..., gt=0)` to `EngineVote` and `DecisionOutput`; define `expected_return` as "% over `horizon_days`"; have each engine (and the ML adapter) declare its own horizon in config; have `LearningTracker` evaluate each sample at its own vote's horizon, not the single global `evaluation_horizon_days`.

**Tests required:** constructing either model without `horizon_days` raises; each engine/adapter emits its configured horizon; `DecisionOutput.horizon_days` matches the votes it was built from; `LearningTracker` stores the sample's own horizon, not the global default.

---

#### Finding 5: Multiple active horizon models can enter the same aggregated decision
**Verdict:** PARTIALLY TRUE — a latent, unguarded risk in `decision_engine` (zero ACTIVE models today), but **already happening live** in the legacy `/analyze/enhanced` composite.

**Evidence (latent path):** `model_serving/service.py:154-167` collects every ACTIVE DIRECTION model across every `(label, horizon_days)` combination with no horizon filter, and `pipeline/service.py:111-112` merges them all into one `aggregate_votes` call with the rule-based engines. A live, read-only query against `ml_training_model_registry` found:
```
promotion_state | label_name | horizon_days | count
candidate        | direction  |            5 |     3
```
Zero ACTIVE, one horizon (5 days) in the whole registry — so this specific mixing cannot manifest in `decision_engine` *yet*. Nothing in `get_active_engines()`, `PipelineService.run()`, or `aggregate_votes()` would stop it the moment a second horizon is promoted.

**Evidence (live path, mixing already happening):** `core/advanced_analysis.py:190-238` (`compute_recommendation`) blends four horizon-inconsistent inputs into one `composite` score: the canonical decision (no horizon, graded at 5 days, 40% weight), an XGBoost model trained with `FORWARD_DAYS=5` (25%), a Monte Carlo simulation with caller-controlled, unbounded `n_days` (default 30, 20% weight — `main.py:1665-1669` passes `n_days=body.n_days` straight from the request body), and Chart-AI with `FORWARD_DAYS=5` (15%). `RecommendationResult` has no horizon field either.

**Reproducible failure scenario (live today):** `POST /analyze/enhanced {"symbol":"AAPL","n_days":365}` blends a 365-day Monte Carlo expected return with two 5-day model signals into one `action_code`/`suggested_position_pct`, with no indication to the caller that the inputs disagree on timeframe.

**Business impact:** Once any second-horizon model is promoted, the canonical ensemble becomes unmeasurable in the same way the legacy path already is. The learning loop will penalize a correct long-horizon model for being graded at the wrong horizon.

**Proposed minimal fix:** After Finding 4's fix, make `DecisionEngine.decide`/`PipelineService.run` take a target `horizon_days` and filter active engines to it; add a guard in `aggregate_votes()` that raises on mixed-horizon votes. For `compute_recommendation`, either bound `n_days` to match its other inputs' horizon or drop Monte Carlo from the composite score entirely (show it as separate context).

**Tests required:** with two ACTIVE models at different horizons, `get_active_engines(horizon_days=5)` returns only the matching one; `aggregate_votes()` raises on mixed horizons; `compute_recommendation` rejects or excludes an out-of-horizon Monte Carlo term.

---

#### Finding 6: "Confidence" is weighted vote consensus, not a calibrated probability
**Verdict:** PARTIALLY TRUE — real isotonic calibration exists one level down (for ML votes only, on a non-purged validation set), but the number actually surfaced as `confidence` is uncalibrated consensus.

**Evidence:**
- `decision_engine/aggregation.py:27-32,58-69`:
  ```python
  def _effective_weight(vote: EngineVote, accuracy_weight: float) -> float:
      return accuracy_weight * vote.confidence
  ...
  confidence = category_weight[decision] / total_weight
  ```
  passed straight into `DecisionOutput.confidence` (`decision_engine/service.py:96-104`) with no transformation.
- Rule-based engines' own confidence is a plain mean of analyzer confidences (`engines/technical/engine.py:126-129`, same pattern in `engines/fundamental/engine.py`).
- Real calibration exists, but only for ML model votes: `ml_training/calibration/calibrator.py` fits `CalibratedClassifierCV(..., method=ISOTONIC)` (`ml_training/service.py:279-284`), served preferentially when it exists (`model_serving/loader.py:76-80,184`). **This fit uses the same validation split flagged as leaky in Finding 2**, so it is optimistic. `learning/calibration.py:22-51` only *measures* ECE/reliability — it never corrects any confidence value. `decision_engine/` itself contains no calibration of any kind.

**Reproducible failure scenario:** Two weak engines vote BUY with accuracy weight 1.0 each, confidences 0.30 and 0.25 — `category_weight[BUY]/total_weight = 1.0`, so the output is "BUY, confidence 100%" from two weak signals that happen to agree.

**Business impact:** `DecisionOutput.confidence` is shown to users as a reliability estimate and would feed position sizing, but any agreement among votes pushes it toward 1.0 regardless of how weak the underlying votes are.

**Proposed minimal fix:** Rename the current aggregate to `consensus`; add a calibrated `confidence` fit per `aggregation_strategy_version` from evaluated `DecisionOutput` outcomes once the learning loop is actually running (Finding A2, below) — note the dependency: this fix cannot be built correctly until that loop exists.

**Tests required:** two weak-but-unanimous votes must not calibrate to confidence 1.0; on a synthetic outcome set where 60% of consensus=0.9 decisions were correct, calibrated confidence lands near 0.6 and ECE drops versus the uncalibrated value.

---

#### Finding 7: "Expected return" is a signal-strength proxy, not a trained forecast
**Verdict:** CONFIRMED TRUE.

**Evidence:**
- `decision_engine/aggregation.py:62,70`: aggregate `expected_return` is a confidence-weighted average of each vote's own `expected_return`.
- Each engine computes its own `expected_return` as `net_signal * (a fixed scale constant)`: Technical multiplies by ATR% (`engines/technical/engine.py:72-74`, scale=1.0, `engines/technical/config.py:70`); Fundamental multiplies by a flat 10.0% scale (`engines/fundamental/config.py:80`); News by a flat 8.0% scale (`engines/news/config.py:44`); the ML adapter by a flat 10.0% scale applied to `p_buy - p_sell` (`ml_training/shadow/adapter.py:81-84`, `ml_training/config.py:66` — this module's own docstring admits it's a fallback because "a classifier has no natural per-vote magnitude").
- `expected_volatility` is a flat config constant too (`ml_training/shadow/adapter.py:85`).
- A real `EXPECTED_RETURN` regression label exists in `ml_training` (`ml_training/service.py:85-86,126-127`), but `MLModelVotingEngineAdapter.vote` never uses a trained regression model's output — it always derives `expected_return` from the scaled classification probabilities instead.

**Reproducible failure scenario:** A Fundamental vote with `net_signal=+0.5` always reports `expected_return=+5.0%` regardless of the stock's actual volatility or any realized-return relationship; an ML vote with `P(BUY)=0.55` reports the same +5.0% magnitude. The aggregate averages numbers on different scales with no common unit, and changing an env var changes the "forecast" with zero change in market information.

**Business impact:** Opportunity ranking, portfolio optimization, and paper-trading position sizing all reference `expected_return` as if it were a forecast; none of it is fit against realized returns, so its own tracked MAE (in `learning/`, once that loop runs) can never improve through training.

**Proposed minimal fix:** Fit a per-engine map from `net_signal` to realized forward return using evaluated outcomes (again depends on the learning loop actually running); for engines with a trained `EXPECTED_RETURN` regression model, use its `predict()` output directly instead of the scaled proxy. Until then, rename the field or document it explicitly as a signal-strength proxy in the API.

**Tests required:** on synthetic outcomes with a known true slope, the fitted map recovers it and `expected_return` tracks the map, not the scale constant; a regression-label model's vote uses its own `predict()` output.

---

### Cluster C — LLM Decision Boundary

#### Finding 8: an LLM-generated trading signal can become the final answer
**Verdict:** CONFIRMED TRUE — intentional, documented, pinned by six passing tests, and reachable from a public endpoint. **This is the audit's highest-severity finding.**

**Evidence:**
- `core/ai_trader_persona.py:108` — the LLM's tool schema includes `signal: TradeSignal` directly on `TradeRecommendation`.
- `core/hybrid_engine.py:168-182` (trader profile): the LLM generates a recommendation (including its own signal) first; a canonical override is then *attempted*.
- `core/hybrid_engine.py:214-241` (`_apply_canonical_decision`), with the module's own docstring:
  ```python
  """A Decision Engine failure (infra down, zero valid votes, etc.)
  falls back to the LLM's own signal rather than dropping the
  recommendation entirely ..."""
  try:
      decision_output = decision_engine.decide(symbol, strict=True)
  except Exception as exc:
      logger.error(f"{symbol}: decision engine yetkisi uygulanamadi, LLM sinyali korunuyor: {exc}")
      return recommendation                       # LLM signal returned as-is
  if not is_data_sufficient(decision_output):
      logger.warning(... "LLM sinyali korunuyor")
      return recommendation                       # LLM signal returned as-is
  ```
  The investor profile has the identical pattern (`core/hybrid_engine.py:268-278`).
- The data-sufficiency gate: `core/analysis_presentation.py:48-50,195-210` requires `data_sufficiency >= 0.34`; `data_sufficiency = len(votes) / len(registered engines)` (`decision_engine/service.py:99`) — with 3 registered engines, **1 vote out of 3 gives 0.333, below the 0.34 threshold**, so the LLM's signal is kept whenever only one of Technical/Fundamental/News actually voted.
- Publicly reachable: `POST /api/v1/signals/analyze` (`api/v1/endpoints/signals.py:67-105`, rate-limited 20/min, mounted at `main.py:376`) returns the engine's output directly, with results cached 15 minutes (`core/hybrid_engine.py:48,192`) — one bad LLM call is served to every caller for that window.
- No provenance field exists anywhere (`TradeRecommendation`, `HorizonView`) to let a client distinguish an LLM-origin signal from a Decision-Engine-origin one.
- Six existing tests assert this exact fallback behavior and would need to be rewritten to assert the opposite: `tests/test_hybrid_engine.py:294,339`; `tests/unit/test_hybrid_engine.py:295,333,358,379`.
- The rest of the LLM surface is clean by contrast: `explanation_engine/groq_provider.py` only explains an already-final `DecisionOutput` and its prompt explicitly forbids proposing a different decision; `explanation_engine/fallback.py` is a deterministic template; `pipeline/service.py` has no LLM fallback at all.

**Reproducible failure scenario:** `POST /api/v1/signals/analyze {"symbols":["BTC-USD"],"profile":"trader"}` where Fundamental abstains for crypto and News has no articles — only Technical votes, `data_sufficiency ≈ 0.333 < 0.34`, and the response is the Groq-generated `signal`/`confidence_score` unchanged, served from cache to every caller for 15 minutes.

**Business impact:** This is a direct violation of this mission's stated constraint #2, occurring exactly when evidence is weakest. The signal is non-reproducible (temperature-driven), never backtested, and indistinguishable from a statistically-grounded one to any caller.

**Proposed minimal fix:** In both fallback sites, replace `return recommendation` with a `NEUTRAL`/zero-confidence result (or drop the symbol); add `signal_source: Literal["decision_engine","unavailable"]`, set only by `core/hybrid_engine.py`, never by the LLM; remove `signal`/`confidence_score` from the LLM's own tool schema so it cannot emit a decision value at all; stop caching fallback results, or cache them for seconds not minutes.

**Tests required:** rewrite all six existing tests to assert the LLM's fake signal never appears on either failure path, for both profiles; assert `signal_source` is set correctly; assert the tool schema itself no longer contains `signal`/`confidence_score` keys.

---

#### Finding 9: non-1-week investor horizons are pure LLM output with no trained model behind them
**Verdict:** CONFIRMED TRUE, with the nuance that the 1-week view's "override" is also not actually a validated 1-week model.

**Evidence:**
- `core/investor_persona.py:38-56` system prompt instructs the LLM to independently produce a `signal` and numeric `confidence_score` (0-100) for each of 1-week, 1-month, and 1-year, explicitly telling it to do so for the 1-year horizon **without** fundamentals data ("Temel analiz ... verisi SANA SAĞLANMADI — bunu tahmin etme").
- `core/investor_persona.py:89-114,134-163`: the tool schema requires signal+confidence+rationale per horizon; `Groq.chat.completions.create(temperature=0.3, ...)` output is validated directly into `InvestorRecommendation` with no model in between.
- No trained 1-month or 1-year model exists anywhere — the registry query in Finding 5 confirms only `horizon_days=5` candidates exist, and every training script hardcodes `HORIZON_DAYS=5`.
- `core/hybrid_engine.py:279-283` overrides **only** `horizon_1_week` with `decide()`'s output — but per Finding 4, `decide()` has no horizon concept of its own; it's graded at a fixed 5 trading days by convention, not validated specifically as a 1-week model. And per Finding 8, even that override is skipped on the same two fallback paths, so `horizon_1_week` can also silently stay fully LLM-generated.
- Publicly reachable via the same `POST /api/v1/signals/analyze` endpoint with `profile="investor"`, whose field description promises a "1-week/1-month/1-year uzun vadeli görüş" (long-term view).

**Reproducible failure scenario:** `POST /api/v1/signals/analyze {"symbols":["THYAO.IS"],"profile":"investor"}` returns `horizon_1_month`/`horizon_1_year` signals and confidence scores (e.g. `STRONG_BUY`, 85) that are pure LLM inference from RSI/MACD/EMA inputs, re-generated (and potentially flipping) every 15 minutes with no change in underlying data, indistinguishable from a validated forecast.

**Business impact:** Two of three investor-facing directional calls, with numeric confidence scores implying statistical grounding, have no training, validation, calibration, or outcome tracking at all — the primary credibility and regulatory risk of this finding.

**Proposed minimal fix:** Make `horizon_1_month`/`horizon_1_year` nullable until real horizon-tagged models exist (depends on Finding 4/5's horizon work); remove `signal`/`confidence_score` from the LLM's tool schema for those horizons, keeping only `rationale` as labelled narrative; add the same `signal_source` provenance field as Finding 8.

**Tests required:** with a fake persona returning a strong signal for the unvalidated horizons, the final output nulls them out with `signal_source == "unavailable"`; the tool schema for those horizons contains no signal/confidence keys.

---

### Cluster D — Operational Visibility

#### Finding 10: `/health` verifies nothing, and the deeper check also always returns 200
**Verdict:** CONFIRMED TRUE — worse than claimed.

**Evidence:**
- `main.py:1323-1325` is entirely static, touching no dependency:
  ```python
  @app.get("/health")
  def health() -> Dict[str, str]:
      return {"status": "healthy"}
  ```
- `main.py:1327-1334` (`/feature-store/health`) does run a real check (`feature_store/service.py:171-194`: Redis PING + Postgres `SELECT 1`, each wrapped in its own try/except) — **but it never returns a non-2xx status**, even when both stores are down; it just returns `{"online_store_available": false, "offline_store_available": false}` with HTTP 200. Its own docstring (lines 172-174) is stale, still claiming it's "not wired into any HTTP endpoint yet."
- A third, richer check exists at `/quant/model-serving/health` (`main.py:1780-1786`, 503 if `_pipeline_service is None`) — nothing probes it either.
- **All HEALTHCHECK targets point at the static endpoint:** `backend/Dockerfile:90-91`, `docker-compose.yml:165-170` (`api` service), and `docker-compose.yml:52-54` (`proxy`'s own startup is gated on `api`'s healthcheck, i.e. on this exact static check). Postgres and Redis, by contrast, have real healthchecks (`pg_isready`, `redis-cli ping`).
- **Startup failures are swallowed, making the static check actively misleading:** `main.py:806-817`, `PipelineService()` construction is wrapped in `try/except Exception: logger.error(...)` and the process continues with `_pipeline_service = None`. Every other service-group initialization follows the same pattern.
- A backward-compatibility test pins the exact current body: `tests/test_main_backward_compatibility.py:40-43` asserts `{"status": "healthy"}` — any fix must keep a liveness-only `/health` unchanged and add readiness elsewhere.

**Reproducible failure scenario:** Postgres becomes unreachable at boot. `PipelineService()` raises, startup logs and swallows it. `/health` returns 200. Docker marks `api` healthy; `proxy` starts and routes real traffic to it. Every `/quant/*` call now returns 503, and `/feature-store/health` itself returns 200 with `offline_store_available: false` — no orchestrator or monitor ever sees red. (Separately: even a correct Docker healthcheck doesn't auto-restart on `unhealthy` under plain `restart: unless-stopped` without an autoheal sidecar.)

**Business impact:** The platform can serve zero signals, or silently drop learning-tracker writes, for an unbounded time while every health signal stays green.

**Proposed minimal fix:** Keep `/health` as a cheap liveness probe (unchanged, keeps the pinned test green). Add `/health/ready`, returning 503 unless `_pipeline_service is not None` AND the feature store reports both stores up AND model serving reports no load failures. Make `/feature-store/health` itself return 503 on any false flag. Point the Dockerfile `HEALTHCHECK` and compose `api.healthcheck` at `/health/ready`.

**Tests required:** `/health/ready` returns 503 when either store is stubbed to fail, and when `_pipeline_service is None`; `/feature-store/health` returns 503 on any false flag; a static test asserts the Dockerfile/compose healthcheck URL is `/health/ready`; `test_health_endpoint_unchanged` stays green.

---

### Additional Findings (surfaced by the structural survey, outside the original 10)

#### Finding A1: `research_lab` isolation is enforced only against direct imports, and is broken transitively
**Verdict:** the isolation *test* passes; the isolation *guarantee* does not hold.

`tests/test_research_isolation.py` (17 passing tests) AST-scans production directories for direct `import research`/`research_lab`/`ml_training` and finds none — but `ml_training` imports `research_lab` extensively (benchmarking, promotion, base repository classes, shadow evaluation — `ml_training/__init__.py:20`, `ml_training/registry/service.py:26-27`, `ml_training/registry/repository.py:28`, `ml_training/shadow/service.py:32`, `ml_training/evaluation/metrics.py:40-41`), and `model_serving` imports `ml_training` (`model_serving/loader.py:44-48`, `rollback.py:43`, `shadow.py:32`, `inference.py:31-34`), and `main.py:93-94` imports `model_serving`. **Empirically verified: `import model_serving` loads 47 `research_lab.*` modules into the live API process.** The model-registry repository that resolves ACTIVE models for live inference even inherits `research_lab.base_repository.PostgresRepositoryBase`, so research-lab connection-pool code runs on every live registry read.

**Business impact:** the stated constraint #5 ("research experiments must remain isolated from production inference") is not actually true today; it only *looks* true to the one test that checks it.

**Proposed minimal fix:** either (a) move `PostgresRepositoryBase` and the promotion-recommendation surface `ml_training` needs out of `research_lab` into a shared, neutral module both packages can depend on, or (b) extend the isolation test to do a transitive import-graph check (not just direct), and accept/fix whatever it then reports. Given `model_serving` legitimately needs *some* bridge to the registry, option (a) is the more durable fix.

**Tests required:** a transitive-import-closure test from each `PRODUCTION_DIRS` entry (and from `main.py`) proves no `research_lab.*` module is ever loaded as a side effect.

---

#### Finding A2: the Continuous Learning loop never runs in production
**Verdict:** confirmed — this is the audit's second-highest-severity finding, because several other findings' proposed fixes depend on it.

Recording is wired (`pipeline/pipeline.py:39,83,200` calls `record_decision` on every run); retention purge is wired (`main.py:799`); dashboards read from it. **But nothing in `main.py`, any cron job, or any script calls `run_learning_cycle()` / `LearningScheduler.run_once()` / `OutcomeEvaluator.evaluate_pending()`** outside an offline shadow-evaluation workflow. `learning/scheduler.py`'s own header says this is deliberate — "the orchestration logic an external scheduler calls on each tick... out of scope here per 'do not integrate endpoints yet'" — but no such external scheduler was ever actually wired up. `crontab -l` on the production host shows only the backup job and the weekly chart-model retrain.

**Business impact:** accuracy, calibration, and drift have never been recomputed from a single real production outcome. The accuracy-weighted voting in `decision_engine/weighting.py` is running on whatever weights were last set (likely defaults), not on anything learned from live performance. This is also why Findings 6 and 7's proposed fixes (calibrated confidence, a trained expected-return map) explicitly note they cannot be correctly built until this loop is live.

**Proposed minimal fix:** add a background loop (same shape as the other `*_loop` functions already in `main.py`, e.g. `market_opportunities_refresh_loop`) that calls `run_learning_cycle()` on a daily cadence, gated behind the pipeline-service-ready check the other loops already use.

**Tests required:** a loop test (mirroring the existing `test_main_background_scan_loops.py` style) confirming the cycle actually runs on schedule and that a learning sample recorded `evaluation_horizon_days` ago gets evaluated.

---

#### Finding A3: the learning evaluator has the same price-provider mismatch as Finding 3, now affecting outcome scoring too
`learning/evaluator.py`'s `OutcomeEvaluator` calls `data/fetcher.py::fetch_price_history_range`, which (per Finding 3) is hard-coded to yfinance — while the original decision for crypto/US-with-Finnhub symbols was made against Binance/Finnhub prices. A decision can be scored against prices it was never actually made on. **Fix is the same as Finding 3's** (route through the provider registry) and should land in the same change.

#### Finding A4: the `providers/` abstraction is bypassed by a large fraction of production code
`data/fetcher.py` itself only routes `fetch_history`/`fetch_info`/`get_balance_status` through the registry — `fetch_financials`, `fetch_balance_sheet`, `fetch_cashflow_statement`, and `fetch_price_history_range` call `yf.Ticker` directly (feeding the Fundamental engine and the learning evaluator). Direct `yf.` calls also appear in `main.py` (chart-AI), `core/regime_scanner.py`, `core/mtf_analyzer.py`, `core/monitoring.py`, `v2/api/router.py`, and `dashboard/config.py`. The Protocol also has no range-based OHLCV method, which is *why* several of these went around it in the first place. **Proposed fix:** add the missing range method to the Protocol (same work as Finding 3), then migrate each bypass call site one at a time behind its own test.

#### Finding A5: `portfolio/` has no FX conversion for multi-currency portfolios
`portfolio/analytics.py:46-58` sums `quantity * current_price` across positions in each symbol's *native* currency (TRY for `.IS`, USD for US) even though a `base_currency` field and a per-position currency already exist elsewhere in the module. A mixed BIST+US portfolio gets a meaningless total value, weight, and risk/optimizer input. **Proposed fix:** convert every position to `base_currency` before aggregating, using the same provider-routed FX rate source recommended for Findings 3/A3/A4.

#### Finding A6: `portfolio/` silently drops unpriced positions from `total_value`
Same file, line 47 — a position with no resolvable current price is dropped from the denominator with no warning, which inflates the weights of the remaining positions and understates total value. **Proposed fix:** either fail the request loudly or flag the affected position explicitly in the response.

#### Finding A7: `paper_trading/` applies BIST market hours to every non-crypto symbol, including US equities, and its scheduler ignores market hours entirely
`paper_trading/config.py:24-28,58-60` defaults to `Europe/Istanbul`, 10:00-18:00, applied to US equities too (`execution.py:38-45`, with no env override in any compose/env file found). Separately, `paper_trading/scheduler.py:47-72` never calls `is_market_open` at all when filling resting LIMIT/STOP/TAKE_PROFIT orders — contradicting its own code comment that resting orders "won't be evaluated... until the market reopens" — so it fills them at any hour against a stale daily-close price (see Finding A5's sibling note on `PriceService`). **Proposed fix:** make market-hours config per-market (reusing `core/market_config.py`'s existing TR/US/CRYPTO distinction, already used elsewhere in this codebase), and have the scheduler actually check it before filling.

#### Finding A8: paper-trading fill-then-sync is not atomic
`paper_trading/scheduler.py:92-93` calls `record_fill` (persists the fill, marks the order FILLED) and then `portfolio_sync.sync_fill` as two separate steps; only `PaperTradingError` is caught, so a failure in between leaves an order marked FILLED with no corresponding portfolio transaction, and the order is never rescanned. **Proposed fix:** wrap both steps in one transaction, or make `sync_fill` idempotent and retryable from a FILLED-but-unsynced state detected on the next scan.

---

## 2. Prioritized Issues

| ID | Title | Priority | Why |
|---|---|---|---|
| F8 | LLM can return a final BUY/SELL signal | **P0** | Direct, live violation of this mission's own stated constraint #2; publicly reachable; tests currently *assert* the violation |
| F10 | `/health` verifies nothing; startup failures swallowed | **P0** | Total operational blindness; the platform can be fully broken while reporting healthy indefinitely |
| A2 | Learning loop never runs | **P0** | Nothing downstream (calibration, accuracy weighting, expected-return fitting) can be correctly built until this exists |
| F1 | Promotion metrics measure market drift, not skill | **P0** | Corrupts every future model-promotion decision at the root |
| F2 | No purge/embargo at split boundaries | **P0** | Corrupts the validation that F1's fix would otherwise rely on being trustworthy |
| F9 | 1-month/1-year investor signals are unvalidated LLM output | **P1** | Serious credibility/regulatory risk, but narrower blast radius than F8 (advisory framing exists, if thin) |
| F3 / A3 | Label vs. live price-provider mismatch (training + outcome scoring) | **P1** | Real, systematic noise injection into both training and the (currently-dormant) learning loop |
| F4 | No horizon field anywhere in the canonical decision model | **P1** | Foundational for Phase 2; not yet causing live harm in `decision_engine` itself (no ACTIVE multi-horizon models) |
| F5 | Horizon mixing | **P1** | Latent in `decision_engine`; **already live** in `core/advanced_analysis.py`'s composite score |
| F6 | Confidence is uncalibrated consensus | **P1** | Real, but its correct fix is blocked on A2 |
| F7 | Expected return is a proxy, not a forecast | **P1** | Real, but its correct fix is blocked on A2 |
| A1 | research_lab isolation broken transitively | **P1** | Violates stated constraint #5; mitigated somewhat by `model_serving` being the only bridge, but the guarantee as tested is false |
| A4 | Provider abstraction bypassed widely | **P1** | Root cause underlying F3/A3; fixing the Protocol gap is prerequisite work for both |
| A5 | No FX conversion in portfolio aggregation | **P2** | Real correctness bug, narrower blast radius (multi-currency portfolios only) |
| A6 | Unpriced positions silently dropped | **P2** | Real, narrow |
| A7 | Wrong market hours for US paper trading; scheduler ignores hours | **P2** | Real, confined to paper trading simulation fidelity |
| A8 | Paper-trading fill/sync not atomic | **P2** | Real, narrow, recoverable via a reconciliation job |

---

## 3. Architecture Changes

**Decision model (Findings 4, 5, 6, 7):** `EngineVote` and `DecisionOutput` gain a required `horizon_days: int`. `DecisionEngine.decide()` and `PipelineService.run()` gain an explicit `horizon_days` parameter; `aggregate_votes()` refuses to mix horizons. `confidence` is split into an always-available `consensus` (today's number, renamed) and a `confidence` that is only populated once a real calibration map exists (depends on A2). `expected_return`'s per-engine scale constants are replaced by a fitted signal→realized-return map per engine per horizon, with the raw proxy kept as a fallback only until enough outcome data exists.

**Provider unification (Findings 3, A3, A4):** `MarketDataProvider` gains a `fetch_ohlcv_range` method implemented by every concrete provider; `data/fetcher.py`'s remaining direct-`yf.Ticker` functions (`fetch_financials`, `fetch_balance_sheet`, `fetch_cashflow_statement`, `fetch_price_history_range`) route through the registry; the training-label path and the `learning` evaluator both switch to the same routed call, closing the train/serve/evaluate price-source gap in one change.

**LLM decision boundary (Findings 8, 9):** the LLM's tool schemas (`core/ai_trader_persona.py`, `core/investor_persona.py`) are stripped of `signal`/`confidence_score` fields entirely wherever no validated model backs that horizon; a `signal_source` provenance field is added to every response surface the LLM touches, set only by the orchestrating code, never by the LLM itself. This is the most isolated, lowest-dependency change in this plan and should ship first.

**Continuous Learning activation (Finding A2):** a new `learning_cycle_loop` background task, same shape as the existing `main.py` loops, actually calls what already exists in `learning/`. No new learning logic is needed — only wiring.

**Evaluation correctness (Findings 1, 2):** `ModelEvaluator` is changed to score a strategy return series derived from the model's own predictions, not the raw test-set return series; `_time_split` becomes horizon-aware with real purge/embargo. These two changes gate all future model promotions and should land before any new model is promoted to ACTIVE.

**Operational health (Finding 10):** a new `/health/ready` endpoint and a corrected `/feature-store/health` status code; Docker/Compose healthchecks repointed at the new endpoint; `/health` itself is untouched (keeps the pinned backward-compatibility test green).

**Isolation hardening (Finding A1):** `PostgresRepositoryBase` and the minimal promotion-read surface `model_serving` actually needs move to a new, neutral module (e.g. `platform_db/` or similar) that both `research_lab` and `ml_training`/`model_serving` depend on, instead of `ml_training`/`model_serving` depending on `research_lab` directly.

These map onto the original mission's Phase 1/2/3 as follows: the evaluation, provider, and learning-loop fixes above **are** Phase 1 ("Quantitative Correctness") — they must land before Phase 2 can produce a trustworthy medium/long-horizon model. The horizon field (Finding 4) is the prerequisite data-model change Phase 2 ("Multi-Horizon Architecture") needs before any medium/long-horizon model can be trained, registered, served, or voted with safely. Phase 3 ("Crypto Intelligence" — funding rates, OI, liquidations, on-chain, etc.) is additive new feature/provider work and has no hard dependency on anything in this plan except that it should land its own price data through the same provider-registry pattern (Finding A4) rather than bypassing it the way several existing crypto paths already do.

## 4. Affected Files

**Decision model / horizon:** `decision_engine/models.py`, `decision_engine/aggregation.py`, `decision_engine/service.py`, `decision_engine/weighting.py`, `pipeline/service.py`, `model_serving/service.py`, `ml_training/shadow/adapter.py`, `engines/technical/engine.py`, `engines/fundamental/engine.py`, `engines/news/engine.py`.

**Evaluation:** `ml_training/evaluation/evaluator.py`, `ml_training/evaluation/metrics.py`, `ml_training/service.py`, `scripts/train_ml_candidate*.py`, `research/ml_trainer.py`.

**Providers:** `providers/base.py`, `providers/hybrid_provider.py`, `providers/binance_provider.py`, `providers/finnhub_provider.py`, `providers/yfinance_provider.py`, `data/fetcher.py`, `learning/evaluator.py`.

**LLM boundary:** `core/hybrid_engine.py`, `core/ai_trader_persona.py`, `core/investor_persona.py`, `api/v1/endpoints/signals.py`, `tests/test_hybrid_engine.py`, `tests/unit/test_hybrid_engine.py`.

**Learning loop:** `main.py` (new background loop + startup wiring), `learning/scheduler.py` (no logic change, just a caller).

**Health:** `main.py`, `feature_store/service.py`, `backend/Dockerfile`, `docker-compose.yml`.

**Isolation:** `research_lab/base_repository.py` (or its replacement), `ml_training/registry/repository.py`, `ml_training/datasets/repository.py`, `model_serving/loader.py`, `tests/test_research_isolation.py`.

**Portfolio/paper-trading (P2):** `portfolio/analytics.py`, `paper_trading/config.py`, `paper_trading/execution.py`, `paper_trading/scheduler.py`, `core/market_config.py`.

## 5. Database Changes

- `ml_training_model_registry` (and any sibling tables keyed by model): no schema change required — `horizon_days` already exists there; the change is in how it's *used* downstream.
- A new column `horizon_days` on whatever table backs `learning_samples` (currently implicitly using the global `evaluation_horizon_days`), migrated with a backfill defaulting existing rows to the current global value (5), so no historical data is lost or misinterpreted.
- A new small table (or a JSON column on an existing calibration-related table) to persist each `aggregation_strategy_version`'s fitted calibration map (Finding 6) and signal→return map (Finding 7), once A2 is live long enough to fit them.
- No destructive migrations are required anywhere in this plan; every change is additive (new nullable/defaulted columns) until the data to populate them non-trivially exists.

## 6. API Contract Changes

- `DecisionOutput`/`EngineVote` (internal + anywhere re-exported, e.g. `PipelineResponse`'s own shape) gain `horizon_days`. Additive; existing consumers that ignore unknown fields are unaffected; version the change if any consumer does strict schema validation.
- `DecisionOutput.confidence` gains a sibling `consensus` field (today's value, renamed concept but same number) so no existing consumer silently gets a different number under the same field name without a visible accompanying field.
- `TradeRecommendation` / `HorizonView` (the `core/hybrid_engine.py` / `/api/v1/signals/analyze` response shapes) gain `signal_source`; `horizon_1_month`/`horizon_1_year` become nullable.
- New endpoint `GET /health/ready`. `/health` itself is contractually frozen (the existing backward-compatibility test enforces this).
- `/feature-store/health` changes its status code behavior (200→503 on failure) — this is a behavior change for any caller that only checked the body, not the status; flag this explicitly in the changelog since it's the one genuinely breaking change in this plan.

## 7. Test Plan

Each finding above already specifies its own required tests; consolidated by priority:

**P0 tests (must exist before any P0 fix ships):** the six rewritten `core/hybrid_engine.py` fallback tests (Finding 8); `/health/ready` dependency-failure tests (Finding 10); a learning-cycle-runs-on-schedule test (A2); an all-SELL-in-a-rising-market evaluator test and a hypothesis-outcome test (Finding 1); a split-boundary purge test parameterized over `horizon_days` (Finding 2).

**P1 tests:** mixed-vendor dataset-build assertion (Finding 3/A3); horizon-required-field construction tests (Finding 4); mixed-horizon aggregator-raises test (Finding 5); calibration-is-not-trivially-1.0 test (Finding 6, gated on A2 landing first); fitted-map-overrides-proxy test (Finding 7, same gate); nulled-out-unvalidated-horizon test (Finding 9); transitive-import-closure test (A1).

**P2 tests:** FX-converted-total-value test (A5); unpriced-position-flagged test (A6); per-market trading-hours test + scheduler-respects-hours test (A7); fill-then-sync-reconciliation test (A8).

**Regression gate:** the full existing backend suite must stay green throughout (it currently is, at ~3,157 passing per this session's own earlier work on an unrelated change) — in particular `test_main_backward_compatibility.py` and `test_research_isolation.py` (which will need deliberate, reviewed changes for A1, not accidental breakage).

## 8. Acceptance Criteria

- No code path reachable from a public endpoint can return an LLM-authored `signal`/`confidence_score` as a final trading decision. (F8)
- `/health/ready` returns a non-2xx status within 10 seconds of Postgres or Redis becoming unreachable, verified by a live chaos test (stop the container, observe the status flip) in addition to unit tests. (F10)
- `run_learning_cycle()` (or its successor) executes on a visible, logged schedule in production, confirmed by a new log line appearing at the expected cadence for at least 7 consecutive days post-deploy. (A2)
- A synthetic "always wrong" model cannot be ACCEPTED by `ModelEvaluator` regardless of market drift during its test window. (F1)
- No sample's `as_of` date appears in more than one of train/val/test, for every `horizon_days` value exercised in tests. (F2)
- `EngineVote`/`DecisionOutput` cannot be constructed without a horizon; `aggregate_votes()` rejects mixed-horizon input. (F4, F5)
- `horizon_1_month`/`horizon_1_year` are `null` (not an LLM opinion) until a real validated model exists for that horizon. (F9)

## 9. Migration and Rollback Plan

- **Additive-first rollout.** Every schema and API change above is additive (new nullable fields/columns) before it is made load-bearing, so a rollback at any point is a plain redeploy of the previous image with no data migration to reverse.
- **F8 (LLM boundary) ships independently and first** — it's a pure code change (strip fields, add provenance, change two `return` statements) with no schema dependency, lowest risk, highest severity. Feature-flag it only if there's a desire to stage the client-visible behavior change (previously-populated `horizon_1_month`/`horizon_1_year` signals going `null`); otherwise ship directly.
- **F10 (health) ships independently and second** — also pure code + Docker/Compose config, no schema dependency. Roll out the new `/health/ready` endpoint first, observe it in parallel with the existing healthcheck for a burn-in period, then switch the actual `HEALTHCHECK`/compose config over once confident it doesn't false-positive.
- **A2 (learning loop) ships third**, before F6/F7's calibration work, since those are explicitly blocked on it. Low risk — it only adds a new scheduled call to already-existing, already-tested logic. Rollback is removing the one new task from the startup list.
- **F1/F2 (evaluation correctness) ship fourth, as a pair**, and must land before any new model is promoted to ACTIVE in production — since zero models are ACTIVE today (per the live registry query in Finding 5), this has zero in-flight promotion to disrupt. No rollback concern beyond reverting the evaluator code.
- **F3/A3/A4 (provider unification) ship fifth** — touches the most call sites, so it's sequenced as its own change with its own full-suite regression run, after the lower-risk items above have already landed and proven the rollout rhythm.
- **F4/F5 (horizon field) ship sixth**, as the prerequisite for any Phase 2 work — additive field, default existing rows/votes to the current implicit 5-day convention so nothing currently running changes behavior until horizon-aware filtering is explicitly turned on.
- **F6/F7 (calibration, real expected-return)** ship only once A2 has been live long enough to have accumulated real evaluated outcomes — this is a data-readiness gate, not a code-readiness one; do not force it on a deadline.
- **A1 (isolation)** is a structural refactor with no runtime behavior change if done correctly; ship it whenever convenient, verified by the transitive-import test passing both before (red) and after (green) the module move.
- **P2 items (A5-A8)** are independent of everything else and each other; ship opportunistically.

## 10. Dependencies Between Phases

```
F8 (LLM boundary)         — independent, ship first
F10 (health)              — independent, ship first
A2 (learning loop live)   — independent, but gates F6 and F7
F1 + F2 (evaluation)      — independent of A2, but should land before any new
                            model promotion; gates nothing else directly
F3 + A3 + A4 (providers)  — independent, but should land before re-running any
                            training (to avoid re-polluting new labels the same way)
F4 (horizon field)        — gates F5 (mixing guard) and gates all of Phase 2
                            (no medium/long-horizon model can be safely served
                            without it)
F5 (mixing guard)         — depends on F4
F6 (calibration)          — depends on A2 (needs real evaluated outcomes)
F7 (real expected return) — depends on A2 (same reason)
F9 (LLM long horizons)    — can ship its "null until validated" mitigation
                            immediately (no dependency); fully resolving it
                            depends on F4 + new Phase-2 horizon models existing
A1 (isolation refactor)   — independent of all of the above
A5–A8 (portfolio/paper)   — independent of all of the above

Phase 2 (multi-horizon models) depends on: F4, F5, and ideally F1+F2 already
landed (no point validating a new horizon's models against a broken evaluator).

Phase 3 (crypto intelligence: funding/OI/liquidations/on-chain/tokenomics) has
no hard dependency on anything above, but should use the Finding A4 provider
pattern for any new data source rather than adding another direct-vendor
bypass.
```

# OptiTrade Quant Research Platform — Prediction Framework Methodology

Date: 2026-07-23

Status: **Methodology / scientific architecture only. No code, no implementation, no API
design.** This document is the scientific foundation underlying
`2026-07-23-quant-research-intelligence-platform-design.md` (Phase 1 architecture) and its
appended Critical Review & Revision. It answers what the platform's models should predict,
how labels and features are engineered, how the feature store, training pipeline, and
validation methodology work, how the system continuously learns, which statistical metrics
matter, and the multi-year model-evolution roadmap.

---

## 1. What Exactly Should the Models Predict

Every candidate target is evaluated against four criteria: is it (a) economically
meaningful, (b) statistically learnable at its horizon, (c) directly actionable by an
existing consumer (Trader Profile = short horizon, Investor Profile = long horizon), and
(d) non-redundant with other targets. Target proliferation — training many separately-labeled
models that are secretly asking overlapping questions — is itself a research-quality risk
(more surface area for overfitting, more multiple-comparison risk, more maintenance burden),
so consolidation is treated as a first-class design goal, not an afterthought.

### Tier 1 — Directly modeled

| Target | Type | Rationale |
|---|---|---|
| P(upward move \| horizon H) | Classification | Core primitive; calibratable; works at any horizon; foundation for BUY/SELL probability |
| Expected return \| horizon H | Regression | Magnitude matters — a 55%-confident 20% move and a 55%-confident 1% move are not the same decision; probability alone discards this |
| Volatility forecast \| horizon H | Regression | Necessary input to every risk-adjusted metric downstream (this system's existing ATR-based SL/TP is already an implicit volatility forecast); also independently informative (an expanding-volatility regime is itself a signal) |
| P(trend continuation) / P(trend reversal) | Two distinct regime-conditional classifiers | Genuinely different questions, not opposites — a market can be in neither state (regime-neutral); ties directly to `MarketRegimeScanner`'s existing classification |
| P(support breakout) / P(resistance rejection) | Event-conditional classifiers | Only meaningful/computed when price is near a known S/R level (ties to `PatternScanner`'s existing proximity features) — inherently conditional, not always-on |

### Tier 2 — Derived, not separately modeled

- **Risk-adjusted return** — computed post-hoc as `expected_return / volatility_forecast`, not trained directly on a historical Sharpe-like label. A ratio target has unstable variance (especially with a small/noisy denominator); training directly on it is statistically fragile compared to separately predicting the numerator and denominator.
- **Maximum drawdown** — NOT predicted directly. Forward max drawdown is a path-dependent, heavy-tailed extreme-value statistic, notoriously hard to regress on directly. Instead: simulate many price paths consistent with the predicted return/volatility distribution (Monte Carlo, §6) and compute max drawdown empirically from the simulated paths.
- **Momentum persistence, mean reversion probability, recovery probability** — collapsed into **one** conditional-return-distribution model (predict the forward return distribution conditioned on current state: recent return, regime, momentum), rather than three separately-labeled classifiers asking overlapping variants of "does the current move continue or reverse." Training three near-redundant targets triples overfitting surface for no real gain in decision-usefulness.

### Should NOT exist as primary targets

- **Next single-candle direction.** Lowest signal-to-noise horizon possible, effectively indistinguishable from noise in liquid markets, and not actionable for a product operating at daily-ish trade/investment cadence, not millisecond execution. Including it invites overfitting to noise and serves neither Trader nor Investor Profile's actual decision cadence.
- **Confidence calibration as a prediction target.** This is a *property of a model's outputs*, measured continuously (§8), not something to be labeled and predicted itself.

---

## 2. Label Engineering

Labels must match how the *consuming engine* actually uses the prediction — Trader-horizon
labels should be anchored to the same ATR-multiple convention `DynamicRiskManager` already
uses for SL/TP; Investor-horizon labels should be anchored to fixed calendar horizons
matching the existing `analysis_predictions.actual_price_7d/30d` reconciliation convention.

| Strategy | Pros | Cons | Recommended use |
|---|---|---|---|
| **Fixed percentage (+3%/+5%)** | Simple, easy to communicate | Not volatility-normalized — a fixed % move means wildly different difficulty across BIST equities, crypto, and US large-caps (OptiTrade's actual multi-asset universe), biasing training toward whichever asset class dominates the sample | Display-layer translation only, never the primary training label across a heterogeneous universe |
| **ATR multiples** | Naturally volatility-normalized across assets; directly consistent with the existing `DynamicRiskManager` risk convention | ATR is backward-looking/lagging — mislabels difficulty exactly when volatility regime is *changing* (often the most valuable prediction window); less intuitive to a non-technical end user, needs a translation layer | **Primary label for Trader-horizon targets** |
| **Time-based (fixed calendar horizon)** | Simple; matches Investor Profile's existing 1w/1m/1y framing and existing DB reconciliation columns exactly | Ignores *when within the window* the move happened (an early sharp move + reversion gets the same label as a smooth gradual move); doesn't adapt to how fast markets are actually moving | **Primary label for Investor-horizon targets** |
| **Event-based** | Labels are conditioned exactly on the situation the prediction is used in — the only correct approach for inherently conditional targets | Introduces selection bias / smaller effective sample (model only ever trained/evaluated on the triggering subpopulation — must never be deployed outside that same condition); requires a precise, versioned trigger definition | Support breakout / resistance rejection targets specifically, nowhere else |
| **Volatility-adjusted (z-scored return)** | Normalizes across assets *and* across time for the same asset's changing vol regime — more principled than raw ATR multiples over long, multi-regime histories | Requires a well-estimated, non-lagging vol model; the label now inherits the vol estimator's own error, compounding into "ground truth" label noise | Long-history, multi-regime training sets where a single asset spans very different vol eras |
| **Regime-adjusted (threshold varies by classified regime)** | Exploits `MarketRegimeScanner` classification already computed in this codebase; makes the same nominal target consistently meaningful across market conditions | Multiplies the label-design surface (regimes × horizons × targets), risking sparsity in each cell; risks subtle leakage if the regime classifier isn't strictly as-of-time-bounded | Combine with time-based/ATR labels as a conditioning dimension, not a fourth independent scheme |
| **Investor- vs Trader-horizon adjusted** | Each horizon gets a model genuinely fit to its own sample size/difficulty/feature relevance (short-horizon leans on microstructure/momentum; long-horizon leans on regime/macro) | Multiplies models to maintain; risks training on overlapping/autocorrelated windows, violating i.i.d. assumptions many standard CV routines implicitly assume | This is a policy, not a technique — apply it, but handle the resulting overlapping-labels problem explicitly in validation (§6, purged CV) |

**Recommendation**: primary label unit = ATR-multiple (Trader) / fixed-calendar-horizon
(Investor), both regime-conditioned, with raw-percentage and Profit-Factor-style framing
reserved for the user-facing translation layer only.

---

## 3. Feature Engineering Taxonomy

Classified by category, not by indicator. Each rated on: **why it matters**, **stability**,
**predictiveness**, **cost**.

**Trend** — Why: captures directional persistence, one of the most robustly documented
cross-asset anomalies in finance. Stability: high over long samples, but trend-following's
*value* is itself regime-dependent (well-documented multi-year drawdowns). Predictiveness:
high in trending regimes, low/negative in choppy ones. Cost: cheap (already computed —
`MarketRegimeScanner`'s R² trend strength).

**Momentum** — Why: distinct from Trend — captures acceleration/deceleration (2nd-order),
not raw persistence. Stability: lower than Trend, more sensitive to short-window noise.
Predictiveness: moderate, well-documented academically, but decays fast and prone to
"momentum crashes" at regime transitions. Cost: cheap (already computed — RSI/MACD/ROC).

**Volume** — Why: proxy for conviction/participation behind a move. Stability: moderate,
affected by non-informational events (rebalancing dates, options expiry, holidays);
requires relative (not absolute) normalization. Predictiveness: moderate, mostly a
confirming/filtering feature rather than a strong standalone predictor. Cost: cheap
(OHLCV volume already present).

**Volatility** — Why: both a risk measure (existing ATR-based SL/TP) and independently
predictive (volatility clustering is one of the most robust stylized facts in all of
quantitative finance). Stability: very high — recommend treating as the highest-confidence
feature category to invest in. Predictiveness: high, especially as the target and as a
normalizer for other features/labels. Cost: cheap-to-moderate.

**Market Structure** — Why: captures the "shape" of price action (S/R proximity,
higher-highs/higher-lows, consolidation geometry) — partially already built
(`PatternScanner`). Stability: moderate — level-detection is somewhat parameter-dependent,
but the underlying "price reacts near prior extremes" effect is well-documented.
Predictiveness: moderate, highly conditional — near-useless far from any identified level.
Cost: cheap-to-moderate.

**Liquidity** — Why: distinct from Volume — captures execution feasibility (spread, depth,
slippage), critical for BIST small-caps and thin crypto altcoins, both in OptiTrade's actual
universe. Stability: can change abruptly (a liquidity event is by definition sudden) — the
least stable category in tail scenarios even though stable day-to-day. Predictiveness:
moderate for execution/risk purposes. Cost: **currently a genuine data gap, not just an
engineering gap** — yfinance OHLCV has no bid-ask/order-book data; would require a new, likely
paid, data source. Recommend explicit deferral, named honestly rather than assumed solvable
in-place.

**News** — Why: captures information not yet priced in; this system already has a full News
Intelligence Pipeline (entity extraction, event classification, sentiment, impact). Stability:
low — sporadic/bursty by nature, and the same headline's impact varies by context (must
distinguish "no news today" from "confirmed neutral news," not collapse both to zero).
Predictiveness: potentially high but short-lived — decays within hours-to-days, a good fit
for Trader-horizon, weak fit for Investor-horizon unless aggregated into slow-moving
sentiment-trend features. Cost: moderate-to-high if LLM-based extraction/sentiment; cheaper
via the existing deterministic keyword classifiers.

**Macro** — Why: top-down systemic conditions — unusually important given OptiTrade's
BIST/Turkish-lira exposure, where FX/macro dominates more than for, e.g., US large-caps.
Stability: high at the definitional level (rate/inflation series are well-defined), low at
the relationship level (how macro maps to any given asset's returns shifts across cycles).
Predictiveness: low at Trader horizon, moderate-to-high at Investor horizon. Cost: moderate —
requires a genuinely new external data source (no macro/economic-calendar integration exists
today), though update cadence is low-frequency so ongoing operational cost is modest once built.

**Cross-Asset** — Why: spillover/contagion/co-movement (BTC dominance on altcoins, USD
strength on BIST) — currently completely absent; every symbol is analyzed in isolation
today. Stability: moderate — correlations are famously time-varying and spike toward 1
during crises, meaning this category is least reliable exactly when it would matter most.
Predictiveness: moderate-to-high, especially for regime-transition detection. Cost:
moderate — requires a cross-asset correlation matrix across the tracked universe (a real
architectural change from today's single-symbol-at-a-time design), but no new external
data source.

**Relative Strength** — Why: performance relative to a benchmark/peer/sector — a
well-documented equity-research factor; this codebase already has partial sector-mapping
infrastructure (`sector_mapper`/`sector_intelligence`). Stability: moderate-high.
Predictiveness: moderate, particularly for CROSS-SECTIONAL ranking (which symbol to
prioritize in a scan) more than single-symbol absolute prediction — a natural fit for the
existing "Piyasa Taraması" (market scan) UX. Cost: cheap-to-moderate.

**Seasonality** — Why: calendar-effect regularities (day-of-week, month-of-year, "sell in
May"). Stability: **low** — a well-documented finding is that classic calendar anomalies
shrink/disappear once widely publicized ("factor decay from crowding"); an honest caveat an
institutional reviewer would specifically probe. Predictiveness: low-to-moderate, likely the
weakest category overall. Cost: essentially free (calendar arithmetic on existing
timestamps) — low risk/low reward, include as a minor supplementary feature only.

**Behavioral** — Why: crowd psychology / sentiment-driven mispricing distinct from
fundamental news — extreme-RSI-as-euphoria/panic, attention/search-trend proxies where
available. Stability: low-moderate — regime/fad-dependent, and any novel social/search data
source is itself noisy and platform-artifact-prone. Predictiveness: potentially high during
extreme/tail episodes specifically (bubbles, panics), low-value as a steady-state feature —
a "fat-tailed value" category: mostly unremarkable, occasionally very informative. Cost:
moderate-to-high for genuinely new behavioral data sources; cheap for price-derived proxies
already implicit in existing RSI/momentum extremes (a first approximation doesn't require
new data).

**Market Regime** — Why: the meta-feature category — not a new information source but a
contextualizer for how to weight/interpret every other category; already computed
(`MarketRegimeScanner`). Stability: the classification scheme is stable; which regime is
currently active is, by definition, exactly what changes. Predictiveness: not predictive
alone, but massively increases the *conditional* predictiveness of every other category
when used as an interaction variable — one of the highest-leverage architectural
investments available. Cost: cheap (already computed).

**Risk** — Why: distinct from Volatility — captures tail/asymmetry properties (skew,
kurtosis, downside deviation, beta-to-market), needed for the derived risk-adjusted/max-DD
targets (§1). Stability: moderate — tail statistics need longer samples for stable
estimates than mean/variance statistics, a genuine estimation-difficulty caveat. Predictiveness:
moderate, mostly useful as context/normalizer rather than a standalone directional
predictor. Cost: cheap-to-moderate (computable from existing OHLCV history, needs
sufficient depth for stable tail estimates).

---

## 4. Feature Store — Production-Grade Design

**Feature versioning**: every feature *definition* gets a stable `feature_name` +
`feature_version`. A computation-logic change (e.g., RSI smoothing window 14→21), even
keeping the same name, is a new version — never a silent redefinition. This is the same
discipline as `engine_version` in the Phase 1 architecture, applied one level below: an
engine's version implicitly bundles a specific set of `feature_name@version` dependencies;
feature versioning is finer-grained and reusable *across* engines.

**Feature lineage**: every stored feature value traces to (a) which `feature_name@version`
computed it, (b) which raw input data (specific OHLCV rows/news items/macro points, each
with their own as-of timestamp) fed it, (c) which engine(s) consumed it downstream. Essential
for debugging a bad prediction after the fact, and for knowing what to invalidate/recompute
when an upstream data correction (e.g., an OHLCV backfill) happens.

**Point-in-time correctness**: the single most important property, implementing the
mandatory `AsOfDataAccessor` (from the architecture's Critical Review) at the feature-store
layer. Every feature value must be retrievable with an explicit as-of timestamp representing
exactly what was *knowable* at that moment — critically accounting for **reporting lag**:
a fundamentals feature must be timestamped by its actual *publication/availability* time,
not the *period it describes* (a Q3 earnings figure is not knowable until weeks after Q3
ends). This is a distinct, easy-to-miss lookahead-bias vector separate from the
OHLCV-level one already addressed.

**Feature freshness**: every feature has a defined expected update cadence (near-real-time
for price/volume-derived, daily for most technical/regime features, much slower for
macro/fundamental). The store tracks staleness (`age_seconds`/`is_stale`) as a first-class
queryable property, so a consuming engine makes a *visible, explicit* choice about proceeding
with stale data, rather than silently using outdated fundamentals unnoticed.

**Feature validation**: schema/range/distribution checks at write time, not just at
training time — an RSI value outside [0,100] indicates a computation bug and should be
quarantined immediately, not silently written and discovered weeks later via degraded
downstream accuracy.

**Feature monitoring**: ongoing tracking of null-rate per feature, distributional drift over
time, and *actual usage* (does a feature ever meaningfully contribute to any engine's
evidence/score, or has it become dead weight — directly feeds the obsolescence question in
§7).

**Feature reuse**: the entire justification for a shared store over each engine computing
its own privately — the same underlying feature (`atr_14`, `regime_classification`,
`news_sentiment_30d_avg`) is computed exactly once and consumed by multiple engines,
directly closing the "no feature store" gap named in the Critical Review and giving
`EvidenceItem.key` a disciplined home instead of an ad-hoc per-engine string.

**Online vs. offline features**: two serving paths sharing *one* definition/computation
implementation, to avoid training/serving skew (a classic, well-documented production ML
bug where offline-training and online-serving implementations of "the same" feature subtly
diverge). Offline = large-batch computation over history for training/backtesting (via
`AsOfDataAccessor`); online = low-latency retrieval for a live request — this project's
existing Redis `TTLCache`/`RedisCacheManager` is a natural online/hot layer, PostgreSQL the
offline/historical layer, directly matching this project's own previously-noted "L1 Redis +
L2 PostgreSQL, versioned" feature-store plan.

---

## 5. Training Dataset Construction

**Building the dataset**: for every `(symbol, as-of-timestamp)` pair in the historical
universe, join the feature vector *as it would have been knowable* at that timestamp
(via the feature store, §4) with the forward label (computed strictly after that timestamp,
per §2). This join is the single most safety-critical operation in the whole pipeline and
must use the *same* `AsOfDataAccessor` abstraction used in live serving and backtesting —
never a bespoke "training data builder" that duplicates, and risks diverging from, that logic.

**Missing data handling**: distinguish "genuinely doesn't apply" (no fundamentals for a
crypto asset — a stable, predictable characteristic, safely encoded as a categorical
"not applicable" state) from "should exist but doesn't" (a provider gap for an equity that
normally has fundamentals — a genuine data-quality issue to flag, not silently impute).
For genuine gaps: forward-fill with an explicit staleness-age companion feature, never mean/
median imputation (which erases informative "we don't actually know" signal). Never impute
using information from *after* the as-of timestamp — an easy, deceptive way to reintroduce
lookahead bias via a seemingly innocent imputation step.

**Survivorship bias avoidance**: the historical training universe must include symbols later
delisted/bankrupted/removed — not only symbols that happen to still exist today. This means
maintaining a **point-in-time symbol universe/membership list** (which symbols were tracked
at each historical date, including since-delisted ones), not simply querying "today's
watchlist, backfilled N years" — exactly how survivorship bias silently creeps in. This is a
currently unaddressed gap: today's yfinance-based, per-symbol-on-demand fetching has no
concept of point-in-time universe membership at all.

**Lookahead bias prevention**: enforced structurally via the mandatory `AsOfDataAccessor` as
the *only* sanctioned way any research/training/backtesting code accesses historical data —
no direct raw-table queries permitted anywhere in that code path. Additionally, labels must
never leak into features even indirectly via a correlated, imprecisely-time-aligned
feature (e.g., a trailing-return feature ending too close to a forward-return label's start).

**Data leakage detection**: beyond structural prevention, add empirical detection —
check a new feature's correlation against a deliberately shuffled or future-shifted version
of itself (a feature that "predicts" its own shuffled counterpart well is a red flag).
Heuristically: any single feature achieving implausibly high standalone accuracy on a task
known to be hard (e.g., >90% on short-horizon direction) should trigger a leakage
investigation, not celebration.

---

## 6. Validation Methodology

**Walk-Forward Validation** — train on an expanding or fixed rolling window, test on the
immediately-following out-of-time period, roll forward, repeat. The gold-standard method
because it's the *only* scheme that exactly mimics production use (always trained on the
past, evaluated on data it couldn't have seen). Should be the primary validation method for
every model/engine in this system, not an optional extra.

**Rolling Validation** — a fixed-size (not expanding) sliding window variant, used
specifically to answer whether performance is stable across regimes/eras, and whether more
historical data actually helps or whether market non-stationarity means older data hurts —
an empirical question, not an assumption.

**Time-Series Cross-Validation (blocked/purged)** — standard random-shuffle k-fold is *wrong*
for time series (lets a model train on data from after its test fold, a direct lookahead
violation). The safe variant uses contiguous blocked folds with a purge gap removing the
overlapping-label leakage described in §5. Use specifically for hyperparameter tuning (many
fast cycles walk-forward can't practically provide) — walk-forward remains the *final*
evaluation; never tune and finally-validate on the same folds, or the "final" number is
contaminated by the tuning process having seen it.

**Stress Testing** — deliberately evaluate behavior during specific known historical extreme
events (2020 COVID crash, 2022 rate-hike cycle, a specific BIST/lira crisis period, a
specific crypto crash), because average walk-forward performance across all history can mask
catastrophic failure in exactly the tail scenarios that matter most for real capital and user
trust. A mandatory, named, curated scenario set, re-run on every model/engine change — not
an occasional ad-hoc check.

**Monte Carlo** — used for simulation-based derived-target estimation, directly enabling
§1's recommendation that max drawdown be simulated (many price paths consistent with the
predicted return/volatility distribution) rather than directly regressed.

**Bootstrap** — used to estimate uncertainty around a performance metric itself (resampling
historical returns/predictions with replacement to build a confidence interval around a
Sharpe ratio or accuracy estimate) — directly answers the Critical Review's "no statistical
significance in benchmarking" gap.

**Out-of-Sample Validation** — the most basic, non-negotiable discipline: a genuinely
held-out slice never touched during any development, feature-selection, or tuning decision,
reserved exclusively for the final go/no-go gate before a model version is promoted to
shadow/production. Distinct from walk-forward's rolling folds (which, across many
development iterations, risk becoming implicitly tuned-to even if each fold was technically
out-of-time) — a true holdout should be consulted rarely, ideally once, at the final gate.

---

## 7. Continuous Learning — Obsolescence and Promotion

**Obsolescence detection**: the primary signal is a feature/engine's contribution weight
(Decision Engine's accuracy-derived weight for engines; permutation/SHAP-style attribution
for features within an engine) trending toward zero over a *sustained* rolling window — not
a single bad period, which could be regime-related and temporary. Critically distinguish:
- **Genuinely obsolete** (stopped working, e.g., a well-known calendar anomaly arbitraged
  away — ties to the Seasonality caveat in §3) — weak across *all* regimes over a long
  window.
- **Regime-dormant** (currently unhelpful because the prevailing regime doesn't suit it,
  e.g., a trend-following feature during a prolonged choppy period, but will matter again) —
  weak only in the *currently* prevailing regime.

The regime-conditional accuracy tracking already built into the Phase 1 architecture's
revision is exactly what makes this distinction possible. Nothing is dropped the moment it
looks weak — a formal "deprecation candidate" status with a defined minimum evaluation
window is required first, avoiding a whipsaw where something is removed just before
conditions shift back in its favor.

**Promotion of new candidates**: every new feature/indicator/engine enters as a shadow
candidate (per the Critical Review's shadow-mode mechanism) — computed and logged, never
yet contributing to a live decision or weight. Promotion requires: (a) statistically
significant standalone predictive value over a minimum sample/time window (not "looked good
for two weeks"), (b) *incremental* value on top of what already exists (a new feature highly
correlated with an existing one adds cost without real diversification — the same
correlation-matrix discipline recommended for engines in the Critical Review, applied to
candidate features too), (c) passing the same stress-test scenarios (§6) as existing
components.

These are two genuinely distinct continuous-learning mechanisms operating at different
timescales, worth not conflating: the Decision Engine's accuracy-reweighting loop (Phase 1
architecture) continuously adjusts *existing* engines' influence; this shadow/promotion
process governs whether to *add or remove* engines/features from the roster at all.

---

## 8. Statistical Evaluation — Which Metrics Matter, When

**Precision / Recall / F1** — meaningful for classification-style targets with genuine class
imbalance (e.g., "support breakout" events are rare). Precision answers "when the model says
X, how often is it right" (matters when false positives are costly); Recall answers "of all
actual X, how many were caught" (matters when missing an opportunity is costly). F1 is a
useful single-number compromise for internal model comparison during development — never
the sole metric reported to a user or used alone as a promotion gate, since it hides
exactly the precision/recall trade-off that matters for how a prediction gets *used*.

**ROC / AUC** — useful for ranking ability independent of a specific decision threshold;
strong fit for the cross-sectional ranking use case (§3's Relative Strength tie-in — "which
symbol, among many, is most likely to move" is fundamentally a ranking task). Less relevant
for a single-symbol, threshold-based, user-facing BUY/SELL/HOLD decision, where the *chosen
operating threshold* matters more than ranking quality across all possible thresholds.

**Calibration Error (ECE, reliability diagrams)** — arguably the single most important
metric for this specific platform, given Explainable AI and end-user trust are named
non-negotiable requirements. Directly operationalizes `confidence_calibration` from the
Phase 1 architecture. A model can have decent accuracy but terrible calibration (routinely
"90% confident" while actually right 60% of the time) — for a product literally showing a
confidence number to non-expert retail users, calibration error should be a **mandatory
promotion gate**, weighted more heavily here than in a typical anonymous internal
trading-signal context, precisely because the confidence figure is directly user-facing and
trust-load-bearing.

**Sharpe Ratio** — meaningful *only* when evaluating a full simulated trading strategy
(entries/exits/sizing through a realistic-cost backtest), never as a raw evaluation of a
bare classification/regression metric — good classification accuracy does not automatically
translate to a good Sharpe ratio, since Sharpe also depends on position sizing, costs, and
win/loss asymmetry. Use at the full-backtest level (§6), not the model-evaluation level.

**Sortino Ratio** — penalizes only downside volatility, more appropriate than Sharpe for
this product's actual user framing (users care about drawdown/loss risk, not "too much
upside volatility," which nobody complains about). Recommend as the *primary* risk-adjusted
backtest metric, with Sharpe reported alongside for standard external comparability.

**Profit Factor** (gross profit / gross loss) — intuitive and directly explainable to a
non-expert Turkish-language retail audience ("for every 1 lira lost, this made X lira").
Valuable specifically for interpretability even though statistically cruder than
Sharpe/Sortino (ignores return timing/variance) — a good user-facing/marketing-adjacent
metric, not sufficient alone as an internal research-quality gate.

**Max Drawdown** — meaningful as a realized backtest statistic (distinct from §1's point
that it must not be directly *modeled*). Essential for risk communication and stress testing
(§6). Report alongside its own uncertainty — a single historical max-drawdown figure from
one backtest run is itself a noisy, small-sample statistic; pair with Monte-Carlo-simulated
drawdown *distributions*, not just the one historically-realized number.

**Expected Value** (P(win)×avg_win − P(loss)×avg_loss) — arguably the most directly
decision-relevant metric in this whole list for a retail user deciding whether to act,
combining the classification-style probability and the regression-style
expected-return/magnitude from §1's Tier 1 targets into one actionable number. Recommend
this as the headline metric most prominently surfaced in the actual product-facing
recommendation — the natural bridge between internal model-quality metrics
(precision/recall/AUC/calibration) and user-facing decision value
(Sharpe/Sortino/Profit-Factor/Expected-Value).

---

## 9. Model Evolution Roadmap

**Stage 0 — Current Rule Engine (today)**: deterministic, hand-tuned threshold/weight rules
(`core/scoring.py`, existing `signals/technical.py`/`fundamental.py` hand-set confidence
values). Strength: maximally explainable, zero training-data requirement. Weakness: weights
are hand-tuned by intuition, cannot adapt to changing feature-outcome relationships without
manual re-tuning.

**→ Gradient Boosting**: triggered once the Feature Store (§4) and Training Dataset pipeline
(§5) exist with sufficient point-in-time-correct historical sample. GBMs (LightGBM/XGBoost-
style — a "ML confidence" component already exists in `core.ml_predictor`) are the natural
first upgrade: highly capable on tabular engineered features (exactly this system's taxonomy
from §3) without deep-learning-scale data requirements, offer built-in feature-importance/
SHAP-style attribution (preserving explainability far better than most alternatives), and are
cheap to retrain frequently, fitting naturally into the walk-forward/continuous-learning
cadence. This stage replaces hand-tuned *weights* within each rule-based engine while
keeping the same feature categories — a data-sets-the-weights upgrade, not yet a wholesale
architecture change.

**→ Ensemble Learning**: triggered once multiple GBM models exist across engines/horizons/
asset-classes and their outputs become worth combining more sophisticatedly than the
Phase 1 accuracy-weighted voting scheme — stacking models trained on different feature
subsets/time windows captures complementary error patterns. A natural, low-risk evolution of
the already-pluggable `AggregationStrategy` protocol, not a new architectural primitive
(this is exactly where the previously-deferred `StackedMetaModel` strategy would land).

**→ Temporal Models**: triggered once the tabular-feature ceiling is reached — GBMs on
engineered features (RSI-at-T, ATR-at-T) discard sequence information beyond each feature's
manually-encoded lookback window. Temporal models (LSTMs, Temporal Convolutional Networks,
simpler state-space/HMM-style regime models) learn sequence-dependent patterns directly.
Best fit: the inherently path-dependent regime-transition-prediction use case, more so than
simpler single-snapshot directional targets, where GBM-on-engineered-features likely remains
competitive and more explainable for longer.

**→ Deep Learning**: triggered once (a) sufficient data volume exists — an honest caveat:
deep learning is *not* automatically better, and for tabular financial features GBMs are
frequently still state-of-the-art in both academic and industry practice; this transition
must be evidence-driven, not assumed inevitable — and (b) genuinely unstructured data
becomes central (full-text news embeddings rather than keyword/entity extraction, raw
order-book sequences if Liquidity features are ever built). Deep learning's comparative
advantage is representation learning from raw/unstructured inputs, a different use case than
"combine 40 engineered numeric features better."

**→ Hybrid AI**: this is essentially where the system already, partially, is *today*
(`AITraderPersona`/`InvestorPersona` combining LLM reasoning with structured upstream
signals). This roadmap stage is the deliberate, disciplined maturation of today's ad-hoc
LLM-persona pattern into a properly integrated hybrid system: deterministic/ML models handle
what they're empirically best at (calibrated numeric probability/score generation — §1's
Tier 1/2 targets); LLM components handle what they're uniquely good at (synthesizing
heterogeneous evidence — numeric + textual + regime — into coherent, context-aware
narrative, and handling genuinely novel situations no fixed architecture was trained for).
Critically, per the Phase 1 architecture's own rule, the LLM's role at this mature stage is
explanation/synthesis, **never** independent decision authority — a meaningfully more
disciplined role than how `AITraderPersona` uses the LLM today.

**→ Future Architecture** (named directionally, not committed to): reinforcement-learning
position-sizing/execution-policy layers (a genuinely *different* problem from directional
prediction — RL suits sequential portfolio-construction problems, not "predict the label"
problems, an important scoping distinction, since RL is often reached for prematurely in
retail-fintech contexts); causal-inference-based feature validation (moving beyond
correlational feature importance to ask *why* a feature works, mattering increasingly as
the cost of a subtly spurious feature grows with scale); foundation-model-style pretrained
financial-time-series embeddings (an active, fast-moving, genuinely unproven research area).
Naming these as "Future" rather than designing them now is the same discipline the Critical
Review's "possible overengineering" section argued for — don't build machinery for a need
that hasn't been empirically demonstrated yet.

---

## Explicit non-goals of this document (per instruction)

No code. No implementation plan. No API design. This is methodology and scientific
architecture only, intended as the research foundation that a future, separately-approved
implementation plan would draw from.

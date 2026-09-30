# Claude Build Specification - Finance AI Platform

Use this document together with `investment_ai_system_schema.md` and `investment_ai_blueprint.pdf`.

## Mission

Build a research-first financial AI platform for stocks and cryptocurrencies. The platform must support long-, medium-, and short-horizon analysis, with an independent risk/execution layer and a source-linked LLM explanation layer.

## Non-negotiable architecture

```text
Data Connectors
  -> Point-in-Time Storage
  -> Feature Store
  -> Horizon Models
  -> Regime Detector + Risk Engine
  -> Decision Engine
  -> LLM Explanation
  -> FastAPI
  -> UI
```

## Phase 1 - foundation

Create:
- Python 3.12 project
- FastAPI
- PostgreSQL + migrations
- Pydantic settings
- structured logging
- pytest
- ruff + mypy
- Docker Compose
- clear module boundaries

Suggested modules:

```text
src/
  api/
  config/
  domain/
  data/
    connectors/
    ingestion/
    normalization/
    point_in_time/
  features/
    stocks/
    crypto/
    macro/
    news/
  models/
    long_horizon/
    medium_horizon/
    short_horizon/
    volatility/
    regime/
  risk/
  backtest/
  decision/
  llm/
  evidence/
  registry/
  monitoring/
  tests/
```

## Phase 2 - data contracts

Implement canonical entities for:
- Asset
- MarketBar
- FundamentalObservation
- MacroObservation
- NewsEvent
- OnChainObservation
- DerivativeObservation
- FeatureObservation
- Prediction
- RiskAssessment
- DecisionObject
- Evidence
- BacktestRun
- ModelVersion

All time-sensitive facts must include availability/published timestamps.

## Phase 3 - feature registry

Implement versioned calculators. Start with a minimum robust set:

Stocks:
- 5D/20D/60D/252D returns
- relative momentum vs index/sector
- 20D/60D volatility
- ADV, spread, turnover
- P/E, EV/EBITDA, FCF yield
- ROIC, ROE, margins, FCF conversion
- revenue/EPS/FCF growth
- EPS/revenue surprise
- EPS revisions 30D/90D
- net debt/EBITDA
- dilution/SBC
- short interest/days to cover
- macro state features

Crypto:
- momentum/volatility/liquidity
- market cap/FDV/supply
- unlock/ADV ratio
- fees/revenue/TVL growth
- exchange netflows
- MVRV/SOPR-like metrics where data is available
- funding/OI/basis/liquidations
- order imbalance/depth/spread

## Phase 4 - labels

Create targets for:
- 1D, 5D, 20D, 60D, 126D, 252D excess/residual return
- threshold-crossing probabilities
- future realized volatility
- MFE/MAE
- triple-barrier outcomes

Use chronological data splits. No random train/test split for the main evaluation.

## Phase 5 - baseline models

Start with:
- naive baseline
- logistic/linear baseline
- LightGBM/CatBoost
- volatility baseline
- simple regime classifier

Do not introduce transformers until the baseline is stable and leakage-tested.

## Phase 6 - backtest engine

Must model:
- fees
- spread
- slippage
- funding
- borrow cost when applicable
- turnover
- position sizing
- liquidity constraints
- concentration limits

Report gross and net metrics separately.

Use walk-forward validation; for overlapping labels use purge/embargo logic.

## Phase 7 - news LLM

The LLM must output structured event objects only. Required fields:
- asset
- event_type
- direction
- materiality
- novelty
- certainty
- expectedness
- horizon
- source_quality
- published_at

Every extracted event must retain source references. The LLM must not invent facts, prices or dates.

## Phase 8 - decision engine

Combine:
- expected return
- directional probability
- volatility/tail risk
- liquidity/execution quality
- transaction costs
- regime state

Return `LONG`, `SHORT`, `NEUTRAL`, or `NO_TRADE` only according to the configured product policy. Do not force a trade.

## Phase 9 - UI contract

For each asset show:
- Long-term view
- Medium-term view
- Short-term view
- Expected return
- Directional probability
- Risk
- Regime
- Catalysts
- Risks
- Invalidation conditions
- Model confidence
- Data confidence
- Execution confidence
- Evidence/source list

## Phase 10 - safety / product boundary

V1 is research/backtest/simulation-first. Do not enable autonomous live trading.

For any personalized investment recommendation or order-execution capability, stop and require a separate compliance/legal design review for each target jurisdiction.

## Definition of done

The first release is successful when:
1. Data is point-in-time and leakage tests pass.
2. Baseline models beat trivial benchmarks out-of-sample, after costs where applicable.
3. Calibration is reported, not just accuracy.
4. Results are broken down by market regime.
5. The same DecisionObject works for both stocks and crypto.
6. LLM explanations are source-linked to structured evidence.
7. The system can answer `NO_TRADE`.
8. Every model run is reproducible from versioned data and features.

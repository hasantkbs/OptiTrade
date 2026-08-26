"""Tests for engines/fundamental/config.py."""
from engines.fundamental.config import ALL_FEATURE_NAMES, FundamentalEngineConfig


def test_all_feature_names_has_no_duplicates():
    assert len(ALL_FEATURE_NAMES) == len(set(ALL_FEATURE_NAMES))


def test_all_feature_names_covers_every_requested_category():
    joined = " ".join(ALL_FEATURE_NAMES)
    for expected_substring in (
        "pe_ratio", "peg", "price_to_sales", "price_to_book", "ev_to_ebitda",
        "revenue_growth", "eps_growth", "operating_income_growth", "fcf_growth",
        "gross_margin", "operating_margin", "net_margin", "roe", "roa", "roic",
        "debt_to_equity", "current_ratio", "quick_ratio", "interest_coverage", "altman_z",
        "operating_cash_flow_margin", "free_cash_flow_margin", "cash_conversion",
        "earnings_consistency", "margin_stability", "capital_efficiency", "balance_sheet_quality",
    ):
        assert expected_substring in joined, f"missing feature category: {expected_substring}"


def test_config_from_env_defaults(monkeypatch):
    for key in (
        "FUNDAMENTAL_ENGINE_MAX_FEATURE_AGE_SECONDS", "FUNDAMENTAL_ENGINE_DECISION_THRESHOLD",
        "FUNDAMENTAL_ENGINE_EXPECTED_RETURN_SCALE_PCT", "FUNDAMENTAL_ENGINE_VERSION",
    ):
        monkeypatch.delenv(key, raising=False)

    config = FundamentalEngineConfig.from_env()
    assert config.max_feature_age_seconds == 86400
    assert config.decision_threshold == 0.2
    assert config.expected_return_scale_pct == 10.0
    assert config.engine_version == "v1"


def test_config_from_env_reads_overrides(monkeypatch):
    monkeypatch.setenv("FUNDAMENTAL_ENGINE_MAX_FEATURE_AGE_SECONDS", "3600")
    monkeypatch.setenv("FUNDAMENTAL_ENGINE_VERSION", "v2")

    config = FundamentalEngineConfig.from_env()
    assert config.max_feature_age_seconds == 3600
    assert config.engine_version == "v2"


def test_config_is_frozen():
    config = FundamentalEngineConfig()
    try:
        config.decision_threshold = 0.9  # type: ignore[misc]
        assert False, "expected an error assigning to a frozen dataclass"
    except AttributeError:
        pass
